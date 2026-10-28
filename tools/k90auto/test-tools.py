#!/usr/bin/env python3
"""Offline checks for frame statistics, the unattended queue, and the runner's teardown."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("summary", HERE / "summary.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)

# The loader as run-auto.py meets it: one state, changed only by the commands the runner sends.
# FB_AFTER_STOP is what `oem stop` leaves behind -- hung-held is what a kernel that held the GPU
# reaches, and the sample taken before the stop still says running.
FAKE_FASTBOOT = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args[:2] == ["-s", "xnuloader"]:
    args = args[2:]
with pathlib.Path(os.environ["FB_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\n")
state_path = pathlib.Path(os.environ["FB_STATE"])
state = state_path.read_text().strip()


def say(text):
    # fastboot prints its own progress line after the bootloader's answer; a parser that takes
    # everything after the key would read that too.
    sys.stdout.write(text + "\nFinished. Total time: 0.000s\n")


if args == ["devices"]:
    seen_path = pathlib.Path(os.environ["FB_DEVICES"])
    seen = int(seen_path.read_text()) if seen_path.exists() else 0
    seen_path.write_text(str(seen + 1))
    say("" if (not os.environ.get("FB_NO_GAP") and seen == 0) else "xnuloader\tfastboot")
elif args[:1] == ["getvar"]:
    key = args[1]
    if key == "result":
        pending = state_path.with_name("stop-reads")
        if state == "running" and pending.exists():
            left = int(pending.read_text()) - 1
            if left > 0:
                pending.write_text(str(left))
            else:
                pending.unlink()
                state = os.environ["FB_AFTER_STOP"]
                state_path.write_text(state)
        drop_after = int(os.environ.get("FB_DROP_AFTER", "0"))
        if drop_after and state == "running":
            reads_path = state_path.with_name("result-reads")
            reads = int(reads_path.read_text()) if reads_path.exists() else 0
            reads_path.write_text(str(reads + 1))
            if reads >= drop_after:
                state = os.environ.get("FB_DROP_TO", "returned")
                state_path.write_text(state)
        say("result: " + state)
    elif key == "build-id":
        say("build-id: " + os.environ.get("FB_BUILD_ID", "unknown"))
    elif key == "ramdisk-protocol":
        say("ramdisk-protocol: 1")
    elif key == "ramdisk-state":
        say("ramdisk-state: " + pathlib.Path(os.environ["FB_RAMDISK"]).read_text().strip())
    else:
        say(key + ": ")
elif args[:2] == ["oem", "run"]:
    state_path.write_text("running")
elif args[:2] == ["oem", "stop"]:
    # The loader only asks the kernel to stop. One that held the GPU stops answering, and the loader
    # reports hung-held after its own silence window, which FB_STOP_AFTER_READS stands in for.
    delay = int(os.environ.get("FB_STOP_AFTER_READS", "0"))
    if delay:
        state_path.with_name("stop-reads").write_text(str(delay))
    else:
        state_path.write_text(os.environ["FB_AFTER_STOP"])
elif args[:2] == ["oem", "ramdisk"] and len(args) == 5:
    pathlib.Path(os.environ["FB_RAMDISK"]).write_text("ready %s %s" % (args[3], args[4]))
elif args[:1] == ["reboot"]:
    state_path.write_text(os.environ.get("FB_AFTER_REBOOT", "idle"))
    pathlib.Path(os.environ["FB_RAMDISK"]).write_text("idle 0 0 0")
elif args[:1] == ["get_staged"]:
    pathlib.Path(args[1]).write_text("console log\n")
else:
    say("OKAY")
'''

FAKE_STAGE = r'''#!/usr/bin/env bash
set -euo pipefail
: "${STAGE_SYSTEM_IMAGE:?}" "${STAGE_SYSTEM_WINDOW:?}"
echo "$STAGE_SYSTEM_IMAGE $STAGE_SYSTEM_WINDOW" >> "$FB_STAGE_LOG"
size=$(stat -f %z "$STAGE_SYSTEM_IMAGE")
fastboot -s xnuloader oem ramdisk begin "$(printf %x "$size")" "$STAGE_SYSTEM_WINDOW"
'''


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


class ToolsTests(unittest.TestCase):
    def test_frame_buckets_exclude_gpu_wait_and_include_under_10_ms(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "sample"
            run = base / "run"
            run.mkdir(parents=True)
            (base / "manifest.json").write_text(json.dumps({"commit": "test", "cmdline": ""}))
            (run / "s000.log").write_text(
                "MiniIOMobileFramebuffer: 100 frames in 5000 ms (20 a second), 2000 us each in the driver, "
                "after 999999 us waiting for the GPU\n"
                "MiniIOMobileFramebuffer: from one frame to the next: 10 times under 10 ms, 20 under 18, "
                "30 under 26, 25 under 35, 15 longer (the longest 40 ms); half under 17 ms, "
                "95 in 100 under 18 ms; 0 pauses\n")
            result = summary.summarize(str(base))
            self.assertEqual(result["under18"], 30)
            self.assertEqual(result["mid"], 55)
            self.assertEqual(result["long"], 15)
            self.assertEqual(result["long_count"], 15)

    def test_summary_merges_overlapping_snapshots(self):
        """The harness pulls the loader's ring repeatedly, so a window the ring later dropped has to be
        read from the snapshot that still had it, and the overlapping part counted once."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "sample"
            run = base / "run"
            run.mkdir(parents=True)
            (base / "manifest.json").write_text(json.dumps({"commit": "test", "cmdline": ""}))
            window = ("MiniIOMobileFramebuffer: 100 frames in 5000 ms (20 a second), 2000 us each in the driver, "
                      "after 0 us waiting for the GPU and, 90 of them, 8000 us for the next refresh; 0 swaps "
                      "waited for the frame before, 0 gave up; 3 swaps came a refresh late themselves\n"
                      "MiniIOMobileFramebuffer: from one frame to the next: 10 times under 10 ms, "
                      "20 under 18, 30 under 26, 25 under 35, 15 longer (the longest 86 ms); half under 17 ms, "
                      "95 in 100 under 18 ms; 0 pauses\n")
            filler = "".join(f"cpufreq: domain 1 in 30 s: 1017 MHz 100%; filler line {k}\n" for k in range(400))
            (run / "s000.log").write_text(window + filler)
            (run / "s001.log").write_text(filler + window.replace("100 frames in 5000 ms (20 a second)",
                                                                  "120 frames in 5000 ms (24 a second)"))
            result = summary.summarize(str(base))
            self.assertEqual(result["long_count"], 30)
            self.assertEqual(result["fps"], 22.0)
            self.assertEqual(result["under18"], 30)

    def run_queue(self, failed):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bins = root / "bin"
            bins.mkdir()
            marker = root / "runs"
            python = bins / "python3"
            python.write_text('#!/bin/bash\necho "$2" >> "$QUEUE_MARKER"\nexit "${QUEUE_EXIT:-0}"\n')
            fastboot = bins / "fastboot"
            fastboot.write_text('#!/bin/bash\necho "result: idle" >&2\n')
            for tool in (python, fastboot):
                tool.chmod(0o755)
            env = dict(os.environ, PATH=str(bins) + os.pathsep + os.environ["PATH"],
                       QUEUE_MARKER=str(marker), QUEUE_EXIT=str(7 if failed else 0))
            result = subprocess.run(["bash", str(HERE / "run-queue.sh"), str(root / "first"), str(root / "second")],
                                    env=env, capture_output=True, text=True)
            return result, marker.read_text().splitlines()

    def test_failed_run_stops_queue_even_if_loader_is_idle(self):
        result, runs = self.run_queue(True)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(len(runs), 1)

    def test_successful_runs_continue(self):
        result, runs = self.run_queue(False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(runs), 2)


class RunAutoTests(unittest.TestCase):
    """run-auto.py against a loader stand-in: what the teardown leaves behind, and what it stages."""

    GIG = 0x100000000           # one byte over the largest single-shot download

    def prepare(self, root, system_bytes, window, system_sha256=None):
        for path in ("tools/k90auto", "bin", "hackios-xnu-kernel/tools", "hackios-xnu-kernel/out",
                     "hackios-xnu-kernel/userland", "run-dir"):
            (root / path).mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / "run-auto.py", root / "tools/k90auto/run-auto.py")
        (root / "hackios-xnu-kernel/tools/stage-system.sh").write_text(FAKE_STAGE)
        for name, body in (("fastboot", FAKE_FASTBOOT), ("adb", "#!/bin/bash\nexit 0\n")):
            (root / "bin" / name).write_text(body)
            (root / "bin" / name).chmod(0o755)
        payload = root / "hackios-xnu-kernel/out/payload.bin"
        payload.write_bytes(b"XNUP" + bytes(60))
        image = root / "hackios-xnu-kernel/userland/system.apfs"
        with image.open("wb") as stream:
            stream.truncate(system_bytes)         # sparse: a 4 GiB image costs no disk
        record = {"payload": {"path": "hackios-xnu-kernel/out/payload.bin", "sha256": digest(payload)},
                  "system": {"path": "hackios-xnu-kernel/userland/system.apfs", "bytes": system_bytes,
                             "sha256": system_sha256 or digest(image)}}
        if window:
            record["window"] = window
        (root / "run-dir/manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        return root / "run-dir"

    def invoke(self, root, base, **extra):
        (root / "state").write_text("idle")
        (root / "ramdisk").write_text("idle 0 0 0")
        env = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ["PATH"],
                   FB_LOG=str(root / "fastboot.jsonl"), FB_STATE=str(root / "state"),
                   FB_RAMDISK=str(root / "ramdisk"), FB_DEVICES=str(root / "devices"),
                   FB_STAGE_LOG=str(root / "stage.log"), FB_AFTER_STOP="hung-held", K90_STOP_WAIT="6")
        env.update({k: str(v) for k, v in extra.items()})
        return subprocess.run([sys.executable, str(root / "tools/k90auto/run-auto.py"), str(base), "1"],
                              env=env, capture_output=True, text=True, cwd=root, timeout=180)

    def sent(self, root):
        log = root / "fastboot.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def teardown_case(self, **extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.prepare(root, 4096, None)
            result = self.invoke(root, base, **extra)
            summary = json.loads((base / "run/reboot.json").read_text())
            return result, summary, self.sent(root), sorted(p.name for p in (base / "run").iterdir())

    def test_stop_into_hung_held_saves_the_log_and_resets(self):
        """The incident this teardown exists for: the sample before `oem stop` says running, and the
        kernel that held the GPU is only hung-held afterwards, so it needs a host reset."""
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="hung-held")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(summary["left"], "hung-held")
        self.assertIn("hung-held.log", files)
        self.assertIn(["oem", "log"], sent)
        self.assertIn(["reboot"], sent)
        self.assertEqual([summary["mode"], summary["off_seen"]], ["loader", True])
        self.assertIn("result: idle", summary["status"])

    def test_stop_into_returned_saves_the_log_and_resets(self):
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="returned")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(summary["left"], "returned")
        self.assertIn("returned.log", files)
        self.assertIn(["reboot"], sent)

    def test_kernel_that_leaves_running_mid_run_stops_the_queue(self):
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="returned", FB_DROP_AFTER="1",
                                                          FB_DROP_TO="returned")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(summary["failed"]["state"], "returned")
        self.assertIn("returned.log", files)
        self.assertIn(["reboot"], sent)

    def test_an_idle_loader_is_left_alone(self):
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="idle")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([summary["left"], summary["mode"], summary["off_seen"]], ["idle", "loader", False])
        self.assertNotIn(["reboot"], sent)
        self.assertIn("result: idle", summary["status"])

    def test_hung_held_appears_only_after_the_loaders_silence_window(self):
        """What the device did: three `oem stop` acknowledgements, still running, and hung-held only
        once the loader's own 50 s of silence had passed. A teardown that samples once misses it."""
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="hung-held", FB_STOP_AFTER_READS="2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([summary["left"], summary["reset"], summary["mode"]], ["hung-held", True, "loader"])
        self.assertIn("hung-held.log", files)
        self.assertEqual(sent.count(["oem", "stop"]), 1)
        self.assertIn(["reboot"], sent)

    def test_a_stop_the_kernel_never_answers_is_reported_not_reset(self):
        """The loader refuses a reboot while a kernel runs, so this is reported and left for a host
        reset rather than answered with a command that cannot succeed."""
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="hung-held", FB_STOP_AFTER_READS="999")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual([summary["left"], summary["reset"], summary["mode"]], ["running", False, "unknown"])
        self.assertIn("running.log", files)
        self.assertNotIn(["reboot"], sent)

    def test_a_reset_too_fast_to_see_the_gap_still_counts(self):
        """The device re-enumerates inside one poll, so requiring a disconnect would fail a run that
        recovered; a loader that answers idle over an empty RAM disk is the fresh one."""
        result, summary, sent, files = self.teardown_case(FB_AFTER_STOP="returned", FB_NO_GAP="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([summary["left"], summary["mode"], summary["off_seen"]], ["returned", "loader", False])
        self.assertIn("result: idle", summary["status"])

    def test_a_big_image_without_a_window_is_refused_before_anything_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # The hash is wrong on purpose: refusing on the window proves the image was never read.
            base = self.prepare(root, self.GIG, None, system_sha256="0" * 64)
            result = self.invoke(root, base)
            sent = self.sent(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs the window recorded", result.stderr)
        self.assertEqual(sent, [])

    def test_a_big_image_goes_by_the_chunked_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.prepare(root, self.GIG, "0x180000000")
            result = self.invoke(root, base, FB_AFTER_STOP="idle")
            staged = (root / "stage.log").read_text().split()
            sent = self.sent(root)
            summary = json.loads((base / "run/reboot.json").read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(staged[1], "0x180000000")
        self.assertIn(["oem", "ramdisk", "begin", "100000000", "0x180000000"], sent)
        self.assertNotIn(["oem", "ramdisk"], sent)
        self.assertEqual(summary["window"], "0x180000000")


if __name__ == "__main__":
    unittest.main()
