#!/usr/bin/env python3
"""Take a short run of consecutive log snapshots around one action, then report what happened.

usage: tools/k90auto/action-probe.py EVIDENCE_DIR [SECONDS] [EVERY_SECONDS] [--note TEXT]

EVIDENCE_DIR is the directory a round is running in; the snapshots go to RUN_DIR/run/probe-NNN.log
so a round's own s###.log numbering is untouched. The intended use is the freeze the user hits when
unlocking: perform the action, run this for 30 seconds, and read one report instead of guessing from
a fixed-length round.

The report answers four questions that a single snapshot cannot: the highest frame id and when it
was finished, the largest gap between consecutive frames, whatever SpringBoard and backboardd said
about themselves, and whether EXC_GUARD, Code=4099, `died on signal` or a bad access line appeared.

Defaults: 30 seconds, one snapshot every 5 seconds. The action is whatever the note says; the script
does not perform it.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

argv = sys.argv[1:]
note = ""
if "--note" in argv:
    at = argv.index("--note")
    if at + 1 >= len(argv):
        raise SystemExit("--note needs the text of the action")
    note = argv[at + 1]
    argv = argv[:at] + argv[at + 2:]
args = argv
if len(args) not in (1, 2, 3):
    raise SystemExit(__doc__.strip())

base = Path(args[0])
duration = float(args[1]) if len(args) > 1 else 30.0
every = float(args[2]) if len(args) > 2 else 5.0
run = base / "run"
if not run.is_dir():
    raise SystemExit(f"{run} is not a directory: start the round first")

FRAME = re.compile(r"^tl: v (\d+) ready (\d+) shown (\d+) done (\d+)", re.M)
QUIET = re.compile(r"framewatch: still no frames, (\d+) s")


def loader(*argv, cap=30):
    result = subprocess.run(["fastboot", "-s", "xnuloader", *map(str, argv)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=cap)
    return result.returncode, result.stdout


def take(index):
    """One snapshot, named probe-NNN.log so it cannot be mistaken for a round snapshot."""
    path = run / f"probe-{index:03d}.log"
    code, _ = loader("oem", "log", cap=8)
    if code != 0:
        return None
    code, out = loader("get_staged", path, cap=40)
    return path if code == 0 and "FAILED" not in out else None


paths = []
started = time.monotonic()
index = 0
while time.monotonic() - started < duration:
    path = take(index)
    if path is not None:
        paths.append(path)
    index += 1
    # Poll the wall clock against the deadline rather than sleeping the remaining time in one go:
    # the loader can be slow enough that a snapshot takes longer than the interval.
    while time.monotonic() - started < every * index and time.monotonic() - started < duration:
        time.sleep(0.5)

if not paths:
    raise SystemExit("no snapshot came back: is a round running and the loader enumerated?")

frames = []
quiet = 0
counts = {"EXC_GUARD": 0, "Code=4099": 0, "died on signal": 0, "bad access": 0}
processes = {}
for path in paths:
    text = path.read_text(errors="replace")
    for match in FRAME.finditer(text):
        frames.append((int(match.group(1)), int(match.group(2)), int(match.group(4))))
    quiet = max(quiet, max((int(x) for x in QUIET.findall(text)), default=0))
    for name in counts:
        counts[name] += text.count(name)
    for name in ("SpringBoard", "backboardd"):
        for match in re.finditer(rf"redwood: proc {name} pid (\d+)([^\n]*)", text):
            processes.setdefault(name, set()).add(f"pid {match.group(1)}{match.group(2)}".strip())

frames.sort(key=lambda row: row[2])
report = {"note": note, "snapshots": [p.name for p in paths],
          "bytes": sum(p.stat().st_size for p in paths), "seconds": round(duration, 1)}
if frames:
    gaps = [(b[2] - a[2]) / 1e6 for a, b in zip(frames, frames[1:]) if b[2] >= a[2]]
    report.update({"first_frame": {"id": frames[0][0], "ready_us": frames[0][1]},
                   "last_frame": {"id": frames[-1][0], "ready_us": frames[-1][1],
                                  "done_us": frames[-1][2]},
                   "frame_count": len(frames),
                   "max_gap_seconds": round(max(gaps), 3) if gaps else 0.0})
report["framewatch_quiet_seconds"] = quiet
report["counts"] = counts
report["processes"] = {name: sorted(seen) for name, seen in processes.items()}
report_path = run / "probe-report.json"
report_path.write_text(json.dumps(report, indent=2) + "\n")

print(f"probe: {len(paths)} snapshots, {report['bytes']} bytes, note={note or '-'}")
if frames:
    print(f"frames: {report['frame_count']} from id {frames[0][0]} at {frames[0][1] / 1e6:.1f} s "
          f"to id {frames[-1][0]} done at {frames[-1][2] / 1e6:.1f} s, max gap {report['max_gap_seconds']} s")
else:
    print("frames: none in these snapshots")
print(f"framewatch quiet: {quiet} s")
print("counts: " + ", ".join(f"{name}={value}" for name, value in counts.items()))
for name in ("SpringBoard", "backboardd"):
    print(f"{name}: " + ("; ".join(report["processes"].get(name, [])) or "no redwood: proc line"))
print(f"report: {report_path}")