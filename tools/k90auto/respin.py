#!/usr/bin/env python3
"""Change the driver settings of a running round and restart processes, without a new image.

usage: tools/k90auto/respin.py ROUND_DIR [--env WORD ...] [--restart NAME ...] [--wait S]
                               [--until TEXT] [--tour STEP ...] [--stop]

--env sets kern.redwood.env to the words, each PROCESS:NAME=VALUE or PROCESS:-NAME, where PROCESS
is the process name (SpringBoard, iconservicesagent); `--env` with no words clears it.
libredwoodmetal applies its process's words when the process loads it, so they take effect in
the processes --restart kills and launchd starts again. --wait is the seconds to wait after that
(default 30), --until waits instead for TEXT to appear in the log after the restart (at most
--wait seconds). --tour runs tour.py's steps, appended to the round's tour.json.
--stop asks the round to end (run/stop-request).

The round has to be running and has to stay up between calls: start it with cycle.py --hold. The
commands go through rsh.py, one line of at most 119 characters each, so a long --env is sent as one
"setenv" and as many "addenv" as it takes. Needs a kernel with kern.redwood.env (12377-cmd13 and
later) and an image whose rwsh has setenv, addenv and restart.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT = 119


def rsh(round_dir, text):
    print(f"rsh: {text}", flush=True)
    return subprocess.run([sys.executable, str(HERE / "rsh.py"), str(round_dir), text]).returncode


def newest_log(run_dir):
    logs = sorted(run_dir.glob("s[0-9]*.log"))
    return logs[-1].read_bytes().decode("utf-8", "replace") if logs else ""


def logged_since(run_dir, anchor):
    """The newest snapshot after ANCHOR, the end of an earlier one; a snapshot is the loader's log
    ring, which stops growing at about 1.3 MB, so offsets of an earlier snapshot do not carry over."""
    text = newest_log(run_dir)
    at = text.rfind(anchor) if anchor else -1
    return text if at < 0 else text[at + len(anchor):]


def env_commands(words):
    """'setenv' with the first words, then 'addenv' with the rest, each within LIMIT."""
    commands, current = [], "setenv"
    for word in words:
        if len(word) + len("addenv ") > LIMIT:
            raise SystemExit(f"respin: {word} is longer than one command can carry")
        if len(current) + 1 + len(word) > LIMIT:
            commands.append(current)
            current = "addenv"
        current += " " + word
    commands.append(current)
    return commands


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("round_dir", type=Path)
    ap.add_argument("--env", nargs="*")
    ap.add_argument("--restart", nargs="+", default=[])
    ap.add_argument("--wait", type=int, default=30)
    ap.add_argument("--until")
    ap.add_argument("--tour", nargs="+", default=[])
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    run_dir = args.round_dir / "run"
    if not run_dir.is_dir() or (run_dir / "reboot.json").exists():
        print(f"respin: {run_dir} is not a running round", file=sys.stderr)
        return 2

    if args.env is not None:
        for command in env_commands(args.env):
            if rsh(args.round_dir, command) != 0:
                return 1
    if args.restart:
        anchor = newest_log(run_dir)[-400:]
        if rsh(args.round_dir, "restart " + " ".join(args.restart)) != 0:
            return 1
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            time.sleep(2)
            if args.until and args.until in logged_since(run_dir, anchor):
                break
        else:
            if args.until:
                print(f"respin: no '{args.until}' within {args.wait} s; going on")
    if args.tour and subprocess.run([sys.executable, str(HERE / "tour.py"), str(args.round_dir),
                                     *args.tour]).returncode != 0:
        return 1
    if args.stop:
        (run_dir / "stop-request").write_text("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
