#!/usr/bin/env python3
"""Host simulation for tools/device-boot-once.py -- no device is contacted.

A fake `fastboot` stands in for the bootloader, answers the getvar/boot/devices sequences of the
planned run and records every argv element it receives. The checks cover the boundaries the
runbook requires: no implicit device, dry-run sends nothing, exactly one boot send, a FAILED
protocol body fails even with exit code 0, a host timeout stops the run, a serial that never
enumerates is never queried, and the approved build id is required after the boot.

Usage: python3 tools/test-device-boot-once.py
Every check prints one PASS line; the first failure prints the recorded call log and exits 1.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "tools" / "device-boot-once.py")

LK_SERIAL = "FAKE-LK-SERIAL"
APPROVED_BID = "0123456789abcdef0123456789abcdef01234567"
FAKE_BUILD_ID = APPROVED_BID

FAKE_FASTBOOT = r'''#!/usr/bin/env bash
# Host-only stand-in: records argv, never opens USB.
printf '%s\n' "$*" >> "${FAKE_CALLS:?}"
scenario="${FAKE_SCENARIO:?}"
state="${FAKE_STATE:?}"
frames() {
	case "$scenario" in
	success|wrong_build_id)
		if [ -f "$state/booted" ] || [ -f "$state/flashed" ]; then printf 'xnuloader\t fastboot\n'
		else printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"; fi ;;
	wrong_serial)
		printf 'OTHER-DEVICE\t fastboot\n' ;;
	ladder_ok)
		if [ -f "$state/rounds" ] && [ "$(cat "$state/rounds")" -ge 1 ]; then printf 'xnuloader\t fastboot\n'
		else printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"; fi ;;
	ladder_fail_then_ok)
		n=0; [ -f "$state/rounds" ] && n=$(cat "$state/rounds")
		if [ "$n" -ge 2 ]; then printf 'xnuloader\t fastboot\n'
		elif [ "$n" -ge 1 ]; then
			g=0; [ -f "$state/gone" ] && g=$(cat "$state/gone"); g=$((g+1)); printf '%s' "$g" > "$state/gone"
			if [ "$g" -le 2 ]; then exit 0; fi
			printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"
		else printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"; fi ;;
	ladder_no_response)
		if [ -f "$state/rounds" ]; then exit 0; fi
		printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}" ;;
	usb_then_lk)
		if [ -f "$state/left-fastboot" ]; then
			n=0; [ -f "$state/gone" ] && n=$(cat "$state/gone")
			n=$((n+1)); printf '%s' "$n" > "$state/gone"
			if [ "$n" -le 3 ]; then exit 0; fi
			printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"
		else printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"; fi ;;
	*)
		printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}" ;;
	esac
}
case "$*" in
	--version) printf 'fastboot version 99.0.0-fake\n' ;;
	devices) frames ;;
	"-s ${FAKE_LK_SERIAL:?} getvar product")
		if [ "$scenario" = loader_env ]; then
			printf 'product: xnuloader\nFinished. Total time: 0.004s\n'
		elif [ "$scenario" = fail_product ]; then
			printf "getvar:product                                     FAILED (remote: 'GetVar Variable Not found')\n"
		else
			printf 'product: annibale\nFinished. Total time: 0.004s\n'
		fi ;;
	"-s ${FAKE_LK_SERIAL:?} getvar current-slot")
		if [ "$scenario" = ladder_slot_pre_b ]; then
			printf 'current-slot: b\nFinished. Total time: 0.004s\n'
		elif [ "$scenario" = ladder_slot_b ] && [ -f "$state/set-active" ]; then
			printf 'current-slot: b\nFinished. Total time: 0.004s\n'
		else
			printf 'current-slot: a\nFinished. Total time: 0.004s\n'
		fi ;;
	"-s ${FAKE_LK_SERIAL:?} flash boot_a "*)
		if [ "$scenario" = flash_failed ]; then
			printf "Sending 'boot_a' (1024 KB)                         OKAY [  0.001s]\n"
			printf "Writing 'boot_a'                                   FAILED (remote: 'partition write error')\n"
		else
			printf "Sending 'boot_a' (1024 KB)                         OKAY [  0.001s]\n"
			printf "Writing 'boot_a'                                   OKAY [  0.001s]\n"
			: > "$state/flashed"
			n=0; [ -f "$state/rounds" ] && n=$(cat "$state/rounds"); printf '%s' "$((n+1))" > "$state/rounds"
		fi ;;
	"-s ${FAKE_LK_SERIAL:?} --set-active="*)
		printf "Setting current slot to '%s'                       OKAY [  0.001s]\n" "${*##*--set-active=}"
		: > "$state/set-active" ;;
	"-s ${FAKE_LK_SERIAL:?} reboot")
		printf 'Rebooting                                          OKAY [  0.000s]\n'
		: > "$state/reboot-sent" ;;
	"-s ${FAKE_LK_SERIAL:?} boot "*)
		case "$scenario" in
		boot_failed_rc0)
			printf "Sending 'boot.img' (1024 KB)                       OKAY [  0.001s]\n"
			printf "Booting                                            FAILED (remote: 'unknown command')\n" ;;
		boot_no_okay)
			printf "Sending 'boot.img' (1024 KB)\n" ;;
		boot_rc1)
			printf "Sending 'boot.img' (1024 KB)                       OKAY [  0.001s]\n"
			printf "FAILED (remote: 'boot rejected')\n"
			exit 1 ;;
		ladder_ok)
		if [ -f "$state/rounds" ] && [ "$(cat "$state/rounds")" -ge 1 ]; then printf 'xnuloader\t fastboot\n'
		else printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"; fi ;;
	ladder_fail_then_ok)
		n=0; [ -f "$state/rounds" ] && n=$(cat "$state/rounds")
		if [ "$n" -ge 2 ]; then printf 'xnuloader\t fastboot\n'
		elif [ "$n" -ge 1 ]; then
			g=0; [ -f "$state/gone" ] && g=$(cat "$state/gone"); g=$((g+1)); printf '%s' "$g" > "$state/gone"
			if [ "$g" -le 2 ]; then exit 0; fi
			printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"
		else printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}"; fi ;;
	ladder_no_response)
		if [ -f "$state/rounds" ]; then exit 0; fi
		printf '%s\t fastboot\n' "${FAKE_LK_SERIAL:?}" ;;
	usb_then_lk)
			printf "Sending 'boot.img' (1234 KB)                       OKAY [  0.029s]\n"
			printf "Booting                                            FAILED (usb_read failed with status e00002ed)\n"
			: > "$state/left-fastboot" ;;
		slow_boot)
			sleep 5
			# only written if this process survived the host cap: proves kill vs background
			: > "$state/survived-past-cap"
			printf 'Booting                                            OKAY [  0.001s]\n'
			: > "$state/booted" ;;
		*)
			printf "Sending 'boot.img' (1024 KB)                       OKAY [  0.001s]\n"
			printf 'Booting                                            OKAY [  0.001s]\n'
			: > "$state/booted" ;;
		esac ;;
	"-s ${FAKE_LOADER_SERIAL:?} getvar product")  printf 'product: %s\nFinished. Total time: 0.004s\n' "${FAKE_LOADER_SERIAL:?}" ;;
	"-s ${FAKE_LOADER_SERIAL:?} getvar version")  printf 'version: 0.5\nFinished. Total time: 0.004s\n' ;;
	"-s ${FAKE_LOADER_SERIAL:?} getvar build-id") printf 'build-id: %s\nFinished. Total time: 0.004s\n' "${FAKE_LOADER_BID:?}" ;;
	"-s ${FAKE_LOADER_SERIAL:?} getvar result")   printf 'result: idle\nFinished. Total time: 0.004s\n' ;;
	*)
		printf "FAILED (remote: 'unexpected fake argument')\n"
		exit 1 ;;
esac
exit 0
'''

FAILURES = []


def check(condition, label):
    if condition:
        print("PASS " + label)
    else:
        FAILURES.append(label)
        print("FAIL " + label)


def calls(log_path):
    if not log_path.exists():
        return []
    return [line.rstrip("\n") for line in log_path.read_text().splitlines() if line.strip()]


def device_calls(recorded):
    """Drop the local tool-version record; the rest are device calls."""
    return [line for line in recorded if line != "--version"]


def reboot_calls(recorded):
    return [line for line in recorded if line.endswith(" reboot") or " reboot " in line]


def boot_calls(recorded):
    return [line for line in recorded if " boot " in line]


class Run:
    """One rehearsal run: temp dir, fake fastboot, canned scenario."""

    def __init__(self, scenario, answer_bid=APPROVED_BID):
        self.scenario = scenario
        self.answer_bid = answer_bid

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="device-boot-once-test-")
        base = Path(self._tmp.name)
        self.state = base / "state"
        self.state.mkdir()
        self.log = base / "calls.log"
        fake = base / "fastboot"
        fake.write_text(FAKE_FASTBOOT)
        fake.chmod(0o755)
        image = base / "cand.img"
        image.write_bytes(b"\0" * 4096)
        import hashlib

        self.image = image
        self.sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
        self.fake = fake
        self.base = base
        return self

    def __exit__(self, *_):
        self._tmp.cleanup()

    def execute(self, *, dry_run=False, serial=LK_SERIAL, image=None, sha256=None,
                build_id=APPROVED_BID, extra=None, recover=False, total=20, boot_cap=1,
                flash=False, set_active=False, ladder=None):
        if ladder:
            manifest = self.base / "ladder.json"
            entries = []
            for index, label in enumerate(ladder, 1):
                image = self.base / ("cand%d.img" % index)
                image.write_bytes(bytes([index]) * 4096)
                import hashlib
                entries.append(
                    {
                        "label": label,
                        "image": str(image),
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    }
                )
            manifest.write_text(__import__("json").dumps({"candidates": entries}))
            argv = [sys.executable, SCRIPT, "--fastboot", str(self.fake), "--ladder", str(manifest),
                    "--expect-build-id", build_id, "--set-active-slot", "a"]
        elif flash:
            argv = [sys.executable, SCRIPT, "--fastboot", str(self.fake),
                    "--flash-image", str(image or self.image),
                    "--flash-image-sha256", sha256 or self.sha256,
                    "--flash-partition", "boot_a", "--expect-build-id", build_id]
            if set_active:
                argv.extend(["--set-active-slot", "a"])
        else:
            argv = [sys.executable, SCRIPT, "--fastboot", str(self.fake), "--image", str(image or self.image),
                    "--image-sha256", sha256 or self.sha256, "--expect-build-id", build_id]
        argv.extend([
            "--loader-serial", "xnuloader", "--log-dir", str(self.base / "logs"),
            "--enum-cap", "1", "--var-cap", "1", "--boot-cap", str(boot_cap),
            "--reboot-cap", "1",
            "--observe-seconds", "3", "--poll-interval", "0.1", "--total-seconds", str(total),
        ])
        if serial is not None:
            argv.extend(["--serial", serial])
        if not dry_run:
            argv.append("--execute")
        if recover:
            argv.append("--recover-reboot")
        argv.extend(extra or [])
        env = dict(os.environ)
        env.pop("ANDROID_SERIAL", None)
        env.update(
            FAKE_CALLS=str(self.log),
            FAKE_SCENARIO=self.scenario,
            FAKE_STATE=str(self.state),
            FAKE_LK_SERIAL=LK_SERIAL,
            FAKE_LOADER_SERIAL="xnuloader",
            FAKE_LOADER_BID=self.answer_bid,
        )
        completed = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60, env=env
        )
        return completed


def expect_one_boot(recorded, label):
    check(len(boot_calls(recorded)) == 1, label + ": exactly one boot send")
    check(len([line for line in recorded if line.startswith("-s " + LK_SERIAL + " boot ")]) == 1,
          label + ": the boot send is bound to the target serial")


def main():
    print("== dry-run: no device command is sent ==")
    with Run("success") as run:
        result = run.execute(dry_run=True)
        check(result.returncode == 0, "dry-run exits 0 on a well-formed plan")
        check(calls(run.log) == [], "dry-run recorded zero fastboot calls")
        check("phase 2 (one send)" in result.stdout, "dry-run prints the single send")
        check("MODE dry-run" in result.stdout, "dry-run names its mode")

    print("== missing serial: usage stop before any command ==")
    with Run("success") as run:
        env_serial = os.environ.pop("ANDROID_SERIAL", None)
        try:
            result = run.execute(dry_run=False, serial=None)
        finally:
            if env_serial is not None:
                os.environ["ANDROID_SERIAL"] = env_serial
        check(result.returncode == 2, "missing serial exits 2")
        check(calls(run.log) == [], "missing serial recorded zero fastboot calls")

    print("== hash mismatch: preflight stop before any command ==")
    with Run("success") as run:
        result = run.execute(dry_run=False, sha256="0" * 64)
        check(result.returncode == 3, "hash mismatch exits 3")
        check(calls(run.log) == [], "hash mismatch recorded zero fastboot calls")

    print("== success: one send, bounded observation, identity matched ==")
    with Run("success") as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 0, "success exits 0")
        check("VERDICT: PASS" in result.stdout, "success prints the PASS verdict")
        expect_one_boot(recorded, "success")
        calls_only = device_calls(recorded)
        check("--version" in recorded, "success: the tool version is recorded")
        check(calls_only[0] == "devices", "success: first device call is the pre-boot enumeration")
        check(any("getvar product" in line and LK_SERIAL in line for line in calls_only),
              "success: bootloader product read before the send")
        loader_queries = [line for line in calls_only if line.startswith("-s xnuloader getvar ")]
        check(len(loader_queries) == 4, "success: exactly four loader queries")
        check(len(set(loader_queries)) == 4, "success: one query per variable, no repeats")
        check(all(line.startswith("-s ") or line == "devices" for line in calls_only),
              "success: every serial-scoped call carries -s")

    print("== FAILED body with exit code 0 stops the run ==")
    with Run("boot_failed_rc0") as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 1, "FAILED body exits 1 even though fastboot returned 0")
        check("FAILED" in result.stdout, "FAILED body is visible in the record")
        expect_one_boot(recorded, "FAILED body")
        check(not any("xnuloader" in line for line in recorded), "FAILED body: no loader query followed")

    print("== FAILED on a pre-boot getvar stops before the send ==")
    with Run("fail_product") as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 1, "pre-boot FAILED exits 1")
        check(boot_calls(recorded) == [], "pre-boot FAILED: nothing was sent")

    print("== nonzero exit code without FAILED text also stops ==")
    with Run("boot_rc1") as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 1, "boot exit code 1 exits 1")
        expect_one_boot(recorded, "boot exit 1")
        check(not any("xnuloader" in line for line in recorded), "boot exit 1: no loader query followed")

    print("== reply without OKAY: the send is not accepted as confirmed ==")
    with Run("boot_no_okay") as run:
        result = run.execute()
        check(result.returncode == 1, "missing OKAY exits 1")
        check("no OKAY" in result.stdout, "missing OKAY names the reason")
        expect_one_boot(device_calls(calls(run.log)), "missing OKAY")

    print("== host timeout: the wait is stopped, nothing is retried ==")
    with Run("slow_boot") as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 4, "boot timeout exits 4")
        check("device side may still be acting" in result.stdout or "outcome unknown" in result.stdout,
              "boot timeout records the device-side unknown state")
        expect_one_boot(recorded, "boot timeout")
        check("SEND RESULT: boot ->" in result.stdout,
              "boot timeout: the failed send is recorded as a send result")
        check("poll1 " in result.stdout, "boot timeout: the observation still runs")

    print("== loader never enumerates: no query on an absent serial ==")
    with Run("lk_persists") as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 1, "no loader enumeration exits 1")
        expect_one_boot(recorded, "no loader")
        check(not any("xnuloader" in line for line in recorded),
              "no loader: the absent serial is never queried")

    print("== wrong build id: identity mismatch stops the run ==")
    with Run("wrong_build_id", answer_bid="b" * 40) as run:
        result = run.execute()
        recorded = calls(run.log)
        check(result.returncode == 1, "build-id mismatch exits 1")
        check("does not match the expected" in result.stdout, "build-id mismatch names the expected value")
        expect_one_boot(recorded, "build-id mismatch")

    print("== resident loader environment is refused, nothing is sent ==")
    with Run("loader_env") as run:
        result = run.execute()
        check(result.returncode == 3, "resident loader environment exits 3")
        check("does not implement boot" in result.stdout, "resident loader environment names the reason")
        check(boot_calls(calls(run.log)) == [], "resident loader environment: nothing was sent")

    print("== requested serial not enumerated: nothing is sent ==")
    with Run("wrong_serial") as run:
        result = run.execute()
        check(result.returncode == 3, "unenumerated target exits 3")
        check("not enumerated" in result.stdout, "unenumerated target names the precondition")
        check(boot_calls(calls(run.log)) == [], "unenumerated target: nothing was sent")

    print("== bootloader answering as the resident loader is refused ==")
    with Run("success") as run:
        result = run.execute(extra=["--expect-pre-product", "xnuloader"])
        check(result.returncode != 0, "wrong pre-product expectation stops the run")
        check("does not match the approved" in result.stdout, "pre-product mismatch names the approved value")
        check(boot_calls(calls(run.log)) == [], "pre-product mismatch: nothing was sent")

    print("== the boot flow never reboots ==")
    with Run("success") as run:
        result = run.execute()
        recorded = device_calls(calls(run.log))
        check(result.returncode == 0, "boot flow exits 0")
        check(reboot_calls(recorded) == [], "boot flow: zero reboot calls")
        check(boot_calls(recorded) != [], "boot flow: the single boot send is present")

    print("== recovery reboot: separate action, exactly one command, nothing follows ==")
    with Run("success") as run:
        result = run.execute(recover=True)
        recorded = device_calls(calls(run.log))
        check(result.returncode == 0, "recovery exits 0")
        check(reboot_calls(recorded) == ["-s " + LK_SERIAL + " reboot"], "recovery: exactly one reboot, bound to the target")
        check(boot_calls(recorded) == [], "recovery: no boot send")
        check(not any("getvar" in line for line in recorded), "recovery: no getvar follows the reboot")
        check(recorded[-1].endswith(" reboot"), "recovery: the reboot is the last device call")
        check(not (run.state / "booted").exists(), "recovery: the fake never saw a boot")

    print("== recovery dry-run sends nothing ==")
    with Run("success") as run:
        result = run.execute(dry_run=True, recover=True)
        check(result.returncode == 0, "recovery dry-run exits 0")
        check(calls(run.log) == [], "recovery dry-run recorded zero fastboot calls")
        check("recovery reboot only" in result.stdout, "recovery dry-run names the action")
        check("no enumeration, query or second command follows the reboot" in result.stdout,
              "recovery dry-run states that nothing follows")

    print("== a timed-out child is killed, not left in the background ==")
    with Run("slow_boot") as run:
        result = run.execute(boot_cap=1)
        survived = (run.state / "survived-past-cap").exists()
        check(result.returncode == 4, "timed-out boot exits 4")
        check(not survived, "timed-out child was killed before finishing its 5s work")

    print("== the overall budget is enforced, reported as a deadline stop ==")
    # lk_persists never presents a loader, so the observation budget is the thing that runs out
    with Run("lk_persists") as run:
        result = run.execute(total=3, boot_cap=10)
        check(result.returncode == 4, "exhausted overall budget exits 4")
        check("STOP:" in result.stdout and "budget" in result.stdout,
              "exhausted budget stops with a budget message")
        check(len(boot_calls(device_calls(calls(run.log)))) == 1,
              "exhausted budget: exactly one boot send, never repeated")

    print("== Booting FAILED at USB level still runs the observation ==")
    with Run("usb_then_lk") as run:
        result = run.execute()
        recorded = device_calls(calls(run.log))
        check(result.returncode == 1, "usb-level Booting FAILED ends in exit 1, not a silent pass")
        check("SEND RESULT: boot ->" in result.stdout, "the failed send is recorded as a send result")
        check("usb_read failed" in result.stdout, "the usb_read failure text is kept")
        check("poll1 " in result.stdout, "the observation still ran after the failure")
        check("fastboot=(none)" in result.stdout, "the empty poll is written to the log")
        check("empty_polls=" in result.stdout, "the empty poll count is reported")
        check(len(boot_calls(recorded)) == 1, "still exactly one boot send")

    print("== flash flow: one write, one reboot, no second flash ==")
    with Run("success") as run:
        result = run.execute(flash=True)
        recorded = device_calls(calls(run.log))
        flash = [line for line in recorded if " flash " in line]
        check(result.returncode == 0, "flash flow exits 0 when the loader comes back")
        check(len(flash) == 1, "exactly one flash send")
        check(flash and flash[0].startswith("-s " + LK_SERIAL + " flash boot_a"), "the flash is bound and targets boot_a")
        check(reboot_calls(recorded) == ["-s " + LK_SERIAL + " reboot"], "exactly one reboot, bound to the target")
        check(boot_calls(recorded) == [], "flash flow sends no ram boot")
        check((run.state / "flashed").exists(), "the fake saw the write")
        check("loader identity" in result.stdout, "the loader identity is read after the reboot")

    print("== flash flow: a FAILED write stops before the reboot ==")
    with Run("flash_failed") as run:
        result = run.execute(flash=True)
        recorded = device_calls(calls(run.log))
        check(result.returncode == 1, "a FAILED write fails the run")
        check(reboot_calls(recorded) == [], "no reboot is sent after a FAILED write")
        check(len([line for line in recorded if " flash " in line]) == 1, "the write is not retried")

    print("== flash flow: set_active is read back ==")
    with Run("success") as run:
        result = run.execute(flash=True, set_active=True)
        recorded = device_calls(calls(run.log))
        check(result.returncode == 0, "set_active path exits 0")
        check([line for line in recorded if "--set-active=a" in line] != [], "set_active is sent once")
        check("current-slot after set_active" in result.stdout, "current-slot is read back after set_active")

    print("== ladder: the first round brings a loader up ==")
    with Run("ladder_ok") as run:
        result = run.execute(ladder=["F1"])
        recorded = device_calls(calls(run.log))
        check(result.returncode == 0, "ladder success exits 0")
        check(len([line for line in recorded if " flash " in line]) == 1, "ladder success: exactly one write")
        check("VERDICT: PASS after 1 round" in result.stdout, "ladder success names the round count")
        check("the ladder stops here" in result.stdout, "ladder success states that it stops")
        check((run.base / "logs").exists(), "ladder writes its log")

    print("== ladder: a round that returns to the bootloader hands over to the next ==")
    with Run("ladder_fail_then_ok") as run:
        result = run.execute(ladder=["F1", "F2"])
        recorded = device_calls(calls(run.log))
        flash = [line for line in recorded if " flash " in line]
        check(result.returncode == 0, "second round succeeding exits 0")
        check(len(flash) == 2, "two writes, one per round, no retry")
        check(flash[0] != flash[1], "the two rounds write different images")
        check("outcome: lk_return" in result.stdout, "the failed round is recorded as lk_return")
        check("VERDICT: PASS after 2 round" in result.stdout, "the verdict names how many rounds ran")

    print("== ladder: an unresponsive device stops the ladder ==")
    with Run("ladder_no_response") as run:
        result = run.execute(ladder=["F1", "F2"])
        recorded = device_calls(calls(run.log))
        check(result.returncode != 0, "no response fails the ladder")
        check(len([line for line in recorded if " flash " in line]) == 1, "no response: the ladder stops after that round")
        check("no fastboot serial" in result.stdout, "no response names the reason")

    print("== ladder: a slot that does not read back as the requested one stops before the reboot ==")
    with Run("ladder_slot_b") as run:
        result = run.execute(ladder=["F1"])
        recorded = device_calls(calls(run.log))
        check(result.returncode != 0, "slot mismatch fails the round")
        check(reboot_calls(recorded) == [], "slot mismatch: no reboot is sent")
        check("current-slot reads 'b'" in result.stdout, "slot mismatch names the observed value")

    print("== ladder: a slot that is not the expected one aborts the whole ladder before writing ==")
    with Run("ladder_slot_pre_b") as run:
        result = run.execute(ladder=["F1", "F2"])
        recorded = device_calls(calls(run.log))
        check(result.returncode != 0, "unexpected slot fails the ladder")
        check(not any(" flash " in line for line in recorded), "unexpected slot: nothing is written")
        check("the ladder stops here" in result.stdout, "unexpected slot names the stop reason")

    print("== ladder: the recipe label of each round reaches the log ==")
    with Run("ladder_fail_then_ok") as run:
        manifest = run.base / "ladder.json"
        import json
        data = json.loads(manifest.read_text())
        data["candidates"][0]["recipe"] = "empty-dtb"
        data["candidates"][1]["recipe"] = "merged-dtb"
        manifest.write_text(json.dumps(data))
        result = run.execute(ladder=["F1", "F2"])
        check("recipe: empty-dtb" in result.stdout, "round 1 recipe label is logged")
        check("recipe: merged-dtb" in result.stdout, "round 2 recipe label is logged")

    print()
    if FAILURES:
        print("%d check(s) failed" % len(FAILURES))
        return 1
    print("all host-simulation checks passed; no device was contacted")
    return 0


if __name__ == "__main__":
    sys.exit(main())