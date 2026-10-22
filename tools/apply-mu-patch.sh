#!/bin/bash
# Apply hackios's Mu-Silicium patch (BootShim XNUP copy + BootManager autostart)
# to a Mu-Silicium checkout. Idempotent: skips if already applied.
# usage: apply-mu-patch.sh [MU_DIR]
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MU="${1:-$ROOT/hackios-xnu-kernel/Mu-Silicium}"
PATCH="$ROOT/hackios-xnu-kernel/uefi/mu-silicium.patch"
cd "$MU"
if git apply -R --check "$PATCH" 2>/dev/null; then
  echo "apply-mu-patch: already applied"
else
  git apply --whitespace=nowarn "$PATCH"
  echo "apply-mu-patch: applied"
fi
