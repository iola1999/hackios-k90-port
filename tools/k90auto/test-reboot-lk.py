#!/usr/bin/env python3
"""Run reboot-lk.py against a fastboot substitute; no USB commands reach a device."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
PAYLOAD = b"synthetic preparation payload"
SHA256 = hashlib.sha256(PAYLOAD).hexdigest()
GOOD_LOG = ("== XNULOADER run (usb) ==\n"
            "reboot-lk: apid=586 owner=0 capacity=128 original=0 target=0x4\n"
            "reboot-lk: prepared apid=586 owner=0 byte=0x4 reason=2; returning to loader for host reboot\n"
            "== END OF LOG ==\n")
FAKE = r'''
import json, os, pathlib, sys
state_path = pathlib.Path(os.environ["FAKE_STATE"])
state = json.loads(state_path.read_text()) if state_path.exists() else {}
config = json.loads(os.environ["FAKE_CONFIG"])
args = sys.argv[1:]
with pathlib.Path(os.environ["FAKE_HISTORY"]).open("a") as stream:
    stream.write(json.dumps(args) + "\n")
if args == ["devices"]:
    serial = "TEST-K90" if state.get("reboot") and not state.get("return_reboot") else "xnuloader"
    print(serial + "\tfastboot")
    sys.exit(0)
assert args[:2] in (["-s", "xnuloader"], ["-s", "TEST-K90"]), args
serial, command = args[1], args[2:]
if command[0] == "getvar":
    key = command[1]
    if key == "product":
        value = config.get("lk_product", "annibale") if serial == "TEST-K90" else "xnuloader"
    elif key == "build-id": value = "test-build"
    elif key == "ramdisk-protocol": value = config.get("protocol", "1")
    elif key == "ramdisk-state": value = config.get("ramdisk", "idle 0 0 300000000")
    elif key == "max-download-size": value = config.get("maximum", "0x03700000")
    elif key == "current-slot": value = config.get("activated_slot", "a") if state.get("active") else config.get("slot", "a")
    elif key == "slot-successful:b": value = config.get("b_successful", "yes")
    elif key == "slot-unbootable:b": value = config.get("b_unbootable", "no")
    elif key == "slot-retry-count:a": value = config.get("activated_retry", "7") if state.get("active") else "0"
    elif key == "slot-unbootable:a": value = config.get("activated_unbootable", "no") if state.get("active") else "yes"
    elif key == "result":
        value = config.get("state", "idle")
        if state.get("run"):
            value = config.get("returned", "returned 23070 0")
            if state.get("fetched"): value = config.get("final_state", value)
    else: raise AssertionError(key)
    if state.get("return_reboot"):
        option, default = {"product": ("return_product", "xnuloader"),
            "build-id": ("return_build", "test-build"), "ramdisk-protocol": ("return_protocol", "1"),
            "ramdisk-state": ("return_ramdisk", "idle 0 0 300000000"),
            "max-download-size": ("return_maximum", "0x03700000"),
            "result": ("return_state", "idle")}[key]
        value = config.get(option, default)
    print("(bootloader) " + key + ": " + value, file=sys.stderr)
elif command[0] == "stage":
    if config.get("stage_failed"):
        print("FAILED (remote: denied)", file=sys.stderr)
    else:
        assert pathlib.Path(command[1]).read_bytes() == b"synthetic preparation payload"
elif command == ["oem", "run"]: state["run"] = True
elif command[0] == "get_staged":
    assert state.get("run")
    pathlib.Path(command[1]).write_text(config["log"])
    state["fetched"] = True
elif command == ["set_active", "a"]:
    assert serial == "TEST-K90" and state.get("reboot")
    if config.get("activation_failed"):
        print("FAILED (remote: slot update failed)", file=sys.stderr)
    else: state["active"] = True
elif command == ["reboot"]:
    if serial == "xnuloader":
        assert state.get("fetched")
        state["reboot"] = True
    else:
        assert state.get("active")
        state["return_reboot"] = True
    if config.get("reboot_lost_reply") or serial == "TEST-K90" and config.get("return_lost_reply"):
        print("FAILED (USB disconnected)", file=sys.stderr)
else: raise AssertionError(command)
state_path.write_text(json.dumps(state))
'''


class RebootTests(unittest.TestCase):
    def invoke(self, config=None, digest=SHA256, explicit_serial=False, return_loader=False):
        config = {"log": GOOD_LOG, **(config or {})}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bins = root / "bin"
            bins.mkdir()
            fake = bins / "fastboot"
            fake.write_text(f"#!{sys.executable}\n" + FAKE)
            fake.chmod(0o755)
            payload = root / "payload.bin"
            payload.write_bytes(PAYLOAD)
            output = root / "run"
            history = root / "history.jsonl"
            env = dict(os.environ, PATH=str(bins) + os.pathsep + os.environ["PATH"],
                       ANDROID_SERIAL="TEST-K90", FAKE_STATE=str(root / "state.json"),
                       FAKE_HISTORY=str(history), FAKE_CONFIG=json.dumps(config))
            argv = [sys.executable, str(HERE / "reboot-lk.py"), str(output),
                    "--payload", str(payload), "--sha256", digest]
            if explicit_serial:
                env.pop("ANDROID_SERIAL")
                argv += ["--serial", "TEST-K90"]
            if return_loader:
                argv += ["--return-loader"]
            process = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            result = json.loads((output / "result.json").read_text())
            commands = [json.loads(line) for line in history.read_text().splitlines()] if history.exists() else []
            records = [json.loads(line) for line in (output / "commands.jsonl").read_text().splitlines()] if commands else []
            self.assertEqual(len(records), len(commands))
            for record in records:
                self.assertTrue({"argv", "rc", "stdout", "stderr", "seconds", "started_monotonic", "started_unix"} <= record.keys())
                self.assertGreaterEqual(record["seconds"], 0)
            return process, result, commands

    def refusal(self, config=None, digest=SHA256, before_stage=False):
        process, result, commands = self.invoke(config, digest)
        self.assertNotEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertFalse(result["reboot_sent"])
        self.assertFalse(result["lk_entered"])
        self.assertFalse(any(command[-1:] == ["reboot"] for command in commands))
        if before_stage:
            self.assertFalse(any(len(command) > 2 and command[2] == "stage" for command in commands))
        return commands

    def test_bad_hash_sends_no_commands(self):
        self.assertEqual(self.refusal(digest="0" * 64, before_stage=True), [])

    def test_unusable_loader_states_stop_before_stage(self):
        for state in ("running 0 0", "returned-held 20 0", "hung-held 20 0", "firmware-fault", "reset-failed 1 0", "checkpoint 1 0"):
            with self.subTest(state=state):
                self.refusal({"state": state}, before_stage=True)

    def test_resident_data_or_pending_transfer_is_preserved(self):
        for state in ("ready 10 10 300000000", "receiving 0 10 300000000", "failed 0 10 300000000", "idle 0 1 300000000"):
            with self.subTest(state=state):
                commands = self.refusal({"ramdisk": state}, before_stage=True)
                self.assertFalse(any("ramdisk" in command for command in commands))

    def test_old_armed_download_target_is_rejected(self):
        self.refusal({"maximum": "0xffffffff"}, before_stage=True)

    def test_unknown_resident_protocol_is_rejected(self):
        self.refusal({"protocol": ""}, before_stage=True)

    def test_failed_stage_stops_even_with_zero_exit_status(self):
        commands = self.refusal({"stage_failed": True})
        self.assertFalse(any(command[-2:] == ["oem", "run"] for command in commands))

    def test_failed_probe_return_never_reboots(self):
        self.refusal({"returned": "returned-held 23070 0"})

    def test_missing_invalid_or_conflicting_markers_never_reboot(self):
        marker = GOOD_LOG.splitlines()[2]
        variants = [GOOD_LOG.replace(marker, ""), GOOD_LOG.replace("owner=0 byte=", "owner=1 byte="),
                    GOOD_LOG.replace("byte=0x4", "byte=0x6"), GOOD_LOG.replace("target=0x4", "target=0x5"),
                    GOOD_LOG.replace("apid=586 owner=0 byte", "apid=587 owner=0 byte"),
                    GOOD_LOG + "reboot-lk: preparation failed: transfer failed\n", GOOD_LOG[:-20],
                    GOOD_LOG.replace(marker, marker + "\n" + marker.replace("owner=0", "owner=1"))]
        for log in variants:
            with self.subTest(log=log):
                self.refusal({"log": log})

    def test_state_changed_after_fetch_prevents_reboot(self):
        self.refusal({"final_state": "returned-held 23070 0"})

    def test_success_stops_at_identified_lk(self):
        for state in ("idle", "returned 23312 0"):
            with self.subTest(state=state):
                process, result, commands = self.invoke({"state": state}, explicit_serial=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertTrue(result["lk_entered"])
                self.assertEqual(result["current_slot"], "a")
                self.assertEqual(sum(command[-1:] == ["reboot"] for command in commands), 1)
                self.assertEqual(commands[-1], ["-s", "TEST-K90", "getvar", "current-slot"])
                self.assertFalse(any("set_active" in command or "ramdisk" in command for command in commands))

    def test_duplicate_log_lines_and_preserved_bit_zero_are_valid(self):
        marker = GOOD_LOG.splitlines()[2]
        log = GOOD_LOG.replace(marker, marker + "\n" + marker).replace("original=0 ", "original=0x1 ")
        log = log.replace("target=0x4", "target=0x5").replace("byte=0x4", "byte=0x5")
        process, result, _ = self.invoke({"log": log})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(result["prepared"]["byte"], 5)

    def test_usb_reset_reply_failure_can_be_verified_at_lk(self):
        process, result, _ = self.invoke({"reboot_lost_reply": True})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse(result["reboot_command_ok"])
        self.assertTrue(result["lk_entered"])

    def test_wrong_destination_product_fails_identification(self):
        process, result, _ = self.invoke({"lk_product": "other"})
        self.assertNotEqual(process.returncode, 0)
        self.assertTrue(result["reboot_sent"])
        self.assertFalse(result["lk_entered"])

    def test_roundtrip_restores_exhausted_a_and_verifies_fresh_loader(self):
        for config in ({}, {"slot": "b", "reboot_lost_reply": True}, {"return_lost_reply": True}):
            with self.subTest(config=config):
                process, result, commands = self.invoke(config, return_loader=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertTrue(result["loader_returned"])
                self.assertEqual(result["slots_before_return"]["slot-retry-count:a"], "0")
                self.assertEqual(result["slots_after_selection"]["slot-retry-count:a"], "7")
                self.assertEqual(commands.count(["-s", "TEST-K90", "set_active", "a"]), 1)
                self.assertEqual(sum(c[-1:] == ["reboot"] for c in commands), 2)
                self.assertFalse(any("flash" in c for c in commands))
                self.assertEqual(commands[-1], ["-s", "xnuloader", "getvar", "max-download-size"])

    def test_return_option_preserves_preparation_guards(self):
        for config, digest in (({}, "0" * 64), ({"state": "returned-held 20 0"}, SHA256),
                               ({"ramdisk": "ready 10 10 300000000"}, SHA256), ({"log": "incomplete"}, SHA256)):
            with self.subTest(config=config):
                process, result, commands = self.invoke(config, digest, return_loader=True)
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(result["reboot_sent"])
                self.assertFalse(any(c[-1:] == ["reboot"] or "set_active" in c for c in commands))

    def test_unverified_b_prevents_slot_change(self):
        for config in ({"b_successful": "no"}, {"b_unbootable": "yes"}, {"b_successful": ""}):
            with self.subTest(config=config):
                process, result, commands = self.invoke(config, return_loader=True)
                self.assertNotEqual(process.returncode, 0)
                self.assertTrue(result["lk_entered"])
                self.assertFalse(result["return_reboot_sent"])
                self.assertFalse(any("set_active" in c for c in commands))

    def test_failed_activation_or_readback_prevents_return_reboot(self):
        for config in ({"activation_failed": True}, {"activated_retry": "0"},
                       {"activated_slot": "b"}, {"activated_unbootable": "yes"}):
            with self.subTest(config=config):
                process, result, commands = self.invoke(config, return_loader=True)
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(result["return_reboot_sent"])
                self.assertEqual(sum(c[-1:] == ["reboot"] for c in commands), 1)

    def test_returned_loader_must_match_and_be_fresh_empty(self):
        for config in ({"return_product": "other"}, {"return_build": "other-build"},
                       {"return_protocol": "2"}, {"return_ramdisk": "ready 1 1 300000000"},
                       {"return_state": "returned 100 0"}, {"return_state": "returned-held 100 0"},
                       {"return_maximum": "0xffffffff"}):
            with self.subTest(config=config):
                process, result, commands = self.invoke(config, return_loader=True)
                self.assertNotEqual(process.returncode, 0)
                self.assertTrue(result["return_reboot_sent"])
                self.assertFalse(result["loader_returned"])
                self.assertEqual(sum(c[-1:] == ["reboot"] for c in commands), 2)

    def test_timeout_records_both_partial_streams(self):
        spec = importlib.util.spec_from_file_location("reboot_lk", HERE / "reboot-lk.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = base / "payload.bin"
            payload.write_bytes(PAYLOAD)
            args = SimpleNamespace(payload=payload, sha256=SHA256, serial="TEST-K90")
            error = subprocess.TimeoutExpired(["fastboot", "devices"], 8,
                                               output=b"partial stdout", stderr=b"partial stderr")
            result = {"reboot_sent": False}
            with patch.object(module.subprocess, "run", side_effect=error):
                with self.assertRaises(RuntimeError):
                    module.workflow(args, base, result)
            record = json.loads((base / "commands.jsonl").read_text())
            self.assertEqual(record["rc"], 124)
            self.assertEqual(record["stdout"], "partial stdout")
            self.assertEqual(record["stderr"], "partial stderr")
            self.assertFalse(result["reboot_sent"])


if __name__ == "__main__":
    unittest.main()
