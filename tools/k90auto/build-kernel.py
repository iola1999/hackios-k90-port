#!/usr/bin/env python3
"""Build the kernel of the kernel submodule's HEAD commit in the kbuild container.

usage: tools/k90auto/build-kernel.py NAME

The committed tree (git archive of HEAD, so uncommitted edits are left out) is applied to Apple's
sources in the container, the container's expanded tree is brought to exactly that input, and the
kernel is built there. Results: hackios-xnu-kernel/out/handoff-mach-NAME and, in the local output
directory ($K90_EVIDENCE, default docs/progress/evidence/k90auto, ignored by Git), kernel-NAME/ with
the input archive, the manifest of every source file, the build log and kernel.json.
Run from the top of the workspace.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile

name = sys.argv[1]
assert re.fullmatch(r"[a-z0-9-]+", name)
root = Path("hackios-xnu-kernel")
evidence = Path(os.environ.get("K90_EVIDENCE", "docs/progress/evidence/k90auto"))
base = evidence / ("kernel-" + name)
base.mkdir(parents=True)
(base / "source").mkdir()
kernel = root / "out" / ("handoff-mach-" + name)
assert not kernel.exists()
commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
with (base / "input.tar").open("wb") as stream:
    subprocess.run(["git", "-C", str(root), "archive", commit, "xnu"], stdout=stream, check=True)
with tarfile.open(base / "input.tar") as archive:
    archive.extractall(base / "source", filter="data")
files = {str(p.relative_to(base / "source")): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (base / "source").rglob("*") if p.is_file()}
(base / "source-manifest.json").write_text(json.dumps({"commit": commit, "files": files}, indent=2) + "\n")
prefix = "/work/k90auto/"
subprocess.run(["docker", "exec", "kbuild", "mkdir", "-p", prefix], check=True)
subprocess.run(["docker", "cp", str(base / "source/xnu"), "kbuild:" + prefix + "input-" + name], check=True)
subprocess.run(["docker", "exec", "-w", prefix, "kbuild", "env", "XNU_URL=file:///work/xnu-tag-source",
                "bash", "input-" + name + "/apply.sh", "reference-" + name], check=True)
sync = r'''from pathlib import Path
import hashlib,json,shutil,sys
name=sys.argv[1]
prefix=Path('/work/k90auto')
ref=prefix/('reference-'+name); expanded=Path('/work/repo/xnu-src/xnu-8796.121.2'); backup=prefix/('prior-'+name)
def listing(base):
    return {str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*')
            if p.is_file() and not set(p.relative_to(base).parts).intersection({'.git','BUILD'})}
r,e=listing(ref),listing(expanded)
changed=[p for p,h in r.items() if e.get(p)!=h];extra=sorted(set(e)-set(r));assert not extra,extra
for f in changed:
    source=expanded/f
    if source.exists():
        target=backup/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    target=expanded/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ref/f,target)
assert listing(expanded)==r
(prefix/('reference-'+name+'.json')).write_text(json.dumps({'reference_count':len(r),'changed':changed},indent=2)+'\n')
print('All source inputs match:',len(r),'updated',len(changed))
'''
subprocess.run(["docker", "exec", "-i", "kbuild", "python3", "-", name], input=sync, text=True, check=True)
subprocess.run(["docker", "cp", "kbuild:" + prefix + "reference-" + name + ".json", str(base / "reference-diff.json")], check=True)
# (the container's checkout of the kernel repository, whose xnu-build.sh builds, follows the same commit)
subprocess.run(["docker", "exec", "-w", "/work/repo", "kbuild", "git", "fetch", "/src", commit], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["docker", "exec", "-w", "/work/repo", "kbuild", "git", "merge", "--ff-only", "FETCH_HEAD"], check=True,
               stdout=subprocess.DEVNULL)
with (base / "build.log").open("wb") as stream:
    subprocess.run(["docker", "exec", "-w", "/work/repo", "kbuild", "bash", "xnu-build.sh", "-j8",
                    "BUILD_DSYM=0", "KEXT_CREATE_SYMBOL_SET=/bin/true"], stdout=stream, stderr=subprocess.STDOUT, check=True)
subprocess.run(["docker", "cp", "kbuild:/work/repo/xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/"
                "mach.development.bcm2837.unstripped", str(kernel)], check=True)
record = {"commit": commit, "kernel": {"path": str(kernel), "bytes": kernel.stat().st_size,
          "sha256": hashlib.sha256(kernel.read_bytes()).hexdigest()}}
(base / "kernel.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record), flush=True)
