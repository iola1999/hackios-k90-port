#!/usr/bin/env python3
"""Wait for a round to end without sleeping a fixed amount.

usage: tools/k90auto/wait-round.py EVIDENCE_DIR [MAX_SECONDS]

EVIDENCE_DIR is the directory run-auto.py was given. The script polls every 5 seconds and returns
as soon as RUN_DIR/run/reboot.json exists, which the teardown writes last. It prints one line with
the elapsed wait and the teardown's verdict, or exits 2 when MAX_SECONDS (default 900) runs out with
no result. Polling instead of sleeping for a guessed duration is the point: a round that freezes is
ended early by run-auto.py, so the wait has no idea how long it will take.
"""
import json
import sys
import time
from pathlib import Path

if len(sys.argv) not in (2, 3):
    raise SystemExit(__doc__.strip())

run = Path(sys.argv[1]) / "run"
budget = float(sys.argv[2]) if len(sys.argv) == 3 else 900.0
started = time.monotonic()
last = None
while True:
    waited = time.monotonic() - started
    record = run / "reboot.json"
    if record.is_file():
        summary = json.loads(record.read_text())
        frozen = summary.get("frozen") or {}
        tail = f" state={summary.get('left')} mode={summary.get('mode')}"
        if frozen:
            tail += (f" FROZEN_AT={frozen.get('elapsed_seconds'):.1f}"
                     f" last_frame={frozen.get('last_frame_id')}")
        print(f"round ended after {waited:.1f} s: samples={summary.get('samples')}{tail}")
        sys.exit(0)
    if waited >= budget:
        print(f"no reboot.json after {waited:.1f} s: the round is still running or its teardown died")
        sys.exit(2)
    commands = run / "commands.jsonl"
    if commands.is_file() and commands.stat().st_size != last:
        last = commands.stat().st_size
    time.sleep(5)