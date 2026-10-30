#!/usr/bin/env python3
"""List the rendering failures one round logged, grouped by kind, without looking at the screen.

usage: tools/k90auto/render-health.py ROUND_DIR [--baseline ROUND_DIR] [--examples N]

Every s*.log is the newest 1.3 MB of the loader's ring, and backboardd's per-frame statistics fill
that in about three minutes, so the snapshots are merged first (summary.merged_log's overlap rule).
A merge step that finds no overlap is counted as a gap: lines may be missing there.

Each line is matched against SIGNATURES, first match wins. A signature names what the failure costs
on screen; the count is over the merged log. Lines from a graphics source (the driver, the compiler
library, QuartzCore's Metal log, MiniIOSurface, the GPU driver) that carry a failure word but match
no signature are listed under "unclassified", so a new kind of failure shows up without editing this
file first. The driver prints some refusals only the first time (RW_ONCE) or at powers of two
(RW_AGAIN), so a count of 1 or a power of two can stand for many more. When the GPU stops, the
last submissions before it and the pipelines the first commits used are printed with their shader
names.

--baseline prints the other round's count beside each row and marks rows only one side has.
Exit code: 0 always; this reports, it does not gate.
"""
import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summary  # noqa: E402

# (kind, regex, what it costs). The regex's first group, when there is one, is kept in the row key, so
# one kind splits by reason ("no drawable: <reason>").
SIGNATURES = [
    ("texture-import", r"Failed to allocate MTLTexture from IOSurface 0x[0-9a-f]+\.\s*(.*)",
     "QuartzCore got no texture for a surface; the layer it backs is not drawn"),
    ("drawable-refused", r"no drawable(?: \(\d+\))?: (.*)",
     "the driver refused a texture over an IOSurface"),
    ("framebuffer-alloc", r"Failed to allocate \[\d+ x \d+\] (.*)",
     "CoreAnimation got no offscreen framebuffer; what it would have drawn there is lost"),
    ("buffer-nil", r"(?:nil buffer from memory: \[[^]]*\],? ?(.*)|(rwa buffer: \d+ bytes left nil.*))",
     "a buffer over caller memory is nil; the image it carries is not drawn"),
    ("command-buffer-error", r"MTLCommandBuffer 0x[0-9a-f]+.* error = (.*)",
     "a command buffer completed with an error; what CoreAnimation does with the frame is its choice"),
    ("dispatch-failed", r"the dispatch failed: (.*)", "a compute dispatch was not run"),
    ("draw-failed", r"the draw failed: (.*)", "a draw was not run"),
    ("command-buffer-failed", r"command buffer failed: (.*)", "the driver failed a command buffer"),
    ("dropped", r"((?:this (?:draw|dispatch) has|is dropped|dropped rather than|refused rather than).*)",
     "an encoded command was dropped"),
    ("pipeline-refused", r"this render pipeline is refused: (.*)",
     "a render pipeline is nil; every draw with it is lost"),
    ("shader-refused", r"AIRFAIL begin (?!hung-|refused-)(\S+ \S+)", "the compiler library refused a shader"),
    ("hung-shader", r"AIRFAIL begin hung-(\S+ \S+)", "a shader of the draw the GPU did not finish (dumped)"),
    ("refused-draw-shader", r"AIRFAIL begin refused-(\S+ \S+)", "a shader of a draw the library refused (dumped)"),
    ("shader-over-cap", r"AIRFAIL over-cap (.*)", "a refused shader too big to dump"),
    ("format-refused", r"(pixel format \d+ is one of Metal's formats packed.*)",
     "the compiler library refused a texture format"),
    ("iosurface-kernel", r"((?:IOSurface\w+ got non-success return from kernel|Mini\w+: selector \d+ not implemented|"
     r"IOSurface\w* failed: e[0-9a-f]+|kIOSurfaceMethod\w+ failed: e[0-9a-f]+).*)",
     "an IOSurface or framebuffer call the kernel does not serve"),
    ("not-implemented", r"((?:not implemented|unsupported|returns nil|; nil$).*)",
     "a Metal feature this driver answers with nil or drops"),
    ("gpu", r"(adreno8: .*(?:timeout failed|submissions closed|hang detected|page ?fault at|GPU fault|"
     r"HFI fatal message).*|THE GPU DID NOT FINISH)", "the GPU stopped or faulted"),
    ("ir3", r"((?:Unhandled ALU op|ir3_context_error|nir_validate|NIR validation failed).*)",
     "the shader compiler hit an unsupported construct"),
    ("crash", r"(\b(?:userabort|usertrap): .*|exited due to .*|Assertion failed.*)", "a process died"),
    ("stall", r"(redwood: stall.*)", "a commit waited past the driver's stall limit"),
]
SIGNATURES = [(kind, re.compile(rx), cost) for kind, rx, cost in SIGNATURES]

# Lines whose source is the graphics stack; only these feed "unclassified".
GRAPHICS = re.compile(r"redwoodmetal\[|^rwa |AIR|\[Metal\]|QuartzCore|CoreAnimation|MiniIOSurface|"
                      r"adreno|RedwoodGPU|IOSurface|ir3|freedreno|redwooddrawable|sbmetal")
FAILURE = re.compile(r"fail|refus|unsupport|not support|cannot|\bnil\b|declin|unhandled|error|invalid|"
                     r"dropped|gave up|not implemented", re.I)
# The module dump that follows an AIRFAIL begin line: base64, one chunk a line.
DUMP_CHUNK = re.compile(r"AIRFAIL [A-Za-z0-9+/=]{16,}$")
GPU_STOP = re.compile(r"HFI fatal message|submissions closed|THE GPU DID NOT FINISH")
SUBMISSION = re.compile(r"^tl: Q \d+ ")
TRACE = re.compile(r"trace commit \d+: .*pipelines(.*)")
SYNC_FAIL = re.compile(r"sync: commit \d+ work \d+ did not finish")
SYNC_DRAW = re.compile(r"sync: commit \d+ work \d+: pipeline ")   # one per draw, said before it runs
HANDLE = re.compile(r"0x[0-9a-f]{6,}")
PIPELINE = re.compile(r"render pipelines: \d+ built, this one \d+ us \((?:ok|refused) (0x[0-9a-f]+)\) "
                      r"vertex (\S+) fragment (\S+)|compute pipeline (0x[0-9a-f]+) is (\S+)")
# Graphics lines that carry a failure word and report nothing wrong.
BENIGN = re.compile(r"error 0$|default_before=nil|MTLCommandBufferStatus: |binary archive|"
                    r"smr \d+ invalid; s2cr not read")

OSLOG = re.compile(r"^\d{4}-\d\d-\d\d (\d\d:\d\d:\d\d)\.\d+[+-]\d{4} ([^\[\s]+)\[(\d+):\d+\] (.*)")
DRIVER = re.compile(r"^redwoodmetal\[(\S+) (\d+)\]: (.*)")
PROC_PID = re.compile(r"^(?:MiniIOSurface: )?([A-Za-z][\w.-]*)\[(\d+)\]")
WATCHED = ("SpringBoard", "backboardd", "Preferences", "iconservicesagent")


def merge(run):
    """The merged log and how many merge steps found no overlap with what came before.

    Every snapshot starts with the same boot section and continues with the ring. A step with no
    overlap means the ring turned over more than once between two pulls; the chunk's boot section is
    already in the text, so only what follows it is appended, and the lines lost in between are gone."""
    text, gaps = "", 0
    for path in summary.log_files(run):
        with open(path, "rb") as f:
            chunk = f.read().decode("utf-8", errors="replace").replace("\x00", "")
        if not text:
            text = chunk
            continue
        cut = summary.overlap(text, chunk)
        if cut == 0:
            gaps += 1
            cut = len(os.path.commonprefix([text[:len(chunk)], chunk]))
            cut = chunk.rfind("\n", 0, cut) + 1
        text += chunk[cut:]
    return text, gaps


def normalize(text):
    """Row key: addresses, surface ids, pids and numbers of four digits or more become placeholders;
    shorter numbers stay, because a pixel format, a selector or a buffer index is what tells two
    refusals apart."""
    text = re.sub(r"0x[0-9a-fA-F]+", "0x_", text)
    text = re.sub(r"(IOSurface|commit|surface) \d+", r"\1 #", text)
    text = re.sub(r"\[\d+(:\d+)?\]", "[#]", text)
    return re.sub(r"\d{4,}", "#", text)[:150]


def scan(base):
    run = os.path.join(summary.round_dir(base), "run")
    text, gaps = merge(run)
    rows = {}
    unclassified = {}
    pids = defaultdict(set)
    first_ts = last_ts = ts = None
    names, before_stop, stopped, sync_fails, sync_draws = {}, [], False, [], []
    for line in text.splitlines():
        if DUMP_CHUNK.search(line):
            continue
        named = PIPELINE.search(line)
        if named:
            if named.group(1):
                names[named.group(1)] = f"{named.group(2)}+{named.group(3)}"
            else:
                names[named.group(4)] = named.group(5)
        if SYNC_DRAW.search(line) and not sync_fails:
            sync_draws.append(line)
        if SYNC_FAIL.search(line):
            sync_fails.append(line)
        if not stopped:
            if GPU_STOP.search(line):
                stopped = True
            elif SUBMISSION.match(line) or TRACE.search(line):
                before_stop.append(line)
        proc, msg = "?", line
        m = OSLOG.match(line)
        if m:
            ts, proc, msg = m.group(1), m.group(2), m.group(4)
            first_ts = first_ts or ts
            last_ts = ts
            pids[proc].add(int(m.group(3)))
        else:
            m = DRIVER.match(line) or PROC_PID.match(line)
            if m:
                proc = m.group(1)
                pids[proc].add(int(m.group(2)))
                msg = m.group(3) if m.re is DRIVER else line
        for kind, rx, cost in SIGNATURES:
            hit = rx.search(msg)
            if hit:
                reason = next((g for g in hit.groups() if g is not None), "")
                key = (kind, proc, normalize(reason))
                row = rows.setdefault(key, {"count": 0, "first": ts, "last": ts, "example": line[:260],
                                            "cost": cost})
                row["count"] += 1
                row["last"] = ts
                break
        else:
            if GRAPHICS.search(line) and FAILURE.search(msg) and not BENIGN.search(msg):
                key = (proc, normalize(msg))
                row = unclassified.setdefault(key, {"count": 0, "example": line[:260]})
                row["count"] += 1
    restarts = {name: sorted(pids[name]) for name in WATCHED if len(pids[name]) > 1}
    hang = None
    if stopped:
        # what was submitted last before the GPU stopped, with the pipeline handles named
        hang = [HANDLE.sub(lambda m: names.get(m.group(0), m.group(0)), line)
                for line in before_stop[-12:] + sync_draws[-8:] + sync_fails]
    return {"bytes": len(text), "gaps": gaps, "first": first_ts, "last": last_ts, "rows": rows,
            "unclassified": unclassified, "restarts": restarts, "hang": hang}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("round")
    ap.add_argument("--baseline")
    ap.add_argument("--examples", type=int, default=1, help="print the first line of each row (0: none)")
    args = ap.parse_args()
    now = scan(args.round)
    old = scan(args.baseline) if args.baseline else None
    print(f"merged log {now['bytes']} bytes, device time {now['first']} .. {now['last']}, "
          f"{now['gaps']} merge gaps")
    for name, ids in now["restarts"].items():
        print(f"restart: {name} ran as {len(ids)} processes {ids}")
    if now["hang"] is not None:
        print("\n== before the GPU stopped: the last submissions and the first commits' pipelines")
        for line in now["hang"]:
            print("   ", line[:300])
    keys = sorted(set(now["rows"]) | set(old["rows"] if old else ()),
                  key=lambda k: (k[0], -now["rows"].get(k, {"count": 0})["count"]))
    kind = None
    for key in keys:
        row = now["rows"].get(key)
        before = old["rows"].get(key, {"count": 0})["count"] if old else None
        if key[0] != kind:
            kind = key[0]
            cost = (row or old["rows"][key])["cost"]
            print(f"\n== {kind}: {cost}")
        count = row["count"] if row else 0
        mark = ""
        if old is not None:
            mark = f"  (baseline {before})" + ("  NEW" if before == 0 else "  GONE" if count == 0 else "")
        span = f" {row['first']}..{row['last']}" if row and row["first"] else ""
        print(f"{count:6d} {key[1]}: {key[2] or '-'}{span}{mark}")
        if row and args.examples:
            print(f"         e.g. {row['example']}")
    if now["unclassified"]:
        print("\n== unclassified graphics lines with a failure word")
        for (proc, key), row in sorted(now["unclassified"].items(), key=lambda kv: -kv[1]["count"])[:40]:
            print(f"{row['count']:6d} {proc}: {row['example'] if args.examples else key}")


if __name__ == "__main__":
    main()
