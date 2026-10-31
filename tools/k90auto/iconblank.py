#!/usr/bin/env python3
"""How long iconservicesagent takes to redraw the icons each time the home screen comes back.

usage: tools/k90auto/iconblank.py ROUND_DIR

iconservicesagent drops its RenderBox pipelines after 3 s without an icon to draw and builds them
again for the next one, so each return to the home screen is a burst of "render pipelines:" lines
from it, ended by SpringBoard importing the redrawn 256x256 icon surfaces ("SpringBoard import N:
surface ... 256x256"). One line per burst: when it began and ended, how many pipelines were built
and how many came back from the driver's cache, the imports within 1.5 s of its end, and the time
from the start of the burst to the last import. Times are the kernel's, from the nearest "at T"
before each line; the snapshots overlap, so each line is counted once.
"""
import re
import sys
from pathlib import Path

BURST_GAP = 2.0


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    run = Path(sys.argv[1]) / "run"
    built, reused, imports, seen = [], [], [], set()
    for path in sorted(run.glob("s[0-9]*.log")) + sorted(run.glob("hung-held.log")):
        t = 0.0
        for line in path.read_bytes().decode("utf-8", "replace").split("\n"):
            m = re.search(r"\bat (\d{9,})\b", line)
            if m:
                t = int(m.group(1)) / 1e6
            if line in seen:
                continue
            if "iconservicesagent" in line and "render pipelines:" in line:
                seen.add(line)
                (reused if "(reused " in line else built).append(t)
            elif "SpringBoard import" in line and "256x256" in line:
                seen.add(line)
                imports.append(t)
    events = sorted([(t, False) for t in built] + [(t, True) for t in reused])
    bursts, current = [], []
    for t, hit in events:
        if current and t - current[-1][0] > BURST_GAP:
            bursts.append(current)
            current = []
        current.append((t, hit))
    if current:
        bursts.append(current)
    for burst in bursts:
        start, end = burst[0][0], burst[-1][0]
        hits = sum(1 for _, hit in burst if hit)
        near = [i for i in imports if start <= i <= end + 1.5]
        last = f"{max(near) - start:.2f} s" if near and start > 0 else "-"
        print(f"{start:9.3f}-{end:9.3f}  {len(burst) - hits:3d} built {hits:3d} reused  "
              f"imports {' '.join(f'{i:.3f}' for i in near) or '-'}  start to last import {last}")


if __name__ == "__main__":
    main()
