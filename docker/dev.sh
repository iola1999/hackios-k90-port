#!/usr/bin/env bash
# Interactive container with the whole workspace at /work.
# --privileged: userland/build.sh mounts/loops images; QEMU needs several GB RAM
# (OrbStack VM memory is the real cap -- raise it in OrbStack settings if QEMU
#  dies, or lower guest RAM with QEMU_RAM_GB=4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# The iOS 26 SDK of the kernel tree is a symlink farm into the host's Xcode SDK (its System,
# Developer and Entitlements.plist all point inside one iPhoneOS*.sdk), so a container that does not
# carry that same absolute path sees no framework header at all and userland/build.sh stops on
# "CoreFoundation/CoreFoundation.h not found". The path is read off the link rather than written
# down here: an Xcode update moves it. The mount is read only and optional -- no host Xcode, no
# link, or a link that resolves to nothing leaves the container exactly as it was, with one line
# saying which SDK path is missing.
SDK_ARGS=()
SDK26_LINK="$ROOT/hackios-xnu-kernel/xnu-deps/26/sdk/iPhoneOS.sdk/System"
if SDK26="$(readlink "$SDK26_LINK" 2>/dev/null)"; then
  SDK26="${SDK26%/System}"
  if [ -n "$SDK26" ] && [ -d "$SDK26" ]; then
    SDK_ARGS=(-v "$SDK26:$SDK26:ro")
  else
    echo "dev.sh: the iOS 26 SDK points at ${SDK26:-nothing}, which is not a directory here" >&2
    echo "dev.sh: starting without it; iOS 26 userland builds will not find their framework headers" >&2
  fi
else
  echo "dev.sh: $SDK26_LINK is not a symlink; no host SDK to mount" >&2
fi

exec docker run --rm -it --privileged \
  -v "$ROOT":/work \
  ${SDK_ARGS[@]+"${SDK_ARGS[@]}"} \
  -e QEMU_RAM_GB="${QEMU_RAM_GB:-4}" \
  hackios-dev:latest bash "$@"
