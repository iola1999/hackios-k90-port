#!/usr/bin/env python3
"""One unattended desktop round from the working tree: pack, boot, tour, render report.

usage: tools/k90auto/cycle.py LABEL [--baseline ROUND_DIR] [--seconds N] [--kernel NAME] [--seed FILE] [--hold] [--tour STEP ...]

--seed FILE (default: the K90_SEED environment variable, if set) boots with a /private/var archive
unpacked over the skeleton: package.py packs it as etc/var.seed and the round gets var_store=1. The
archive comes from `var_store save FILE` and tools/k90auto/varseed.py; it stays in a local, ignored
directory (docs/analysis/2026-10-31-every-boot-is-first-boot.md).

  1. package.py with the interactive jobs and rwsh (the caller's environment goes through, so
     ICON_METAL=1 and the other package switches work as they do there), then make-payload.py
     for kernel NAME (default 12377-cmd1) with four cores.
  2. The loader has to be enumerated and idle with an empty RAM disk; otherwise this stops. Every
     CHECKPOINT_EVERY rounds the A slot's retry count is reset at LK (reboot-lk.py, set_active a;
     LK is addressed by ANDROID_SERIAL).
  3. round-run.py in the background; once SpringBoard reports the boot unlock, tour.py runs TOUR or --tour
     (only its first step when the GPU has already stopped), and the round is asked to stop
     (run/stop-request) instead of running out its N seconds. With --hold it is not asked: it runs
     until respin.py --stop or the N seconds, and respin.py changes settings and restarts processes
     in it meanwhile.
  4. render-health.py, against --baseline when given, into ROUND_DIR/render-report.txt.

Exit code: 0 when the round ran and the loader came back idle, 1 otherwise. The device rules of
AGENTS.md section 5 hold: nothing here reboots a device that is not an enumerated, idle loader.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
EVIDENCE = WORKSPACE / "docs/progress/evidence/k90auto"
STATE = EVIDENCE / "cycle-state.json"
CHECKPOINT_EVERY = 2
UNLOCK_LINE = "sb26: boot unlock done"
GPU_STOP = "submissions closed"   # after this the compositor draws in software, so the tour is cut short
UNLOCK_WAIT = 420           # upload (about 120 s) plus boot to the home screen
SETTINGS_ICON = (0.616, 0.70)
TOUR = [
    "home@3*2",
    "icons-layers=notify com.redwood.layers.Icon@4*0",
    "wallpaper-layers=notify com.redwood.layers.Wallpaper@4*0",
    "statusbar-layers=notify com.redwood.layers.StatusBar@4*0",
    f"settings=/redwood/bin/rwtouch tap {SETTINGS_ICON[0]} {SETTINGS_ICON[1]}@4*2",
    "settings-scrolled=/redwood/bin/rwtouch swipe 0.5 0.7 0.5 0.35 300@3*2",
    "home-again=/redwood/bin/rwtouch swipe 0.5 0.995 0.5 0.55 200@4*1",
    "control-center=/redwood/bin/rwtouch swipe 0.9 0.005 0.9 0.6 300@3*2",
    "cc-closed=/redwood/bin/rwtouch swipe 0.5 0.995 0.5 0.55 200@3*1",
    "notifications=/redwood/bin/rwtouch swipe 0.3 0.005 0.3 0.7 300@3*1",
    "nc-closed=/redwood/bin/rwtouch swipe 0.5 0.995 0.5 0.55 200@3*1",
]


def run(args, **kw):
    print("+", " ".join(str(a) for a in args), flush=True)
    return subprocess.run([str(a) for a in args], cwd=WORKSPACE, **kw)


def fastboot(*args, serial="xnuloader", timeout=20):
    result = subprocess.run(["fastboot", "-s", serial, *args], capture_output=True, text=True,
                            timeout=timeout)
    return result.stdout + result.stderr


def loader_ready():
    devices = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5).stdout
    if "xnuloader" not in devices:
        return "no xnuloader in fastboot devices"
    if "result: idle" not in fastboot("getvar", "result"):
        return "loader result is not idle"
    if "ramdisk-state: idle 0 0 0" not in fastboot("getvar", "ramdisk-state"):
        return "loader RAM disk is not empty"
    return None


def checkpoint():
    """LK step of the reset: through reboot-lk.py to LK, set_active a, reboot to the loader."""
    serial = os.environ.get("ANDROID_SERIAL")
    if not serial:
        return "ANDROID_SERIAL is not set, and LK is addressed by it"
    out = EVIDENCE / f"reboot-lk-cycle-{int(time.time())}"
    prepare = WORKSPACE / "hackios-xnu-kernel/out/ios26-resume/reboot-lk-prepare/annibale-reboot-lk-prepare.bin"
    sha = "6b81e800ae789cf30adbaaa9c98768012e264c66a4e56110c6449cecf93fb7d7"
    if run([sys.executable, HERE / "reboot-lk.py", out, "--payload", prepare, "--sha256", sha,
            "--serial", serial], capture_output=True, text=True).returncode != 0:
        return "reboot-lk.py failed"
    fastboot("set_active", "a", serial=serial)
    if "slot-retry-count:a: 7" not in fastboot("getvar", "slot-retry-count:a", serial=serial):
        return "slot A retry count did not reset to 7"
    fastboot("reboot", serial=serial)
    for _ in range(60):
        time.sleep(1)
        if loader_ready() is None:
            return None
    return "the loader did not come back after the checkpoint"


def newest_log(run_dir):
    logs = sorted(run_dir.glob("s[0-9]*.log"))
    return logs[-1].read_bytes().decode("utf-8", "replace") if logs else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("label")
    ap.add_argument("--baseline")
    ap.add_argument("--seconds", type=int, default=900)
    ap.add_argument("--kernel", default="12377-cmd1")
    ap.add_argument("--boot-args", default="", help="observation boot-args added after the fixed ones")
    ap.add_argument("--hold", action="store_true", help="keep the round up after the tour, for respin.py")
    ap.add_argument("--tour", nargs="+", help="tour.py steps instead of TOUR")
    ap.add_argument("--seed", default=os.environ.get("K90_SEED"), help="a /private/var archive to boot with")
    args = ap.parse_args()
    if args.seed:
        os.environ["SEED"] = args.seed
        args.boot_args = " ".join([args.boot_args, "var_store=1"]).strip()

    problem = loader_ready()
    if problem:
        print(f"STOP: {problem}")
        return 1
    state = json.loads(STATE.read_text()) if STATE.exists() else {"rounds_since_checkpoint": 0}
    if state["rounds_since_checkpoint"] >= CHECKPOINT_EVERY:
        problem = checkpoint()
        if problem:
            print(f"STOP: {problem}")
            return 1
        state["rounds_since_checkpoint"] = 0

    env = dict(os.environ, JOBS_SOURCE="tools/k90auto/jobs/rc.jobs.interactive",
               PAYLOAD_PROGRAMS="hackios-xnu-kernel/out/ios26-resume/rwsh:hackios-xnu-kernel/out/ios26-resume/var_store")
    with open(EVIDENCE / f"pack-{args.label}.log", "w") as log:
        if run([sys.executable, HERE / "package.py"], env=env, stdout=log, stderr=subprocess.STDOUT).returncode:
            print(f"STOP: package.py failed, see {log.name}")
            return 1
    payload_env = dict(os.environ, CPU_ARGS="cpus=4 bootcpu=7 small_cores_after=0",
                       SYSTEM="hackios-xnu-kernel/userland/system26.apfs", SYSTEM_WINDOW="0x300000000",
                       MEMSIZE="300000000", IDENTITY="v57")
    made = run([sys.executable, HERE / "make-payload.py", args.kernel, args.label,
                "out/ios26-resume/bbmetal-device/root.apfs",
                " ".join(["gpu_log=1 metal=1 cpufreq=1 fb_threads=2 touch_lat=1 gpu_coherent=1", args.boot_args]).strip()],
               env=payload_env, capture_output=True, text=True)
    if made.returncode:
        print(f"STOP: make-payload.py failed: {made.stdout[-400:]}{made.stderr[-400:]}")
        return 1
    round_dir = EVIDENCE / f"kernel-{args.kernel}-{args.label}"

    state["rounds_since_checkpoint"] += 1
    STATE.write_text(json.dumps(state) + "\n")
    out = open(EVIDENCE / f"cycle-{args.label}.out", "w")
    rounder = subprocess.Popen([sys.executable, str(HERE / "round-run.py"), str(round_dir), str(args.seconds),
                                "0,0,5"], cwd=WORKSPACE, stdout=out, stderr=subprocess.STDOUT,
                               env=dict(os.environ, K90_FREEZE_OFF="1"))
    begun = time.monotonic()
    while rounder.poll() is None and UNLOCK_LINE not in newest_log(round_dir / "run"):
        if time.monotonic() - begun > UNLOCK_WAIT:
            print("no boot unlock seen; the tour is skipped")
            break
        time.sleep(5)
    if rounder.poll() is None and UNLOCK_LINE in newest_log(round_dir / "run"):
        gpu_stopped = GPU_STOP in newest_log(round_dir / "run")
        if gpu_stopped:
            print("the GPU stopped before the tour; only the home screen is taken")
        tour = args.tour or TOUR
        run([sys.executable, HERE / "tour.py", round_dir, *(tour[:1] if gpu_stopped else tour)])
        if args.hold:
            print(f"held: tools/k90auto/respin.py {round_dir} ... (--stop ends it)", flush=True)
        else:
            (round_dir / "run" / "stop-request").write_text("")
    rounder.wait()

    report = run([sys.executable, HERE / "render-health.py", round_dir,
                  *(["--baseline", args.baseline] if args.baseline else [])], capture_output=True, text=True)
    (round_dir / "render-report.txt").write_text(report.stdout)
    print(f"report: {round_dir / 'render-report.txt'}  sheet: {round_dir / 'run/tour-sheet.png'}")
    problem = loader_ready()
    if problem:
        print(f"STOP after the round: {problem}")
        return 1
    return 0 if rounder.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
