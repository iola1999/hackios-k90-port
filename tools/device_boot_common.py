"""Shared machinery for the device scripts: bounded child calls, deadlines, log recorder.

Split out of device-boot-once.py to keep each file under the 1000-line limit; nothing here
knows about a particular flow (RAM boot, flash, recovery).
"""

import hashlib
import os
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = ROOT / "logs" / "device-boot-once"

EXIT_OK = 0
EXIT_DEVICE = 1
EXIT_USAGE = 2
EXIT_PREFLIGHT = 3
EXIT_DEADLINE = 4

FORTY_HEX = re.compile(r"^[0-9a-f]{40}$")
SIXTY_FOUR_HEX = re.compile(r"^[0-9a-f]{64}$")

SCOPE_IN = (
    "enumeration (read-only), bootloader identity and current slot (read-only)",
    "image hash re-check immediately before the send",
    "exactly one fastboot boot of the approved candidate",
    "bounded re-enumeration plus one query each of product/version/build-id/result",
)
SCOPE_OUT = (
    "kernel load, oem run, stage, oem stop",
    "GPU work of any kind",
    "slot switch (set_active) and any flash or erase",
    "adb commands and oem reboot",
    "reboot in the boot flow; recovery is the separate action --recover-reboot only",
    "automatic retry and automatic recovery",
)


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def shell_join(argv):
    return " ".join(shlex.quote(part) for part in argv)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_devices(text):
    """Return the serials that `fastboot devices` reports in the fastboot state."""
    serials = []
    for raw in (text or "").splitlines():
        parts = raw.strip().split()
        if len(parts) >= 2 and parts[1] == "fastboot":
            serials.append(parts[0])
    return serials


def parse_getvar(text, var):
    """Return (value, failure_line) for one getvar variable.

    fastboot answers a good variable on a line `var: value` and a missing one on a line
    `getvar:var ... FAILED (...)`. `value` is None when no value line is present and "" when the
    loader answered an empty value; the caller distinguishes both from a real value.
    """
    value = None
    failure = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.lower().startswith("getvar:" + var) and "failed" in line.lower():
            failure = line
        match = re.match(r"^" + re.escape(var) + r":(.*)$", line)
        if match:
            value = match.group(1).strip()
    return value, failure


def usb_snapshot():
    """USB device list with VID:PID, read on the host (macOS ioreg). Read-only, 0.01s.

    `fastboot devices` only lists devices in the fastboot state, so it cannot show a gadget that
    the loader brings up while it runs. This returns every USB device as {id, name, serial} so a
    disappearance and a re-appearance can be timestamped (runbook §4.4).
    """
    ioreg_cmd = os.environ.get("DEVICE_BOOT_ONCE_IOREG", "ioreg")
    try:
        completed = subprocess.run(
            [ioreg_cmd, "-p", "IOUSB", "-l", "-w", "0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    entries = []
    name = None
    serial = None
    vid = None
    for line in completed.stdout.splitlines():
        match = re.search(r'"USB Product Name" = "([^"]*)"', line)
        if match:
            name = match.group(1)
            continue
        match = re.search(r'"USB Serial Number" = "([^"]*)"', line)
        if match:
            serial = match.group(1)
            continue
        match = re.search(r'"idVendor" = (\d+)', line)
        if match:
            vid = int(match.group(1))
            continue
        match = re.search(r'"idProduct" = (\d+)', line)
        if match:
            pid = int(match.group(1))
            ident = ("%04x:%04x" % (vid, pid)) if vid is not None else ("????:%04x" % pid)
            entries.append({"id": ident, "name": name or "", "serial": serial or ""})
    return entries


def usb_ids(entries):
    if entries is None:
        return None
    return sorted({entry["id"] for entry in entries})


def format_usb(entries):
    if entries is None:
        return "unavailable"
    if not entries:
        return "(none)"
    seen = {}
    for entry in entries:
        key = entry["id"]
        label = entry["name"][:24]
        seen[key] = label if label and key not in seen else seen.get(key, label)
    return ", ".join("%s(%s)" % (key, seen[key]) if seen[key] else key for key in sorted(seen))


def argv_devices(tool):
    return [tool, "devices"]


def argv_getvar(tool, serial, var):
    return [tool, "-s", serial, "getvar", var]


def argv_boot(tool, serial, image):
    return [tool, "-s", serial, "boot", image]


def argv_reboot(tool, serial):
    return [tool, "-s", serial, "reboot"]


class Stop(Exception):
    """The run stops here; nothing is retried and no recovery command is sent."""

    exit_code = EXIT_DEVICE
    note = ""


class UsageStop(Stop):
    exit_code = EXIT_USAGE


class PreflightStop(Stop):
    exit_code = EXIT_PREFLIGHT


class DeviceStop(Stop):
    exit_code = EXIT_DEVICE


class HostTimeout(Stop):
    exit_code = EXIT_DEADLINE
    note = "host wait stopped; the device side may still be acting (outcome unknown)"


class DeadlineReached(Stop):
    exit_code = EXIT_DEADLINE
    note = "host deadline reached; the device side may still be acting (outcome unknown)"


class Recorder:
    """Timestamps every line to stdout and, in execute mode, to the run log."""

    def __init__(self, log_path=None):
        self.log_path = log_path
        self._handle = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = log_path.open("w", encoding="utf-8")

    def say(self, message=""):
        for line in str(message).splitlines() or [""]:
            stamped = "[" + utc() + "] " + line
            print(stamped, flush=True)
            if self._handle is not None:
                self._handle.write(stamped + "\n")
                self._handle.flush()

    def block(self, title, body):
        self.say("--- " + title + " ---")
        lines = (body or "").splitlines()
        if not lines:
            self.say("    (no output)")
        for line in lines:
            self.say("    " + line)

    def close(self):
        if self._handle is not None:
            self._handle.close()
            self._handle = None


class Deadline:
    """A host-side monotonic budget. Child deadlines never extend the parent."""

    def __init__(self, seconds, label):
        self.label = label
        self.end = time.monotonic() + max(0.0, seconds)

    def remaining(self):
        return self.end - time.monotonic()

    def nested(self, seconds, label):
        child = Deadline(0, label)
        child.end = min(self.end, time.monotonic() + max(0.0, seconds))
        return child

    def require(self):
        if self.remaining() <= 0:
            raise DeadlineReached(self.label + " budget is spent")


def run_argv(argv, cap, label, recorder, budget):
    """One bounded child process. A FAILED protocol body fails the call even when rc is 0."""
    remaining = budget.remaining()
    if remaining <= 0:
        raise DeadlineReached(budget.label + " budget is spent before " + label)
    timeout = max(0.2, min(cap, remaining))
    recorder.say("RUN " + label)
    recorder.say("    argv: " + shell_join(argv))
    recorder.say("    cap: %.2fs, host deadline left: %.2fs" % (timeout, remaining))
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        partial = error.stdout
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        recorder.say(
            "TIMEOUT %s after %.2fs: host wait stopped, no retry" % (label, time.monotonic() - started)
        )
        recorder.block("partial output", partial)
        raise HostTimeout(label + " exceeded the host cap")
    except OSError as error:
        raise PreflightStop("cannot run %s: %s" % (argv[0], error))
    elapsed = time.monotonic() - started
    body = completed.stdout or ""
    recorder.say("DONE %s: rc=%d elapsed=%.2fs" % (label, completed.returncode, elapsed))
    recorder.block("output", body)
    # The protocol answer matters, not the CLI exit code: a FAILED body must stop the call even
    # when the tool returns 0 (LK answers an unknown getvar this way).
    if "FAILED" in body:
        raise DeviceStop(label + ": protocol body contains FAILED (rc=%d)" % completed.returncode)
    if completed.returncode != 0:
        raise DeviceStop(label + ": exit code %d" % completed.returncode)
    return body


class Adb:
    """Bounded adb calls, fixed argv, one process per call."""

    def __init__(self, tool, recorder, deadline, cap=10.0):
        self.tool = tool
        self.recorder = recorder
        self.deadline = deadline
        self.cap = cap

    def devices(self, deadline=None):
        return run_argv([self.tool, "devices"], self.cap, "adb devices", self.recorder, deadline or self.deadline)

    def shell(self, serial, command, deadline=None):
        return run_argv(
            [self.tool, "-s", serial, "shell", command],
            self.cap,
            "adb shell: " + command,
            self.recorder,
            deadline or self.deadline,
        )

    def reboot_bootloader(self, serial, deadline=None):
        return run_argv(
            [self.tool, "-s", serial, "reboot", "bootloader"],
            self.cap,
            "adb reboot bootloader",
            self.recorder,
            deadline or self.deadline,
        )


class Device:
    """Fixed fastboot argv, one process per call, no shell, every call bounded."""

    def __init__(self, tool, recorder, deadline, enum_cap, var_cap, boot_cap, reboot_cap=30.0,
                 flash_cap=180.0):
        self.tool = tool
        self.recorder = recorder
        self.deadline = deadline
        self.enum_cap = enum_cap
        self.var_cap = var_cap
        self.boot_cap = boot_cap
        self.reboot_cap = reboot_cap
        self.flash_cap = flash_cap

    def _run(self, argv, cap, label, deadline=None):
        return run_argv(argv, cap, label, self.recorder, deadline or self.deadline)

    def devices(self, deadline=None):
        return self._run(argv_devices(self.tool), self.enum_cap, "enumerate fastboot devices", deadline)

    def getvar(self, serial, var, deadline=None):
        return self._run(
            argv_getvar(self.tool, serial, var),
            self.var_cap,
            "getvar %s on %s" % (var, serial),
            deadline,
        )

    def boot(self, serial, image):
        return self._run(
            argv_boot(self.tool, serial, image),
            self.boot_cap,
            "single boot send of " + image,
        )

    def flash(self, serial, partition, image):
        return self._run(
            [self.tool, "-s", serial, "flash", partition, image],
            self.flash_cap,
            "single flash of %s into %s" % (image, partition),
        )

    def set_active(self, serial, slot):
        # The flag form is what this bootloader answered OKAY to on 2026-10-25 (19:41:06Z);
        # the `set_active <slot>` subcommand has not been exercised on it.
        return self._run(
            [self.tool, "-s", serial, "--set-active=" + slot],
            self.var_cap,
            "set_active " + slot,
        )

    def reboot(self, serial):
        """Recovery only. Never called from the boot flow (see execute())."""
        return self._run(
            argv_reboot(self.tool, serial),
            self.reboot_cap,
            "recovery reboot on " + serial,
        )


def require_value(body, var, label):
    value, failure = parse_getvar(body, var)
    if failure is not None:
        raise DeviceStop("%s: protocol body reports %s" % (label, failure))
    if value is None:
        raise DeviceStop("%s: no %s line in the reply" % (label, var))
    return value


