#!/bin/bash
# Apply hackios's Mu-Silicium patch (BootShim XNUP copy + BootManager autostart)
# to a Mu-Silicium checkout. Idempotent: skips if already applied.
# usage: apply-mu-patch.sh [MU_DIR]
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MU="${1:-$ROOT/hackios-xnu-kernel/Mu-Silicium}"
PATCH="$ROOT/hackios-xnu-kernel/uefi/mu-silicium.patch"
cd "$MU"
# XnuLoader.c is created by the patch AND carries k90-port tweaks (boot_a log
# partition), so a content-based reverse check lies once we edit it -- use
# presence as the applied marker instead.
if [ -f Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.c ]; then
  echo "apply-mu-patch: already applied"
else
  git apply --whitespace=nowarn "$PATCH"
  echo "apply-mu-patch: applied"
fi
# BootManagerLib.inf gains XnuLoader.c/h -- shipped by uefi/files/ (we skip the
# redwoodPkg part of files/: annibale builds on the dodge-based package instead)
cp -f "$ROOT/hackios-xnu-kernel/uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader."{c,h} \
   "$MU/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/"
echo "apply-mu-patch: XnuLoader.c/h in place"
