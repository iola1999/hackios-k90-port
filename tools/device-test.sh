#!/bin/bash
# device-test.sh -- run the annibale verification battery unattended.
# Assumes the phone is reachable (Android with adb, or LK fastboot).
# See docs/plan/device-test-playbook.md for the decision tree this automates.
set -uo pipefail   # F05: a test battery that cannot see a failed pipe reports the wrong verdict
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
K="$ROOT/hackios-xnu-kernel"
SER=${SER:-${ANDROID_SERIAL}}
say() { echo "[device-test] $*"; }

# every grep below consumes its stream to EOF: with pipefail on, grep -q would kill the producer
# with SIGPIPE and turn a healthy "device present" into a spurious "absent" (F05).
in_fastboot() { timeout 2 fastboot devices 2>/dev/null | grep fastboot >/dev/null; }
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

# F03-BEGIN -- host-simulated verbatim by /tmp/task20/probe_sim.sh (fastboot stubs, three inputs)
probe_loader() { # watch for the resident loader. fastboot answers getvar -- and errors -- on
  # stderr (review F03; the old 2>/dev/null threw the only real output away), so keep both
  # streams and the exit code and name what actually answered: our loader, fastbootd, LK, a
  # dead link, or a timeout. PROBE_TRIES exists so the host simulation does not wait a minute.
  local out rc usersp cls last=""
  for _ in $(seq 1 "${PROBE_TRIES:-60}"); do
    out=$(timeout 2 fastboot getvar product 2>&1); rc=$?
    if [ $rc -eq 124 ]; then cls="timeout (fastboot wedged? check the cable)"
    elif [ $rc -ne 0 ]; then cls="dead link (rc $rc): $(printf %s "$out" | head -1)"
    elif [[ $out == *xnuloader* ]]; then say "getvar: product xnuloader -- the loader is up"; return 0
    else
      usersp=$(timeout 2 fastboot getvar is-userspace 2>&1)
      if [ $? -eq 0 ] && [[ $usersp == *yes* ]]; then cls="fastbootd (userspace): fastboot reboot bootloader to reach LK"
      else cls="LK fastboot, loader not resident yet ($(printf %s "$out" | head -1))"
      fi
    fi
    [ "$cls" = "$last" ] || { say "getvar: $cls"; last=$cls; }
    sleep 1
  done; return 1
}
# F03-END

say "== deps: everything this battery shells out to =="
missing=""
for c in fastboot adb timeout; do command -v "$c" >/dev/null 2>&1 || missing="$missing $c"; done
[ -f "$K/xnu-annibale-log.img" ] || missing="$missing xnu-annibale-log.img(build: common/build.sh annibale)"
[ -z "$missing" ] || { say "MISSING:$missing"; exit 1; }

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
  head4k=$(head -c 4096 /tmp/logdump.bin || true)   # to a variable: reads the pipe to EOF (F05)
  if [[ $head4k == *XNULOADER* ]]; then
    say "log found in /tmp/logdump.bin:"; head -40 /tmp/logdump.bin | sed 's/^/  | /'
  else
    say "boot_a has no loader text (all zero?) -- GPT name 'boot_a' mismatch? check by-name list from Android"
  fi
fi
say "done. Decision tree: docs/plan/device-test-playbook.md"
