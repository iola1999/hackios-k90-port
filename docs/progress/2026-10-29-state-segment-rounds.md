# 2026-10-29 晚间 `state` 段分段三轮

这一批按[下一轮方案](../plan/2026-10-29-next-round-plan.md)起轮，目标是把慢 draw 在 `draw_vbos<>` 的 `state` 段里的落点逐层分开。一批上限 3 轮，每轮只换 AIR。审查意见与第三轮要补的探针见[晚间会话审查](../analysis/2026-10-29-evening-session-review.md)。

## 1. 身份

三轮共用的产物，与方案 §2.1 相同：

| 项 | 值 |
|---|---|
| 内核 | `f055cc0a…` |
| 驱动 | `529d19bf…` |
| 注入库 | `1d727833…` |
| 作业 | `rc.jobs.perf-sustain`，`/etc/rc.jobs` 为 `16462e32…` |
| 系统盘 | `system26.apfs`，`SYSTEM_WINDOW=0x300000000` |
| cmdline 追加项 | `gpu_log=1 metal=1 cpufreq=1 fb_threads=2 touch_lat=1` |

| 轮 | 轮次目录 | AIR | 载荷 |
|---|---|---|---|
| 1 | `kernel-12377-attr26-diag3x-statecursor2` | `57fdb85c…` | `b4b9d6ab…`，25,474,120 字节 |
| 2 | `kernel-12377-attr26-diag3x-statecursor3` | `b303726d…` | `2b93bac4…`，25,470,024 字节 |

## 2. 设备

- 21:09 设备在 LK，`slot-retry-count:a` 读到 1，`set_active a` 后为 7，`slot-unbootable:a`／`b` 都是 `no`。
- 21:11 loader 枚举，`result idle`、`ramdisk-state idle 0 0 0`、`ramdisk-protocol 1`、`build-id unknown`，起第一轮。
- 第二轮之前走[引导目标切换 SOP](../plan/device-boot-target-sop.md) §5.3 的整轮重启：B 槽 Android 24 秒到 `sys.boot_completed=1`，Android 到 LK 6 秒，LK 到 loader 12 秒，`set_active a` 后计数回到 7。
- 两轮都由 `run-auto.py` 在 80.0 秒判定帧流停止后收尾，带回 idle loader；22:50 前后复查仍是 `idle`、`idle 0 0 0`、`xnuloader`。

## 3. 第一轮：`statecursor2`

判据零全部满足：`redwood lib loaded pid 38 name backboardd` 出现；`fd draw calls` 打到 5,000；`fd draw seg slow: state` 22 条，每条前面都有配对的 `fd draw state segs`。

- 判据一：22 条全部满足 D1，`prog_state` 占 `T` 的 99.81%～100%，D2、D3 不成立。按方案 §4.1，第二轮在 `prog_state` 里插子段。
- 慢 draw 的 `wall` 50,806～1,768,524 µs，`cpu` 45～481 µs，`flt` 10～369。
- 判据二：`fd bo prefault slow` 0 条，按 P2 记。
- 判据三：3 份线程快照（draw 54 在 394 ms、draw 76 在 1,714 ms、draw 4796 在 540 ms），pc 都在 `libsystem_kernel`，1 条在 CoreFoundation，没有一条在 AIR 里，绘制线程没有认出来。逐线程解名见[晚间会话审查](../analysis/2026-10-29-evening-session-review.md) §4。
- 末帧 637，此后帧流不再恢复。

## 4. 第二轮：`statecursor3`

相对第一轮只换 AIR：`get_program_state()` 里加 `prog_key`、`prog_fixup`、`prog_lookup`、`prog_variant` 四个子段，补丁是 `hackios-xnu-kernel/tools/mesa/fd6-state-segs-2.patch`。判据零全部满足，`fd draw calls` 打到 6,000。

- 25 条慢 draw 全部落在 `prog_lookup`，即 `ir3_cache_lookup()` 这一次调用，占 `T` 的 99.70%～100%，其余三段合计不到 0.3%。
- 慢 draw 的 `wall` 55,097～2,035,601 µs，`cpu` 43～566 µs，`flt` 14～450，`cpu`／`wall` 不超过 0.004。
- `fd bo prefault slow` 1 条：`0x135bb9880 16384 bytes 101180 us`，日志里紧随其后的那条慢 draw `wall` 196,295 µs，按 P2 记。
- 线程快照 4 份（draw 39、45、5864、5905，336～401 ms）。
- 末帧 771；backboardd 的 `tl: cnt` 除紧接末帧的一条（`1 0 1 1 0`）外全为 0，没有 `rd in` 不配对的 draw，停止时没有 draw 在执行。

两轮的慢 draw 都紧跟在新建 render pipeline 之后，统计见[晚间会话审查](../analysis/2026-10-29-evening-session-review.md) §3。

## 5. 第三轮的准备

`ir3_cache_lookup()` 内部按 `prog_hash`、`prog_search`、`prog_hit`、`prog_shaders`、`prog_build`、`prog_constlen`、`prog_rebuild`、`prog_binning` 八处插点，补丁是 `hackios-xnu-kernel/tools/mesa/prog-lookup-segs.patch`，AIR 编出 `35cc6646…`，`library-baseline.json` 已按 `UPDATE_BASELINE=1` 更新。载荷还没有打包。起轮前要按审查 §5 补三组探针并登记判据。
