#!/usr/bin/env python3
"""Verify the loader idle, or recover its existing A slot from identified B-slot Android."""
import json, subprocess, sys, time
from pathlib import Path
base=Path(sys.argv[1]);base.mkdir()
records=[]
# Android needs a moment after the reset before adbd answers: two rounds (bbmetal13, bbmetal15)
# asserted here with no device listed and needed the operator. ADB_WAIT is the bounded wait for it.
ADB_WAIT=40
def call(argv,limit=8):
    started=time.monotonic()
    r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=limit)
    item={"argv":argv,"rc":r.returncode,"output":r.stdout,"seconds":time.monotonic()-started}
    records.append(item);(base/"commands.json").write_text(json.dumps(records,indent=2)+"\n")
    assert r.returncode==0 and "FAILED" not in r.stdout,item
    return r.stdout

def fastboots():
    return [l.split()[0] for l in call(["fastboot","devices"],3).splitlines() if "fastboot" in l]
def adb_devices():
    return [l.split()[0] for l in call(["adb","devices"],3).splitlines() if l.endswith("\tdevice")]
def idle():
    # build-id is recorded, not checked: this loader answers "unknown", and an identity the
    # firmware does not carry says nothing about which build is resident.
    pre=["fastboot","-s","xnuloader"]
    assert "product: xnuloader" in call(pre+["getvar","product"])
    build_id=call(pre+["getvar","build-id"]).strip().splitlines()[0]
    assert "result: idle" in call(pre+["getvar","result"])
    return build_id
if "xnuloader" in fastboots():
    print("loader idle verified (%s); no mode change"%idle());sys.exit(0)
start=time.monotonic()
while not adb_devices():
    assert time.monotonic()-start<ADB_WAIT,"no Android device on adb within %ds"%ADB_WAIT
    time.sleep(2)
selected=[]
for serial in adb_devices():
    pre=["adb","-s",serial,"shell","getprop"]
    if call(pre+["ro.product.device"]).strip()=="annibale":
        assert call(pre+["ro.boot.slot_suffix"]).strip()=="_b"
        selected.append(serial)
assert len(selected)==1, "exactly one annibale Android B slot required"
serial=selected[0];call(["adb","-s",serial,"reboot","bootloader"])
start=time.monotonic()
while serial not in fastboots():
    assert time.monotonic()-start<45,"LK did not enumerate"
    time.sleep(1)
pre=["fastboot","-s",serial]
assert "product: annibale" in call(pre+["getvar","product"])
for variable in ("current-slot","slot-retry-count:a","slot-unbootable:a","slot-successful:a","slot-successful:b"):
    value=call(pre+["getvar",variable])
    if variable=="slot-successful:b": assert "slot-successful:b: yes" in value
call(pre+["set_active","a"]);call(pre+["reboot"])
start=time.monotonic();off=False
while True:
    found=fastboots()
    if serial not in found and "xnuloader" not in found:off=True
    if off and "xnuloader" in found:break
    assert time.monotonic()-start<60,"the loader did not re-enumerate"
    time.sleep(1)
print("identified Android B to LK to existing loader A; %s"%idle())