# round fixguard 归档说明（骨架，修复轮）

回答[运行协议](../plan/k90auto-run-protocol.md) §5 要求的六项「这一轮跑的是什么」：内核、驱动、AIR 库、作业集合、手势脚本、探针版本。证据目录 `docs/progress/evidence/k90auto/kernel-12377-attr26-fixguard/`（轮名由 device 定 label `fixguard`，lead 没有另给名字），payload `out/handoff-12377-attr26-fixguard.bin`。本文件由 desktop 抄录维护，数据来源是 device 的打包回报与收尾回报，desktop 按文末复算命令独立复算核对。与 round F 的唯一差别是 AIR 库：round F 的 AIR 源码加一个 patch `hackios-xnu-kernel/tools/mesa/freedreno-shared-no-shadow.patch`（display，工作区 7,197 B，在 `fd_try_shadow_resource` 入口拒绝 shadow 一个 `is_shared` 的资源；它的说明段含 memmove 归属已定四项、三个行长的映射与「行长是被 map 的 box 的行长」的细化，`diff --git` 之前、`patch(1)` 会跳过、不进树），perf 已重建 AIR（`1be6ebf7…`、14,000,400 B）、device 重打 root 与 payload（AIR 库在 root 镜像的 `/lib/libredwoodair.dylib`，root.apfs 与 payload 的 sha 都是新值），唯一变量是这个 patch。device 打包前有两条强制核验；liveness-watch.sh（`9c31aee`）加 nohup 执行方式是本轮硬门槛（round F 第二次异常的对策）；手册 §5 两条恢复规程（先抢拉环再 stop、每 60 s 核 `commands.jsonl` mtime）本轮起生效。

## 1. 六项身份（期望值；device 重建回报后抄实测）

- 内核：期望与 round F 同（`cf1502f5632284af…`、20,210,232 字节、源码提交 `5c9f563`）；实测 `________`。
- 驱动：期望与 round F 同（`9d66dd36…`）；实测 `________`。
- AIR 库：**本轮变量**——期望 `1be6ebf7…`、14,000,400 字节（perf 重建回报；round F 是 `d7b9ced5…`、13,983,936 字节，带逐帧计时插桩的前提不变），源码 = round F 的 AIR 源码加 `freedreno-shared-no-shadow.patch`；源码摘要按[运行协议](../plan/k90auto-run-protocol.md)的固定取法记。实测 `________`。
- 作业集合：期望与 round F 同（`jobs_effective` 36 条、`jobs_dropped` 只有 `com.apple.appprotectiond.plist`、`jobs_source.sha256` `e6ece111…`、`jobs_sha256` `9a7be5c3…` 镜像内 43 行）。条目 diff 闸的期望（device 定，三句）：条目级 diff 对 round F 镜像零增删（136=136，无新增无删除条目）；内容级差异恰一处＝`/lib/libredwoodair.dylib`；root.apfs 与 payload 的 sha 都是新值、打包后实测填——`dfbc7e48…` 是 round F 的 root sha，在 image-diff 里当 OLD 侧用，**不是**本轮 root 的期望值。实测 `________`。
- 手势脚本：期望与 round F 同（`rc.jobs.freezef`，`a51a085`；探针序列见 [round F 归档说明](2026-10-28-roundf-archive.md) §1）。实测 `________`。
- 探针版本：期望与 round F 同（lsprobe 源 `85311cac…`、二进制 `54697751…`）。实测 `________`。
- payload：期望 = round F 配置换 AIR 后重打，`payload_sha256` 与 `pack.root_sha256` 都是新值（AIR 库在 root 镜像的 `/lib/libredwoodair.dylib`、字节变，root.apfs 内容随之变），sha 由 device 打包后回报。实测 `________`。

## 2. 判据（预先登记，lead 定、device 转发原文照抄）与收尾读数空位

- 总判据原文：「判据我预先写下来：bad access 归零就是故障修掉了，接着看形态是否从循环变成冻结或更好；bad access 不变就是守卫无效，C1 与 C2 两个候选排除，那时上 display 那四处打印，候选从四个减到两个。」
- 三条成功判据原文：「① bad access 归零（对照 round F 的 116 raw／16 唯一、首故障 rel 17.8）；② 桌面仍然画对——拒绝一个本来需要的 shadow 可能让像素画错，所以截图带哈希要有内容变化、不是全黑也不是花屏，这一项用带哈希数法；③ 帧数与 C/D 健康段可比（C/D 是 3611／3620 帧）。」
- 分支原文：「若 ① 过而 ② 或 ③ 不过，那是守卫挡住了一个必要的 shadow，转 display 的候选 1（模板加 PIPE_BIND_SHARED 并把 is_format_supported 查询带上这个位重问）。若 ① 不过，守卫无效，C1 与 C2 排除，那时上 display 那四处打印，候选从四个减到两个。」
- 三种结果的后续动作（lead 裁定原文，10-28 晚）：**三项都通过**（bad access 归零、画面仍然正确、帧数与 C/D 健康段可比）＝故障修好，下一步是冻结这一类的提交停止，以及验收轮（关掉性能插桩后量 55 fps 与满频时长）。**第一项通过而第二或第三项不通过**＝阻止了一个必要的 shadow，转 display 的候选 1（AIR 侧模板加 `PIPE_BIND_SHARED` 并把格式支持查询带上这个位重问）。**第一项不通过**＝两个候选被排除（`fd_resource_get_handle:1136` 与 `fd_resource_uncompress:554`），上打印轮，范围已收窄到 `rwa_texture_read` 一条链，因为 E 与 F 全部 `pipeline seen` 唯一行里 `depth` 全是 0、`rwa_depth_read` 没有对象。
- 挂起项（lead 裁定原文）：v1 到 v2 打印格式改动的对照轮，只在第一项不通过时才做；本条写明它挂起与决定的条件，它是挂起项、没有被排除。
- 判据①的归因限定（lead 定，perf 的机制论证按原文抄）：bad access 归零时，归因对象是「守卫加打印格式改动」这个组合。机制论证由 perf 给到了文件级与函数级两层，原文是：「第二处差异在树里的位置是 `fd_perf_window_add()` 内的计数累加与窗口汇总 printf，加上 `perf_draw.h` 里的计数器声明；这两个文件不含 `shadow`、`copy_rect`、`is_shared`、`bo_get_handle` 任何一处；而故障路径所在的 `freedreno_resource.c` 与它的应用前副本逐行相比只多守卫那 27 行 diff。」
- 判据②的参考数据文件名：device 在用 `fixguard-criterion2-reference.json`（lead 定沿用）。
- 判据②修订原文：「三条测试改成：带哈希数出来的状态数 ≥3、带均值色与 C/D 参考在 ±10% 内、带内方差在参考范围内」；参考基线两侧原文：「通过一侧是 C/D 的带状态（壁纸斜条纹、30,192 个非黑像素、C 与 D 逐位相同），不通过一侧是 round F 的全黑加虚线（1,545 与 1,548 个非黑像素、对 C/D 带内容的包含比例 0.000）」；时间文本带掩膜实测为空集（roundc 相隔 160 s 的两张 home 逐字节零差异）。
- 登记时刻说明：本节文字在 fixguard 起跑前已落进工作区（device 转发原文与 desktop 落档均有消息时刻可证）；顶层仓 git 写冻结（words 历史合并中）期间无法提交，解冻后随 round F 批次一并提交——若提交时刻晚于证据目录可读时刻，以本节的工作区落档时刻与消息记录为登记时刻。
- 收尾读数（device 收尾回报后抄）：`summary.py --verify` `________`；`gestures.py` `________`；`round-stats.py` 三段 `________`；`reboot.json` 四字段 `________`；bad access 计数（raw／唯一，对照 round F 的 116／16）`________`；带哈希三测试（状态数、均值色对 C/D ±10%、带内方差）`________`；帧数（对照 C/D 3611／3620）`________`；形态判定（循环→冻结或更好／不变）`________`；B 值与锚点 `________`。
