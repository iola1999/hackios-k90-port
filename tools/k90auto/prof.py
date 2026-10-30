#!/usr/bin/env python3
"""Read the interrupt-sampled profile (kern.redwood.prof) of a round and name its places.

usage: tools/k90auto/prof.py ROUND_DIR [--slide HEX] [--top N] [--threads PID]

The kernel (12377-cmd23 and later) samples the interrupted context at every interrupt; rwsh
"sysctl kern.redwood.prof_on=1" starts it and "sysctl kern.redwood.prof" prints it, which rsh.py
leaves in ROUND_DIR/run/cmd-*.log. This takes the newest printout there and prints:
  - samples per process, user and kernel apart, with the process names from the newest "ps";
  - the most frequent places, a user pc and lr as image+offset in the shared cache (the slide is
    the newest "tl: td PID slide" line, which a "dump PID" prints, or --slide), with the nearest
    exported symbol when the image exports one below it; a kernel pc as symbol+offset from the
    round's kernel (kernsym.py).
With --threads PID it prints the user backtraces of that process's threads instead ("tl: td PID tid
T bt ..." lines and their "bt+" continuations, one set per "dump PID"), the same stack once with the number of dumps it was seen in.
"""
import argparse
import bisect
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
sys.path.insert(0, str(WORKSPACE / "hackios-xnu-kernel/tools/dsc"))
import cache as dsc_cache  # noqa: E402
import macho  # noqa: E402

CACHE_DIR = WORKSPACE / "hackios-xnu-kernel/ios26/23G90__iPhone18,3"


def logs(run):
    texts = []
    for path in sorted(run.glob("cmd-*.log"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        texts.append(path.read_bytes().decode("utf-8", "replace").replace("\0", ""))
    return "\n".join(texts)


def snapshots(run):
    """The periodic log snapshots, where a process's first lines are (the cmd logs start later)."""
    return [path.read_bytes().decode("utf-8", "replace") for path in sorted(run.glob("s[0-9]*.log"))]


def newest_profile(text):
    """The lines of the last kern.redwood.prof printout: rwsh SEQ| lines after its first one."""
    starts = [m for m in re.finditer(r"^rwsh (\d+)\| kern\.redwood\.prof = (samples .*)$", text, re.M)]
    if not starts:
        return []
    last = starts[-1]
    seq = last.group(1)
    lines = [last.group(2)]
    for line in text[last.end():].splitlines():
        m = re.match(rf"^rwsh {seq}\| (.*)$", line)
        if m:
            lines.append(m.group(1))
        elif line.startswith(f"rwsh {seq} exit"):
            break
    return lines


def process_names(text):
    names = {"-2": "(idle)", "0": "(kernel)"}
    for m in re.finditer(r"^rwsh \d+\|\s+(\d+)\s+\d+\s+\d+\s+[\d.]+\s+[\d.]+\s+\d+ (.+)$", text, re.M):
        names[m.group(1)] = m.group(2).strip()
    return names


# The driver and the compiler library are not in the shared cache. The driver says where each
# process loaded them ("[NAME PID] images: driver 0x... air 0x...", redwoodmetal_console.inc), and
# their symbols are read from the builds package.py left in OWN_IMAGES_DIR, which are the round's own
# only until the next pack.
OWN_IMAGES_DIR = WORKSPACE / "hackios-xnu-kernel/out/ios26-resume/bbmetal-device"
OWN_IMAGES = {"driver": "libredwoodmetal.dylib", "air": "libredwoodair.dylib"}


def own_image_bases(text):
    bases = {}
    for m in re.finditer(r"\[\S+ (\d+)\] images: driver (0x[0-9a-f]+) air (0x[0-9a-f]+)", text):
        bases[int(m.group(1))] = {"driver": int(m.group(2), 16), "air": int(m.group(3), 16)}
    return bases


class UserNames:
    def __init__(self, slide, bases=None):
        self.cache = dsc_cache.Cache(str(CACHE_DIR))
        self.slide = slide
        self.exports = {}
        self.bases = bases or {}
        self.own = {}

    def own_symbol(self, which, offset):
        if which not in self.own:
            table = []
            path = OWN_IMAGES_DIR / OWN_IMAGES[which]
            out = subprocess.run(["nm", "-n", "--defined-only", str(path)], capture_output=True, text=True).stdout
            for line in out.splitlines():
                parts = line.split(None, 2)
                if len(parts) == 3 and parts[1] in "tT":
                    table.append((int(parts[0], 16), parts[2]))
            self.own[which] = table
        table = self.own[which]
        i = bisect.bisect_right(table, (offset, "\uffff")) - 1
        return f"{table[i][1]}+{offset - table[i][0]:#x}" if i >= 0 else None

    def own_name(self, pc, pid):
        # The nearest base below the pc; an image is far smaller than the gap to the next one.
        below = [(base, which) for which, base in self.bases.get(pid, {}).items() if base <= pc]
        if not below:
            return None
        base, which = max(below)
        if pc - base > 64 << 20:
            return None
        sym = self.own_symbol(which, pc - base)
        return f"{OWN_IMAGES[which]}+{pc - base:#x}" + (f" ({sym})" if sym else "")

    def symbol(self, image, address):
        if image.path not in self.exports:
            table = []
            try:
                for name, kind, value, _extra in macho.exports(self.cache, image):
                    if kind == "regular" and value:
                        table.append((value, name))
            except Exception:
                pass
            table.sort()
            self.exports[image.path] = table
        table = self.exports[image.path]
        i = bisect.bisect_right(table, (address, "￿")) - 1
        return f"{table[i][1]}+{address - table[i][0]:#x}" if i >= 0 else None

    def name(self, pc, pid=None):
        address = pc - self.slide
        if not (self.cache.shared_region_start <= address <
                self.cache.shared_region_start + self.cache.shared_region_size):
            return (self.own_name(pc, pid) if pid is not None else None) or f"{pc:#x}"
        try:
            image = self.cache.image_of(address)
        except Exception:
            image = None
        if image is None:
            return f"{pc:#x}"
        short = image.path.rsplit("/", 1)[-1]
        sym = self.symbol(image, address)
        return f"{short}+{address - image.address:#x}" + (f" ({sym})" if sym else "")


def kernel_names(round_dir, pcs):
    manifest = json.loads((round_dir / "manifest.json").read_text()) if (round_dir / "manifest.json").exists() else {}
    kernel = manifest.get("kernel", {}).get("path")
    if not kernel or not pcs:
        return {}
    out = subprocess.run([sys.executable, str(HERE / "kernsym.py"), "--kernel", str(WORKSPACE / kernel)],
                         input="\n".join(f"pc {pc:#x}" for pc in pcs), capture_output=True, text=True).stdout
    return dict(zip(pcs, [line.strip() for line in out.splitlines()]))


def threads(text, pid, user):
    # A kernel from 12377-cmd28 on continues a long backtrace on "bt+" lines right after the "bt" one.
    stacks = collections.Counter()
    tid, frames = None, ()
    for m in re.finditer(rf"tl: td {pid} tid (\d+) bt(\+?) ((?:[0-9a-f]+ ?)+)", text):
        more = tuple(int(x, 16) for x in m.group(3).split() if int(x, 16))
        if m.group(2) and m.group(1) == tid:
            frames += more
            continue
        if frames:
            stacks[(tid, frames)] += 1
        tid, frames = m.group(1), more
    if frames:
        stacks[(tid, frames)] += 1
    for (tid, frames), count in sorted(stacks.items(), key=lambda kv: (-kv[1], kv[0][0])):
        print(f"tid {tid}: seen {count}")
        for pc in frames:
            print(f"    {user.name(pc, pid)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("round_dir", type=Path)
    ap.add_argument("--slide", type=lambda s: int(s, 16))
    ap.add_argument("--top", type=int, default=64)
    ap.add_argument("--threads", type=int, metavar="PID")
    args = ap.parse_args()
    text = logs(args.round_dir / "run")
    if args.threads is not None:
        slides = re.findall(rf"tl: td {args.threads} slide (0x[0-9a-f]+)", text)
        slide = args.slide if args.slide is not None else int(slides[-1], 16) if slides else 0
        threads(text, args.threads,
                UserNames(slide, own_image_bases(text + "\n" + "\n".join(snapshots(args.round_dir / "run")))))
        return 0
    lines = newest_profile(text)
    if not lines:
        print("no kern.redwood.prof printout in the round's cmd logs")
        return 1
    slides = re.findall(r"tl: td \d+ slide (0x[0-9a-f]+)", text)
    slide = args.slide if args.slide is not None else int(slides[-1], 16) if slides else 0
    names = process_names(text)
    print(lines[0], f"(shared cache slide {slide:#x})")
    entries = []
    for line in lines[1:]:
        m = re.match(r"pid (-?\d+) user (\d+) kernel (\d+)", line)
        if m:
            print(f"  {names.get(m.group(1), '?'):32s} pid {m.group(1):>4s}  user {m.group(2):>6s}  kernel {m.group(3):>6s}")
            continue
        m = re.match(r"(\d+) (-?\d+) ([uk]) ([0-9a-f]+) ([0-9a-f]+)", line)
        if m:
            entries.append((int(m.group(1)), m.group(2), m.group(3), int(m.group(4), 16), int(m.group(5), 16)))
    user = UserNames(slide, own_image_bases(text + "\n" + "\n".join(snapshots(args.round_dir / "run"))))
    kernel = kernel_names(args.round_dir, sorted({a for e in entries if e[2] == "k" for a in e[3:5] if a}))
    for count, pid, where, pc, lr in entries[:args.top]:
        who = names.get(pid, "?")[:20]
        if where == "u":
            print(f"{count:6d} {who:20s} u {user.name(pc, int(pid))}  <- {user.name(lr, int(pid))}")
        else:
            print(f"{count:6d} {who:20s} k {kernel.get(pc, hex(pc))}  <- {kernel.get(lr, hex(lr))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
