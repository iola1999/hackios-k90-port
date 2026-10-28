# 2026-10-28 round D 归档说明

回答[运行协议](../plan/k90auto-run-protocol.md) §5 要求的六项「这一轮跑的是什么」：内核、驱动、AIR 库、作业集合、手势脚本、探针版本。证据目录是 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundd/`。本文件由 desktop 抄录维护，数据来源是 device 的打包回报与收尾回报。round D 是 round C 载荷的零改动重跑（lead 10-28 放行，task-21，device 执行）：同一份 payload `ebdca4adfc9fb5f4…`（25,437,256 B，device 校验通过后原样复用）、同一份内核 `cf1502f5632284af…`、同一份 apfs（root `e36caefb…`）、同一份 jobs（`a4af9a9f…`+`88326d5e…` 两项），roundd 的 manifest 从 roundc 逐字节复制（`91859058…`）。目的：分开「翻转来自内核」与「翻转来自轮次间变化」；两种结果都有用——又是冻结就与 round C 构成 2/2，是循环就说明形态轮间可变、交接文档把两种形态当成由驱动决定的稳定形态这个框架不成立，且 `lr`／`x0`／`x1`／`x2` 第一次有数据。

填写规则：

- device 宣布收尾之前不读轮次目录；读了必须标 partial 与截至的快照号（协议 §5）。打包字段在 device 打包回报后填，收尾读数在 device 收尾回报后填。
- 身份期望全部等于 round C 原值，逐项对照 [round C 归档说明](2026-10-28-roundc-archive.md) 的对应节；任何一项与期望不符：停下报 lead。
- bad access 与 `tl: td` 的判读口径、`lr` 三步归属、`is_saved_state64` 排除项、帧数三口径与 crashes 列新旧口径，沿用 round C 骨架 §7 的原文，本文件不重抄。

## 1. 六项身份（device 回报后抄实测）

- 内核：期望 `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492`、20,210,232 字节、源码提交 `5c9f563`；`manifest.kernel` 实测 `________`。
- 驱动：期望 `9d66dd36…`；`pack.driver_sha256` `________`；apfs 解出 `________`。pack 段的 `expected_*` 字段是 roundb 期历史快照（`make-payload.py:97` `pack = dict(pack_record)` 逐字复制），读法按 round C 骨架 §2 的注记。
- AIR 库：期望 `d7b9ced5…`（带逐帧计时插桩，fps 与帧间隔引用带这个前提，见 round C 骨架 §3）；`pack.air_sha256` `________`。
- 作业集合：期望 `jobs_effective` 36 条、`jobs_dropped` 只有 `com.apple.appprotectiond.plist`；实测 `________`。
- 手势脚本：期望 `rc.jobs.freeze` 原样（`jobs_source.sha256` `a4af9a9f…` 且 `jobs_sha256` `88326d5e…`，两项同时成立才算）；实测 `________`。
- 探针版本：期望 lsprobe 源 digest `85311cac…`、二进制 `54697751…`；实测 `________`。

## 2. pack 核对与收尾读数

- payload：期望 `ebdca4adfc9fb5f4…`（零改动重跑，出现重建 payload 即停下报 lead）；`pack.root_sha256` `________`（期望 `e36caefb…`）、`pack.gpu_speed` `________`（期望 3）。
- 收尾读数（device 宣布收尾后抄）：`summary.py --verify` `________`；`gestures.py` `________`；`round-stats.py` 三段 `________`；`reboot.json` 四字段 `________`；summary 表行原样 `________`。
- 关键新行：bad access 行与 `tl: td` 行 `________`；覆盖限制同 round C——打印进入条件限定 backboardd 与 SpringBoard（`sleh.c:2107-2108`），0 条读作「这两个进程零故障」。
- 形态判定（本轮目的）：冻结（帧号连续、`exited code` 0 条、提交最终永久停止）还是循环（多代 bbd 段错误、按 `exited code` 的 pid 集合分代）`________`；bad access 若有数据，按 round C 骨架 §7 的三条判据与 `lr` 三步归属填 `________`。
- 时间线核对（本轮如再有容器或构建窗口，按 round C 骨架 §7 的办法核对并写出换算）`________`。
