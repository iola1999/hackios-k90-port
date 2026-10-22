#!/bin/bash
# device-test.sh -- run the annibale verification battery unattended.
# Assumes the phone is reachable (Android with adb, or LK fastboot).
# See docs/plan/device-test-playbook.md for the decision tree this automates.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
K="$ROOT/hackios-xnu-kernel"
SER=${SER:-${ANDROID_SERIAL}}
say() { echo "[device-test] $*"; }

in_fastboot() { timeout 2 fastboot devices 2>/dev/null | grep -q fastboot; }
in_android()  { adb -s "$SER" get-state >/dev/null 2>&1; }

to_lk_fastboot() {
  in_fastboot && { say "already in fastboot (if ioreg shows 2510DRK44C this is fastbootd: run: fastboot reboot bootloader)"; return 0; }
  in_android || { say "phone not visible (off? unlock screen? adb?)"; return 1; }
  say "rebooting Android -> LK fastboot ..."
  adb -s "$SER" reboot bootloader
  for _ in $(seq 1 30); do sleep 2; in_fastboot && return 0; done
  say "fastboot never appeared"; return 1
}

boot_with_retry() { # boot_with_retry <img> -- LK is moody: re-enter fastboot and retry
  local img=$1 r
  for try in 1 2 3; do
    to_lk_fastboot || return 1
    r=$(cd "$K" && timeout 30 fastboot boot "$(basename "$img")" 2>&1 | grep -oE "OKAY|FAILED" | tail -1)
    [ "$r" = "OKAY" ] && { say "boot OKAY (try $try)"; return 0; }
    say "Load Error (try $try) -- power-cycling the bootloader"
    timeout 10 fastboot reboot >/dev/null 2>&1; sleep 12
    ( in_android && adb -s "$SER" reboot bootloader && for _ in $(seq 1 30); do sleep 2; in_fastboot && break; done ) >/dev/null 2>&1
  done; return 1
}

probe_loader() { # watch for the resident loader (getvar product: xnuloader)
  for _ in $(seq 1 60); do
    if timeout 2 fastboot getvar product 2>/dev/null | grep -q xnuloader; then return 0; fi
    sleep 1
  done; return 1
}

say "== stage 0: reach the phone =="
to_lk_fastboot || exit 1

say "== stage 1: variant A (USB diagnosis) =="
if boot_with_retry "$K/xnu-annibale-log.img"; then
  if probe_loader; then
    say "LOADER IS UP over USB -- full control available:"
    say "  $K/xl log ; $K/xl ramdisk ... ; $K/xl run ; $K/xl screenshot"
    exit 0
  fi
  say "no loader USB within 60s; fetching the boot_a log ..."
fi

say "== stage 2: read the boot_a log partition =="
for _ in $(seq 1 40); do in_fastboot && break; in_android && break; sleep 3; done
got=0
if in_fastboot; then
  timeout 30 fastboot fetch boot_a /tmp/logdump.bin >/dev/null 2>&1 && got=1
fi
[ $got -eq 0 ] && in_android && { adb -s "$SER" shell su -c "dd if=/dev/block/by-name/boot_a bs=4096 count=128 2>/dev/null" > /tmp/logdump.bin; got=1; }
if [ $got -eq 1 ]; then
  if head -c 4096 /tmp/logdump.bin | grep -q "XNULOADER"; then
    say "log found in /tmp/logdump.bin:"; head -40 /tmp/logdump.bin | sed 's/^/  | /'
  else
    say "boot_a has no loader text (all zero?) -- GPT name 'boot_a' mismatch? check by-name list from Android"
  fi
fi
say "done. Decision tree: docs/plan/device-test-playbook.md"
