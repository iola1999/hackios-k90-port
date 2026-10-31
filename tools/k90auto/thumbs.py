#!/usr/bin/env python3
"""Turn the driver's REDWOOD_THUMBS samples back into images.

usage: tools/k90auto/thumbs.py ROUND_DIR [PROCESS]

The driver prints, after each draw in sync mode, a 32x32 sample of every colour attachment ("out")
and every fragment texture ("in"), at the end of a commit also each resolve target ("res"), with REDWOOD_THUMB_DRAWS also the attachments before the draw
("pre"): a header line `thumb SEQ: commit C work W ROLE SLOT: format F
WxH PTR` and 32 lines `thumb SEQ ROW: ...`, four characters a texel (R, G, B, A, top six bits each,
base64 digits). This writes ROUND_DIR/thumbs-N.png, one row per draw: the attachments before
it, its textures, and the attachments after it, with a gap between the groups, each tile over a grey checkerboard so that alpha shows, and
ROUND_DIR/thumbs.txt naming every tile. PROCESS limits it to one process name.

A sample larger than 32x32 (REDWOOD_THUMB_SIZE) is shown in the sheet at every n-th texel and also
written whole as ROUND_DIR/thumb-SEQ.png.

A two-channel float attachment (RG16Float, RenderBox's coverage) is sampled with signs: R and G
are magnitudes and B is 128 for a negative R and 64 for a negative G (rwa_texture_thumbnail), so a
negative winding shows tinted blue.
"""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
DIGITS64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
SIZE, SCALE, ROWS_PER_SHEET = 32, 3, 36
HEADER = re.compile(r"redwoodmetal\[(\S+) (\d+)\]: thumb (\d+): commit (\d+) work (\d+) (in|out|pre|res) (\d+): "
                    r"format (\d+) (\d+x\d+) (\S+)( buffer| surface)?")
ROW = re.compile(r"redwoodmetal\[(\S+) (\d+)\]: thumb (\d+) (\d+): ([A-Za-z0-9+/]{32,})\s*$")

# 3x5 digits, as tour.py has them: this ffmpeg has no drawtext.
GLYPHS = ["111101101101111", "010110010010111", "111001111100111", "111001111001111", "101101111001001",
          "111100111001111", "111100111101111", "111001001001001", "111101111101111", "111101111001111"]


def merged(run_dir):
    spec = importlib.util.spec_from_file_location("render_health", HERE / "render-health.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text, _ = module.merge(Path(run_dir) / "run")
    return text


def stamp(tile, number, scale=2):
    text = str(number)
    tile[:5 * scale + 4, :len(text) * 4 * scale + 4] = 255
    for i, ch in enumerate(text):
        glyph = np.array([int(b) for b in GLYPHS[int(ch)]], np.uint8).reshape(5, 3)
        block = np.kron(glyph, np.ones((scale, scale), np.uint8)).astype(bool)
        tile[2:2 + 5 * scale, 2 + i * 4 * scale:2 + i * 4 * scale + 3 * scale][block] = (220, 0, 0)


def texels_of(rows):
    """The sample at the size the driver printed it (REDWOOD_THUMB_SIZE), as float RGBA."""
    size = len(next(iter(rows.values()))) // 4 if rows else SIZE
    texels = np.zeros((size, size, 4), np.float32)
    for y, line in rows.items():
        if y < size and len(line) == size * 4:
            texels[y] = (np.array([DIGITS64.index(ch) for ch in line], np.float32) * (255.0 / 63.0)).reshape(size, 4)
    return texels


def picture(texels, scale):
    size = texels.shape[0]
    checker = ((np.indices((size, size)).sum(axis=0) // 4) % 2) * 60 + 70
    alpha = texels[:, :, 3:4] / 255.0
    rgb = texels[:, :, :3] * alpha + checker[:, :, None] * (1 - alpha)
    return np.kron(rgb, np.ones((scale, scale, 1))).astype(np.uint8)


def tile_of(rows):
    """The sheet's tile: SIZE x SIZE, every n-th texel of a larger sample."""
    texels = texels_of(rows)
    step = max(1, texels.shape[0] // SIZE)
    return picture(texels[::step, ::step][:SIZE, :SIZE], SCALE)


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    run_dir = Path(sys.argv[1])
    only = sys.argv[2] if len(sys.argv) > 2 else None
    heads, bodies = {}, {}
    for line in merged(run_dir).splitlines():
        m = HEADER.search(line)
        if m and (only is None or m.group(1) == only):
            key = (m.group(1), m.group(2), int(m.group(3)))
            heads[key] = dict(process=m.group(1), pid=m.group(2), seq=int(m.group(3)),
                              commit=int(m.group(4)), work=int(m.group(5)), role=m.group(6),
                              slot=int(m.group(7)), format=int(m.group(8)), size=m.group(9),
                              texture=m.group(10), kind=(m.group(11) or "").strip())
            continue
        m = ROW.search(line)
        if m and (only is None or m.group(1) == only):
            bodies.setdefault((m.group(1), m.group(2), int(m.group(3))), {})[int(m.group(4))] = m.group(5)

    draws = {}
    for key, head in sorted(heads.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        draws.setdefault((head["process"], head["pid"], head["commit"], head["work"]), []).append((key, head))
    if not draws:
        print("no thumbnails in this round's log")
        return 1

    edge = SIZE * SCALE
    gap = 12
    index_lines = []
    sheet_rows = []
    for (process, pid, commit, work), items in draws.items():
        groups = [[it for it in items if it[1]["role"] == role] for role in ("pre", "in", "out", "res")]
        row = []
        for group in groups:
            if group:
                row += ([None] if row else []) + group
        sheet_rows.append(((process, pid, commit, work), row))
        for key, head in groups[0] + groups[1] + groups[2] + groups[3]:
            rows = bodies.get(key, {})
            size = len(next(iter(rows.values()))) // 4 if rows else SIZE
            missing = size - len(rows)
            if size > SIZE and rows:
                big = picture(texels_of(rows), 2)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{big.shape[1]}x{big.shape[0]}", "-i", "-",
                                str(run_dir / f"thumb-{head['seq']}.png")], input=big.tobytes(), check=True)
            index_lines.append(f"{head['seq']:5d} {process}[{pid}] commit {commit} work {work} "
                               f"{head['role']} {head['slot']}: format {head['format']} {head['size']} "
                               f"{head['texture']} {head['kind']}".rstrip() +
                               (f" ({missing} rows lost)" if missing else ""))

    width = max(len(t) for _, t in sheet_rows) * (edge + 4) + gap
    written = []
    for start in range(0, len(sheet_rows), ROWS_PER_SHEET):
        chunk = sheet_rows[start:start + ROWS_PER_SHEET]
        grid = np.full((len(chunk) * (edge + 4), width, 3), 255, np.uint8)
        for r, (_, row_tiles) in enumerate(chunk):
            x = 0
            for item in row_tiles:
                if item is None:
                    x += gap
                    continue
                key, head = item
                tile = tile_of(bodies.get(key, {})).copy()
                stamp(tile, head["seq"])
                grid[r * (edge + 4):r * (edge + 4) + edge, x:x + edge] = tile
                x += edge + 4
        out = run_dir / f"thumbs-{start // ROWS_PER_SHEET}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                        f"{grid.shape[1]}x{grid.shape[0]}", "-i", "-", str(out)],
                       input=grid.tobytes(), check=True)
        written.append(out)
    (run_dir / "thumbs.txt").write_text("\n".join(index_lines) + "\n")
    print(f"{len(heads)} thumbnails in {len(draws)} draws: " + " ".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
