#!/usr/bin/env python3
"""Replay the system image identity checks against manifests that already ran.

usage: tools/k90auto/test-system-guard.py   (from the top of the workspace)

Reads only the system/window fields of each manifest, so it neither packs nor writes anything. The
synthetic rows cover the cases no existing manifest has: the iOS 26 image with no window, and the iOS
16.5 image with no window (which must report the size bound, not the window one).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import system_guard as guard

EVIDENCE = Path("docs/progress/evidence/k90auto")
MANIFESTS = (
    ("kernel-12377-attr26-fixguard3", True, "iOS 16.5 image, 2,492,227,584 bytes, default path"),
    ("kernel-12377-attr26-roundc", False, "iOS 26 image, 4,925,816,832 bytes, window 0x300000000"),
    ("kernel-12377-attr26-roundf", False, "iOS 26 image, window 0x300000000"),
)
SYNTHETIC = (
    ("26 image without window", guard.IOS26_SYSTEM, 4925816832, "x", "", True),
    ("16.5 image without window", guard.DEFAULT_SYSTEM, 2492227584, None, "", True),
    ("26 image with window", guard.IOS26_SYSTEM, 4925816832, "x", "0x300000000", False),
    ("image below the band", guard.DEFAULT_SYSTEM, (4 << 30) - 1, None, "", True),
    ("image above the band", "hackios-xnu-kernel/userland/other.apfs", (5 << 30) + 1, None, "", True),
)
failed = 0
for name, expect_error, note in MANIFESTS:
    manifest = json.loads((EVIDENCE / name / "manifest.json").read_text())
    system = manifest["system"]
    window = manifest.get("window", "")
    # The manifest records the resolved path, not the raw SYSTEM value: a round whose path is the
    # default most likely left SYSTEM unset, any other path had to come from the variable.
    env = None if system["path"] == guard.DEFAULT_SYSTEM else system["path"]
    message = guard.identity_error(system["path"], system["bytes"], env, window)
    got = message is not None
    failed += got != expect_error
    print(f"{'ok ' if got == expect_error else 'BAD'} {name}: rejected={got} expected={expect_error} ({note})")
    if message:
        print(f"    {message}")
for label, path, size, env, window, expect_error in SYNTHETIC:
    message = guard.identity_error(path, size, env, window)
    got = message is not None
    failed += got != expect_error
    print(f"{'ok ' if got == expect_error else 'BAD'} synthetic {label}: rejected={got} expected={expect_error}")
    if message:
        print(f"    {message}")
total = len(MANIFESTS) + len(SYNTHETIC)
print(f"{total - failed} passed, {failed} failed")
sys.exit(1 if failed else 0)