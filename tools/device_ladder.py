"""Candidate ladder: one write and one reboot per round, stopping at the first loader.

Each round re-reads the slot, re-checks the image hash and re-confirms the bootloader before
writing, so a round that leaves the device in an unexpected state stops the whole ladder.
"""

import json
import time
from pathlib import Path

from device_boot_common import (
    EXIT_DEVICE,
    EXIT_OK,
    SIXTY_FOUR_HEX,
    Deadline,
    Device,
    DeviceStop,
    PreflightStop,
    UsageStop,
    require_value,
    sha256_file,
)
from device_flow_support import (
    record_tool_version,
    describe_send,
    loader_identity,
    observe,
    preflight_identity,
    record_send,
)

SCOPE_LADDER_IN = (
    "per round: enumeration, product and current slot (read-only)",
    "per round: image hash re-check immediately before the write",
    "per round: exactly one flash boot_a, one set_active, one reboot",
    "per round: bounded enumeration with empty polls recorded",
)


SCOPE_LADDER_OUT = (
    "a retry inside a round",
    "flashing any partition other than boot_a",
    "erase, format, wipe, oem commands, stage",
    "kernel load and GPU work",
    "continuing the ladder after an unresponsive device",
)


def write_ladder_summary(args, recorder, rounds, verdict):
    """Keep the round table next to the raw log so the next session does not re-derive it."""
    if not getattr(recorder, "log_path", None):
        return
    path = recorder.log_path.with_suffix(".rounds.json")
    path.write_text(json.dumps({"verdict": verdict, "rounds": rounds}, indent=2) + "\n")
    recorder.say("round table: " + str(path))


def load_ladder(path):
    """Read the candidate ladder. Every entry carries its own approved hash."""
    data = json.loads(Path(path).read_text())
    entries = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries:
        raise UsageStop("the ladder file has no candidates")
    return entries


def ladder_local_checks(args, entries, tool, recorder):
    problems = []
    if tool is None:
        recorder.say("preflight fastboot: MISSING")
        problems.append("fastboot is not resolvable; pass --fastboot with an absolute path")
    else:
        recorder.say("preflight fastboot: " + tool)
    if args.flash_partition not in (None, "boot_a"):
        problems.append("the ladder writes boot_a only; --flash-partition must be boot_a")
    for index, entry in enumerate(entries, 1):
        label = entry.get("label") or ("round%d" % index)
        image = entry.get("image")
        digest = (entry.get("sha256") or "").lower()
        if not image:
            problems.append("%s: no image path" % label)
            continue
        if not SIXTY_FOUR_HEX.match(digest):
            problems.append("%s: sha256 is not a 64 hex value" % label)
        path = Path(image)
        if not path.is_file():
            problems.append("%s: image not found: %s" % (label, image))
            continue
        actual = sha256_file(path)
        recorder.say(
            "preflight %s: %s bytes=%d sha256=%s match=%s"
            % (label, image, path.stat().st_size, actual, actual == digest)
        )
        if actual != digest:
            problems.append("%s: image hash mismatch: %s != %s" % (label, actual, digest))
    recorder.say("preflight rounds: %d" % len(entries))
    recorder.say("preflight target serial: " + args.serial)
    return problems


def plan_ladder(args, entries, tool):
    resolved = tool or "<fastboot>"
    lines = ["ladder file: " + args.ladder + " (%d rounds)" % len(entries)]
    for index, entry in enumerate(entries, 1):
        label = entry.get("label") or ("round%d" % index)
        lines.append(
            "round %d %s [recipe %s]: %s -s %s flash boot_a %s"
            % (index, label, entry.get("recipe") or "(not labelled)", resolved, args.serial, entry.get("image"))
        )
    lines.append("per round, in this order:")
    lines.append("    1 read-only: devices, getvar product (must be %s), getvar current-slot recorded" % (args.expect_pre_product or "annibale"))
    lines.append("    1b slot gate: current-slot must read %s, otherwise the whole ladder aborts" % args.ladder_expect_current_slot)
    lines.append("    2 local: sha256 of the round image compared with the ladder entry")
    lines.append("    3 one write: flash boot_a")
    lines.append("    4 one write: --set-active=a, then read current-slot back; anything but a stops the ladder before the reboot")
    lines.append("    5 one reboot")
    lines.append(
        "    6 poll %s devices every %.1fs for at most %.0fs, recording empty polls with offsets"
        % (resolved, args.poll_interval, args.observe_seconds)
    )
    lines.append("decision points:")
    lines.append("    loader serial enumerated -> success, read identity, stop the ladder")
    lines.append("    bootloader back after an empty gap -> that round failed, confirm product, next round")
    lines.append("    no fastboot serial for the whole window -> stop the ladder, needs a human")
    lines.append("    flash or set_active not OKAY -> stop before the reboot")
    return lines


def ladder_execute(args, tool, recorder):
    """Try candidates in order; one round per candidate, no retry inside a round."""
    entries = load_ladder(args.ladder)
    recorder.say("MODE ladder: %d rounds, stopping at the first loader" % len(entries))
    for entry in SCOPE_LADDER_IN:
        recorder.say("scope in:  " + entry)
    for entry in SCOPE_LADDER_OUT:
        recorder.say("scope out: " + entry)
    recorder.say("")
    problems = ladder_local_checks(args, entries, tool, recorder)
    if problems:
        raise PreflightStop("; ".join(problems))
    deadline = Deadline(args.total_seconds, "ladder")
    record_tool_version(tool, recorder, deadline)
    device = Device(
        tool, recorder, deadline, args.enum_cap, args.var_cap, args.boot_cap,
        args.reboot_cap, args.flash_cap,
    )
    rounds = []
    for index, entry in enumerate(entries, 1):
        label = entry.get("label") or ("round%d" % index)
        recipe = entry.get("recipe") or "(not labelled)"
        recorder.say("")
        recorder.say("== round %d/%d: %s ==" % (index, len(entries), label))
        recorder.say("recipe: " + recipe)
        product, slot = preflight_identity(args, device, recorder)
        if slot != args.ladder_expect_current_slot:
            raise DeviceStop(
                "%s: current-slot reads %r before the write, expected %r; the ladder stops here "
                "rather than writing onto an unexpected slot state"
                % (label, slot, args.ladder_expect_current_slot)
            )
        recorder.say("slot gate: current-slot is %s, as expected" % args.ladder_expect_current_slot)
        digest = sha256_file(Path(entry["image"]))
        recorder.say("image sha256 at flash time: " + digest)
        if digest != entry.get("sha256", "").lower():
            raise PreflightStop("%s: image hash changed since packaging; nothing was written" % label)
        flash_status = record_send(
            recorder, "flash boot_a " + label,
            lambda image=entry["image"]: device.flash(args.serial, "boot_a", image),
        )
        if not flash_status["ok"]:
            raise DeviceStop("%s: the flash did not report OKAY; no set_active and no reboot was sent" % label)
        device.set_active(args.serial, args.set_active_slot)
        after = require_value(
            device.getvar(args.serial, "current-slot"), "current-slot", "current slot after set_active"
        )
        recorder.say("current-slot after set_active: " + (after if after else "(empty)"))
        if after != args.set_active_slot:
            raise DeviceStop(
                "%s: set_active %s was accepted but current-slot reads %r; stopping before the reboot"
                % (label, args.set_active_slot, after)
            )
        reboot_status = record_send(recorder, "reboot " + label, lambda: device.reboot(args.serial))
        reboot_time = time.monotonic()
        result = observe(args, device, recorder, deadline, reboot_time, lk_return_stops=True)
        rounds.append(
            {
                "label": label,
                "recipe": recipe,
                "image": entry["image"],
                "sha256": digest,
                "slot_before": slot,
                "flash": describe_send(flash_status),
                "reboot": describe_send(reboot_status),
                "outcome": result["outcome"],
                "polls": result["polls"],
                "empty_polls": result["empty_polls"],
                "empty_offsets": ["%.2f" % value for value in result["empty_offsets"]],
            }
        )
        recorder.say("round %s outcome: %s" % (label, result["outcome"]))
        if result["outcome"] == "loader":
            recorder.say("")
            recorder.say("== loader identity, one query per variable ==")
            identity = loader_identity(args, device, recorder)
            recorder.say("")
            recorder.say("VERDICT: PASS after %d round(s)" % index)
            recorder.say(
                "    loader identity: product=%s version=%s build-id=%s result=%s"
                % (identity["product"], identity["version"], identity["build_id"], identity["result"])
            )
            recorder.say("    the ladder stops here; no further round is sent")
            write_ladder_summary(args, recorder, rounds, "loader")
            return EXIT_OK
        if result["outcome"] == "no_response":
            recorder.say("")
            recorder.say("VERDICT: STOP after round %s: no fastboot serial for the whole window" % label)
            recorder.say("    the ladder does not continue from an unresponsive device")
            write_ladder_summary(args, recorder, rounds, "no_response")
            raise DeviceStop("no fastboot serial appeared within %.0fs; the device needs a human" % args.observe_seconds)
        if index < len(entries):
            recorder.say("next round: confirming the bootloader answers before the next write")
    recorder.say("")
    recorder.say("VERDICT: FAILED after %d round(s); every round returned to the bootloader" % len(rounds))
    write_ladder_summary(args, recorder, rounds, "bootloader_returned")
    return EXIT_DEVICE
