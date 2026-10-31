#!/usr/bin/env python3
"""Find frames that flash: a part of the screen that changes for one or two frames and then returns.

usage: tools/k90auto/flicker.py RECORDING OUTDIR [--cell 16] [--thresh 40]

Reads the kernel's screen recording (RWREC003). For each frame n and each cell of the grid, a flash
is: the cell differs from frame n-1 by more than THRESH (mean absolute difference of RGB), and frame
n+k (k = 1 or 2) is back within THRESH/4 of frame n-1. Prints one line per flashing frame and writes
OUTDIR/flash-N.png with frames n-1, n, n+k side by side, the flashing cells outlined.
"""
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def frames(path):
    data = open(path, "rb").read()
    magic, w, h, count, oldest = struct.unpack_from("<8sIIII", data, 0)
    assert magic == b"RWREC003", magic
    size = w * h * 3
    times, pics, at = [], [], 32
    for _ in range(count):
        if at + 8 + size > len(data):
            break
        times.append(struct.unpack_from("<Q", data, at)[0] / 1e9)
        pics.append(np.frombuffer(data, np.uint8, size, at + 8).reshape(h, w, 3))
        at += 8 + size
    if 0 < oldest < len(times):
        times = times[oldest:] + times[:oldest]
        pics = pics[oldest:] + pics[:oldest]
    began = struct.unpack_from("<Q", data, 24)[0] / 1e9
    return began, times, pics


def cells(pic, cell):
    h, w, _ = pic.shape
    hh, ww = h // cell * cell, w // cell * cell
    p = pic[:hh, :ww].astype(np.int16)
    return p.reshape(hh // cell, cell, ww // cell, cell, 3)


def diff(a, b, cell):
    return np.abs(cells(a, cell) - cells(b, cell)).mean(axis=(1, 3, 4))


def main():
    path, out = sys.argv[1], Path(sys.argv[2])
    cell = int(sys.argv[sys.argv.index("--cell") + 1]) if "--cell" in sys.argv else 16
    thresh = float(sys.argv[sys.argv.index("--thresh") + 1]) if "--thresh" in sys.argv else 40
    out.mkdir(parents=True, exist_ok=True)
    began, times, pics = frames(path)
    print(f"{len(pics)} frames, {times[0]:.3f} to {times[-1]:.3f} s of the recording, began {began:.3f} s kernel time")
    found = 0
    for n in range(1, len(pics) - 1):
        d_in = diff(pics[n], pics[n - 1], cell)
        moved = d_in > thresh
        if not moved.any():
            continue
        for k in (1, 2):
            if n + k >= len(pics):
                break
            back = diff(pics[n + k], pics[n - 1], cell) < thresh / 4
            flash = moved & back
            if flash.sum() >= 2:
                ys, xs = np.nonzero(flash)
                print(f"frame {n} at {times[n]:.3f} s (kernel {began + times[n]:.3f}): {flash.sum()} cells flash for {k} "
                      f"frame(s), rows {ys.min() * cell}-{(ys.max() + 1) * cell}, columns {xs.min() * cell}-{(xs.max() + 1) * cell}; "
                      f"gaps {1000 * (times[n] - times[n - 1]):.0f} ms, {1000 * (times[n + k] - times[n]):.0f} ms")
                h, w, _ = pics[n].shape
                sheet = Image.new("RGB", (w * 3 + 20, h), "white")
                for i, p in enumerate((pics[n - 1], pics[n], pics[n + k])):
                    sheet.paste(Image.fromarray(np.ascontiguousarray(p)), (i * (w + 10), 0))
                draw = ImageDraw.Draw(sheet)
                for y, x in zip(ys, xs):
                    draw.rectangle([w + 10 + x * cell, y * cell, w + 10 + (x + 1) * cell - 1, (y + 1) * cell - 1], outline="red")
                sheet.save(out / f"flash-{n}.png")
                found += 1
                break
    print(f"{found} flashing frames")
    # frames out of order: n far from both neighbours while the neighbours are close to each other
    print("out-of-order candidates (ratio = (d(n-1,n) + d(n,n+1)) / d(n-1,n+1)):")
    for n in range(1, len(pics) - 1):
        a = diff(pics[n], pics[n - 1], cell).sum()
        b = diff(pics[n + 1], pics[n], cell).sum()
        c = diff(pics[n + 1], pics[n - 1], cell).sum()
        if min(a, b) > 2000 and (a + b) / (c + 1) > 2.5:
            print(f"  frame {n} at {times[n]:.3f} s: d-in {a:.0f}, d-out {b:.0f}, neighbours {c:.0f}, ratio {(a + b) / (c + 1):.1f}")


if __name__ == "__main__":
    main()
