#!/usr/bin/env python3
"""Read and trim a /private/var archive written by `var_store save FILE` (a seed).

usage: tools/k90auto/varseed.py list SEED [DEPTH]
       tools/k90auto/varseed.py drop SEED OUT PREFIX...

list prints the bytes and entries under each path of DEPTH components (default 3), largest first.
drop writes OUT without the entries whose path is PREFIX or lies under it, and with a header that
checks out again; a hard link whose first name was dropped is dropped with it. The format is
userland/src/var_store.c's: a 4096-byte header (struct head), then per entry a 48-byte struct entry,
its path, its extended attributes, its contents, and padding to 8 bytes of the archive.
"""
import struct
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

HEAD = struct.Struct("<8sIIQQQQII")
ENTRY = struct.Struct("<IIIIIIIIqQ")
KINDS = {1: "dir", 2: "file", 3: "symlink", 4: "hardlink", 5: "dirtime"}
HARDLINK = 4


def read(path):
    data = Path(path).read_bytes()
    magic, version, slot, generation, size, count, seconds, crc, head_crc = HEAD.unpack_from(data)
    assert magic == b"RDWVAR\0\0" and version == 1, f"{path} is not a var_store archive"
    archive = data[4096:4096 + size]
    assert len(archive) == size and zlib.crc32(archive) == crc, f"{path}: the contents do not check out"
    entries, at = [], 0
    for _ in range(count):
        kind, mode, uid, gid, flags, pathlen, nxattr, nsec, sec, length = ENTRY.unpack_from(archive, at)
        start = at
        at += ENTRY.size
        name = archive[at:at + pathlen].decode("utf-8", "replace")
        at += pathlen
        for _ in range(nxattr):
            namelen, vlen = struct.unpack_from("<II", archive, at)
            at += 8 + namelen + vlen
        if kind != 5:
            tail = archive[at:at + length] if kind == HARDLINK else None
            at += length
        else:
            tail = None
        at += -at % 8
        entries.append({"kind": kind, "path": name, "bytes": length if kind == 2 else 0,
                        "raw": archive[start:at], "first": tail.decode("utf-8", "replace") if tail else None})
    assert at == size, f"{path}: {size - at} bytes after the last entry"
    return generation, entries


def under(path, prefixes):
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("list", "drop"):
        raise SystemExit(__doc__.strip())
    generation, entries = read(sys.argv[2])
    if sys.argv[1] == "list":
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        sizes, counts = defaultdict(int), defaultdict(int)
        for e in entries:
            key = "/".join(e["path"].split("/")[:depth])
            sizes[key] += e["bytes"]
            counts[key] += 1
        print(f"{sum(e['bytes'] for e in entries)} bytes of file contents in {len(entries)} entries")
        for key in sorted(sizes, key=sizes.get, reverse=True)[:60]:
            print(f"{sizes[key]:>12} {counts[key]:>6}  {key}")
        return 0
    out, prefixes = Path(sys.argv[3]), [p.strip("/") for p in sys.argv[4:]]
    kept = [e for e in entries if not under(e["path"], prefixes)
            and not (e["kind"] == HARDLINK and under(e["first"], prefixes))]
    archive = b"".join(e["raw"] for e in kept)
    head = HEAD.pack(b"RDWVAR\0\0", 1, 0, generation, len(archive), len(kept), int(time.time()),
                     zlib.crc32(archive), 0)
    head = HEAD.pack(*HEAD.unpack(head)[:-1], zlib.crc32(head))
    # whole blocks, as var_store's own save leaves them: its load reads the archive block by block
    out.write_bytes(head.ljust(4096, b"\0") + archive + b"\0" * (-len(archive) % 4096))
    print(f"{out}: {len(kept)} of {len(entries)} entries, {len(archive)} bytes "
          f"({sum(e['bytes'] for e in entries) - sum(e['bytes'] for e in kept)} bytes of contents dropped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
