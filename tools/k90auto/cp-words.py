#!/usr/bin/env python3
"""Decode the command words the kernel prints after a GPU hang into packets.

usage: tools/k90auto/cp-words.py ROUND_DIR|LOG [--pm4 adreno_pm4.xml]

The kernel (adreno8_gpu_hang_dump, kernel 12377-cmd4 on) prints, per pipe and IB level, the
level's base, REM_SIZE and INIT_SIZE, and the dwords from up to 48 before the CP's position to
16 after it:

  adreno8: hang pipe 1 IB2 base 0x10d86000 rem 12 init 495
  adreno8: pipe 1 IB2 at -48 0x10d86700: 70268000 ...

The dump starts at an arbitrary word, so the decoder tries every start up to the position and
keeps the one whose packet headers (type 7 and type 4, with their parity bits) chain without a
break through the position. Each packet is printed with its opcode or register offset, and the
one the position falls in is marked; the CP prefetches, so the packet it stopped in can be one
or two before the mark.

Opcode and event names come from Mesa's adreno_pm4.xml (the host Mesa tree's copy by default,
CP_PM4 or --pm4 for another), keeping only the values whose variants include A8XX.
"""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PM4 = os.environ.get("CP_PM4", "/tmp/mesa-air-host/mesa-26.2.5/src/freedreno/registers/adreno/adreno_pm4.xml")
DUMP = re.compile(r"adreno8: pipe (\d+) (\w+) at -(\d+) (0x[0-9a-f]+):((?: (?:[0-9a-f]{8}|unmapped))+)")
LEVEL = re.compile(r"adreno8: hang pipe (\d+) (\w+) base (0x[0-9a-f]+) rem (\d+) init (\d+)")


def has_a8xx(variants):
    if not variants:
        return True
    for item in variants.replace(" ", "").split(","):
        low, dash, high = item.partition("-")
        lo = int(low[1])
        hi = int(high[1]) if high else (9 if dash else lo)
        if lo <= 8 <= hi:
            return True
    return False


def names(path):
    root = ET.parse(path).getroot()
    opcodes, events = {}, {}
    for enum in root.iter():
        if not enum.tag.endswith("enum"):
            continue
        table = {"adreno_pm4_type3_packets": opcodes, "vgt_event_type": events}.get(enum.get("name"))
        if table is None:
            continue
        for value in enum:
            if value.tag.endswith("value") and has_a8xx(value.get("variants")):
                table.setdefault(int(value.get("value"), 0), value.get("name"))
    return opcodes, events


def odd(value):
    return bin(value).count("1") % 2 == 1


def header(word):
    """(kind, size in words including the header, field) or None."""
    if word is None:
        return None
    # Mesa's pm4_pkt7_hdr and pm4_pkt4_hdr: each field is followed by a bit that makes its
    # number of ones odd.
    if word >> 28 == 7:
        opcode, count = (word >> 16) & 0x7f, word & 0x7fff
        if odd(opcode) != (word >> 23) & 1 and odd(count) != (word >> 15) & 1:
            return ("pkt7", count + 1, opcode)
    if word >> 28 == 4:
        reg, count = (word >> 8) & 0x3ffff, word & 0x7f
        if odd(reg) != (word >> 27) & 1 and odd(count) != (word >> 7) & 1:
            return ("pkt4", count + 1, reg)
    return None


def chain(words, start, position):
    """Packets from `start`; None if a header breaks before `position` is passed."""
    packets, at = [], start
    while at < len(words):
        h = header(words[at])
        if h is None:
            return packets if at > position else None
        packets.append((at, h))
        at += h[1]
    return packets


def decode(words, position, opcodes, events, out):
    best = None
    for start in range(position + 1):
        packets = chain(words, start, position)
        if packets and any(p[0] <= position < p[0] + p[1][1] or p[0] >= position for p in packets):
            best = packets
            break
    if best is None:
        out.write("    no packet chain reaches the position\n")
        return
    for at, (kind, size, field) in best:
        body = words[at + 1:at + size]
        mark = " <- CP position" if at <= position < at + size else ""
        if kind == "pkt7":
            name = opcodes.get(field, f"opcode {field:#x}")
            extra = ""
            if name.startswith("CP_EVENT_WRITE") and body and body[0] is not None:
                extra = f" event {events.get(body[0] & 0xff, body[0] & 0xff)}"
            out.write(f"    [{at - position:+4d}] {name} ({size - 1} words){extra}{mark}\n")
        else:
            out.write(f"    [{at - position:+4d}] write reg {field:#06x} x{size - 1}{mark}\n")
        shown = " ".join("unmapped" if w is None else f"{w:08x}" for w in body[:12])
        if shown:
            out.write(f"           {shown}{' ...' if len(body) > 12 else ''}\n")


def read_text(target):
    target = Path(target)
    if target.is_dir():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import importlib.util
        spec = importlib.util.spec_from_file_location("rh", Path(__file__).resolve().parent / "render-health.py")
        rh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rh)
        return rh.merge(target / "run" if (target / "run").is_dir() else target)[0]
    return target.read_bytes().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target")
    ap.add_argument("--pm4", default=PM4)
    args = ap.parse_args()
    opcodes, events = names(args.pm4)
    text = read_text(args.target)

    seen = set()
    for m in LEVEL.finditer(text):
        if m.group(0) not in seen:
            seen.add(m.group(0))
            print(m.group(0))
    dumps = {}
    for m in DUMP.finditer(text):
        key = (m.group(1), m.group(2), int(m.group(3)))
        words = [None if w == "unmapped" else int(w, 16) for w in m.group(5).split()]
        dumps.setdefault(key, {})[int(m.group(4), 16)] = words
    for (pipe, level, before), lines in sorted(dumps.items()):
        first = min(lines)
        words = []
        for address in sorted(lines):
            words.extend(lines[address])
        print(f"pipe {pipe} {level}: {len(words)} words from {first:#x}, position {first + 4 * before:#x}")
        decode(words, before, opcodes, events, sys.stdout)
    if not dumps:
        print("no command words in this log (kernel before 12377-cmd4, or GX was off)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
