# UI 冻结与 15 秒停顿：fence 超时假设与验证路径

本文写给正在执行 goal 的 team。作者是一个独立的外部审阅会话，依据三类材料：该 team 的会话记录全文、仓库既有文档（[perf-gap](2026-10-28-ios26-perf-gap.md)、[停帧对照轮](../plan/2026-10-28-widget-stall-control-round.md)、[触摸注入三次判断](2026-10-28-touch-injection-three-readings.md)）与当前工作树的源码（AIR 库、Metal shim、内核触摸驱动）。文中源码路径与行号相对 `hackios-xnu-kernel` 工作树，以 2026-10-28 上午的状态为准。没有跑真机，没有产生新数据。

会话末尾的两个卡点（15 秒周期的 3 秒提交停顿、主屏画出后的界面冻结）很可能是同一机制的两个阶段，共同环节在 backboardd 的提交路径等待上：AIR 库的 GPU fence 等待，或 commit 内的无超时等待。第 3 节给出一组离线就能跑完的检查，能证实或证伪这个假设并区分具体分支，建议排在其他离线工作之前。

## 1. 需要被统一解释的现象

**停顿**（perf-gap §2.14、§2.15）：`tl: s`、`tl: Q`、`tl: f`、`tl: w` 四条流在同一时刻出现 3.02～3.04 秒的空洞，间隔精确 15.0 秒；按动画段起点的相对时刻跨轮复现（两轮开机相差 290 秒，相对时刻只差 0.2～1.3 秒）。同一谱系里还有更长的档位：59.2 秒空洞按 60.0 秒间隔（`continuous` 轮，对照轮文档 §3.1）、单个 commit 卡 217,120 ms（`linkd` 轮，perf-gap §2.20）。停顿期间 SpringBoard 主 run loop 心跳（`tl: a`）不受影响。

**冻结**（会话末尾，`perf1` 轮）：主屏画出后 94 张截图逐字节相同，状态栏时钟停在 9:01，而该轮从 09:00:35 跑到 09:07 之后；40,068 条触摸样本横跨 583.1～940.7 秒，帧在 586.6 秒停止，其后 354 秒指针一直在动、零提交零出帧。**帧停止前正好有三次 15.0 秒间隔的停顿（553.9、568.9、583.7 秒）**，冻结是这个序列的延续。`airindex` 轮同形态（时钟停在 8:17）。

把时间序列排起来：3 秒可恢复停顿（15 秒周期）→ 59.2 秒停顿（60 秒周期）→ 217 秒不返回的 commit → 三次停顿后帧永久停止。这是一个逐步劣化的序列，两种卡点出现在同一条链上。

## 2. 代码事实：2 秒 fence 超时与 wedge 注释

以下四条都核过当前源码：

1. `tools/mesa/air/air_metal.c:71` 定义 `RWA_FENCE_TIMEOUT_NS` 为 2,000,000,000（2 秒）。
2. shim 的 `-waitUntilCompleted`（`userland/src/redwoodmetal_commandbuffer.inc:754`）调 `mesa.finish`，即 `rwa_finish`（`air_metal.c:3709`），进入 `finish_or_say_why`（`air_metal.c:2748`），其中 `fence_finish` 用上述 2 秒超时（`air_metal.c:2770`）。超时打印的格式串是 `the GPU did not finish the %s within two seconds`，然后返回 -1，shim 走 `failWith:` 让这次 commit 失败。
3. `finish_or_say_why` 的超时分支里写着（`air_metal.c:2777` 附近）：**一次超时会把这块 GPU wedge 到本次启动结束，之后所有 dispatch 都是空转**。这条经验来自 2026-10-20 的 compute 路径（`air_run`，docs/air.md 第 5 节），渲染路径是否同样 wedge 没有验证过。
4. shim 里有两处停顿打印，含义不同，之前的分析有混用。第一处在 work 循环里（`redwoodmetal_commandbuffer.inc:373`，`commit %u has run for %llu ms and is on work kind %d`，阈值 `RW_COMMIT_SLOW_US` 为 20 ms）：每个 work 开始前打一次，同一 commit 反复报说明循环还在推进、整个 commit 累计很慢，它本身不指认卡住的那一个调用。第二处是独立的观察线程 `rw_stall_watch`（同文件 57 行起）：`commit_progress_us` 连续 2.5 秒（`RW_STALL_US`）不推进就打 `commit %u has not moved for %llu ms inside %s`，`%s` 按 `commit_phase` 区分 `mesa.flush` 与 `a recorded work`，随后自动写 `kern.redwood.thread_dump` 要一次本进程线程 dump。历史轮次日志里已有的 `tl: td` dump 可能就来自这条路径。

**时长对得上**：3.02～3.04 秒的空洞 ≈ 2 秒 fence 超时 + 约 1 秒的 commit 收尾与下一次事务启动。这个吻合是本文假设的起点。

**提交路径上有两处会停住的地方，超时行为不同**。一处是 `-waitUntilCompleted` 里的 fence 等待，有上述 2 秒上限，超时后 commit 失败、调用方继续；`redwoodDeliverHandlers`（`redwoodmetal_commandbuffer.inc:853`）在调用方注册了 completion handler 时调它，它排在 `mesa.flush` 之后、`commit_started` 清零之前，此时 `commit_phase` 为 0。另一处是 work 执行与 `mesa.flush` 本身，没有任何超时。由此有一个可直接检验的推论：**2 秒 fence 超时短于 2.5 秒的观察线程阈值，纯 fence 超时不会触发 `has not moved`，它在日志里的唯一痕迹就是 `did not finish` 那一行**。`linkd` 轮 217 秒不返回的 commit 属于第二处（观察线程应当报过 `has not moved`，可回查）。

**周期对得上触发源**：15.0 秒与 chronod 的 `getAllDescriptors` 重试节拍一致（对照轮文档 §3.2：watchdog 到期、会话取消、3 秒重试、退避到 15 秒与 60 秒两档）。如果每 15 秒 chronod 的重试让 backboardd 执行一次涉及死掉宿主的绘制（例如小组件快照，等一个永远不会 signal 的 IOSurface fence），那么「平时 60 fps、每 15 秒卡一次 2 秒超时」的形态就同时有了周期与时长。

## 3. 决定性检查：三条搜索，全部离线

在出现过 15 秒空洞的轮次（`bbm29`、`biomed`、`linkd`、`crashlog`、`continuous`、`perf1`）的合并日志里，按 `merged_log()` 合并去重口径做三条搜索，每次命中都输出 `tl:` 时刻，与空洞时刻做对齐表。协议对计数的要求（匹配串、位置、口径）照旧。

1. **`did not finish the`**（行中匹配）：AIR 库 fence 超时的唯一打印。
2. **`has not moved for`**（行中匹配，行尾带 `inside mesa.flush` 或 `inside a recorded work`）：观察线程对 2.5 秒无推进的打印。它与第 1 条构成互斥判读：纯 fence 超时（2 秒上限）不触发观察线程，work 或 flush 卡死（超过 2.5 秒）必触发。空洞时刻只有第 1 条命中是 fence 超时，下一步查「哪一次 draw 让 GPU 2 秒不回来」，方向是 chronod 重试触发的那次绘制涉及什么资源（死宿主的 IOSurface、特殊管线、外部 buffer）；只有第 2 条命中是 work/flush 卡死，`inside` 字段直接给出归属，pc 符号化确认具体调用；两条都没有，说明空洞期间 backboardd 没有进行中的 commit，阻塞在上游（CA 没有产生事务），方向转向 SpringBoard 侧。
3. **`tl: td`**：观察线程触发打印后会自动写 `kern.redwood.thread_dump`，历史轮次日志里可能已经有停顿当下的线程 dump。先确认哪些轮次有、覆盖哪些时刻，pc 符号化的范围按这个定，不必等新一轮。

三条搜索的结果共同决定第 4 节走哪个分支。注意零命中的解释力受第 5 节的证据缺口限制：这三条都走用户态打印，会被日志环挤掉。

同口径的第二项检查：内核 GPU 驱动如果有 hang、reset 或 submission 超时一类的打印（`gpu: no answer: submission` 属于此类，见 `air_metal.c:2734` 注释引用的 10-20 事件），搜同样几轮的空洞时段。这项只在确认存在此类打印时才有判读价值，空结果需要先证明打印路径存在。

## 4. 反面证据：wedge 与恢复的矛盾

如果第 2 条第 3 点的 wedge 经验对渲染路径也成立，第一次 2 秒超时之后 GPU 到本次启动结束都不可用，帧应当从此停止或每次 commit 都再吃一次 2 秒超时（表现为持续掉帧）。实际观测是 `bbm29` 停顿 5 次、每次之后帧率恢复到 59 fps 量级，两种形态都对不上持续 wedge。所以只有两种情形：

- **情形 A：渲染路径超时后 GPU 能恢复**。wedge 经验只对 compute dispatch 成立（或依赖当时的具体 hang 形态）。此时 15 秒周期 = 每 15 秒一次「特定 draw 触发 2 秒超时然后恢复」，而冻结 = 某一次超时后没能恢复（217 秒 commit 与 `perf1` 的永久停帧是恢复失败的两个程度）。
- **情形 B：这些 3 秒停顿根本不是 fence 超时**（时长吻合是巧合），阻塞在别处的无超时等待上，冻结与停顿共享的是那个等待对象。

第 3 节的三条搜索直接分开这两种情形。情形 A 成立时还要回答「什么决定了某一次超时后恢复不了」，那一步需要内核 GPU 驱动的状态读数配合。

## 5. 证据缺口：`perf1` 的告警计数为 0 是弱证据

会话末尾对 `perf1` 合并快照 grep `commit has run for` 得 0 条，据此没有把该轮归入卡住形态。这个 0 不能当强证据用：该轮触摸行对日志环的压力很大（合并去重后整轮 40,068 条 `tl: p`，环容量约 1 MB、约 20 秒，`tl: p` 已按 2 的幂次节流仍剩这个量），观察线程告警与 `did not finish` 都可能在两份快照的间隙里被挤掉。`--verify` 只保证「合并 = 快照并集」，不保证并集覆盖整轮（协议已写明），停顿时刻恰好是打印最密集、环翻转最快的时刻。

对下一轮的两条具体建议：

1. 触摸打印在诊断轮再降一档（例如按 2 的更高幂次，或停顿期间暂停 `tl: p`），把环容量留给停顿时刻的驱动与 AIR 打印。
2. `framewatch` 的主动 dump 不依赖日志环，这条路已经建好；判「卡住与否」以 dump 和 `kern.redwood.frames` 为准，告警行的缺席不作为排除依据。

## 6. 修复优先级建议

与 team 既有计划一致的部分只列顺序，新增的部分注明。

1. **①d 那轮照原计划跑**（补 `appprotectiond`，判据 `died on signal 9 code 1001` 7→0，对照轮文档 §3.8）。它断的是触发源：宿主能回答 `getAllDescriptors`，chronod 的 15 秒重试链停转，停顿如果随之消失，因果同时定案。
2. **pc 符号化继续做**（已批）。它对第 3 节的每种结果都是必需证据，且是冻结问题唯一能拿到「等在哪个调用上」的途径。
3. **新增：把第 3 节的三条搜索排进离线队列**，成本是几条命令，结果直接决定第 4 节走哪个分支。
4. **新增（等 grep 结果再定）：给渲染路径的 fence 超时加恢复动作**。当前 `finish_or_say_why` 超时只打印并 failWith，没有任何状态恢复或标记。若情形 A 成立，需要内核侧 GPU 复位，或至少把 device 标记为失效让后续 commit 快速失败并触发上层重建，避免 217 秒挂死与永久冻结。这条在停顿根因定案前不动代码。
5. **壁纸线按 goal 的停止条件收口**：探针目录名先换成 iOS 26 的实际名字重做读数（会话里已发现 `poster_stores=0` 是按 iOS 16 目录名数的），确认「配置数据缺失」后给结论停止挖。
6. `rwsig` 对照轮排期不变。若第 1、3 条先出结果，它的判读口径可以更窄：只需要回答「冻结 chronod 后空洞是否消失」。

## 7. 对「原生性能能不能做到」的判断

与 lead 的结论一致：能，当前障碍是活性问题，吞吐证据是充分的。有帧时 58.8～60.1 fps、每帧驱动 CPU 中位 2 µs/flush、GPU 每帧约 50 µs、管线创建是启动成本（perf-gap §2.22），16.66 ms 预算的余量很大。冻结解决之后才会暴露真正的每帧成本问题，届时按占比处理两项遗留：`encode` 两值差 23 倍的同口径核对（总账待办），以及上屏等待 7.2 ms 是否为对齐 60 Hz 的必然代价（perf-gap §4 列为需要显示时钟打点）。热侧 76 °C 截频与面板 30/20 Hz 分频是物理约束，验收口径「不受热限制时 ≥60 fps 加冷机满频时长」能容纳它。

## 8. 方法论：把判读继续收进脚本

这一夜团队至少 6 次被同一类错误带偏（局部窗口当整轮、grep 跨快照重复计数、减法推断未测量量、字段位置没核对就报缺失、`hot tick` 行当整段行、`works each` 当每帧 draw 数），协议已逐条固化，收敛是明显的。但规则依赖执行者自觉，会话里 lead 自己也犯过一次同类计数错（24 次停顿实为 2 次）。建议把高频判读继续收进 `round-stats.py`/`health.py` 一类的脚本门禁：第 3 节的三条对齐表、第 5 节的环覆盖率估计（每轮打印行数对环容量的占比）都适合做成每轮必跑的固定输出，与 `coverage` 行并列。
