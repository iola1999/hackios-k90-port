"""Flow helpers shared by the boot, flash and ladder flows: bounded observation and identity.

Kept apart from device-boot-once.py so each file stays under the 1000-line limit; the flows
themselves live in device-boot-once.py and device_ladder.py.
"""

import subprocess
import time

from device_boot_common import (
    DeadlineReached,
    DeviceStop,
    HostTimeout,
    PreflightStop,
    Stop,
    format_usb,
    parse_devices,
    require_value,
    usb_ids,
    usb_snapshot,
)

def record_send(recorder, label, call):
    """Run one send and turn its outcome into a record item.

    `Booting FAILED (usb_read failed ...)` means the device left the fastboot state mid-command.
    That is exactly the signal the observation is looking for, so the send result is recorded and
    the observation still runs. Only a spent host budget stops the run here.
    """
    try:
        return {"ok": True, "body": call(), "label": label, "timeout": False}
    except DeadlineReached:
        raise
    except Stop as stop:
        recorder.say("SEND RESULT: %s -> %s" % (label, stop))
        recorder.say("    recorded as an observation; the run continues into re-enumeration")
        return {"ok": False, "body": str(stop), "label": label, "timeout": isinstance(stop, HostTimeout)}


def describe_send(status):
    if status is None:
        return "no send"
    return ("OKAY" if status["ok"] else "FAILED") + " (" + status["label"] + ")"


def preflight_identity(args, device, recorder):
    """Read-only checks against the bootloader that is expected to answer boot."""
    body = device.devices()
    serials = parse_devices(body)
    recorder.say("enumerated serials: " + (", ".join(serials) if serials else "(none)"))
    if args.serial not in serials:
        raise PreflightStop(
            "target serial is not enumerated in the fastboot state; nothing was sent"
        )
    if serials != [args.serial]:
        recorder.say("note: other fastboot serials are present; commands stay bound to the target")
    body = device.getvar(args.serial, "product")
    product = require_value(body, "product", "bootloader product")
    if product == "":
        raise DeviceStop("bootloader product is empty")
    recorder.say("bootloader product: " + product)
    if args.expect_pre_product is not None and product != args.expect_pre_product:
        raise DeviceStop(
            "bootloader product %r does not match the approved %r" % (product, args.expect_pre_product)
        )
    if product == args.loader_serial:
        raise PreflightStop(
            "the target answers product %r: that is the resident loader, which does not implement boot"
            % product
        )
    body = device.getvar(args.serial, "current-slot")
    slot = require_value(body, "current-slot", "current slot")
    recorder.say("current-slot: " + (slot if slot else "(empty)"))
    if args.expect_current_slot is not None and slot != args.expect_current_slot:
        raise DeviceStop(
            "current-slot %r does not match the approved %r" % (slot, args.expect_current_slot)
        )
    return product, slot


def observe(args, device, recorder, total_deadline, send_time, lk_return_stops=False):
    """Poll enumeration and the host USB list; timestamp every change, including emptiness.

    An empty poll is a result, not a gap in the record: it is printed with its time offset and
    announced as an event, because "the device left the fastboot state" is what separates a
    loader that took control from one that never started. The USB list catches the window where
    the device is not in fastboot at all.
    """
    budget = total_deadline.nested(args.observe_seconds, "observation")
    poll = 0
    empty_polls = 0
    empty_offsets = []
    last = None
    gaps = []
    open_gap = None
    lk_after_gap = None
    lk_hold = 0
    usb_seen = set()
    prev_fb = None
    prev_usb = None
    watch = getattr(args, "watch_usb", True)
    while True:
        if budget.remaining() <= 0:
            break
        body = device.devices(deadline=budget)
        serials = parse_devices(body)
        entries = usb_snapshot() if watch else None
        ids = usb_ids(entries)
        poll += 1
        offset = time.monotonic() - send_time
        recorder.say(
            "poll%d t=+%.2fs fastboot=%s usb=%s"
            % (poll, offset, ", ".join(serials) if serials else "(none)", format_usb(entries))
        )
        if prev_fb is not None and serials != prev_fb:
            if not serials:
                recorder.say("EVENT t=+%.2fs fastboot enumeration became empty (device left fastboot)" % offset)
            else:
                recorder.say(
                    "EVENT t=+%.2fs fastboot enumeration listed: %s" % (offset, ", ".join(serials))
                )
        if ids is not None and prev_usb is not None and ids != prev_usb:
            appeared = sorted(set(ids) - set(prev_usb))
            gone = sorted(set(prev_usb) - set(ids))
            for ident in appeared:
                recorder.say("EVENT t=+%.2fs usb device appeared: %s" % (offset, ident))
            for ident in gone:
                recorder.say("EVENT t=+%.2fs usb device disappeared: %s" % (offset, ident))
        prev_fb = serials
        if ids is not None:
            prev_usb = ids
            usb_seen.update(ids)
        if not serials:
            empty_polls += 1
            empty_offsets.append(offset)
            if open_gap is None:
                open_gap = offset
        elif open_gap is not None:
            gaps.append((open_gap, offset))
            open_gap = None
        if lk_return_stops and serials and empty_polls and args.serial in serials:
            if lk_after_gap is None:
                lk_after_gap = offset
                recorder.say("EVENT t=+%.2fs the bootloader is back after an empty gap" % offset)
            lk_hold += 1
            if lk_hold >= 2:
                if open_gap is not None:
                    gaps.append((open_gap, offset))
                    open_gap = None
                recorder.say(
                    "observation summary: polls=%d empty_polls=%d outcome=bootloader_returned" % (poll, empty_polls)
                )
                recorder.say("empty poll offsets: " + ", ".join("+%.2fs" % v for v in empty_offsets))
                return {
                    "outcome": "lk_return",
                    "serials": [],
                    "polls": poll,
                    "empty_polls": empty_polls,
                    "empty_offsets": empty_offsets,
                    "gaps": gaps,
                    "usb_seen": sorted(usb_seen),
                }
        if args.loader_serial in serials:
            if open_gap is not None:
                gaps.append((open_gap, offset))
                open_gap = None
            recorder.say(
                "%s enumerated after %d poll(s) at t=+%.2fs" % (args.loader_serial, poll, offset)
            )
            recorder.say(
                "observation summary: polls=%d empty_polls=%d empty_gap=%s usb_seen=%s"
                % (
                    poll,
                    empty_polls,
                    ("yes" if gaps or open_gap is not None else "no"),
                    ", ".join(sorted(usb_seen)) if usb_seen else "(none)",
                )
            )
            if gaps:
                recorder.say("gaps: " + "; ".join("t=+%.2fs..+%.2fs" % (a, b) for a, b in gaps))
            if empty_offsets:
                recorder.say(
                    "empty poll offsets: " + ", ".join("+%.2fs" % value for value in empty_offsets)
                )
            return {
                "outcome": "loader",
                "serials": serials,
                "polls": poll,
                "empty_polls": empty_polls,
                "empty_offsets": empty_offsets,
                "gaps": gaps,
                "usb_seen": sorted(usb_seen),
            }
        last = serials
        pause = min(args.poll_interval, max(0.0, budget.remaining()))
        if pause > 0:
            time.sleep(pause)
    if open_gap is not None:
        gaps.append((open_gap, time.monotonic() - send_time))
    if last:
        detail = "the bootloader serial is still enumerated and no loader serial appeared"
    else:
        detail = "no fastboot serial was enumerated"
    recorder.say(
        "observation summary: polls=%d empty_polls=%d empty_gap=%s usb_seen=%s"
        % (
            poll,
            empty_polls,
            ("yes" if gaps else "no"),
            ", ".join(sorted(usb_seen)) if usb_seen else "(none)",
        )
    )
    if gaps:
        recorder.say("gaps: " + "; ".join("t=+%.2fs..+%.2fs" % (a, b) for a, b in gaps))
    if empty_offsets:
        recorder.say("empty poll offsets: " + ", ".join("+%.2fs" % value for value in empty_offsets))
    message = (
        "%s within the %.0fs observation budget; the device outcome is not established"
        % (detail, args.observe_seconds)
    )
    if gaps:
        message += " (an empty enumeration gap was observed, so the device did leave fastboot at least once)"
    else:
        message += " (enumeration never went empty: the device never left the fastboot state)"
    if lk_return_stops:
        outcome = "no_response" if not last else "never_left"
        recorder.say("observation summary: polls=%d empty_polls=%d outcome=%s" % (poll, empty_polls, outcome))
        recorder.say("empty poll offsets: " + ", ".join("+%.2fs" % v for v in empty_offsets))
        return {
            "outcome": outcome,
            "serials": last or [],
            "polls": poll,
            "empty_polls": empty_polls,
            "empty_offsets": empty_offsets,
            "gaps": gaps,
            "usb_seen": sorted(usb_seen),
        }
    if total_deadline.remaining() <= 0:
        raise DeadlineReached(message)
    raise DeviceStop(message)


def loader_identity(args, device, recorder):
    """One query per variable, only on a serial that the enumeration already listed."""
    product = require_value(
        device.getvar(args.loader_serial, "product"), "product", "loader product"
    )
    recorder.say("loader product: " + (product if product else "(empty)"))
    if product != args.loader_serial:
        raise DeviceStop(
            "loader product %r does not match the expected %r" % (product, args.loader_serial)
        )
    version = require_value(
        device.getvar(args.loader_serial, "version"), "version", "loader version"
    )
    recorder.say("loader version: " + (version if version else "(empty)"))
    if args.expect_version is not None and version != args.expect_version:
        raise DeviceStop(
            "loader version %r does not match the approved %r" % (version, args.expect_version)
        )
    build_id = require_value(
        device.getvar(args.loader_serial, "build-id"), "build-id", "loader build-id"
    )
    recorder.say("loader build-id: " + (build_id if build_id else "(empty)"))
    expected_build_id = "" if args.allow_empty_build_id else args.expect_build_id
    if build_id != expected_build_id:
        raise DeviceStop(
            "loader build-id %r does not match the expected %r%s"
            % (
                build_id,
                expected_build_id,
                " (empty, archived image)" if args.allow_empty_build_id else "",
            )
        )
    result = require_value(device.getvar(args.loader_serial, "result"), "result", "loader result")
    recorder.say("loader result: " + (result if result else "(empty)"))
    if result != "idle":
        raise DeviceStop("loader result is %r, not idle; this run does not act on a live kernel" % result)
    return {"product": product, "version": version, "build_id": build_id, "result": result}


def record_tool_version(tool, recorder, deadline):
    """Local command: record which fastboot binary and version this run used."""
    try:
        completed = subprocess.run(
            [tool, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=min(2.0, max(0.2, deadline.remaining())),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        recorder.say("fastboot version: not recorded (%s)" % error)
        return
    recorder.say("fastboot: " + tool)
    recorder.block("fastboot --version", completed.stdout)
