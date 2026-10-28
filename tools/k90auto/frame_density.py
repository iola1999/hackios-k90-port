"""拖动窗与静止窗的出帧密度之比，用来判「拖动有没有引起重绘」。

2026-10-28 在 `perf1` 上得到过一组方向相反的读数：拖动窗中位数 0 帧/秒、静止窗 14 帧/秒，
看起来像拖动抑制了出帧，实际是那一轮的拖动整体落在冻结之后（指针唯一行覆盖 583.1～940.7
秒，出帧只到 586.6 秒）。所以这个比值只有在两组窗都落在出帧期内时才有意义，报告里必须同时
给出三样：两组窗各自的时段范围、各组窗落在出帧期内的比例、两组的中位数。缺第一项会把时间
先后读成因果。

窗口取 2 秒。窗内至少一条 `tl: p` 记为拖动窗，否则记为静止窗。出帧期取首帧到末帧的时刻
区间。所有计数按唯一行：同一时刻的行只算一次。
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summary

WINDOW_S = 2.0


def frames(text):
    return sorted({int(m.group(1)) / 1e6 for m in re.finditer(r'^tl: v \d+ ready (\d+) ', text, re.M)})


def touches(text):
    return sorted({int(m.group(1)) / 1e6 for m in re.finditer(r'^tl: p \d+ \d+ \d+ \d+ at (\d+)$', text, re.M)})


def runs(values):
    """把时刻列表合并成连续时段，间隔不超过一个窗口的算同一段。"""
    out = []
    for value in values:
        if out and value - out[-1][1] <= WINDOW_S:
            out[-1][1] = value
        else:
            out.append([value, value])
    return [(start, end) for start, end in out]


def measure(base):
    run_dir = base if base.rstrip('/').endswith('/run') else os.path.join(base, 'run')
    text = summary.merged_log(run_dir)
    frame_times = frames(text)
    touch_times = touches(text)
    if not frame_times or not touch_times:
        return None

    frame_span = (frame_times[0], frame_times[-1])
    start = min(frame_times[0], touch_times[0])
    end = max(frame_times[-1], touch_times[-1])

    drag, still = [], []
    at = start
    while at + WINDOW_S <= end:
        counted = sum(1 for t in frame_times if at <= t < at + WINDOW_S)
        density = counted / WINDOW_S
        dragging = any(at <= t < at + WINDOW_S for t in touch_times)
        inside = at + WINDOW_S <= frame_span[1] and at >= frame_span[0]
        (drag if dragging else still).append((at, density, inside))
        at += WINDOW_S

    return frame_span, (start, end), drag, still


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def show(name, span, start_end, drag, still):
    print(f'{name}')
    print(f'  frames {span[0]:.1f}..{span[1]:.1f} s, pointer {start_end[0]:.1f}..{start_end[1]:.1f} s, '
          f'{len(drag) + len(still)} windows of {WINDOW_S:.0f} s')
    for label, windows in (('drag', drag), ('still', still)):
        if not windows:
            print(f'  {label}: none')
            continue
        inside = [d for at, d, within in windows if within]
        share = 100 * len(inside) / len(windows)
        both = median([d for at, d, within in windows])
        print(f'  {label}: {len(windows)} windows, {share:.0f} drops in the frame period, '
              f'median {both if both is None else round(both, 1)} fps overall, '
              f'{median(inside) if inside else "n/a"} fps inside the frame period')
        print('    seen at ' + ', '.join(f'{a:.0f}..{b:.0f}' for a, b in runs([at for at, _, _ in windows])))
    drag_inside = median([d for at, d, within in drag if within])
    still_inside = median([d for at, d, within in still if within])
    if drag_inside is None or still_inside is None:
        print('  ratio: n/a, one side has no window inside the frame period')
    elif still_inside == 0:
        print(f'  ratio: n/a, still windows average 0 fps inside the frame period')
    else:
        print(f'  ratio: {drag_inside / still_inside:.2f} (drag {drag_inside} fps over still {still_inside} fps, '
              f'inside the frame period)')


if __name__ == '__main__':
    for path in sys.argv[1:]:
        result = measure(path)
        if result is None:
            print(f'{path}: no frames or no pointer events')
            continue
        show(path.rstrip('/').split('/')[-2] if path.rstrip('/').endswith('run') else path.rstrip('/').split('/')[-1], *result)