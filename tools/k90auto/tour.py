#!/usr/bin/env python3
"""Drive a running round through a list of touches and screenshots, then put the shots on one sheet.

usage: tools/k90auto/tour.py ROUND_DIR STEP [STEP ...]

Each STEP is LABEL=COMMAND@SETTLE*SHOTS, for example
  settings=/redwood/bin/rwtouch tap 0.5 0.5@3*2
  home@1*1                      (no command: only screenshots)
COMMAND goes to the device through rsh.py (rwsh, so at most 119 characters); SETTLE is the seconds
to wait after it; SHOTS is how many screenshots to take after that, one after another. With two or
more, the shots of one step are compared: the screen did not change between them, so pixels that
differ outside the status bar are flicker or content that comes and goes.

The round must be running under run-auto.py with on-request screenshots (shot-now.py's channel)
and rwsh in its rc.jobs. Results go to ROUND_DIR/run/tour.json, appended per call, and
ROUND_DIR/run/tour-sheet.png holds every step so far, numbered in the order of tour.json. Exit code: 0, or 1 when a command
or a screenshot did not come back.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1156, 2510
SHOT_BYTES = WIDTH * HEIGHT * 4
STATUS_BAR_ROWS = 150      # the clock changes every minute
CHANGED = 24               # a channel difference above this counts as a changed pixel


def parse(step):
    label, _, rest = step.partition("=")
    if "@" not in label and "@" not in rest:
        raise SystemExit(f"{step}: expected LABEL=COMMAND@SETTLE*SHOTS")
    if not rest:
        label, _, timing = label.partition("@")
        command = ""
    else:
        command, _, timing = rest.rpartition("@")
    settle, _, shots = timing.partition("*")
    return label, command.strip(), float(settle), int(shots or 1)


def take_shot(run):
    """Ask for one screenshot and return its path once the whole file is there."""
    before = {p.name for p in run.glob("shot-*.raw")}
    request = run / "shot-request"
    deadline = time.monotonic() + 60
    while request.exists():
        if time.monotonic() > deadline:
            return None
        time.sleep(0.2)
    request.write_text("")
    while time.monotonic() < deadline:
        new = [p for p in run.glob("shot-*.raw") if p.name not in before and p.stat().st_size == SHOT_BYTES]
        if new and not request.exists():
            return max(new, key=lambda p: p.name)
        time.sleep(0.3)
    return None


def pixels(path):
    return np.frombuffer(path.read_bytes(), np.uint8).reshape(HEIGHT, WIDTH, 4)[:, :, :3]


def compare(a, b):
    """Changed share of the screen below the status bar, and the box around the changed pixels."""
    diff = np.abs(pixels(a).astype(np.int16) - pixels(b).astype(np.int16)).max(axis=2) > CHANGED
    diff[:STATUS_BAR_ROWS] = False
    rows, cols = np.nonzero(diff)
    box = None if rows.size == 0 else [int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())]
    return round(float(diff.mean()), 5), box


# 3x5 digits for the tile numbers: this ffmpeg has no drawtext, and the label of each number is in
# tour.json and in what this script prints.
DIGITS = ["111101101101111", "010110010010111", "111001111100111", "111001111001111", "101101111001001",
          "111100111001111", "111100111101111", "111001001001001", "111101111101111", "111101111001111"]


def stamp(tile, number, scale=6):
    text = str(number)
    tile[:5 * scale + 8, :len(text) * 4 * scale + 8] = 255
    for i, ch in enumerate(text):
        glyph = np.array([int(b) for b in DIGITS[int(ch)]], np.uint8).reshape(5, 3)
        block = np.kron(glyph, np.ones((scale, scale), np.uint8)).astype(bool)
        y, x = 4, 4 + i * 4 * scale
        tile[y:y + 5 * scale, x:x + 3 * scale][block] = (220, 0, 0)


def sheet(run, entries, per_row=8):
    tiles = []
    for i, entry in enumerate(entries):
        tile = pixels(run / entry["shot"])[::4, ::4][:, :, ::-1].copy()   # BGRA rows to RGB, 1/4 size
        stamp(tile, i)
        tiles.append(tile)
    h, w = tiles[0].shape[:2]
    rows = (len(tiles) + per_row - 1) // per_row
    grid = np.zeros((rows * h, min(len(tiles), per_row) * w, 3), np.uint8)
    for i, tile in enumerate(tiles):
        grid[(i // per_row) * h:(i // per_row + 1) * h, (i % per_row) * w:(i % per_row + 1) * w] = tile
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                    f"{grid.shape[1]}x{grid.shape[0]}", "-i", "-", str(run / "tour-sheet.png")],
                   input=grid.tobytes(), check=True)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip())
    base = Path(sys.argv[1])
    run = base / "run"
    record = run / "tour.json"
    entries = json.loads(record.read_text()) if record.exists() else []
    status = 0
    for step in sys.argv[2:]:
        label, command, settle, count = parse(step)
        if command:
            sent = subprocess.run([sys.executable, str(HERE / "rsh.py"), str(base), *command.split()],
                                  capture_output=True, text=True, timeout=90)
            if sent.returncode != 0:
                print(f"{label}: command exited {sent.returncode}: {sent.stdout[-300:]}{sent.stderr[-300:]}")
                status = 1
        time.sleep(settle)
        shots = []
        for _ in range(count):
            shot = take_shot(run)
            if shot is None:
                print(f"{label}: no screenshot came back")
                status = 1
                break
            shots.append(shot)
        for n, shot in enumerate(shots):
            entry = {"label": label if count == 1 else f"{label}-{n + 1}", "command": command,
                     "shot": shot.name}
            if n:
                entry["changed_share"], entry["changed_box"] = compare(shots[n - 1], shot)
            entries.append(entry)
            print(json.dumps(entry))
    record.write_text(json.dumps(entries, indent=1) + "\n")
    if entries:
        sheet(run, entries)
        print(f"sheet: {run / 'tour-sheet.png'}")
    return status


if __name__ == "__main__":
    sys.exit(main())
