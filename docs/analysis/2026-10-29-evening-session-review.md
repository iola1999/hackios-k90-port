# 2026-10-29 下午到晚间会话的审查

这份文档审查 2026-10-29 14:25 到 22:40 的会话：它做了什么，方案里哪些地方有问题，接手后按什么顺序继续。上一段会话的复盘见[会话复盘](2026-10-29-session-review.md)。文中「实测」指在轮次目录、mesa 源码与 loader 源码上读到的内容，「推断」指由读数推出、还没有真机验证的部分。

## 1. 会话做了什么

- 复盘上一段会话，写成[会话复盘](2026-10-29-session-review.md)与[离线工作队列](../plan/2026-10-29-offline-work-queue.md)，离线队列 O1～O11 两批都已提交，最后一笔是 `ada4864`。
- 新增 `hackios-xnu-kernel/tools/dsc/`（kernel `5586c7c`），在 26 的共享缓存里静态定位 `AppleCLCDDisplay`、`EAGLServer` 与 `GLESContext` 的虚表。
- `package.py` 的 `pack.sources` 补上驱动的全部 `#include`（`f99ff4a`），驱动注释与实现对齐（kernel `6229821`）。
- 设备 21:09 回到 LK，跑完两轮真机（下表），第三轮的 AIR 已编好，载荷没有打包。
- 应用户要求给 loader 加屏显：新增 `xnuloader/loader_06a_screen_ui.inc`，改 `loader_06_usb_entry.inc` 与 `loader_ramdisk.inc`，宿主机渲染测试通过，没有提交，没有上机。

| 轮 | 轮次目录 | AIR | 结果 |
|---|---|---|---|
| 1 | `kernel-12377-attr26-diag3x-statecursor2` | `57fdb85c…` | 22 条慢 draw 的 `state` 段全部落在 `prog_state`（99.8%～100%）；预落页 0 条；线程快照 3 份；末帧 637，80.0 秒收尾 |
| 2 | `kernel-12377-attr26-diag3x-statecursor3` | `b303726d…` | 25 条全部落在 `prog_lookup`，即 `ir3_cache_lookup()`（99.7%～100%）；预落页 1 条，16,384 字节 101,180 µs；末帧 771，80.0 秒收尾 |
| 3 | 未起轮 | `35cc6646…` | `ir3_cache_lookup()` 内 8 个子段，`library-baseline.json` 已改成这一版，未提交 |

两轮的内核、驱动与注入库相同（`f055cc0a…`、`529d19bf…`、`1d727833…`），载荷分别是 `b4b9d6ab…` 与 `2b93bac4…`。两轮的读数目前只写在会话里，仓库里没有对应的 progress 记录。

## 2. 「着色器编译已排除」的依据不成立

[注入与 draw 串行记录](../progress/2026-10-29-ios26-injection-and-draw-serial.md) §3.2 的第一条排除依据是「`prog_builds` 全轮累计为 0」，[会话复盘](2026-10-29-session-review.md) §6 的卡点表沿用了这一条。这个读数是截断的结果（实测）。

- `tools/mesa/perf-prog-builds.patch` 在窗口汇总行里打印 `w->prog_builds / w->frames`，窗口是 128 次 flush，整数除法。一个窗口里有 25 次未命中，打出来也是 0。
- 第二轮第一个窗口是 `perf flush 128: … own 45407 (track 58 prog 45114 …) … prog_builds 0 us`：平均每次 flush 有 45 毫秒花在取程序状态上，计数仍是 0。
- [慢 draw 的读数判据](2026-10-29-slow-draw-reading-criteria.md) §4 原写「一轮的 `prog_builds` 为 0 只能推出该轮没有编译」，0 本身说明不了这一点。这三处已按本节改写。

## 3. 慢 draw 与新建 pipeline 一一对应

驱动只在第一次建 pipeline 或单次建 pipeline 不少于 1 毫秒时打印 `render pipelines: N built`（`tools/userland-driver/redwoodmetal.m:1544`）。按这一行数「上一次新建 pipeline 之后过了几帧 `tl: v`」，三轮的慢 draw 分布如下（实测，按 `wall cpu flt` 三元组去重）。

| 轮次 | 新建 pipeline 行 | 慢 draw | 0 帧之内 | 2 帧之内 | 更远 |
|---|---|---|---|---|---|
| `diag3x-statefault` | 30 | 24 | 23 | 23 | 1 条（18 帧） |
| `statecursor2` | 28 | 22 | 19 | 21 | 1 条（37 帧） |
| `statecursor3` | 29 | 25 | 23 | 25 | 0 |

71 条里 65 条出现在新 pipeline 建好之后、下一帧呈现之前。慢 draw 成批出现，每批前面是一批新建的 pipeline：第二轮 commit 766 的 10 条慢 draw 前面是编号 32～49 的 pipeline，其中有 `glass_background_sdf_lph`（单次 23,042 µs）一类的玻璃效果着色器。

mesa 源码给出了这段等待的一条可能路径（实测源码，因果是推断）。

- `ir3_cache_lookup()` 未命中时为每个 stage 调 `ir3_get_shader()`（`ir3_cache.c`），后者在 `util_queue_fence_wait(&hwcso->ready)` 上等 `ir3q` 队列编完初始变体（`ir3_gallium.c:398-415`）。
- 初始变体在建 shader state 时入队（`ir3_gallium.c:351-356`），建 pipeline 只花 1～23 毫秒，编译留在队列里。
- 队列线程数是 `sysconf(_SC_NPROCESSORS_ONLN) / 2`，下限 1（`ir3_gallium.c:542-549`）。这一批载荷用 `cpus=2`，只有 1 个编译线程，一批 pipeline 的着色器排成一队依次编。
- Darwin 上 `UTIL_FUTEX_SUPPORTED` 为 0（`util/futex.h`），fence 走 `mtx`／`cnd`，等待中的线程停在 `psynch_cvwait`。

这条路径能解释 CPU 与墙钟的比值：绘制线程每条慢 draw 只用 43～566 µs CPU，墙钟 55 毫秒到 2.04 秒，比值不超过 0.004。`flt` 是整个进程的缺页数（[缺页口径核对](2026-10-29-slow-draw-fault-accounting.md) §1.2），编译线程分配内存时的缺页也计在里面，所以「墙钟随 `flt` 上升」的回归定位不了是哪个线程在缺页。

## 4. 与这条路径不一致的读数

第一轮的三份线程快照不支持「编译线程正在编」（实测读数，解名的 slide 是推断）。

- 三份快照取在 draw 54（394 ms）、draw 76（1,714 ms）与 draw 4796（540 ms），每份 18～20 个线程，没有一个线程的 pc 落在 AIR 里。这一轮 AIR 的 `fd_draw_vbo` 在 `0x102a50080`，按 `nm` 的偏移 `0x2e8080` 算出 AIR 从 `0x102768000` 起、`__TEXT` 长 `0xc1c000`。
- 用 slide `0x1fbf0000` 解名。这个 slide 是按 tid 244 的 pc 与归档里 `mach_msg2_trap` 同在 `libsystem_kernel+0xcd4` 反推的；8 个 pc 解出的名字与各自返回地址所在的库一致（`workq_kernreturn` 与 `psynch_cvwait` 的返回地址在 `libsystem_pthread`，`madvise` 在 `libsystem_malloc`，`sys_ulock_wait` 与 `semaphore_wait_trap` 在 `libdispatch`）。

| 系统调用 | tid |
|---|---|
| `mach_msg2_trap` | 244、297（2 份）、324、360、363、390 |
| `workq_kernreturn` | 292、305、327（2 份）、376、378、539、621、622（1 份） |
| `psynch_cvwait` | 300、362（三份都在） |
| `sys_ulock_wait`（libdispatch） | 328 |
| `semaphore_wait_trap`（libdispatch） | 375 |
| `sys_ulock_wake`（libdispatch） | 622（1 份） |
| `read` | 302 |
| `madvise`（libsystem_malloc） | 297（1 份） |
| CoreFoundation 内的用户态 pc | 327（1 份） |
| pc 为 0 | 623，发起快照的看门线程自己 |

`thread_get_state` 读别的线程之前先 `thread_hold` 再 `thread_stop`，等它停下才取寄存器（`hackios-xnu-kernel/out/xnu12377/osfmk/kern/thread_act.c:849-858`），所以正在执行用户态代码的线程会给出当时的 pc，327 那一份落在 CoreFoundation 就是这种情形。三个时刻都没有 pc 在 AIR 里的线程，有三种可能：编译线程自己也在等（锁、I/O 或 IOKit 调用）；等待发生在 `prog_build` 或 `create_state` 一侧而不在 fence 上；快照恰好落在两次编译之间。这三种可能第三轮现有的 8 个子段只能分开一部分。

## 5. 第三轮的探针需要补

`35cc6646…` 只把 `ir3_cache_lookup()` 切成 8 段，能回答「睡在哪一步」，回答不了「为什么睡」。[AGENTS.md](../../AGENTS.md) §5 要求相关观测点装进同一份库、同一轮取完，这一轮应当在同一份 AIR 里再加三组读数，内核、驱动、注入库与作业都不动，相对第二轮仍然只换 AIR。

- `ir3_get_shader()` 的 fence 等待：stage、着色器名、等待时长、等待线程的 tid。tid 用来在线程快照里认出绘制线程。
- `ir3q` 的每个编译任务：入队到开始的时长、执行墙钟、编译线程 CPU、编译线程 tid、着色器名。三项分别对应「排队」「编译慢」「编译线程在等」。
- `fd_bo_new()` 超过 5 毫秒的分配：大小、耗时、tid，覆盖 `create_state` 一侧建程序 BO 的可能。

第二轮按[下一轮方案](../plan/2026-10-29-next-round-plan.md) §4.1 走，判据是事先登记的；第三轮那 8 个子段各对应什么结论，方案里还没有写。接手后已登记在[下一轮方案](../plan/2026-10-29-next-round-plan.md) §8。

## 6. loader 屏显改动的问题

工作树里的改动（`loader_06a_screen_ui.inc` 348 行，另两个文件 26 行）有以下问题，上机前要改。

- 空闲时转动的方块大约 10 秒才动一步。`ui_tick()` 只在命令循环里调，`usb_rx()` 空闲时要等满 `USB_IDLE_WAIT_SECONDS`（10 秒）才返回（`loader_06_usb_entry.inc:262` 起的 `usb_wait()`），而方块就是用来判断 loader 有没有停住的。
- 一次性下载到驻留区时，进度条的分母取的是 `limit`，即窗口容量，进度条到不了 100%。分块传输与普通载荷没有这个问题。
- 内核跑过之后（`kernel_resources_held` 或 `firmware_fault` 置位），命令循环里的 `ui_tick()` 会在内核最后一帧上画方块和日志，之后 `oem screenshot` 取到的画面就混进了 loader 的像素。
- 百分比写成「45 PCT」，用户看不懂；进度条加「已收／总量 MB」就够了。
- 日志里的 `_`、`,`、`[`、`]` 等字符没有字形，显示成 `?`。
- 没有跑 `tools/test-loader-lifecycle.py` 与 `tools/test-loader-buildid.py`，没有带 `BUILD_ID` 构建，没有提交。

装在 A 槽的 v8（镜像 `7ffbdd44…`，镜像内 `loader.efi` 为 `ebf60d74…`）构建时没有设 `BUILD_ID`，`getvar build-id` 答 `unknown`，对不上提交。上新 loader 之前，先确认当前 HEAD 不加屏显时能不能编出 `ebf60d74…`：能编出来，新旧 loader 的差别就只剩屏显；编不出来，要先查清 v8 与 HEAD 的源码差在哪。

## 7. 流程上的问题

- 两轮读数、第二轮与第三轮的探针补丁都没有入库（接手后已补：读数见[分段三轮](../progress/2026-10-29-state-segment-rounds.md)，补丁随第三轮一起提交）。`tools/mesa/fd6-state-segs-2.patch` 与 `tools/mesa/prog-lookup-segs.patch` 不在 `.userland.git` 里，kernel 仓库的 `.gitignore` 忽略了 `/tools/mesa/`，`common/ugit status` 也不报未跟踪文件，要用 `common/ugit add -f` 指名加入。
- 顶层 `tools/k90auto/library-baseline.json` 的改动没有提交（接手后随第三轮的 AIR 一起提交）：`air_sha256` 改成了 `35cc6646…`，`source_sha256` 多了 `f99ff4a` 之后的八个驱动源文件。
- `hackios-xnu-userland/userland/src/inject.c` 的未提交改动是共享树里已提交内容的旧副本，等用户定去留，已经搁了半天。
- 第三轮之前插入了 loader 换版。loader 不在被测的图形栈里，但它在引导链上，第三轮如果同时换 AIR 与 loader，就是两个变量。第三轮读的是 `ir3_cache_lookup()` 内部各段的份额，loader 换版影响不到段间比例；这一点要写进轮次注记。
- [AGENTS.md](../../AGENTS.md) §5 写「设备命令只由 device 成员执行，lead 只做枚举与只读查询」。这段会话没有组队，所有设备命令由主 agent 直接执行。规则针对的是多个成员同时向设备发命令的情形，单 agent 会话是否适用，规则里没有写。
- 会话的 PNG 截图第一次是全透明的：帧缓冲第 4 字节为 0，编码时被当成了 alpha。仓库里没有把 `oem screenshot` 原始数据转成图片的工具，每次都临时写脚本。

## 8. 停帧判定把锁屏静止也算了进去

run-auto 的停帧判定只有一条：一份快照里末帧之后 20 秒没有新帧（`K90_FREEZE_SECONDS`），满足就收尾、复位回 loader。它本来是省时间、省 A 槽重试次数的收尾规则，后来的分析把它当成了「帧流永久停止」的判据。画面静止时 CA 也不出帧，这条规则分不开「卡住」与「没东西可画」。

- 作业 `rc.jobs.perf-sustain` 按主屏写：三段水平慢拖，注释说的是 home screen 横向翻页。iOS 26 开机停在锁屏，作业里没有解锁，水平慢拖在锁屏上不一定引起画面变化。
- 第三轮实测：236.2 秒到 261.8 秒之间没有帧，同一段有 3,165 个触摸采样、横坐标走完一整段拖动、没有触摸被丢弃；23:16:00 时钟跳分钟时出了 18 帧，之后又静默，run-auto 据此判停。渲染链路在整分钟时是活的，这次停帧是锁屏静止。第二轮的末帧 771 也落在整分钟（21:24:00.058）。
- 三轮在开机时都有一次背光 0→1（SpringBoard 启动序列），之后到日志结束没有背光或 `displayState` 变化。用户在第三轮看到的黑屏，是 run-auto 收尾后复位重启的那 16.8 秒。
- 归档里观察窗不少于 100 秒、时间换算可靠的 11 轮，末帧之后跨过 2～7 次整分钟，没有新帧，也没有背光变化记录，时钟该更新而没有更新。这 11 轮与今天三轮的形态不同，仍是真停住的候选。

上一会话「停帧不是锁屏或息屏，是归档里那个帧循环停止的签名」这一判断，对今天三轮不成立。慢 draw 是另一件事：它发生在出帧过程中，读数在 draw 内部，不受这一点影响。

下一批应先改测法再追停帧：开机后上滑解锁进主屏；用主动刺激判响应（注入一个必然引起画面变化的动作，看之后 1 秒内有没有新帧），或至少把观察窗拉过下一个整分钟；轮次按固定时长跑完，不靠「20 秒没帧」提前收尾。

## 9. 接手后的顺序

1. 把第一、二轮的读数写进 progress 记录，探针补丁与 baseline 入库。
2. 按 §6 改 loader 屏显，宿主机渲染与 loader 测试通过后提交，按提交号设 `BUILD_ID` 构建，刷入前由用户确认。
3. 按 §5 在第三轮的 AIR 里补三组探针，判据先登记进[下一轮方案](../plan/2026-10-29-next-round-plan.md)，再重编、打包、起轮。
4. 第三轮是这一批的最后一轮，读完按判据分流，停下汇报。结果见[分段三轮](../progress/2026-10-29-state-segment-rounds.md) §5。
