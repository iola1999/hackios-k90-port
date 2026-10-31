# backboardd 合成路径的处理器开销（2026-10-31）

用户在 2026-10-31 反馈滑动卡、机身发热、右上角没有电池图标。本文记录 backboardd 合成路径上的改动与读数：描边线宽、调用方内存的 buffer、提交合并、驱动探针的开销，以及之后的 buffer 纹理导入、面板按行更新、GPU 频率、GPU 完成中断和没有反应的手势。逐轮读数见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md)，开机图标的根因见[每次开机都是首次开机](2026-10-31-every-boot-is-first-boot.md)。

## 1. 结论

- 翻页帧率分两档，由每帧的绘制次数决定：主屏页每帧约 75 次绘制，今天视图（小组件页）约 410～430 次。从第 1 页向右滑会进入今天视图，所以同一组翻页里两档交替出现。
- 电池图标的外框与填充是 `CAShapeLayer` 的描边，backboardd 把它画成线段图元。AIR 的光栅化状态线宽为 0，freedreno 按线宽的一半写线段的半宽，线段不出像素。线宽改为 1 后电池图标显示（`bo6`）。
- `newBufferWithBytesNoCopy:` 创建的 buffer 原来是一份拷贝，每次提交前要把调用方的整块内存读回并哈希。内核新增 `kRedwoodMemory`，把调用方的内存页直接做成 GPU buffer，这一步去掉了（`bo9`）。
- freedreno 的提交合并在这里没有生效，今天视图每个显示间隔向内核提交约 33 次。打开合并后约 3 次（`bo10`）。
- 驱动里为排查慢绘制加的探针，每次绘制调用 10 次 `thread_info`、8 次 `getrusage`，占了每次绘制驱动耗时的约四分之三。去掉后今天视图每帧的驱动耗时从 16.8 毫秒降到 4.4 毫秒，backboardd 全轮处理器时间从 158.6 秒降到 97.2 秒（`bo11`）。
- 调用方内存 buffer 上的纹理，导入时 buffer object 的大小是 0，布局检查失败后退回拷贝。导入时带上大小后，`bo12` 打印出的导入全部成功。
- 面板只重画源图像里变了的行（`12377-cmd38`）。屏幕静止时每帧的面板拷贝从约 8.2 毫秒降到 1.6 毫秒（`bo14`）。
- GPU 最高频率按设备树的档位从 342 MHz 提到 607 MHz（`12377-cmd39`）。今天视图翻页时 GPU 忙碌比例从 94% 降到 56%，GPU 最高 49.8 °C（`bo15`）。
- 等 GPU 的线程改为睡到 GMU 的消息中断（`12377-cmd40`）。主屏翻页 0.57 秒窗口里帧率 61～63 帧／秒的窗口变多，快档中位数 56.2 帧／秒（`bo16`）。
- §6 之后留下的计时点每次绘制仍读多次时钟，`bo16` 里 `mach_absolute_time` 占 backboardd 用户态样本的 18%。默认关闭后，backboardd 每帧处理器时间从约 9.3 毫秒降到 5.8 毫秒（`bo17`）。
- 一部分手势完全没有画面响应：`bo16` 的 84 步里有 7 次滑动没有出帧，内核收到了每次滑动的 40 个触摸采样，之后约 4 秒里 backboardd 与 SpringBoard 都没有提交。这些滑动的抬起事件没有到 backboardd 处理触点的函数，读数见 §12。
- 今天视图上下滚动时 backboardd 因 AIR 缺 `air.fmax3` 退出，补上三元最值后不再退出（`bo19`），见 §14。

## 2. 帧率的两档

- 翻页从屏幕边缘起手，每 5 对左右滑按一次主屏键（`bo5` 起）。按主屏键回到第 1 页；之后哪几对落在今天视图，取决于哪一次滑动没有翻过去。
- 0.57 秒的手势窗口按帧率分组：不低于 45 帧／秒的算快档，5～45 帧／秒的算慢档。

| 轮次 | 快档窗口数 | 快档中位数（帧／秒） | 慢档窗口数 | 慢档中位数（帧／秒） | 改动 |
|---|---|---|---|---|---|
| `bo5` | 30 | 49.3 | 23 | 28.0 | 基线（`12377-cmd33`） |
| `bo6` | 52 | 49.2 | 33 | 26.3 | 描边线宽 1 |
| `bo9` | 43 | 52.9 | 29 | 30.0 | 调用方内存的 buffer（`12377-cmd36`） |
| `bo10` | 34 | 52.8 | 38 | 35.1 | 提交合并 |
| `bo11` | 42 | 54.3 | 25 | 36.8 | 探针只读时钟 |

- backboardd 记录的慢提交（`commit N took N ms over N recorded works`）里，绘制次数不少于 300 的提交耗时中位数：`bo5` 33 毫秒、`bo6` 34 毫秒、`bo9` 30 毫秒、`bo10` 30 毫秒，绘制次数中位数 408～413。
- GPU 侧：`bo10` 慢档每帧 GPU 执行约 12 毫秒，频率 342 MHz，GPU 没有满载。慢档的瓶颈在 backboardd 的处理器时间。

## 3. 描边线宽

- 电池图标的外框与填充是两个 `CAShapeLayer`。backboardd 用管线 `TcmaA2LlnXhf`（顶点函数 `VfxLlnXh`）画它们，图元是 `MTLPrimitiveTypeLine`。
- AIR 建光栅化状态时没有设线宽，`line_width` 为 0。freedreno 在 `fd6_rasterizer.cc` 里写 `linehalfwidth = line_width / 2`，半宽为 0 的线段不覆盖任何像素。
- Metal 的线段固定 1 像素宽，所以 AIR 的光栅化状态加上 `.line_width = 1.0f`（`tools/mesa/air/air_metal.c`）。`bo6` 的截图里电池外框与填充显示，巡检用的六个测试图层（`notify com.redwood.shapes.test`）的描边也显示。

## 4. 调用方内存的 buffer

原来的做法：

- `newBufferWithBytesNoCopy:` 的 buffer 由 AIR 另分配一块 GPU 内存，把调用方的内容拷进去，再记下调用方的地址（`rwa_buffer_set_mirror`）。
- 每次提交前，`rwa_buffer_textures_refresh` 对每个建在这类 buffer 上的纹理调用 `buffer_mirror_pull`：用 `vm_read_overwrite` 按 16 KB 一段读回调用方的整块内存，再按行哈希判断要不要重新上传。

现在的做法：

- 内核的 `RedwoodGPUUserClient` 新增方法 `kRedwoodMemory`（0x7c，`RedwoodGPUMemory.inc` 的 `memoryBuffer`）。它用 `IOMemoryDescriptor::withAddressRange` 包住调用方的地址范围并 `prepare`，再交给 `newBuffer` 做成 GEM buffer，返回句柄。
- AIR 的 `rwa_buffer_from_memory`（`air_metal_texture.inc`）用这个句柄经 `resource_from_handle` 导入，再映射出来。`redwoodmetal.m` 的 `initWithBytesNoCopy` 先走这条路，失败时退回拷贝。
- 只读的内存区域按读写方向 `prepare` 会返回 `KERN_PROTECTION_FAILURE`。内核改按只读方向 `prepare`，buffer 带 `MSM_BO_GPU_READONLY`。

调用方内存再映射回同一进程时的三个问题：

- `12377-cmd34`（`bo7`）：同一进程里映射一段本来就属于它的内存，`IOMemoryDescriptor` 直接返回原地址。buffer 释放时的解除映射把调用方自己的内存也解除了，backboardd 在 `buffer_texture_upload` 读到未映射的地址，崩溃 16 次。
- `12377-cmd35`（`bo8`）：映射加 `kIOMapUnique` 能拿到新地址，但解除映射时 `is_io_connect_unmap_memory_from_task` 带着 `kIOMapReference` 再走一次 `doMap`，内核 data abort。
- `12377-cmd36`（`bo9` 起）：改用 `kIOMapGuardedSmall`。映射得到带保护页的新地址，解除映射时 `copyCompatible` 按同样的标志找到这份映射。`bo9`、`bo10` 没有崩溃。

结果：`bo9` 三个进程打印出来的这类 buffer 全部走了新路（backboardd 40 个、SpringBoard 32 个、iconservicesagent 32 个，日志只打印前 32 个和之后每第 256 个）。`bo9` 的处理器采样里没有 `buffer_mirror_pull`，慢档中位数从 26.3 升到 30.0 帧／秒。

## 5. 提交合并

- freedreno 的 `fd_submit_sp_flush` 可以把几次刷新攒成一次提交。条件有两个：`should_defer` 要求待提交的 buffer 不超过 30 个、命令不超过 128 条；`has_shared` 要求这次提交不引用共享 buffer，除非管道设了 `no_implicit_sync`。
- backboardd 每帧都引用 IOSurface，`has_shared` 总是成立，每次刷新都单独提交。内核的 `tl: Q` 行按显示间隔（相邻两条 `tl: v`）计数，backboardd 命令超过 20000 字的间隔里，`bo9` 的提交次数中位数 33（十分位 27～42），`bo10` 为 3（3～4）。
- 改法（`tools/mesa/fd-submit-merge.patch`）：Darwin 上不按共享 buffer 阻止合并，RedwoodGPU 不按共享 buffer 给提交排序；待合并的命令上限改为 64 条，内核单次提交最多接受 82 条（`GPU_A830_SUBMIT_CMDS`）。
- AIR 的 `rwa_flush` 刷新时不再等待，用 0 超时的 `fence_finish` 把攒下的提交交给内核，fence 留给 `rwa_finish` 等。

`bo9` 与 `bo10` 中每帧不少于 300 次绘制的统计窗口（backboardd 的 `perf flush` 行，取中位数）：

| 轮次 | 每帧绘制 | 驱动耗时（毫秒） | 其中资源跟踪（毫秒） | 提交耗时（微秒） |
|---|---|---|---|---|
| `bo6` | 412 | 20.3 | 5.9 | 259 |
| `bo9` | 397 | 25.3 | 9.3 | 165 |
| `bo10` | 414 | 16.8 | 0.5 | 15 |

资源跟踪里的时间来自 `fd_batch_resource_read_slowpath`：读一个正被另一个批次写的资源时，freedreno 先刷新并提交那个批次。合并之后这部分从 9.3 毫秒降到 0.5 毫秒。

## 6. 探针的开销

- 2026-10-29 起为排查秒级的慢绘制，freedreno 与 AIR 里陆续加了分段计时（`tools/mesa/fd6-draw-seg-slow.patch` 等）。每个时间点除了读时钟，还用 `thread_info` 读本线程的处理器时间、用 `getrusage` 读进程的缺页数。
- 每次绘制经过 8 个这样的时间点（`draw_vbos<>` 的入口、状态、发射前后、streamout 前后、清理前后），另有 AIR 在 `draw_vbo` 前后的 2 次 `thread_info`。`fd_bo_cpu_prep` 每次调用还有 1 次。
- `bo9` 的内核采样（只采 backboardd）：内核态样本 2070 个，用户态 1794 个。内核态的前两项是 `ml_set_interrupts_enabled_with_debug` 与 `hw_lck_ticket_contended`，采样器只记 PC 与 LR，看不到是哪个系统调用。
- `bo11` 把这些时间点改为只读时钟（`tools/mesa/fd-probe-wall-only.patch`），AIR 去掉 `thread_cpu_us`。

`bo10` 与 `bo11` 的对比（backboardd，中位数）：

| 读数 | `bo10` | `bo11` |
|---|---|---|
| 每 256 次绘制里 `draw_vbo` 的耗时（毫秒） | 9.8 | 2.3 |
| 每次绘制的 `draw_vbo`（微秒） | 38.3 | 9.1 |
| 今天视图每帧的驱动耗时（毫秒） | 16.8 | 4.4 |
| 今天视图相邻两次刷新的间隔（毫秒） | 35.7 | 23.8 |
| 记录下来的慢提交（条） | 2794 | 260 |
| 巡检结束时 backboardd 的处理器时间（秒，用户态／系统态） | 158.6（85.5／73.0） | 97.2（73.1／24.1） |
| 巡检结束时全部进程的处理器时间（秒） | 302 | 238 |

慢档帧率只从 35.1 升到 36.8 帧／秒。今天视图每帧的驱动耗时降到 4.4 毫秒后，帧间隔仍有 23.8 毫秒，瓶颈已不在驱动的处理器时间，见 §7。

## 7. buffer 纹理导入的大小

- `bo11` 里建在调用方内存 buffer 上的纹理，导入（`buffer_texture_alias`）大多失败：每个进程只打印前 16 次，backboardd 与 SpringBoard 打印出的全部失败，iconservicesagent 失败 9 次、成功 6 次。失败都在 Gallium 的布局检查，`fd_screen_bo_from_handle` 传入的大小是 0。
- `tools/mesa/fd-import-size.patch` 改为传 `winsys_handle.size`，AIR 导入时填上 buffer 的大小。导入的 buffer 预取页面时只读不写，调用方只读的内存映射过来也是只读。
- `bo12`（`12377-cmd37`）三个进程打印出的 48 次导入全部成功，纹理直接读调用方的内存，不再拷贝与哈希。快档 54.3、慢档 38.8 帧／秒。

## 8. freedreno 的 madvise

- freedreno 的 buffer 缓存每次放入、取出 buffer 都调用一次 `madvise`，经 IOKit 进内核。RedwoodGPU 保留所有 buffer，对 `kMsmGemMadvise` 总是回答「保留」。`bo12` 的线程回溯里，backboardd 渲染线程最常停在这两次往返上。
- `tools/mesa/fd-madvise-skip.patch` 在 Darwin 上直接返回「保留」，不进内核。
- 同一轮（`bo13`）开始用 `redwood_drm.c` 的调用计数：每 4 秒按 ioctl 编号打印调用次数与耗时（`redwooddrm[PID]: calls in N ms, selector:calls/us ...`）。`bo13` 快档 54.3、慢档 36.9 帧／秒，与 `bo12` 相比没有可分辨的变化。

## 9. 面板按行更新

- 面板驱动 `MiniIOMobileFramebuffer` 每帧把 1125x2436 的源图像缩放拷进 1156x2510 的面板内存。`bo13` 里屏幕静止（每秒 5～12 帧）时每帧拷贝中位数 8.2 毫秒，翻页时 8.6 毫秒，两个线程分担。
- `12377-cmd38` 对源图像每行算一个哈希（四路 FNV），没有行变化的帧直接跳过，有变化时只画变化行覆盖的面板行段（`MiniFramebufferRows.inc`）。只在第 0 层单独一个 surface 时启用，boot-arg `fb_rows=0` 关闭。5 秒统计行加上「N 帧没有行变化；每帧画 N 行面板；源图像第 A～B 行有变化」。
- `bo14`：屏幕静止时每帧拷贝中位数 1.6 毫秒，翻页时 5.4 毫秒。`bo16` 里只有时钟图标秒针走动时，每帧画约 112 行面板。

## 10. GPU 频率

- 设备树（`docs/analysis/data/annibale.dts.gz` 的 `qcom,gpu-pwrlevel-bins`）给出六张档位表。160～832 MHz 各档的 level、总线投票与 ACD 值在六张表里相同，900 MHz 一档的总线投票不同。本机 speed bin 为 232（0xe8），对应第 2 张表。
- `12377-cmd39` 在 `adreno8_cx.c` 增加 389、443、525、607 MHz 四档（`adreno8_speed=4`～`7`），level 与总线投票取自设备树，不发 ACD。607 MHz 以上暂不开放，等这四档跑过再定。
- 调速规则不变：负载（折算到最低档）超过 20%，或最近 300 毫秒内有触摸，升到最高档；低于 10% 持续 500 毫秒回到最低档；GPU 温度传感器不低于 70 °C 时降到最低档，低于 60 °C 再放开。
- `bo15`（`GPU_SPEED=7`）：今天视图翻页时 GPU 忙碌比例从 `bo13` 的 94%（342 MHz）降到 56%，GPU 最高 49.8 °C，没有 GPU 故障。快档 56.1、慢档 38.2 帧／秒。慢档帧率没有随 GPU 变快而提高，瓶颈在 backboardd 的处理器时间。

## 11. GPU 完成中断

- 原来等 GPU 的线程每 200 微秒醒一次查完成的时间戳。设备树的 GMU 节点给出两个中断，其中「hfi」是 SPI 0x130（INTID 336），电平触发，GMU 往消息队列写消息（包括提交完成的 `TS_RETIRE`）时触发。
- `12377-cmd40` 在 RedwoodGPU 启动时挂上这个中断（`adreno8_hfi.c`，boot-arg `gpu_irq=0` 关闭），打开 `GMU_GMU2HOST_MASK` 的第 0 位。中断处理清掉状态、计数并唤醒等待者；等待者睡到下一次中断，最长 2 毫秒。100 毫秒内超过 20000 次时关掉中断，退回轮询。
- `bo16`：每 5 秒的 GPU 统计行加上中断次数，静止时约 50 次（每秒约 10 帧）。快档 60 个窗口，中位数 56.2 帧／秒，其中 0.57 秒窗口出 36 帧（63 帧／秒）的比 `bo15` 多；慢档 10 个窗口，中位数 36.9 帧／秒。
- `bo16` 里 backboardd 的处理器时间全轮 124.7 秒，`bo15` 为 110.1 秒，两轮出帧数相近（约 13400 帧）。两轮的巡检落在今天视图的次数不同，这个差别不能归到中断上。

## 12. 没有反应的手势

- 巡检的滑动由 `rwtouch` 写进 `/dev/redwood-touch`，内核为每个采样打一行 `tl: p`，`input26-service` 读出后交给 backboardd 的 HID 事件系统。
- `bo16` 的 84 步里，r13、r26、l27、r30、tr3、tr4、tl6 这 7 次滑动没有出帧。每次滑动内核都记了 40 个触摸采样，之后到下一个手势之前（约 4 秒）没有 `tl: Q`、`tl: s`、`tl: v`，backboardd 与 SpringBoard 都没有提交。失败的滑动前屏幕都静止了 1.9 秒以上，同样静止约 2 秒后起手的滑动多数正常。
- r30 之后屏幕约 60 秒没有新帧，其间的两次主屏键也没有出帧。
- `12377-cmd40`、`12377-cmd41` 的看门狗在屏幕静止后的第一次触摸时就转储，转储时 SpringBoard 主线程都在 run loop 里等待。那一刻事件还没送到，这些转储不能说明手势停在哪一步。`12377-cmd42` 改为：一个手势开始（距上一次触摸超过 300 毫秒）400 毫秒后面板仍没有新帧，就转储 backboardd、SpringBoard 与 `input26-service` 的线程，并打印 `/dev/redwood-touch` 里没读走的采样数。
- 每轮巡检落在哪一屏，取决于前面有没有滑动失败，所以各轮的快档、慢档窗口数不同。`bo18` 起巡检改为每组先按主屏键回到第 1 页再左右各滑一次，今天视图里改为上下滚动。
- `bo18`（`12377-cmd42`）的 3 次转储：手势开始 400 毫秒后 `/dev/redwood-touch` 里没有未读采样，`input26-service` 停在 `read` 等下一个采样；SpringBoard 主线程停在 `GSEventRunModal` 的 run loop 里等待，backboardd 各线程也在等待。
- backboardd 自己的 `TouchEvents` 日志给出了差别。有反应的滑动在按下时记「contact 1 presence: touching」与「Touch entered (insideExclusive)」，抬起时记「contact 1 presence: none」，向右滑还有 SpringBoard 发来的触摸投递策略（「TDPS server got new policy <share ...>」）。没有反应的滑动只有按下的两行，没有抬起，也没有策略。其中几次在按下时记「range-in for pathIndex with existing contact -- using existing」，即 backboardd 仍把上一次的 1 号触点记为按下状态。
- 打印这几行的是 backboardd 里处理数字化仪事件的函数（`/usr/libexec/backboardd` 的 `sub_100011630`）。它处理的每个抬起事件都会把触点改为 none 并打印「presence: none」，没有这一行说明抬起事件没有到这个函数。事件在 `input26-service` 与这个函数之间的哪一步停下，还没有读数。
- 巡检的滑动都从屏幕边缘起手（x 为 0.97 或 0.03），`input26-service` 给这类触点加 `DIGITIZER_FROM_EDGE_TIP`。`bo20` 只改起手位置（x 为 0.85 或 0.15），用来区分边缘起手是否相关。

## 13. 探针的开销（二）

- `bo16` 的处理器采样里，`mach_absolute_time` 占 backboardd 用户态样本的 18%。这个函数在用户态是 `isb` 加读计时器，样本落在 `isb` 之后。来源是 freedreno 与 AIR 里仍在每次绘制读时钟的计时点。
- `tools/mesa/fd-perf-off.patch` 让这些计时点只在环境变量 `FD_PERF_DRAW=1` 时读时钟，`fd_bo_cpu_prep` 同样处理；AIR 的 `draw_mark()` 同理。
- `bo17`：`mach_absolute_time` 降到 backboardd 用户态样本的 1%。backboardd 全轮处理器时间 54.7 秒（`bo16` 124.7 秒），全部进程 195.7 秒（`bo16` 259.9 秒）。按出帧数折算，backboardd 每帧约 5.8 毫秒（`bo16` 约 9.3 毫秒）；`bo17` 巡检进今天视图的一步失败，今天视图的帧比 `bo16` 少，这个比值偏低多少没有读数。
- 快档 66 个窗口，中位数 52.8 帧／秒；慢档 6 个窗口，39.5 帧／秒。

## 14. 今天视图里 backboardd 退出

- `bo18` 在今天视图上下滚动时，backboardd 退出 4 次（SIGABRT，退出原因的命名空间是 CoreAnimation）。每次退出前 AIR 拒绝了片段着色器 `TimgBadcA2S1Xhfu_Ialp` 的管线：「intrinsic: air.fmax3.f16」，CoreAnimation 建不出这条管线就终止进程。
- `tools/mesa/air/air_intrinsics.c` 增加 `min3`、`max3`、`median3`（浮点、有符号与无符号整数），`median3` 按 `max(min(x, y), min(max(x, y), z))` 展开。
- `bo19` 同一段巡检 backboardd 没有退出，今天视图可以上下滚动，滚动时 0.57 秒窗口多在 12～15 帧。
- 各轮里仍被拒绝的管线只剩 SpringBoard 的一条：「a store of a pointer into memory, which this frontend has no address to write」，`bo10`～`bo19` 每轮都有。

## 15. 未解决

- 今天视图的帧率：GPU 在 607 MHz 时约一半时间空闲，左右翻进今天视图的慢档仍在 37～40 帧／秒，`bo19` 在今天视图上下滚动时多在 21～26 帧／秒。每帧约 410 次绘制的处理器时间在 CoreAnimation 自身、驱动与内核之间如何分配，还没有按帧的读数。
- backboardd 的内核态时间：`bo17` 的采样里 backboardd 内核态 1522 个、用户态 904 个。内核态前几项是开中断处（`ml_set_interrupts_enabled_with_debug`，调用方是线程切换后的 `Call_continuation`）与 workqueue 锁的自旋（`hw_lck_ticket_contended`，调用方是 `workq_thread_set_max_qos`、`workq_unpark_continue`、`workq_park_and_unlock`、`workq_kern_threadreq_initiate`）。这些调用来自 libdispatch 的 workloop 线程的唤醒与停放，哪些队列在频繁唤醒还没有读数。
- 采样器在每次中断时记录被打断的位置（`tools/k90auto/prof.py`）。关中断期间到达的中断要等开中断才处理，样本记在开中断的位置，关中断期间实际执行的函数记不到。按进程的处理器时间以 `ps` 为准。
- 没有反应的手势：抬起事件没有到 backboardd 处理触点的函数，读数见 §12。
