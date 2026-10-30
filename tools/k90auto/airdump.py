#!/usr/bin/env python3
"""Write back the AIR modules the driver printed with REDWOOD_DUMP_AIR.

usage: tools/k90auto/airdump.py ROUND_DIR

The driver prints each render pipeline function's bitcode once, as `air dump NAME: N bytes`
followed by base64 lines `air dump NAME K: ...` (redwoodmetal_diag.inc). This writes
ROUND_DIR/air/NAME.bc for every module that arrived whole, and names the ones the log upload
lost lines of. Read a module with llvm-dis.
"""
import base64
import importlib.util
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
HEADER = re.compile(r"redwoodmetal\[(\S+) \d+\]: air dump (\S+): (\d+) bytes")
CHUNK = re.compile(r"redwoodmetal\[(\S+) \d+\]: air dump (\S+) (\d+): ([A-Za-z0-9+/=]+)\s*$")


def merged(run_dir):
    spec = importlib.util.spec_from_file_location("render_health", HERE / "render-health.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text, _ = module.merge(Path(run_dir) / "run")
    return text


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    run_dir = Path(sys.argv[1])
    sizes, chunks = {}, {}
    for line in merged(run_dir).splitlines():
        m = HEADER.search(line)
        if m:
            sizes[m.group(2)] = int(m.group(3))
            continue
        m = CHUNK.search(line)
        if m:
            chunks.setdefault(m.group(2), {})[int(m.group(3))] = m.group(4)
    if not sizes:
        print("no air dump in this round's log")
        return 1
    out = run_dir / "air"
    out.mkdir(exist_ok=True)
    whole, broken = 0, []
    for name, size in sorted(sizes.items()):
        parts = chunks.get(name, {})
        expected = (4 * ((size + 2) // 3) + 95) // 96
        missing = [k for k in range(expected) if k not in parts]
        if missing:
            broken.append(f"{name} ({len(missing)} of {expected} lines lost)")
            continue
        data = base64.b64decode("".join(parts[k] for k in range(expected)))
        if len(data) != size:
            broken.append(f"{name} ({len(data)} bytes decoded, {size} printed)")
            continue
        (out / f"{name}.bc").write_bytes(data)
        whole += 1
    print(f"{whole} modules written to {out}")
    for line in broken:
        print("incomplete:", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
