#!/usr/bin/env python3
"""Scan serial baud rates live during a boot window; report byte counts and ASCII-ness."""
import sys, time, termios, struct, fcntl, tty

PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.wchusbserial3120'
TOTAL = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
BAUDS = [921600, 460800, 230400, 1500000, 115200, 57600]
CODE = {b: b for b in BAUDS}  # macOS/BSD termios uses the raw baud number

fd = open(PORT, 'rb+', buffering=0)
tty.setraw(fd)
per = TOTAL / len(BAUDS)
res = {}
for b in BAUDS:
    attrs = termios.tcgetattr(fd)
    attrs[4] = attrs[5] = CODE[b]
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    time.sleep(0.2)
    data = b''
    end = time.time() + per
    import select
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                data += fd.read(4096)
            except Exception:
                break
    printable = sum(1 for c in data if 32 <= c < 127 or c in (10, 13))
    res[b] = (len(data), printable)
    print(f'baud {b}: {len(data)} bytes, {printable} ascii', flush=True)
fd.close()
best = max(res, key=lambda b: res[b][1])
print(f'BEST: {best} ({res[best][1]} printable)', file=sys.stderr)
