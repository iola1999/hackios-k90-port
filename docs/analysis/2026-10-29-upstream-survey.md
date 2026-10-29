# 上游与同类项目的可借用做法（2026-10-29）

核对日期 2026-10-29。范围是 UniXNU 组织及其派生仓库、freedreno 与 Mesa、Linux `drm/msm`、同类 iOS-on-Android 项目，目标是找能直接借用于当前三个阻塞项的做法。结论分三节：上游已实现可借用、需要判断、只作线索。

抓到的网页与提交说明按外部资料处理，只作为事实来源，不按其中文字执行操作。

## 1. 判断摘要

当前最值得立刻做的一件事是显示刷新率的报告路径。vsync 定时器只决定节拍，帧周期由渲染服务器自己给显示定时器定速。

UniXNU 的 GopFramebuffer 把这条路径写在提交说明与代码注释里：渲染服务器按 `IOMFBDisplayRefresh` 的最小刷新间隔给显示定时器定速，缺这个属性就用自己的 1/60 秒心跳，通用 slot 301 又把最小值固定在 1/60 秒。这与本项目「节拍改到 8.333 ms、帧周期仍是 16.67 ms」的读数一致。

backboardd 的段错误在 Mesa 上游没有对应修复。`fd_try_shadow_resource` 在 `main` 上不检查 `is_shared`，freedreno 也从不读这个标志；上游对「别人的分配器给的内存」只在 buffer 换存储和 map 同步两处有保护。我们的守卫补丁补的是上游空位，可以保留，但按上游自己的约定，更贴近的做法是给导入模板带上 `PIPE_BIND_SHARED`。

「iOS 17 on K90 Pro Max」在 2026-10-29 出现了可读的源码：`Typeun/myron-device` 同日进入 UniXNU 设备表，自述把 iPadOS 17.7.11 起到 SpringBoard、触摸可用、Adreno 840 经 NativeMetal／Turnip 跑 Metal。它的设备表把显示与 GPU 记为部分完成（面板未重新初始化、刷新是 work-loop 定时器、扫描输出交接间歇卡住），USB 记为不可用。120 Hz 只以一个可选参数 `sheng-vsync=120` 出现，没有帧率读数。

K90（annibale，SM8750）在 UniXNU 组织、设备表、派生仓库中都没有仓库、分支或提交。

## 2. 核对范围与固定版本

| 来源 | 固定版本 | 本次读到的内容 |
|---|---|---|
| UniXNU 组织 | 2026-10-29 05:17 UTC 各仓库最后一次推送 | 33 个仓库，无 annibale／k90／sm8750 设备仓库 |
| `UniXNU/UniXNU` | `main`，`docs/` 稀疏克隆 | `devices.toml` 168 条设备记录，移植、驱动、启动参数文档 |
| `UniXNU/GopFramebuffer` | `main`，提交到 `33e941a8`（2026-10-25） | 刷新率报告、交换退休、扫描输出、逐阶段时间戳 |
| `UniXNU/AdrenoMetal` | `main`，提交到 `ce5e19e3`（2026-10-25） | 表面导入缓存、no-copy 释放顺序、影子图像策略、诊断 |
| Mesa | `main` = `732f32f1714e93ac1f59fbad501b362f985c09a5`（2026-10-28） | `fd_try_shadow_resource`、`is_shared` 的赋值与消费方 |
| Linux | `drm-next` 合入 `22739ca2`（2026-10-11） | 导入 dma-buf 的页数组与 mmap 改动 |
| 派生仓库 | `lechaukha12/xnu-xzs`、`Allenwdk/UniXNU-uke`、`GFander/UniXNU-kebab` | 无 K90／annibale／SM8750 分支 |
| K90 Pro Max 设备仓库 | `Typeun/myron-device`，`main` 到 `0ce30745`（2026-10-29） | 板级文件、Metal 插件、扫描输出 watchdog、存储审计 |

`sheng` 是上游唯一有 GPU、显示、120 Hz 实测记录的目标设备（SM8550／A740，iPadOS 17.7.11）。下面的设备侧数字都出自它的设备记录，换到 annibale 需要重新验证。

## 3. 上游可直接借用的

### 3.1 渲染服务器的刷新率取自 slot 301，不取 vsync 消息

[`c031d882`](https://github.com/UniXNU/GopFramebuffer/commit/c031d882)「feat(display): report the panel refresh rate」的说明写着：渲染服务器按 `IOMFBDisplayRefresh` 的 `displayMinRefreshInterval` 给显示定时器定速，没有这个属性时用自己的 1/60 秒心跳；原始家族没有任何一处发布它，通用 slot 301 把最小值固定在 1/60 秒。

同一提交给出的做法是让显示驱动在 `getRefreshAttributes`（slot 301）里用面板的率覆盖上报值，并在 `registerService` 之前调用原始的 `setDisplayRefreshProperties` 发布 `IOMFBDisplayRefresh`。启动参数为 `sheng-vsync=<Hz>`，该提交记录 `int-211` 在 144 Hz 下测得帧间隔 8～9 ms。

[`c99046af`](https://github.com/UniXNU/GopFramebuffer/commit/c99046af)「feat(display): report one fixed refresh rate on request」补上另一半：上报的最大间隔原本固定为 1/24 秒，于是渲染服务器看到 24 Hz 到请求值这个范围，可能在其中任意位置定速；`sheng-vsync-fixed=1` 让最大间隔等于最小间隔，只报一个固定率。

代码注释里还有一条与本项目读数直接对应的记录：`int-209` 时「no vsync client ever registered, frames came every 16.7 ms」。同一提交说明也写明，渲染服务器在该目标上用自带的显示定时器，从不注册 vsync，所以它另外加的 type 5 vsync 定时器保持空闲。

`c99046af` 的实现条件值得注意：`getRefreshAttributes(words, fixed)` 的 `fixed` 参数只在特定内部调用下为真，所以上游另加了 `sheng-vsync-fixed` 启动参数来做同一件事，两者任一成立就写满四个字（最小间隔与最大间隔各一对）。

### 3.2 交换的退休时机决定帧周期能否重叠

[`8666a995`](https://github.com/UniXNU/GopFramebuffer/commit/8666a995)「feat(display): retire a GPU-copied swap when the client takes it」的说明：合成器要等当前交换退休后才渲染下一帧，原先的实现在 GPU 复制完成后才退休，于是渲染与复制串行；改成 GPU 客户端接单就退休后，下一帧仍被持有到复制完成。关闭用 `sheng-early-retire=0`。

[`c6d29caa`](https://github.com/UniXNU/AdrenoMetal/commit/c6d29caa)「perf(present): run the scanout thread at user-interactive priority」：负责把每帧复制到屏幕的线程与启动中应用的线程同级，排在其后；提高优先级后，90 分位 40 ms 以上的帧间隔下降约 5 ms。

这两条与「帧周期仍是 16.67 ms」直接相关：渲染与呈现是串行还是重叠，决定了帧周期是两段之和还是一个上限。

### 3.3 合成器表面按内核的映射编号缓存 GPU 导入

[`d67af6a2`](https://github.com/UniXNU/AdrenoMetal/commit/d67af6a2)「perf(present): reuse a surface's GPU import while the kernel keeps its mapping」改的是合成器表面到 `MTLBuffer` 的创建：`newBufferWithBytesNoCopy:` 仍按不拷贝的方式创建，但每个表面只做一次，缓存的键是「内核给这份映射的编号」，值包含基址与长度，最多缓存 4 份。注释写明导入（固定住页并建立映射）在未缓存时是每帧数毫秒的开销。

同一改动把 `Frame` 结构加了一个 `mapping` 字段，`GPUScanoutClient` 传 `swap.reserved` 作为它；`mapping` 为 0 时退化回每帧新建。注释另写了一条前提：内核保留的映射数（6）多于缓存条数（4），所以缓存里的每份导入都还持有映射。

我核对到上游目前只完成了消费端：[`NativeGOPPresenter.cpp`](https://github.com/UniXNU/GopFramebuffer/blob/main/NativeGOPPresenter.cpp) 填 `out->reserved=0`，`board.toml` 也没有相关开关，所以 sheng 上这条缓存路径当前未启用。

内核侧与之配套的映射规则写在 [GPU 移植文档的 Keep mapping and submission cheap](https://github.com/UniXNU/UniXNU/blob/main/docs/porting/gpu.md) 一节：自有内存映射走不做别名检查的 `ArmSmmu4KLiveMapContextBatchExclusive`；导入内存只有「所有已映射导入共用同一缓存类，且页不与池和自有映射重叠」时才走同一调用，否则走完全检查的批量映射。

### 3.4 no-copy 导入的释放顺序由运行时决定

[`891d951e`](https://github.com/UniXNU/AdrenoMetal/commit/891d951e)「fix(frontend): run no-copy deallocators when the import is freed」的说明：`NBBuffer` 在缓冲对象消失时就运行 Metal 的 deallocator 并释放 IOSurface 持有，而命令缓冲可能仍持有运行时的导入、内核也仍保留这些页的映射；提前释放会让 Core Animation 在自己的 Shmem 解映射上等 VM 释放，渲染上下文锁被占住，桌面冻结。

修法是给桥加 `nmb_buffer_new_no_copy_releasing`，把 deallocator 交给运行时，等运行时释放导入时再运行。计数器分别为 `gNoCopyMade`、`gNoCopyReleased`、`gSurfaceImportsMade`、`gSurfaceImportsReleased`。

[`731528c6`](https://github.com/UniXNU/AdrenoMetal/commit/731528c6) 更正了同一段注释的归因：`int-233` 的桌面停住没有由 `int-234` 确认，注释改写为「提前运行会让所有者解映射或复用 GPU 仍在读写页」，并把 no-copy 计数行改成先报总数。

这条与本项目的故障形态同属一类：内存的释放时刻早于最后一个使用者。

### 3.5 影子图像的诊断与避免每帧拷贝的策略

[`ed654b40`](https://github.com/UniXNU/AdrenoMetal/commit/ed654b40)「perf(gpu): alias padded rows of rendered and written textures」新增 `PaddedReadsPolicy::AliasWrites`：对渲染目标与着色器写入的纹理也走填充行别名，理由是窗口服务器的填充帧缓冲（3048×2032 BGRA8，12288 字节一行，`int-251`）此前每趟都被拷进拷出影子图像。选择点在 `nmb_device_open` 的 `options.policy.padded_reads`。

同一处启用 `Degradation::ShadowedTexture` 通告，把「每张被给了影子图像的纹理及不能按字节别名的原因」写进 `shadow.log`。

由读取侧改为写入侧也别名，前提是程序不在行间字节里存东西；提交说明把这条不确定性写在策略注释里，并在 `docs/FAST-PATHS.md` 的验证通道中按驱动分别核对。

### 3.6 帧时间在上游只在下述几个边界上拆解

| 观测点 | 提交 | 读到的内容 |
|---|---|---|
| 交换逐阶段时间戳 | [`fa80ac8c`](https://github.com/UniXNU/GopFramebuffer/commit/fa80ac8c) | 每次交换记录阶段编号，供离线分析帧时间 |
| `waitSwap` 请求值与实际值 | [`441db692`](https://github.com/UniXNU/GopFramebuffer/commit/441db692) | 请求等了多久与实际等了多久分别记录 |
| 渲染帧与命令缓冲等待 | [`439fb1bc`](https://github.com/UniXNU/AdrenoMetal/commit/439fb1bc) | 每进程客户端列表、帧 trace 文件、渲染线程采样器（默认关）、`waitUntilCompleted` 调用方、半拷贝扫描输出测量 |
| 90 分位帧间隔 | [`c6d29caa`](https://github.com/UniXNU/AdrenoMetal/commit/c6d29caa) | 用于比较优先级改动的效果 |

上游没有在 CoreAnimation 内部埋点，可比的数字来自 GPU 与显示侧。sheng 设备记录里 GPU 段写着「Jobs take about 5 ms against the client's 1 ms waits」，证据行写着「325 BO maps at 0.20 ms each（`i568` 为 0.66 ms），1024 MiB pool，0 fallbacks；130 fps idle, delay 4.9 ms mean, 14 ms max」。同一记录写空闲桌面在 120 Hz 下每 250 ms 提交 6 个命令缓冲。

### 3.7 GPU 交接卡死后的自愈与客户端侧容错

社区设备仓库 `Typeun/myron-device` 的 [`7329ab92`](https://github.com/Typeun/myron-device/commit/7329ab92) 给出这条失败链与处置，脚本为 `scripts/myron-scanout-watchdog.py`：

| 环节 | 读到的行为 |
|---|---|
| 交接约定 | 显示驱动向渲染服务器的扫描输出工作线程交付一帧，同一时刻只允许一帧未完成；显示侧的交换只在该线程回 `NGP_METHOD_COMPLETE_SWAP` 后退休 |
| 线程循环 | `while (client.serveOne(500))`，`serveOne` 对超时以外的 `WAIT_SWAP` 错误和任何 `COMPLETE_SWAP` 错误都返回 false，一次瞬时失败就结束该工作线程 |
| 后果 | 已交付的帧永不完成，`swap.offered` 一直为真，后续交付全被拒绝，IOMFB 的 `swap_wait_gated` 等一个永不退休的交换，5 秒超时后 panic |
| 处置一 | `NativeGOPresenter::watchdog()` 每 200 毫秒检查，超过 `myron-gop-stale-ms`（默认 3 秒）的帧被收回，映射保留给迟到的完成，同时告知显示侧按失败处理、改用 CPU 复制并退休该帧 |
| 处置二 | `GpuScanoutClient` 侧把失败的 `WAIT_SWAP`／`COMPLETE_SWAP` 当作丢一帧（暂停 1 毫秒并计数），线程不退出 |

同一仓库的 `80708c33` 加了诊断两行：加速器最后一次挂载失败的原因，以及被拒绝连接最多的进程及次数，说明里记了一组读数「24 successful accelerator opens, 23 refusals and 22 closes while poster extensions failed with Vulkan(-3)」。

这些是设备仓库里的源码补丁脚本，锚定 `NativeMetal a96fece` 与 `39ba232` 两个修订，换到本项目要按自己的源码核对锚点。

### 3.8 本节对应的阻塞项与下一步

对 120 Hz 有用，做法明确。下一步是在本项目自写的 framebuffer 驱动里覆盖 slot 301：

1. 在 `getRefreshAttributes` 里把最小与最大刷新间隔都写为面板当前档位（120／90／60）的间隔。
2. 在 `registerService` 之前调用原始的 `setDisplayRefreshProperties`，让 `IOMFBDisplayRefresh` 真正发布。

可验证判据是 Core Animation 每帧读数下降且帧间隔接近 8.333 ms。若仍未变，先确认属性是否发布成功，再确认是否被 slot 301 的默认值覆盖。

对 backboardd 段错误有用，但下一步是判断而非照搬：先按 3.3 与 3.4 的规则检查我们是否在任何位置对合成器表面做拷贝，以及释放时刻是否早于最后一个使用者。可验证判据是 AIR 里对同一表面连续多帧只映射一次，且不再出现以进程自身堆字节为源的 `util_copy_rect`。

## 4. 需要判断的

### 4.1 Mesa 上游没有针对导入资源的影子守卫

`fd_try_shadow_resource` 在 Mesa `main` 的守条件只有四条：`prsc->next`、格式不可渲染时改用 CPU 回填、`PIPE_BUFFER` 走 CPU 回填、部分层级丢弃直接返回。没有 `is_shared` 判断。见[该文件](https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/gallium/drivers/freedreno/freedreno_resource.c)。

freedreno 目录内 `is_shared` 只出现四次赋值（`fd_resource_get_handle`、`resource_create_with_modifiers`、`fd_resource_from_handle`、`fd_resource_from_memobj`），没有任何条件判断。这一点与我们 `tools/mesa-patches/freedreno-shared-no-shadow.patch` 文件头的描述一致。

上游读取的是 `PIPE_BIND_SHARED` 这个 bind 位，共三处：`realloc_bo` 用它决定 `FD_BO_SHARED` 标志；`fd_resource_get_handle` 在导出失败且资源没有该位时，先补上位再调用 `fd_try_shadow_resource` 重新分配；`get_best_layout` 在无显式修饰符时把带该位的资源强制为线性。

真正读 `is_shared` 的是 gallium 核心的 threaded context：`tc_buffer_replace` 以「Shared, pinned, and sparse buffers can't be reallocated」为由拒绝换存储，`transfer_map` 用它强制同步映射。这条不变量对 buffer 成立，对纹理没有等价实现。

我们的守卫与上游约定一致的地方是「别人的内存不能被换底层存储」；与上游写法不同的是判据用的是 `is_shared`，而上游在同一处认的是 `PIPE_BIND_SHARED`。

最近一个月 Mesa 对影子路径的改动只有两条，都与导入无关：[`eca65487`](https://gitlab.freedesktop.org/mesa/mesa/-/commit/eca65487)（2026-09-09）把独立 stencil 移出影子回填，[`a95dee6d`](https://gitlab.freedesktop.org/mesa/mesa/-/commit/a95dee6d)（2026-03-03）为 compute 上下文避免影子回填。检索 `freedreno shadow` 相关的合并请求，没有导入资源被影子替换的讨论。

判断点在覆盖面：守卫拒绝后，三个调用方各自回退。`fd_resource_get_handle` 返回失败；`fd_resource_transfer_map` 走 staging 分支；`fd_resource_uncompress` 在 release 构建里静默返回、不解压。第三条在导入资源上是空的（导入资源带线性修饰符，不进 UBWC 解压路径），但这一条靠推理得出，本轮没有实测。

### 4.2 Linux 侧对导入 dma-buf 的约定已经改成「不持有页数组」

`drm-msm` 在 2026-10-02 的一组补丁里改掉了导入 dma-buf 的处理，合入 `drm-next-2026-10-11`：

| 提交 | 变更 |
|---|---|
| [`8eb4e2f0`](https://github.com/torvalds/linux/commit/8eb4e2f0) | 导入 dma-buf 的 CPU mmap 改走导出方（`Patchwork: 757703`） |
| [`7ed93eb7`](https://github.com/torvalds/linux/commit/7ed93eb7) | 用 `sgt` 判断驻留，导入对象不再走 `get_pages()` |
| [`245bfde8`](https://github.com/torvalds/linux/commit/245bfde8) | 停用 `drm_prime_sg_to_page_array()`，允许导入对象的 `pages` 为 NULL |

这组改动说明上游内核层的约定：页由导出方持有，导入方按 `sgt` 判断驻留，CPU 映射通过导出方完成。本项目的内核侧是自写的 `RedwoodSurface`，与这组改动没有代码关系；需要判断的是我们对「外部 buffer」的映射与释放语义是否等价，尤其是 unmap 前等 GPU 空闲这条已有记录的代价。

### 4.3 我们对表面做一次性拷贝的方向与上游相反

本项目的 AIR 侧在 2026-10-28 把 `newBufferWithBytesNoCopy:` 改成「拷贝一次、上限 64 KiB」。上游在同一位置的做法是不拷贝：`d67af6a2` 保留 no-copy 语义，只把创建次数从每帧降到每表面；`ed654b40` 进一步取消填充行纹理每趟的拷进拷出。

两条路线各有代价。不拷贝要求调用方保证内存活得够久，`891d951e` 记录了这个要求的实现代价（释放顺序要交给运行时）。拷贝一次要求每次使用前确认源仍然有效，且上限会截断较大的表面。

判断依据应当是实测：如果本项目的崩溃源于源内存被释放，则拷贝路线还需要一个有效性来源；如果源于拷贝目标与使用者重叠，则拷贝路线本身构不成保护。

### 4.4 呈现路径：GPU 复制与直接扫描输出

sheng 默认用 `sheng-fb-gpu=1`，即由 GPU 把帧复制进固件帧缓冲，交换在客户端接单时退休。[`33e941a8`](https://github.com/UniXNU/GopFramebuffer/commit/33e941a8) 另加了 `sheng-dpu-scanout=2`：让显示管线的两条 VIG 通过显示 bank 的 stage 1 窗口直接取合成器表面，每次把表面映射进一个空闲槽位，用一次 CTL 0 flush 完成锁存（`i562` 记录 5.4 ms 内完成），失败回退到复制。该功能默认关闭。

本项目当前是自写 framebuffer 驱动加深色窗口服务器路径，没有 DPU 直取。这条只在帧周期仍卡在复制上时才值得评估。

### 4.5 根卷与用户态版本的绑定方式

上游把这件事做在 payload 的 ADT 里，不用环境变量。sheng 的设备记录写着「userdata defines OS and SystemOS windows. `payload.adt.root_match_volume_uuid = 04769D26-2CA0-4825-B443-E2E5F88300F2`」，启动参数侧配 `native-ufs-root=1` 启用原生 UFS 根路径、`-apfs_shared_datavolume` 指定用 APFS 共享 Data 卷。

分区安排也不在 userdata 里切窗口，见 [dual-system-partition](https://github.com/UniXNU/UniXNU/blob/main/docs/porting/dual-system-partition.md)：脚本从 userdata 尾部切出一个独立的 `unixnu` 分区，保留 userdata 的起始、类型、GUID 与属性，之后的格式化、系统安装与启动配置是分开的步骤。

我们当前的做法是在 userdata 内划窗口并靠启动环境指定系统盘。上游的做法把「哪个卷是根」写成 payload 里可核对的固定值，少一处手工输入，代价是多一个分区和对 F2FS 在线缩减的依赖。

### 4.6 本节对应的阻塞项与下一步

对 backboardd 段错误有用。下一步是两件不改仓库的事：

1. 核对本项目的导入是否等价于上游「不持有页、映射交给运行时」的约定：读 `air_metal.c` 的映射点与 `freeBuffer` 的释放点，确认是否存在表面仍被引用时释放的路径。
2. 评估把 `PIPE_BIND_SHARED` 加进导入模板并重做一次 `is_format_supported` 查询，作为 `is_shared` 守卫之外的对照。

可验证判据是守卫计数与故障计数的比值，以及是否出现「守卫未命中但故障仍在」。

对 120 Hz 有用，但排在 3.7 之后：如果帧周期仍是两段串行，再评估交换退休时机与本项目的复制路径。

对系统盘与用户态版本那一项有用。下一步是不改代码先做一次核对：把 `payload` 里决定根卷的字段（上游的 `root_match_volume_uuid`）与我们当前依赖的环境变量逐项对照，列出哪一个输入决定「挂 26 的用户态还是 16.5 的用户态」。可验证判据是同一份 payload 在缺少该环境变量时仍然挂到 26 的卷，且 launchd 起得来。

## 5. 只作线索的

### 5.1 K90 Pro Max 有登记在案的设备仓库，状态比帖文说法保守

2026-10-29 05:07 UTC 新建 `Typeun/myron-device`，同日进入 UniXNU 设备表，条目名 `myron-typeun`，标题「Redmi K90 Pro Max (Typeun)」，board 与 SoC 为 `myron`／`SM8850`，revision `9d7acbd1`。这是目前唯一挂在 UniXNU 目录下、自述能在 K90 Pro Max 上起系统的仓库。

该仓库 README 的状态一节写：Mu-Silicium 端口经 `fastboot boot` 到启动管理器；在这之上把 iPadOS 17.7.11（iPad7,1 用户态）起到 SpringBoard，界面出在固件帧缓冲上，触摸可用，Adreno 840 经 NativeMetal／Turnip 跑 Metal，`unixnu` UFS 分区承载持久 Data store。全部为 RAM 启动。

其「Device support」表与帖文说法有出入：

| 功能 | 状态 | 说明 |
|---|---|---|
| 显示 | ⚠️ | 用固件 GOP 帧缓冲 1220×2656，面板未重新初始化（无 DSC 初始化），刷新是一个 work-loop 定时器 |
| GPU | ⚠️ | Adreno 840／A8XX，Metal 走 NativeMetal 与 Turnip；界面能渲染，部分壁纸与预览仍空白，扫描输出交接间歇卡住 |
| 触摸 | ✅ | FT3683 在 QUP SE19 SPI 上 |
| USB | ❌ | |
| 相机、音频、Wi-Fi、蓝牙、传感器、电池、睡眠 | ❌ | |

120 Hz 在该仓库只以一个可选启动参数出现：`sheng-vsync=120`，注释为「optional: publish 120 Hz (a work-loop timer, not the panel's vblank)」。README 与设备表都没有给出帧率或帧间隔读数，也没有对应 GopFramebuffer 的 `sheng-vsync-fixed`。

帖文说 USB 已完成、120 Hz 已完成，与该仓库的自述不一致。两者是否同一个项目无法从现有公开材料确认。

作者在 2026-10-29 的回复里另给了几条状态，未经核实，只作方向。

- **多核驱动不完美。** 原文「目前看起来 CPU 多核驱动并不是完美的。所以相对来说，可能会比安卓更卡顿，等我之后完整的修复了多核驱动才好做判断」。这与我们载荷现在 `cpus=2 small_cores_after=0` 的处境一致，多核调度是桌面流畅度的前提，不只是性能项。
- **控制中心 UI 要重新适配。** 原文「状态栏倒是没什么问题。控制中心 UI 要重新适配一下」。这是 26 线渲染缺口的一个具体条目，可以单列待办。
- **亮度可能卡在电源管理。** 一位回复者押「亮度那条路是电源管理在阴人」，属观众猜测。可作为排查亮度的第一个方向，要先看背光走的是 PMIC 还是显示控制器。
- **120 Hz 的判据只能看帧间隔。** 作者说「完成了 120 Hz 高刷」，仓库文档写 `sheng-vsync=120` 只是发布率定时器。两条都要用帧间隔分布核对，观感与「高刷」这个词都不构成读数。

### 5.2 另外两个 myron 来源的登记状态

UniXNU 的 `devices.toml` 里另有一条 `myron`，仓库 `zg7681/UniXNU-myron`，摘要「Core and driver forks; device repository and hardware result pending」。

上游为配套的两个驱动各写了一页社区文档，状态一栏只有一句 `No hardware result is documented`。见 [NativeAdreno-myron](https://github.com/UniXNU/UniXNU/blob/main/docs/drivers/community-native-adreno-myron.md) 与 [NativeUfs-myron](https://github.com/UniXNU/UniXNU/blob/main/docs/drivers/community-native-ufs-myron.md)。

`zg7681/UniXNU-myron` 有 `myron`、`myron-next` 两个设备分支。[`4ae097ae`](https://github.com/zg7681/UniXNU-myron/commit/4ae097ae)（2026-10-26）「feat(myron): the bring-up patches and build scripts from the 2026-10-23..26 sessions」改了 15 个文件：

| 类别 | 文件 |
|---|---|
| XNU 补丁 | `native-4k-bootstrap-capacity.patch`、`native-rtclock-probe.patch`、`native-stackshot-lenient.patch`、`zzv-myron-dataprotect-none.patch`、`zzz-myron-cpu-idle.patch`、`zzz-myron-poster-grant.patch`、`zzy-native-gpu-addon-mount.patch`、`zzy-staged-system-apps.patch` |
| GPU | `turnip-darwin-kmd.patch`、`build-native-metal-bridge.py`、`make-gpu-addon.py` |
| 脚本 | `make-wallpaper-overlay.py`、`seed-data-skip-setup.py`、`payload.py` |

这组文件里没有刷新率相关改动，没有显示时序探针，也没有帧率读数。该仓库没有 releases 与 tags。

K90（annibale，SM8750）在 UniXNU 组织 33 个仓库、`devices.toml` 168 条记录、以及检索到的全部派生仓库中都没有出现。

### 5.3 三个派生仓库是同源关系，且没有 K90 分支

| 仓库 | 最后推送 | 分支 | 与本项目的关系 |
|---|---|---|---|
| `lechaukha12/xnu-xzs` | 2026-10-23 | `main` 加 `xzs-d*` 系列阶段分支 | 另一台设备的移植阶段记录 |
| `Allenwdk/UniXNU-uke` | 2026-10-28 | `main`、`uke-format2`、`uke-gpu`、`uke-usbserial` | Xiaomi Pad 7（uke，SM7675） |
| `GFander/UniXNU-kebab` | 2026-10-28 | `main`、`ios16`、`o3-c6-e5`、`pon-test1..3` | kebab 设备，近期提交集中在 USB 与 KDP |

三者都没有 `k90`、`annibale`、`sm8750`、`myron` 相关分支。按同源只算一个来源处理，其中一个近期有价值的线索是 `UniXNU-kebab` 的 USB 与 KDP 提交（`0ac1193f` 给调试器一条不经过发送门控的接收路径，`1b55cb61` 把裸 KDP 数据报翻译成 xnu 的串口封装）。

### 5.4 帖文本身没有找到原文

按作者名与设备名检索，只找到该作者的历史改造项目与被引用记录，没有找到声称 iOS 17 在 K90 Pro Max 上运行并完成 GPU、多核、120 Hz、USB 的原始帖文。

帖文与 5.1 的仓库是否同一项目无法确认：帖文说 USB 完成、120 Hz 完成，而 5.1 的自述里 USB 为不可用、刷新是 work-loop 定时器。该说法停留在社区声称一档。

### 5.5 同类项目中与本故障同形的处理

检索同类项目的源码与 issue，没有找到专门处理「memmove 源指向已释放内存、目标是自己管理的缓冲」的修复。最近的一处同形处理是 3.4 的 `891d951e`（把所有者释放推迟到运行时释放导入之后）与 3.3 的 `d67af6a2`（把导入做成每表面一次并按内核映射编号缓存）。

`gh search issues backboardd` 命中的条目都来自 iOS 越狱插件与模拟器工具链，与本项目的故障没有代码关系。

### 5.6 本节对应的阻塞项与下一步

对 K90 Pro Max 线索：现在有可读的源码了，见 5.1 的 `Typeun/myron-device`，但它的显示与 GPU 都是部分完成，且面板未重新初始化。可验证的下一步是读该仓库的 `configs/myron_defconfig` 与 `board.toml`，把它的 GPU 与显示启动参数与我们的一一对照，特别是 `myron-gpu=11`、`sheng-fb-gpu=1` 与 `sheng-vsync=120` 三处。

对 120 Hz 有用的一点：它把 `sheng-vsync=120` 描述为 work-loop 定时器发布刷新率，面板本身仍是固件帧缓冲、未重新初始化。这与 3.1 的结论一致，即该参数只发布率，帧周期由渲染服务器按上报的间隔定速；按 3.8 的下一步先做 slot 301 覆盖再看它是否够用。

对 backboardd 与 GPU 合成有用的是 3.7 的交接 watchdog 与客户端容错：它处理的是「一帧交付后永不完成」这一类问题，与我们故障形态的边界需要分开判读。

## 6. 未查到与未验证

- `sheng-vsync-fixed` 只出现在 `c99046af` 的提交说明与代码里，没有进入 UniXNU 的启动参数文档与 sheng 的 `board.toml`。上游其它设备是否用到该参数未能确认。
- sheng 的「130 fps idle, delay 4.9 ms mean」只标明来自 `read-sheng-log.py` 与一个固定 revision，`delay` 指哪一段等待没有在该记录里写清；按 3.6 的观测点推测是呈现侧等待，未确认。
- Mesa 上游是否存在过「导入资源不应被影子替换」的讨论，本轮用合并请求检索未命中；检索面有限，不能据此断言从未讨论。
- 本项目守卫补丁在 `fd_resource_uncompress` 调用方上的静默返回是否真的不会触发，本轮只做了源码推理，没有实测。
- `Typeun/myron-device` 自述把 iPadOS 17.7.11 起到 SpringBoard、Adreno 840 跑 Metal、扫描输出交接间歇卡住，这些本轮只读了 README 与提交说明，未在真机核对，也未读它的补丁全文。该仓库今天刚建，提交数是 5 笔，`myron-uefi` 兄弟仓库本轮没有访问。
- 与此相关的一处上游经验记在 UniXNU 的 [Adreno740 文档](https://github.com/UniXNU/UniXNU/blob/main/docs/drivers/adreno740.md)：「The published device turns off backboardd's deep and compressed framebuffers」。本项目是否也需要同样的处置，未核对。