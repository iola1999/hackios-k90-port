#!/usr/bin/env python3
"""One variable: backboardd gets the Metal device registration SpringBoard already has.

The 2026-10-27 runs showed metal=1 opening the kernel's gate and SpringBoard registering the
Redwood device, while backboardd still printed "Failed to initialize Metal or OpenGLES contexts!"
and composited on the CPU. The run that armed backboardd then showed why: it died fifteen times on
-[RedwoodMetalBlitEncoder generateMipmapsForTexture:], a selector the driver does not implement,
before anything was drawn. So this image carries both libraries rebuilt from the current source:

  - libredwood-sbmetal-experiment.dylib, whose target table serves SpringBoard and backboardd;
  - libredwoodmetal.dylib, which logs and skips mipmap generation and forwards the other blit
    selectors MTLBlitCommandEncoder declares instead of aborting the process on them.

and four changes to the root tree: the injection names backboardd as well, backboardd's launchd
job carries REDWOOD_SB_METAL=1 (in the job plist and in the launchd cache, which must agree), the
libraries above replace the frozen ones, and etc/rc.jobs is the eight-round gesture script from
tools/k90auto/rc.jobs.desktop in place of the base image's one-shot sequence.

The AIR library beside this script is the same build the base image carries, plus one patch:
tools/mesa/air/air_metal.c drops a fragment shader's [[depth]] stores when the pipeline has no
depth attachment, instead of refusing the pipeline. CoreAnimation builds such a pipeline and exits
with OS_REASON_COREANIMATION when the answer is no. Rebuilt with
`ninja -C out/ios26-resume/mesa-arm64e/build src/gallium/drivers/freedreno/libredwoodair.dylib`
after copying the patched source over that tree's src/compiler/air/air_metal.c, then signed adhoc.

The driver source is the userland repository's HEAD, which also carries the
minimumLinearTextureAlignmentForPixelFormat: override that the frozen 1ea7c58d library in the base
image was built without. That override is the one thing here this image does not isolate.

usage: python3 tools/k90auto/package.py      (from the workspace root)

The products stay in the ignored build directory
`hackios-xnu-kernel/out/ios26-resume/bbmetal-device/` (root image, the two libraries,
manifest.json, the logs); `jobs/` beside this script is the tracked copy of the launchd jobs it
puts into the root image.
"""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import shutil
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent        # tools/k90auto/
WORKSPACE = HERE.parents[1] / "hackios-xnu-kernel"      # the kernel checkout, from <workspace>/tools/k90auto
OUT = WORKSPACE / "out/ios26-resume/bbmetal-device"   # where the products and the logs stay
# PAYLOAD_SRC_ROOT packs from a clean copy of the sources instead of the working tree, so a package
# can be built while somebody else has an edit in flight (and the manifest records which sources).
SRC_ROOT = Path(os.environ.get("PAYLOAD_SRC_ROOT", str(WORKSPACE)))
# PAYLOAD_PROGRAMS=path[:path] installs programs rebuilt from the current source into /bin of the
# root image. The base image's copies are frozen by BASE_ROOT_SHA256, so a program that changed
# (metal_drv_test, for one) has to be named here or the image keeps the old binary.
EXTRA_PROGRAMS = [Path(p) for p in os.environ.get("PAYLOAD_PROGRAMS", "").split(":") if p]
# The AIR library is not compiled here; tools/k90auto/build-air.py is the only entry point that
# builds it, because the arm64e build reads its own copy of the sources and an unsynced edit builds
# a valid library that is missing what the round is meant to measure. Its record says which library
# that build produced and which format strings it holds: both are checked here, and
# PAYLOAD_AIR_STRINGS (colon separated) adds the fields this round depends on.
AIR_RECORD = WORKSPACE / "out/ios26-resume/mesa-arm64e/air-build-record.json"
AIR_REQUIRED = [t for t in os.environ.get("PAYLOAD_AIR_STRINGS", "").split(":") if t]
# PROBE=1 builds userland/src/lsprobe.m into /bin/lsprobe and adds one line to rc.jobs that runs it
# at 60 s and 300 s. It is read-only: it asks LSApplicationWorkspace and MobileInstallationLookup for
# the application list and prints the count, the bundle identifiers and the extension records each
# proxy carries. The console cannot answer that question on its own -- SpringBoard says six lines in a
# whole boot -- and two icons on a desktop that may have had fifteen is exactly the difference between
# "LaunchServices knows two applications" and "LaunchServices knows them all and none renders".
PROBE = os.environ.get("PROBE") == "1"
PROBE_SOURCES = ["userland/src/lsprobe.m"]
PROBE_FLAGS = ["-Os", "-Wall", "-Wextra", "-framework", "Foundation"]
# Two processes, not one with two offsets: the t=60 side has been observed to disappear before it
# reaches its second offset, and the answers at t=300 do not depend on the earlier ones. Each is
# backgrounded so a slow probe cannot hold the rest of the boot script.
PROBE_LINE = "/redwood/bin/lsprobe 60 &\n/redwood/bin/lsprobe 300 &\n"
# VARSTORE_SHOW=1 adds one line that reads both slots of the darwin partition. Saving is not part of
# it: a save writes the partition and is its own variable, while this only answers whether a store
# from an earlier boot exists at all -- the question that decides whether the data volume can carry
# install records across boots. No boot argument is involved: var_store=1 is what restores a store
# over the skeleton, and that one changes every later boot and cannot share a round.
VARSTORE_SHOW = os.environ.get("VARSTORE_SHOW") == "1"
VARSTORE_LINE = "/redwood/bin/var_store show\n"
BASE = WORKSPACE / "out/ios26-resume/air-arm64e-device/on"
TOOLS = WORKSPACE / "tools/apfs"
INJECT = (
    "/redwood/lib/libredwood-sbmetal-experiment.dylib SpringBoard backboardd" +
    (" iconservicesagent" if os.environ.get("ICON_METAL") == "1" else "") + "\n"
    "/redwood/lib/libredwood.dylib backboardd\n"
    "/redwood/lib/libredwood-sb26.dylib SpringBoard PosterBoard\n"
)
JOBS = "etc/rc.jobs"
# JOBS_SOURCE=... runs a different touch script than the acceptance one. A diagnostic that has
# to catch the screen mid-drag needs its own timing, and the acceptance script stays as it is.
JOBS_SOURCE = Path(os.environ.get("JOBS_SOURCE", HERE / "rc.jobs.desktop"))
# Whether the name above came from the environment or from the default. A round that ran the
# default and a round that asked for that same file are different statements, and the archive has
# to carry which one happened: two rounds with 3550 and 17 frames differ by their gesture script,
# and that was not recoverable from either manifest before this field existed.
JOBS_SOURCE_GIVEN = "JOBS_SOURCE" in os.environ
JOB = "LaunchDaemons/com.apple.backboardd.plist"
CACHE_KEY = "/System/Library/LaunchDaemons/com.apple.backboardd.plist"
# iconservicesagent renders the icons applications ask IconServices for. Without a Metal device it
# renders them in software, and IconRendering then refuses to serialize every one of them
# ("TextureIOError.usingSoftwareRenderer", 230 times in the ffma1 round): the General page of
# Settings showed grey squares. ICON_METAL=1 gives it the same registration as backboardd. Off by
# default: in lock2cpu4 (2026-10-30) the AIR frontend refused its path_exterior_fragment pipeline,
# iconservicesagent was the first process to report THE GPU DID NOT FINISH, and the kernel closed
# GPU submissions until a cold reset.
ICON_METAL = os.environ.get("ICON_METAL") == "1"
ICON_JOB = "LaunchDaemons/com.apple.iconservices.iconservicesagent.plist"
ICON_CACHE_KEY = "/System/Library/LaunchDaemons/com.apple.iconservices.iconservicesagent.plist"
# MSAA=1 asks the driver for four samples on both processes that encode render passes:
# backboardd draws the window server's layers, SpringBoard its own, and a run of one without
# the other compares two different devices. Off by default, because the answer changes what
# every application that asks -supportsSampleCount: does.
MSAA = os.environ.get("MSAA") == "1"
MSAA_JOBS = ["com.apple.backboardd.plist", "com.apple.SpringBoard.plist"]
# JOB_ENV="a.plist:KEY=VALUE b.plist:KEY=VALUE" adds one environment variable per item to a job, in
# its plist and in the launchd cache. The ones in use: OS_ACTIVITY_DT_MODE=YES sends a job's os_log
# to stderr and so to the console (backboardd, iconservicesagent and chronod have it already);
# REDWOOD_SYNC_DRAWS=1 makes the driver wait after every draw and name the one the GPU did not
# finish (redwoodmetal_diag.inc); FD_MESA_DEBUG is freedreno's own debug switch.
JOB_ENV = []
for item in os.environ.get("JOB_ENV", "").split():
    job_name, _, setting = item.partition(":")
    key, _, value = setting.partition("=")
    if not job_name.endswith(".plist") or not key:
        raise SystemExit(f"JOB_ENV item {item!r} is not NAME.plist:KEY=VALUE")
    JOB_ENV.append((job_name, key, value))

# The wallpaper and the widgets are drawn by two services this boot does not start, and each
# lookup for them fails: SpringBoard and iconservicesagent ask for
# com.apple.posterboardservices.services, which is the wallpaper, and the home screen's widget
# stays on "Waiting…" because nothing hosts a widget extension. The plists are the real ones:
# chronod's from the 2026-10-25 QEMU image, PosterBoard's from
# System/Library/LaunchAngels/com.apple.PosterBoard.plist with one change -- the real one marks
# its service _ExperimentalNonLaunching so that RunningBoard, not launchd, starts the angel, and
# nothing here asks RunningBoard for an angel scene.
EXTRA_JOBS = ["com.apple.chronod.plist", "com.apple.PosterBoard.plist",
              "com.apple.replicatord.plist", "com.apple.mobile.installd.plist",
              "com.apple.biomed.plist", "com.apple.ReportCrash.plist", "com.apple.linkd.plist",
              "com.apple.contextstored.plist", "com.apple.dasd.plist",
              "com.apple.appprotectiond.plist"]
# biomed is the only one here Apple ships without RunAtLoad, and that is how it has to stay: it
# serves com.apple.biome.access.user, and launchd starts it when chronod first opens a Biome stream.
# Forcing RunAtLoad on it would start a second copy of Apple's scheduling while the desktop is still
# coming up. EnablePressuredExit is Apple's own and is left as it is: launchd reclaims it when idle
# and starts it again on the next lookup, which is what a client that keeps asking wants anyway.
# com.apple.biomesyncd is deliberately not here: it syncs Biome to paired devices over Rapport and
# Cascade and serves none of the names chronod looks up, so it would answer nothing on this boot.
# ReportCrash holds a Mach service whose entry carries an ExceptionServer subtype: launchd keeps the
# receive right for the name and starts the job when something is delivered to it, so the same
# treatment as biomed (Apple's keys untouched, no RunAtLoad) is also the correct one here. Without
# the job registered, a corpse notification has no receiver and the host that dies leaves nothing on
# the memory disk to read.
# linkd is the largest remaining one: all 1376 raw Code=4099 lines on the biomed round come from
# chronod, and 88 percent of them are com.apple.linkd.registry. Apple's plist has no RunAtLoad and
# lists ten Mach services, so it starts when one of them is looked up. Its LaunchEvents watch
# LaunchServices application registration, which is worth knowing at boot: this boot registers about
# 259 applications in the first seconds, and each notification can wake linkd. That is Apple's own
# shape and is left alone; a pid that changes repeatedly in the run is how it would show.
ON_DEMAND_JOBS = {"com.apple.biomed.plist", "com.apple.ReportCrash.plist", "com.apple.linkd.plist",
                  "com.apple.contextstored.plist", "com.apple.dasd.plist",
                  "com.apple.appprotectiond.plist"}
# contextstored is here for one service: com.apple.coreduetd.context. 9 lines of
# NSCocoaErrorDomain Code=4099 on kernel-12377-attr26-continuous are that name failing to look
# up (error 3, no such process) on the key paths /device/dasd/widgetBudget, widgetSystemAdded and
# widgetOverride; the provider is contextstored, not dasd, which is why registering this one name
# is what answers them. On demand, as Apple ships it: a lookup starts the job, and the point is
# that the lookup has a receiver, not that the daemon runs at boot.
# dasd is here for com.apple.duetactivityscheduler, which widget refreshes ask for the budgets of:
# 74 lines on kernel-12377-attr26-persona3 look that name up and find nothing. On demand too, and
# it matters more here than for contextstored: duetactivityscheduler takes over background
# scheduling once it runs, so forcing RunAtLoad would change when the system runs background work
# and make the performance and temperature readings of this round incomparable with earlier ones.
# appprotectiond is here for com.apple.appprotectiond.read, the largest single name in the 4099
# count (163 on persona3, 172 on continuous): one job provides all eight appprotectiond services,
# so registering it is what gives that lookup a receiver. It watches extensions and view subjects
# through extensionmonitor and viewsubjectmonitor, which is the same ground the widget hosts die
# on, so a round with it needs the death-cause lines from 8776c5d to see a side effect at all.
# The home screen showed two icons of the sixty-four bundles that carry no SBAppTags hidden, and
# lsd[29] asked eight times for com.apple.mobile.installd without an answer: LaunchServices takes
# its application list from installd, and pluginkit takes its extension records from
# LaunchServices, so the two extension identities chronod asks for cannot resolve either. Both
# daemons are in the image and neither is in the job cache; installd's own plist runs it as
# _installd, a user the memory filesystem rebuilt at boot does not have, so it runs as root here.
JOB_USERS = {"com.apple.mobile.installd.plist": "root"}
# chronod is started late on purpose. Every run so far asked for widget and control extension
# identities eight and thirty-nine seconds after boot, before pluginkit and LaunchServices had
# registered the extensions of the 259 applications, and gave up for a day. StartInterval with
# RunAtLoad off puts its first start at about 120 s, after that registration.
LATE_JOBS = {"com.apple.chronod.plist": {"StartInterval": 120}}
JOBS_DIR = HERE / "jobs"
SDK = ["/usr/bin/xcrun", "-sdk", "iphoneos", "clang", "-arch", "arm64e", "-miphoneos-version-min=26.0"]

# Both commands are the ones the frozen libraries were built with (build.sh for the shim,
# mps-commandbuffer-production/build-commands.json for the driver).
SHIM_SOURCES = ["userland/src/sb_metal_experiment.m"]
SHIM_FLAGS = ["-Os", "-Wall", "-Wextra", "-Werror", "-framework", "Foundation", "-framework", "Metal",
              "-framework", "UIKit", "-framework", "IOKit"]
# The iOS 26 driver's sources live in the kernel checkout under tools/userland-driver/, not under
# userland/src/: that tree is excluded by the checkout's .gitignore, so a print added there has no
# rebuildable origin. The library this pack ships is built from exactly these files, and the build
# is reproducible: 241,488 bytes, sha256 9d66dd36… from clang 21.0.0 and SDK 27.1, provided the
# output keeps the name libredwoodmetal.dylib -- the adhoc signature's identifier is
# <filename>-<UUID>, so any other output name yields a different whole-file hash with the same
# __text and LC_UUID. Steps are in docs/analysis/2026-10-28-arm64e-userland-build-path.md §1.1.
DRIVER_SOURCES = ["tools/userland-driver/redwoodmetal.m",
                  "tools/userland-driver/redwooddrawable.m"]
DRIVER_FLAGS = ["-O1", "-framework", "Foundation", "-framework", "IOKit", "-framework", "Metal"]
# Everything the two driver sources include. The manifest used to name only redwoodmetal_blit.inc, and
# when the shipped 827045e4… had to be traced to a commit the file that differed was
# redwoodmetal_commandbuffer.inc, which no manifest recorded: the .m hashes matched and the product
# hash did not, so the search could only end by rebuilding from candidate trees.
DRIVER_INCLUDES = ["tools/userland-driver/redwood_drawable.h",
                   "tools/userland-driver/redwoodmetal_archive.inc",
                   "tools/userland-driver/redwoodmetal_blit.inc",
                   "tools/userland-driver/redwoodmetal_commandbuffer.inc",
                   "tools/userland-driver/redwoodmetal_diag.inc",
                   "tools/userland-driver/redwoodmetal_mesa.inc",
                   "tools/userland-driver/redwoodmetal_state.inc",
                   "tools/userland-driver/redwoodmetal_stitch.inc",
                   "tools/userland-driver/redwoodmetal_texture.inc",
                   "tools/userland-driver/redwoodmetal_work.inc",
                   "tools/userland-driver/redwoodmetal_work_private.h"]

# SpringBoard's 23G90 adaptations: the local activation state, the software icon selection and the
# lock screen dismissal after boot (com.redwood.unlock dismisses it again). The base image carries an
# older build of it that no inject.conf line loaded, so the iOS 26 lock screen stayed up until it was
# swiped away by hand; the pack builds this one from the current source and injects it. The same
# library is injected into PosterBoard, where only inject_posterboard.c's constructor acts: it logs
# the errors behind the data store PosterBoard cannot create, which is why the wallpaper is empty.
SB26_SOURCES = ["userland/src/inject_sb26.c", "userland/src/inject_sb26_layers.c",
                "userland/src/inject_posterboard.c"]
SB26_FLAGS = ["-Os", "-Wall", "-Wextra", "-Werror", "-framework", "CoreFoundation", "-framework", "Metal"]

# The run this image is compared against used exactly these.
BASE_ROOT_SHA256 = "33ed5fc9cb18367c124e6fd26a2fc982f7d80b3a44e04754f87cf74b5aa381f0"
OLD_SHIM_SHA256 = "be308aea0cb5c86dd8faa22df59aeefabe8fc688678ba80e2af2adf59f4da142"
OLD_DRIVER_SHA256 = "1ea7c58ddb8ad6506749527fac41d1ca7ea10f977c3a9f0deefdd39b5880a907"
OLD_AIR_SHA256 = "adf0328a025f959bd6bb7da7e7b81ec600075b5ad39aa7c3b31e8df506a8d604"

# make-payload.py defaults this to 3 while nearly every comparable round used 1, so a forgotten
# GPU_SPEED changes the GPU clock without changing the request. It is recorded here as well as in the
# round manifest, and a note that names a different speed stops the pack.
GPU_SPEED = int(os.environ.get("GPU_SPEED", "3"))
# REDWOOD_DIAG=1 puts a diagnostic variable in the driver processes' environment. Diagnostic prints
# (the driver's load address today, anything else added for one investigation later) are behind it,
# so enabling one does not change the library. The manifest records whether this round carried them.
REDWOOD_DIAG = os.environ.get("REDWOOD_DIAG") == "1"
# JOBS_DROP="a.plist b.plist" packs without those jobs. A round changes one thing, and EXTRA_JOBS
# accumulates what earlier rounds proved: without a way to leave one out, adding the next job also
# changes the previous one's result. The names dropped are recorded in the manifest, so a round says
# what it did not carry as well as what it did.
JOBS_DROP = {n.strip() for n in os.environ.get("JOBS_DROP", "").split() if n.strip()}
missing_drop = JOBS_DROP - set(EXTRA_JOBS)
assert not missing_drop, f"JOBS_DROP names jobs that are not in EXTRA_JOBS: {sorted(missing_drop)}"

sys.path.insert(0, str(TOOLS))
from apfs import Container, pick_volume, walk, ROOT_DIR_INO_NUM   # noqa: E402


def dirty_sources():
    """What is uncommitted in the trees a pack is built from, as one git status per repository.

    The result goes into the pack record so a round states what it was built from. It does not stop
    the pack. Two checks, because the sources live in two repositories: the kernel work tree keeps
    userland, Mesa and the AIR sources under .userland.git, which common/ugit reads, and the packaging
    code is in the top repository. Documentation and unrelated tools cannot change what a round runs,
    so they are outside both checks."""
    reports = []
    for name, command, cwd in (
            ("kernel work tree under .userland.git (userland, Mesa, AIR sources)",
             ["common/ugit", "status", "--short"], WORKSPACE),
            ("top repository (packaging code)",
             ["git", "status", "--short", "--", "tools/k90auto"], WORKSPACE.parent)):
        try:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as error:
            reports.append(f"{name}: could not be read ({error})")
            continue
        if result.returncode != 0:
            reports.append(f"{name}: could not be read ({result.stderr.strip() or result.returncode})")
            continue
        if result.stdout.strip():
            reports.append(f"{name}:\n{result.stdout.rstrip()}")
    return reports


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


# Every library in this image is loaded by an arm64e process, and dyld refuses an arm64 slice in one
# by discarding it without a line: the processes then run with none of the library's work done, which
# reads as the library not being injected at all. 0x80000002 is ARM64E with the LIB64 bit, which is
# what build.sh's own gate (:885-922) requires of everything it stages.
ARM64E_WITH_LIB64 = 0x80000002


def cpusubtype(path):
    """The cpusubtype of a thin Mach-O, read from its header."""
    with Path(path).open("rb") as source:
        header = source.read(12)
    magic, _cputype, cpusubtype = struct.unpack("<Iii", header)
    assert magic in (0xFEEDFACF, 0xFEEDFACE), f"{path} is not a thin Mach-O (magic {magic:#x})"
    return cpusubtype & 0xFFFFFFFF


def records(path):
    """Every path in a root image, with the metadata mkapfs.py would have to reproduce."""
    container = Container(str(path))
    volume = pick_volume(container, None)
    meta, bodies = {}, {}
    for name, _, fid, kind in [("/", "", ROOT_DIR_INO_NUM, 4), *walk(volume, ROOT_DIR_INO_NUM)]:
        inode = volume.inode(fid)
        data = inode.contents() if kind == 8 else inode.symlink_target_bytes() if kind == 10 else b""
        bodies[name] = data
        meta[name] = {"kind": kind, "sha256": hashlib.sha256(data).hexdigest(),
                      **{k: getattr(inode, k) for k in
                         ["mode", "owner", "group", "create_time", "mod_time", "change_time",
                          "access_time", "protection_class", "bsd_flags", "internal_flags", "nlink"]},
                      "xattrs": {n: hashlib.sha256(volume.xattr_bytes(fid, n, inode.xattrs)).hexdigest()
                                 for n in inode.xattrs}}
    container.close()
    return meta, bodies


def build(sources, install_name, flags, out, dynamic=True):
    """One arm64e library (or one program, dynamic=False) from the current source, signed as build.sh signs one."""
    kind = ["-dynamiclib", "-install_name", install_name] if dynamic else []
    command = SDK + flags + ["-fno-objc-arc", *kind, *sources, "-lobjc", "-o", str(out)]
    with out.with_suffix(".build.log").open("w") as log:
        log.write(" ".join(command) + "\n")
        subprocess.run(command, stdout=log, stderr=log, check=True, cwd=SRC_ROOT)
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(out)], check=True)
    return command


def add_switch(root):
    """REDWOOD_SB_METAL=1 for backboardd (and iconservicesagent with ICON_METAL=1), in the job
    plists and in the launchd cache. Returns backboardd's job."""
    cache_path = root / "xpc/launchd.plist"
    cache = plistlib.loads(cache_path.read_bytes())
    jobs = []
    targets = [(JOB, CACHE_KEY)] + ([(ICON_JOB, ICON_CACHE_KEY)] if ICON_METAL else [])
    for relative, key in targets:
        job_path = root / relative
        job = plistlib.loads(job_path.read_bytes())
        job.setdefault("EnvironmentVariables", {})["REDWOOD_SB_METAL"] = "1"
        blob = plistlib.dumps(job, fmt=plistlib.FMT_BINARY)
        job_path.write_bytes(blob)
        assert plistlib.loads(blob) == job, "the job plist did not survive the round trip"
        cache["LaunchDaemons"][key] = job
        jobs.append(job)
    cache_path.write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY))
    return jobs[0]


def add_diag(root, cache):
    """REDWOOD_DIAG=1 for the two processes that load the driver, when REDWOOD_DIAG=1 asks.

    Diagnostic prints sit behind this variable so a round can turn them on without a different
    library, and the manifest records whether the round carried them. Without the variable the driver
    prints none of them."""
    for name in MSAA_JOBS:
        job_path = root / "LaunchDaemons" / name
        job = plistlib.loads(job_path.read_bytes())

        job.setdefault("EnvironmentVariables", {})["REDWOOD_DIAG"] = "1"
        blob = plistlib.dumps(job, fmt=plistlib.FMT_BINARY)
        job_path.write_bytes(blob)
        cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] = job
    (root / "xpc/launchd.plist").write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY))
    return cache


def add_env(root, cache, settings):
    """Each (job, key, value) in the job's environment, in its plist and in the launchd cache."""
    for name, key, value in settings:
        job_path = root / "LaunchDaemons" / name
        job = plistlib.loads(job_path.read_bytes())
        job.setdefault("EnvironmentVariables", {})[key] = value
        job_path.write_bytes(plistlib.dumps(job, fmt=plistlib.FMT_BINARY))
        cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] = job
    (root / "xpc/launchd.plist").write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY))
    return cache


def add_msaa(root):
    """REDWOOD_MSAA=1 for the two processes that encode render passes, when MSAA=1 asks."""
    cache_path = root / "xpc/launchd.plist"
    cache = plistlib.loads(cache_path.read_bytes())

    for name in MSAA_JOBS:
        job_path = root / "LaunchDaemons" / name
        job = plistlib.loads(job_path.read_bytes())

        job.setdefault("EnvironmentVariables", {})["REDWOOD_MSAA"] = "1"
        blob = plistlib.dumps(job, fmt=plistlib.FMT_BINARY)
        job_path.write_bytes(blob)
        cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] = job
    cache_path.write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY))


def add_extra_jobs(root):
    """The wallpaper and the widget services, in the LaunchDaemons directory and the cache."""
    cache_path = root / "xpc/launchd.plist"
    cache = plistlib.loads(cache_path.read_bytes())
    for name in EXTRA_JOBS:
        if name in JOBS_DROP:
            continue
        job = plistlib.loads((JOBS_DIR / name).read_bytes())
        # RunAtLoad for all: nothing else here asks for them early. KeepAlive off, so a service
        # that cannot run in this boot is seen dead once in the log rather than restarted for the
        # length of the run. The jobs in LATE_JOBS are the exception: their first start is put off
        # by StartInterval instead, so it lands after pluginkit has registered the extensions.
        if name not in ON_DEMAND_JOBS:
            job["RunAtLoad"] = True
            job["KeepAlive"] = False
        user = JOB_USERS.get(name)
        if user is not None:
            job["UserName"] = user
            job.pop("GroupName", None)
        late = LATE_JOBS.get(name)
        if late is not None:
            job["RunAtLoad"] = False
            job.update(late)
        blob = plistlib.dumps(job, fmt=plistlib.FMT_BINARY)
        (root / "LaunchDaemons" / name).write_bytes(blob)
        cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] = job
    cache_path.write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY))
    return cache


def main():
    dirty = dirty_sources()
    if dirty:
        print("工作树有未提交的改动，打包照常进行。改动清单写进 pack 记录的 worktree_status，"
              "这一轮由什么构成以那一份清单为准。")
    notes = os.environ.get("ROUND_NOTES", "")
    claimed = set(re.findall(r"(?:adreno8_speed|gpu_speed|GPU_SPEED|speed)\s*[=:]\s*(\d+)", notes))
    wrong = sorted(value for value in claimed if int(value) != GPU_SPEED)
    if wrong:
        raise SystemExit(
            f"round notes name GPU speed {', '.join(wrong)} but this pack runs adreno8_speed={GPU_SPEED} "
            f"(GPU_SPEED defaults to 3). Set GPU_SPEED to the value the round is meant to run, or fix "
            f"the note; a record that says one thing while the round runs another is what this check is for.")

    assert sha(BASE / "root.apfs") == BASE_ROOT_SHA256, "base root image changed"
    assert sha(BASE / "root/lib/libredwood-sbmetal-experiment.dylib") == OLD_SHIM_SHA256, "base shim changed"
    assert sha(BASE / "root/lib/libredwoodmetal.dylib") == OLD_DRIVER_SHA256, "base driver changed"
    assert sha(BASE / "root/lib/libredwoodair.dylib") == OLD_AIR_SHA256, "base AIR library changed"

    shim = OUT / "libredwood-sbmetal-experiment.dylib"
    driver = OUT / "libredwoodmetal.dylib"
    air = OUT / "libredwoodair.dylib"
    sb26 = OUT / "libredwood-sb26.dylib"
    # build.sh's own product, which this pack used to take from the base root: a change to
    # userland/src/inject.c then never reached an image, and on 2026-10-29 tl: b was in obj/ and in
    # userland/root/ while the packed /lib/libredwood.dylib was e527b342… from an earlier round.
    userland = SRC_ROOT / "userland/root/lib/libredwood.dylib"
    assert userland.is_file(), f"{userland} is userland/build.sh's product; run it before packing"
    assert air.is_file(), (f"{air} is missing; tools/k90auto/build-air.py writes it and signs it, "
                           "and ninja alone does not")
    # The ninja build leaves the library unsigned, and dyld refuses it: the image then boots,
    # composits on the CPU and records plausible frame times with no GPU submission at all.
    signed = subprocess.run(["/usr/bin/codesign", "-dv", str(air)], capture_output=True, text=True)
    assert "Signature=adhoc" in signed.stderr, (
        f"{air} is not signed adhoc, and dyld will refuse it. The file to pack is "
        "out/ios26-resume/bbmetal-device/libredwoodair.dylib, which build-air.py signs with "
        "codesign --force --sign -; the copy ninja leaves under "
        "out/ios26-resume/mesa-arm64e/build/src/gallium/drivers/freedreno/ is unsigned by "
        "construction, so it can never pass this check. Run tools/k90auto/build-air.py")
    commands = {"shim": build(SHIM_SOURCES, "/redwood/lib/libredwood-sbmetal-experiment.dylib",
                              SHIM_FLAGS, shim),
                "driver": build(DRIVER_SOURCES, "/redwood/lib/libredwoodmetal.dylib",
                                 DRIVER_FLAGS, driver),
                "sb26": build(SB26_SOURCES, "/redwood/lib/libredwood-sb26.dylib", SB26_FLAGS, sb26)}
    probe = OUT / "lsprobe"
    if PROBE:
        commands["probe"] = build(PROBE_SOURCES, "", PROBE_FLAGS, probe, dynamic=False)
    sources = {name: sha(SRC_ROOT / name)
               for name in [*SHIM_SOURCES, *DRIVER_SOURCES, *DRIVER_INCLUDES, *SB26_SOURCES,
                            "userland/src/sb_metal_registration_sequence.inc",
                            "userland/src/sb_metal_compression_policy.inc",
                            "tools/mesa/air/air_metal.c", "tools/mesa/air/air_to_nir.c",
                            *(PROBE_SOURCES if PROBE else [])]}
    # The probe goes first, not last. init runs a job file one line at a time and waits for each, so a
    # probe line appended after a few minutes of gestures only starts when the gestures are over: on
    # 2026-10-28 the two lsprobe lines sat behind 500 s of drags and never ran, while the same lines at
    # the top of the file run from the first second of the round.
    jobs_source_bytes = JOBS_SOURCE.read_bytes()
    jobs = ((PROBE_LINE.encode() if PROBE else b"") + (VARSTORE_LINE.encode() if VARSTORE_SHOW else b"")
            + jobs_source_bytes)

    before, _ = records(BASE / "root.apfs")
    protected = {str(p): sha(p) for p in [BASE / "root.apfs"]}

    dest = OUT / "root"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE / "root", dest, symlinks=True)
    # The base root is a build product, and a line added to userland/build.sh does not reach a pack
    # until build.sh is run again: on 2026-10-28 the two directories added to the data volume template
    # were still missing from the packed etc/var.skel, and the round that was meant to test them ran
    # without them. var.skel.extra is the one place those lines are written down; build.sh appends it
    # when it builds the skeleton, and this step appends whatever the base root is too old to have.
    skeleton = dest / "etc/var.skel"
    wanted = [line for line in (WORKSPACE / "userland/var.skel.extra").read_text().splitlines()
              if line and not line.startswith("#")]
    present = skeleton.read_text()
    appended = [line for line in wanted if line + "\n" not in present]
    if appended:
        with skeleton.open("a") as out:
            out.write("".join(line + "\n" for line in appended))
        print(f"etc/var.skel in the base root is older than userland/var.skel.extra: added "
              f"{len(appended)} line(s); rerun userland/build.sh to rebuild the base root")
    # The count of lines added is a middle quantity: it says what this step did, not what the image
    # carries. These two names are what a round is measured on, so the pack fails when either is
    # missing from the packed skeleton, whoever broke it and however.
    for required in ("/private/var/mobile/Library/MobileInstallation",
                     "/private/var/mobile/Library/SpringBoard"):
        assert required in skeleton.read_text(), (
            f"the packed etc/var.skel has no line for {required}: init will not create that "
            f"directory and the round cannot test anything that needs it")
    shutil.copy2(shim, dest / "lib/libredwood-sbmetal-experiment.dylib")
    shutil.copy2(driver, dest / "lib/libredwoodmetal.dylib")
    # What lands in the image has to be the library that was just built: on 2026-10-29 a pack left
    # 9d66dd36… in the root while the staging copy was d296b5a4…, and nothing noticed.
    assert sha(dest / "lib/libredwoodmetal.dylib") == sha(driver), \
        "the driver in the image is not the one this pack built"
    shutil.copy2(air, dest / "lib/libredwoodair.dylib")
    shutil.copy2(sb26, dest / "lib/libredwood-sb26.dylib")
    shutil.copy2(userland, dest / "lib/libredwood.dylib")
    assert sha(dest / "lib/libredwood.dylib") == sha(userland), \
        "libredwood.dylib in the image is not the one build.sh produced"
    # build.sh compiles this one with $DYN (-arch arm64, iOS 16.5 SDK) and every other library in
    # this image with -arch arm64e: on 2026-10-29 the image carried an arm64 slice and backboardd
    # ran with none of its work done, while dyld said nothing ("no load, no line"). The hash above
    # cannot catch that -- the file really was the one build.sh made.
    assert cpusubtype(dest / "lib/libredwood.dylib") == ARM64E_WITH_LIB64, (
        f"libredwood.dylib is cpusubtype {cpusubtype(dest / 'lib/libredwood.dylib'):#x}, and this "
        "image's processes are arm64e: rebuild it with -arch arm64e and an iOS 26 SDK, as build.sh "
        "does for its other libraries, then sign it")
    for program in EXTRA_PROGRAMS:
        assert program.is_file(), f"{program} is named in PAYLOAD_PROGRAMS and is not a file"
        shutil.copy2(program, dest / "bin" / program.name)
    # A job whose program is not on the image spawns nothing, and the failure looks exactly like a
    # service that does not answer: the image is assembled by path prefix and file size
    # (ios26/select-system.py), so a program over the size limit for its directory is simply absent.
    # bluetoothd, 12,151,072 bytes, is one of the 19 such programs found on 2026-10-28.
    for plist_path in sorted((dest / "LaunchDaemons").glob("*.plist")):
        plist_data = plistlib.loads(plist_path.read_bytes())
        program = (plist_data.get("ProgramArguments") or [plist_data.get("Program")])[0]
        # Only our own image is checked here. Programs under /usr, /bin and /System come from the
        # system volume (system26.apfs), which this packer does not open; the audit of those is
        # tools/check-launchd-programs.py against that image.
        if not program or not program.startswith("/redwood/"):
            continue
        # this image is what mounts at /redwood, so /redwood/sbin/init is dest/sbin/init here
        relative = program[len("/redwood"):] if program.startswith("/redwood/") else program
        assert (dest / relative.lstrip("/")).exists(), (
            f"{plist_path.name} runs {program}, which is not on this image; the extraction in "
            f"ios26/select-system.py left it out, so this job can only fail to spawn")
    if AIR_RECORD.is_file():
        record = json.loads(AIR_RECORD.read_text())
        got = hashlib.sha256(air.read_bytes()).hexdigest()
        assert got == record["library_sha256"], (
            f"the AIR library here is {got[:16]}, but the last build-air.py run made "
            f"{record['library_sha256'][:16]}; run tools/k90auto/build-air.py")
        air_source = record.get("source_sha256:air_metal.c")
        # Every file build-air.py copies, with both digests. air_to_nir.c was outside the copied set
        # until 2026-10-28, so a change to it reached no build and said nothing; recording the record's
        # entries here means a round can be asked afterwards which sources its AIR library came from.
        air_sources = {key: value for key, value in record.items()
                       if str(key).startswith(("source_sha256:", "tree_sha256:"))}
    else:
        record, air_source, air_sources = {}, None, {}
    held = set()
    for text in [air.read_bytes()]:
        held = set(t for t in AIR_REQUIRED if t.encode() in text)
    missing = [t for t in AIR_REQUIRED if t not in held]
    assert not missing, f"the AIR library does not hold {missing}; check build-air.py --check"
    for name, present in record.get("holds", {}).items():
        assert present or name not in AIR_REQUIRED, f"build-air.py recorded {name} as absent"
    (dest / "etc/inject.conf").write_text(INJECT)
    if PROBE:
        shutil.copy2(probe, dest / "bin/lsprobe")
    # the desktop's own gesture script: the base image carries a one-shot sequence (unlock, two
    # page swipes and a Control Center pull, then nothing), and an acceptance run needs the eight
    # rounds the harness measures. The probe's line ends with "&": init runs the lines of rc.jobs
    # one after another and would otherwise hold the gestures for the probe's last offset.
    (dest / JOBS).write_bytes(jobs)
    job = add_switch(dest)
    if MSAA:
        add_msaa(dest)
    cache = add_extra_jobs(dest)
    if REDWOOD_DIAG:
        cache = add_diag(dest, cache)
        # add_diag rewrote this job too; the assertion further down compares the packed plist with
        # what this variable holds, so it has to be read again rather than kept from add_switch.
        job = plistlib.loads((dest / JOB).read_bytes())
    if JOB_ENV:
        cache = add_env(dest, cache, JOB_ENV)
        job = plistlib.loads((dest / JOB).read_bytes())
    # What launchd will know this boot, names only: the cache is the authority (iOS 26 takes its jobs
    # from /System/Library/xpc/launchd.plist, not from the LaunchDaemons directory), so reading the
    # labels back out of it answers "which jobs did this round carry" without replaying EXTRA_JOBS,
    # ON_DEMAND_JOBS and JOBS_DROP in the reader's head.
    jobs_effective = sorted(Path(key).name for key in cache["LaunchDaemons"])

    with (OUT / "root-build.log").open("w") as log:
        subprocess.run([sys.executable, str(TOOLS / "mkapfs.py"), "-z", "--plain", "fw",
                        "-o", str(OUT / "root.apfs"), "redwood=" + str(dest)],
                       stdout=log, stderr=log, check=True, cwd=WORKSPACE)

    after, bodies = records(OUT / "root.apfs")
    # The staged root and the finished image are two different things: the check above reads the
    # directory this script filled, and only this one answers what the device will load.
    for name, product in (("/lib/libredwood.dylib", userland),
                          ("/lib/libredwoodmetal.dylib", driver)):
        assert after[name]["sha256"] == sha(product), \
            f"{name} in root.apfs is not what this pack built"
    added = ({"/LaunchDaemons/" + name for name in EXTRA_JOBS if name not in JOBS_DROP}
             | ({"/bin/lsprobe"} if PROBE else set())
             | {"/bin/" + program.name for program in EXTRA_PROGRAMS})
    assert set(after) - set(before) == added, \
        f"unexpected files: {sorted(set(after) - set(before) - added)}"
    assert set(before) - set(after) == set(), sorted(set(before) - set(after))
    changes = {n: {k: [before[n][k], after[n][k]] for k in before[n] if before[n][k] != after[n][k]}
               for n in before if before[n] != after[n]}
    for name in added:
        changes[name] = {"sha256": [None, after[name]["sha256"]]}
    expected = {"/lib/libredwood-sbmetal-experiment.dylib", "/lib/libredwoodmetal.dylib",
                "/lib/libredwoodair.dylib", "/lib/libredwood.dylib", "/lib/libredwood-sb26.dylib",
                "/etc/inject.conf",
                "/etc/rc.jobs", "/" + JOB, *(["/" + ICON_JOB] if ICON_METAL else []),
                "/xpc/launchd.plist", *["/bin/" + program.name for program in EXTRA_PROGRAMS],
                # Anything added under a directory changes that directory's own times, and records()
                # reports the directory alongside the file, so the parent of every added file belongs
                # in this set. /bin is the only one today: the extra jobs' directory is listed on the
                # next line with the same reason. A new file somewhere else needs its parent added
                # here or the comparison above fails on a directory nobody meant to change.
                *(["/bin"] if PROBE or EXTRA_PROGRAMS else []),
                *(["/bin/lsprobe"] if PROBE else []),
                # the two jobs below change this directory's own times as well
                "/LaunchDaemons", *["/LaunchDaemons/" + name for name in EXTRA_JOBS if name not in JOBS_DROP],
                # the diagnostic switch rewrites the two jobs whose processes load the driver
                *(["/LaunchDaemons/" + name for name in MSAA_JOBS] if REDWOOD_DIAG else []),
                *{"/LaunchDaemons/" + name for name, _, _ in JOB_ENV},
                # the skeleton is rewritten only when the base root is too old to carry a line that
                # userland/var.skel.extra names; an empty skeleton_appended means it was left alone
                *(["/etc/var.skel"] if appended else [])}
    assert set(changes) == expected, f"unexpected changes: {sorted(set(changes) ^ expected)}"
    for name, diff in changes.items():
        assert set(diff) <= {"sha256", "xattrs", "internal_flags", "nlink"}, (name, sorted(diff))

    assert bodies["/etc/inject.conf"].decode() == INJECT
    assert bodies["/etc/rc.jobs"] == jobs
    assert plistlib.loads(bodies["/" + JOB]) == job
    cache = plistlib.loads(bodies["/xpc/launchd.plist"])
    assert cache["LaunchDaemons"][CACHE_KEY] == job, "the launchd cache and the job plist disagree"
    assert job["EnvironmentVariables"]["REDWOOD_SB_METAL"] == "1"
    if ICON_METAL:
        icon_job = plistlib.loads(bodies["/" + ICON_JOB])
        assert cache["LaunchDaemons"][ICON_CACHE_KEY] == icon_job, "iconservicesagent: cache and plist disagree"
        assert icon_job["EnvironmentVariables"]["REDWOOD_SB_METAL"] == "1"
    for name in EXTRA_JOBS:
        if name in JOBS_DROP:
            continue
        extra = plistlib.loads(bodies["/LaunchDaemons/" + name])
        if name in ON_DEMAND_JOBS:
            assert "RunAtLoad" not in extra and extra["EnablePressuredExit"] is True, name
            assert extra["MachServices"], name
            continue
        assert extra["KeepAlive"] is False, name
        if name in LATE_JOBS:
            assert extra["RunAtLoad"] is False and extra["StartInterval"] == 120, name
        else:
            assert extra["RunAtLoad"] is True, name
        assert cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] == extra, name
    for name, path in [("/lib/libredwood-sbmetal-experiment.dylib", shim),
                       ("/lib/libredwoodmetal.dylib", driver),
                       ("/lib/libredwoodair.dylib", air),
                       *[("/bin/" + program.name, program) for program in EXTRA_PROGRAMS],
                       *([("/bin/lsprobe", probe)] if PROBE else [])]:
        assert hashlib.sha256(bodies[name]).hexdigest() == sha(path), name

    driver_sha, air_sha = sha(driver), sha(air)

    report = {
        "base": str(BASE), "base_root_sha256": BASE_ROOT_SHA256,
        "driver_sha256": driver_sha, "air_sha256": air_sha,
        "variable": "backboardd armed for Metal registration; the driver survives the blit selectors "
                    "it does not implement; the eight-round gesture script drives the run",
        "old_shim_sha256": OLD_SHIM_SHA256, "new_shim_sha256": sha(shim),
        "old_driver_sha256": OLD_DRIVER_SHA256, "new_driver_sha256": sha(driver),
        "old_air_sha256": OLD_AIR_SHA256, "new_air_sha256": sha(air), "air_source_sha256": air_source,
        "userland_sha256": sha(userland), "userland_bytes": userland.stat().st_size,
        "inject_source_sha256": sha(SRC_ROOT / "userland/src/inject.c"),
        "air_sources": air_sources,
        # Every source this pack read, with its sha256: shim, driver, probe, AIR, and the kernel commit
        # is in `kernel` below. Without this section a round cannot be asked which code it ran.
        "sources": sources,
        # What this round ran. A round is a set of choices, and the manifest has to name them: the
        # gesture script, the probe sources, the job set, the libraries, the kernel. air_sources above
        # closed half of that gap; these close the other half.
        "jobs_source": {"path": str(JOBS_SOURCE.relative_to(WORKSPACE))
                        if JOBS_SOURCE.is_relative_to(WORKSPACE) else str(JOBS_SOURCE),
                        "sha256": sha(JOBS_SOURCE),
                        "given": JOBS_SOURCE_GIVEN},
        "probe_sources": {name: sources[name] for name in PROBE_SOURCES if name in sources},
        "air_delta": "tools/mesa/air/air_metal.c drops the [[depth]] stores of a pipeline with no "
                     "depth attachment instead of refusing it; the rest of that build is the base "
                     "image's own",
        "also_changed": "the driver source is the userland HEAD, which carries the "
                        "minimumLinearTextureAlignmentForPixelFormat: override the frozen library "
                        "was built without",
        "build_commands": commands, "source_sha256": sources,
        "inject_conf": INJECT.strip(),
        "jobs_sha256": hashlib.sha256(jobs).hexdigest(), "probe": PROBE, "varstore_show": VARSTORE_SHOW,
        "skeleton_appended": appended, "jobs_dropped": sorted(JOBS_DROP), "job_env": [f"{n}:{k}={v}" for n, k, v in JOB_ENV],
        "jobs_effective": jobs_effective, "jobs_effective_count": len(jobs_effective),
        "redwood_diag": REDWOOD_DIAG,
        "changes": changes,
        "dirty_worktree": bool(dirty), "worktree_status": dirty,
        # A round can change more than the one variable its request names. Anything passed here is
        # carried into the archive so the round is read as what it actually ran.
        "round_notes": [note.strip() for note in os.environ.get("ROUND_NOTES", "").split(";") if note.strip()],
        "gpu_speed": GPU_SPEED,
        "root_sha256": sha(OUT / "root.apfs"), "root_bytes": (OUT / "root.apfs").stat().st_size,
        "expected_runtime_log": ["redwoodmetal[SpringBoard", "redwoodmetal[backboardd",
                                 "sbmetal26: registration completed device=1",
                                 "MiniIOMobileFramebuffer:", "RedwoodGPU: submission"],
        "must_not_appear": ["incompatible architecture", "unrecognized selector",
                            "OS_REASON_COREANIMATION", "nowhere for that store to go"],
        "protected_verified": protected,
    }
    # The manifest has to say which sources this pack read. quiet20 is unaccountable for exactly one
    # reason: its manifest carried no `sources` section, so nothing recorded whether the driver in the
    # image came from the tree that has the dealloc prints. A pack that cannot name its inputs is not
    # written at all, rather than left for somebody to reconstruct later.
    required = [*SHIM_SOURCES, *DRIVER_SOURCES, *DRIVER_INCLUDES,
                "tools/mesa/air/air_metal.c", "tools/mesa/air/air_to_nir.c"]
    absent = [name for name in required if not report.get("sources", {}).get(name)]
    if not report.get("sources") or absent:
        raise SystemExit("the manifest would not record the build inputs, missing: "
                         + (", ".join(absent) if absent else "the whole sources section")
                         + f"\n(the kernel commit is {report.get('kernel', {}).get('commit', '?')})")
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in
                      ["variable", "new_shim_sha256", "new_driver_sha256", "new_air_sha256",
                       "driver_sha256", "air_sha256", "root_sha256", "root_bytes"]}, indent=2))


if __name__ == "__main__":
    main()
