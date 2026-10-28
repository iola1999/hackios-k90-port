#!/usr/bin/env python3
"""Turn a fault pc into a function name.

The kernel prints `redwood: <comm> bad access at <addr> pc <pc>`; the driver prints
`rwa metal: driver code at <addr>` once per process, which is the loaded address of rw_print.
Neither number means anything on its own: the dylib is position independent, so its slide differs
per process, and the reader would have to do this subtraction by hand for every crash.

    tools/symbolize.py <dylib> <driver code at> <pc> [<pc> ...]

Takes the dylib that was actually packaged (`out/ios26-resume/bbmetal-device/libredwoodmetal.dylib`
right after a pack, before the next pack overwrites it), finds rw_print in its symbol table, and
reports the function containing each pc plus the offset inside it. A pc that falls outside the
dylib is reported as such -- that is a reading too, and the one that says the fault was not in this
code.
"""

import argparse
import pathlib
import re
import subprocess
import sys


def symbols(dylib):
    """Every defined text symbol, sorted by address, from the dylib's own table."""
    out = subprocess.run(["xcrun", "llvm-nm", "-n", "--defined-only", str(dylib)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"llvm-nm refused {dylib}: {out.stderr.strip()}")
    found = []
    for line in out.stdout.splitlines():
        # Three fields, except object methods whose names hold spaces: split twice at most.
        parts = line.split(maxsplit=2)
        if len(parts) != 3 or not re.fullmatch(r"[0-9a-f]+", parts[0]):
            continue
        if parts[1] not in ("t", "T"):
            continue
        found.append((int(parts[0], 16), parts[2].strip()))
    return sorted(found)


def containing(table, address):
    """The symbol whose range covers the address, plus the offset into it."""
    low, high = 0, len(table) - 1
    while low <= high:
        middle = (low + high) // 2
        if table[middle][0] <= address:
            low = middle + 1
        else:
            high = middle - 1
    if high < 0:
        return None, 0
    return table[high][1], address - table[high][0]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dylib")
    parser.add_argument("driver_code_at", help="the value the driver printed for its own code")
    parser.add_argument("pcs", nargs="+", help="fault pcs from the kernel's bad-access line")
    args = parser.parse_args()

    table = symbols(args.dylib)
    anchor = [entry for entry in table if entry[1] == "_rw_print"]
    if not anchor:
        sys.exit("no _rw_print in this dylib: it is not the driver, or it was stripped")
    anchor_file, anchor_loaded = anchor[0][0], int(args.driver_code_at, 0)
    slide = anchor_loaded - anchor_file
    lowest, highest = table[0][0] + slide, table[-1][0] + slide

    print(f"dylib {pathlib.Path(args.dylib).name}: {len(table)} text symbols, "
          f"_rw_print at file {anchor_file:#x}, loaded {anchor_loaded:#x}, slide {slide:#x}")
    print(f"this copy covers loaded addresses {lowest:#x}..{highest:#x} "
          f"({len(table)} symbols; the last symbol's length is not known here)")
    for pc in args.pcs:
        address = int(pc, 0)
        if not lowest <= address <= highest:
            print(f"  {address:#x}  outside this dylib")
            continue
        name, offset = containing(table, address - slide)
        print(f"  {address:#x}  {name}+{offset:#x}" if name else f"  {address:#x}  before the first symbol")


if __name__ == "__main__":
    main()