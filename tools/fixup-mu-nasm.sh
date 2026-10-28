#!/bin/bash
# Replace the mu_nasm NuGet external dep with the host's own nasm.
# NuGet on Linux needs Mono (~400MB); the NuGet package is just a nasm binary
# (same NASM 2.16 line Ubuntu ships), so point the ext_dep at a local copy.
# Run INSIDE the build container, from anywhere; idempotent.
set -e
MU="${1:-$(dirname "$(readlink -f "$0")")/../hackios-xnu-kernel/Mu-Silicium}"
BIN="$MU/Mu_Basecore/BaseTools/Bin"
[ -d "$BIN" ] || { echo "fixup-mu-nasm: no $BIN" >&2; exit 1; }
mkdir -p "$BIN/LinuxNasm"
cp -f "$(command -v nasm)" "$BIN/LinuxNasm/nasm"
# this pytool version has no "external" extdep type (only nuget/web/git/az-universal),
# and nuget wants Mono; drop the descriptor and rely on PATH (container ships nasm 2.16,
# the same version line the NuGet package wraps).
[ -f "$BIN/nasm_ext_dep.yaml.orig" ] || mv "$BIN/nasm_ext_dep.yaml" "$BIN/nasm_ext_dep.yaml.orig" 2>/dev/null || true
echo "fixup-mu-nasm: done ($(nasm -v))"
