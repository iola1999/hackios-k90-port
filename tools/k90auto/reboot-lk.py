#!/usr/bin/env python3
"""Prepare the K90 LK target through a verified payload; stop at LK by default.

Usage: reboot-lk.py OUTPUT --payload FILE --sha256 HASH [--serial LK_SERIAL] [--return-loader]
LK_SERIAL defaults to ANDROID_SERIAL. OUTPUT must be a new directory.
Requires an idle/returned loader, empty resident RAM disk and exclusive device access.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

PLAYBOOK = "docs/plan/device-test-playbook.md"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def field(output, key):
    values = re.findall(r"^(?:\(bootloader\)[ \t]*)?" + re.escape(key) + r":[ \t]*(.*?)[ \t]*$", output, re.M)
    require(len(values) == 1 and values[0], f"Missing or ambiguous {key} response")
    return values[0]


def prepared(log):
    require(log.startswith("== XNULOADER run (usb) ==\n") and log.rstrip().endswith("== END OF LOG =="),
            "Incomplete run log; prepared status cannot be verified")
    require("reboot-lk: preparation failed:" not in log and "reboot-lk: loader_return returned" not in log,
            "Preparation failed; leaving the device state for inspection")
    lines = re.findall(r"reboot-lk: prepared[^\r\n]*", log)
    parsed = [re.fullmatch(r"reboot-lk: prepared apid=(\d+) owner=0 byte=(0x[45]) reason=2; "
                          r"returning to loader for host reboot", line) for line in lines]
    require(parsed and all(parsed), "Invalid prepared marker; reboot not sent")
    markers = {match.groups() for match in parsed}
    require(len(markers) == 1, "Missing or conflicting prepared marker; reboot not sent")
    apid, byte = next(iter(markers))
    targets = set(re.findall(r"reboot-lk: apid=(\d+) owner=0 capacity=(\d+) "
                             r"original=(0x[0-9a-f]+|0) target=(0x[0-9a-f]+|0)", log))
    require(len(targets) == 1, "Missing or conflicting target readback context")
    target_apid, capacity, original, target = next(iter(targets))
    require(apid == target_apid and int(capacity) >= 9 and
            int(byte, 16) == int(target, 0) == ((int(original, 0) & 1) | 4),
            "Prepared marker disagrees with target byte or APID")
    return {"apid": int(apid), "owner": 0, "byte": int(byte, 16), "reason": 2}


def workflow(args, base, result):
    payload = args.payload.resolve(strict=True)
    digest = hashlib.sha256()
    with payload.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    result["payload"] = {"path": str(payload), "bytes": payload.stat().st_size, "sha256": digest.hexdigest()}
    require(digest.hexdigest() == args.sha256.lower(), "Payload SHA256 mismatch; no device command sent")
    require(0 < payload.stat().st_size <= 0x03700000, "Payload exceeds the loader download buffer")

    def call(argv, limit=8, check=True):
        started = time.monotonic()
        record = {"argv": argv, "started_unix": time.time(), "started_monotonic": started, "limit_seconds": limit}
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=limit)
            record.update(rc=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        except subprocess.TimeoutExpired as error:
            def text(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
            record.update(rc=124, error="timeout", stdout=text(error.stdout), stderr=text(error.stderr))
        except OSError as error:
            record.update(rc=127, error=str(error), stdout="", stderr="")
        record["seconds"] = time.monotonic() - started
        output = record["stdout"] + record["stderr"]
        record["ok"] = record["rc"] == 0 and "FAILED" not in output
        with (base / "commands.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        if check:
            require(record["ok"], f"Command failed: {' '.join(argv)}; see commands.jsonl")
        return record

    def getvar(serial, key):
        record = call(["fastboot", "-s", serial, "getvar", key])
        return field(record["stdout"] + record["stderr"], key)

    def devices(check=True):
        record = call(["fastboot", "devices"], check=check)
        return [parts[0] for line in record["stdout"].splitlines()
                if len(parts := line.split()) == 2 and parts[1] == "fastboot"] if record["ok"] else None

    def loader_ready(only_returned=False):
        state = getvar("xnuloader", "result")
        allowed = re.fullmatch(r"returned [0-9a-f]+ [0-9a-f]+", state) or (not only_returned and state == "idle")
        require(allowed, f"Loader state {state!r} is not reusable. Preserve logs and follow {PLAYBOOK} for cold-reset recovery.")
        ramdisk = getvar("xnuloader", "ramdisk-state")
        require(re.fullmatch(r"idle 0 0 [0-9a-f]+", ramdisk),
                f"Resident RAM state {ramdisk!r} must be preserved. Follow {PLAYBOOK} for cold-reset recovery.")
        return state

    def return_to_loader():
        require(getvar(args.serial, "product") == "annibale", "LK product changed before slot selection")
        slot = getvar(args.serial, "current-slot")
        require(slot in ("a", "b"), "Invalid LK current-slot response")
        before = {key: getvar(args.serial, key) for key in
                  ("slot-successful:b", "slot-unbootable:b", "slot-retry-count:a", "slot-unbootable:a")}
        result["slots_before_return"] = {"current-slot": slot, **before}
        require(before["slot-successful:b"] == "yes" and before["slot-unbootable:b"] == "no",
                "Slot B is not confirmed successful and bootable; leaving the device at LK")
        call(["fastboot", "-s", args.serial, "set_active", "a"])
        after = {key: getvar(args.serial, key) for key in
                 ("current-slot", "slot-retry-count:a", "slot-unbootable:a")}
        result["slots_after_selection"] = after
        require(after == {"current-slot": "a", "slot-retry-count:a": "7", "slot-unbootable:a": "no"},
                "Slot A activation did not restore the verified K90 retry state; reboot not sent")
        result["return_reboot_sent"] = True
        reboot = call(["fastboot", "-s", args.serial, "reboot"], check=False)
        result["return_reboot_command_ok"] = reboot["ok"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            found = devices(check=False)
            if found is not None and "xnuloader" in found:
                require(found.count("xnuloader") == 1 and args.serial not in found,
                        "Ambiguous loader/LK enumeration after return reboot")
                require(getvar("xnuloader", "product") == "xnuloader", "Unexpected returned loader product")
                build_id = getvar("xnuloader", "build-id")
                require(build_id == result["loader_build_id"], "Returned loader build-id changed")
                require(getvar("xnuloader", "ramdisk-protocol") == "1", "Returned loader RAM protocol changed")
                require(loader_ready() == "idle", "Returned loader is not fresh idle")
                require(getvar("xnuloader", "max-download-size") == "0x03700000",
                        "Returned loader download target is not its payload buffer")
                result.update(loader_returned=True, returned_loader_build_id=build_id)
                return
            time.sleep(1)
        raise RuntimeError("Fresh loader was not identified within 60 seconds; inspect the recorded USB results")

    found = devices()
    require(found.count("xnuloader") == 1 and args.serial not in found,
            "Expected one xnuloader and no existing device with the requested LK serial")
    require(getvar("xnuloader", "product") == "xnuloader", "Unexpected loader product")
    result["loader_build_id"] = getvar("xnuloader", "build-id")
    require(getvar("xnuloader", "ramdisk-protocol") == "1", "Loader cannot report resident RAM state")
    result["initial_state"] = loader_ready()
    # Legacy oem ramdisk can arm the next download while resident length is still zero.
    require(getvar("xnuloader", "max-download-size") == "0x03700000",
            f"Loader download target is not its payload buffer. Preserve state and follow {PLAYBOOK}.")
    call(["fastboot", "-s", "xnuloader", "stage", str(payload)], limit=60)
    call(["fastboot", "-s", "xnuloader", "oem", "run"])
    deadline = time.monotonic() + 40
    while True:
        state = getvar("xnuloader", "result")
        if not re.fullmatch(r"running [0-9a-f]+ [0-9a-f]+", state):
            require(re.fullmatch(r"returned [0-9a-f]+ [0-9a-f]+", state),
                    f"Probe did not return normally: {state}; reboot not sent")
            break
        require(time.monotonic() < deadline, "Probe return timed out; reboot not sent")
        time.sleep(1)
    logfile = base / "prepared.log"
    call(["fastboot", "-s", "xnuloader", "get_staged", str(logfile)], limit=20)
    result["prepared"] = prepared(logfile.read_text(errors="replace"))
    result["prepared_log_sha256"] = hashlib.sha256(logfile.read_bytes()).hexdigest()
    loader_ready(only_returned=True)
    # A lost USB reply can accompany a successful reset; identify the destination before judging it.
    result["reboot_sent"] = True
    reboot = call(["fastboot", "-s", "xnuloader", "reboot"], check=False)
    result["reboot_command_ok"] = reboot["ok"]
    deadline = time.monotonic() + 60
    off_seen = False
    while time.monotonic() < deadline:
        found = devices(check=False)
        if found is not None:
            off_seen |= "xnuloader" not in found
            if args.serial in found and "xnuloader" not in found:
                require(getvar(args.serial, "product") == "annibale", "Destination product is not annibale")
                slot = getvar(args.serial, "current-slot")
                require(slot in ("a", "b"), "Invalid LK current-slot response")
                result.update(lk_entered=True, current_slot=slot, loader_disconnected=off_seen)
                if args.return_loader:
                    return_to_loader()
                return
            require(not (off_seen and "xnuloader" in found), "Reset returned to xnuloader; LK was not reached")
        time.sleep(1)
    raise RuntimeError("LK was not identified within 60 seconds; inspect the recorded USB results")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory for commands.jsonl, prepared.log and result.json")
    parser.add_argument("--payload", type=Path, required=True, help="verified prepare-only XNUP payload")
    parser.add_argument("--sha256", required=True, help="expected full SHA256 of the payload")
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL"), help="LK serial; defaults to ANDROID_SERIAL")
    parser.add_argument("--return-loader", action="store_true",
                        help="after LK verification, require bootable successful B, reset A retries and verify fresh loader")
    args = parser.parse_args()
    if not args.serial or args.serial == "xnuloader" or any(c.isspace() for c in args.serial):
        parser.error("--serial or ANDROID_SERIAL must identify the device in LK")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        parser.error("--sha256 requires a full SHA256 digest")
    base = args.output.resolve()
    base.mkdir(parents=True)
    result = {"lk_entered": False, "reboot_sent": False, "serial": args.serial,
              "return_loader_requested": args.return_loader, "loader_returned": False, "return_reboot_sent": False}
    started = time.monotonic()
    try:
        workflow(args, base, result)
    except (RuntimeError, OSError) as error:
        result["error"] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        result["seconds"] = time.monotonic() - started
        (base / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if args.return_loader and result["loader_returned"]:
        print(f"Slot A retries restored; fresh loader idle with empty RAM verified. Records: {base}")
        return 0
    if not args.return_loader and result["lk_entered"]:
        print(f"LK FASTBOOT verified on slot {result['current_slot']}; stopped at LK. Records: {base}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
