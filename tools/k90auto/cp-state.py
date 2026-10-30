#!/usr/bin/env python3
"""Rebuild the register state of the draw the GPU hung in, from the kernel's command tree.

usage: tools/k90auto/cp-state.py ROUND_DIR|LOG [--regs a6xx.xml] [--all] [--pass gmem|sysmem|binning]

From kernel 12377-cmd8 on, a hang report prints BR's IB1 whole and every IB and draw-state group
it names, three levels down (adreno8_bo_dump_tree):

  adreno8: tree 0 of 513 0x14332000: 70268000 ...
  adreno8: fs bindless slot 55 0x1678b0dc0: 00000000 ...

This walks IB1 the way the CP does: register writes (type-4 packets and CP_CONTEXT_REG_BUNCH)
change the state, CP_INDIRECT_BUFFER is followed, CP_SET_DRAW_STATE replaces the group with its
id, and at each CP_DRAW_* the groups in force for the chosen pass are applied over the direct
writes. The last draw's state is printed with register names from Mesa's a6xx.xml (A8XX
variants), then the fb-read bindless descriptors. --all prints every draw's state, not just the
last one.
"""
import argparse
import importlib.util
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGS = "/tmp/mesa-air-host/mesa-26.2.5/src/freedreno/registers/adreno/a6xx.xml"
TREE = re.compile(r"adreno8: tree (\d+) of (\d+) (0x[0-9a-f]+):((?: (?:[0-9a-f]{8}|unmapped))+)")
SLOT = re.compile(r"adreno8: fs bindless slot (\d+) (0x[0-9a-f]+):((?: (?:[0-9a-f]{8}|unmapped))+)")
INDIRECT = {0x3f, 0x57}
SET_DRAW_STATE = 0x43
REG_BUNCH = 0x5c
# CP_SET_DRAW_STATE's BINNING, GMEM and SYSMEM bits: a group with any of them set runs only in
# those passes (freedreno's PROG_BINNING group, for one, is binning-only).
PASS_BITS = 7 << 20
PASS = {"binning": 1 << 20, "gmem": 1 << 21, "sysmem": 1 << 22}
DRAWS = {0x38: "CP_DRAW_INDX_OFFSET", 0x28: "CP_DRAW_INDIRECT", 0x29: "CP_DRAW_INDX_INDIRECT",
         0x24: "CP_DRAW_AUTO"}


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp_words = load("cp-words")


def register_names(path):
    """offset -> name for the A6XX domain's registers that exist on A8XX."""
    names = {}
    root = ET.parse(path).getroot()
    domain = next(d for d in root if d.tag.endswith("domain") and d.get("name") == "A6XX")

    def add(offset, name, wide):
        names.setdefault(offset, name)
        if wide:
            names.setdefault(offset + 1, name + "+1")

    for item in domain:
        tag = item.tag.split("}")[-1]
        if not cp_words.has_a8xx(item.get("variants")):
            continue
        if tag in ("reg32", "reg64"):
            add(int(item.get("offset"), 0), item.get("name"), tag == "reg64")
        elif tag == "array":
            base, stride = int(item.get("offset"), 0), int(item.get("stride", "1"), 0)
            inner = [r for r in item if r.tag.split("}")[-1] in ("reg32", "reg64")
                     and cp_words.has_a8xx(r.get("variants"))]
            for i in range(int(item.get("length", "1"), 0)):
                if not inner:
                    add(base + i * stride, f"{item.get('name')}[{i}]", False)
                for r in inner:
                    add(base + i * stride + int(r.get("offset"), 0),
                        f"{item.get('name')}[{i}].{r.get('name')}", r.tag.endswith("reg64"))
    return names


def buffers(text):
    """GPU address -> words (None for unmapped), one entry per printed buffer. The merged log
    can carry a kernel line twice; a line inside a buffer already read is skipped."""
    out, current = {}, None
    for m in TREE.finditer(text):
        address = int(m.group(3), 16)
        words = [None if w == "unmapped" else int(w, 16) for w in m.group(4).split()]
        if current is not None and address == current + 4 * len(out[current]):
            out[current].extend(words)
        elif not any(s <= address < s + 4 * len(ws) for s, ws in out.items()):
            current = address
            out[current] = words
    return out


class Walk:
    def __init__(self, bufs, pass_bit):
        self.bufs = bufs
        self.pass_bit = pass_bit
        self.regs = {}
        self.groups = {}
        self.draws = []

    def words(self, address, count):
        for start, ws in self.bufs.items():
            if start <= address and address + 4 * count <= start + 4 * len(ws):
                at = (address - start) // 4
                return ws[at:at + count]
        return None

    def run(self, address, count, regs, follow=True):
        ws = self.words(address, count)
        if ws is None:
            print(f"  buffer {address:#x} ({count} words) was not printed")
            return
        at = 0
        while at < len(ws):
            h = cp_words.header(ws[at])
            if h is None:
                print(f"  {address + 4 * at:#x}: not a packet header ({ws[at]}), stopped")
                return
            kind, size, field = h
            body = ws[at + 1:at + size]
            if kind == "pkt4":
                for i, v in enumerate(body):
                    regs[field + i] = v
            elif field == REG_BUNCH:
                for i in range(0, len(body) - 1, 2):
                    regs[body[i]] = body[i + 1]
            elif field in INDIRECT and follow and len(body) >= 3:
                self.run(body[0] | body[1] << 32, body[2] & 0xfffff, regs)
            elif field == SET_DRAW_STATE:
                for i in range(0, len(body) - 2, 3):
                    flags, lo, hi = body[i:i + 3]
                    group = (flags >> 24) & 0x3f
                    if flags & (1 << 18):
                        self.groups.clear()
                    if flags & (1 << 17) or not flags & 0xffff:
                        self.groups.pop(group, None)
                    else:
                        self.groups[group] = (lo | hi << 32, flags & 0xffff, flags)
            elif field in DRAWS:
                state = dict(regs)
                for group in sorted(self.groups):
                    addr, n, flags = self.groups[group]
                    passes = flags & PASS_BITS
                    if passes and not passes & self.pass_bit:
                        continue
                    self.run(addr, n, state, follow=False)
                self.draws.append((DRAWS[field], address + 4 * at, body, state, dict(self.groups)))
            at += size


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target")
    ap.add_argument("--regs", default=REGS)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pass", dest="pass_name", choices=sorted(PASS), default="gmem",
                    help="which pass's draw-state groups apply at the draw (default gmem)")
    args = ap.parse_args()
    text = cp_words.read_text(args.target)
    names = register_names(args.regs)
    bufs = buffers(text)
    if not bufs:
        print("no command tree in this log (kernel before 12377-cmd8, or no hang dump)")
        return 1
    roots = [int(m.group(3), 16) for m in TREE.finditer(text) if m.group(1) == "0"]
    root = roots[0]
    count = int(next(m.group(2) for m in TREE.finditer(text) if m.group(1) == "0"))
    print(f"IB1 {root:#x}, {count} words; {len(bufs)} buffers printed")
    walk = Walk(bufs, PASS[args.pass_name])
    walk.run(root, count, walk.regs)
    print(f"{len(walk.draws)} draws")
    for n, (name, where, body, state, groups) in enumerate(walk.draws):
        if not args.all and n != len(walk.draws) - 1:
            continue
        print(f"\n== draw {n + 1}: {name} at {where:#x}: " + " ".join(f"{w:08x}" for w in body))
        print(f"   groups ({args.pass_name}): " + ", ".join(
            f"{g}={a:#x}/{c}" + ("" if not f & PASS_BITS or f & PASS[args.pass_name] else " (skipped)")
            for g, (a, c, f) in sorted(groups.items())))
        for reg in sorted(state):
            print(f"   {reg:#06x} {names.get(reg, '?'):48s} {state[reg]:08x}")
    slots = [(int(m.group(1)), m.group(2), m.group(3)) for m in SLOT.finditer(text)]
    seen = set()
    for slot, address, words in slots:
        if (slot, address) not in seen:
            seen.add((slot, address))
            print(f"bindless slot {slot} {address}:{words}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
