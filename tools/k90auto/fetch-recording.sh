#!/bin/bash
# usage: tools/k90auto/fetch-recording.sh ROUND_DIR OUT.bin
# Fetch the kernel's screen recording (boot-args rec_secs=...) while a round is held (cycle.py --hold),
# before it is stopped: the teardown resets the phone. Needs the loader that started the kernel to be
# v13 or later (oem stage). The address is the "into N MB at 0x..." line of the round's log, the length
# comes from the RWREC003 header.
set -e
round=$1; out=$2
log=$(ls "$round"/run/s*.log | tail -1)
addr=$(grep -ao "into [0-9]* MB at 0x[0-9a-f]*" "$log" | tail -1 | awk '{print $NF}')
[ -n "$addr" ] || { echo "no recording address in $log"; exit 1; }
hex=${addr#0x}
tmp=$(mktemp -d)
fastboot -s xnuloader oem stage "$hex" 20 >/dev/null 2>&1
fastboot -s xnuloader get_staged "$tmp/hdr.bin" >/dev/null 2>&1
len=$(python3 -I -c "
import struct,sys
m,w,h,f,o=struct.unpack('<8sIIII',open('$tmp/hdr.bin','rb').read(24))
assert m==b'RWREC003',m
print('%x' % (32+f*(8+w*h*3)))
print(w,h,f,o,file=sys.stderr)")
echo "recording at $addr, length 0x$len"
fastboot -s xnuloader oem stage "$hex" "$len" 2>&1 | tail -1
time fastboot -s xnuloader get_staged "$out" 2>&1 | tail -2
ls -la "$out"
rm -rf "$tmp"
