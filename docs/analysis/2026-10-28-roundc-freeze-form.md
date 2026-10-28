# round C 冻结形态分析（2026-10-28）

round C（内核 `cf1502f5632284af…`，payload `ebdca4adfc9fb5f4…`，apfs 复用 roundb 的 `e36caefb…`，jobs `a4af9a9f…`）全轮 bad access 零条，按[判读口径 §8](2026-10-28-roundc-reading-criteria.md)归冻结形态。本页回答 task-19 的六项：冻结时刻换算、线程 dump、线程数曲线、拷贝路径相关性削弱到什么程度、49152 尺寸的出处、died 分类对照，外加 `run-queue.sh` 调用更正与建议。全部离线，数据是 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundc/run/` 的 21 份 s*.log 与 hung-held.log，脚本与机器可读输出在 `docs/progress/evidence/k90auto/analysis-roundc/`（`freeze_form.py`、`freeze_form.out.json`、`read_roundc.py`）。轮次身份与收尾四条命令原文见[内核改动记录 §6](../progress/2026-10-28-kernel-badaccess-region.md)。

## 1. 换算口径与数据来源

轮内相对秒 = (µs − 12841497838)/1e6，T0 取全部日志里最早的 `tl:` 行 µs，与 `summary.py --verify` coverage 行的起点相同。带 µs 的行（`tl: s`、`tl: v`、`tl: w`、framewatch 各款）直接换算；不带 µs 的行（`periodic dump`、dump 块）用同一快照内最近的前后带 µs 行夹逼，报区间。日志环跨快照有重复，所有计数分 raw（跨快照求和）与唯一行两个口径，逐处标明。

截图文件名是轮内十分之一秒时刻：`run-auto.py:34` 解析 `RUN_TIMING`（本轮默认 `3,100,20`），`:163` 的调度是 `elapsed >= shot_from` 且距上一张满 `shot_every`，`:166` 命名 `shot-{int(elapsed * 10):05d}.raw`。所以 `shot-01001.raw` 是 100.1 s、`shot-04190.raw` 是 419.0 s，101 张覆盖 100.1..419.0 s、间隔约 3.2 s。前 100 s 没有截图是 `shot_from=100` 的设计值。

## 2. 冻结时间线（第 1 项）

全部时刻是轮内相对秒。

- 2.9 s：首次交换（`tl: s 1`）。
- 2.9→18.3 s：第一个交换空档，长 15.4 s，即 round-stats 报的首个 hole；`still no frames` 第一段计数出现在这一段（N=6..8 于 9.6..11.6 s，起点约 3.6 s），属开机段。
- 18.3→100.2 s：渲染段。3611 帧、3611 次交换，帧号 1..3611 零断裂。15 s 周期的约 3 s 交换空档在 31.4→34.4、46.4→49.4、61.4→64.4、76.4→79.4 s；末段空档变密：91.4→93.6、94.2→97.6、97.7→100.1 s。
- 约 90.2 s：rwtouch 的 swipe（`rc.jobs.freeze:13` 的 `wait 90` 之后）；gestures 报 swipe-left 1 次、无动画可量。
- 约 100.25 s：rwtouch 的 `button home`（`wait 90` + swipe 0.25 s + `wait 10`）；round-stats 的 30 s 窗口表在 92.9..122.9 s 窗口记 34 finger、2 button。
- **100.2 s：末次交换（`tl: s 3611`），提交永久停止。与 `button home` 的时刻差在 0.1 s 量级内。**这是本轮数据里最紧的一对时刻，只证明一起出现；home 键处理路径与该内核的交互是否参与停止，本轮分辨不了。
- 100.5 s 起：`still no frames` 第二段计数，N=6 于 106.5 s，连续无复位，N=318 于 419.8 s（hung-held.log），跨 155.6 s 的触发簇不中断。
- 100.1..103.1 s 之间：截图内容唯一一次变化。101 张截图共 2 个唯一哈希，`shot-01001`（100.1 s）是一个值，`shot-01031`（103.1 s）起全部是另一个值。**内容冻结时刻 ∈ (100.1, 103.1]，与提交停止 100.2 s 一致。**
- 155.6 s：一次性触发簇。`no frames for 2 s` 对两个 pid 各一条、`no process named /redwood/bin/framewatch`、`no process named 2`、`no process named 6`，以及对应的一对 dump（SB 18 线程）。出处是 `rc.jobs.freeze:19` 的 `framewatch 2 6 backboardd SpringBoard`：`:14-18` 的注释写明该行靠 `:13` 的 wait 链排在约 150 s 启动、阈值 2 s、6 个 dump 名额；155.6 s 触发与启动时刻（约 153.6 s）吻合。`no process named 2`／`no process named 6` 说明该实例把一部分命令行参数当成进程名去 dump 了，参数处理与注释意图对不上，原样记录。它的 6 个 dump 名额在日志里只见 155.6 s 一对，其余名额无对应行。

与交接文档 §1 旧驱动 `31f2d6b7` 冻结轮的对照。旧轮两个数（内容冻在 131 s、提交停在 273 s）已是轮内相对秒，与本页口径相同，**可比**。结论：同属冻结形态家族（双进程 `exited code` 0 条、帧号零断裂、`still no frames` 连续计数到轮末、主线程 settling 在 `psynch_cvwait` 固定等待对象，见 §3），子形态有三处不同：

三个 framewatch 实例的启动文本在日志里各出现一次，与 `rc.jobs.freeze` 的三行一一对应，读采样前先按这三行认实例：`watching kern.redwood.frames from 0, still after 5 s, at most 0 dumps`（`:11` 停滞模式，`still no frames` 两段计数都来自它）、`periodic dumps every 20 s, 15 of them, 2 names`（`:12` 周期模式）、`watching kern.redwood.frames from 3611, still after 2 s, at most 6 dumps`（`:19`，约 153.6 s 启动时帧计数已停在 3611，155.6 s 触发簇来自它）。周期模式的预算在日志结束前用完：最后一次 `periodic dump 15 of 15` 在 s020.log:18297，并集口径最后一个 dump 在 309.4 s，`still no frames` 持续到 419.8 s，dump 缺口约 110 s；冻结段（100.2 s 起）的前约 209 s 有周期采样，缺的只是尾段。

| 项 | 旧驱动冻结轮（31f2d6b7） | round C（9d66dd36 + 新内核） |
|---|---|---|
| 内容冻结对提交停止 | 内容先冻（131 s），提交再持续 142 s（273 s） | 同时（内容 ∈ (100.1,103.1]，提交 100.2 s） |
| 提交停止对 home 键（约 100.25 s） | 停止在 273 s，距按键约 173 s | 停止在 100.2 s，与按键时刻一致 |
| 15 s 周期 3 s 空档位置 | 约 180 s 起（`rc.jobs.freeze:16` 注释） | 31.4..79.4 s，按键之前 |

旧轮的主线程描述（`psynch_cvwait` 等私有对象、从 +106 s 起 runloop 不再泵）在 round C 成立：tid 221 的等待对象自 rel (86.5, 108.5] 区间内固定，之后 14 代 dump 不变（§3）。

## 3. dump 与主线程（第 2 项）

dump 来源两个实例：`rc.jobs.freeze:12` 的 `--every 20 --count 15`（周期 20 s、15 代）与 `:19` 的事件触发（1 代）。实测每进程 16 代：rel 23.1、43.7、63.2、86.5、108.5、128.7、148.8、155.6（事件）、168.8、188.9、209.0、229.1、249.1、269.2、289.3、309.4 s，周期约 20.1 s，与 `--every 20 --count 15` 吻合。309.4 s 之后无 dump（周期名额用完，事件实例的余量没再触发），`still no frames` 行持续到 419.8 s。

字段语义按打印源码：`redwood_threads.c:60-63` 依次打 `thread->state`、`thread->wait_event`、`thread->sched_pri`、保存的 upcb 用户 pc。本内核树 `osfmk/kern` 里检索不到 `TS_UNINT` 等 state 位定义，数值到语义的映射未建立，state 按原值报（tid 221 经历过 4→1）。

pc 归属用桩解码：pc − slide（0x105a4000）− libsystem_kernel 加载址（0x232f09000）得镜像内偏移；该偏移换算文件偏移用 subcache `.46` 自己的 mapping 表（mappingOffset 0x228、唯一一项 address 0x22c8a8000、size 0x6b98000、fileOffset 0），得文件偏移 0x6661000，与[归属复核 §2](2026-10-28-roundb-memmove-attribution.md)一致。从 pc 往前 4 条指令内找 `movz/movn x16`：movz 是 BSD 调用号（对照 `bsd/kern/syscalls.master`），movn 是 mach trap 号 −(imm+1)（对照 `osfmk/mach/syscall_sw.h`）。本轮 dump 出现的五个 pc：

| pc | 镜像内偏移 | pc−8 处的装载指令 | 号 | 名字 |
|---|---|---|---|---|
| 0x2434b2ba4 | +0x5ba4 | movz x16,#305 | 305 | `psynch_cvwait` |
| 0x2434b35e8 | +0x65e8 | movz x16,#305 | 305 | `psynch_cvwait` |
| 0x2434ada54 | +0xa54 | movz x16,#375 | 375 | `kevent_id` |
| 0x2434ada80 | +0xa80 | movz x16,#368 | 368 | `workq_kernreturn` |
| 0x2434adcd4 | +0xcd4 | movn x16,#46 | −47 | `mach_msg2_trap` |

形态自洽：mov 在 pc−8、svc（`d4001001`）在 pc−4、保存的 pc 指向 svc 之后第一条，与 roundb tid 306 的 pc 指 `ret` 是同一形状。同一 syscall 有两个桩（+0x5ba4 与 +0x65e8 都是 `psynch_cvwait`）。

SpringBoard（pid 30）主线程候选 tid 221：每代 dump 的第一行、pri 47、rel 108.5 s 起三元组恒定。dump 行没有「主线程」标志，认定依据是这三条加与交接文档形状一致，属推断。序列：

| rel s | 线程数 | state | wait | pc |
|---|---|---|---|---|
| 63.2 | 25 | 4 | 0 | +0x5ba4（psynch_cvwait） |
| 86.5 | 23 | 4 | 0 | +0xa54（kevent_id） |
| 108.5 | 24 | 1 | 0xfffffff91baf2e00 | +0x65e8（psynch_cvwait） |
| 128.7..309.4（13 代） | 22→18 | 1 | 0xfffffff91baf2e00 | +0x65e8（psynch_cvwait） |

等待对象 0xfffffff91baf2e00 自 108.5 s 起 14 代约 200 s 不变；固定时刻夹逼在 (86.5, 108.5]，与提交停止 100.2 s 一致。交接文档「主线程在 `psynch_cvwait` 上等一个私有对象」在本轮成立，等待对象是同一个且不再变化。dump 里其余线程的 wait 对象集中在 0xfffffff91baf0d00..0xfffffff91baf3a00 同页区间，pc 多在 +0x65e8 与 +0xa80。

backboardd（pid 38）主线程候选 tid 244（每代第一行，pri 31）：state 1、wait 0、pc +0xcd4（mach_msg2_trap）全 16 代恒定，渲染段内已如此。这个形状区分不了渲染与冻结两种状态，只说明每次采样时 bbd 主线程都在 mach 消息等待里。

exec 行本轮出现在 s002..s020 与 hung-held.log，两行实测值 `tl: td 30 exec 0x100fb4000 SpringBoard`、`tl: td 38 exec 0x100c78000 backboardd`。本轮 dump 里所有 pc 都在共享缓存内，没有落进主二进制区间的，exec 基址没有参与命名；行本身的有效性（非零基址、名字正确）已验证，pc 减 exec 基址的用法留给有主二进制 pc 的轮次。

与旧驱动 `31f2d6b7` 冻结轮（`kernel-12377-attr26-freeze`）的主线程对照。旧轮数据两个来源：交接文档 §1 的 display 判读（8 个 dump 时刻 +20.6/41.2/60.1/83.3/106.2/126.4/136.8/155.9 s，墙钟锚），以及本轮分析对该目录 s*.log 的直接检索（tid 221 行原样）。

| 项 | 旧冻结轮（31f2d6b7） | round C（9d66dd36 + 新内核） |
|---|---|---|
| 主线程 tid | 221 | 221（每代首行 + pri 47 推断，与旧轮认定一致，互为印证） |
| settling 前的形状 | +41.2..83.3 s 在 `mach_msg2_trap`（pc 尾 `+0xcd4`） | 63.2 s `psynch_cvwait`（state 4 wait 0）、86.5 s `kevent_id`（state 4 wait 0） |
| settling 时刻 | +106.2 s（dump 采样点） | (86.5, 108.5] 区间 |
| settling 后 state／pri | 1／47 | 1／47 |
| settling 后 pc | libsystem_kernel `+0x65e8`（`psynch_cvwait` 桩，slide 0x1dde0000） | 同一桩 `+0x65e8`（slide 0x105a4000） |
| 等待对象 | `0xfffffff6e7eef800`，只在 pid 30 出现 | `0xfffffff91baf2e00`，检索 s020 全部 dump 只出现在 pid 30 tid 221 一行 |
| settling 对内容冻结／提交停止 | settling 先于内容冻结（131 s）25 s，先于提交停止（273 s）167 s | settling 与提交停止（100.2 s）同段，内容冻结 (100.1,103.1] |

两轮主线程在「同一 tid、同一 syscall 与同一桩偏移、同 state 值、等待对象同样只属于 pid 30」四项上一致；对象地址不同，但跨 boot 的内核堆地址不构成对象标识，地址差异不能用来否证同源。就主线程证据而言，旧驱动冻结轮与 round C 的冻结是同一个静止状态，子形态差异集中在 settling 与提交停止的先后（§2 表）。[协议 §「符号化 pc 走 stub 的系统调用号」](../plan/k90auto-run-protocol.md)要求把桩解码落成工具，本页的解码器已在 `freeze_form.py` 里（输入 slide 与 pc，输出镜像内偏移、系统调用号与名字）；本轮五个 pc 的解码结果与协议记录的旧轮六个主导 pc 同族，都是普通阻塞调用，没有一条落在 CoreAnimation 或 backboardd 的提交路径上。

## 4. 线程数曲线（第 3 项，含更正）

**更正**：我在收尾报告里写过「SpringBoard 线程数 18→57 随时间增长」，那是把唯一行按文本排序的输出误读成时间序。按 dump 时序，实测是 57→18 收敛：

| rel s | 23.1 | 43.7 | 63.2 | 86.5 | 108.5 | 128.7 | 148.8 | 155.6 | 168.8 | 188.9 | 209.0..309.4 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SB 线程数 | 57 | 28 | 25 | 23 | 24 | 22 | 20 | 18 | 21 | 18 | 18（恒定） |

backboardd 同期 13→12..14 波动，309.4 s 收在 13，全程平坦。

先后关系：收敛主体在提交停止（100.2 s）之前（57→23 于 86.5 s），停止之后继续降到 18 并自 188.9 s 恒定，期间只有 168.8 s 一次 18→21 回弹。所以「增长在停止之前、可能是成因」与「停止后请求堆积、增长是后果」两个方向都不成立：曲线没有持续增长段，冻结点两侧都是下降。boot 期 57 收敛到常驻 18 与 workqueue 线程回收形状一致（dump 里有 +0xa80 `workq_kernreturn` 桩），不再归因。

## 5. 拷贝路径相关性假设被削弱到什么程度（第 4 项）

对照数据。两轮同一份 apfs（驱动 `9d66dd36`）、同一份 jobs、同一个带插桩的 AIR（`d7b9ced5`，两轮都有 `perf draw: timing on` 行），唯一变量是内核（`9a7a118a` 对 `cf1502f5`）：

| 项 | roundb | round C |
|---|---|---|
| `rwa buffer: copied` raw（s*.log） | 1775 | 230 |
| copied 后 4 行内出现 bad access | 209（11.8%） | 0 |
| bad access raw／唯一行／物理事件 | 212／11／15 | 0／0／0 |
| 驱动侧 nil（`left nil, over the`） | 8 | 16（1081344×3、1163264×13，rel 18.5 与 54.1 s） |
| CA 侧 `nil buffer from memory` | 8 | 16 |
| copied 时间范围（rel） | 全轮散布 | 18.5..100.1 s（全在渲染段） |

两轮插桩状态相同，「随后 4 行内」窗口的行密度口径跨这两轮可比；判读口径 §12 的不可比警告针对插桩开关不同的轮次对，本对照不落入。

能排除的：「拷贝必然或在短时间内必然伴随故障」被 230 次拷贝零故障直接否证；「故障发生率是 copied 次数的稳定函数」也被否证（同驱动同插桩，11.8% 对 0%，唯一变量是内核）。

不能排除的：「拷贝路径是故障链的必要参与项」这个弱命题两轮都满足 copied 存在，本对照分不开拷贝路径的贡献与内核版本的贡献；roundb 内核（`9a7a118a`）与拷贝缓冲的交互以何种机制产生越界 src，属于 task-18 的源码 delta 排查，本页不下结论。

样本边界：轮次对 n=1 对 n=1；round C 的 230 次拷贝来自同一进程同一 UI 状态，轮内不是独立样本；轮间方差未测（同一 payload 重跑没做过）。

## 6. 49152 尺寸与两轮拷贝尺寸分布（第 5 项）

49152（48 KiB）的全部出现：raw 17 条、唯一行 1 条（ptr `0x102c24000`、buffer `0x1027e3000`），进程全部是 backboardd 38，首现 rel 94.2 s（s005.log:21047），上下文是 16384 拷贝的连发段。同一唯一行重复 17 次是日志环跨快照重复。

两轮 `copied` 唯一行尺寸分布（roundb 引自 task-19 任务文本，口径同判读标准 §3.6）：

| 尺寸 | roundb 唯一行 | round C 唯一行 | round C raw（含 hung-held） | round C 进程 |
|---|---|---|---|---|
| 15360 | 5 | 1 | 3 | SpringBoard 30 |
| 16384 | 4 | 16 | 214 | backboardd 38 |
| 32768 | 94 | 1 | 3 | backboardd 38 |
| 49152 | 0 | 1 | 17 | backboardd 38 |
| 62464 | 5 | 1 | 3 | SpringBoard 30 |
| 65536 | 1 | 1 | 3 | backboardd 38 |

分布差异与形态差异并列记录，不互推：两轮桌面状态不同（roundb 黑屏循环、SpringBoard 未到过主屏；round C 渲染主屏约 100 s 后冻结），CA 的请求长度跟随 UI 内容，分布差异预期内。32768→94 对 1 与 16384→4 对 16 是两轮主导尺寸的互换；49152 只在 round C 出现，roundb 的故障地址与 32768 长度绑定（归属复核 §6），round C 无故障，两条线各自成立。

## 7. died 分类对照（第 6 项）

口径：raw = 跨快照求和，唯一行 = 行文本去重，进程数 = pid 去重。roundb 唯一行合计 178、raw 2883；round C 唯一行合计 28、raw 363。

| 类 | roundb raw／唯一行／进程数 | round C raw／唯一行／进程数 |
|---|---|---|
| backboardd sig11 code11 | 225／15／15 | 0 |
| SpringBoard sig9 code0 | 217／14／14 | 0 |
| SpringBoard sig6 code6 | 18／1／1 | 0 |
| widget/extension sig9 code0 | 1788／106／106 | 0 |
| widget/extension sig9 code1001 | 224／15／15 | 204／17／17 |
| widget/extension sig5 code5 | 0 | 117／9／9 |
| ACCHWComponentAu sig9 code9 | 229／15／15 | 0 |
| AudioConverterSe sig9 code9 | 93／6／6 | 0 |
| MTLCompilerServi sig9 code9 | 47／4／4 | 0 |
| launchd.ios／MSUEarlyBootTask sig1 code-1 | 42／2／2 | 42／2／2 |

round C 的 sig9 code1001 明细（唯一行 17、进程数 17）：AccessibilityCon×2、AdaptiveMusicCon×2、FitnessWidget×2、MusicWidgets×1、NewsToday2×1、PassbookWidgetsE×2、ScreenTimeWidget×3、StocksWidget×3、WorldClockWidget×1，rel 27.9..167.8 s 散布。sig5 code5 明细（唯一行 9）：BarcodeScannerWi、CalculatorWidget、LauncherControlE 各 3 代 pid，rel 166.8..167.8 s 集中，在冻结之后约 66 s。sig1 code-1 两行都在 rel 0.1 s（boot 段）。

「widget 死亡是否属于正常运行」的判据与判定：

- sig9 code1001：进程名全部是 widget/extension 家族；散布全轮；同名进程多代 pid（拉起→回收循环）；roundb 同样存在（15 进程）；`package.py` 的 ON_DEMAND_JOBS 注释记录这类任务按「launchd 在空闲时回收」设计。判为正常回收。
- sig1 code-1（launchd.ios、MSUEarlyBootTask，rel 0.1 s）：两轮完全一致，boot 交接段行为，判为正常。
- sig5 code5（SIGTRAP，3 进程 9 行，rel 166.8 s 同秒集中）：回收形状应是 sig9 code1001，SIGTRAP 批量同秒死亡与之不符，roundb 无此类，且在冻结之后。原样报，成因不猜；round C 无崩溃报告（`crash_files=0`，通道未通），没有进一步材料。
- roundb 独有的 sig9 code0 大批量（106 widget + 14 SB）与 sig9 code9 三类（ACCHW/AudioConverter/MTLCompiler）在 round C 全部消失，与 roundb 的重启循环形状一致：code0 类是循环期间的连带杀。此条属对照观察，机制归 task-18 之后的裁决。

## 8. run-queue.sh 调用更正与建议（归 task-10）

本轮实际执行的调用是 `run-queue.sh docs/progress/evidence/k90auto/kernel-12377-attr26-roundc 420`。用法（`run-queue.sh` 38 行）：位置参数是 `RUN_DIR...` 目录列表，秒数走环境变量 `RUN_SECONDS`（默认 420）。`420` 被静默当成第二个轮次目录，脚本先完整跑完真实轮次（`QUEUE done … 14:10:03`），再对 `420/manifest.json` 报 `QUEUE stop: 420/manifest.json names no payload` 并 exit 1。

数据未受影响的依据：本轮秒数走默认 420，`SAMPLED_SECONDS 420.4473890408408` 为证；`QUEUE done` 先于 `QUEUE stop`；GUARD 行、reboot.json、21 份快照完整；exit 1 发生在设备已恢复 loader idle 之后，与设备状态无关。

失误的形状比用法更值得记：一个多余的数字参数没有在入口被拒绝，而是被当成目录名进入队列，错误在消耗完一整轮设备时间（约 10.7 分钟）之后才出现。建议 task-10 给 `run-queue.sh` 加前置校验：循环开始前逐个检查参数是存在且含 `manifest.json` 的目录，任何一个不满足立即退出，不消耗设备时间；纯数字参数可以直接拒绝并提示秒数用 `RUN_SECONDS`。本页不改脚本。

## 9. 结论

round C 是拷贝路径驱动 `9d66dd36` 第一次出现冻结形态，此前该形态只在旧驱动 `31f2d6b7` 的轮次出现过。冻结形态家族的四个要素本轮全部成立：双进程 `exited code` 0 条、帧号 1..3611 零断裂、交换空档加提交永久停止、主线程 `psynch_cvwait` 等待对象固定（tid 221，rel 108.5 s 起约 200 s 不变）。主线程证据四项与旧冻结轮一致（同 tid、同桩偏移、同 state 值、等待对象同属 pid 30 私有，§3 表），两轮的冻结就主线程而言是同一个静止状态；「冻结形态由驱动版本决定」的旧框架在驱动 `9d66dd36` 上不再成立，与 task-21 要分开的问题直接相关。

子形态与旧轮不同的三处（§2 表）：内容冻结与提交停止同时（旧轮相差 142 s）；提交停止与 `button home` 时刻一致到 0.1 s 量级（旧轮距按键约 173 s）；15 s 周期 3 s 空档出现在按键之前的 31.4..79.4 s（旧轮约 180 s 起）。第二处是本轮数据里最紧的时刻对应，它把「home 键处理路径参与提交停止」列为下一轮可检验的假设，也保留「停止已在进行、按键恰好落在停止点」的可能，本轮数据分辨不了两者。

正面证据单列：101 张截图（100.1..419.0 s）全部判为 home screen、`bad_shots=0`，加上渲染段（0..100.2 s）3611 帧零断裂，这是重启循环出现以来第一轮拿到「桌面显示出来并保持」的完整读数。截图覆盖段从 100.1 s 起是 `shot_from=100` 的设计值，渲染段的画面内容由帧计数与 round-stats 的 tier 判定支撑，无逐张截图。

拷贝路径相关性：强命题（拷贝必然伴随故障、故障率是 copied 次数的稳定函数）被 230 次拷贝零故障否证；弱命题（拷贝路径是故障链的必要参与项）本轮无分辨力，等 task-18 的内核源码 delta 结论。
