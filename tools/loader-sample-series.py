#!/usr/bin/env python3
"""Sample the resident loader on a fixed schedule while a kernel runs.

Purpose: separate "the loader still answers" from "the picture still moves" after a
desktop round freezes. Each sample records whether getvar answered at all, how long it
took, the result value, and the tail of the kernel log ring buffer.

Dry run by default. --execute is required to talk to the device.

A staged upload is never interrupted. A reply of a few dozen bytes needs one or two IN
tokens, so killing the client that waits for it cannot leave the transfer half done; a
1 MiB staged chunk needs hundreds, and a client killed in the middle of one leaves the
loader's IN record owned with no terminal event to release it (docs/analysis/local/
usb-endpoint-wedge-after-upload.md). So get_staged runs to its own end however long that
takes, while the two small probes keep their cap.

Every call is a fresh fastboot process, which is a fresh client and a fresh look at the
bus. After a call that did not answer the rest of that sample is skipped, and before the
next sample the bus is probed with `fastboot devices`: a silent channel is recorded as a
measurement and is not retried in the same state.
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DEVICE = 1

SERIAL = "xnuloader"
SCREEN_BYTES_PER_PIXEL = 4

# The floor the sampling asks for: 0.15 s between an upload and the next command was the
# pattern in the rounds that ended with a silent channel.
MIN_GAP_FLOOR = 0.5
STAGED_SOFT_CAP = 120.0
STAGED_PROGRESS = 5.0

_last_call_done = 0.0


def utc():
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


def pace(min_gap):
    """Start the next device call no sooner than min_gap after the previous one ended."""
    global _last_call_done
    wait = _last_call_done + min_gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def call(argv, cap, min_gap):
    """Run one short fastboot call. Returns (rc, body, elapsed, timed_out)."""
    global _last_call_done
    pace(min_gap)
    started = time.monotonic()
    try:
        # this fastboot writes getvar output to stderr, so both streams are merged here
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=cap)
        return done.returncode, done.stdout or "", time.monotonic() - started, False
    except subprocess.TimeoutExpired:
        return 124, "", time.monotonic() - started, True
    except OSError as error:
        return 127, str(error), time.monotonic() - started, False
    finally:
        _last_call_done = time.monotonic()


def fetch(argv, soft_cap, min_gap, log):
    """Run one staged upload to its own end; the client is never killed.

    soft_cap is when the log starts saying how long it has been going: a note that the
    sample is over its expected time, not a reason to interrupt a transfer whose
    interruption is what pins the loader's IN endpoint.
    """
    global _last_call_done
    pace(min_gap)
    started = time.monotonic()
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # one look every few seconds, and never so rarely that the soft-cap note misses its moment
    poll = min(STAGED_PROGRESS, max(0.25, soft_cap / 4.0))
    warned = False
    while True:
        try:
            out, _ = child.communicate(timeout=poll)
            _last_call_done = time.monotonic()
            return child.returncode, out or "", time.monotonic() - started, False
        except subprocess.TimeoutExpired:
            waited = time.monotonic() - started
            if not warned and waited >= soft_cap:
                warned = True
                log.append("[%s] staged upload still running after %.0fs (soft cap %.0fs); "
                           "the client is not killed, the transfer ends when it ends"
                           % (utc(), waited, soft_cap))


def field(body, name):
    for line in body.splitlines():
        if line.startswith(name + ":"):
            return line[len(name) + 1:].strip()
    return None


def tail(body, count):
    lines = [line for line in body.splitlines() if line.strip()]
    return lines[-count:]


def device_present(tool, min_gap):
    """A fresh client asks the bus who is there; no transfer of its own is left behind."""
    rc, body, _took, timed_out = call([tool, "devices"], 10.0, min_gap)
    return not timed_out and rc == 0 and SERIAL in body


def sample(args, tool, at_seconds, elapsed, recorder):
    """One sample. A call that did not answer ends the sample; nothing is retried."""
    row = {"at": at_seconds, "wall": utc(), "skipped": False}

    rc, body, took, timed_out = call([tool, "-s", SERIAL, "getvar", "result"],
                                     args.var_cap, args.min_gap)
    row["result_ok"] = not timed_out and rc == 0
    row["result_took"] = took
    row["result"] = field(body, "result") if row["result_ok"] else "(no answer)"
    recorder.append("[%s] +%ss getvar result: %s in %.2fs -> %r"
                    % (utc(), at_seconds, "answered" if row["result_ok"] else "SILENT",
                       took, row["result"]))

    rc, body, took, timed_out = call([tool, "-s", SERIAL, "oem", "log"],
                                     args.log_cap, args.min_gap)
    log_ok = not timed_out and rc == 0 and "FAILED" not in body
    row["log_ok"] = log_ok
    row["log_bytes"] = 0
    row["log_tail"] = []
    if log_ok:
        target = args.log_dir / ("log-%03d.txt" % at_seconds)
        # a file left by an earlier round would pass target.exists() and report its size
        if target.exists():
            target.unlink()
        rc, body, took, timed_out = fetch(
            [tool, "-s", SERIAL, "get_staged", str(target)], args.staged_cap, args.min_gap,
            recorder)
        got = not timed_out and rc == 0 and "FAILED" not in body and target.exists()
        row["log_bytes"] = target.stat().st_size if target.exists() else 0
        row["log_tail"] = tail(target.read_text(errors="replace"), args.tail_lines) if got else []
        recorder.append("[%s] +%ss oem log: %s, %d bytes fetched in %.2fs"
                        % (utc(), at_seconds, "prepared" if got else "staged but not fetched",
                           row["log_bytes"], took))
        if not got:
            row["skipped"] = True
    else:
        row["skipped"] = True
        recorder.append("[%s] +%ss oem log: SILENT" % (utc(), at_seconds))
    if row["skipped"]:
        recorder.append("[%s] +%ss the rest of this sample is skipped, and the next sample "
                        "probes the bus with a fresh client" % (utc(), at_seconds))

    row["shot_ok"] = None
    row["shot_bytes"] = 0
    if at_seconds in args.shot_at:
        if row["skipped"]:
            row["shot_ok"] = False
            recorder.append("[%s] +%ss oem screenshot: skipped with the rest of the sample"
                            % (utc(), at_seconds))
        else:
            rc, body, took, timed_out = call([tool, "-s", SERIAL, "oem", "screenshot"],
                                             args.log_cap, args.min_gap)
            if not timed_out and rc == 0 and "FAILED" not in body:
                target = args.log_dir / ("screen-%03d.raw" % at_seconds)
                if target.exists():
                    target.unlink()
                rc, body, took, timed_out = fetch(
                    [tool, "-s", SERIAL, "get_staged", str(target)], args.staged_cap,
                    args.min_gap, recorder)
                row["shot_ok"] = not timed_out and rc == 0 and target.exists()
                row["shot_bytes"] = target.stat().st_size if target.exists() else 0
            else:
                row["shot_ok"] = False
            recorder.append("[%s] +%ss oem screenshot: %s, %d bytes"
                            % (utc(), at_seconds, "ok" if row["shot_ok"] else "failed",
                               row["shot_bytes"]))

    row["drift"] = time.monotonic() - elapsed - at_seconds
    return row


def verdict(rows):
    live = [row for row in rows if row["result_ok"]]
    later = [row for row in rows if row["at"] >= 180]
    if not live:
        return "the loader never answered: the channel is silent from the first sample"
    if all(row["result_ok"] for row in later):
        return ("the loader answered at +180s and later: the loader is alive; a frozen picture "
                "is the kernel's, not the USB channel's")
    if not any(row["result_ok"] for row in later):
        return ("the loader answered up to +%ds and was silent from +180s on: the channel died "
                "before the last samples" % live[-1]["at"])
    return "mixed: the channel answered some samples and was silent at others"


def execute(args, tool):
    recorder = []
    out_dir = Path(args.log_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    schedule = [int(v) for v in args.times.split(",")]

    started = time.monotonic()
    rows = []
    previous_skipped = False
    for at_seconds in schedule:
        wait = at_seconds - (time.monotonic() - started)
        if wait > 0:
            time.sleep(wait)
        if previous_skipped:
            if not device_present(tool, args.min_gap):
                recorder.append("[%s] +%ss the device is not on the bus with a fresh client; "
                                "the series stops here" % (utc(), at_seconds))
                break
            recorder.append("[%s] +%ss a fresh client sees the device; the sample goes on"
                            % (utc(), at_seconds))
        row = sample(args, tool, at_seconds, started, recorder)
        previous_skipped = row["skipped"]
        rows.append(row)
        if time.monotonic() - started > args.total_seconds:
            recorder.append("[%s] total budget %ss reached; stopping"
                            % (utc(), args.total_seconds))
            break

    lines = ["", "== samples =="]
    for row in rows:
        lines.append("+%ds %-9s %-14s log=%d shot=%s"
                     % (row["at"], "answered" if row["result_ok"] else "SILENT",
                        row["result"], row["log_bytes"],
                        "-" if row["shot_ok"] is None else ("ok" if row["shot_ok"] else "failed")))
    lines.append("")
    lines.append("verdict: " + verdict(rows))
    text = "\n".join(recorder + lines)
    print(text)
    summary = out_dir / "series.txt"
    summary.write_text(text + "\n")
    print("\nwritten: %s" % summary)
    return EXIT_OK if rows else EXIT_DEVICE


def plan(args, tool):
    print("MODE dry-run: no command is executed and no device is contacted")
    print("action: sample the resident loader on a fixed schedule while a kernel runs")
    print("")
    print("target serial: %s" % SERIAL)
    print("schedule, seconds after the run starts: %s" % args.times)
    print("screenshot at: %s" % ",".join(str(v) for v in sorted(args.shot_at)))
    print("")
    print("per sample, in this order:")
    print("    1 %s -s %s getvar result          (cap %ss)" % (tool, SERIAL, args.var_cap))
    print("    2 %s -s %s oem log                (cap %ss)" % (tool, SERIAL, args.log_cap))
    print("    3 %s -s %s get_staged <log>       (soft cap %ss, the client is never killed)"
          % (tool, SERIAL, args.staged_cap))
    print("    4 at the screenshot times: oem screenshot then get_staged <raw>")
    print("")
    print("between any two device calls: at least %.1fs" % args.min_gap)
    print("after a call that did not answer: the rest of the sample is skipped, and the next")
    print("    sample asks %s devices before it does anything else" % tool)
    print("")
    print("recorded per sample: whether getvar answered, its latency, the result value,")
    print("    fetched log bytes and the last %d lines, screenshot bytes" % args.tail_lines)
    print("never: a kill of a staged upload, a retry in the same connection state,")
    print("    a reboot, a write to any partition")
    print("")
    print("scope in:  reads of the loader's state, kernel log ring buffer and frame buffer")
    print("scope out: any staging of a new image, any reset, any persistent write")
    print("")
    print("dry-run verdict: plan is well formed; nothing was sent")
    return EXIT_OK


def main(argv):
    parser = argparse.ArgumentParser(description="Sample the resident loader on a schedule.")
    parser.add_argument("--execute", action="store_true", help="talk to the device")
    parser.add_argument("--fastboot", default="fastboot")
    parser.add_argument("--times", default="30,90,150,180,210,240")
    parser.add_argument("--shot-at", default="150")
    parser.add_argument("--log-dir", default="logs/loader-series")
    parser.add_argument("--tail-lines", type=int, default=8)
    parser.add_argument("--var-cap", type=float, default=8.0)
    parser.add_argument("--log-cap", type=float, default=10.0)
    parser.add_argument("--staged-cap", type=float, default=STAGED_SOFT_CAP,
                        help="when the staged upload starts saying how long it has been going")
    parser.add_argument("--min-gap", type=float, default=MIN_GAP_FLOOR,
                        help="floor between two device calls (never below %ss)" % MIN_GAP_FLOOR)
    parser.add_argument("--total-seconds", type=float, default=300.0)
    args = parser.parse_args(argv)
    args.shot_at = {int(v) for v in args.shot_at.split(",") if v.strip()}
    args.log_dir = Path(args.log_dir)
    if args.min_gap < MIN_GAP_FLOOR:
        print("--min-gap is held at %ss: %ss between an upload and the next command was the "
              "pattern in the rounds that ended with a silent channel" % (MIN_GAP_FLOOR, args.min_gap),
              file=sys.stderr)
        args.min_gap = MIN_GAP_FLOOR

    try:
        [int(v) for v in args.times.split(",")]
    except ValueError:
        print("--times wants comma-separated seconds", file=sys.stderr)
        return EXIT_USAGE

    if not args.execute:
        return plan(args, args.fastboot)
    return execute(args, args.fastboot)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))