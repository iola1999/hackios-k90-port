# iOS 26 可用桌面：解锁、着色器编译与渲染缺口（2026-10-29 夜～10-30）

本轮工作的目标是让 iOS 26 开机后能进主屏并能操作，判断以截图、日志和手持操作为准，不再从帧间隔推断停帧。前一阶段的结论见[晚间会话审查](../analysis/2026-10-29-evening-session-review.md)。

## 1. 轮次与身份

| 轮次目录 | 作业 | 与上一轮的差别 | 结果 |
|---|---|---|---|
| `kernel-12377-attr26-diag3x-homecycle1` | `rc.jobs.home-cycle`（首版） | 作业换成上划解锁加左右翻页，440 秒定长，`K90_FREEZE_OFF=1` | 自动上划没有解锁；用户手动上划后进主屏，约 20 秒后停帧 |
| `kernel-12377-attr26-diag3x-interactive1` | `rc.jobs.interactive` | 注入 `libredwood-sb26.dylib`（开机自动解锁），去掉 `com.apple.appprotectiond`，驱动线程快照带调用栈，不发合成手势，600 秒 | 开机自动解锁；主屏先只有文字，图标陆续出现；能打开设置并逐级进入 |
| `kernel-12377-attr26-diag3x-lock2cpu4` | `rc.jobs.interactive` | AIR 入口锁，`iconservicesagent` 注入 Metal 注册，4 核 | 开机时 GPU 超时停用，CoreAnimation 退回软件合成；主屏图标与电池图标都显示，应用内上划仍转菊花 |
| `kernel-12377-attr26-diag3x-lock3cpu4` | `rc.jobs.interactive` | 去掉 `iconservicesagent` 的 Metal 注册（`ICON_METAL` 默认关闭） | 4 核正常，无 GPU 错误；从设置上划不再转菊花；主屏没有图标，没有电池图标 |
| `kernel-12377-cmd1-render1` | `rc.jobs.interactive` 加 `rwsh` | 内核 `12377-cmd1`、loader v10、§7.2 的第一批修复 | 开机自动解锁；主屏没有图标、电池图标与壁纸 |
| `kernel-12377-cmd1-render2` | 同上，`cycle.py` 无人值守 | §8 的第二批修复，`ICON_METAL=1` | `iconservicesagent` 第 6 次提交时 GPU 挂起；软件合成下图标与电池图标显示，回主屏后 backboardd 断言崩溃，之后一直转菊花 |
| `kernel-12377-cmd1-render3` | 同上 | AIR 支持沿循环传回的指针；驱动列出每个进程前 16 次提交用到的管线 | 开机 42 秒 GPU 停用；软件合成下主屏、设置、控制中心都能截到，回主屏那一步截到锁屏 |
| `kernel-12377-cmd1-render4` | 同上 | `iconservicesagent` 设 `REDWOOD_SYNC_DRAWS=1`，每个绘制后等它完成；SpringBoard 与 PosterBoard 设 `OS_ACTIVITY_DT_MODE=YES`，打开 os_log | 定位到没有完成的绘制；SpringBoard 的 os_log 占满日志环，开机解锁那一行丢失，巡检没有执行 |
| `kernel-12377-cmd1-render5` | 同上 | 同步模式下打印没有完成的绘制的两个着色器模块；os_log 只开 PosterBoard | GPU 在开机解锁前停用，巡检只截了主屏；取到挂起绘制的模块 |
| `kernel-12377-cmd1-render6` | 同上 | `iconservicesagent` 加 `FD_MESA_DEBUG=sysmem` | 仍然挂起；软件合成下主屏、设置可用，回主屏时 backboardd 断言崩溃，之后转菊花 |
| `kernel-12377-cmd1-render7` | 同上 | 去掉 `sysmem`；同步模式下每个绘制提交前打印一行描述；PosterBoard 加 `OS_ACTIVITY_MODE=debug` | `iconservicesagent` 还没有绘制，GPU 已停用；PosterBoard 的日志没有变多 |
| `kernel-12377-cmd1-render8` | 同上 | `iconservicesagent` 加 `FD_MESA_DEBUG=nolrz`，日志确认进程读到了这个值 | 仍然挂起 |
| `kernel-12377-cmd2-render9` | 同上 | 内核 `12377-cmd2`：打印 HFI 150 的全部字和已完成的 EOP 时间戳 | 第 11 次提交没有完成，是 `iconservicesagent` 的 `primitive__vertex` 绘制；HFI 150 在驱动的两秒等待之后才到，没有打印出来 |
| `kernel-12377-cmd3-render10` | 同上 | 内核 `12377-cmd3`：报告前再读 3 秒 HFI；绘制描述加索引；PosterBoard 注入错误探针 | 第 12 次提交没有完成，是 SpringBoard 的 57 缓冲提交；取到 HFI 150 全文；PosterBoard 的数据存储初始化返回 nil 且没有错误 |
| `kernel-12377-cmd3-render11` | 同上 | AIR 的索引绘制开启图元重启（§8.7）；SpringBoard 设 `IR3_SHADER_DEBUG=vs`；PosterBoard 探针记录数据存储初始化的四步 | 第 9 次提交没有完成，是 SpringBoard 的 57 缓冲提交；SpringBoard 的顶点着色器汇编里没有 `primitive__vertex`；PosterBoard 的迁移返回 0 |
| `kernel-12377-cmd3-render12` | 同上 | SpringBoard 与 `iconservicesagent` 都设 `REDWOOD_SYNC_DRAWS=1` | 第 10 次提交没有完成，是 SpringBoard 第 2 次提交第 3 个 work，`primitive__vertex+ffea2ba11dhmha4`；取到 `primitive__vertex` 的 A830 汇编 |
| `kernel-12377-cmd3-render13` | 同上 | 两个进程设 `AIR_DISCARD=off`，`discard_fragment` 翻译成空操作；SpringBoard 设 `IR3_SHADER_DEBUG=fs`；PosterBoard 探针加迁移的版本号 | 仍然挂起，第 10 次提交是 `iconservicesagent` 的 `primitive__vertex+ffia2ba3ca7dhmha4`；PosterBoard 从 59 迁移到 61 失败 1151 次 |

两轮内核相同（`out/xnu12377-f055cc0a-restored.bin`），cmdline 相同（`cpus=2 bootcpu=7`，`adreno8_speed=3`）。`interactive1` 的驱动为 `ceefc187…`，AIR 仍为 `b5b44d51…`。

## 2. 解锁

- 首版 `rc.jobs.home-cycle` 的 rwtouch 行有约 200 个词，`init` 每行只解析前 63 个词（`userland/src/init.c` 的 `run_command()`），rwtouch 执行到第 63 个词报 `bad step "swipe"` 退出。现在的版本每行不超过 49 个词。
- 两次自动上划发生在锁屏可操作之前：SpringBoard 23:41:24 连上 backboardd，开机 logo 层 23:41:42.3 移除，23:41:37.6～40.6 与 42.3～45.6 两段背光关闭（backboardd 记 `canceling events for suppression reason: backlight dim/off`）。第一次上划在 31.9 s 落在 logo 层上，第二次约 38 s 落在背光关闭期间。用户 23:45:2x 手动上划一次就解锁了，iOS 26 本身的解锁路径没有问题。
- 16.5 的 `inject_sb.c` 在 SpringBoard 启动 10 秒后调用 `-[SBLockScreenManager unlockUIFromSource:withOptions:]`（来源 24）。iOS 26 的 `inject_sb26.c` 没有这一段，而且打包脚本的 `INJECT` 从未加载 `libredwood-sb26.dylib`。
- 现在 `inject_sb26.c` 从第 10 秒起每 3 秒查一次 `isUILocked`，见过锁屏且解锁后停止，最多 60 次；注册 `com.redwood.unlock` 通知（`rwtouch notify com.redwood.unlock`）；`autounlock=0` 保留锁屏。`package.py` 从源码编这个库并注入 SpringBoard。`interactive1` 日志：`sb26: unlock boot: answer=1 locked_after=0`，第 2 次检查时完成。

## 3. 停帧与着色器编译

`homecycle1` 解锁后最后一帧在 23:45:44。之后用户的触摸照常到达 backboardd 并分给 SpringBoard，两个进程的驱动每秒打印 `tl: cnt 0 0 0 0 0`，进程都还活着，只是没有提交。停住时 SpringBoard 的驱动记 `draw 3 has run for 424 ms` 与 `commit 3 has not moved for 2708 ms inside a recorded work`，线程快照里编译线程停在 `libredwoodair.dylib`。收尾时的 `THE KERNEL HUNG ... no sign of life for 50 seconds` 出现在 `oem stop` 之后，是 GPU 资源未归还时的正常收尾（`hung-held`），使用期间内核没有挂死。

`interactive1` 的线程快照带上了调用栈（驱动 `rw_print_threads()`，库内偏移用 `atos -arch arm64e -l 0x0` 还原）：

- 渲染线程：`rwa_render_draw → fd_draw_vbo → fd6_draw_vbos → get_program_state → ir3_cache_lookup → ir3_get_shader → _util_queue_fence_wait`。
- 编译线程：`util_queue_thread_func → create_initial_variants_async → … → ir3_compile_shader_nir`，三次采样分别停在 `nir_opt_cse`、`nir_opt_shrink_stores`、`ir3_legalize`。

第 280 秒前的统计（`ir3q job:` 与 `ir3 wait:` 行）：

| 量 | 值 |
|---|---|
| backboardd 编译线程任务数 | 193 个，墙钟合计 4.97 s，线程 CPU 合计 0.50 s |
| 排在前面的任务数最大值 | 33 |
| 入队到开始的最长时间 | 2.87 s |
| backboardd 渲染线程等待 | 67 次，合计 5.06 s，最长 0.77 s |
| 另一个等待线程（tid 483） | 16 次，合计 6.78 s，最长 1.79 s |

编译队列的线程数是在线 CPU 数的一半，`cpus=2` 下只有 1 个。任务的线程 CPU 只占墙钟的 10%，编译线程多数时间处于可运行但未被调度的状态，或者在等待。

改动（`hackios-xnu-kernel/tools/mesa/ir3-compile-steal.patch`，AIR `62eced7a…`）：

- `util_queue_steal_job()`：把还没开始的任务从队列里取走，且不发出 fence 信号。`ir3_get_shader()` 用它把自己要的任务拿过来在本线程编译，编完再发信号，其他线程照常在 fence 上等。
- 编译队列线程在 Darwin 上设为 `QOS_CLASS_USER_INITIATED`，仍低于渲染线程。在渲染线程上就地执行的任务不改该线程的 QoS。

### 3.1 SpringBoard 主线程永久卡死：`Unhandled ALU op: ffma`

两轮的 SpringBoard 都卡在同一处，日志里各有一次 `Unhandled ALU op: ffma`：

- 着色器是 RenderBox 的片段着色器 `feanea4fba6dhmha4`（管线标签 `primitive_coverage`），出错指令是 `%63 = ffma %62, 0.25, %59`。AIR 前端在 Metal 的 `fma()`（非 fast）和 `llvm.fmuladd` 上发出严格融合的 `nir_ffma`（`tools/mesa/air/air_intrinsics.c`、`air_llvm.inc`）。ir3 的 `float_mul_add32` 只声明了 `has_fmad` 和 `fuse`，NIR 不会为它降级严格 `ffma`，`emit_alu()` 走进 `default` 分支。
- `ir3_context_error()` 结尾是 `UNREACHABLE("")`，release 构建里展开为 `__builtin_unreachable`。编译线程（`interactive1` 的 tid 289）的调用栈停在 `ir3_context_error < ir3_context_error < emit_alu`，之后没有返回。
- SpringBoard 主线程（tid 221）停在 `RenderBox → Metal → rwa_render_draw → fd_draw_vbo → … → ir3_get_shader → _util_queue_fence_wait`。驱动记 `commit 3 has not moved for 2735 ms inside a recorded work` 之后，SpringBoard 每秒的 `tl: cnt` 全是 0，直到收尾。
- 用户看到的现象都由 SpringBoard 主线程负责，因此一起失效：小白条不画，上划回主屏、下拉通知中心和控制中心没有反应，状态栏时间停在 11:58，设置里的侧边返回没有反应。设置本身是另一个进程，页面内的点按照常响应。

修复（`hackios-xnu-kernel/tools/mesa/ir3-ffma-as-mad.patch`，AIR `66ea12d0…`，同时带第 3 节的取任务与 QoS 改动）：

- `emit_alu()` 把 `nir_op_ffma` 按 `nir_op_fmad` 发射。Mesa 在同一处注明 a6xx 以后的 mad 不融合，所以结果比源码多一次舍入。
- `ir3_context_error()` 结尾改为 `abort()`：进程带着着色器转储退出，由 launchd 重启，不再无限等待。

### 3.2 `ffma1` 的结果与 backboardd 崩溃

`ffma1`（AIR `66ea12d0…`，900 秒）用户手持操作的结论：小白条出现，桌面时钟指针走动，控制中心能下拉。整轮 17,152 帧，`interactive1` 为 4,057 帧。编译等待的变化：

| 量 | `interactive1` | `ffma1` |
|---|---|---|
| 单个等待线程的等待合计 | 5.06 s 与 6.78 s | 每个线程 0.03～0.59 s，tid 1056 为 2.03 s |
| 单次等待最长 | 1.79 s | 0.53 s |
| 在渲染线程上就地编译的任务 | 无 | 例如 tid 351 的 43 个任务，墙钟 0.07 s，CPU 0.07 s |

从设置底部上划回主屏会转菊花。这一轮 backboardd 崩了 4 次（pid 38、141、164、184），都是 SIGSEGV，位置在 `libredwoodair` 的 `fd6_vsc_update_sizes` 与附近的 fd6 绘制代码（`fd6_draw_vbos`，`x0` 为 0）。每次崩溃前一行都是驱动的 `commit N started while commit N-1 was still running`；`interactive1` 与 `homecycle1` 没有这一行。backboardd 每次退出后 SpringBoard 被结束（`reason 15`），重启后着色器重新编译，最后一次重启在收尾前没有回到锁屏。

修复（驱动 `5bb05bfd…`）：`-commit` 进入时取一把进程内的递归锁，`redwoodReturnSlot` 之后释放，完成回调在锁外执行。

### 3.3 `lock1`：提交锁之后仍然崩溃

`lock1`（驱动 `5bb05bfd…`）里 backboardd 在同一位置崩溃（pc 在 `fd6_vsc_update_sizes`+32，`x0` 为 0），这次之前没有并发提交的日志行。`fd_draw_vbo()` 在调用 `draw_vbos` 之前刚确认过 `ctx->batch`，`fd6_draw_vbos` 里再读到的却是 NULL。可能的来源是驱动在 `-commit` 之外调用的入口（纹理上传与读回、缓冲纹理刷新）从别的线程刷掉了当前 batch。

修复（AIR `c5bc52ec…`）：`air_metal.c` 加一把进程级递归锁 `rwa_lock`，33 个会碰到 pipe_context 的 `rwa_*` 入口第一句是 `RWA_LOCKED`，用 `__attribute__((cleanup))` 在任何返回路径上解锁。`air_metal_copy.inc` 与 `air_metal_compute.inc` 里也有入口，`tools/k90auto/build-air.py` 的 `FILES` 加上这两个文件，否则改动不会进入构建树。

同一轮另有两条读数：

- backboardd 调用 `IOSurfaceClientQueryTransactionList`（MiniIOSurface 58 号调用，5 个标量入、3 个标量出），内核答 `kIOReturnUnsupported`。`MiniIOSurface.cpp` 对 58 号返回成功和空列表，内核 `12377-cmd1` 起生效：`lock3cpu4` 记 2848 次 `got non-success return from kernel`，`render1` 为 0。
- `iconservicesagent` 没有 Metal 设备，230 次 `Failed to serialize finalized icon ... TextureIOError.usingSoftwareRenderer`。`package.py` 的 `ICON_METAL=1` 把 Metal 注册库注入它，并在它的任务 plist 与 launchd 缓存里设 `REDWOOD_SB_METAL=1`；注册库的目标表有 `iconservicesagent`。`lock2cpu4` 之后默认关闭，见 §6。

## 4. 其他读数

- `appprotectiond` 在 `homecycle1` 里 159 秒平均占 56% 的 CPU（内核 `caught burning CPU`），`interactive1` 起用 `JOBS_DROP` 去掉。
- `iconservicesagent` 开机后 12 秒内做了 1149 次图标缓存垃圾回收，之后持续报 `Failed to serialize finalized icon`。
- `homecycle1` 主核簇最高 78.3 °C（`cpufreq: ... hottest 78.3 C`）。
- 插着 USB 时电池在放电：`lock1` 的电量计电流为 -300～-760 mA，SOC 一直是 80%。loader 读高通 UEFI 充电缓存 25 次失败 13 次，最后一次是 `charger=0 charging=0`，内核据此报「not on a charger」。状态栏右上角的电池图标不显示，控制中心里显示 80%、未充电。

## 5. 截图里的渲染缺口（`interactive1`、`ffma1`）

- 设置页向下滚动后，顶部导航栏的滚动边缘模糊不对：背后的列表内容被拉成横向条纹，没有纵向模糊；模糊区下半段整片发黑，没有渐隐到下面的内容。backboardd 在这段时间建的管线里有 `variable_blur_vert_lph`／`glass_background_no_bleed_lph`、`downsample_blur_vert_lph` 配 `downsample_4_frag_lph`、`downsample_8_frag_lph`、`narrow_blur_19_frag_lph`。用户另报滚动时闪烁较多。
- 设置「通用」页各行左侧图标和页首大图标都是灰色空方块；设置首页的「电池」一行缺图标。
- 103～332 秒之间所有截图的状态栏时间都是 11:58。
- 「关于本机」的歌曲、视频、照片一直是 Loading…，容量为 Zero KB。这一条属于系统数据服务，与渲染无关。

## 6. `lock2cpu4` 与 `lock3cpu4`

- `lock2cpu4` 给 `iconservicesagent` 注册了 Metal。它的绘制被拒绝了 3 类：`device` 缓冲绑在 40、344 字节偏移；RGBA16Float 表面每行 576、448、192、704 字节；格式 90（RGB10A2Unorm）17 次。随后内核报 `adreno8: context EOP timeout failed; submissions closed`，GPU 停用到冷启动，CoreAnimation 改用软件合成，主屏图标和电池图标在软件合成下都能显示。
- `lock3cpu4` 去掉了这项注册，`GenericARMPE: 4 of 4 processors are running`，12 份日志快照里没有 GPU 错误。从设置上划返回不再转菊花（用户确认）。主屏只有文字、没有电池图标。

## 7. 从日志自动找渲染问题

### 7.1 工具

`tools/k90auto/render-health.py` 合并一轮的日志快照，把驱动、AIR 库、QuartzCore 的 Metal 日志、MiniIOSurface 与 GPU 驱动里的失败行按类别分组计数，并能和另一轮逐行对比。用法与读法见 `tools/k90auto/README.md` §8。合并时发现两点：

- 每份快照是同一段开机日志头加一个 1 MB 的环。`lock3cpu4` 里有 3 次两次拉取之间环已转过一整圈，这几处的行丢了；之前的合并在这里把整份快照连同日志头重新接上，开机阶段的行会被数 4 次。现在只接日志头之后的部分，并报告缺口数。
- backboardd 每个慢提交按 work 各打一行 `commit N has run for`，`lock3cpu4` 的一个快照窗口里有 2489 行，占满了环的三分之一。现在每当提交时长翻倍才打一行；`rd in` 的门槛从 50 ms 提到 500 ms；无拷贝缓冲的 `copied` 行只打前 32 次和每第 256 次。

### 7.2 `lock3cpu4` 的读数与第一批修复（`render1`）

| 类别 | 次数 | 原因 | 修复 |
|---|---|---|---|
| QuartzCore `Failed to allocate MTLTexture from IOSurface` | 988（其中 0xf8 号表面 883） | 驱动的 IOSurface 导入不认格式 30（RG8Unorm） | 格式表加 30 对 `'LA08'`（SpringBoard 与 Spotlight 建的两字节像素表面） |
| `compute_average_luma` 调度失败、命令缓冲报错 | 各 160 | 线程组缓冲的长度由 `-setThreadgroupMemoryLength:atIndex:` 给，调度入口没有这个参数 | AIR 新入口 `rwa_dispatch_threadgroup`，动态线程组缓冲排在静态线程组数组之后，Gallium 用 `variable_shared_mem` 加上这段长度；驱动记下编码器给的长度 |
| SpringBoard `the draw failed` | 10 | 渐变着色器的 `device` 缓冲绑在 124 字节偏移，Gallium 的 `shader_buffer_offset_alignment` 为 64 | 改为 4，与 turnip 的 `minStorageBufferOffsetAlignment` 相同（`tools/mesa/freedreno-ssbo-offset-4.patch`） |
| `nil buffer from memory`（640x155，114688 字节） | 12 | 无拷贝缓冲只接受 64 KiB 以内 | 上限改为 16 MiB |
| `Failed to allocate [281 x 609] BGRA framebuffer` | 3 | QuartzCore 在这之前调用 `newTextureWithDescriptor:iosurface:plane:` 得到 nil | 由拒绝日志定位，见下一行 |
| 驱动 `no drawable` | 按 2 的幂打印 | 打印次数由所有原因共用一个计数 | 前 64 次逐条打印，带 Metal 格式、用途和表面的 FourCC、尺寸、行字节数 |
| IOSurface 58 号调用 | 2848 | 内核未实现 | 内核 `12377-cmd1` |

RGBA16Float 表面的行字节数第一批放宽到 64 字节（只采样的导入）。`render1` 对比 `lock3cpu4`：上表各项在 `render1` 均为 0，但这一轮没有打开设置，部分路径没有走到，需要 `render2` 的固定巡检对比。

## 8. `render1`：图标、电池图标与壁纸

截图（`kernel-12377-cmd1-render1/run/tour-sheet.png`）：壁纸全黑，应用图标、小组件内容和程序坞里的图标都没有，标签和程序坞底板在；状态栏只有时间。缺的都是其他进程以 IOSurface 交来的内容，SpringBoard 自己画的部分都在。

- `iconservicesagent` 仍是软件渲染：231 次 `Failed to serialize finalized icon ... TextureIOError.usingSoftwareRenderer`，开机后反复做图标缓存垃圾回收（1148 次）。图标没有生成出来。
- `sb26: icon rendering Metal device=1`：SpringBoard 有 Metal 设备，`SBIconImageView` 走 Liquid Glass 的 Metal 绘制。SpringBoard 把一张 120x120、每行 960 字节的 RGBA16Float 表面当渲染目标导入（`usage 0x5`），被 128 字节的行对齐拒绝。
- PosterBoard（pid 38）在运行，日志里没有它的输出；三个线程都在等待。壁纸由谁绘制、为什么没有内容，留给图层树读数。

第二批修复（`render2`）：

- 行字节数按用途放宽：只采样的导入只要求整像素，A8XX 纹理描述符的 `TEX_LINE_OFFSET` 以位为单位；颜色渲染目标要求 64 字节，这样的渲染目标由 `fd_gmem_render_tiles` 改用 sysmem 直接写入，GMEM 回写按 16 像素块写，会越过行尾。`fdl_pitch` 的第 0 级返回导入时给的行字节数。补丁 `tools/mesa/fdl6-linear-import-pitch.patch`，驱动侧的 64 字节检查一并去掉。
- AIR 格式表加 90～94（RGB10A2Unorm、RGB10A2Uint、RG11B10Float、RGB9E5Float、BGR10A2Unorm），按首个通道在低位的布局对应 Gallium 格式。
- SpringBoard 注入库加图层树读数：rwsh 发 `notify com.redwood.layers.<过滤词>`，见 `tools/k90auto/README.md` §8。
- `ICON_METAL=1`：上面三项覆盖了 `lock2cpu4` 里 `iconservicesagent` 被拒绝的绘制，这一轮重新给它注册 Metal。

### 8.1 `render2`

- 开机 41 秒（01:48:52）`iconservicesagent` 的 `path_exterior` 管线被拒绝（顶点模块里有一个沿循环回边传回的指针 phi），RenderBox 记 `precondition failure: pipeline error`。
- 接着它的第 6 次提交（20 个缓冲，10x10 的三个颜色附件加深度，管线 `primitive_coverage`、`primitive_color`）没有完成：GMU 发 `HFI fatal message 150 data 0x1`，内核关闭 GPU 提交，驱动报 `THE GPU DID NOT FINISH`。KGSL 的编号里 150 是上下文出错，`0x1` 是 GPU 硬件挂起。
- 之后 CoreAnimation 走软件合成，主屏图标、小组件和电池图标都显示（`tour-sheet.png` 0、1 号）；打开设置并滚动正常；上划回主屏后 backboardd 在 `ogl-context.cpp` 的 `push_surface` 断言失败，SpringBoard 与 backboardd 各重启两次，屏幕停在菊花。
- `render3` 的改动：AIR 支持沿循环传回的指针（偏移放进寄存器，资源必须相同）；驱动在每个进程的前 16 次提交里列出用到的管线，`render-health.py` 在 GPU 停止时把最后几次提交和这些管线按着色器名打印出来。

### 8.2 `render3`

- `path_exterior` 不再被拒绝。新出现的拒绝：顶点模块里 phi 的某个操作数本身是运行时选出的指针（`iconservicesagent` 4 次，SpringBoard 1 次）；片段模块调用只声明未定义的 `custom_fn.MTL_VISIBLE_FN_REF`（2 次）；`fpba2ma11bemha4` 读 1 号纹理而只绑定了 1 张纹理（3 次）。
- 01:55:31 内核报 `context EOP timeout failed; submissions closed`。停止前最后几次提交来自 `iconservicesagent`（9～13 号）和 SpringBoard（14 号），几个进程的提交交错，`trace commit` 列出的管线不能指出是哪一个绘制没有完成。
- 截图（`kernel-12377-cmd1-render3/run/tour-sheet.png`）：主屏图标、小组件、设置、控制中心都在，壁纸仍是黑色；设置滚动后顶部的「Settings」小标题和底部搜索栏下面没有模糊背景，列表文字直接透出来；回主屏那一步截到的是锁屏。01:56:30 backboardd 在 `push_surface` 断言失败，SpringBoard、backboardd、`iconservicesagent` 各运行了 3 个进程。

### 8.3 `render4`

- 驱动的 `REDWOOD_SYNC_DRAWS=1`（打包时由 `JOB_ENV` 加给指定任务）在每个绘制之后提交并等待完成，没有完成的那个绘制按管线、附件数和绑定数打印。`iconservicesagent` 第 1 次提交的第 2 个绘制没有完成：`primitive__vertex` 加片段着色器 `fe2baca3dba6dhmha4`，3 个颜色附件，没有纹理，1 个缓冲。同一提交的第 1 个绘制（`ffebaca3ca7dhmha4`）完成了。
- `fe2baca3dba6dhmha4` 不在 RenderBox 的 `default.metallib` 里。`archive.metallib` 是一个 Mach-O，装着 17 个约 732 字节的函数拼接描述，这类着色器在运行时拼出，模块只能从日志里取。
- SpringBoard 打开 os_log 后，合并日志有 180 MB、12 处缺口，开机解锁那一行落在缺口里，`cycle.py` 没有执行巡检。本轮各类计数也受缺口影响，`render3` 的部分拒绝在这里计为 0 不能说明已经消失。
- `render5` 的改动：同步模式下驱动保留每个渲染管线的两个模块，绘制没有完成时以 `AIRFAIL begin hung-vertex`／`hung-fragment` 打印出来，`render-health.py` 单独归为 `hung-shader`；os_log 只开 PosterBoard。

### 8.4 `render5` 与 `render6`：挂起的绘制

三轮里没有完成的绘制都来自 `iconservicesagent`，形状相同：顶点着色器 `primitive__vertex`，片段着色器是 RenderBox 运行时拼出的 `primitive` 类，3 个颜色附件，没有纹理，1 个缓冲。

| 轮次 | 位置 | 片段着色器 | 帧缓冲读取 |
|---|---|---|---|
| `render4` | 第 1 次提交第 2 个 work | `fe2baca3dba6dhmha4` | 未取到模块 |
| `render5` | 第 2 次提交第 4 个 work | `ffia2ba3ca7dhmha4` | 读 1 号渲染目标 `coverage` |
| `render6` | 第 1 次提交第 4 个 work | `ffeba5ca7jbmhia3` | 没有 |

- 两个取到的片段着色器都没有循环和内存写入：先由 `fwidth` 算边缘覆盖率，覆盖率为 0 时 `discard_fragment`（NIR 里是 `demote`），再写 `color`（half4）和 `coverage`（half2）两个输出。宿主上用当前 AIR 源码编的 `air2nir` 翻译结果没有发现异常。
- `render6` 用 `FD_MESA_DEBUG=sysmem` 让 `iconservicesagent` 的批次不走 GMEM，仍然挂起；这个开关是否生效，日志里没有读数。
- `render4`～`render6` 的内核不打印已完成的时间戳，同步模式下没有完成的绘制可能排在别的进程挂起的提交之后（§8.5），上表三行的归属都没有确认。
- `render6` 里第 2、3、4 个 work 各自一次提交，命令流都是 353 个字，只有第 4 个没有完成；内核报 `RedwoodGPU no answer; last timestamp 9; SMMU fault 0`，没有缺页。
- 软件合成下回到主屏时 backboardd 在 `ogl-context.cpp` 的 `push_surface` 断言失败（`render3`、`render6` 都出现），这一步只在 GPU 停用之后发生。
- `render7` 的改动：同步模式下每个绘制在提交前打印一行，包括图元类型、顶点与实例数、每个颜色附件的格式、尺寸、采样数、是否基于 IOSurface、是否清除，以及深度附件、视口与裁剪，用来对照同一个 pass 里完成和没完成的绘制；PosterBoard 加 `OS_ACTIVITY_MODE=debug`。

### 8.5 `render7` 与 `render8`

- 内核给所有进程只用一个 GMU context（`adreno8_context_submit`），提交按顺序完成；同步模式下某个绘制没有完成，只有它之前所有进程的提交都完成了，挂起的才是这个绘制。`render11` 里 `iconservicesagent` 报没有完成的绘制排在 SpringBoard 挂起的第 9 次提交之后。归属以 retired 时间戳和 HFI 150 的时间戳为准（`render9` 起）。
- `render7` 里 GPU 停在 SpringBoard 的第 4 次提交（57 个缓冲、3385 个字）或 `iconservicesagent` 没有绘制的第 5 次提交（150 个字），日志分不出是哪一个。
- `render3`、`render5`～`render8` 停用前一秒内都有 SpringBoard 的 `fpba2ma11bemha4 reads texture 1 and 1 texture was bound`。这次拒绝发生在 CPU 侧、在设置任何 Gallium 状态之前，和挂起同时出现，是因为两个进程都在解锁时开始画图标。
- `render8` 的绘制描述：`iconservicesagent` 画图标的 pass 有三个颜色附件，依次是 RGBA16Float（115）、RG16Float（65）、RGBA16Float，深度附件是 Depth32Float_Stencil8（260），深度附件清除，深度测试并写入，绘制是带裁剪的索引三角形带，尺寸在 64x64 到 128x128 之间。
- 各轮完成的 `iconservicesagent` 绘制都用 `plane__vertex`，挂起的都是第一个用 `primitive` 类顶点着色器（`primitive__vertex`、`primitive_gradient_vertex`）的绘制。两个着色器翻译成 NIR 后没有循环和异常结构。
- `render8` 关掉 LRZ 后仍然挂起，LRZ 不是 `iconservicesagent` 挂起的原因。
- 内核只打印 GMU `context bad`（150）消息的第二个字。`render9` 换内核 `12377-cmd2`：打印这条消息的全部 26 个字，`RedwoodGPU ... no answer` 一行加上已完成的 EOP 时间戳。

### 8.6 `render9` 与 `render10`：GMU 的挂起报告

- `render9` 的内核行是 `last timestamp 12, retired 10`：第 11 次提交没有完成，即 `iconservicesagent` 第 2 次提交第 4 个 work，`primitive__vertex+ffia2ba3ca7dhmha4`，10 个索引的三角形带。同一 pass 里完成的绘制是 4 个索引的四边形（索引 `1 0 2 3`）和 64 个索引、多实例的路径。
- `render10` 挂起的是第 12 次提交，即 SpringBoard 的 57 缓冲提交，其中也有一个 `primitive__vertex` 绘制（`ffea2ba11dhmha4`）。两个进程挂起的批次都含 `primitive__vertex`，片段着色器各不相同。
- `primitive__vertex` 用 16 位的 `vertex_id` 做整数运算（`and`、比较），按 `vid > 3` 分支算外圈顶点，10 个索引是绕矩形一圈的三角形带。`render12` 取到的 A830 汇编见 §8.9。

`render10` 的 HFI 150 全文（26 个字）按 KGSL 的布局读：

| 字 | 值 | 含义 |
|---|---|---|
| 1 | 1 | 版本 |
| 2、3、4 | 1、2、0xc | GC context 1，policy 2，时间戳 12 |
| 5、6、7 | 0xffffffff、1、0 | 没有 LPAC context |
| 8 | 0x259 | 错误码，对应的名称还没有查到 |
| 9 | 0x00100002 | 第 2 类（ringbuffer）的段，16 个字 |
| 10～25 | 键值对 | RB 0，RPTR 0x548，WPTR 0x5f9，大小 0x2000 字，已排队时间戳 13，已完成时间戳 11，基址 0x10028000 |

报告里没有错误寄存器段（第 1 类），GMU 报的是 CP 停在第 12 次提交上，没有报操作码错误或受保护寄存器写入。

### 8.7 Metal 的图元重启

Metal 的索引绘制总是开启图元重启：16 位索引的 0xFFFF、32 位索引的 0xFFFFFFFF 结束当前图元，所有图元类型都是这样（Apple `drawIndexedPrimitives` 文档，gpuweb issue 1220 引用了原文）。AIR 的绘制原先写的是 Metal 没有重启索引并关闭了重启，现在改为索引绘制都开启，重启值不计入索引范围。这一项从 `render11` 起在机上，`render13` 挂起的仍是 10 个索引的 `primitive__vertex` 绘制，挂起和图元重启无关。

### 8.8 PosterBoard 的数据存储

- `render10` 的探针读数：`-[PBFPosterExtensionDataStore initWithURL:...]` 的 URL 是 `file:///var/mobile/Library/Application%20Support/`，返回 nil，错误为 nil；调用方随后生成 `Data store could not be created for an unknown reason which evades explanation`。
- 传入的 extension provider 是 nil，这是调用方 `buildDataStoreForURL:` 写死的（`mov x4, #0`），不是失败原因。
- 初始化里没有新建 NSError。之前的 57 个错误来自旧壁纸迁移读 `/var/mobile/Library/SpringBoard/LockBackground*.jpg`、`HomeBackground*.jpg` 等文件不存在，以及 `com.apple.managedconfiguration.profiled.public` 查找失败。
- 初始化会在四处返回 nil：迁移失败、bundle ID 迁移失败、完整性校验失败、SQLite 数据库打开失败。这四处只发 `os_signpost`，控制台看不到，探针在 `userland/src/inject_posterboard.c`。
- `render11`、`render13` 的读数：`isDataStoreUpToDateForCurrentVersion` 为 0，`_mostUpToDateValidDataStoreToMigrateFrom` 为 NSNotFound，`+migrateDataStoreAtBaseURL:fromVersion:59 toVersion:61 ...` 返回 NO 且没有错误，初始化随后返回 nil。PosterBoard 一直重试，`render13` 里重试了 1151 次。
- 迁移的版本范围由两个类方法给出，最低 59、当前 61。一个版本有效的条件（`_PBFDetermineDataStoreViabilityForVersionWithinBaseURL`）是数据存储、扩展容器、图库缓存三个目录存在，60 起还要有 SQLite 库，并且每一项都满足 `+expectedURLResourceValuesForDirectories` 给出的资源值。
- 这组资源值只有一项，值来自 `+expectedFileProtection`，即文件保护等级。RAM 盘所在的卷不支持数据保护（同一日志里 chronod 记 `volume does not support data protection`），这一项读回来不会相符，推断任何版本都不会有效，迁移每次都失败。
- 改动：注入库让 `expectedURLResourceValuesForDirectories`、`...ForFiles` 与 `expectedSnapshotURLResourceValues` 返回空字典，有效性只剩存在性检查。还没有上机。

### 8.9 `render11`～`render13`：挂起绘制读帧缓冲

- `render12` 的 HFI 150 时间戳是 10，已完成 9，即第 10 次提交，SpringBoard 第 2 次提交第 3 个 work：`primitive__vertex+ffea2ba11dhmha4`，4 个索引的四边形，128x128 的三个颜色附件，深度测试只读，绑定 1 个纹理。同一提交的第 1、2 个 work 完成。
- 第 2 个 work 的顶点着色器 `vhia3ea2dba6dhmha4` 与 `primitive__vertex` 的 A830 汇编只差常量偏移、一组输出和指令顺序，两者都没有循环，主体里都没有内存访问。顶点着色器不是挂起的区别所在。
- `render13` 去掉 `discard_fragment` 后仍然挂起，HFI 150 时间戳 10，是 `iconservicesagent` 第 2 次提交第 4 个 work，`primitive__vertex+ffia2ba3ca7dhmha4`，10 个索引。日志确认两个进程都读到了 `AIR_DISCARD=off`。丢弃片元不是挂起的原因，这个开关只用于这一轮，AIR 源码里没有保留。

有时间戳确认的两个挂起绘制，片段着色器都读帧缓冲：`ffea2ba11dhmha4` 读 0 号目标 `dest` 与 1 号目标 `coverage`，`ffia2ba3ca7dhmha4` 读 1 号目标。`render13` 的片段着色器汇编里，帧缓冲读取是两条 `isamm.a.s2en.uniform.base4`，按片元坐标、`VARYING_SLOT_LAYER` 与采样号读 bindless 描述符 0x37、0x38。有汇编可查的完成绘制（`fca15dhmha4`、`fhia3ea2dba6dhmha4`、`fpba2ia11bemha4`）都不读帧缓冲。

freedreno 对读帧缓冲的绘制有三处特殊处理，挂起可能出在其中之一：

- 批次带 `FD_GMEM_FB_READ`，总走 GMEM。描述符由 `patch_fb_read_gmem` 的 A8XX 分支从零拼出，基址是 GMEM 内偏移；turnip 的同类描述符从完整的视图描述符改出（`tu_cmd_buffer.cc`），两者至少 7 号字（数组层偏移）不同：freedreno 填资源的层大小，turnip 在单层时填 0。
- `GRAS_SC_CNTL.single_prim_mode` 在 GMEM 下设为 `FLUSH_PER_OVERLAP`，因为 AIR 把帧缓冲读取标为 coherent。
- `freedreno-darwin.patch` 在一个批次里第一个读帧缓冲的绘制之前加 `CCU_CLEAN_COLOR` 与 `CACHE_INVALIDATE`。这一段是为 a642l 写的，同步模式下每个绘制自成一个批次，每个读帧缓冲的绘制都会带上。

`render6` 用 sysmem 仍然挂起，但那一轮的归属没有确认（§8.4），不能据此排除 GMEM 路径。为了区分这三处，内核 `12377-cmd4` 在挂起报告之后读 RBBM 与 CP 状态、各级 IB 的基址与剩余长度，并打印 CP 位置前后的命令字，用 `tools/k90auto/cp-words.py` 解成包名。还没有上机。

## 9. 无人值守的一轮

- 命令通道：loader v10 的 `oem sh`、内核 `kern.redwood.cmd`、iOS 上的 `rwsh`、主机上的 `tools/k90auto/rsh.py`，`render1` 里 `ps` 与 `dump 38` 都有回应。
- `tools/k90auto/tour.py` 经命令通道点按、滑动并截图，同一步的两张截图在状态栏以下比较差异，所有截图拼成一张编号的图。
- `tools/k90auto/cycle.py` 串起打包、payload、上传、等开机解锁、固定巡检、提前结束和渲染报告，每两轮在 LK 重置 A 槽重试次数，loader 状态不对就停止。

