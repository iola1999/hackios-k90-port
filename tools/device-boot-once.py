"""Single-send device flows with bounded observation: RAM boot, flash, recovery.

Usage:
  python3 tools/device-boot-once.py --image <img> --image-sha256 <64hex> \
      --expect-build-id <40hex> --expect-pre-product annibale --expect-current-slot a
  python3 tools/device-boot-once.py --flash-image <img> --flash-image-sha256 <64hex> \
      --flash-partition boot_a --set-active-slot a --enter-bootloader-via-adb

Dry-run is the default; --execute is required to send anything. Exit codes: 0 pass,
1 device/protocol/identity failure, 2 usage, 3 local preflight, 4 host deadline.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from device_boot_common import (  # noqa: F401  (re-exported for the flows below)
    DEFAULT_LOG_DIR,
    EXIT_DEADLINE,
    EXIT_DEVICE,
    EXIT_OK,
    EXIT_PREFLIGHT,
    EXIT_USAGE,
    FORTY_HEX,
    SIXTY_FOUR_HEX,
    SCOPE_IN,
    SCOPE_OUT,
    Adb,
    Deadline,
    DeadlineReached,
    Device,
    DeviceStop,
    HostTimeout,
    PreflightStop,
    Recorder,
    Stop,
    UsageStop,
    argv_boot,
    argv_devices,
    argv_getvar,
    argv_reboot,
    format_usb,
    parse_devices,
    parse_getvar,
    require_value,
    run_argv,
    sha256_file,
    shell_join,
    usb_ids,
    usb_snapshot,
    utc,
)

from device_flow_support import (  # noqa: F401
    describe_send,
    record_tool_version,
    loader_identity,
    observe,
    preflight_identity,
    record_send,
)

from device_ladder import (  # noqa: F401
    SCOPE_LADDER_IN,
    SCOPE_LADDER_OUT,
    ladder_execute,
    ladder_local_checks,
    load_ladder,
    plan_ladder,
)

def build_parser():
    parser = argparse.ArgumentParser(
        description="Single RAM boot from LK fastboot with a bounded identity check. Dry-run by default.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "exit codes: 0 pass, 1 device/protocol/identity failure, 2 usage, "
            "3 local preflight, 4 host deadline or per-call timeout"
        ),
    )
    parser.add_argument("--execute", action="store_true", help="send; without it the run is a dry-run")
    parser.add_argument(
        "--recover-reboot",
        action="store_true",
        help="separate recovery action: send one `fastboot reboot` and nothing else; "
             "mutually exclusive with the boot flow and never chained after it",
    )
    parser.add_argument("--serial", default=None, help="target serial as enumerated; defaults to ANDROID_SERIAL")
    parser.add_argument("--loader-serial", default="xnuloader", help="serial the loader is expected to enumerate as")
    parser.add_argument("--image", default=None, help="approved boot image to send once")
    parser.add_argument(
        "--ladder-expect-current-slot",
        default="a",
        help="the ladder aborts if current-slot reads anything else before a round is written",
    )
    parser.add_argument(
        "--ladder",
        default=None,
        help="JSON file listing candidates to try in order; each entry needs label, image, sha256",
    )
    parser.add_argument(
        "--flash-image",
        default=None,
        help="image to write into --flash-partition (flash flow instead of a RAM boot)",
    )
    parser.add_argument("--flash-image-sha256", default=None, help="expected sha256 of --flash-image")
    parser.add_argument("--flash-partition", default=None, help="partition to write, e.g. boot_a")
    parser.add_argument(
        "--set-active-slot",
        default="a",
        help="run `fastboot set_active <slot>` after a successful flash, before the reboot",
    )
    parser.add_argument(
        "--enter-bootloader-via-adb",
        action="store_true",
        help="start with `adb reboot bootloader` and wait for the bootloader to enumerate",
    )
    parser.add_argument(
        "--wait-android",
        action="store_true",
        help="after the observation window, wait for adb and read ro.boot.slot_suffix",
    )
    parser.add_argument("--adb", default=None, help="adb binary; defaults to the PATH lookup")
    parser.add_argument("--adb-cap", type=float, default=15.0, help="per-call cap for adb")
    parser.add_argument("--flash-cap", type=float, default=180.0, help="per-call cap for the single flash")
    parser.add_argument("--lk-wait-seconds", type=float, default=60.0, help="budget to wait for LK after adb reboot bootloader")
    parser.add_argument("--android-wait-seconds", type=float, default=120.0, help="budget to wait for Android after the flash reboot")
    parser.add_argument("--image-sha256", default=None, help="expected sha256 of the image (64 hex)")
    parser.add_argument("--expect-build-id", default=None, help="approved 40 hex loader build id")
    parser.add_argument(
        "--allow-empty-build-id",
        action="store_true",
        help="archived images answer an empty build-id: expect exactly the empty value "
             "instead of a 40 hex id (mutually exclusive with --expect-build-id)",
    )
    parser.add_argument(
        "--no-usb-watch",
        dest="watch_usb",
        action="store_false",
        help="do not record the host USB device list per poll (default: record it)",
    )
    parser.set_defaults(watch_usb=True)
    parser.add_argument("--expect-pre-product", default=None, help="expected bootloader product before the send")
    parser.add_argument("--expect-current-slot", default=None, help="expected current-slot value before the send")
    parser.add_argument("--expect-version", default=None, help="expected loader version after the boot")
    parser.add_argument("--fastboot", default=None, help="fastboot binary; defaults to the PATH lookup")
    parser.add_argument("--total-seconds", type=float, default=180.0, help="host deadline for the whole run")
    parser.add_argument("--enum-cap", type=float, default=2.0, help="per-call cap for enumeration")
    parser.add_argument("--var-cap", type=float, default=2.0, help="per-call cap for one getvar")
    parser.add_argument("--boot-cap", type=float, default=30.0, help="per-call cap for the single boot send")
    parser.add_argument("--reboot-cap", type=float, default=30.0, help="per-call cap for the recovery reboot")
    parser.add_argument(
        "--observe-seconds", type=float, default=90.0, help="budget for re-enumeration after the send"
    )
    parser.add_argument("--poll-interval", type=float, default=3.0, help="pause between enumeration polls")
    parser.add_argument(
        "--log-dir", default=str(DEFAULT_LOG_DIR), help="directory for the raw run log (execute mode only)"
    )
    return parser


def resolve_tool(args):
    if args.fastboot:
        tool = args.fastboot
    else:
        tool = shutil.which("fastboot")
    if not tool:
        return None
    if os.sep in tool:
        return tool if os.access(tool, os.X_OK) else None
    return tool


def local_checks(args, tool, recorder, hash_now):
    """Local-only checks. Returns a list of problems; never contacts the device."""
    problems = []
    if tool is None:
        problems.append(
            "fastboot is not resolvable; pass --fastboot with an absolute path or put it on PATH"
        )
        recorder.say("preflight fastboot: MISSING")
    else:
        recorder.say("preflight fastboot: " + tool)
    if args.image is None:
        problems.append("--image is required")
    else:
        path = Path(args.image)
        if not path.is_file():
            problems.append("image not found: " + str(path))
        else:
            size = path.stat().st_size
            recorder.say("preflight image: %s bytes=%d" % (path, size))
            if size <= 0:
                problems.append("image is empty: " + str(path))
            if hash_now:
                digest = sha256_file(path)
                recorder.say("preflight image sha256: " + digest)
                if digest != args.image_sha256:
                    problems.append(
                        "image hash mismatch: %s != approved %s" % (digest, args.image_sha256)
                    )
    recorder.say(
        "preflight expect-build-id: "
        + ("(empty value, archived image)" if args.allow_empty_build_id else str(args.expect_build_id))
    )
    recorder.say("preflight usb watch: " + ("on" if getattr(args, "watch_usb", True) else "off"))
    recorder.say("preflight target serial: " + args.serial)
    return problems


def plan_lines(args, tool):
    """The exact commands execute mode would send, built from the same argv helpers."""
    resolved = tool or "<fastboot>"
    return [
        "phase 0 (local): record " + shell_join([resolved, "--version"]) + " and the resolved path",
        "phase 1 (read-only): " + shell_join(argv_devices(resolved)),
        "phase 1 (read-only): " + shell_join(argv_getvar(resolved, args.serial, "product")),
        "phase 1 (read-only): " + shell_join(argv_getvar(resolved, args.serial, "current-slot")),
        "phase 1 (local): sha256 of " + args.image + " compared with the approved value",
        "phase 2 (one send): " + shell_join(argv_boot(resolved, args.serial, args.image)),
        "phase 3 (poll): " + shell_join(argv_devices(resolved))
        + " every %.1fs for at most %.0fs, stop at the first poll that lists %s"
        % (args.poll_interval, args.observe_seconds, args.loader_serial),
        "phase 3 (each once, only after %s is enumerated): %s"
        % (args.loader_serial, ", ".join(shell_join(argv_getvar(resolved, args.loader_serial, var))
                                         for var in ("product", "version", "build-id", "result"))),
        "each poll also records the host USB device list (ioreg); %s"
        % ("on" if getattr(args, "watch_usb", True) else "off"),
        "expected build-id: "
        + ("empty value (archived image)" if args.allow_empty_build_id else args.expect_build_id),
        "host deadline for the whole run: %.0fs (each call capped by min(per-call cap, remaining))"
        % args.total_seconds,
    ]


SCOPE_FLASH_IN = (
    "adb reboot bootloader when --enter-bootloader-via-adb is given",
    "enumeration, bootloader product and current slot (read-only)",
    "image hash re-check immediately before the write",
    "exactly one flash of one partition",
    "optional one set_active, reading current-slot back",
    "one reboot, then bounded re-enumeration with empty polls recorded",
    "optional adb read of ro.boot.slot_suffix after the reboot",
)

SCOPE_FLASH_OUT = (
    "a second flash, a retry, or a flash of any other partition",
    "erase, format, wipe, oem commands, stage",
    "kernel load and GPU work",
    "automatic rollback to another image",
)







def flash_local_checks(args, tool, recorder):
    problems = []
    if tool is None:
        recorder.say("preflight fastboot: MISSING")
        problems.append("fastboot is not resolvable; pass --fastboot with an absolute path")
    else:
        recorder.say("preflight fastboot: " + tool)
    if not args.flash_partition:
        problems.append("--flash-partition is required in the flash flow")
    if not SIXTY_FOUR_HEX.match(args.flash_image_sha256 or ""):
        problems.append("--flash-image-sha256 must be a full 64 lower-case hex value")
    path = Path(args.flash_image)
    if not path.is_file():
        problems.append("flash image not found: " + str(path))
        return problems
    recorder.say("preflight flash image: %s bytes=%d" % (path, path.stat().st_size))
    digest = sha256_file(path)
    recorder.say("preflight flash sha256: " + digest)
    if digest != args.flash_image_sha256:
        problems.append("flash image hash mismatch: %s != approved %s" % (digest, args.flash_image_sha256))
    if args.set_active_slot is not None and args.set_active_slot not in ("a", "b"):
        problems.append("--set-active-slot must be a or b")
    if args.allow_empty_build_id and args.expect_build_id:
        problems.append("--allow-empty-build-id and --expect-build-id are mutually exclusive; pick one")
    if not args.allow_empty_build_id and not FORTY_HEX.match(args.expect_build_id or ""):
        problems.append("--expect-build-id must be a full 40 lower-case hex commit id (or pass --allow-empty-build-id)")
    recorder.say("preflight expect-build-id: " + ("(empty value)" if args.allow_empty_build_id else str(args.expect_build_id)))
    recorder.say("preflight usb watch: " + ("on" if getattr(args, "watch_usb", True) else "off"))
    recorder.say("preflight target serial: " + args.serial)
    return problems


def plan_flash(args, tool):
    resolved = tool or "<fastboot>"
    lines = []
    if args.enter_bootloader_via_adb:
        lines.append("phase 0 (control): adb -s %s reboot bootloader, then poll up to %.0fs for the bootloader" % (args.serial, args.lk_wait_seconds))
    lines.append("phase 1 (read-only): %s" % shell_join(argv_devices(resolved)))
    lines.append("phase 1 (read-only): %s -s %s getvar product, getvar current-slot" % (resolved, args.serial))
    lines.append("phase 1 (local): sha256 of %s compared with the approved value" % args.flash_image)
    lines.append("phase 2 (one write): %s -s %s flash %s %s" % (resolved, args.serial, args.flash_partition, args.flash_image))
    if args.set_active_slot:
        lines.append("phase 2b (one write): %s -s %s set_active %s, then read current-slot back" % (resolved, args.serial, args.set_active_slot))
    lines.append("phase 3 (one reboot): %s -s %s reboot" % (resolved, args.serial))
    lines.append(
        "phase 4 (poll): %s devices every %.1fs for at most %.0fs, recording empty polls with offsets"
        % (resolved, args.poll_interval, args.observe_seconds)
    )
    lines.append("phase 4 (each once, only after xnuloader is enumerated): getvar product, version, build-id, result")
    if args.wait_android:
        lines.append("phase 4b: if no loader appears, wait up to %.0fs for adb and read ro.boot.slot_suffix" % args.android_wait_seconds)
    lines.append("expected build-id: " + ("empty value" if args.allow_empty_build_id else str(args.expect_build_id)))
    lines.append("host deadline for the whole flow: %.0fs (each call capped by min(per-call cap, remaining))" % args.total_seconds)
    return lines


def validate_plan(args):
    problems = []
    if args.allow_empty_build_id:
        if args.expect_build_id:
            problems.append(
                "--allow-empty-build-id and --expect-build-id are mutually exclusive; pick one"
            )
    elif not FORTY_HEX.match(args.expect_build_id or ""):
        problems.append("--expect-build-id must be a full 40 lower-case hex commit id")
    if not SIXTY_FOUR_HEX.match(args.image_sha256 or ""):
        problems.append("--image-sha256 must be a full 64 lower-case hex value")
    if args.serial == args.loader_serial:
        problems.append("--serial must be the bootloader serial, not the loader serial")
    return problems


def plan_recovery(args, tool):
    """The recovery action is one command and nothing after it."""
    resolved = tool or "<fastboot>"
    return [
        "phase 1 (read-only): " + shell_join(argv_devices(resolved)),
        "phase 2 (one send): " + shell_join(argv_reboot(resolved, args.serial)),
        "stop: no enumeration, query or second command follows the reboot",
        "host deadline for the action: %.0fs" % args.total_seconds,
    ]


def dry_run(args, tool, recorder):
    recorder.say("MODE dry-run: no command is executed and no device is contacted")
    recorder.say("Execute mode needs --execute plus the recorded user authorization and the Lead review")
    if args.recover_reboot:
        recorder.say("action: recovery reboot only (separate from the boot flow; never chained after it)")
    if args.ladder:
        recorder.say("action: ladder flow (one write and one reboot per round, stop at the first loader)")
    if args.flash_image:
        recorder.say("action: flash flow (one partition write, one reboot, bounded observation)")
    recorder.say("")
    if args.recover_reboot:
        problems = []
        if not SIXTY_FOUR_HEX.match(args.image_sha256 or "") and args.image_sha256 is not None:
            problems.append("--image-sha256 is malformed")
    elif args.flash_image:
        problems = flash_local_checks(args, tool, recorder)
    elif args.ladder:
        try:
            ladder_entries = load_ladder(args.ladder)
        except (OSError, ValueError, UsageStop) as error:
            ladder_entries = []
            problems = ["cannot read the ladder file: %s" % error]
        else:
            problems = ladder_local_checks(args, ladder_entries, tool, recorder)
    else:
        problems = local_checks(args, tool, recorder, hash_now=True)
        problems.extend(validate_plan(args))
    recorder.say("")
    recorder.say("plan:")
    if args.recover_reboot:
        lines = plan_recovery(args, tool)
    elif args.ladder:
        lines = plan_ladder(args, ladder_entries, tool)
    elif args.flash_image:
        lines = plan_flash(args, tool)
    else:
        lines = plan_lines(args, tool)
    for line in lines:
        recorder.say("    " + line)
    recorder.say("")
    if args.ladder:
        scope_in, scope_out = SCOPE_LADDER_IN, SCOPE_LADDER_OUT
    elif args.flash_image:
        scope_in, scope_out = SCOPE_FLASH_IN, SCOPE_FLASH_OUT
    else:
        scope_in, scope_out = SCOPE_IN, SCOPE_OUT
    for entry in scope_in:
        recorder.say("scope in:  " + entry)
    for entry in scope_out:
        recorder.say("scope out: " + entry)
    if problems:
        recorder.say("")
        for problem in problems:
            recorder.say("PREFLIGHT PROBLEM: " + problem)
        recorder.say("dry-run verdict: the plan would stop before any device command")
        return EXIT_PREFLIGHT
    recorder.say("")
    recorder.say("dry-run verdict: plan is well formed; nothing was sent")
    return EXIT_OK










def recover(args, tool, recorder):
    """One reboot, only because the operator asked for it in this invocation.

    Nothing follows it: no enumeration, no query, no second command. Whether the phone came
    back is read by the operator afterwards, per runbook §8.
    """
    recorder.say("MODE recovery: one reboot is sent; nothing follows it")
    recorder.say("scope: recovery only. no boot, no flash, no oem, no set_active, no stage, no retry")
    deadline = Deadline(args.total_seconds, "recovery")
    record_tool_version(tool, recorder, deadline)
    device = Device(tool, recorder, deadline, args.enum_cap, args.var_cap, args.boot_cap, args.reboot_cap)
    body = device.devices()
    serials = parse_devices(body)
    recorder.say("enumerated serials: " + (", ".join(serials) if serials else "(none)"))
    if args.serial not in serials:
        raise PreflightStop("target serial is not enumerated; nothing was sent")
    if serials != [args.serial]:
        recorder.say("note: other fastboot serials are present; the reboot stays bound to the target")
    device.reboot(args.serial)
    recorder.say("")
    recorder.say("VERDICT: the reboot command was accepted; the device state is not established here")
    recorder.say("    read `fastboot devices` / `getvar product` yourself afterwards, per runbook §8")
    recorder.say("    no further command was sent by this process")
    return EXIT_OK






def wait_for_bootloader(args, device, recorder, deadline):
    """After `adb reboot bootloader`: poll until the target serial answers in fastboot."""
    budget = deadline.nested(args.lk_wait_seconds, "lk wait")
    started = time.monotonic()
    polls = 0
    while budget.remaining() > 0:
        polls += 1
        serials = parse_devices(device.devices(deadline=budget))
        recorder.say(
            "lk poll%d t=+%.1fs fastboot=%s" % (polls, time.monotonic() - started, ", ".join(serials) if serials else "(none)")
        )
        if args.serial in serials:
            recorder.say("bootloader enumerated after %.1fs (%d polls)" % (time.monotonic() - started, polls))
            return polls
        pause = min(1.0, max(0.0, budget.remaining()))
        if pause > 0:
            time.sleep(pause)
    raise DeviceStop(
        "adb reboot bootloader was sent but the target did not enumerate in fastboot within %.0fs"
        % args.lk_wait_seconds
    )


def wait_for_android(args, adb, recorder, deadline):
    """Wait for adb to list the target, then read the slot suffix it actually booted."""
    budget = deadline.nested(args.android_wait_seconds, "android wait")
    started = time.monotonic()
    polls = 0
    while budget.remaining() > 0:
        polls += 1
        body = adb.devices(deadline=budget)
        listed = [line.split("\t")[0] for line in body.splitlines() if "\tdevice" in line]
        recorder.say("android poll%d fastboot-unrelated adb=%s" % (polls, ", ".join(listed) if listed else "(none)"))
        if args.serial in listed:
            slot = adb.shell(args.serial, "getprop ro.boot.slot_suffix", deadline=budget)
            recorder.say("android reachable after %.1fs; ro.boot.slot_suffix=%s" % (time.monotonic() - started, slot.strip() or "(empty)"))
            return slot.strip()
        pause = min(2.0, max(0.0, budget.remaining()))
        if pause > 0:
            time.sleep(pause)
    recorder.say("android did not come up within %.0fs" % args.android_wait_seconds)
    return None


def flash_execute(args, tool, recorder):
    """Write one partition once, then reboot once and observe what the bootloader picks up."""
    recorder.say("MODE flash: one partition write, one reboot, bounded observation")
    for entry in SCOPE_FLASH_IN:
        recorder.say("scope in:  " + entry)
    for entry in SCOPE_FLASH_OUT:
        recorder.say("scope out: " + entry)
    recorder.say("")
    problems = flash_local_checks(args, tool, recorder)
    if problems:
        raise PreflightStop("; ".join(problems))
    deadline = Deadline(args.total_seconds, "flash flow")
    record_tool_version(tool, recorder, deadline)
    device = Device(
        tool, recorder, deadline, args.enum_cap, args.var_cap, args.boot_cap,
        args.reboot_cap, args.flash_cap,
    )
    adb = None
    if args.enter_bootloader_via_adb or args.wait_android:
        adb_tool = args.adb or shutil.which("adb")
        if not adb_tool:
            raise PreflightStop("adb is not resolvable but --enter-bootloader-via-adb/--wait-android was given")
        adb = Adb(adb_tool, recorder, deadline, args.adb_cap)
        recorder.say("adb: " + adb_tool)

    if args.enter_bootloader_via_adb:
        recorder.say("")
        recorder.say("== phase 0: enter the bootloader through adb ==")
        adb.reboot_bootloader(args.serial)
        wait_for_bootloader(args, device, recorder, deadline)

    recorder.say("")
    recorder.say("== phase 1: read-only checks on the bootloader ==")
    product, slot = preflight_identity(args, device, recorder)

    recorder.say("")
    recorder.say("== phase 2: hash gate and the single flash ==")
    digest = sha256_file(Path(args.flash_image))
    recorder.say("image sha256 at flash time: " + digest)
    if digest != args.flash_image_sha256:
        raise PreflightStop(
            "image hash changed since packaging: %s != approved %s; nothing was written"
            % (digest, args.flash_image_sha256)
        )
    flash_status = record_send(
        recorder,
        "flash " + args.flash_partition,
        lambda: device.flash(args.serial, args.flash_partition, args.flash_image),
    )
    if not flash_status["ok"]:
        raise DeviceStop(
            "the flash did not report OKAY, so no reboot and no set_active was sent; "
            "the partition state is unknown and the run stops here (%s)" % flash_status["body"]
        )

    if args.set_active_slot:
        recorder.say("")
        recorder.say("== phase 2b: set_active ==")
        device.set_active(args.serial, args.set_active_slot)
        after = require_value(
            device.getvar(args.serial, "current-slot"), "current-slot", "current slot after set_active"
        )
        recorder.say("current-slot after set_active: " + (after if after else "(empty)"))
        if after != args.set_active_slot:
            raise DeviceStop(
                "set_active %s was accepted but current-slot reads %r" % (args.set_active_slot, after)
            )

    recorder.say("")
    recorder.say("== phase 3: the single reboot ==")
    reboot_status = record_send(recorder, "reboot", lambda: device.reboot(args.serial))
    reboot_time = time.monotonic()

    recorder.say("")
    recorder.say("== phase 4: bounded observation ==")
    result = observe(args, device, recorder, deadline, reboot_time)

    identity = None
    android_slot = None
    if result["serials"]:
        recorder.say("")
        recorder.say("== phase 4b: loader identity, one query per variable ==")
        identity = loader_identity(args, device, recorder)
    elif args.wait_android and adb is not None:
        recorder.say("")
        recorder.say("== phase 4b: wait for Android ==")
        android_slot = wait_for_android(args, adb, recorder, deadline)

    recorder.say("")
    recorder.say("VERDICT: PASS")
    recorder.say("    bootloader before flash: product=%s current-slot=%s" % (product, slot or "(empty)"))
    recorder.say("    flash %s: %s" % (args.flash_partition, describe_send(flash_status)))
    recorder.say("    reboot: %s" % describe_send(reboot_status))
    recorder.say(
        "    observation: polls=%d empty_polls=%d gaps=%d"
        % (result["polls"], result["empty_polls"], len(result["gaps"]))
    )
    if identity is not None:
        recorder.say(
            "    loader identity: product=%s version=%s build-id=%s result=%s"
            % (identity["product"], identity["version"], identity["build_id"], identity["result"])
        )
    if android_slot is not None:
        recorder.say("    android booted with ro.boot.slot_suffix=%s" % (android_slot or "(empty)"))
    recorder.say("    stopped here: no second flash, no retry, no oem command")
    return EXIT_OK










def execute(args, tool, recorder):
    # Structural guard: the boot flow and the recovery action never share a process, so no
    # reboot can follow a boot automatically (docs/analysis/local/device-boot-once-runbook.md §8).
    if args.recover_reboot:
        raise UsageStop("--recover-reboot runs the recovery action only; it is not part of the boot flow")
    if args.flash_image:
        raise UsageStop("--flash-image runs the flash flow; it is not part of the RAM boot flow")
    if args.ladder:
        raise UsageStop("--ladder runs the ladder flow; it is not part of the RAM boot flow")
    recorder.say("MODE execute: one boot is sent; any failure stops the run with no retry")
    if args.ladder:
        scope_in, scope_out = SCOPE_LADDER_IN, SCOPE_LADDER_OUT
    elif args.flash_image:
        scope_in, scope_out = SCOPE_FLASH_IN, SCOPE_FLASH_OUT
    else:
        scope_in, scope_out = SCOPE_IN, SCOPE_OUT
    for entry in scope_in:
        recorder.say("scope in:  " + entry)
    for entry in scope_out:
        recorder.say("scope out: " + entry)
    recorder.say("")
    # The hash is checked twice: here before any device call, and again immediately before the
    # send, so a candidate that changes while the pre-boot reads run is still refused.
    problems = local_checks(args, tool, recorder, hash_now=True)
    problems.extend(validate_plan(args))
    if problems:
        raise PreflightStop("; ".join(problems))
    deadline = Deadline(args.total_seconds, "whole run")
    record_tool_version(tool, recorder, deadline)
    device = Device(tool, recorder, deadline, args.enum_cap, args.var_cap, args.boot_cap)

    recorder.say("")
    recorder.say("== phase 1: read-only pre-boot checks ==")
    product, slot = preflight_identity(args, device, recorder)

    recorder.say("")
    recorder.say("== phase 2: hash gate and the single send ==")
    digest = sha256_file(Path(args.image))
    recorder.say("image sha256 at send time: " + digest)
    if digest != args.image_sha256:
        raise PreflightStop(
            "image hash changed since packaging: %s != approved %s; nothing was sent"
            % (digest, args.image_sha256)
        )
    boot_status = record_send(recorder, "boot", lambda: device.boot(args.serial, args.image))
    send_time = time.monotonic()
    if boot_status["ok"]:
        if "OKAY" not in boot_status["body"]:
            recorder.say("note: the reply contains no OKAY; the send is not confirmed as accepted")
        if "Booting" not in boot_status["body"]:
            recorder.say("note: the reply has no 'Booting' line; this fastboot version words its answer differently")
    else:
        recorder.say("    a FAILED 'Booting' body, usb_read failure included, is the device leaving fastboot")
        recorder.say("    the observation below is what decides the outcome")

    recorder.say("")
    recorder.say("== phase 3: bounded re-enumeration ==")
    try:
        result = observe(args, device, recorder, deadline, send_time)
    except DeviceStop as stop:
        if boot_status.get("timeout"):
            raise HostTimeout("%s (the boot send itself timed out, so the device side is unknown)" % stop)
        raise
    serials = result["serials"]

    recorder.say("")
    recorder.say("== phase 3: loader identity, one query per variable ==")
    identity = loader_identity(args, device, recorder)

    recorder.say("")
    recorder.say("VERDICT: PASS")
    recorder.say("    bootloader before send: product=%s current-slot=%s" % (product, slot or "(empty)"))
    recorder.say("    boot send: " + describe_send(boot_status))
    recorder.say("    observation: polls=%d empty_polls=%d gaps=%d" % (result["polls"], result["empty_polls"], len(result["gaps"])))
    recorder.say("    enumerated after send: " + ", ".join(serials))
    recorder.say(
        "    loader identity: product=%s version=%s build-id=%s result=%s"
        % (identity["product"], identity["version"], identity["build_id"], identity["result"])
    )
    recorder.say("    stopped here: no kernel, GPU, slot switch, flash, reboot or recovery command was sent")
    return EXIT_OK


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    serial = (args.serial or os.environ.get("ANDROID_SERIAL") or "").strip()
    if not serial:
        print(
            "device-boot-once: no target serial. Pass --serial or set ANDROID_SERIAL from the "
            "enumeration you confirmed; this script never picks a device on its own.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    args.serial = serial

    tool = resolve_tool(args)
    log_path = None
    if args.execute:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = Path(args.log_dir) / ("boot-once-" + stamp + ".log")
    try:
        recorder = Recorder(log_path)
    except OSError as error:
        print(
            "device-boot-once: cannot open the run log %s: %s; nothing was sent"
            % (log_path, error),
            file=sys.stderr,
        )
        return EXIT_PREFLIGHT
    try:
        if not args.execute:
            return dry_run(args, tool, recorder)
        if tool is None:
            raise PreflightStop("fastboot is not resolvable; pass --fastboot with an absolute path")
        recorder.say("log: " + str(log_path))
        if args.recover_reboot:
            return recover(args, tool, recorder)
        if args.ladder:
            return ladder_execute(args, tool, recorder)
        if args.flash_image:
            return flash_execute(args, tool, recorder)
        return execute(args, tool, recorder)
    except Stop as stop:
        recorder.say("")
        recorder.say("STOP: " + str(stop))
        if stop.note:
            recorder.say("note: " + stop.note)
        recorder.say("VERDICT: FAILED (exit %d)" % stop.exit_code)
        recorder.say("    nothing was retried; no recovery command was sent")
        recorder.say("    recovery is manual per the runbook and needs separate authorization")
        return stop.exit_code
    finally:
        recorder.close()


if __name__ == "__main__":
    sys.exit(main())