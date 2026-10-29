#!/usr/bin/env python3
"""Ask a running round for one screenshot, to be taken now rather than on a fixed interval.

usage: tools/k90auto/shot-now.py RUN_DIR

RUN_DIR is the evidence directory the round runs in, the one run-auto.py was given. The script
writes RUN_DIR/run/shot-request and exits; the round takes one shot the next time it looks, named
by the elapsed second it was taken at. A request written while another is still pending is refused
instead of queued, so a caller that repeats itself does not pile up screenshots of one moment.

Exit codes: 0 the request is in place, 1 the round directory is not there or a request is pending.
"""
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit(__doc__.strip())

run = Path(sys.argv[1]) / "run"
if not run.is_dir():
    raise SystemExit(f"{run} is not a directory: give the evidence directory a round is running in")
request = run / "shot-request"
if request.exists():
    raise SystemExit(f"{request} already exists: the round has not served the previous request yet")
request.write_text("")
print(f"requested one screenshot in {run}")