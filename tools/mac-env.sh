#!/usr/bin/env bash
# Mac-native host environment for the HackiOS tree (host = macOS, QEMU is TCG
# either way -- qemu/run.sh hardcodes -accel tcg). Source it, then run the
# upstream scripts unmodified:  source tools/mac-env.sh && ios165/fetch.sh
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:$(dirname "$0")/hostbin:$PATH"
export QEMU_EFI="$PWD/tools/qemu-efi/QEMU_EFI.fd"     # brew qemu's edk2-aarch64 (64 MiB unit)
export QEMU_VARS="$PWD/tools/qemu-efi/QEMU_VARS.fd"   # blank vars (EDK2 initializes on first boot)
