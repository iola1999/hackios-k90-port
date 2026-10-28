"""有输入期间的帧率：性能线唯一的排名依据。

只统计 `tl: p` 有指针事件的时段内、间隔落在十四到二十毫秒之间的帧。没有输入的时段一律不计，
所以这个数不受脚本结束后的空闲刷新率影响，也不受不同轮次脚本长度不同的影响。

整轮 fps 不能作判据：它同时受面板刷新率与空闲期影响，测的是「屏幕有多闲」。
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summary

FRAME_MIN_MS = 14.0
FRAME_MAX_MS = 20.0
TOUCH_TAIL_S = 0.25


def frames(text):
    return sorted(int(m.group(1)) / 1e6 for m in re.finditer(r'^tl: v \d+ ready (\d+) ', text, re.M))


def touches(text):
    return sorted(int(m.group(1)) / 1e6 for m in re.finditer(r'^tl: p \d+ .* at (\d+)$', text, re.M))


def segments(text, split_s=0.5):
    """把指针事件切成连续段。返回每段起点与时长，用于判断样本够不够。"""
    times = touches(text)
    out = []
    for when in times:
        if out and when - out[-1][1] <= split_s:
            out[-1][1] = when
        else:
            out.append([when, when])
    return [(start, end - start) for start, end in out]


def input_fps(text):
    """返回 (有输入期间帧率, 参与统计的帧数, 有输入时段总长)。"""
    frame_times = frames(text)
    touch_times = touches(text)
    if not frame_times or not touch_times:
        return None, 0, 0.0

    inside = 0.0
    counted = 0
    for previous, current in zip(frame_times, frame_times[1:]):
        gap_ms = (current - previous) * 1000
        if not FRAME_MIN_MS <= gap_ms <= FRAME_MAX_MS:
            continue
        # 一个间隔算「有输入」，要求它前后 TOUCH_TAIL_S 内有一个指针事件。
        if not any(previous - TOUCH_TAIL_S <= t <= current + TOUCH_TAIL_S for t in touch_times):
            continue
        counted += 1
        inside += gap_ms / 1000

    return (counted / inside if inside else None), counted, inside


def report(base):
    run = base if base.rstrip('/').endswith('/run') else os.path.join(base, 'run')
    text = summary.merged_log(run)
    rate, counted, span = input_fps(text)
    segs = segments(text)
    longest = max((s for _, s in segs), default=0.0)
    name = os.path.dirname(run).rstrip('/').split('/')[-1]
    if rate is None:
        print(f'{name:42s} no input-period frames')
    else:
        print(f'{name:42s} {rate:5.1f} fps over {span:6.1f} s ({counted} frames); '
              f'{len(segs)} touch segments, longest {longest:.1f} s')


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        report(argument)