#!/usr/bin/env python3
"""Turn a Qualcomm kernel panel node (from the device's own device tree) into a
QCOM-UEFI DisplayDxe Panel XML, the format the Mu-Silicium firmware's RawFiles use.

Kernel DTS command blob:  [type vc dsc eos delay_lo delay_hi] [len] [data...]
UEFI XML command line:    <type> <data bytes...> [<delay>]   (delay trailing, optional)

usage: dts2panelxml.py <merged.dts> <node label> <out.xml> <PanelName>
"""
import re, sys

dts, node, out, panel_name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
lines = open(dts).read().splitlines()
start = next(i for i, l in enumerate(lines) if node + ':' in l)
depth = 0
for end in range(start, len(lines)):
    depth += lines[end].count('{') - lines[end].count('}')
    if depth == 0 and end > start:
        break
block = '\n'.join(lines[start:end + 1])

def prop(name):
    m = re.search(re.escape(name) + r'\s*=\s*(\[[^\]]*\]|<[^>]*>|"[^"]*")\s*;', block, re.S)
    return m.group(1) if m else None

def num(name, default=None):
    v = prop(name)
    if v is None or not v.startswith('<'):
        return default
    hexes = re.findall(r'0x([0-9a-fA-F]+)', v)
    return int(hexes[0], 16) if hexes else default

def bytes_of(name):
    v = prop(name)
    if v is None:
        return []
    return [int(x, 16) for x in re.findall(r'\b[0-9a-fA-F]{2}\b', re.sub(r'[^0-9a-fA-F ]', ' ', v))]

def emit_cmds(bs):
    """kernel 6-byte-header stream -> UEFI per-line form"""
    out, i = [], 0
    while i + 7 <= len(bs):
        typ, delay, ln = bs[i], bs[i + 4] | (bs[i + 5] << 8), bs[i + 6]
        data = bs[i + 7:i + 7 + ln]
        if ln and typ:
            line = '%02X %s' % (typ, ' '.join('%02X' % b for b in data))
            if delay:
                line += ' %d' % delay
            out.append(' ' + line)
        i += 7 + ln
    return out

w, h = num('qcom,mdss-dsi-panel-width'), num('qcom,mdss-dsi-panel-height')
hfp, hbp, hpw = (num('qcom,mdss-dsi-h-front-porch', 64), num('qcom,mdss-dsi-h-back-porch', 64),
                num('qcom,mdss-dsi-h-pulse-width', 32))
vfp, vbp, vpw = (num('qcom,mdss-dsi-v-front-porch', 64), num('qcom,mdss-dsi-v-back-porch', 64),
                num('qcom,mdss-dsi-v-pulse-width', 32))
fps = num('qcom,mdss-dsi-panel-framerate', 60)
clk = num('qcom,mdss-dsi-panel-clockrate', 0)
lanes = num('qcom,mdss-dsi-panic-lanes') or 4  # kernel names it differently per tree; SM8750 panels are 4-lane
dsc_w, dsc_h = num('qcom,mdss-dsc-slice-width', 0), num('qcom,mdss-dsc-slice-height', 0)
dsc_ver = num('qcom,mdss-dsc-version', 0x11)
on = emit_cmds(bytes_of('qcom,mdss-dsi-on-command'))
refresh = fps << 16

xml = f"""<?xml version='1.0' encoding='utf-8'?>
<PanelName>{panel_name}</PanelName>
<PanelDescription>{panel_name} dsc cmd panel ({w}*{h} dsi-timing, from the device tree of the phone)</PanelDescription>
<Group id='Active Timing'>
 <HorizontalActive>{w}</HorizontalActive>
 <HorizontalFrontPorch>{hfp}</HorizontalFrontPorch>
 <HorizontalBackPorch>{hbp}</HorizontalBackPorch>
 <HorizontalSyncPulse>{hpw}</HorizontalSyncPulse>
 <HorizontalSyncSkew>0</HorizontalSyncSkew>
 <HorizontalLeftBorder>0</HorizontalLeftBorder>
 <HorizontalRightBorder>0</HorizontalRightBorder>
 <VerticalActive>{h}</VerticalActive>
 <VerticalFrontPorch>{vfp}</VerticalFrontPorch>
 <VerticalBackPorch>{vbp}</VerticalBackPorch>
 <VerticalSyncPulse>{vpw}</VerticalSyncPulse>
 <VerticalSyncSkew>0</VerticalSyncSkew>
 <VerticalTopBorder>0</VerticalTopBorder>
 <VerticalBottomBorder>0</VerticalBottomBorder>
 <InvertDataPolarity>False</InvertDataPolarity>
 <InvertVsyncPolairty>False</InvertVsyncPolairty>
 <InvertHsyncPolarity>False</InvertHsyncPolarity>
 <BorderColor>0x0</BorderColor>
</Group>
<Group id='Display Interface'>
 <InterfaceType>9</InterfaceType>
 <InterfaceColorFormat>3</InterfaceColorFormat>
</Group>
<Group id='DSI Interface'>
 <DSIBitClockFrequency>{clk}</DSIBitClockFrequency>
 <DSIChannelId>2</DSIChannelId>
 <DSIVirtualId>0</DSIVirtualId>
 <DSIColorFormat>36</DSIColorFormat>
 <DSITrafficMode>1</DSITrafficMode>
 <DSILanes>{lanes}</DSILanes>
 <DSIRefreshRate>0x{refresh:x}</DSIRefreshRate>
 <DSISSCConfig>0</DSISSCConfig>
 <DSICmdSwapInterface>False</DSICmdSwapInterface>
 <DSICmdUsingTrigger>False</DSICmdUsingTrigger>
 <DSIEnableAutoRefresh>True</DSIEnableAutoRefresh>
 <DSIAutoRefreshFrameNumDiv>1</DSIAutoRefreshFrameNumDiv>
 <DSITECheckEnable>True</DSITECheckEnable>
 <DSITEUsingDedicatedTEPin>True</DSITEUsingDedicatedTEPin>
 <DSITEvSyncStartPos>{h}</DSITEvSyncStartPos>
 <DSITEvSyncInitVal>{h}</DSITEvSyncInitVal>
 <DSITEvSyncSelect>0</DSITEvSyncSelect>
 <DSIDSCEnable>True</DSIDSCEnable>
 <DSIDSCMajor>{dsc_ver >> 4}</DSIDSCMajor>
 <DSIDSCMinor>{dsc_ver & 0xF}</DSIDSCMinor>
 <DSIDSCScr>0</DSIDSCScr>
 <DSIDSCProfileID>0x0</DSIDSCProfileID>
 <DSIDSCSliceWidth>{dsc_w}</DSIDSCSliceWidth>
 <DSIDSCSliceHeight>{dsc_h}</DSIDSCSliceHeight>
 <DSIControllerMapping>
  00
 </DSIControllerMapping>
 <DSILP11AtInit>True</DSILP11AtInit>
</Group>
<DSIInitSequence>
{chr(10).join(on)}
</DSIInitSequence>
"""
open(out, 'w').write(xml)
print(f'{out}: {w}x{h} @{fps}Hz clk={clk} lanes={lanes} dsc={dsc_ver >> 4}.{dsc_ver & 0xF} slice={dsc_w}x{dsc_h} init_cmds={len(on)}')
