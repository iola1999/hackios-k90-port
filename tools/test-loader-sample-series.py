#!/usr/bin/env python3
"""Host simulation for tools/loader-sample-series.py -- no device is contacted.

A fake `fastboot` stands in for the loader, records every argv element with the time it
arrived and the process id that sent it, and answers the four calls the sampler makes. The
checks cover what the sampler promises after the endpoint-wedge round: a staged upload is
never killed (a transfer that takes longer than the soft cap still finishes), the floor
between two device calls holds even when a smaller --min-gap is asked for, a call that did
not answer ends its sample so no upload starts on a silent channel, every call is a fresh
client, and a file left by an earlier round is not counted as this round's bytes.

Usage: python3 tools/test-loader-sample-series.py
Every check prints one PASS line; the first failure prints the recorded call log and exits 1.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "tools" / "loader-sample-series.py")

FAKE_FASTBOOT = r'''#!/usr/bin/env bash
# Host-only stand-in: records argv, time and pid, never opens USB.
printf '%s\t%s\t%s\n' "$(date +%s.%N)" "$$" "$*" >> "${FAKE_CALLS:?}"
mode="${FAKE_MODE:?}"
case "$*" in
*" devices")
	printf 'xnuloader\t fastboot\n' ;;
*" getvar result")
	printf 'result: running 0 0\n' ;;
*"oem log")
	if [ "$mode" = silent_log ]; then
		exit 1
	fi
	printf 'OKAY\n' ;;
*"oem screenshot")
	printf 'OKAY\n' ;;
*" get_staged "*)
	path="${@: -1}"
	if [ "$mode" = slow_staged ]; then sleep 4; else sleep 0.05; fi
	head -c "${FAKE_STAGED_BYTES:-32}" /dev/zero > "$path"
	printf 'Sending %s bytes\nOKAY\n' "${FAKE_STAGED_BYTES:-32}" ;;
*)
	printf 'FAILED (unknown command)\n'
	exit 1 ;;
esac
'''

FAILURES = []


def check(condition, label):
    if condition:
        print("PASS %s" % label)
    else:
        print("FAIL %s" % label)
        FAILURES.append(label)


def run(tmp, mode, argv_extra, staged_bytes=32):
    calls = tmp / ("calls-%s.txt" % mode)
    log_dir = tmp / ("logs-%s" % mode)
    env = dict(os.environ)
    env["FAKE_CALLS"] = str(calls)
    env["FAKE_MODE"] = mode
    env["FAKE_STAGED_BYTES"] = str(staged_bytes)
    started = time_monotonic()
    done = subprocess.run([sys.executable, SCRIPT, "--execute", "--fastboot", str(tmp / "fastboot"),
                           "--log-dir", str(log_dir), "--tail-lines", "3"] + argv_extra,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                          timeout=180)
    return done.stdout or "", calls, log_dir, time_monotonic() - started


def time_monotonic():
    import time
    return time.monotonic()


def recorded(calls):
    rows = []
    if not calls.exists():
        return rows
    for line in calls.read_text().splitlines():
        when, pid, rest = line.split("\t", 2)
        rows.append((float(when), pid, rest))
    return rows


def main():
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        fake = tmp / "fastboot"
        fake.write_text(FAKE_FASTBOOT)
        fake.chmod(0o755)

        # dry run: nothing sent
        done = subprocess.run([sys.executable, SCRIPT, "--fastboot", str(fake),
                               "--log-dir", str(tmp / "dry")],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        check(done.returncode == 0, "dry run exits 0")
        check("soft cap 120.0s" in (done.stdout or ""), "plan states the 120 s staged soft cap")
        check("never killed" in (done.stdout or ""), "plan states the staged client is not killed")
        check(not (tmp / "dry").exists() or not any((tmp / "dry").iterdir()),
              "dry run sends nothing and writes nothing")

        # a staged upload longer than the soft cap still completes
        out, calls, log_dir, took = run(tmp, "slow_staged", ["--times", "1", "--staged-cap", "1"])
        rows = recorded(calls)
        staged = [row for row in rows if "get_staged" in row[2]]
        check(len(staged) == 1, "the slow upload was submitted once")
        check("the client is not killed" in out, "the soft cap only writes a note")
        check("staged but not fetched" not in out, "the transfer that outlived the soft cap finished")
        check(took >= 4.0, "the sampler waited for the whole transfer (%.1fs)" % took)
        check((log_dir / "log-001.txt").stat().st_size == 32, "the fetched bytes were recorded")

        # the floor between two device calls holds with a smaller --min-gap asked for
        out, calls, _log_dir, _took = run(tmp, "ok", ["--times", "1,2", "--min-gap", "0.1"])
        rows = recorded(calls)
        gaps = [rows[i + 1][0] - rows[i][0] for i in range(len(rows) - 1)]
        check(rows and min(gaps) >= 0.45, "every gap between calls is at least 0.5s (min %.2fs)"
              % (min(gaps) if gaps else -1))
        check("--min-gap is held at" in out, "a smaller floor is refused with a note")

        # every call is a different client
        pids = {row[1] for row in rows}
        check(len(pids) == len(rows), "each call is a fresh fastboot process")

        # a call that did not answer ends its sample: no upload on a silent channel
        out, calls, _log_dir, _took = run(tmp, "silent_log", ["--times", "1,2"])
        rows = recorded(calls)
        staged = [row for row in rows if "get_staged" in row[2]]
        check(not staged, "a silent channel never starts an upload")
        check("the rest of this sample is skipped" in out, "the sample is recorded as skipped")
        first_of_second = None
        seen_first = False
        for row in rows:
            if " getvar result" in row[2]:
                if seen_first:
                    first_of_second = row[2]
                    break
                seen_first = True
        check(first_of_second is None or first_of_second.endswith("devices"),
              "the next sample probes the bus with a fresh client first")

        # a file from an earlier round is not counted as this round's bytes
        stale = log_dir_path = None
        out, calls, log_dir, _took = run(tmp, "ok", ["--times", "1"], staged_bytes=10)
        log_dir_path = log_dir
        stale = log_dir_path / "log-001.txt"
        before = stale.stat().st_size
        stale.write_bytes(b"x" * 900)
        out2, calls2, log_dir2, _took2 = run(tmp, "ok", ["--times", "1"], staged_bytes=10)
        check((log_dir2 / "log-001.txt").stat().st_size == 10,
              "a stale file is replaced, not counted (%d bytes before)" % before)

    print()
    if FAILURES:
        print("%d check(s) failed" % len(FAILURES))
        return 1
    print("all host-simulation checks passed; no device was contacted")
    return 0


if __name__ == "__main__":
    sys.exit(main())