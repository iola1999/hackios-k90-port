#!/usr/bin/env python3
"""One round's numbers, computed the way the reading rules say, so a round is read the same way twice.

The rules this implements are the ones written down in docs/plan/k90auto-run-protocol.md and in the
control-round plan: counts are per service name, never a single total for all Code=4099 lines;
snapshots overlap, so lines are deduplicated before counting; frame holes come from the frame id and
the swap ids, not from `ready` deltas.

    tools/round-stats.py docs/progress/evidence/k90auto/kernel-12377-attr26-persona4

Prints, in order: how much of the round the log covers, frames and holes, touch posts against
swaps, frames and finger events in each 30-second window, which screen tier the screenshots reached,
Code=4099 per service,
watchdog violations per extension, host deaths, and the probe's own readings. Nothing is guessed
from absence: a section with no lines says so and leaves the conclusion to the reader.
"""

import argparse
import gzip
import pathlib
import re
import sys

SNAPSHOT = re.compile(r"^s\d+\.log$")
SERVICE_4099 = re.compile(r"service named (com\.apple\.[A-Za-z0-9._-]+)")
EXTENSION = re.compile(r"\[(com\.apple\.[A-Za-z0-9._-]+::[A-Za-z0-9._-]+)\]")
CORPSE = re.compile(r"Process\[(\d+)\] crashed: (\S+)\.")
SWAP = re.compile(r"tl: s (\d+) (\S+) at (\d+)")
FRAME = re.compile(r"tl: v (\d+)")
PROBE_FILES = re.compile(r"lsprobe t=(\d+) files_applications=(\S+) files_staged=(\S+) "
                         r"mobileinstallation_dir=(\S+) iconstate=(\S+) icondomain=(\S+) "
                         r"posterboard_dir=(\S+) posterboard_db=(\S+) pluginkit_dir=(\S+) "
                         r"containers_system=(\S+)")
PROBE_PROCS = re.compile(r"lsprobe t=(\d+) procs=(.*)")
PROBE_CONTAINERS = re.compile(r"lsprobe t=(\d+) containers_mobile=(\d+)"
                              r"(?: containers_plugin=(\d+))?")
PROBE_CRASHES = re.compile(r"lsprobe t=(\d+) crash_files=(\d+) crashes=(.*)")


def baseline_verdict(frame_ids, gaps):
    """Whether this round's frame numbers can be compared with another round's.

    A round cut into pieces by restarts has frame ids that jump and few frames overall; its frame
    rate, its percentile gaps and its stall lengths describe the restarts, not the desktop. The
    thresholds are the ones the control-round plan names: more than three id gaps, or fewer than
    500 frames.
    """
    if gaps > 3:
        return f"NOT A PERFORMANCE BASELINE: {gaps} frame-id gaps (a restart each)"
    if len(frame_ids) < 500:
        return f"NOT A PERFORMANCE BASELINE: only {len(frame_ids)} frames"
    return "usable as a performance baseline"


def read_lines(run_dir):
    """Every line of every snapshot, deduplicated: the snapshots overlap by design."""
    seen = set()
    for path in sorted(run_dir.iterdir()):
        if not SNAPSHOT.match(path.name):
            continue
        opener = gzip.open if path.name.endswith(".gz") else open
        with opener(path, "rb") as handle:
            for raw in handle.read().split(b"\n"):
                line = raw.replace(b"\x00", b"").decode("utf-8", "replace").rstrip()
                if line and line not in seen:
                    seen.add(line)
                    yield line


def section(title):
    print()
    print(title)
    print("-" * len(title))


def frames(lines):
    """Frames and holes, each number tagged with the baseline verdict."""
    swaps = {}
    frames_seen = set()
    for line in lines:
        m = SWAP.search(line)
        if m:
            swaps[int(m.group(1))] = int(m.group(3))
        m = FRAME.search(line)
        if m:
            frames_seen.add(int(m.group(1)))
    ids = sorted(frames_seen)
    section("frames")
    if not ids:
        print("no tl: v line: the kernel in this round did not print them")
        return "", []
    span = 0
    if swaps:
        span = max(swaps.values()) / 1e6
    holes = [(b - a, b) for a, b in zip(ids, ids[1:]) if b - a > 1]
    # A jump in the frame id is a restart's fingerprint: the compositor started a new counter.
    # Rounds with several of these are cut into pieces and cannot be compared with others on stall
    # length or frame rate, whatever the holes say.
    verdict = baseline_verdict(ids, len(holes))
    # The full sentence once, then a short tag on every line that carries a number: a reader who
    # copies three lines out of the middle still carries the qualification with them.
    tag = "[!PERF]" if verdict.startswith("NOT A") else ""
    print(f"{tag} {verdict}".strip())
    print(f"{tag} {len(ids)} distinct frame ids, {ids[0]}..{ids[-1]}; "
          f"{len(swaps)} swap handovers" + (f", last at {span:.1f} s" if span else "") +
          f"; id gaps {len(holes)}")
    if swaps:
        times = sorted(swaps.values())
        gaps = [(later - earlier, later) for earlier, later in zip(times, times[1:])
                if later - earlier > 1_500_000]
        print(f"{tag} swap gaps over 1.5 s: {len(gaps)}"
              + (f", longest {max(gap for gap, _ in gaps) / 1e6:.1f} s" if gaps else ""))
        for gap, at in gaps[:8]:
            print(f"{tag}   {gap / 1e6:6.1f} s ending {at / 1e6:8.1f} s")
    return verdict, ids


TOUCH = re.compile(r"tl: p ")


def touch(lines):
    """What the touch driver posted, against what the compositor swapped.

    A ratio near one means every posted sample was followed by a frame; a ratio well under one
    means frames were fewer than input, which is what a stalled compositor looks like from the
    driver's side. The count is unique lines: `grep -o` without `-h` prefixes each line with its
    file name, so `sort -u` then deduplicates per file and reports the raw count as if it were
    unique -- that mistake is how "the tool has no such section" was read as "there were no
    samples" on 2026-10-28.
    """
    section("touch posts against swaps")
    posts = sum(1 for line in lines if TOUCH.search(line))
    swaps = sum(1 for line in lines if SWAP.search(line))
    if not posts:
        print("no 'tl: p' line in this round")
        return
    ratio = f"{posts / swaps:.2f}" if swaps else "no swaps"
    print(f"{posts} touch posts, {swaps} swap handovers, posts/swap {ratio}")


DRAW_TRACE = re.compile(r"tl: v (\d+) ready (\d+) shown (\d+) done (\d+)")
TOUCH_SAMPLE = re.compile(r"tl: p (\d+) (\d+) (\d+) (\d+) at (\d+)")
# The driver reports a touch sample every 8 ms; a gap this long ends a gesture.
GESTURE_GAP_US = 300_000

SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_BYTES = 1156, 2510, 4
# Sampling every 997th pixel keeps the walk under a millisecond per file and stays stable between
# rounds; the tiers are wide apart, so the exact count does not matter.
SCREEN_STRIDE = 997
LOCK_SCREEN_MAX, HOME_SCREEN_MIN = 0.005, 0.10
# The kernel log ring the evidence snapshots are read from; the figure decides what an absent
# line proves (see ring_coverage).
RING_BYTES = 1024 * 1024


TOUCH_WINDOW_US = 30_000_000


def drags(lines):
    """Frames drawn in each 30-second window, beside the touches posted in it.

    Whether a gesture lands on something that redraws is the first question a performance round has
    to answer: a panel or a page turn produces frames for as long as the drag lasts, and a home
    screen with one page produces none. Windows rather than gesture boundaries, because the driver
    prints touch samples on powers of two (`RW_AGAIN`), so the samples inside one long drag grow
    seconds apart and any segmentation by gap length cuts a single drag into pieces.
    """
    section("frames and finger events per 30 s window")
    fingers = []        # types 1..3: a finger landing, moving, lifting
    buttons = []        # types 4..5: a hardware button, whose x and y are zero by definition
    drawn = []
    for line in lines:
        touch = TOUCH_SAMPLE.match(line)
        if touch:
            kind = int(touch.group(1))
            (fingers if kind in (1, 2, 3) else buttons).append(int(touch.group(5)))
            continue
        trace = DRAW_TRACE.match(line)
        if trace:
            drawn.append(int(trace.group(4)))
    if not fingers and not drawn:
        print("no finger events and no frames: nothing to compare")
        return
    fingers.sort()
    buttons.sort()
    drawn.sort()
    span = max([fingers[-1] if fingers else 0, drawn[-1] if drawn else 0])
    print(f"{len(fingers)} finger events, {len(buttons)} button events, {len(drawn)} frames; "
          f"windows of 30 s from the first event")
    print(f"{'from':>7} {'to':>7} {'fingers':>8} {'buttons':>8} {'frames':>7} {'fps':>6}")
    import bisect
    began = min(fingers[0] if fingers else span, drawn[0] if drawn else span)
    window = began
    while window <= span:
        close = window + TOUCH_WINDOW_US
        landed = bisect.bisect_left(fingers, close) - bisect.bisect_left(fingers, window)
        pressed = bisect.bisect_left(buttons, close) - bisect.bisect_left(buttons, window)
        first = bisect.bisect_left(drawn, window)
        count = bisect.bisect_left(drawn, close) - first
        print(f"{window / 1e6:7.1f} {close / 1e6:7.1f} {landed:8d} {pressed:8d} {count:7d} "
              f"{count / 30:6.1f}")
        window = close


def screens(run_dir):
    """Which tier the round's screenshots reached, from the pixels rather than from looking.

    Three tiers measured on 2026-10-28: pure black reads 0 bright samples of 2911, the lock screen
    reads about 102 (the clock, the date, the bar), and the home screen about 1163 (icons, widgets,
    dock). The last one also stays constant frame to frame, because a static home screen does not
    redraw. So the useful question is which tier a round reached and when it settled there, not how
    long each tier lasted.
    """
    section("screens")
    shots = sorted(pathlib.Path(run_dir).glob("shot-*.raw"))
    if not shots:
        print("no shot-*.raw in this run: nothing was captured")
        return
    tiers = []
    for shot in shots:
        data = shot.read_bytes()
        pixels = len(data) // SCREEN_BYTES
        if pixels == 0:
            continue
        bright = 0
        sampled = 0
        for index in range(0, pixels, SCREEN_STRIDE):
            base = SCREEN_BYTES * index
            blue, green, red = data[base], data[base + 1], data[base + 2]
            bright += max(red, green, blue) > 8
            sampled += 1
        ratio = bright / sampled
        tier = ("home" if ratio >= HOME_SCREEN_MIN else
                "lock" if ratio > LOCK_SCREEN_MAX else "black")
        tiers.append((int(shot.name[5:10]) / 10.0, tier, ratio))
    names = {"home": "home screen", "lock": "lock screen", "black": "black"}
    print(f"{len(tiers)} screenshots; {SCREEN_WIDTH}x{SCREEN_HEIGHT} expected, "
          f"{len(shots[0].read_bytes())} bytes in the first one")
    # Compressed run lengths, so a round that passed through a tier and fell back out of it does not
    # read like one that stayed: `black x1 -> lock x24 -> black x70` says the lock screen was drawn
    # and then lost, which is the shape of a failed transition.
    runs = []
    for _, tier, _ in tiers:
        if runs and runs[-1][0] == tier:
            runs[-1][1] += 1
        else:
            runs.append([tier, 1])
    print("  order: " + " -> ".join(f"{names[tier]} x{count}" for tier, count in runs))
    reached = max(tiers, key=lambda t: {"black": 0, "lock": 1, "home": 2}[t[1]])[1]
    print(f"  highest tier this round: {names[reached]}; last shot is "
          f"{names[tiers[-1][1]]} at {tiers[-1][0]:.1f} s")


def service_4099(lines):
    section("Code=4099 per service")
    counts = {}
    total = 0
    for line in lines:
        if "Code=4099" not in line:
            continue
        total += 1
        m = SERVICE_4099.search(line)
        counts[m.group(1) if m else "(no service named)"] = \
            counts.get(m.group(1) if m else "(no service named)", 0) + 1
    if not total:
        print("none")
        return
    print(f"{total} lines. A total is not a reading: compare per name.")
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {name}")


def watchdog(lines):
    section("watchdog provision violations per extension")
    counts = {}
    for line in lines:
        if "Watchdog provision violated" not in line:
            continue
        m = EXTENSION.search(line)
        name = m.group(1) if m else "(no extension in line)"
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        print("none")
        return
    total = sum(counts.values())
    print(f"{total} lines over {len(counts)} extensions")
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {name}")


def deaths(lines):
    section("host deaths")
    corpse = {}
    signal_lines = 0
    refused = []
    full = []
    for line in lines:
        m = CORPSE.search(line)
        if m:
            corpse[m.group(2)] = corpse.get(m.group(2), 0) + 1
        if "died on signal" in line:
            signal_lines += 1
        if "corpse refused" in line:
            refused.append(line.strip())
        if "corpse slots full" in line:
            full.append(line.strip())
    if corpse:
        print("Too many corpses being created, per process:")
        for name, count in sorted(corpse.items(), key=lambda kv: -kv[1]):
            print(f"  {count:5d}  {name}")
    else:
        print("no 'Too many corpses' line")
    print(f"'died on signal' lines: {signal_lines}")
    for line in refused[:4]:
        print("  " + line)
    for line in full[:4]:
        print("  " + line)
    if not corpse and not signal_lines and not refused and not full:
        print("nothing recorded: this round says no host died, not that the path was not taken")


DEATH = re.compile(r"redwood: proc (\S+) pid (\d+) died on signal (-?\d+) code (-?\d+)")


def death_classes(lines):
    """Deaths as one table of (signal, code) pairs.

    The comm in the kernel's line is 16 bytes truncated, so it is printed as it came: expanding a
    truncated name is how a process gets mistaken for another one with a similar name.
    """
    section("deaths by signal and code")
    pairs = {}
    for line in lines:
        m = DEATH.search(line)
        if not m:
            continue
        key = (int(m.group(3)), int(m.group(4)))
        comms = pairs.setdefault(key, {})
        comms[m.group(1)] = comms.get(m.group(1), 0) + 1
    if not pairs:
        print("no 'died on signal' line: this kernel did not carry the death-cause print")
        return
    total = sum(sum(comms.values()) for comms in pairs.values())
    ordered = sorted(pairs.items(), key=lambda kv: -sum(kv[1].values()))
    print(f"{total} lines, " + "  ".join(f"{signal}/{code}={sum(comms.values())}"
                                        for (signal, code), comms in ordered))
    for (signal, code), comms in ordered:
        top = sorted(comms.items(), key=lambda kv: -kv[1])[:4]
        print(f"  signal {signal} code {code}: " +
              ", ".join(f"{comm} x{count}" for comm, count in top))


def metal(lines):
    """What the driver refused, and whether the copy path was taken.

    The two no-copy counts are lines printed, not calls made: the served line is RW_AGAIN on
    purpose (the first call, then powers of two), so a busy round prints a handful for hundreds of
    calls. Reading them as call totals would understate the path that was taken.
    """
    section("Metal refusals and the no-copy path")
    patterns = (
        ("nil buffer from memory", r"nil buffer from memory"),
        ("Metal failed to build render pipeline", r"Metal failed to build render pipeline"),
        ("no-copy served as a copy (printed lines, not calls)",
         r"no-copy buffer of \d+ bytes served as a copy"),
        ("no-copy could not be allocated", r"no-copy buffer of \d+ bytes could not be allocated"),
    )
    for label, pattern in patterns:
        count = sum(1 for line in lines if re.search(pattern, line))
        print(f"  {count:5d}  {label}")
    sizes = {}
    for line in lines:
        m = re.search(r"no-copy buffer of (\d+) bytes served as a copy", line)
        if m:
            sizes[m.group(1)] = sizes.get(m.group(1), 0) + 1
    for size, count in sorted(sizes.items(), key=lambda kv: -int(kv[0]))[:4]:
        print(f"         {count:5d} printed line(s) of size {size}")


def probe(lines):
    section("probe readings")
    files = {}
    procs = {}
    containers = {}
    crashes = {}
    for line in lines:
        m = PROBE_FILES.search(line)
        if m:
            files[m.group(1)] = m.groups()[1:]
        m = PROBE_PROCS.search(line)
        if m:
            procs[m.group(1)] = m.group(2).split()
        m = PROBE_CONTAINERS.search(line)
        if m:
            containers[m.group(1)] = m.groups()[1:]
        m = PROBE_CRASHES.search(line)
        if m:
            crashes[m.group(1)] = m.groups()[1:]
    if not files:
        print("no lsprobe line at all: this round ran without the probe")
        return
    for t in sorted(files, key=int):
        apps, staged, install, icon, icondomain, poster, poster_db, pluginkit, system = files[t]
        print(f"t={t} files_applications={apps} files_staged={staged} "
              f"mobileinstallation_dir={install} iconstate={icon} icondomain={icondomain} "
              f"posterboard_dir={poster} posterboard_db={poster_db} "
              f"pluginkit_dir={pluginkit} containers_system={system}")
        if t in containers:
            mobile, plugin = containers[t]
            print(f"       containers_mobile={mobile}" + (f" containers_plugin={plugin}" if plugin else ""))
        if t in crashes:
            count, names = crashes[t]
            print(f"       crash_files={count} crashes={names}")
        if t in procs:
            print("       procs=" + " ".join(procs[t]))


def fence_probe(lines):
    """Did anything time out waiting for a fence, and where.

    The fence-timeout hypothesis (docs/analysis/2026-10-28-ui-freeze-fence-timeout-hypothesis.md)
    predicts a line saying a command did not finish within two seconds at each stall. A hit that
    lines up with a stall supports it; no hit at all says the block is outside the fence path. Read
    it with ring_coverage(): a round whose ring holds a few seconds of log cannot rule anything out
    by absence.
    """
    section("fence timeouts")
    hits = [line for line in lines if "did not finish the" in line]
    print(f"{len(hits)} line(s) saying a command did not finish in time")
    for line in hits[:10]:
        print(f"  {line[:150]}")


def ring_coverage(lines):
    """How much of the round the log ring could hold, and therefore what absence proves.

    The ring holds roughly a megabyte and the snapshots are taken about every twenty seconds, so
    the number that decides whether a missing line means anything is how many seconds of this
    round's own logging fit in that megabyte. A round at seventeen seconds of log cannot be read
    as "it did not happen"; a round at eighty-five can.
    """
    section("ring coverage")
    tl = [int(m.group(1)) / 1e6 for m in (re.search(r"^tl: .*?(\d{9,})", line) for line in lines) if m]
    if not tl or len(lines) < 2:
        print("not enough tl: lines to estimate")
        return
    span = max(tl) - min(tl)
    average = sum(len(line) for line in lines) / len(lines) + 1
    held = RING_BYTES / average
    seconds = held / (len(lines) / span) if span else 0.0
    print(f"{len(lines)} lines over {span:.0f} s, {average:.0f} bytes per line")
    print(f"a {RING_BYTES // 1024} KiB ring holds about {held:.0f} lines, "
          f"about {seconds:.0f} s of this round's logging")
    print("absence of a line proves nothing when that figure is below the snapshot interval (~20 s)")


def swap_holes(lines):
    """The intervals between swap handoffs, bucketed, because the stall periods are what get matched.

    Three-second holes every fifteen seconds and fifty-nine-second holes every sixty are different
    mechanisms that look alike in a frame-rate average; bucketing them apart is what lets a round
    with chronod removed say whether chronod was the trigger.
    """
    section("swap holes")
    at = sorted(int(m.group(1)) / 1e6 for m in (re.search(r"^tl: s \d+ backboardd at (\d+)$", line) for line in lines) if m)
    if len(at) < 2:
        print(f"{len(at)} swap handoffs, no interval to measure")
        return
    gaps = [(a, b - a) for a, b in zip(at, at[1:]) if b - a > 1.0]
    buckets = {"1-6 s": 0, "12-18 s": 0, "45-65 s": 0, "other": 0}
    for _, width in gaps:
        if width < 6:
            buckets["1-6 s"] += 1
        elif width < 18:
            buckets["12-18 s"] += 1
        elif 45 < width < 65:
            buckets["45-65 s"] += 1
        else:
            buckets["other"] += 1
    print(f"{len(at)} swap handoffs, {len(gaps)} hole(s) over 1 s: " +
          ", ".join(f"{name} x{count}" for name, count in buckets.items() if count))
    for start, width in gaps[:12]:
        print(f"  {start:.1f} s for {width:.1f} s")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("round", help="evidence directory of one round")
    args = parser.parse_args()
    run_dir = pathlib.Path(args.round) / "run"
    if not run_dir.is_dir():
        sys.exit(f"{run_dir} is not a round's run directory")
    lines = list(read_lines(run_dir))
    print(f"{args.round}: {len(lines)} distinct log lines")
    # Every `tl:` line carries the kernel's own microsecond counter, whose zero is not the round's
    # start and not the gesture script's first `wait`. Saying which basis the seconds are on keeps a
    # reader from lining a window up against a script line and concluding the touch never happened.
    print("tl: seconds below are relative to the earliest tl: event in these logs, "
          "not to boot and not to the script's first wait")
    frames(lines)
    touch(lines)
    drags(lines)
    screens(run_dir)
    service_4099(lines)
    watchdog(lines)
    deaths(lines)
    death_classes(lines)
    metal(lines)
    probe(lines)
    fence_probe(lines)
    ring_coverage(lines)
    swap_holes(lines)


if __name__ == "__main__":
    main()