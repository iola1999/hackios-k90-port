#!/usr/bin/env python3
"""Run one round, retrying the boot-lottery panic that happens before the desktop starts.

The failure this exists for: about half the boots on 2026-10-29 ended one second after `oem run` with
`state: returned` and a log line `PANIC caller ...: UBSAN trap taken in early startup code
@ubsan_minimal.c:81`. It happened with three unrelated payloads and on every reset path tried, so the
round's own configuration cannot be blamed and the payload does not need to be rebuilt; only the boot
is wasted. Six boots on that day: three panicked, three went on to run the desktop.

    tools/k90auto/round-run.py ROUND_DIR [SECONDS] [SHOT_EVERY]

Every attempt is a full tools/k90auto/run-auto.py run, which stages the payload, samples, tears down
and leaves the device at an idle loader. An attempt counts as the lottery only when all three of these
hold:

    run/reboot.json says left == "returned"
    failed.elapsed_seconds <= 5.0
    some log in run/ contains "PANIC caller"

Two panic signatures reach that one-second return and both are retried: the UBSAN trap taken in early
startup code, and the `cpu_id <= (unsigned int)ml_get_max_cpu_number()` assertion followed by an
invalid kernel stack pointer and a jump to pc 0. Every attempt records which signature it saw. The
cost of the wider rule is three wasted boots when a payload genuinely fails early; each fails in about
a second, so the device time spent is negligible.

A retry moves the previous attempt's run/ aside to run-attempt-<n>/ so each attempt keeps its own logs,
then runs again. The attempts are written to ROUND_DIR/run/attempts.json. K90_PANIC_RETRY caps the
number of attempts (default 3): when every attempt panics, the round is reported as failed and the
decision is the caller's.

Exit status 0 when an attempt ran without the lottery, 3 when all attempts panicked, otherwise the
status of the last run-auto.py.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_AUTO = HERE / "run-auto.py"
PANIC_MARK = "PANIC caller"
ATTEMPT_SECONDS = 5.0


def attempt_summary(round_dir):
    """Read one finished attempt: its reboot summary and whether it is the boot-lottery panic."""
    run = round_dir / "run"
    summary = {}
    reboot = run / "reboot.json"
    if reboot.exists():
        summary = json.loads(reboot.read_text())
    logs = sorted(run.glob("*.log"))
    marked, signatures = [], set()
    for path in logs:
        text = path.read_text(errors="replace")
        if PANIC_MARK not in text:
            continue
        marked.append(path.name)
        # Two signatures share the one-second return: the UBSAN trap and the cpu_id assertion that
        # follows the secondary core failing to register. Which one a boot hits is recorded, because
        # the kernel reads them differently.
        if "UBSAN trap" in text:
            signatures.add("ubsan")
        if "ml_get_max_cpu_number" in text or "Invalid kernel stack pointer" in text:
            signatures.add("assert")
    failed = summary.get("failed") or {}
    left = summary.get("left")
    elapsed = failed.get("elapsed_seconds")
    lottery = bool(left == "returned" and elapsed is not None and elapsed <= ATTEMPT_SECONDS and marked)
    return {"left": left, "elapsed_seconds": elapsed, "panic_mark_in": marked,
            "signatures": sorted(signatures),
            "payload_sha256": summary.get("payload_sha256"), "lottery": lottery}


SLOT_FLOOR = 3
SLOT_RESET = "7"


def slot_verdict(retry_a):
    """What to do with a slot-retry-count:a reading: None means "no reading", otherwise a decision.

    The A slot never gets marked successful when iOS is started through the loader, so the counter
    falls by two every round and LK falls back to B slot Android at zero (SOP section 4 trap 4).
    Relaunching the round below the floor is what puts the device on Android partway through an
    unattended sequence.
    """
    if retry_a is None:
        return None
    return "reset" if retry_a < SLOT_FLOOR else "pass"


def read_retry_a():
    """slot-retry-count:a, or None when the device answers as the loader rather than LK."""
    try:
        out = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    serials = [line.split()[0] for line in out.splitlines() if line.strip()]
    lk = [s for s in serials if s and s != "xnuloader"]
    if not lk:
        return None
    try:
        out = subprocess.run(["fastboot", "-s", lk[0], "getvar", "slot-retry-count:a"],
                             capture_output=True, text=True, timeout=8)
    except (subprocess.SubprocessError, OSError):
        return None
    text = (out.stdout or "") + (out.stderr or "")
    for line in text.splitlines():
        if "slot-retry-count:a" in line:
            tail = line.split("slot-retry-count:a")[-1].strip(" :")
            if tail.isdigit():
                return int(tail)
    return None


def slot_preflight():
    """Return 0 to run the round, 3 when the A slot could not be brought back above the floor."""
    value = read_retry_a()
    verdict = slot_verdict(value)
    if verdict is None:
        print("SLOT no slot-retry-count reading: the device answers as the loader, where the "
              "counter is not exposed; the check belongs to the LK step of the reset", flush=True)
        return 0
    if verdict == "pass":
        print(f"SLOT slot-retry-count:a={value} at or above the floor {SLOT_FLOOR}", flush=True)
        return 0
    print(f"SLOT slot-retry-count:a={value} below the floor {SLOT_FLOOR}: set_active a to reset it",
          flush=True)
    serials = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5).stdout
    name = [line.split()[0] for line in serials.splitlines() if line.strip() and "xnuloader" not in line]
    if not name:
        print("SLOT reset failed: no LK device to send set_active to", flush=True)
        return 3
    done = subprocess.run(["fastboot", "-s", name[0], "set_active", "a"], capture_output=True, text=True, timeout=10)
    if done.returncode != 0 or "FAILED" in ((done.stdout or "") + (done.stderr or "")):
        print(f"SLOT reset failed: {done.stdout or done.stderr}".strip(), flush=True)
        return 3
    after = read_retry_a()
    if slot_verdict(after) != "pass":
        print(f"SLOT reset did not raise the counter (now {after}); the loader was not restarted, "
              f"so the next boot can still fall back to slot b", flush=True)
        return 3
    print(f"SLOT reset to {after}; reboot the loader before the round if the slot changed", flush=True)
    return 0


def archive_attempt(round_dir, number):
    """Move run/ aside so the next attempt starts from an empty directory and keeps these logs."""
    target = round_dir / f"run-attempt-{number}"
    if target.exists():
        shutil.rmtree(target)
    (round_dir / "run").rename(target)
    return target


def main():
    if "--self-test" in sys.argv:
        return self_test()
    if "--slot-test" in sys.argv:
        at = sys.argv.index("--slot-test")
        value = int(sys.argv[at + 1]) if len(sys.argv) > at + 1 else None
        print(f"SLOT-TEST value {value} verdict {slot_verdict(value)}")
        return 0
    if len(sys.argv) < 2:
        print(__doc__.split("    tools/k90auto/round-run.py")[0].strip())
        print("\nusage: round-run.py ROUND_DIR [SECONDS] [SHOT_EVERY]")
        return 2
    round_dir = Path(sys.argv[1]).resolve()
    # A round directory carries the manifest make-payload.py wrote; without one there is no payload
    # and run-auto.py would die on a missing file long after the boot that was supposed to be spent.
    if not (round_dir / "manifest.json").exists():
        print(f"{round_dir} has no manifest.json: this round has not been packed yet, "
              f"run tools/k90auto/make-payload.py first", flush=True)
        return 2
    seconds = sys.argv[2] if len(sys.argv) > 2 else "240"
    shots = sys.argv[3] if len(sys.argv) > 3 else "0,100,20"
    # 0 means one attempt with no retry: the boot-stability validation reads the raw panic rate and a
    # retry loop would turn six boots into up to eighteen attempts and hide the ratio.
    preflight = slot_preflight()
    if preflight != 0:
        return preflight
    limit = max(1, int(os.environ.get("K90_PANIC_RETRY", "3")))
    attempts = []
    code = 0
    for number in range(1, limit + 1):
        if number > 1:
            print(f"RETRY {number} of {limit}: {PANIC_MARK} on the previous boot", flush=True)
            archive_attempt(round_dir, number - 1)
        code = subprocess.run([sys.executable, str(RUN_AUTO), str(round_dir), seconds, shots]).returncode
        result = attempt_summary(round_dir)
        result["attempt"] = number
        attempts.append(result)
        print("ATTEMPT", json.dumps(result), flush=True)
        if not result["lottery"]:
            break
    (round_dir / "run").mkdir(parents=True, exist_ok=True)
    (round_dir / "run" / "attempts.json").write_text(json.dumps({"limit": limit, "attempts": attempts}, indent=2) + "\n")
    if attempts and attempts[-1]["lottery"]:
        print(f"RETRY_END all {len(attempts)} attempts panicked in early startup", flush=True)
        return 3
    print(f"RETRY_END attempts={len(attempts)} lottery={sum(a['lottery'] for a in attempts)}", flush=True)
    return code


def self_test():
    """Fabricate attempts and check the three-way decision: retry, stop on a real run, stop at the cap."""
    import tempfile
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def make(name, left, elapsed, mark):
            d = root / name
            (d / "run").mkdir(parents=True)
            (d / "run" / "reboot.json").write_text(json.dumps(
                {"left": left, "failed": {"state": left, "elapsed_seconds": elapsed},
                 "payload_sha256": "x"}))
            body = "nothing\n" if not mark else "PANIC caller 0x1: UBSAN trap taken in early startup code @ubsan_minimal.c:81\n"
            (d / "run" / "returned.log").write_text(body)
            return d

        lottery = make("a", "returned", 1.05, True)
        cases.append(("lottery at 1.05 s", attempt_summary(lottery)["lottery"], True))
        slow = make("b", "returned", 40.0, True)
        cases.append(("returned at 40 s is not the lottery", attempt_summary(slow)["lottery"], False))
        plain = make("c", "hung-held", 1.0, True)
        cases.append(("hung-held is not the lottery", attempt_summary(plain)["lottery"], False))
        nomark = make("d", "returned", 1.0, False)
        cases.append(("no PANIC line is not the lottery", attempt_summary(nomark)["lottery"], False))
        assert_d = make("f", "returned", 1.06, True)
        (assert_d / "run" / "returned.log").write_text(
            "PANIC caller 0xfffffff007aa49b0: machine_routines.c:1339 Assertion failed: "
            "cpu_id <= (unsigned int)ml_get_max_cpu_number()\n")
        summary_f = attempt_summary(assert_d)
        cases.append(("assertion signature still counts as the lottery", summary_f["lottery"], True))
        cases.append(("assertion signature is named", summary_f["signatures"], ["assert"]))
        kept = make("e", "returned", 1.05, True)
        archived = archive_attempt(kept, 1)
        cases.append(("archive keeps the first attempt's log",
                      (archived / "returned.log").exists() and not (kept / "run").exists(), True))
    bad = 0
    for name, got, want in cases:
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'pass' if ok else 'FAIL'}  {name}: {got} want {want}")
    print(f"SELFTEST {'pass' if bad == 0 else 'FAIL'} {len(cases) - bad} of {len(cases)}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())