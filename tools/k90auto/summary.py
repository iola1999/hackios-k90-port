#!/usr/bin/env python3
"""Summarize unattended K90 desktop runs: frame pacing, GL frame times, CPU levels, temperatures,
panics and screenshot checks, one row per run directory (made by run-auto.py).

usage: tools/k90auto/summary.py [--markdown] [--windows] [--verify] RUN_DIR...

Frame figures count only windows that report at least 20 frames and at least 10 a second, which is what
an animation on screen looks like; a static screen redraws a few times over tens of seconds. Two frame
rates are printed: fps divides the window's frames by its whole span, as the driver's line does, so a
window that ends in a static stretch is understated; fps_mv counts only the intervals under FRAME_PAUSE
(90 ms) and divides those, so it measures the animation alone. static is the share of the counted
windows' span that no frame followed within FRAME_PAUSE. --verify checks that the merged log holds every
frame window any snapshot of the run held, and exits 1 when one is missing.
ff_s is the seconds the round held its top clock bin, counted in the kernel's own 30 s domain-1
histograms from the first one the round logged; --verify prints the same figure with the window counts
and the hottest readings beside it. A frame rate says how fast frames came, this says at what clock they
came, and the acceptance criterion needs both: the same rate at a lowered ceiling is a different result.
Screenshots: raw BGRA 1156x2510 (shot-*.raw) or the PNGs sheets.sh made of them (png/shot-*.png);
the check counts the status-bar blue of the wallpaper in the rows below the GMEM bin boundary, where
the framebuffer-fetch fault of 2026-10-25 put it.
"""
import glob
import json
import os
from collections import Counter
from pathlib import Path
import re
import subprocess
import sys

WIDTH, HEIGHT, STRIDE = 1156, 2510, 1156 * 4
BAND = (1286, 1400, 100, 1100)          # rows and columns, panel coordinates
BLUE = (9, 126, 201)                    # RGB, with a tolerance of 5 to 6
FRAME_PAUSE = 90                        # ms; the driver's FRAME_PAUSE, from here on nothing was moving

WINDOW_HEAD = re.compile(r'MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\)')
WINDOW_LINE = re.compile(r'^MiniIOMobileFramebuffer: \d+ frames in .*$', re.M)
# The second half of the driver's window line, which the distribution regex above skips over on its way
# to "from one frame to the next:". It is read separately so the group indices that half already has
# stay where they are. "us for the next refresh" is the driver's own count of the beat wait, the
# clock_delay_until() in MiniIOMobileFramebuffer.cpp show(); it is the largest single piece of a frame
# at 60 Hz and until now it had to be recovered by subtracting two other readings. The three counts
# after it are how often a swap had to wait for the one before, gave up, or was itself late: all three
# read 0 in round C, which is what makes "the driver never made CoreAnimation wait" a reading rather
# than an inference.
WINDOW_BEAT = re.compile(
    r'MiniIOMobileFramebuffer: \d+ frames in \d+ ms \(\d+ a second\), \d+ us each in the driver, '
    r'after \d+ us waiting for the GPU and, (\d+) of them, (\d+) us for the next refresh; '
    r'(\d+) swaps waited for the frame before, (\d+) gave up; '
    r'(\d+) swaps came a refresh late themselves')
FRAME = re.compile(r'tl: v \d+ ready (\d+) shown')
FRAME_LINE = re.compile(r'^tl: v \d+ ready .*$', re.M)


def overlap(text, chunk, probes=(262144, 65536, 16384, 4096, 1024, 256, 64)):
    """Where the chunk's new content starts: the offset in the chunk just past the text's last bytes, or
    0 when nothing of the text's end can be found. The loader's log is a ring, so a snapshot holds the
    oldest lines it still had, then the newest: the text ends with the previous snapshot's newest lines,
    and those appear in the chunk only at the ring's write point.

    Two cases need no search. While the ring is filling the chunk is the text plus new lines, so the text
    is a prefix of it. A chunk that is a suffix of the text carries nothing new.

    The search takes the text's tail in the largest pieces first: a short piece can occur more than once,
    because a stretch of repeated log lines is written twice, and anchoring at the wrong copy either
    drops the lines between the two or appends a stretch twice. 256 KB of consecutive log lines is one
    place in a run. The first occurrence wins: an earlier copy is the same lines written before, and the
    copy that ends the text's own content is the one whose continuation is new."""
    if chunk.startswith(text):
        return len(text)
    if len(chunk) <= len(text) and text.endswith(chunk):
        return len(chunk)
    for size in probes:
        if size > len(text):
            continue
        piece = text[-size:]
        at = chunk.find(piece)
        while at >= 0:
            if chunk[at:at + size] == piece:
                return at + size
            at = chunk.find(piece, at + 1)
    return 0


def log_files(run):
    """Every file of one run that holds loader log content, in merge order.

    The harness pulls the ring again on the teardown paths, so a run can end with a file no s*.log
    covers: the biomed round's hung-held.log held 489 frame lines past its last snapshot. verify() has
    to expect the same set this returns, or those lines read as content the merge invented.
    hung-held-serial.log stays out: it is the serial console, another source than the ring."""
    logs = sorted(glob.glob(os.path.join(run, 's[0-9]*.log')))   # (s*.log would also take system-upload.log)
    for name in ('returned.log', 'hung-held.log', 'running.log'):
        if os.path.exists(os.path.join(run, name)):
            logs.append(os.path.join(run, name))
    return logs


def round_dir(path):
    """The round directory, whichever of its two levels the caller passed.

    Every reader here joins 'run' onto the round directory, so passing <round>/run used to look for
    <round>/run/run, find nothing, and print a row of zeros with exit code 0. gestures.py takes the
    other level, which is how the two got mixed up. Both levels resolve to the same directory now."""
    p = path.rstrip('/')
    if os.path.isdir(os.path.join(p, 'run')):
        return p
    if os.path.basename(p) == 'run':
        return os.path.dirname(p)
    return p


def merged_log(run):
    """Everything the loader's log ring held at any point in the run. Each s*.log is what the ring held
    when the harness pulled it, so consecutive snapshots overlap and the last one has already lost what
    the ring dropped: reading only the last one reports no frame window for a run that had them."""
    text = ''
    for path in log_files(run):
        chunk = Path(path).read_text(errors='replace').replace('\x00', '')
        if not text:
            text = chunk
            continue
        cut = overlap(text, chunk)
        text += chunk[cut:]
    return text


def window_list(text):
    """Every frame window the log printed, in order, each with the frames it covers and with its
    numbers when its distribution line survived. A window's frames are those since the window before
    it closed; the driver keeps its last-frame mark across windows, so the interval from that frame to
    this window's first counts here and nowhere else. Only touch_lat=1 runs print the frame lines, and
    a window whose distribution the ring cut has no numbers: it is listed all the same. 'beat' holds the
    window's beat-wait and swap-queue counts, read by their own regex, and is None on the same terms."""
    numbers = {m.start(): m.groups() for m in re.finditer(
        r'MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\), (\d+) us each in the driver, '
        r'after (\d+) us waiting(?:(?!MiniIOMobileFramebuffer: \d+ frames in).)*?from one frame to the next: '
        r'(\d+) times under 10 ms, (\d+) under 18, (\d+) under 26, (\d+) under 35, (\d+) longer', text, re.S)}
    beat = {m.start(): m.groups() for m in WINDOW_BEAT.finditer(text)}
    out, frames = [], []
    for m in re.finditer(r'tl: v \d+ ready (\d+) shown|MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms \((\d+) a second\)', text):
        if m.group(1):
            frames.append(int(m.group(1)) / 1000)       # microseconds to ms
            continue
        out.append({'frames': frames, 'numbers': numbers.get(m.start()), 'beat': beat.get(m.start())})
        frames = []
    return out


def moving(window):
    """Frames of one window that followed their predecessor within FRAME_PAUSE, and the time those
    intervals took. Frames after a longer gap are counted in no moving figure: that is a screen which
    had nothing to show, and the driver's own histogram leaves them out too."""
    frames = window['frames']
    intervals = [b - a for a, b in zip(frames, frames[1:])]
    quick = [x for x in intervals if x < FRAME_PAUSE]
    return len(quick), sum(quick)


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))] if values else 0


def band_hits(pixels, rgba_order):
    try:
        import numpy as np
    except ImportError:
        return None
    a = np.frombuffer(pixels, np.uint8).reshape(HEIGHT, WIDTH, 4).astype(int)
    r, g, b = (a[..., 2], a[..., 1], a[..., 0]) if rgba_order == 'bgra' else (a[..., 0], a[..., 1], a[..., 2])
    y0, y1, x0, x1 = BAND
    r, g, b = r[y0:y1, x0:x1], g[y0:y1, x0:x1], b[y0:y1, x0:x1]
    m = (abs(r - BLUE[0]) <= 5) & (abs(g - BLUE[1]) <= 6) & (abs(b - BLUE[2]) <= 5)
    return int(m.sum())


def screenshots(run):
    shots = sorted(glob.glob(os.path.join(run, 'shot-*.raw')))
    hits = []
    for s in shots:
        data = Path(s).read_bytes()
        if len(data) == STRIDE * HEIGHT:
            hits.append(band_hits(data, 'bgra'))
    for p in sorted(glob.glob(os.path.join(run, 'png', 'shot-*.png'))):
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'],
                             capture_output=True).stdout
        if len(raw) == STRIDE * HEIGHT:
            hits.append(band_hits(raw, 'rgba'))
    hits = [h for h in hits if h is not None]
    return len(hits), sum(1 for h in hits if h >= 200)


def summarize(base, detail=False):
    run = os.path.join(base, 'run')
    text = merged_log(run)
    manifest = json.loads(Path(base, 'manifest.json').read_text())
    windows = window_list(text)
    # A window counts when an animation was on screen: frames enough for a distribution, at a rate that
    # is not the odd redraw of a static screen over tens of seconds.
    busy = [w for w in windows if w['numbers'] and int(w['numbers'][0]) >= 20 and int(w['numbers'][2]) >= 10]
    frames = sum(int(w['numbers'][0]) for w in busy)
    ms = sum(int(w['numbers'][1]) for w in busy)
    buckets = [sum(int(w['numbers'][5 + i]) for w in busy) for i in range(5)]
    # The beat fields come from their own regex, so a window can have one and not the other when the
    # ring cut a line in half. Only windows that reported a beat wait and had at least one frame
    # waiting count; a window with 0 of them would divide by zero and says nothing about the wait.
    beat_windows = [w for w in busy if w['beat'] and int(w['beat'][0]) > 0]
    n = sum(buckets) or 1
    fast = [moving(w) for w in busy]
    moving_frames, moving_ms = sum(f[0] for f in fast), sum(f[1] for f in fast)
    gl = [int(t) for t in re.findall(r'redwood-gl: frame \d+: .*?; (\d+) us \(', text)]
    hottest = [float(t) for t in re.findall(r'hottest (-?\d+\.\d) C', text)]
    levels = {}
    for line in re.findall(r'cpufreq: domain 1 in (\d+) s:([^;]*);', text):
        for mhz, share in re.findall(r' (\d+) MHz (\d+)%', line[1]):
            levels[int(mhz)] = levels.get(int(mhz), 0) + int(share) * int(line[0])
    total = sum(levels.values()) or 1
    lowest = min(levels) if levels else None
    shots, bad = screenshots(run)
    sampled = re.search(r'SAMPLED_SECONDS ([\d.]+)', Path(os.path.dirname(base), 'run-' + os.path.basename(base) + '.log').read_text()) \
        if os.path.exists(os.path.join(os.path.dirname(base), 'run-' + os.path.basename(base) + '.log')) else None
    cmd = manifest.get('cmdline', '')
    keep = [a for a in cmd.split() if a.split('=')[0] in ('cpus', 'cpufreq', 'cpufreq_mhz', 'fb_threads', 'gpu_log', 'fb_hz', 'glenv')]
    full = full_frequency(text)
    return {
        'run': os.path.basename(base.rstrip('/')),
        'commit': manifest.get('commit', '')[:7],
        'args': ' '.join(keep),
        'seconds': float(sampled.group(1)) if sampled else None,
        'panic': len(re.findall(r'^panic\(cpu', text, re.M)) // 2 + ('PANIC caller' in text and not re.search(r'^panic\(cpu', text, re.M)),
        'fps': 1000 * frames / ms if ms else 0,
        'fps_mv': 1000 * moving_frames / moving_ms if moving_ms else None,
        'static': 100 * (1 - moving_ms / ms) if moving_ms else None,
        'driver_us': sum(int(w['numbers'][3]) for w in busy) / len(busy) if busy else 0,
        # Weighted by the frames that actually waited, not by the window count: a window reports the
        # mean over its own waiting frames, and the windows differ in how many frames those are.
        'beat_us': (sum(int(w['beat'][0]) * int(w['beat'][1]) for w in beat_windows)
                    / sum(int(w['beat'][0]) for w in beat_windows)) if beat_windows else None,
        'onbeat': 100 * sum(int(w['beat'][0]) for w in beat_windows) / frames if beat_windows and frames else None,
        'swap_held': sum(int(w['beat'][2]) for w in beat_windows),
        'swap_lost': sum(int(w['beat'][3]) for w in beat_windows),
        'swap_late': sum(int(w['beat'][4]) for w in beat_windows),
        'gl_p50': percentile(gl, 0.5) / 1000, 'gl_p90': percentile(gl, 0.9) / 1000,
        'under18': 100 * (buckets[0] + buckets[1]) / n, 'mid': 100 * (buckets[2] + buckets[3]) / n, 'long': 100 * buckets[4] / n,
        'long_count': buckets[4],
        'hottest': max(hottest) if hottest else None,
        'lowest_share': 100 * levels[lowest] / total if lowest else None,
        'ff_s': full['seconds'] if full else None,
        'shots': shots, 'bad_shots': bad,
        # Process exits the kernel reported, over the merged log. This used to count occurrences of
        # ReportCrash / Terminated due to / EXC_BAD_ACCESS / EXC_CRASH, and ReportCrash is the name of
        # the crash reporter, so it matched the LaunchDaemons listing, the dyld unnest line and two
        # lsprobe lines in every round: roundb read 6 with 30 real exits, round C read 7 with none.
        # No crash report has ever appeared in these logs, the three exception strings included.
        'crashes': len(re.findall(r'redwood: \S+ pid \d+ exited code -?\d+ reason \d+', text)),
    }


# Which tl: lines carry a reading of the device's own clock, and which field of them to take. One
# value per line, the same field a whole-line scan for the first run of nine or more digits landed
# on, so a round whose lines all predate this table reports the coverage it always did.
#
# tl: td stays out on purpose. It heads a thread dump and its numbers are a pid, tid, state, pri, a
# wait channel and a pc. A pc whose hex digits happen to be all decimal (round D had 0x237103808)
# is nine digits long and reads as a plausible microsecond value, and taking it reported a 4707 s
# span and a 4289.2 s largest gap on a round whose real span is about 418 s. Round C did not trip
# it because every pc there carries a hex letter. tl: split and tl: init carry durations and limits
# rather than clock readings; their fields are short enough that a whole-line scan never matched
# them, and they stay out for the same reason tl: td does.
TL_TIME = (
    re.compile(r'^tl: [wQsfp] .*? at (\d+)'),
    re.compile(r'^tl: v \d+ ready (\d+)'),
    re.compile(r'^tl: a (\d+)'),
    re.compile(r'^tl: i \d+ posted (\d+)'),
    re.compile(r'^tl: c before \d+ seen (\d+)'),
)


def tl_time(line):
    """The device-clock microseconds this tl: line reports, or None when it reports no clock reading.

    A physical line carrying two records is skipped whole, for the reason recorded beside TL_TIME in
    tools/round-stats.py: the ring seam cuts a record mid-field, and the truncated first record can
    report a value ten times too small. bbm29 has 41 such lines and its coverage span drops from
    608.5 s to 405.7 s once they are left out.
    """
    if line.find('tl: ', 4) != -1:
        return None
    for pattern in TL_TIME:
        matched = pattern.match(line)
        if matched:
            return int(matched.group(1))
    return None

CPUFREQ_WINDOW = re.compile(
    r'cpufreq: domain 1 in (\d+) s:([^;]*); (\d+) changes, \d+ us each; \d+ times at the limit; '
    r'hottest (-?[\d.]+) C')


def full_frequency(text):
    """How long the round held its top clock bin: the second half of the acceptance figure, beside a
    frame rate that says nothing about the clock the frames were drawn at.

    The kernel's own histograms carry no tl: stamp, so this counts windows from the first one the round
    logged rather than reading a timestamp: the origin is that first window and the granularity is the
    window length. The top bin is this round's own highest MHz, because what decides throttling is that
    a ceiling came down, and the ceiling belongs to the round. Only domain 1 and only the `in N s:`
    histograms, the two choices summarize() already made: `hot ticks N of M` lines interleave with them
    and are a different distribution.

    A round that followed another one starts on a warm device, so a full-frequency stretch here is not
    automatically a cold one; the hottest reading of the first window goes with it for that judgement.
    The top bin also disappears when the load does, which is not thermal limiting: the hottest reading of
    the window that dropped it, against the round's peak, says which of the two ended the stretch. A drop
    at 71 C of a 75 C peak is limiting, the roundb drop at 47 C of a 74 C peak is a black screen with
    nothing to draw."""
    windows = [(int(sec), {int(mhz): int(share) for mhz, share in re.findall(r' (\d+) MHz (\d+)%', hist)},
                int(changes), float(temp))
               for sec, hist, changes, temp in CPUFREQ_WINDOW.findall(text)]
    if not windows:
        return None
    top = max(mhz for _, bins, _, _ in windows for mhz in bins)
    held = next((i for i, w in enumerate(windows) if w[1].get(top, 0) <= 0), len(windows))
    dropped = held < len(windows)
    return {'top': top, 'windows': len(windows), 'held': held,
            'seconds': sum(w[0] for w in windows[:held]),
            'first_hot': windows[0][3],
            'changes_at_drop': windows[held][2] if dropped else None,
            'hot_at_drop': windows[held][3] if dropped else None,
            'peak_hot': max(w[3] for w in windows),
            'dropped': dropped}


def coverage(base):
    """What stretch of the device's own clock the merged log actually holds, and whether the frames in it
    add up. --verify proves the merge agrees with the snapshots; it cannot see a stretch that every snapshot
    dropped, so the earliest and latest tl: timestamps are reported in absolute microseconds as well as
    their span: an earliest of 238 s on a run that began at boot is the fact that a span alone hides."""
    merged = merged_log(os.path.join(base, 'run'))
    times = [t for t in (tl_time(line) for line in merged.splitlines()
                         if line.startswith('tl: ')) if t is not None]
    if not times:
        return None
    first, last = min(times), max(times)
    ordered = sorted(times)
    gap = max((b - a for a, b in zip(ordered, ordered[1:])), default=0)
    frames = sum(int(w['numbers'][0]) for w in window_list(merged) if w['numbers'])
    span = last - first
    return {'first': first, 'last': last, 'span': span, 'gap': gap,
            'frames': frames, 'fps': 1e6 * frames / span if span > 0 else None}


REGISTRATION_STUCK = re.compile(
    r'memorystatus_perform_idle_demotion\(\) timed out stuck process \d+ \[(pkd|extensionkitservice|iconservicesagent)\]')


def registration_health(base):
    """The extension and icon chain being judged stuck says the desktop's upstream registration has degraded;
    a run in that state still reports frames, they just stop being produced partway through, so its rates
    only describe the part before. Reported next to coverage rather than folded into the exit code."""
    merged = merged_log(os.path.join(base, 'run'))
    hits = REGISTRATION_STUCK.findall(merged)
    return hits


def thermal(base):
    """The clock ceiling of the round, next to coverage: both say what the frame numbers describe."""
    return full_frequency(merged_log(os.path.join(base, 'run')))


def verify(base):
    """The merged log must hold every frame window and every frame the run's log files held, the set
    log_files() names. The ring drops what it overwrote and each file holds a different part, so a merge
    that misses lines loses windows without any other sign, and one that matches them at the wrong copy
    repeats whole stretches.

    The frames carry an id that only grows, so their counts are the criterion: per line the merge must
    hold as many as the fullest file did, and no file can hold a frame twice. A window line has
    no such id and two windows of a still screen can print the same text, so for those only the set of
    distinct lines is required; their counts are reported for reading. Returns the per-kind counts and
    the lines that came out wrong."""
    run = os.path.join(base, 'run')
    wanted = {'window': {}, 'frame': {}}
    for name in log_files(run):
        text = Path(name).read_text(errors='replace').replace('\x00', '')
        for kind, pattern in (('window', WINDOW_LINE), ('frame', FRAME_LINE)):
            for line, count in Counter(m.group(0) for m in pattern.finditer(text)).items():
                wanted[kind][line] = max(wanted[kind].get(line, 0), count)
    merged = merged_log(run)
    out = {}
    for kind, pattern in (('window', WINDOW_LINE), ('frame', FRAME_LINE)):
        got = Counter(m.group(0) for m in pattern.finditer(merged))
        missing = [line for line in wanted[kind] if line not in got]
        extra = [line for line in got if line not in wanted[kind]]
        wrong = [(line, got.get(line, 0), count) for line, count in wanted[kind].items()
                 if kind == 'frame' and got.get(line, 0) != count]
        out[kind] = {'snapshots': len(wanted[kind]), 'merged': len(got), 'wrong': wrong, 'extra': extra}
    return out


def main():
    markdown = '--markdown' in sys.argv
    detail = '--windows' in sys.argv
    checks = '--verify' in sys.argv
    flags = ('--markdown', '--windows', '--verify')
    runs = [round_dir(a) for a in sys.argv[1:] if a not in flags]
    empty = [r for r in runs if not log_files(os.path.join(r, 'run'))]
    if empty:
        for r in empty:
            print(f'summary.py: no s[0-9]*.log and no returned/hung-held/running.log under {r}/run',
                  file=sys.stderr)
        return 1
    if checks:
        bad = 0
        for base in runs:
            out = verify(base)
            cells = []
            for kind in ('window', 'frame'):
                r = out[kind]
                cells.append(f'{kind}s {r["merged"]} merged / {r["snapshots"]} in snapshots'
                             + (f', {len(r["wrong"])} wrong count, {len(r["extra"])} not in any snapshot'
                                if r['wrong'] or r['extra'] else ''))
                for line, got, count in r['wrong']:
                    print(f'  {kind}: merged {got}x, snapshots {count}x: ' + line[:140])
                for line in r.get('missing', []):
                    print(f'  {kind}: missing: ' + line[:140])
                for line in r['extra']:
                    print(f'  {kind}: not in any snapshot: ' + line[:140])
                bad += len(r['wrong']) + len(r['extra']) + len(r.get('missing', []))
            print(f'{os.path.basename(base.rstrip("/"))}: ' + '; '.join(cells))
            c = coverage(base)
            if c is None:
                print('  coverage: no tl: line, the span is unknown')
            else:
                # 动画只占跨度的一部分，所以 frames/跨度 一定低于 summary 的 fps，两者不是同一个量；
                # 能发现整段缺失的是「相邻 tl: 时间戳之间最大的空档」，正常不会超过快照间隔太多。
                print(f'  coverage: tl: {c["first"]} to {c["last"]} us, span {c["span"] / 1e6:.0f} s, '
                      f'largest gap between tl: lines {c["gap"] / 1e6:.1f} s, {c["frames"]} frames')
            # The driver's own count of how often a swap had to wait, over the windows that reported it.
            # All three at 0 is the reading behind "the driver never held CoreAnimation up": present()
            # only blocks its caller while the swap queue is full, so a nonzero first count is the only
            # way this driver can cost a frame its place in the beat.
            beat = [w['beat'] for w in window_list(merged_log(os.path.join(base, 'run'))) if w['beat']]
            waited = sum(int(b[0]) for b in beat)
            if beat:
                print(f'  swap queue: over {len(beat)} window(s), {sum(int(b[2]) for b in beat)} swaps waited '
                      f'for the frame before, {sum(int(b[3]) for b in beat)} gave up, '
                      f'{sum(int(b[4]) for b in beat)} came a refresh late themselves; '
                      f'{waited} frames waited for the next refresh'
                      + (f', {sum(int(b[0]) * int(b[1]) for b in beat) / waited:.0f} us each' if waited else ''))
            else:
                print('  swap queue: no window line carried the beat fields, the wait is unknown')
            hits = registration_health(base)
            if hits:
                print(f'  registration: {len(hits)} stuck judgement(s) on ' + ', '.join(sorted(set(hits))) +
                      ' -- the desktop\'s upstream degraded, so the rates describe only the part before')
            ff = thermal(base)
            if ff is None:
                print('  thermal: no cpufreq domain 1 window, the clock ceiling is unknown')
            else:
                # 满频时长以窗口数计，原点是本轮第一个 cpufreq 窗口；连续轮次里设备可能已经是热的，
                # 所以第一个窗口的 hottest 一起打出来，由读的人判是不是冷机。掉档那一刻的 hottest
                # 与本轮峰值一起给出：接近峰值是热限制，远低于峰值是负载没了。
                tail = (f', dropped at window {ff["held"] + 1} of {ff["windows"]} '
                        f'({ff["changes_at_drop"]} changes, hottest {ff["hot_at_drop"]:.1f} C '
                        f'of a {ff["peak_hot"]:.1f} C peak)'
                        if ff['dropped'] else
                        f', still there in the last of {ff["windows"]} windows '
                        f'(peak {ff["peak_hot"]:.1f} C)')
                print(f'  thermal: {ff["top"]} MHz held for {ff["seconds"]} s '
                      f'({ff["held"]} of {ff["windows"]} windows, domain 1), '
                      f'hottest {ff["first_hot"]:.1f} C in the first window' + tail)
        return 1 if bad else 0
    rows = [summarize(r) for r in runs]
    if detail:
        for r in runs:
            for w in window_list(merged_log(os.path.join(r, 'run'))):
                if not w['numbers']:
                    continue
                quick, took = moving(w)
                print(f'{os.path.basename(r.rstrip("/"))}: {w["numbers"][0]} frames in {w["numbers"][1]} ms '
                      f'({w["numbers"][2]} a second), {quick} of them within {FRAME_PAUSE} ms taking '
                      f'{took:.0f} ms ({1000 * quick / took if took else 0:.1f} a second)')
    cols = [('run', '{}'), ('commit', '{}'), ('args', '{}'), ('seconds', '{:.0f}'), ('panic', '{}'), ('fps', '{:.1f}'),
            ('fps_mv', '{:.1f}'), ('static', '{:.0f}%'),
            ('driver_us', '{:.0f}'), ('beat_us', '{:.0f}'), ('onbeat', '{:.0f}%'),
            ('gl_p50', '{:.1f}'), ('gl_p90', '{:.1f}'), ('under18', '{:.0f}%'), ('mid', '{:.0f}%'),
            ('long', '{:.0f}%'), ('long_count', '{}'), ('hottest', '{:.1f}'), ('lowest_share', '{:.0f}%'),
            ('ff_s', '{:.0f}'), ('shots', '{}'),
            ('bad_shots', '{}'), ('crashes', '{}')]

    def cell(row, key, fmt):
        return '-' if row[key] is None else fmt.format(row[key])
    if markdown:
        print('| ' + ' | '.join(c for c, _ in cols) + ' |')
        print('|' + '---|' * len(cols))
        for row in rows:
            print('| ' + ' | '.join(cell(row, c, f) for c, f in cols) + ' |')
    else:
        for row in rows:
            print('  '.join(f'{c}={cell(row, c, f)}' for c, f in cols))


if __name__ == '__main__':
    sys.exit(main())
