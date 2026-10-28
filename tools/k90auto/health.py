"""一轮跑完先看两件事：桌面到底起来了没有，以及 backboardd 有没有重起。

两件事都从已有的 `tl:` 行里读，不需要额外插桩。它们解决的是「跑满七分钟才发现那一轮停在锁屏」
这一类白跑：帧数多并不说明桌面起来了，锁屏也会出帧。

桌面起来了的判据：连续五秒内每一帧的间隔都在十四到二十毫秒之间。锁屏的动画、启动时的首帧、
以及停帧之后零星的帧都不满足这一条，所以它不会被这些情形骗过去。
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summary

WINDOW_S = 5.0
FRAME_MIN_MS = 14.0
FRAME_MAX_MS = 20.0


def frames_per_second_of_run(text):
    return sorted(int(m.group(1)) / 1e6 for m in re.finditer(r'^tl: v \d+ ready (\d+) ', text, re.M))


def home_screen(text):
    """返回 (是否在连续出帧, 第一段满足条件的起始秒)。持续五秒的每一帧间隔都在门槛内才算。

    这判的是「有画面在动」，不是「到了主屏」：启动转圈也按稳定帧率出帧，2026-10-28 的
    `linkd` 与 `crashlog` 两轮就是这样被判成 `home screen: yes` 的，而截图最后一分钟仍是
    黑底转圈。是否真的到了主屏只能读截图。
    """
    times = frames_per_second_of_run(text)
    run_start, run_len = None, 0
    for previous, current in zip(times, times[1:]):
        gap_ms = (current - previous) * 1000
        if FRAME_MIN_MS <= gap_ms <= FRAME_MAX_MS:
            if run_len == 0:
                run_start = previous
            run_len = current - run_start
            if run_len >= WINDOW_S:
                return True, run_start
        else:
            run_start, run_len = None, 0
    return False, None


def submits(text):
    return [int(m.group(1)) / 1e6 for m in re.finditer(r'^tl: s \d+ backboardd at (\d+)$', text, re.M)]


def stalls(text, threshold_s=5.0):
    """提交之间的长空档。它不是重起，但一轮的帧率数字要按它切段。

    重起本身在这里看不到：帧号由 shim 计数，进程重起后接着往下数，回退检测因此只对「计数被清零」
    的那一类重起有效。要判重起要看 launchd 侧的记录。
    """
    times = submits(text)
    return [(a, b - a) for a, b in zip(times, times[1:]) if b - a >= threshold_s]


def restarts(text):
    """帧号回退说明计数被清零过，只在那一类重起上有效。"""
    seen = []
    for match in re.finditer(r'^tl: s (\d+) backboardd at (\d+)$', text, re.M):
        number, when = int(match.group(1)), int(match.group(2)) / 1e6
        if seen and number < seen[-1][1]:
            seen.append((when, number))
        elif not seen:
            seen.append((when, number))
    return [when for when, _ in seen][1:]


def report(base):
    run = os.path.join(base, 'run') if not base.rstrip('/').endswith('run') else base
    text = summary.merged_log(run)
    up, when = home_screen(text)
    print(base.rstrip('/').split('/')[-1])
    print(f'  frames: {"steady" if up else "none"}' + (f' from {when:.1f} s' if up else '') +
          f'; {len(frames_per_second_of_run(text))} frames')
    print('  home screen: unknown without reading the screenshots (a start-up spinner draws at a '
          'steady rate too)')
    times = restarts(text)
    print(f'  counter resets: {len(times)}' + (' at ' + ', '.join(f'{t:.1f} s' for t in times) if times else '') +
          ' (a restart that keeps the counter running does not show here; read launchd for that)')
    long_gaps = stalls(text)
    print(f'  submit gaps over 5 s: {len(long_gaps)}' +
          (': ' + ', '.join(f'{a:.1f}+{g:.1f}' for a, g in long_gaps) if long_gaps else ''))


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        report(argument)