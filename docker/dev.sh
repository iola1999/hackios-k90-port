#!/usr/bin/env bash
# Interactive container with the whole workspace at /work.
# --privileged: userland/build.sh mounts/loops images; QEMU needs several GB RAM
# (OrbStack VM memory is the real cap -- raise it in OrbStack settings if QEMU
#  dies, or lower guest RAM with QEMU_RAM_GB=4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec docker run --rm -it --privileged \
  -v "$ROOT":/work \
  -e QEMU_RAM_GB="${QEMU_RAM_GB:-4}" \
  hackios-dev:latest bash "$@"
