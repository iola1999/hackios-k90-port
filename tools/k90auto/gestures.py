#!/usr/bin/env python3
"""Frame intervals in the main animation of each gesture of an unattended run.

usage: tools/k90auto/gestures.py [--each] RUN_DIR[/run] ...

Needs a run with boot-arg touch_lat=1 (the "tl:" timeline lines; glslow=3000 adds the window
server's draw times). A gesture starts at its touch-down: a touch near the top edge is a Control
Center pull, others are page swipes to the left or right of the screen's middle. Its main
animation runs from the first frame shown after the touch-down (tl: v ... done) for 1.8 s for a
pull and 600 ms for a swipe; the frame intervals inside it are pooled per kind of gesture, leaving
out the ones at or above FRAME_PAUSE: the driver calls a gap that long a still screen, not a slow
frame, and a gesture can end with one when the animation is over before its window is.

The line after the per-kind ones gives one row per Control Center pull: frames shown, how long
the animation ran, how many gaps of FRAME_PAUSE or more it held, its own fps and its longest
interval. A pooled line hides a pull that only reached 40 fps among seven near 60, which is the
shape of a run whose p50 is fine and whose p95 is not. The last line is the acceptance check
against the iOS 16.5 baseline's per-pull numbers.
"""
import glob
import re
import statistics
import sys

FRAME_PAUSE = 90        # ms; the driver's FRAME_PAUSE
CC_TARGET_FPS = 55          # every pull; iOS 16.5's six rounds run 55.9 to 60.6 per pull
CC_TARGET_MEDIAN = 56.4     # the low end of its medians, 56.4 to 59.8
CC_TARGET_GAP = 100         # ms; the longest interval in any of its windows was 88


def load(run):
    lines = set()
    # s[0-9]*.log, not s*.log: system-upload.log sits beside the snapshots and holds the fastboot
    # upload record. It carries no "tl:" line today, so the wider glob reads the same set for now, and
    # summary.py narrows it for the same reason.
    for name in sorted(glob.glob(run + "/s[0-9]*.log")):
        for raw in open(name, "rb"):
            text = raw.decode("utf-8", "replace")
            at = text.find("tl: ")
            if at >= 0:
                lines.add(text[at:].strip())
    downs, shown, draws = [], [], {}
    for line in lines:
        m = re.match(r"tl: p 1 \d+ (\d+) (\d+) at (\d+)", line)
        if m:
            downs.append((int(m.group(3)), int(m.group(1)) / 65535, int(m.group(2)) / 65535))
            continue
        m = re.match(r"tl: v (\d+) ready (\d+) shown (\d+) done (\d+)", line)
        if m:
            shown.append(int(m.group(4)))
            continue
        m = re.match(r"tl: g (\d+) began (\d+) ended (\d+)", line)
        if m:
            draws[int(m.group(2))] = (int(m.group(3)) - int(m.group(2))) / 1000
    return sorted(downs), sorted(shown), draws


def run_dir(path):
    """The run directory, whichever of its two levels the caller passed. summary.py takes the round
    directory and joins 'run' itself, so the two levels get mixed up; passing the round directory here
    used to find no snapshot and print a row of zeros with exit code 0."""
    p = path.rstrip("/")
    if glob.glob(p + "/s[0-9]*.log"):
        return p
    if glob.glob(p + "/run/s[0-9]*.log"):
        return p + "/run"
    return p


def kind(x, y):
    if y < 0.05:
        return "cc-pull", 1800
    return ("swipe-left", 600) if x > 0.5 else ("swipe-right", 600)


def main():
    each = "--each" in sys.argv[1:]
    runs = [run_dir(a) for a in sys.argv[1:] if a != "--each"]
    missing = [r for r in runs if not glob.glob(r + "/s[0-9]*.log")]
    for r in missing:
        print(f"gestures.py: no s[0-9]*.log under {r}", file=sys.stderr)
    if missing:
        sys.exit(1)
    for run in runs:
        downs, shown, draws = load(run)
        found = {}
        for at, x, y in downs:
            name, span = kind(x, y)
            frames = [v for v in shown if at < v <= at + 3000000]
            if not frames:
                continue
            main_part = [v for v in frames if v <= frames[0] + span * 1000]
            g = found.setdefault(name, {"intervals": [], "first": [], "draw": [], "rows": []})
            ivs = [(b - a) / 1000 for a, b in zip(main_part, main_part[1:])]
            g["intervals"] += ivs
            g["first"].append((frames[0] - at) / 1000)
            g["rows"].append((len(main_part), (main_part[-1] - frames[0]) / 1000, ivs))
            g["draw"] += [v for began, v in draws.items() if frames[0] - 200000 <= began <= frames[0] + span * 1000]
        print(run.rstrip("/").split("/")[-2] if run.rstrip("/").endswith("run") else run)
        # 覆盖跨度与注入次数：跨度不足或识别到的次数少于注入次数时，结论只能是「样本不足」，
        # 不能报「失败」——手势可能落在日志环没有覆盖到的那一段。
        times = sorted(v for v in shown)
        span_s = (times[-1] - times[0]) / 1e6 if times else 0.0
        gap_s = max(((b - a) / 1e6 for a, b in zip(times, times[1:])), default=0.0) if times else 0.0
        injected = sum(1 for _, x, y in downs if kind(x, y)[0].startswith("cc-"))
        print(f"  coverage: {span_s:.0f} s of frames, largest gap {gap_s:.1f} s, "
              f"{len(downs)} touch downs recognised, {injected} of them Control Center pulls")
        for name, g in sorted(found.items()):
            all_iv = sorted(g["intervals"])
            iv = [i for i in all_iv if i < FRAME_PAUSE]
            still = len(all_iv) - len(iv)
            n = len(iv)
            if n == 0:
                if not str.startswith(name, "cc-"):
                    print(f"  {name:12s} {len(g['first'])}x: no animation to measure, each window "
                          f"held one frame -- a desktop with one page turns nothing, the swipe "
                          f"springs back")
                continue
            q = lambda f: iv[min(n - 1, int(f * n))]
            draw = sorted(g["draw"])
            drawn = (f"window-server draw p50 {statistics.median(draw):4.1f} p95 {draw[int(.95 * len(draw))]:5.1f} ms"
                     if draw else "no draw times (glslow=3000)")
            print(f"  {name:12s} {len(g['first'])}x: {n} intervals, p50 {q(.5):5.1f} p95 {q(.95):5.1f} max {iv[-1]:6.1f} ms; "
                  f">18 {100 * sum(i > 18 for i in iv) / n:3.0f}% >34.5 {100 * sum(i > 34.5 for i in iv) / n:3.0f}%; "
                  f"{1000 * n / sum(iv):4.1f} fps; touch to first frame p50 {statistics.median(g['first']):5.1f} ms; "
                  f"{still} gaps over {FRAME_PAUSE} ms left out; {drawn}")
        pulls = found.get("cc-pull", {}).get("rows")
        if pulls:
            report_pulls([r for r in pulls if len(r[2]) >= 2], each)


def report_pulls(pulls, each):
    """One row per Control Center pull, then the acceptance check: which pulls reached the iOS 16.5
    floor, how many the paired count, and the longest interval inside any of the windows."""
    fps = [1000 * len([i for i in ivs if i < FRAME_PAUSE]) / sum(i for i in ivs if i < FRAME_PAUSE)
           for _, _, ivs in pulls]
    for n, (frames, span, ivs) in enumerate(pulls, 1):
        moving = [i for i in ivs if i < FRAME_PAUSE]
        if each:
            print(f"  pull {n}: {frames} frames, {span:4.0f} ms, {len(ivs) - len(moving)} gap(s) over "
                  f"{FRAME_PAUSE} ms, {fps[n - 1]:4.1f} fps, longest {max(ivs):5.0f} ms")
    total = len(pulls)
    at55 = sum(f >= CC_TARGET_FPS for f in fps)
    median = statistics.median(fps)
    worst = max(max(ivs) for _, _, ivs in pulls)
    verdict = "pass" if at55 == total and median >= CC_TARGET_MEDIAN and worst <= CC_TARGET_GAP else "fail"
    print(f"  pulls: {total}, fps " + " ".join(f"{f:.1f}" for f in fps) +
          f"; at least {CC_TARGET_FPS}: {at55} of {total}, median {median:.1f}, longest interval "
          f"{worst:.0f} ms; target every pull at {CC_TARGET_FPS}, median {CC_TARGET_MEDIAN}, "
          f"{CC_TARGET_GAP} ms -> {verdict}")


if __name__ == "__main__":
    main()
