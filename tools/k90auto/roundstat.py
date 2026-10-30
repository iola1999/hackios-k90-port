#!/usr/bin/env python3
"""Performance readings of one or more rounds, side by side.

usage: tools/k90auto/roundstat.py ROUND_DIR [ROUND_DIR ...]

For each round, from the log snapshots in ROUND_DIR/run (s*.log and cmd-*.log, each line once):
  - gestures: every touch sequence (touch lines "tl: p", a gap over 0.5 s starts the next one)
    with the frames the display took during it and 0.25 s after ("tl: v ... ready"): duration,
    frames, frames a second, median and longest interval between frames;
  - driver: per process, the "perf driver" lines summed, as microseconds per draw for the whole
    draw and its tracking, program, state emission and draw parts;
  - waits: per process, the "fd bo prep slow" lines (freedreno waiting for the GPU before the
    processor may touch a buffer object): how many and how long in total;
  - copies: per process, the IOSurfaces sampled through a copy (rw_surface_through_copy), and
    the last "rwa buffer textures" line (uploads against unchanged textures).
"""
import collections
import re
import statistics
import sys
from pathlib import Path


def lines(run):
    seen = set()
    paths = sorted(run.glob("s[0-9]*.log"), key=lambda p: p.stat().st_mtime)
    paths += sorted(run.glob("cmd-*.log"), key=lambda p: p.stat().st_mtime)
    for path in paths:
        for line in path.read_bytes().decode("utf-8", "replace").splitlines():
            if line not in seen:
                seen.add(line)
                yield line


def gestures(text):
    frames = sorted({int(m.group(1)) / 1e6 for line in text
                     for m in [re.match(r"tl: v \d+ ready (\d+) ", line)] if m})
    touches = sorted({int(m.group(1)) / 1e6 for line in text
                      for m in [re.match(r"tl: p \d+ \d+ \d+ \d+ at (\d+)$", line)] if m})
    spans = []
    for t in touches:
        if spans and t - spans[-1][1] < 0.5:
            spans[-1][1] = t
        else:
            spans.append([t, t])
    for start, end in spans:
        end += 0.25
        inside = [f for f in frames if start <= f <= end]
        gaps = [b - a for a, b in zip(inside, inside[1:])]
        yield (end - start, len(inside), len(inside) / (end - start),
               1000 * statistics.median(gaps) if gaps else None, 1000 * max(gaps) if gaps else None)


def main():
    for run_dir in map(Path, sys.argv[1:]):
        text = list(lines(run_dir / "run"))
        print(f"== {run_dir.name}")
        for duration, count, rate, median, longest in gestures(text):
            ms = f"median {median:5.1f} ms, longest {longest:4.0f} ms" if median else "no interval"
            print(f"  gesture {duration:4.2f} s: {count:3d} frames, {rate:5.1f} a second, {ms}")
        driver = collections.defaultdict(lambda: [0] * 6)
        waits = collections.defaultdict(lambda: [0, 0])
        copies = collections.Counter()
        uploads = {}
        for line in text:
            m = re.search(r"\[(\S+) \d+\] perf driver \d+ us: (\d+) draws in (\d+) us, tracking (\d+) "
                          r"prog (\d+) emit (\d+) draw (\d+) us", line)
            if m:
                for i in range(6):
                    driver[m.group(1)][i] += int(m.group(i + 2))
            m = re.search(r"\[(\S+) \d+\] fd bo prep slow: .* (\d+) us", line)
            if m:
                waits[m.group(1)][0] += 1
                waits[m.group(1)][1] += int(m.group(2))
            m = re.search(r"\[(\S+) (\d+)\].*bytes a row is sampled through a copy", line)
            if m:
                copies[f"{m.group(1)} {m.group(2)}"] += 1
            m = re.search(r"\[(\S+) \d+\] rwa buffer textures: (.*)", line)
            if m:
                uploads[m.group(1)] = m.group(2)
        for name, (draws, total, track, prog, emit, draw) in sorted(driver.items()):
            n = draws or 1
            print(f"  driver {name:20s} {draws:7d} draws, per draw {total / n:7.1f} us: tracking "
                  f"{track / n:6.1f}, program {prog / n:6.1f}, emit {emit / n:6.1f}, draw {draw / n:5.1f}")
        for name, (count, us) in sorted(waits.items()):
            print(f"  waits  {name:20s} {count:5d} slow buffer preparations, {us / 1000:8.1f} ms in all")
        for name, count in sorted(copies.items()):
            print(f"  copies {name:20s} {count:5d} surfaces sampled through a copy (at most 64 said)")
        for name, line in sorted(uploads.items()):
            print(f"  uploads {name:19s} {line}")


if __name__ == "__main__":
    main()
