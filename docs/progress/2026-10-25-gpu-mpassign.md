# GPU 安全交接轮（mode 2，2026-10-25）

`adreno8_secure_preflight=2` 在本轮做了一次真实的 MP_ASSIGN 交接：78 个 GPU 页面的归属交给 CP_PIXEL，4 个批次的 SCM 调用全部返回 `0`、answer `0`。MEM_ALLOC 仍按设计不回包。原始日志 `logs/m2/s018.log`（89,097 B）。

## 1. 运行身份

| 项 | 值 |
|---|---|
| 内核 | `out/handoff-mach-mbit`，19,193,896 B，`d80dec00b80a422b8b1108da28e074f711ddfcc8f1dc5d20379043b6e99672fc` |
| payload | `out/handoff-m2-r1.bin`，28,414,280 B，`982bb0c2d51a92d3346e8881b0ec9f1d9d22646c6b8933600f1c337696661f4f` |
| 根盘 | `out/handoff-ui-gen80000.apfs`，9,220,096 B，`582b9fb28693ade94e0e374b3e55870ef986cea0a8660fc3e39d27b59f5c376e` |
| cmdline | `debug=0x8 rd=md0 debug=0x10e cpus=1 bootcpu=7 epoch=1792907792 adreno8=14 adreno8_pause=0 adreno8_watch=0 adreno8_keep=1 adreno8_return=0 adreno8_speed=1 adreno8_secure_preflight=2` |
| 日志 | `s018.log`，89,097 B |

运行前 LK 为 `product: annibale`、`current-slot: a`；`reboot` 后 +16.9 秒回 `xnuloader`，`build-id 4f6ab13bdbab08314745e04ad77fcc8d6967e1d6`、`result: idle`。`oem ramdisk` 后 `max-download-size` 为 `0xffffffff`；根盘上传 `OKAY [ 0.231s]`，payload 上传 `OKAY [ 0.710s]`。

## 2. 预期顺序逐条核对

八条全部出现，前五条与上一轮相同：

```
adreno8: MEM_ALLOC kind 5 handle 0x5 flags 0x1007 size 0x138000 align 0
adreno8: 14: about to read smmu cb preflight at 0x3dc3000
adreno8: 14: smmu cb preflight (0x3dc3000) = 0x96cc51a
adreno8: 14: preflight routing sample at t=28100662812ns: scanned 24, valid 1, 0 on the candidate route or context 3; HLOS-side conditions are satisfied at the sample time
adreno8: 14: secure preflight: stream 2 match 2 context 3 satisfied the HLOS-side conditions at the sample time
```

交接与批次部分原文：

```
adreno8: MP_ASSIGN argument page at 0x8cb784000
adreno8: secure handover attempted: 78 pages merge into 78 data regions plus 3 table pages, 4 logical MP_ASSIGN batches
adreno8: MP_ASSIGN plan: batch 0 table, permissions HLOS read/write and CP_PIXEL read, argument page 0x8cb784000, 3 regions
adreno8: MP_ASSIGN batch 0 table: 3 regions, 2 permission records, 0 top-level SCM calls before
adreno8: MP_ASSIGN batch 0 table returned 0, answer 0, 1 top-level SCM calls (A6 interrupted continuation SMCs not counted)
adreno8: MP_ASSIGN plan: batch 1 data, permissions CP_PIXEL read/write, argument page 0x8cb784000, 32 regions
adreno8: MP_ASSIGN batch 1 data: 32 regions, 1 permission records, 1 top-level SCM calls before
adreno8: MP_ASSIGN batch 1 data returned 0, answer 0, 2 top-level SCM calls (A6 interrupted continuation SMCs not counted)
adreno8: MP_ASSIGN plan: batch 2 data, permissions CP_PIXEL read/write, argument page 0x8cb784000, 32 regions
adreno8: MP_ASSIGN batch 2 data: 32 regions, 1 permission records, 2 top-level SCM calls before
adreno8: MP_ASSIGN batch 2 data returned 0, answer 0, 3 top-level SCM calls (A6 interrupted continuation SMCs not counted)
adreno8: MP_ASSIGN plan: batch 3 data, permissions CP_PIXEL read/write, argument page 0x8cb784000, 14 regions
adreno8: MP_ASSIGN batch 3 data: 14 regions, 1 permission records, 3 top-level SCM calls before
adreno8: MP_ASSIGN batch 3 data returned 0, answer 0, 4 top-level SCM calls (A6 interrupted continuation SMCs not counted)
adreno8: secure handover complete: 78 pages owned by CP_PIXEL after 4 top-level MP_ASSIGN SCM calls, A6 interrupted continuation SMCs not counted, retained until cold reset; no MEM_ALLOC reply
adreno8: secure allocation experiment ends here: no MEM_ALLOC reply is built, START fails on purpose
adreno8: START resource request 20 failed (11 words)
```

## 3. 页数与批次核对

`78 pages merge into 78 data regions plus 3 table pages, 4 logical MP_ASSIGN batches`，即 N=78、M=3、K=4。

| 批次 | 类型 | region 数 | region 长度 | 权限 | 调用前累计 SCM | 返回 |
|---|---|---|---|---|---|---|
| 0 | table | 3 | 16384 | HLOS read/write 与 CP_PIXEL read | 0 | `returned 0, answer 0`，累计 1 |
| 1 | data | 32 | 16384 | CP_PIXEL read/write | 1 | `returned 0, answer 0`，累计 2 |
| 2 | data | 32 | 16384 | CP_PIXEL read/write | 2 | `returned 0, answer 0`，累计 3 |
| 3 | data | 14 | 16384 | CP_PIXEL read/write | 3 | `returned 0, answer 0`，累计 4 |

- data 三类合计 32 + 32 + 14 = **78**，与 N 一致
- table 的 3 个 region 与 M 一致
- 81 个 region 条目的地址互不重复，长度全部为 16384
- 顶层 SCM 调用计数逐批加 1，最后一批结束为 4，与 K 一致
- 参数页地址 `0x8cb784000` 在各批中相同

## 4. 失败分支未出现

`secure pages retained until cold reset` 与 `secure allocation failed; retain GPU memory until cold reset` 在整份日志里出现 0 次。

`retained until cold reset` 这个短语出现在交接完成行里（`… retained until cold reset; no MEM_ALLOC reply`），含义是这 78 页由 CP_PIXEL 持有到冷启动为止，与失败分支的措辞不同。

## 5. 失联判别

两段式实验：第一段 0.5 秒间隔抓日志 10 秒，18 次快照全部成功，日志在 1.24 秒后稳定在 89,097 字节；随后停手 60 秒，期间每 15 秒只发一次 `getvar result`，不取任何日志。

| 时刻 | 命令 | 结果 |
|---|---|---|
| +25 秒 | `getvar result` | `result: running 0 0` |
| +40 秒 | `getvar result` | `result: running 0 0` |
| 约 +55 秒发出 | `getvar result` | 超时（60 秒上限，回落到 +115 秒才打印） |
| 约 +70 秒发出 | `getvar result` | 超时 |
| 第二段 | `oem log` + `get_staged` | 超时，`after60.log` 为 0 字节 |

在完全不抓日志的窗口里通道仍然失联，因此「高频 `oem log`／`get_staged` 导致失联」这个条件可以排除。剩下的条件与 `adreno8: GPU probe requires host cold reset before reusing kernel memory` 同源的收尾路径有关，该行在本轮末尾同样出现。失联发生在 `oem run` 之后约 40 至 55 秒。

## 6. 失联后 `reboot` 的实测

通道失联后发 `fastboot -s xnuloader reboot`（90 秒上限，合并两个流）：超时，无任何部分输出。随后以 0.5 秒间隔轮询设备 75 秒，设备**从未从 USB 掉线**，一直以 `xnuloader` 枚举；再查 `getvar result`（25 秒上限）仍超时，ioreg 中设备仍在。

两种可能的失联方式里，本轮落在「手机不动」这一支：命令没有被 loader 取走，`reboot` 无法恢复，只能冷启动。这与「loader 仍在收命令、只是应答被丢」的情形不同。

## 7. `START resource request 20 failed` 的归因

```
adreno8: secure allocation experiment ends here: no MEM_ALLOC reply is built, START fails on purpose
adreno8: START resource request 20 failed (11 words)
```

本轮按设计不构造 MEM_ALLOC 回包，START 的资源请求 20 等不到回应，于是失败。这一行是实验模式的预期输出，不是硬件异常：

```
adreno8: 14: SMMU fault check: no fault bits set
adreno8: 14: what the GMU says now: init result 0x100, hfi 0x1, gmu2host info 0 mask 0xffffffff, ao interrupts 0, fence 0, power/clk 0x3
adreno8: 14: RSC status 0, sequence busy 0
adreno8: 14: HFI queue 0 status 1, read 292, write 292
adreno8: 14: HFI queue 1 status 1, read 128, write 128
adreno8: 14: HFI queue 2 status 1, read 0, write 0
```

## 8. 下一步

secure 页面的归属已交给 CP_PIXEL，剩下两件事：把 secure 页表翻译安装到 CB3，以及在 MEM_ALLOC 路径上真正回包。回包之后 `START resource request 20` 才有可能拿到回应。