#!/usr/bin/env python3
"""Run a payload, collect logs and screenshots, then leave the loader idle again.

usage: tools/k90auto/run-auto.py RUN_DIR [SECONDS] [SHOT_EVERY,SHOT_FROM,LOG_EVERY]

RUN_DIR is what make-payload.py printed. Its manifest.json names the payload and the system image
the loader keeps resident; an image over 0xffffffff bytes also needs the window recorded there, and
is transferred by hackios-xnu-kernel/tools/stage-system.sh one 256 MiB block at a time.

The run always ends with the device back in a fresh idle loader. A kernel that held GPU resources
reaches hung-held, which keeps every page until a cold reset, so the teardown saves the log the
loader holds and reboots instead of leaving that state for the operator.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

WORKSPACE = Path(__file__).resolve().parents[2]
def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


base = Path(sys.argv[1])
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 240
shot_every, shot_from, log_every = (int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "3,100,20").split(","))
manifest = json.loads((base / "manifest.json").read_text())
# A failed pack leaves no new payload behind, and the queue used to run whatever directory it was
# handed: on 2026-10-28 make-payload.py stopped on an existing directory and the round ran the first
# version of the payload instead, with none of that round's changes in it. The run therefore starts
# only when both files still hash to what the manifest recorded, and when they also match what the
# operator says they should be. The two hashes go into the run log so a later reader can tell which
# payload a round actually booted without asking anyone.
payload_path = WORKSPACE / manifest["payload"]["path"]
ramdisk_path = WORKSPACE / manifest["ramdisk"]["path"]
for what, path, stated in (("payload", payload_path, manifest["payload"]["sha256"]),
                           ("packed root", ramdisk_path, manifest["ramdisk"]["sha256"])):
    if not path.is_file():
        raise SystemExit(f"refusing to run: the {what} {path} named by {base}/manifest.json is gone")
    actual = digest(path)
    if actual != stated:
        raise SystemExit(f"refusing to run: the {what} {path} hashes to {actual[:16]} but its manifest "
                         f"recorded {stated[:16]}; this directory does not describe the file in it")
expected = {"payload": manifest["payload"]["sha256"], "root": manifest["ramdisk"]["sha256"]}
for name, key in (("payload", "EXPECT_PAYLOAD_SHA256"), ("root", "EXPECT_ROOT_SHA256")):
    wanted = os.environ.get(key)
    if wanted and wanted != expected[name]:
        raise SystemExit(f"refusing to run: {key}={wanted[:16]} but this payload's {name} is "
                         f"{expected[name][:16]}; the pack that was meant to produce it did not")
print(f"GUARD payload={expected['payload'][:16]} root={expected['root'][:16]} dir={base.name}")
run = base / "run"
# A run directory is one run's record: files left by an earlier attempt would be read as this one's.
assert not run.exists() or not any(run.iterdir()), f"{run} is not empty"
run.mkdir(exist_ok=True)

# Runs recorded before make-payload.py wrote the system image carry the 16.5 one this tool checked.
system = manifest.get("system") or {"path": "hackios-xnu-kernel/userland/system.apfs",
                                    "sha256": "a3ab9dce59e527b65feb4ef161680f094087da26e79aabdddfa6e9ac9ee10b71",
                                    "bytes": 2492227584}
window = manifest.get("window")
system_image = WORKSPACE / system["path"]
CHUNKED_LIMIT = 0xffffffff
# The loader calls a kernel that stopped answering hung-held once it has been silent for its own
# SILENCE_SECONDS (50 in loader_02_platform_cpu_ufs_survey.inc); a stop is only answered before that.
# K90_STOP_WAIT shortens the wait, which the offline tests use.
STOP_WAIT_SECONDS = int(os.environ.get("K90_STOP_WAIT", "70"))


def call(args, cap=10, check=True):
    start = time.monotonic()
    try:
        result = subprocess.run(["fastboot", "-s", "xnuloader", *map(str, args)], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=cap)
        rc, output = result.returncode, result.stdout
    except subprocess.TimeoutExpired as error:
        rc, output = 124, str(error.stdout or "")
    record = {"args": list(map(str, args)), "rc": rc, "output": output, "host_monotonic": start,
              "seconds": time.monotonic() - start}
    with (run / "commands.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    if check:
        assert rc == 0 and "FAILED" not in output, record
    return record


def state():
    """The loader's own word for what it holds: idle, running, returned, hung-held, fault. A read
    that does not answer gives "unknown", so the teardown keeps going instead of dying on it."""
    return variable("result", check=False)


def fresh_loader():
    """Idle over an empty RAM disk: the state a run starts from, and the state a reset ends in."""
    output = call(["getvar", "ramdisk-state"], 8, False)["output"]
    return state() == "idle" and re.search(r"ramdisk-state:\s*idle 0 0 ", output) is not None


def variable(key, check=True):
    """One getvar's value. fastboot prints the bootloader's answer among its own progress lines,
    sometimes with a "(bootloader) " prefix, so the value is what follows the key on its line."""
    output = call(["getvar", key], 8, check)["output"]
    match = re.search(r"^(?:\(bootloader\)[ \t]*)?" + re.escape(key) + r":[ \t]*(\S*)", output, re.M)
    if match:
        return match.group(1)
    assert not check, f"loader did not report {key}: {output}"
    return "unknown"


payload = WORKSPACE / manifest["payload"]["path"]
# The cheap checks first: a loader that is not fresh idle, or an image whose window was never
# recorded, is worth refusing before two gigabytes are read to confirm a hash.
assert system_image.is_file() and system_image.stat().st_size == system["bytes"], system
if system["bytes"] > CHUNKED_LIMIT:
    assert window, "an image over 0xffffffff bytes needs the window recorded in manifest.json"
# The loader's build-id says which build is resident; a build without the RAM disk protocol would
# silently mis-stage, so the capability is what this checks and the identity is what it records.
loader_build_id = variable("build-id")
assert variable("ramdisk-protocol") == "1", "the loader does not offer the RAM disk protocol"
assert variable("result") == "idle", "the loader is not fresh idle"
assert digest(payload) == manifest["payload"]["sha256"], "payload does not match its manifest"
assert digest(system_image) == system["sha256"], "system image does not match its manifest"

if system["bytes"] > CHUNKED_LIMIT:
    stage = WORKSPACE / "hackios-xnu-kernel/tools/stage-system.sh"
    with (run / "system-upload.log").open("w") as log:
        subprocess.run(["bash", str(stage)], check=True,
                       env=dict(os.environ, STAGE_SYSTEM_IMAGE=str(system_image),
                                STAGE_SYSTEM_WINDOW=window),
                       stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    ready = call(["getvar", "ramdisk-state"])["output"]
    assert "ready" in ready and f'{system["bytes"]:x}' in ready.lower(), ready
else:
    call(["oem", "ramdisk"])
    call(["stage", system_image], 300)
call(["stage", payload], 25)
start = time.monotonic()
call(["oem", "run"])
print("RUN_STARTED", flush=True)


index = 0
failed = None
last_shot = -1e9
while time.monotonic() - start < duration:
    elapsed = time.monotonic() - start
    name = state()
    if name != "running":
        failed = {"state": name, "elapsed_seconds": elapsed}
        print("NOT_RUNNING", name, flush=True)
        break
    if elapsed >= log_every * index:
        if call(["oem", "log"], 8, False)["rc"] == 0:
            call(["get_staged", run / f"s{index:03d}.log"], 20, False)
        index += 1
    if elapsed >= shot_from and elapsed - last_shot >= shot_every:
        last_shot = elapsed
        if call(["oem", "screenshot"], 8, False)["rc"] == 0:
            call(["get_staged", run / f"shot-{int(elapsed * 10):05d}.raw"], 30, False)
    time.sleep(0.5)
print("SAMPLED_SECONDS", time.monotonic() - start, "failed_call", failed, flush=True)


def teardown():
    """Save the log the loader holds and reset, so the next run starts from an idle loader. Returns
    the state it left and whether it sent the reset.

    Every action re-reads the state. `oem stop` only asks: a kernel that held the GPU stops
    answering, and the loader reports hung-held once that kernel has been silent for its own 50 s,
    which is far longer than the stop takes to be acknowledged. A reboot is refused while a kernel
    is running, so a state that never leaves running is reported instead of reset."""
    stopped = False
    for _ in range(3):
        name = state()
        if name == "idle":
            return name, False
        if name == "running":
            if stopped:
                call(["oem", "log"], 8, False)
                call(["get_staged", run / "running.log"], 40, False)
                return name, False
            stopped = True
            call(["oem", "stop"], 20, False)
            deadline = time.monotonic() + STOP_WAIT_SECONDS
            while time.monotonic() < deadline and state() == "running":
                time.sleep(1)
            continue
        # The HUNG branch composed the kernel log into the staging area already; "oem log" would
        # compose the loader's own serial log over it (32,767 bytes, `log_buf`), which is how the
        # 2026-10-27 rounds lost the stop-side lines. Take that snapshot first and keep both.
        call(["get_staged", run / f"{name}.log"], 40, False)
        call(["oem", "log"], 8, False)
        call(["get_staged", run / f"{name}-serial.log"], 40, False)
        call(["reboot"], 10, False)
        return name, True
    return state(), False


left, reset = teardown()
off_seen, mode, seconds = False, "unknown", 0.0
if left == "idle":
    mode = "loader"               # nothing was reset, so the loader never went away
elif reset:
    watch = time.monotonic()
    while time.monotonic() - watch < 90:
        devices = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=3).stdout
        if "xnuloader" in devices:
            # A reset can finish between two polls, so the gap is recorded rather than required:
            # a loader that answers idle over an empty RAM disk is the fresh one the next run needs.
            if fresh_loader():
                mode = "loader"
                break
        else:
            off_seen = True
            android = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=3).stdout
            if "\tdevice" in android:
                mode = "android"
                break
        time.sleep(1)
    seconds = time.monotonic() - watch
summary = {"off_seen": off_seen, "mode": mode, "seconds": seconds, "left": left, "reset": reset,
           "failed": failed, "samples": index, "loader_build_id": loader_build_id, "window": window,
           "payload_sha256": manifest["payload"]["sha256"], "system_sha256": system["sha256"],
           "status": call(["getvar", "result"], 8, False)["output"] if mode == "loader" else None,
           # the daily evidence for "the device never stays somewhere only a person can leave it":
           # after every round the loader must still identify as xnuloader and answer idle.
           "product": call(["getvar", "product"], 8, False)["output"] if mode == "loader" else None}
(run / "reboot.json").write_text(json.dumps(summary, indent=2) + "\n")
print("REBOOT_END", summary, flush=True)
if failed is not None or mode not in ("loader", "android"):
    sys.exit(1)
if mode == "loader" and "result: idle" not in (summary["status"] or ""):
    sys.exit(1)
