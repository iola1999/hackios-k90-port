#!/usr/bin/env python3
"""stubsym.py — 把 redwood dump 里的用户态 pc 解码成 libsystem_kernel 桩的系统调用名。

方法（对应 docs/plan/k90auto-run-protocol.md §「符号化 pc 走 stub 的系统调用号」）：
- dump 保存的 pc 是返回地址，指向桩里 svc #0x80 之后的第一条指令。桩的固定形状是
  movz x16, #imm（BSD 系统调用）或 movn x16, #imm（mach trap，调用号 = -(imm+1)），
  随后 svc。解码时从 pc 往回最多扫 4 条指令（pc-16..pc-4），取离 pc 最近的 x16 装载指令。
- 号码到名字：正数查 bsd/kern/syscalls.master（同一号码可能有多行，例如 305 先
  psynch_cvwait 后 nosys，取文件里第一条）；负数查 osfmk/mach/syscall_sw.h 的
  kernel_trap(name, num, argc) 行。
- pc 到缓存文件偏移：u = pc - slide 得到未加偏移地址；off = u - LOAD + FOFF。
  LOAD 是 libsystem_kernel 在 dyld 共享缓存里的加载地址，FOFF 是它的文件偏移。
  FOFF 用缓存头部自己的 mapping 表定位：mapping 条目带 address/size/fileOffset，
  取地址区间包含 LOAD 的条目，FOFF = fileOffset + (LOAD - address)。当前默认值
  对应 .46 子缓存（条目 addr 0x22c8a8000 size 0x6b98000 fileOffset 0，
  LOAD 0x232f09000，得 FOFF 0x6661000），与该缓存的归属复核一致。

用法（纯函数式：输入走参数或 stdin，输出走 stdout，不依赖轮次目录布局）：
    stubsym.py --slide 0x105a4000 --pc 0x2434b35e8 --pc 0x2434ada54
    echo 0x2434b35e8 | stubsym.py --slide 0x105a4000
stdin 每行一个 pc：优先取 `pc 0x...` 字段，其次取行内最后一个 0x 十六进制数，
其余内容忽略（dump 行可以整行贴进来）；--pc 与 stdin 可以混用。
可选参数（默认值对应当前 ios26 .46 缓存与 out/xnu12377 内核树，均相对当前目录）：
    --stub-file   共享缓存文件
    --load        libsystem_kernel 加载地址（未加 slide 的 u 空间）
    --file-off    libsystem_kernel 文件偏移
    --master      syscalls.master 路径
    --syscall-sw  syscall_sw.h 路径
输出每个 pc 一行：
    <pc> u=<去 slide 地址> off=+<镜像内偏移> num=<调用号> name=<名字>
解码失败时 name= 给出失败环节（无装载指令 / 号码不在表 / 偏移出文件范围）。
pc 解码失败退出码仍为 0（逐行报告）；用法错误（缺 slide、无任何 pc）退出码 2。
"""
import argparse
import re
import struct
import sys

MOVZ_X16 = 0xD2800010
MOVN_X16 = 0x92800010
OP_MASK = 0xFF80001F


def load_bsd_table(path):
    table = {}
    pat = re.compile(r'^(\d+)\s+AUE_\w+\s+\S+\s+\{\s*\S+\s+(\w+)')
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = pat.match(line)
            if m and int(m.group(1)) not in table:   # 同号码取第一条
                table[int(m.group(1))] = m.group(2)
    return table


def load_mach_table(path):
    table = {}
    pat = re.compile(r'kernel_trap\((\w+),\s*(-\d+)')
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = pat.search(line)
            if m:
                table[int(m.group(2))] = m.group(1)
    return table


class Context:
    def __init__(self, stub_file, load, file_off, master, syscall_sw):
        self.load = load
        self.file_off = file_off
        self.bsd = load_bsd_table(master)
        self.mach = load_mach_table(syscall_sw)
        with open(stub_file, 'rb') as fh:
            self.size = fh.seek(0, 2)
        self.stub_file = stub_file

    def num_to_name(self, num):
        if num > 0:
            return self.bsd.get(num)
        if num < 0:
            return self.mach.get(num)
        return None

    def decode(self, pc, slide):
        u = pc - slide
        off = u - self.load
        if off < 0:
            return None, 'u=%#x off=%#x 为负，pc 不在 libsystem_kernel 区' % (u, off)
        fpos = self.file_off + off
        if fpos < 16 or fpos >= self.size:
            return None, '文件偏移 %#x 超出 %s 范围' % (fpos, self.stub_file)
        with open(self.stub_file, 'rb') as fh:
            fh.seek(fpos - 16)
            words = struct.unpack('<4I', fh.read(16))
        for w in reversed(words):                    # 离 pc 最近的装载指令优先
            if (w & OP_MASK) == MOVN_X16:
                return -(((w >> 5) & 0xFFFF) + 1), None
            if (w & OP_MASK) == MOVZ_X16:
                return (w >> 5) & 0xFFFF, None
        return None, 'pc-16..pc-4 无 movz/movn x16（words=%s）' % [hex(w) for w in words]


def format_result(pc, slide, ctx):
    u = pc - slide
    num, err = ctx.decode(pc, slide)
    head = '%#x u=%#x off=%#x' % (pc, u, u - ctx.load)
    if err:
        return '%s num=- name=解码失败(%s)' % (head, err)
    name = ctx.num_to_name(num)
    if name is None:
        return '%s num=%d name=号码不在表' % (head, num)
    return '%s num=%d name=%s' % (head, num, name)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description=__doc__.splitlines()[0])
    ap.add_argument('--slide', required=True)
    ap.add_argument('--pc', action='append', default=[])
    ap.add_argument('--stub-file',
                    default='hackios-xnu-kernel/ios26/23G90__iPhone18,3/dyld_shared_cache_arm64e.46')
    ap.add_argument('--load', default='0x232f09000')
    ap.add_argument('--file-off', default='0x6661000')
    ap.add_argument('--master', default='hackios-xnu-kernel/out/xnu12377/bsd/kern/syscalls.master')
    ap.add_argument('--syscall-sw', default='hackios-xnu-kernel/out/xnu12377/osfmk/mach/syscall_sw.h')
    args = ap.parse_args(argv)

    pcs = [int(p, 16) for p in args.pc]
    if not sys.stdin.isatty():
        for line in sys.stdin:
            m = re.search(r'\bpc (0x[0-9a-fA-F]+)', line)
            if m:
                pcs.append(int(m.group(1), 16))
                continue
            found = re.findall(r'0x[0-9a-fA-F]+', line)
            if found:
                pcs.append(int(found[-1], 16))
    if not pcs:
        ap.error('没有任何 pc（--pc 或 stdin）')
    slide = int(args.slide, 16)
    ctx = Context(args.stub_file, int(args.load, 16), int(args.file_off, 16),
                  args.master, args.syscall_sw)
    for pc in pcs:
        print(format_result(pc, slide, ctx))
    return 0


if __name__ == '__main__':
    sys.exit(main())
