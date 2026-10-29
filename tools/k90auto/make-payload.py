#!/usr/bin/env python3
"""Make a desktop payload (kernel + root image + boot-args) for an unattended run.

usage: tools/k90auto/make-payload.py NAME LABEL RAMDISK "EXTRA BOOT-ARGS"

NAME is a kernel built by build-kernel.py; RAMDISK a root image under hackios-xnu-kernel/ (for an
unattended run one whose etc/rc.jobs is rc.jobs.desktop); EXTRA BOOT-ARGS are added after the fixed
ones (GPU stage 23 with the secure handover, two prime cores, the Goodix touch screen, the volume and
power keys, the battery gauge). Prints the run directory to give run-queue.sh. Run from the top of
the workspace.

env: K90_EVIDENCE (default docs/progress/evidence/k90auto), CPU_ARGS (default
"cpus=2 bootcpu=7 small_cores_after=0"), GPU_SPEED (adreno8_speed, default 3: up to 342 MHz with load;
kernels before 34209c1 need 1), SYSTEM (workspace-relative system image the loader keeps resident,
default hackios-xnu-kernel/userland/system.apfs), SYSTEM_WINDOW (hex window bytes; required for an
image over 0xffffffff bytes, which run-auto.py then transfers by the chunked protocol),
MEMSIZE and IDENTITY (passed to mkpayload.py as --memsize and --identity; iOS 26 needs
300000000 and v57, and 16.5 leaves both to mkpayload.py's defaults).
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import time
# The system image bounds live beside this script so the replay test exercises the same code.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import system_guard

name, label, ramdisk_arg, extra = sys.argv[1:5]
assert re.fullmatch(r"[a-z0-9-]+", label) and re.fullmatch(r"[A-Za-z0-9_=.,: -]*", extra)
evidence = Path(os.environ.get("K90_EVIDENCE", "docs/progress/evidence/k90auto"))
record = json.loads((evidence / ("kernel-" + name) / "kernel.json").read_text())
base = evidence / f"kernel-{name}-{label}"
# The round directory is what keeps two packs with the same label from sharing a record, so the
# collision is checked here. Creating it here instead left an empty directory behind whenever an
# assertion below fired (hit on 2026-10-28); it is created when the record is ready to write.
assert not base.exists(), f"{base} already exists: this label has a round record"
root = Path("hackios-xnu-kernel")
kernel = Path(record["kernel"]["path"])
ramdisk = root / ramdisk_arg
payload = root / f"out/handoff-{name}-{label}.bin"
def digest(path):
    """Chunked: the system image is gigabytes and does not fit in memory."""
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


assert digest(kernel) == record["kernel"]["sha256"]
system_image = Path(os.environ.get("SYSTEM", system_guard.DEFAULT_SYSTEM))
window = os.environ.get("SYSTEM_WINDOW", "")
assert system_image.is_file(), system_image
if window:
    assert re.fullmatch(r"0x[0-9a-fA-F]+", window) and int(window, 16) % (32 << 20) == 0, window
system_bytes = system_image.stat().st_size
system_error = system_guard.identity_error(system_image, system_bytes,
                                           os.environ.get("SYSTEM"), window)
assert system_error is None, system_error
cpu_args = os.environ.get("CPU_ARGS", "cpus=2 bootcpu=7 small_cores_after=0")
gpu_speed = int(os.environ.get("GPU_SPEED", "3"))
memsize = os.environ.get("MEMSIZE", "")       # iOS 26 needs the RAM it is staged into: 300000000
identity = os.environ.get("IDENTITY", "")     # and the loader identity of that iOS: v57
# rootdev=md0 and launchd_unsecure_cache=1 belong to the fixed set: iOS 26's launchd takes its jobs
# and its 733 AppExtensions records from /System/Library/xpc/launchd.plist, and launchd_cache_loader
# hands that cache over only with this boot-arg (it otherwise has to verify Apple's signature). Without
# them launchd prints "Skipping boot-task" instead of "Using unsecure cache" and no extension record
# ever reaches it. Every run before this harness carried them; the desktop of 2026-10-27 12:40 on the
# same root image (15 icons, two named widgets, four Dock icons) is one of those runs.
cmdline = (f"debug=0x10e rootdev=md0 launchd_unsecure_cache=1 {cpu_args} epoch={int(time.time())} adreno8=23 adreno8_pause=0 adreno8_fine=0 adreno8_watch=0 "
           f"adreno8_keep=1 adreno8_return=0 adreno8_speed={gpu_speed} adreno8_secure_preflight=4 touchscreen=2 buttons=1 battery=1 "
           f"{extra}").strip()
# Fail here rather than discover it 400 seconds into a run: a payload that boots into a desktop with
# two icons looks exactly like a registration problem, and it took two days to see that the cache
# never arrived. REQUIRED is recorded in the manifest so a later diff shows whether a run had them.
REQUIRED = ("rootdev=md0", "launchd_unsecure_cache=1", f"adreno8_speed={gpu_speed}")
absent = [arg for arg in REQUIRED if arg not in cmdline.split()]
assert not absent, f"boot-args lost {absent}: iOS 26's launchd will run with no cache and no AppExtensions"
argv = ["python3", "xnuloader/mkpayload.py", "-o", str(payload.relative_to(root)),
        "kernel=" + str(kernel.relative_to(root)), "ramdisk=" + str(ramdisk.relative_to(root)),
        "--cmdline", cmdline, "--exact-cmd", cmdline, "--require", "kernel=" + digest(kernel),
        "--require", "ramdisk=" + digest(ramdisk), "--forbid-cmd", "loader_return_after"]
if memsize:
    assert re.fullmatch(r"[0-9a-fA-F]+", memsize), memsize      # mkpayload.py reads hex bytes
    argv += ["--memsize", memsize]
if identity:
    assert re.fullmatch(r"[a-z0-9]+", identity), identity
    argv += ["--identity", identity]
subprocess.run(argv, cwd=root, check=True)
# The pack manifest beside the packed root says what that pack put in: whether the probe and the
# var_store line were added, which skeleton lines had to be appended because the base root was older
# than userland/var.skel.extra, and which driver the round will run. Without copying it here the round
# record answers "which files were uploaded" but not "what was in them", and the only copy lives in
# out/, which the next pack overwrites.
pack_manifest = ramdisk.parent / "manifest.json"
assert pack_manifest.is_file(), f"{pack_manifest} is missing: without it a round cannot say what it ran"
pack_record = json.loads(pack_manifest.read_text())
# The whole record, not a chosen list. A list was here until 2026-10-28 and it silently dropped every
# field added to the pack after the list was written: the freeze round ran the current package.py,
# which writes jobs_source, probe_sources, air_sources and jobs_effective_count, and the round record
# carried none of them. Copying the record keeps a future field from needing a second edit here.
pack = dict(pack_record)
assert pack["root_sha256"] == digest(ramdisk), (
    f"the pack beside {ramdisk} records root {str(pack['root_sha256'])[:16]} but the file hashes to "
    f"{digest(ramdisk)[:16]}: this root is not the one that pack made")
# Patches that did not apply, written by mk-mesa.sh beside the build. Copied verbatim: the parsing
# that decides what is a patch belongs to the script that applies them, and a round that lists its
# rejected patches can be read the same way a month later.
patch_rejects = ""
patch_rejects_file = Path(__file__).resolve().parent.parent.parent / "out/patch-rejects.txt"
if patch_rejects_file.is_file():
    patch_rejects = patch_rejects_file.read_text()

if pack["gpu_speed"] is not None:
    assert int(pack["gpu_speed"]) == gpu_speed, (
        f"the pack ran adreno8_speed={pack['gpu_speed']} but this payload boots adreno8_speed={gpu_speed}")
record.update({"ramdisk": {"path": str(ramdisk), "bytes": ramdisk.stat().st_size, "sha256": digest(ramdisk)},
               "cmdline": cmdline, "boot_cmdline": cmdline, "gpu_speed": gpu_speed,
               "cpu_args": cpu_args, "extra_boot_args": extra, "argv": argv,
               "required_cmdline": list(REQUIRED),
               "system": {"path": str(system_image), "bytes": system_bytes,
                          "sha256": digest(system_image)},
               "payload": {"path": str(payload), "bytes": payload.stat().st_size, "sha256": digest(payload)},
               "pack": pack, "patch_rejects": patch_rejects})
if window:
    record["window"] = window
base.mkdir()
(base / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
print(base)
# The GPU speed is the one setting whose default (3) differs from what almost every earlier round
# used (1), so a round that forgets GPU_SPEED silently runs a different clock than the one it is being
# compared with. Printing it with the directory makes the real value part of what the operator pastes
# back, and the manifest keeps it next to the full cmdline.
print(f"gpu_speed={gpu_speed}")
