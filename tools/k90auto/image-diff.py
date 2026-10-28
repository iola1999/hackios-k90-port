#!/usr/bin/env python3
"""Entry-level diff between two APFS root images: the standing pack-acceptance gate.

package.py's own gates compare the driver and AIR hashes and the dirty state of the sources;
none of them compares the packed image against what the previous round actually ran, so a
recipe gap packs silently: round F's first attempt omitted PAYLOAD_PROGRAMS (the channel
that carries /bin/framewatch, package.py:53-56/:452-454) and the image shipped without
framewatch — every sampling instance died on "No such file or directory" while lsprobe,
rwtouch and the touch lines all worked, and the round would have looked alive. A companion
gap in the recipe walk: added files leave only a null->sha trace in the pack record's
changes field, so recipe reconciliation must attribute every null->sha entry to its channel
(EXTRA_JOBS / PROBE / PAYLOAD_PROGRAMS) and treat an unattributable one as a gap.

This gate compares a new image against a known-good reference image entry by entry: names,
kind, size, content sha256, mode and xattrs. Timestamps and owner are deliberately not
compared: mkapfs.py forces every timestamp to --time (default 1683900000) and uid/gid to 0,
so they carry no host-side information; mode does (it is the only field taken from the host
file, mkapfs.py:126-135).

usage: image-diff.py OLD.apfs NEW.apfs [--expect-diff PATH ...] [--expect-absent PATH ...]
       [--expect-present PATH ...]
--expect-diff lists the entries allowed to differ (a jobs-only round lists /etc/rc.jobs).
The gate passes when: entry counts are equal, no entry exists on only one side, the differing
set equals --expect-diff exactly, every --expect-present entry is on both sides with equal
content sha256, and no --expect-absent entry is on either side. Exit 0 on pass, 1 on fail
with every violation printed (not just the first).
"""
import hashlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "hackios-xnu-kernel/tools/apfs"
sys.path.insert(0, str(TOOLS))
from apfs import Container, pick_volume, walk, ROOT_DIR_INO_NUM  # noqa: E402

# What the round is measured on; everything else in the image is context.
META = ("kind", "mode")


def entries(path):
    container = Container(str(path))
    volume = pick_volume(container, None)
    out = {}
    for name, _, fid, kind in [("/", "", ROOT_DIR_INO_NUM, 4), *walk(volume, ROOT_DIR_INO_NUM)]:
        inode = volume.inode(fid)
        body = inode.contents() if kind == 8 else inode.symlink_target_bytes() if kind == 10 else b""
        xattrs = {n: hashlib.sha256(volume.xattr_bytes(fid, n, inode.xattrs)).hexdigest()
                  for n in inode.xattrs}
        out[name] = {"kind": kind, "mode": inode.mode, "size": len(body),
                     "sha256": hashlib.sha256(body).hexdigest(), "xattrs": xattrs}
    return out


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    old_path, new_path = args[0], args[1]
    expect_diff, expect_absent, expect_present = [], [], []
    bucket = None
    for a in args[2:]:
        if a == "--expect-diff":
            bucket = expect_diff
        elif a == "--expect-absent":
            bucket = expect_absent
        elif a == "--expect-present":
            bucket = expect_present
        else:
            bucket.append(a)
    old, new = entries(old_path), entries(new_path)
    fails = []
    if len(old) != len(new):
        fails.append(f"entry count differs: old {len(old)} vs new {len(new)}")
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    if only_old:
        fails.append(f"entries only in old: {only_old}")
    if only_new:
        fails.append(f"entries only in new: {only_new}")
    differing = sorted(n for n in set(old) & set(new) if old[n] != new[n])
    if differing != sorted(expect_diff):
        fails.append(f"differing entries {differing} != expected {sorted(expect_diff)}")
    for name in expect_present:
        if name not in old or name not in new:
            fails.append(f"expected present on both sides, missing: {name}")
        elif old[name]["sha256"] != new[name]["sha256"]:
            fails.append(f"expected present identical, content differs: {name}")
    for name in expect_absent:
        for tag, side in (("old", old), ("new", new)):
            if name in side:
                fails.append(f"expected absent, present in {tag}: {name}")
    print(f"old {old_path}: {len(old)} entries")
    print(f"new {new_path}: {len(new)} entries")
    print(f"differing: {differing}")
    if fails:
        for f in fails:
            print("FAIL:", f)
        sys.exit(1)
    print("PASS: entry sets identical outside the expected diff")


if __name__ == "__main__":
    main()
