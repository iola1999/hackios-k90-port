#!/usr/bin/env python3
"""kernsym.py — 把内核 pc 解到符号与偏移。

输入是内核态地址（`__TEXT` 里 `0xfffffff007...` 那一档），输出所在符号与符号内偏移。
内核开了 KASLR，运行期 pc 带着 slide；把日志里读到的 pc 原样传入，或用 `--slide`
显式给出，工具先减去 slide 再查表。

符号表来自 `nm -n`，按地址升序，用二分查找定位「地址不大于 pc 的最后一个符号」。
同地址多条时取第一条（`nm -n` 里 `BRK_AUTDA_FAILURE` 这类会重复三份）。

用法（纯函数式，输入走参数或 stdin，输出走 stdout）：
    kernsym.py --pc 0xfffffff00712a3b4
    kernsym.py --slide 0x120000 --pc 0xfffffff00712a3b4
    echo 'pc 0xfffffff00712a3b4' | kernsym.py

stdin 每行一个 pc：优先取 `pc 0x...` 字段，其次取行内最后一个 0x 十六进制数，
其余内容忽略；`--pc` 与 stdin 可以混用。用户态地址（低于 `0xfffffff000000000`）
直接报 `not-kernel`，这类 pc 交给 `stubsym.py`。

可选参数：
    --kernel   内核镜像路径，默认 out/xnu12377/BUILD/obj/mach.development.bcm2837
    --slide    KASLR slide，十六进制或十进制，默认 0
"""

import argparse
import bisect
import os
import re
import subprocess
import sys

DEFAULT_KERNEL = "out/xnu12377/BUILD/obj/mach.development.bcm2837"
KERNEL_FLOOR = 0xFFFFFFF000000000


def load_symbols(path):
    """返回 (地址列表, 名字列表)。地址升序，同地址保留第一条。"""
    if not os.path.exists(path):
        raise SystemExit(f"kernel not found: {path}")
    out = subprocess.run(["nm", "-n", path], capture_output=True, text=True, check=True).stdout
    addrs, names = [], []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        if addrs and addr <= addrs[-1]:
            continue
        addrs.append(addr)
        names.append(parts[2].strip())
    return addrs, names


def resolve(pc, slide, addrs, names):
    raw = pc
    if pc >= KERNEL_FLOOR:
        pc -= slide
    else:
        return f"0x{raw:x} not-kernel"
    i = bisect.bisect_right(addrs, pc) - 1
    if i < 0:
        return f"0x{raw:x} below-first-symbol"
    return f"0x{raw:x} {names[i]}+0x{pc - addrs[i]:x}"


def pc_from_line(line):
    m = re.search(r"\bpc\s+(0x[0-9a-fA-F]+)", line)
    if m:
        return int(m.group(1), 16)
    hits = re.findall(r"0x[0-9a-fA-F]+", line)
    if not hits:
        return None
    return int(hits[-1], 16)


def main():
    ap = argparse.ArgumentParser(description="resolves kernel pcs to symbols")
    ap.add_argument("--kernel", default=DEFAULT_KERNEL)
    ap.add_argument("--slide", default="0")
    ap.add_argument("--pc", action="append", default=[])
    args = ap.parse_args()

    slide = int(str(args.slide), 0)
    pcs = [int(p, 0) for p in args.pc]
    for line in sys.stdin:
        pc = pc_from_line(line)
        if pc is not None:
            pcs.append(pc)
    if not pcs:
        ap.error("no pcs given")

    addrs, names = load_symbols(args.kernel)
    for pc in pcs:
        print(resolve(pc, slide, addrs, names))


if __name__ == "__main__":
    main()