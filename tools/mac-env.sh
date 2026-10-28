#!/usr/bin/env bash
# Mac-native host environment for the HackiOS tree (host = macOS, QEMU is TCG
# either way -- qemu/run.sh hardcodes -accel tcg). Source it, then run the
# upstream scripts unmodified:  source tools/mac-env.sh && ios165/fetch.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:$ROOT/tools/hostbin:$PATH"
export QEMU_EFI="$ROOT/tools/qemu-efi/QEMU_EFI.fd"   # brew qemu's edk2-aarch64 (64 MiB unit)
export QEMU_VARS="$ROOT/tools/qemu-efi/QEMU_VARS.fd" # blank vars (EDK2 initializes on first boot)
