#!/usr/bin/env python3
"""The iOS system image kept on the phone's own storage as an Android DSU image.

Android's DSU installer ("Dynamic System Updates") writes the image into a file on userdata that
libfiemap maps beneath the metadata encryption, so the bytes on the storage are the image itself.
The loader finds that file's extents through the DSU's lp_metadata on the metadata partition and
reads it into the resident window ("oem dsu load"), which replaces the USB upload of
stage-system.sh. The DSU is installed and never enabled: Android keeps booting as before, and
Settings > Developer options > DSU, or the installer's notification, discards it.

usage: tools/k90auto/dsu.py status                     (phone in Android)
       tools/k90auto/dsu.py install [--image PATH] [--replace]   (phone in Android)
       tools/k90auto/dsu.py wait                       (phone in Android)
       tools/k90auto/dsu.py record [--image PATH]

install pads the image with zeros to the slot (--slot-gib, default 16, so that a grown image still
fits), gzips it, pushes it, starts the installer and waits for it. The installer's own log says when
it is done (DynamicSystemInstallationService, a cause of INSTALL_COMPLETED), and wait does only
that part. record writes what the phone holds -- one SHA-1 per MiB over the whole slot, the image's
SHA-256 and size -- into docs/progress/evidence/k90auto/dsu/ (git-ignored), for the loader's check
after "oem dsu load" and for patching changed pieces later. The device is the one ANDROID_SERIAL
names.
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
STATE = WORKSPACE / "docs/progress/evidence/k90auto/dsu"
DEFAULT_IMAGE = "hackios-xnu-kernel/userland/system26.apfs"
PIECE = 1 << 20
REMOTE = "/sdcard/Download/dsu-system.gz"


def adb(*args, timeout=60, check=True):
    serial = os.environ.get("ANDROID_SERIAL")
    if not serial:
        sys.exit("dsu: ANDROID_SERIAL is not set")
    result = subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        sys.exit(f"dsu: adb {' '.join(args[:2])} failed: {result.stderr.strip()[-300:]}")
    return result.stdout.replace("\r", "")


def status():
    return adb("shell", "gsi_tool", "status", check=False).strip()


def installer_state():
    """The installer's last status line: (status, cause), or None before it has written one."""
    out = adb("shell", "logcat -d -s DynamicSystemInstallationService:* | grep 'status:' | tail -1", check=False)
    line = out.strip()
    if "status:" not in line:
        return None
    status = line.split("status:", 1)[1].split(",", 1)[0].strip()
    cause = line.split("cause:", 1)[1].split(",", 1)[0].strip() if "cause:" in line else ""
    progress = line.split("total_progress:", 1)[1].strip() if "total_progress:" in line else ""
    return status, cause, progress


def sums_of(image, slot):
    """One SHA-1 per MiB over the slot (zeros past the image), and the image's SHA-256."""
    sums, zero, sha = [], hashlib.sha1(bytes(PIECE)).hexdigest(), hashlib.sha256()
    with open(image, "rb") as src:
        for _ in range(slot // PIECE):
            piece = src.read(PIECE)
            sha.update(piece)
            sums.append(hashlib.sha1(piece.ljust(PIECE, b"\0")).hexdigest() if piece else zero)
    return sums, sha.hexdigest()


def write_gz(image, slot, path):
    """The image followed by zeros up to the slot, gzipped at level 1."""
    with open(image, "rb") as src, gzip.open(path, "wb", compresslevel=1) as dst:
        for _ in range(slot // PIECE):
            dst.write(src.read(PIECE).ljust(PIECE, b"\0"))


def wait(seconds):
    seen = None
    for _ in range(int(seconds / 5)):
        state = installer_state()
        if state != seen:
            print(f"dsu: installer {state}", flush=True)
            seen = state
        if state and "INSTALL_COMPLETED" in state[1]:
            adb("shell", "rm", "-f", REMOTE, check=False)
            return
        if state and ("ERROR" in state[1] or "FAILED" in state[0]):
            sys.exit(f"dsu: the installer stopped: {state}")
        time.sleep(5)
    sys.exit(f"dsu: not done after {seconds} s: {installer_state()}")


def record(args):
    image = WORKSPACE / args.image
    slot = args.slot_gib << 30
    sums, sha = sums_of(image, slot)
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "system.sums").write_text("\n".join(sums) + "\n")
    entry = {"image": args.image, "bytes": image.stat().st_size, "sha256": sha, "slot_bytes": slot,
             "userdata_bytes": args.userdata_gib << 30, "piece_bytes": PIECE, "recorded": time.strftime("%F %T")}
    (STATE / "system.json").write_text(json.dumps(entry, indent=1) + "\n")
    print(f"dsu: recorded in {STATE.relative_to(WORKSPACE)}")


def install(args):
    image = WORKSPACE / args.image
    size, slot = image.stat().st_size, args.slot_gib << 30
    if size > slot:
        sys.exit(f"dsu: {image} ({size} bytes) does not fit a {args.slot_gib} GiB slot")
    if "device" not in adb("get-state", check=False):
        sys.exit("dsu: the phone is not in Android")
    before = status()
    print(f"dsu: gsi_tool status before: {before}")
    if "installed" in before and not args.replace:
        sys.exit("dsu: a DSU image is already there; --replace wipes it first")
    if "installed" in before:
        # only an image that is not in use: the phone must be running its own Android
        if "disabled" not in before.split() or adb("shell", "getprop", "ro.gsid.image_running").strip() != "0":
            sys.exit(f"dsu: the installed image is enabled or running; not wiping it ({before})")
        adb("shell", "gsi_tool", "wipe")
        print(f"dsu: wiped the old image; gsi_tool status now: {status()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="dsu-") as tmp:
        gz = Path(tmp) / "dsu-system.gz"
        print(f"dsu: {image.name}, {size} bytes, padded to {slot} and gzipped", flush=True)
        write_gz(image, slot, gz)
        print(f"dsu: pushing {gz.stat().st_size} bytes", flush=True)
        adb("push", str(gz), REMOTE, timeout=1800)
    adb("shell", "logcat", "-c", check=False)
    adb("shell", "setprop", "persist.sys.fflag.override.settings_dynamic_system", "true")
    adb("shell", "am", "start-activity", "-W", "-n",
        "com.android.dynsystem/com.android.dynsystem.VerificationActivity",
        "-a", "android.os.image.action.START_INSTALL", "-d", "file://" + REMOTE.replace("/sdcard", "/storage/emulated/0"),
        "--el", "KEY_SYSTEM_SIZE", str(slot), "--el", "KEY_USERDATA_SIZE", str(args.userdata_gib << 30))
    print("dsu: the installer is running; the phone may ask for confirmation", flush=True)
    wait(args.wait)
    record(args)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    w = sub.add_parser("wait")
    w.add_argument("--wait", type=int, default=1800, help="seconds to wait for the installer")
    for name in ("install", "record"):
        p = sub.add_parser(name)
        p.add_argument("--image", default=DEFAULT_IMAGE, help="workspace-relative system image")
        p.add_argument("--slot-gib", type=int, default=16)
        p.add_argument("--userdata-gib", type=int, default=2)
        p.add_argument("--wait", type=int, default=1800, help="seconds to wait for the installer")
        p.add_argument("--replace", action="store_true", help="wipe a DSU image that is already installed")
    args = ap.parse_args()
    if args.command == "status":
        print(status())
    elif args.command == "wait":
        wait(args.wait)
    elif args.command == "record":
        record(args)
    else:
        install(args)


if __name__ == "__main__":
    main()
