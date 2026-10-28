#!/usr/bin/env python3
"""检查界面进程日志；退出 0 仅确认运行状态，画面仍需单独验收。"""
import argparse
import json
from pathlib import Path
import re


def inspect_logs(paths, processes):
    pids = {name: set() for name in processes}
    failures = set()
    unassigned_assertions = set()
    pid_patterns = {
        name: re.compile(r"(?<![\w])" + re.escape(name) + r"\[(\d+)(?:[:\]])")
        for name in processes
    }
    crash_pattern = re.compile(r"\b(userabort|usertrap):\s+([^\s\[]+)\[(\d+)\]")
    for path in paths:
        # USB 环形日志可含 NUL；文本解码后继续逐行检查，不依赖 grep 的二进制判断。
        text = path.read_bytes().decode("utf-8", errors="replace")
        for name, pattern in pid_patterns.items():
            pids[name].update(map(int, pattern.findall(text)))
        for kind, name, pid in crash_pattern.findall(text):
            if name in pids:
                pids[name].add(int(pid))
                failures.add(f"{name}: {kind}")
        for line in text.splitlines():
            if re.search(r"(?:^|\x00)panic\(cpu|PANIC caller", line):
                failures.add("kernel panic")
            if "Assertion failed:" in line or "failed assertion" in line:
                owners = [name for name, pattern in pid_patterns.items() if pattern.search(line)]
                if owners:
                    failures.update(f"{name}: assertion" for name in owners)
                else:
                    # 无进程前缀的断言保留待审；不能从下一行猜测所有者。
                    unassigned_assertions.add(line.strip())
    for name, values in pids.items():
        if len(values) > 1:
            failures.add(f"{name}: multiple PIDs")
    missing = [name for name, values in pids.items() if not values]
    status = "failed" if failures else "review_required" if missing or unassigned_assertions else "observed"
    return {
        "status": status,
        "process_pids": {name: sorted(values) for name, values in pids.items()},
        "failures": sorted(failures),
        "missing_processes": missing,
        "unassigned_assertion_count": len(unassigned_assertions),
        "scope": "Selected logs only; display, gestures, frame rate and GPU rendering require separate validation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--process", action="append", default=[], help="增加本轮预期出现的进程")
    parser.add_argument("--output", type=Path, help="保存 JSON 检查结果")
    args = parser.parse_args()
    processes = list(dict.fromkeys(["SpringBoard", "backboardd", *args.process]))
    try:
        result = inspect_logs(args.logs, processes)
    except OSError as error:
        parser.error(str(error))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    return {"observed": 0, "failed": 2, "review_required": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
