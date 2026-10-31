# 锁屏壁纸：MercuryPosterExtension 的渲染链路（2026-10-31）

用户在 2026-10-31 反馈开机后没有壁纸。本文记录默认壁纸由谁绘制、怎样送到屏幕，以及 `bo24` 起逐轮找到并去掉的缺口。逐轮读数见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §1。

## 1. 结论

- 默认锁屏海报是 `com.apple.MercuryPoster:configuration:space.dynamic`（PosterBoard 日志里的 `PosterActivated`）。它由 ExtensionKit 扩展 MercuryPosterExtension 用自己 bundle 里的 Metal 着色器（`default.metallib`、`Space.metallib`）和 KTX 纹理绘制。SpringBoard 的 `_SBWallpaperSecureWindow` 用 `CALayerHost` 挂载扩展的三个 `PRPosterWindow` context，另有一个 `PBUISnapshotReplicaView` 显示海报快照。
- 壁纸黑屏由一串依次出现的缺口叠成，前一个不去掉就看不到后一个：扩展没有 Metal 设备；扩展的输出全部丢失；AIR 翻译器拒绝 Space 着色器；驱动丢弃顶点阶段的纹理；库拒绝 ASTC 与 BC 压缩格式；绑定检查、整级拷贝和非整除网格的派发；constexpr 的 bicubic 采样器。`bo31` 起扩展的提交不再出错。
- `bo24`～`bo34` 每轮 backboardd 两次拒绝 SpringBoard 壁纸窗口的 commit（「CompressedImage port is MACH_PORT_NULL!」）。被拒的是海报快照：PosterUIFoundation 默认把快照存成 ATX 格式，SpringBoard 为它建的 memory entry 大小为 0，内核返回 `KERN_INVALID_ARGUMENT`。`bo35` 起快照改存 PNG，commit 不再被拒，见 §6。
- 最后一个缺口在驱动的多重采样：扩展用 4 倍多重采样画壁纸，每帧解析出的 drawable 全部为 0（颜色与 alpha 都是 0，`bo36`）；改成单采样直接画进 drawable 后，主屏与锁屏都显示壁纸（`bo37`）。驱动在没有 `REDWOOD_MSAA` 时把多重采样请求一律按单采样处理，见 §7。

## 2. 壁纸的绘制与挂载

- MercuryPosterExtension 没有 launchd 任务，由 PosterBoard 经 ExtensionKit 拉起。它的标准输出与标准错误是 `/dev/null`。`package.py` 默认给它插入 Metal 设备登记库（`POSTER_METAL=0` 不插入），这是它拿到 Metal 设备的唯一途径。
- 扩展进程里有三个 `PRPosterWindow`（`bo29`、`bo31` 的图层转储）。第二个窗口里的 `MercuryPosterExtension.WallpaperMetalView` 是 `CAMetalLayer`，内容为 `CAImageQueue`。渲染通道是 1125x2436、4 倍多重采样（`bo31` 的 `pipeline seen` 行；`bo29` 的通道是 562x1218）。
- SpringBoard 的 `_SBWallpaperSecureWindow`（`bo31`）：三个 `_UISceneLayerHostContainerView` 分别挂载扩展的三个 context（`f320974f`、`7766143a`、`6e40b1bb`），与扩展进程里三个窗口的 context 一一对应。`PBUISnapshotReplicaView` 下的 `UIImageView` 内容是 1125x2436 的 CGImage，按 64x64 网格读出的平均值为白色。
- 绘制前扩展先建「coordinator」：创建计算与渲染管线，加载 KTX 纹理。任何一步失败都会打印「couldn’t set up coordinator」，之后不再绘制，也不再提交。

## 3. 观测

- 扩展的标准输出是 `/dev/null`，驱动和 AIR 库的输出原先全部丢失。驱动在检测到标准输出是 `/dev/null` 时改把每行写进 `kern.redwood.say`（`redwoodmetal_console.inc`），内核日志里是 `say PID MercuryPosterExtension: ...`（`bo25` 起）。
- os_log 要在 libSystem 初始化时读到 `OS_ACTIVITY_DT_MODE`，插入库的构造函数运行时已经晚了。`EXT_ENV="MercuryPosterExtension:OS_ACTIVITY_DT_MODE=YES"` 把变量写进根盘的 `/redwood/etc/env/MercuryPosterExtension`；`inject_posterboard.c` 读到文件后设置变量、重新执行一次进程，并把标准错误转进 `kern.redwood.say`（`bo27` 起）。
- backboardd 的「serialization error from context X」之前还有一行 `进程路径 (pid) : 原因`，原因来自 QuartzCore 解码器的报错函数。用 `sb26 layer window N 类名 context X` 行把 context 对到 SpringBoard 的窗口。
- 宿主机上的 `air2nir --report` 新增 `group_free=1` 字段（§5）。
- 提交末尾的采样（`REDWOOD_THUMBS`）新增 `res`：颜色附件的 resolve 目标。多重采样的附件本身不能采样（`rwa_texture_thumbnail` 拒绝）。
- 内核 `12377-cmd47` 起 `redwood_tl` 一行最长 319 字节，超长时截断并保留换行。此前上限 192 字节，`say` 行超长后丢掉换行，与下一行连在一起，64 像素宽的采样行读不出来（`bo36`）。

## 4. 逐轮的缺口

| 轮次 | 读数 | 改法 |
|---|---|---|
| `bo24` | `POSTER_METAL=1` 后扩展拿到 Metal 设备，壁纸仍黑；backboardd 开始报 SpringBoard 壁纸窗口的 serialization error（`bo23` 没有） | — |
| `bo25` | 驱动行经 `kern.redwood.say` 进日志，扩展的 os_log 仍不可见 | 驱动的 `/dev/null` 输出改走 `kern.redwood.say` |
| `bo26` | 打开 `REDWOOD_THUMBS`，没有缩略图：扩展没有提交过命令缓冲 | `kern.redwood.say` 每行间隔 5 毫秒 |
| `bo27` | os_log 可见；「couldn’t set up coordinator: Error Domain=RedwoodMetal Code=1」，AIR 拒绝管线 | `EXT_ENV` 与重新执行 |
| `bo28` | 管线全部创建；`albedo-a.ktx` 是 `ASTC_6x6_sRGB`（像素格式 190），库拒绝 | AIR 翻译器与顶点纹理（§5） |
| `bo29` | coordinator 建成，开始提交；`space::rasterizeBackgroundFragment reads texture 3 and 9 textures were bound`；blit 缺 `copyFromTexture:...sliceCount:levelCount:` | ASTC 与 BC 格式、`copyFromBuffer:...toTexture:` |
| `bo30` | 背景绘制通过；「the shader's own sampler at index 0 asks for filter::bicubic」 | 运行时选择的纹理可不绑定、整级拷贝、非整除网格的派发 |
| `bo31` | 扩展不再报错，提交持续；锁屏仍黑；backboardd：「CompressedImage port is MACH_PORT_NULL!」 | bicubic 按 linear 采样 |
| `bo32` | 用 dyld interpose 拦 SpringBoard 的 `mach_make_memory_entry_64`，没有任何输出 | — |
| `bo33` | 内核探针没有输出 | 内核 `12377-cmd45`：`vm_map_copyin_internal` 失败时打印原因 |
| `bo34` | SpringBoard 的 memory entry 大小为 0，返回 4；壁纸窗口里的快照是 ATX 格式的 CGImage，见 §6 | 内核 `12377-cmd46`：拷贝型 memory entry 在任何一步失败都打印 |
| `bo35` | 没有 serialization error；快照是 PNG，内容为不透明黑色 | 海报快照存成 PNG |
| `bo36` | 扩展解析出的 drawable 全部为 0，见 §7 | 驱动在提交末尾采样 resolve 目标（`res`） |
| `bo37` | 主屏与锁屏显示壁纸；逐 draw 采样里 drawable 画出壁纸 | 内核 `12377-cmd47`；扩展用单采样（`REDWOOD_ONE_SAMPLE=1`，之后改为默认） |
| `bo38` | 默认配置下全程有壁纸，滑动帧率与温度和 `bo23` 相当 | 单采样与 `POSTER_METAL` 改为默认 |

`bo32` 没有输出的原因：共享缓存里 QuartzCore 调用 libsystem_kernel 走的是直接跳转的 stub（`adrp`、`add`、`br`），没有可供 dyld 改写的指针，所以插入库的 `__interpose` 拦不到。

## 5. 翻译器与运行时的改动

AIR 翻译器（`tools/mesa/air/`）：

- 写入运行时计算的 mip 级别的图像（`VariableBlurrer::downsample`）：每个级别占一个图像槽（`image_level_slot`，每个纹理最多 15 级，ir3 共 32 个 bindless 图像），运行时按级别建视图。
- 运行时选择的纹理：`select` 与 `phi` 在纹理之间选择时，指针的 `binding` 置 0，槽号放进 `offset`，采样时作为 `nir_tex_src_texture_offset`。被选择的各个纹理标记为可不绑定（`air_texture_may_be_unbound`），因为应用只绑定选中的那一个（`rasterizeBackgroundFragment` 的四个 gobo 纹理）。
- 空纹理：`air.get_null_texture_*` 与 `air.is_null_texture_*`；对空纹理写入不做事，读取与采样得 0，尺寸为 0。
- 函数调用的聚合参数（`CALL_PARAM_AGG`）、`insertvalue` 进嵌套聚合的 undef 常量、`llvm.smax`／`smin`／`umax`／`umin`。
- 计算着色器是否读线程组（`reads_threadgroup`）：不读线程组位置与尺寸、不用 SIMD 组操作、屏障和线程组内存的内核记为 `group_free`。

验证：宿主机上编译 `air2nir`，对 176 个系统 metallib 加 `Space.metallib` 与扩展的 `default.metallib` 共 11398 个模块比较改动前后的 `--report`。翻译成功从 3590 个增加到 3858 个，没有原先成功、现在失败的模块，原先成功的模块 NIR 指令数全部不变。`Space.metallib` 里 `space::*`、`tori::*`、`VariableBlurrer::*` 全部翻译成功。

运行时（`air_metal.c` 与驱动）：

- 顶点阶段的纹理与采样器：驱动原先丢弃 `setVertexTexture:` 与 `setVertexSamplerState:`，`space::rasterizeMeshVertex` 在顶点阶段采样。
- 压缩格式：ASTC 的 LDR 与 sRGB 两组（186～200、204～218）和 BC1～BC7（130～153）按块规格直接对应 Gallium 格式，只能采样；上传按块计算行宽与层跨度。扩展的 KTX 是 `ASTC_6x6`（`albedo-a.ktx`）、`ASTC_4x4`（`normals-*.ktx`、`jurin_0*`）和 BC1（`jurin_innerglow*`、`jurin_unwrap_mask*`）。
- blit：`copyFromBuffer:...toTexture:` 在命令缓冲执行到它时由处理器从 buffer 写入纹理；`copyFromTexture:...sliceCount:levelCount:` 拆成逐级逐层的区域拷贝。
- 网格不能被线程组尺寸整除的 `dispatchThreads:`：freedreno 没有部分线程组。`group_free` 的内核按维把线程组尺寸降到能整除网格的最大值（`space::updateCylinderVertexPositions` 的 3602 个线程按 2 个一组），其余内核仍拒绝。
- constexpr 的 bicubic 采样器按 linear 采样，与 API 采样器的 cubic 一致；放大处比原图软。

## 6. SpringBoard 的 commit 被拒

- 报错位置：QuartzCore 解码 `CA::Render::CompressedImage` 时端口为空，报「CompressedImage port is MACH_PORT_NULL!」，整次 commit 记为 serialization error。`bo24`～`bo34` 每轮各两次，都来自 SpringBoard 的 `_SBWallpaperSecureWindow`。
- CompressedImage 是块压缩格式的图像：构造函数按像素格式 186～218（ASTC）分支。编码时若还没有端口，QuartzCore 调用 `mach_make_memory_entry_64(task, &size, 数据地址, VM_PROT_READ | MAP_MEM_USE_DATA_ADDR | MAP_MEM_VM_COPY, &port, MACH_PORT_NULL)`；解码端用 `mach_vm_map` 把这个 entry 只读映射进 backboardd。端口为空说明 SpringBoard 里这次调用失败了。
- 内核探针（`xnu26/patches/74-osfmk%vm%vm_memory_entry.c.patch`，每次开机最多 16 行）：`12377-cmd45` 只在 `vm_map_copyin_internal` 失败时打印，`bo33` 没有输出；`12377-cmd46` 在 `mach_make_memory_entry_cleanup` 打印每次失败的拷贝型调用。`bo34` 的读数是 `SpringBoard[33] copy entry for 0x1154e0000 + 0x0 permission 0x300001 failed 4`，另一个地址 `0x1154e8000` 相同：大小为 0，在参数检查一步返回 `KERN_INVALID_ARGUMENT`。
- 这张图是海报快照。`bo34` 的图层转储里，`PBUISnapshotReplicaView` 下的 `UIImageView` 内容是 `<ATX >` 格式的 CGImage。PosterUIFoundation 的 `PUIImageOnDiskFormat` 默认用 ATX 写快照（`+defaultATX`、`+atxWithBlockSize:twiddling:`）。
- 改法：`inject_posterboard.c` 在 PosterBoard、SpringBoard 与扩展里把这两个类方法换成 `+png`。`bo35` 起快照是 `<PNG >`，没有 serialization error。快照内容是不透明黑色（`mean 000000ff`），扩展的渲染见 §7。

## 7. 多重采样的 drawable 为空

- `bo35` 里 backboardd 导入了扩展的 1125x2436 surface（`redwooddrawable: backboardd import N: surface 12` 等），合成链路上没有报错。
- `bo36` 在扩展里打开 `REDWOOD_SYNC_DRAWS` 与提交末尾的采样（`REDWOOD_THUMBS`，`REDWOOD_THUMB_ONLY=res0,out0`）。多重采样的颜色附件不能直接采样，驱动新增 `res` 一项采样颜色附件的 resolve 目标。commit 3～8 的 1125x2436（surface）与 562x1218 两个 resolve 目标，读到的部分全部是 0，颜色与 alpha 都是 0。
- 扩展的渲染通道是 4 倍多重采样，每个 draw 结束时 AIR 库用 blit 把颜色附件 resolve 进 resolve 目标。驱动对 `-supportsSampleCount:4` 默认回答 NO，只在 `REDWOOD_MSAA=1` 时回答 YES；扩展不问这个结果，照样用 4 倍。
- `bo37` 的变量：扩展打开 `REDWOOD_ONE_SAMPLE=1`，驱动把多重采样纹理和管线都建成单采样，带 resolve 目标的通道直接画进 resolve 目标。主屏与锁屏显示壁纸。
- 默认行为（`redwoodmetal_diag.inc` 的 `rw_one_sample`）：没有 `REDWOOD_MSAA` 时，驱动对 `-supportsSampleCount:4` 回答 NO，仍要 4 倍的应用拿到单采样。纹理对象照旧报告应用要的采样数，编码器据此区分这类附件与 CoreAnimation 的单采样附件；后者也带 resolve 目标，Metal 规定这时不写 resolve 目标。
- 单采样也去掉了每个带 resolve 目标的 draw 之后对整张 drawable 的 resolve blit。

## 8. 锁屏时钟与玻璃效果

- 时钟的图层（`bo39`）：`CSProminentTimeView` 下是 SwiftUI 的 `TitleLabelView`，其中 `SwiftUI.SDFLayer`（`CABackdropLayer` 子类）下挂 `CASDFLayer` 与 `CASDFElementLayer`，后者的内容是 723x267 的 CGImage。时间数字由 backboardd 的 SDF 玻璃管线（`glass_background_lph`、`glass_foreground_sdf_lph`、`glass_background_sdf_no_bleed_lph`）画出。日期走 `BSUIVibrancyEffectView`，一直正常显示。
- 模糊金字塔（`bo40`）：玻璃采样的模糊背景由 `variable_blur_downsample_frag_lph` 逐级画进一张 384x256 纹理的各个 mip 级别，每个通道用颜色附件的 `level` 指定级别。驱动原先忽略 `level`，所有通道都画进第 0 级，每个通道开头的清屏又把上一级清掉，玻璃读到的模糊背景为空。驱动改为对 `level` 非 0 的颜色附件建这一级的纹理视图（`redwoodmetal_texture.inc` 的 `rw_attachment_level`）。
- 附件尺寸（`bo41`）：这些通道的第二个颜色附件没有指定级别，和级别视图大小不同，AIR 库按「所有附件同尺寸」拒绝，一轮里 96 个命令缓冲失败，锁屏闪烁。库改为按所有附件共有的区域绘制，与 Metal 一致。`bo42` 没有绘制失败，Dock 的玻璃底板显示，时钟仍不显示。
- 时间的 SDF 输入（`bo42`）：玻璃管线采样的 SDF 是 SpringBoard 渲染的 `RGhA` 654x270 IOSurface，backboardd 读出为空，玻璃只画出包围盒形状。SpringBoard 每轮有一条 SwiftUI custom effect 管线被拒（`custom_effect_vertex` 加 `ffgea5cmba5dhmhba3`，链接 `custom_fn`）：`custom_fn` 把纹理句柄存进局部结构体 `RB::Layer`。这条管线与时钟 SDF 为空的关系是推断，没有验证。
- 翻译器改动：存进局部（常量偏移的 alloca）的指针记在翻译期的槽里，同一位置读回指针时取回它（`air_ptr_slot.inc`）。宿主机上带 `--link` 的这条管线可以翻译；系统 metallib 语料 11398 个模块翻译成功 3858 个，没有回退。没有上机。

## 9. 未解决

- 扩展里 `IOSurfaceSharedEventAddEventListener failed: e00002c7` 与 `kIOSurfaceMethodSetCoreVideoBridgedKeys failed: e00002c7`：MiniIOSurface 没有实现 selector 40（`IOSurfaceSharedEventAddEventListener`）和 54（`IOSurfaceClientSetCoreVideoBridgedKeys`）。同样没有实现、开机过程中被调用的还有 17（`IOSurfaceClientSetSurfaceNotify`）、32（`IOSurfaceGetGraphicsCommPageAddress`）、41（`IOSurfaceSharedEventRemoveEventListener`），这些在不带 `POSTER_METAL` 的 `bo23` 里也出现。selector 与函数的对应来自 iOS 26 IOSurface 框架的反汇编。
- 锁屏时钟仍不显示，见 §8。
- `bo43` 版本上从主屏打开应用是纯黑屏（用户反馈），日志里 backboardd 没有绘制失败，原因没有查。
- 4 倍多重采样的渲染或 resolve 在 A830 上得到全 0，哪一步出错没有查。查时用 `REDWOOD_MSAA=1` 给扩展打开 4 倍，再用提交末尾的采样读 `res`。
- `bo38` 巡检末尾、关闭搜索后的一张截图里第一排图标被横向截去一段，3 分钟后补拍的截图正常，原因没有查。
- Dock 的玻璃在进入桌面后先完整，随后一段时间只剩边缘高光，几分钟后恢复（用户反馈，`bo42` 之后），原因没有查。
