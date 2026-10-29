#!/usr/bin/env python3
"""Whether one round's logs can carry an acceptance number, by the six criteria of
docs/analysis/2026-10-29-frame-budget.md §5.3.

    tools/k90auto/round-gate.py ROUND_DIR [--injected N]

Prints one verdict line and the six criteria, each pass or fail with the number behind it. It reads
only run/s[0-9]*.log, the same file set tools/round-stats.py reads, deduplicates whole lines across
the overlapping snapshots, and writes nothing. A round whose logs are complete but whose frames do
not overlap the injected touch is "not enough samples", which is a different answer from "failed":
the gesture may have landed outside what the ring kept.

The six criteria, and why each one is where it is:

  overlap      the injected touch must cover the frame stream, not follow it. Five rounds measured
               on 2026-10-29 produce 79 to 103 s of frames and then the touch, so the frames are an
               animation with no input. Counted as the share of frames whose tl: v done falls
               inside [first touch down, last touch sample].
  single touch the longest one uninterrupted touch has to be 30 s or more. Samples closer together
               than TOUCH_GAP_US are one touch; the driver prints them on powers of two, so a long
               drag grows seconds apart and any shorter threshold cuts it in pieces.
  frames in it that touch has to carry at least 30 s x 55 = 1650 frames, else the round cannot
               settle a 55 fps claim whatever its intervals look like.
  gesture count the number of touch downs has to equal the number injected. This needs --injected:
               the logs carry what arrived, not what the job script asked for. Without the flag the
               criterion is reported as undecided, never as pass.
  frame ids    no jump in the frame id, which is what a restart of the compositor leaves behind.
  swap holes   no interval between hand-overs over 1.5 s: a frame stream with a freeze in it is not
               a steady state, however good the percentiles between the freezes are.

A round that fails any one of them is not usable for an acceptance number. The verdict line says so
in those words, and does not say the round failed.
"""

import argparse
import glob
import pathlib
import re
import sys

# A touch sample every 8 ms; a gap this long ends one touch. Same value as round-stats.py's
# GESTURE_GAP_US, so the two tools cut gestures the same way.
TOUCH_GAP_US = 300_000
# The longest touch an acceptance round needs, and the frame rate the numbers are judged against.
WANTED_TOUCH_US = 30_000_000
WANTED_FPS = 55
# A hand-over interval longer than this is a freeze, not a slow frame (round-stats.py's figure).
HOLE_US = 1_500_000
# The share of the frame stream the injected touch has to cover.
WANTED_COVERAGE = 0.80

SNAPSHOT = re.compile(r"^s[0-9]+\.log$")
TOUCH_SAMPLE = re.compile(r"^tl: p (\d+) (\d+) (\d+) (\d+) at (\d+)")
FRAME_ID = re.compile(r"^tl: v (\d+)")
FRAME = re.compile(r"^tl: v (\d+) ready (\d+) shown (\d+) done (\d+)")
SWAP = re.compile(r"^tl: s (\d+) \S+ at (\d+)$")


def run_dir(path):
    """The run directory, whichever of the round's two levels the caller passed."""
    p = pathlib.Path(path).as_posix().rstrip("/")
    if glob.glob(p + "/s[0-9]*.log"):
        return pathlib.Path(p)
    if glob.glob(p + "/run/s[0-9]*.log"):
        return pathlib.Path(p) / "run"
    return pathlib.Path(p)


def read_lines(directory):
    """Every line of every snapshot once: the snapshots overlap by design."""
    seen = set()
    for name in sorted(directory.iterdir()):
        if not SNAPSHOT.match(name.name):
            continue
        with open(name, "rb") as handle:
            for raw in handle.read().split(b"\n"):
                line = raw.replace(b"\x00", b"").decode("utf-8", "replace").rstrip()
                if line and line not in seen:
                    seen.add(line)
                    yield line


def gestures(downs):
    """The touch samples cut into touches: one ends where the next is TOUCH_GAP_US or more later."""
    spans, first, last = [], None, None
    for at in downs:
        if first is None:
            first = last = at
        elif at - last < TOUCH_GAP_US:
            last = at
        else:
            spans.append((first, last))
            first = last = at
    if first is not None:
        spans.append((first, last))
    return spans


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("round", help="evidence directory of one round, or its run/ directory")
    parser.add_argument("--injected", type=int, default=None,
                        help="how many touch downs the job script asked for; without it the "
                             "gesture-count criterion is reported as undecided")
    args = parser.parse_args()

    directory = run_dir(args.round)
    if not directory.is_dir():
        sys.exit(f"round-gate.py: {directory} is not a directory")

    downs, samples, frames, swaps, ids_seen = [], [], {}, {}, set()
    for line in read_lines(directory):
        m = TOUCH_SAMPLE.match(line)
        if m:
            samples.append(int(m.group(5)))
            if int(m.group(1)) == 1:
                downs.append(int(m.group(5)))
            continue
        m = FRAME_ID.match(line)
        if m:
            ids_seen.add(int(m.group(1)))
            full = FRAME.match(line)
            if full:
                frames[int(full.group(1))] = int(full.group(4))
            continue
        m = SWAP.match(line)
        if m:
            swaps[int(m.group(1))] = int(m.group(2))

    print(f"round-gate.py: {args.round.rstrip('/')}")
    if not frames:
        print("  verdict: NOT ENOUGH SAMPLES -- no 'tl: v' line: this round did not run with touch_lat=1")
        return

    # The id set is counted the way round-stats.py counts it (any "tl: v" line), so the two tools
    # report the same frame ids; the timestamps come from the lines that carry all three of them.
    ids = sorted(ids_seen)
    inside = sum(1 for at in frames.values() if downs and downs[0] <= at <= samples[-1])
    coverage = inside / len(frames)
    spans = gestures(sorted(samples))
    longest = max((last - first for first, last in spans), default=0)
    carried = 0
    if spans:
        first, last = max(spans, key=lambda span: span[1] - span[0])
        carried = sum(1 for at in frames.values() if first <= at <= last)
    holes = [(b - a, b) for a, b in zip(ids, ids[1:]) if b - a > 1]
    gaps = [(later - earlier, later)
            for earlier, later in zip(sorted(swaps.values()), sorted(swaps.values())[1:])
            if later - earlier > HOLE_US]

    wanted_frames = WANTED_TOUCH_US // 1_000_000 * WANTED_FPS
    checks = [
        ("overlap", coverage >= WANTED_COVERAGE,
         f"{inside} of {len(frames)} frames fall inside the touch ({100 * coverage:.1f}%), want "
         f"{100 * WANTED_COVERAGE:.0f}% or more"),
        ("single touch", longest >= WANTED_TOUCH_US,
         f"longest touch {longest / 1e6:.1f} s, want {WANTED_TOUCH_US / 1e6:.0f} s or more"),
        ("frames in it", carried >= wanted_frames,
         f"{carried} frames inside the longest touch, want {wanted_frames} or more"),
        ("frame ids", not holes,
         f"{len(ids)} distinct ids, {ids[0]}..{ids[-1]}, {len(holes)} jump(s)"),
        ("swap holes", not gaps,
         f"{len(swaps)} hand-overs, {len(gaps)} interval(s) over {HOLE_US / 1e6:.1f} s"
         + (f", longest {max(g for g, _ in gaps) / 1e6:.1f} s" if gaps else "")),
    ]
    if args.injected is None:
        checks.insert(3, ("gesture count", None,
                          f"{len(downs)} touch downs in the logs, injected count not given "
                          f"(--injected N)"))
    else:
        checks.insert(3, ("gesture count", len(downs) == args.injected,
                          f"{len(downs)} touch downs in the logs, {args.injected} injected"))

    # The density of the injected samples inside the longest touch: not a criterion of its own,
    # because a rate under the target frame rate cannot carry 1,650 frames in 30 s and the check
    # above catches it. Printed because a round that fails "frames in it" has to say whether the
    # script sent too little or the compositor drew too little, and those read the same otherwise.
    if spans:
        first, last = max(spans, key=lambda span: span[1] - span[0])
        inside = sorted(at for at in samples if first <= at <= last)
        steps = sorted(b - a for a, b in zip(inside, inside[1:]))
        if steps:
            print(f"  (sample interval inside the longest touch: p50 {steps[len(steps) // 2] / 1000:.1f} ms, "
                  f"p95 {steps[int(0.95 * len(steps))] / 1000:.1f} ms, {len(inside)} samples; "
                  f"rwtouch sends one every 8 ms, so a larger p50 means the script did not keep moving)")

    failed = [name for name, ok, _ in checks if ok is False]
    undecided = [name for name, ok, _ in checks if ok is None]
    if failed:
        verdict = f"NOT ENOUGH SAMPLES -- {len(failed)} of {len(checks)} criteria not met: " + \
                  ", ".join(failed)
    elif undecided:
        verdict = f"UNDECIDED -- {len(checks) - len(undecided)} criteria met, " + \
                  ", ".join(undecided) + " has no input to judge"
    else:
        verdict = f"USABLE FOR AN ACCEPTANCE NUMBER -- all {len(checks)} criteria met"
    print(f"  verdict: {verdict}")
    for name, ok, detail in checks:
        mark = "pass" if ok else "fail" if ok is False else "undecided"
        print(f"  {mark:9s} {name:14s} {detail}")
    print("  (this says whether the round can carry a number, not whether the number is good: "
          "the frame-rate judgement is in the round's report)")


if __name__ == "__main__":
    main()