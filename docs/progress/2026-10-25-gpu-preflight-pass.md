# GPU 安全预检通过轮（2026-10-25）

`handoff-m-bit-r1.bin` 把阶段 14 的安全预检判据从「SCTLR 非零」改成「M 位置位」。本轮判据通过，执行路径第一次越过了 r5 那轮被拒绝的位置，停在 `secure preflight-only mode` 的设计停止点上。原始日志与命令记录见 [证据清单](evidence/2026-10-25-gpu-preflight-pass/MANIFEST.md)。

## 1. 运行身份

| 项 | 值 |
|---|---|
| 内核 | `out/handoff-mach-mbit`，19,193,896 B，`d80dec00b80a422b8b1108da28e074f711ddfcc8f1dc5d20379043b6e99672fc` |
| payload | `out/handoff-m-bit-r1.bin`，28,414,280 B，`4243d802bcd5580951afb90a5ea4611d4abaef6e6962c1d98c3458707f5f35b0` |
| 根盘 | `out/handoff-ui-gen80000.apfs`，9,220,096 B，`582b9fb28693ade94e0e374b3e55870ef986cea0a8660fc3e39d27b59f5c376e` |
| cmdline | `debug=0x8 rd=md0 debug=0x10e cpus=1 bootcpu=7 epoch=1792875888 adreno8=14 adreno8_pause=0 adreno8_watch=0 adreno8_keep=1 adreno8_return=0 adreno8_speed=1 adreno8_secure_preflight=1` |
| 内核版本串 | `Darwin Kernel Version 22.5.0: Sat Oct 24 21:03:20 UTC 2026; root:xnu-8796.121.2[xnu-8796.121.2-dirty]/BUILD/obj/DEVELOPMENT_ARM64_BCM2837` |
| 日志 | `s009.log`，73,278 B，1,196 行，`e2c9ccfbfe0f7dfe092b149b19895d554ae49d673cb2a79d7846321079c60ad1` |

运行前 LK 只读确认为 `product: annibale`、`current-slot: a`；`reboot` 后 17.4 秒回到 loader，`build-id 4f6ab13bdbab08314745e04ad77fcc8d6967e1d6`、`result: idle`。

## 2. 阶段 9 至 13 与 r5 一致全部通过

```
adreno8: 9: fw/gen80000_gmu.bin: 88896 bytes in the image of /dev/md1
adreno8: 9: 6 firmware reservations, 0x76084 bytes
adreno8: 9: gmu log IOVA 0x60002000: 4 mapped 4 KiB pages; XNU page size 0x4000
adreno8: 9: gmu hfi IOVA 0x60006000: 4 mapped 4 KiB pages; XNU page size 0x4000
adreno8: 9: smmu idr0 (0x3da0020) = 0x4c017e18
adreno8: 9: smmu idr1 (0x3da0024) = 0x40000015
adreno8: 9: SMMU: 24 stream match registers, 21 contexts, 32 pages of 0x1000 before the contexts' own
adreno8: 9: smmu idr2 capabilities (0x3da0028) = 0x5511
adreno8: 9: smmu scr0 (0x3da0000) = 0x2e0406
adreno8: 9: IDR0.ATOSNS=1; hardware translation operations unavailable
adreno8: 9: 128 page mappings verified by software table walk
adreno8: 9: gmu translation enabled: stream 5, context 2, root PA 0x8cb124000
adreno8: 9: completed
adreno8: 10: about to write gmu hold CM3 in reset for firmware loading at 0x3d7e000: 0x1
adreno8: 10: GMU firmware loaded: 0x15a50 bytes verified
adreno8: 10: completed
adreno8: 11: SCM 0x42000601 returned 0, answer 0x1
adreno8: 11: SCM 0x42002801 returned 0, answer 0
adreno8: 11: about to write gmu ao interrupt mask at 0x3d8ec18: 0xffffffff
adreno8: 11: about to write gmu gmu2host interrupt mask at 0x3d7e64c: 0xffffffff
adreno8: 11: about to write gmu ao interrupt clear at 0x3d8ec10: 0xffffffff
adreno8: 11: about to write gmu gmu2host interrupt clear at 0x3d7e644: 0xffffffff
adreno8: 11: about to write gmu initial RPMh power state at 0x3d7dfa4: 0xf
adreno8: 11: about to write gmu falnext intf at 0x3d7dfb4: 0x1
```

`9: 128 page mappings verified by software table walk` 与 `10: GMU firmware loaded: 0x15a50 bytes verified` 两行与 r5 那轮相同。

## 3. 阶段 14：从 SMR／S2CR 采样到预检通过

```
adreno8: MEM_ALLOC kind 5 handle 0x5 flags 0x1007 size 0x138000 align 0
adreno8: 14: about to read smmu cb preflight at 0x3dc3000
adreno8: 14: smmu cb preflight (0x3dc3000) = 0x96cc51a
adreno8: 14: about to read smmu smr sample at 0x3da0800
adreno8: 14: smmu smr sample (0x3da0800) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0804
adreno8: 14: smmu smr sample (0x3da0804) = 0x80000005
adreno8: 14: about to read smmu s2cr sample at 0x3da0c04
adreno8: 14: smmu s2cr sample (0x3da0c04) = 0x302
adreno8: 14: preflight routing sample: match 1 smr 0x80000005 s2cr 0x302
adreno8: 14: about to read smmu smr sample at 0x3da0808
adreno8: 14: smmu smr sample (0x3da0808) = 0
adreno8: 14: preflight routing sample: match 2 smr 0 invalid; s2cr not read
adreno8: 14: about to read smmu smr sample at 0x3da080c
adreno8: 14: smmu smr sample (0x3da080c) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0810
adreno8: 14: smmu smr sample (0x3da0810) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0814
adreno8: 14: smmu smr sample (0x3da0814) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0818
adreno8: 14: smmu smr sample (0x3da0818) = 0
adreno8: 14: about to read smmu smr sample at 0x3da081c
adreno8: 14: smmu smr sample (0x3da081c) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0820
adreno8: 14: smmu smr sample (0x3da0820) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0824
adreno8: 14: smmu smr sample (0x3da0824) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0828
adreno8: 14: smmu smr sample (0x3da0828) = 0
adreno8: 14: about to read smmu smr sample at 0x3da082c
adreno8: 14: smmu smr sample (0x3da082c) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0830
adreno8: 14: smmu smr sample (0x3da0830) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0834
adreno8: 14: smmu smr sample (0x3da0834) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0838
adreno8: 14: smmu smr sample (0x3da0838) = 0
adreno8: 14: about to read smmu smr sample at 0x3da083c
adreno8: 14: smmu smr sample (0x3da083c) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0840
adreno8: 14: smmu smr sample (0x3da0840) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0844
adreno8: 14: smmu smr sample (0x3da0844) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0848
adreno8: 14: smmu smr sample (0x3da0848) = 0
adreno8: 14: about to read smmu smr sample at 0x3da084c
adreno8: 14: smmu smr sample (0x3da084c) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0850
adreno8: 14: smmu smr sample (0x3da0850) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0854
adreno8: 14: smmu smr sample (0x3da0854) = 0
adreno8: 14: about to read smmu smr sample at 0x3da0858
adreno8: 14: smmu smr sample (0x3da0858) = 0
adreno8: 14: about to read smmu smr sample at 0x3da085c
adreno8: 14: smmu smr sample (0x3da085c) = 0
adreno8: 14: preflight routing sample at t=28100662812ns: scanned 24, valid 1, 0 on the candidate route or context 3; HLOS-side conditions are satisfied at the sample time
adreno8: 14: about to read smmu gmu route check at 0x3da0804
adreno8: 14: smmu gmu route check (0x3da0804) = 0x80000005
adreno8: 14: about to read smmu gmu route check at 0x3da0c04
adreno8: 14: smmu gmu route check (0x3da0c04) = 0x302
adreno8: 14: secure preflight: stream 2 match 2 context 3 satisfied the HLOS-side conditions at the sample time
adreno8: secure preflight-only mode: START stops here without MP_ASSIGN or MEM_ALLOC reply
```

24 个 stream match register 采样里只有索引 1（`0x3da0804`）非零，值为 `0x80000005`，对应 s2cr `0x302`；其余全为 0。CB3 的 SCTLR 仍读作 `0x96cc51a`，M 位为 0，判据按 M 位判断为通过。

与上一轮 cbscan 的交叉验证：阶段 9 打印的 `context 2, root PA 0x8cb124000` 与 cbscan-r2 post-step-9 读到的 CB2 TTBR0 low `0xcb124000` 一致，两条独立路径对上。

## 4. 停止点与归因

```
adreno8: START resource request 20 failed (11 words)
adreno8: 14: FAILED; the steps after it are not attempted
adreno8: keeping everything up (adreno8_keep): the GMU's firmware goes on running and answering
adreno8: over; the system goes on starting
```

`request 20 failed` 由 preflight-only 模式直接带出：该模式按设计不回 MP_ASSIGN、不回 MEM_ALLOC，START 的资源请求等不到回应，于是失败并终止后续步骤。这不是新的硬件问题。

## 5. GMU 健康指标

```
adreno8: 14: CM3 reset 0, boot config 0x2, config 0x4012, GMU clock branch 0x8002001, source 0x100000
adreno8: 14: SMMU fault check: no fault bits set
adreno8: 14: what the GMU says now: init result 0x100, hfi 0x1, gmu2host info 0 mask 0xffffffff, ao interrupts 0, fence 0, power/clk 0x3
adreno8: 14: RSC status 0, sequence busy 0
adreno8: 14: HFI queue 0 status 1, read 292, write 292
adreno8: 14: HFI queue 1 status 1, read 128, write 128
adreno8: 14: HFI queue 2 status 1, read 0, write 0
adreno8: 14: the GMU's log, last 24 lines of 56 it wrote:
```

- SMMU 无 fault 位
- 两条有流量的 HFI 队列读指针与写指针相等（0 号 292/292、1 号 128/128），队列已排空
- `RSC status 0, sequence busy 0`，GMU 侧没有挂起的序列
- `init result 0x100`、`hfi 0x1`，GMU 固件在运行
- GMU 自己写了 56 行日志，最后 24 行出现在本轮日志里（`log 32` 至 `log 55`），内容为重复的 `00000021`／`00000004` 轮次记录

## 6. 未决：通道失联的两个条件分不开

本轮以 0.5 秒间隔抓日志，共 9 次快照、持续 4.71 秒，通道没有失联。run 结束后单独查询 `result` 仍是 0.02 秒返回 `running 0 0`。约两分钟后（05:55:23Z）再次探测：`fastboot devices` 仍列 `xnuloader`，`getvar result`／`product`／`build-id` 各 30 秒超时，通道失联。

与 20:56 那次 cbscan-r2 相同，本轮末尾也有 `adreno8: GPU probe requires host cold reset before reusing kernel memory`。目前两个条件都还没被排除：

- 内核 panic 后进入 cold-reset 收尾路径
- 运行期间高频执行 `oem log` + `get_staged`

判别办法：在一轮里先按 0.5 秒间隔抓 10 秒，然后停止抓日志、保持在线 60 秒，期间每 15 秒只发一次 `getvar result`。若通道在完全不抓日志的条件下仍然失联，条件落在 cold-reset 收尾路径上；若保持在线，条件指向高频取日志。

逐次运行的收尾日志与恢复方式见 [panic 之后通道无应答记录](../analysis/2026-10-25-loader-usb-after-panic.md)。

## 7. 设备状态

本轮结束后未 reboot。内核 panic 在 `Process 1 exec of /sbin/launchd failed, errno 2`（小根盘里没有 launchd），与 GPU 无关。通道失联需要冷启动恢复。

## 8. 下一步

封装方正在装配 `adreno8_secure_preflight=2` 的 payload，那一步会做一次 MP_ASSIGN 交接。顺序仍为 `oem ramdisk` → stage 根盘 → stage payload → `oem run`。