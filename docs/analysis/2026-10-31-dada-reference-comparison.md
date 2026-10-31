# 小米 15 iOS 26 参考仓库对照（2026-10-31）

用户在 2026-10-31 提供了 [hakios-arm64e-dada](https://github.com/superboyyy/hakios-arm64e-dada)：在小米 15（dada，SM8750，Adreno 830）上运行 XNU 12377 和 iOS 26 arm64e 用户态，同样基于 HakiOS。本文逐项对照它和我们的内核、平台驱动、引导、用户态与图形路径，列出可借鉴的做法、我们的现状、价值与改动量。全部为离线阅读与主机验证，没有上真机；条目默认基于两边代码的对照，推断与未核实处在条目里写明。

引用格式：对方文件写 `dada:路径:行号`，路径相对参考仓库根目录；内核改动都在 `dada:kernel/xnu-12377.121.6-dada.patch`，写作 `patch:行号`。我们的文件写项目相对路径。

## 1. 结论

- 锁屏时钟：`bo45` 起显示，由指针槽改动（userland `b67e4c470`）修好，SpringBoard 的管线拒绝降为 0。§3.1 的两处改动（单采样附件直接画进 resolve 目标、`glass_background_*_lph` 的导数改为 32 位按像素计算）在同一次开机内逐个关掉后时间仍显示，与时钟无关，保留并留有开关。读数见[锁屏壁纸](2026-10-31-mercury-wallpaper.md) §8。Dock 玻璃没有单独判读，RenderBox 的两项（§3.7）与 CA 的 inline SDF（§4.2）仍待查。
- 应用打开黑屏：`bo44` 起应用的异常文本能输出（§4.1），两处异常都是系统盘缺文件，选取规则已放宽，见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §6。是否给应用 Metal 设备（§4.4）等应用能打开后再定。
- 滑动卡：GPU 调频已按对方的思路改为最低 342 MHz、触摸后 1.5 秒（内核 `12377-cmd50`），`bo47` 的翻页与滚动帧率和旧规则相同，调频排除（§3.8）。剩下的方向是 CPU 7 核加低频上限的对照（§6.4）、显示控制器直接扫描（§6.5）、DDR 静态投票（§6.6）。
- 迭代效率与无人值守：loader 武装看门狗（§5.1）、系统盘放进 DSU（§5.2）、`fastboot boot` 起 loader（§5.4）经用户同意后已实现并上真机。离线方面，QuartzCore 的 AIR slice 已加入主机语料，glassref 值得移植（§3.4）。
- 平台驱动：蓝牙的 iOS 26 接法对方已跑通，引脚与 K90 一致（§6.2）；充电状态、音频、Wi-Fi 共用「SMMU 直通 + 4 GB 以下 DMA + ADSP」这一层（§6.1、§6.3）。
- 路线：保持现有的 AIR→NIR→freedreno 路径，从对方的两条路径里取具体做法（§3.7）。

## 2. 对方的实际进度

README 的状态表有几处和代码对不上。

- 「8 核」：内核实际用 7 个核，loader 自己占 core 0 服务 USB 和块读（`dada:base/xnuloader/loader.c:4048-4087`；`patch:4887` 的注释写 prime 核是逻辑 CPU 5、6）。我们的 loader 逻辑相同（`hackios-xnu-kernel/xnuloader/loader_05_layout_run_kernel.inc:775-810`），`cpus=7` 是上限。
- 「3.52 GHz」：`dadacpu=2` 固定在 sustained 档时的频率。日常脚本 `dada:base/tools/dada-ios.sh:38` 用 `dadacpu=3`（调速器），默认上限 CPU 2.4 GHz、GPU 660 MHz（`patch:5155`；`dada:kernel/HISTORY.txt:76`）。
- 截图：`dada:base/docs` 下的锁屏、主屏、设置、App Store 截图来自 iOS 16.5 的 POCO X5 Pro（`dada:base/README.md:26-29,40`），分辨率 720x1600 和 1080x2400。iOS 26 上实测到的是进主屏、触摸、蓝牙、扬声器（`dada:README.md:20`）。仓库里没有 iOS 26 应用能打开的记录。
- 「闪存按需读写」：按需读已实现。运行期写闪存只放行 redwood 的 darwin 分区（`dada:base/xnuloader/loader.c:1691-1695,2323`），DSU 分区只读（`:1679`）。对方没有持久化 `/private/var`，用镜像里的 `var.pack` 种子，和我们的 `var.seed` 是同一类做法。
- 两边内核同源：`redwood_guard.c`、`redwood_battery.c`、`redwood_qmi.c`、`redwood_sparse.c` 逐字相同，`redwood_ufs.c` 只差 25 行。对方针对 SM8750 的增量集中在 `hakios_dada_*.c` 和 loader。

## 3. 图形与 Metal

对方的 AIR 翻译器和 Metal 驱动与我们同源（`dada:userland/tools/mesa/air/`、`dada:userland/userland/src/redwoodmetal.m`），逐函数对照后差异如下。我们的文件在 `hackios-xnu-kernel/tools/` 下，写作 `tools/...`。

### 3.1 结果写不进目标的几处

- 单采样附件的 resolve（已改，未上真机）：
  - 对方：创建 render encoder 时，只要 storeAction 是两种 resolve 之一且 resolveTexture 不为空，就记下 resolveTexture、resolveLevel、resolveSlice；endEncoding 时每个附件记一次拷贝，排在本通道所有 draw 之后，不检查采样数，通道里没有 draw 也执行（`dada:userland/userland/src/redwoodmetal.m:5384-5394,6706-6736`）。
  - 我们：每个 draw 之后做 resolve，只写 level 0，源为单采样时跳过（`tools/mesa/air/air_metal.c:6909-6950`）。跳过的依据是「Metal 对单采样通道不写 resolve 目标」，这是我们自己的假设，没有核实；Apple GPU 分块渲染，通道结束时把块内存写到 resolve 目标，单采样也会写。我们记录过 CoreAnimation 在 420 秒里有 354 次单采样附件带 storeAction 2。
  - 对方的注释（glass21）只说 RenderBox 不做 resolve 时显示的纹理是空的，没写附件采样数。锁屏时钟的 SDF 输入为空（[壁纸与锁屏时钟](2026-10-31-mercury-wallpaper.md) §8），这是首要怀疑点。
  - 改法：storeAction 为 `MultisampleResolve`、loadAction 不是 Load、像素格式相同时，驱动把 resolve 目标（按 `resolveLevel`）直接当作颜色附件，和多重采样附件已有的处理一致（`tools/userland-driver/redwoodmetal.m` 的 render encoder 初始化）。`REDWOOD_RESOLVE_BLIT=1` 恢复旧行为。
- 导数（已改，未上真机）：
  - 对方：`dfdx`、`dfdy`、`fwidth` 一律转成 32 位、按像素（fine）计算（`dada:userland/tools/mesa/air/air_intrinsics.c:533-549`）。注释记录 ir3 按 F32 发射 dsx/dsy，half 操作数在 A830 上让 fwidth.f16 得到 inf 和 NaN，Apple GPU 得到 0.5（glasscase `h_fwidth`，以及 `glass_background_sdf_lph`）；按 quad 的粗导数让 fwidth 抗锯齿的边缘偏差几十个像素。
  - 我们：直接用 `nir_ddx`/`nir_ddy`，保留 half（`tools/mesa/air/air_intrinsics.c:520-526`）。
  - 离线核对（2026-10-31）：QuartzCore 的 171 个可翻译函数里，导数操作数为 half 的只有 `glass_background_lph`、`glass_background_no_bleed_lph`、`glass_background_sdf_lph`、`glass_background_sdf_no_bleed_lph` 四个；`bo43` 的 backboardd 建过后两条管线（顶点着色器 `sdf_filter_vert_lph`），锁屏时钟与 Dock 玻璃走这一组。
  - 改法约 15 行，主机语料无回退。`AIR_COARSE_DERIVATIVES=1` 恢复旧行为，主机上验证过开关前后的输出分别与改动前后逐项一致。
  - 对方在「discard 之后取导数」的 draw 上遇到过 A830 停机，加了 defer_demote；我们有 `air_gather_quad_helpers`（`tools/mesa/air/air_intrinsics.c:1149`），对方没有，需单独一轮验证。
- 只清屏的通道：对方在没有 draw 的通道里也执行 load action，每个附件用自己的清屏颜色，只清自己（`PIPE_CLEAR_COLOR0 << i`）（`dada:userland/userland/src/redwoodmetal.m:4766-4786,5395-5403,6683-6703`）。我们的 endEncoding 不做事，只读附件 0 的 load action，再用 `PIPE_CLEAR_COLOR` 一起清所有附件（`tools/userland-driver/redwoodmetal.m:3346`，`tools/mesa/air/air_metal.c:6817-6836`）。结果是目标残留上一轮内容。改动约 80 行。
- 单个 draw 失败：我们的 draw 或拷贝失败后整个 command buffer 标为错误，后面的 draw 都不执行（`tools/userland-driver/redwoodmetal_commandbuffer.inc:537-549,1043-1055`）；对方只跳过这一个 draw，注释写旧做法出现过黑块和整帧黑屏（`dada:userland/userland/src/redwoodmetal.m:4789,5129-5142`）。`bo42`、`bo43` 的日志里「command buffer failed」为 0 次，这两轮的时钟问题与它无关；`bo41` 的 96 次失败已由附件尺寸修复解决。改动约 10 行，作为防护保留在待办里。
- 拷贝：我们的 `rwa_texture_copy` 和 `rwa_buffer_copy` 每次都 flush 并等 fence，要求格式完全相同，区域重叠直接拒绝（`tools/mesa/air/air_metal_copy.inc:37,81,93,104`）。对方不等待；块大小与采样数相同时用 `resource_copy_region`，否则用 `pipe->blit`（`dada:userland/tools/mesa/air/air_metal.c:4400-4440`）。`bo43` 里 MercuryPosterExtension 每 64 个 command buffer 有 394 次拷贝，每次平均 2.1 ms。
- function constant：对方把 `air.function_constant` 求值为 false 的参数当作不存在，常量折叠后没用到的纹理和采样器补 null 视图（`dada:userland/tools/mesa/air/air_to_nir.c:2492-2510,5662`）。注释写 RenderBox 曾因此漏画图标（glass21）。我们只认 `air.arg_unused`。改动中（约 300 行）。

### 3.2 编译与性能

- CSO 共享：对方用 `nir_serialize` 加 blake3 做键，同一个阶段只编译一次，引用计数释放（`dada:userland/tools/mesa/air/air_metal.c:5951-6012`）。我们每个管线各编一份。约 70 行。
- 特化后折叠：对方只翻译常量分支实际走到的块，callee 按常量实参特化，跑 opt 循环后 `nir_sweep`，编译完释放 NIR；注释记录 `fixed_frag_lph_cph` 从 8907 条指令降到 25 条，每个管线常驻内存从 6 MB 降到 0.1 MB（`dada:userland/tools/mesa/air/air_to_nir.c:4029,5119,5998,6326-6380`）。我们只做 inline、vars_to_ssa 和 dce，片段着色器的 NIR 一直挂在管线上。改动中。
- 未对齐 UBO：缺 `air.buffer_size` 时对方最多上传 16 KB，注释说之前每个 draw 上传整块 uniform，占窗口服务器 60% 的 CPU（`dada:userland/tools/mesa/air/air_metal.c:3384,4108-4110`）。我们上限 64 KB（`tools/mesa/air/air_metal.c:3613`）。先统计这条路径的次数。
- A830 停机防护：`widen_scratch` 把 8/16 位 scratch 访问改成 32 位读改写，`air_cap_loops` 给渲染阶段的循环设 16384 次上限（`dada:userland/tools/mesa/air/air_to_nir.c:5855,5905`）。我们没有。每项 30～50 行。

### 3.3 应用相关的兼容项

- 结构体 phi 和指向不同位置的指针 phi：对方支持（`dada:userland/tools/mesa/air/air_to_nir.c:4798,4953`），我们拒绝（`tools/mesa/air/air_to_nir.c:2763,2818`）。日志里出现这两句时才相关。
- 导入的 IOSurface 给可写绑定：VideoToolbox 的 `VTMTSComputeFunction1x1` 会写没有 ShaderWrite 的表面（`dada:userland/tools/mesa/air/air_metal.c:1536-1546`）；`redwooddrawable.m` 允许 R8/R16/R32 整数格式套在字节数相同的单平面表面上（`dada:userland/userland/src/redwooddrawable.m:393-404,620-640`）。和带视频的应用有关。
- Blit 编码器：对方实现了 fillBuffer、纹理到缓冲拷贝、整纹理拷贝，synchronize 和 optimizeContents 为空实现；所有驱动类遇到未知 selector 返回 0 并记一次日志（`dada:userland/userland/src/redwoodmetal.m:581-635,6797-6945`）。我们只有 blit 编码器这样处理，其他类遇到未知 selector 仍抛异常（`tools/userland-driver/redwoodmetal_blit.inc:242-264`）。应用在 Metal 驱动里抛异常也会 SIGABRT，和 4.1 一起看。
- 点精灵：对方把 point_coord 做成 `VARYING_SLOT_PNTC` 输入，理由是 ir3 不处理 `load_point_coord`，CA 粒子着色器报「Unhandled intrinsic type」（`dada:userland/tools/mesa/air/air_to_nir.c:985-1000`）。我们用 `nir_load_point_coord`（`tools/mesa/air/air_to_nir.c:889`）。约 10 行。

### 3.4 定位与测试工具

- `metal_bisect`：从指定开机秒数起按时间段轮流跳过一组管线的 draw，配合录屏找出导致变黑的那一组（`dada:userland/userland/src/redwoodmetal.m:4870-4920`）。`metal_procs` 只让指定进程拿到 Metal 设备，其余进程走 CPU 路径（`:1543-1580`），可以用来判断应用黑屏出在驱动还是合成。
- 以 LLVM 为准的数值比对：`cpuref.py` 把 AIR 的 triple 改成主机后用 llc 编译，同一着色器走我们的前端后解释 NIR，两边逐项比较；271 个片段着色器里 256 个能自动比对，另有 3424 个 case 在 softpipe 上执行（`dada:userland/tools/air/air.md` 第 4 节）。我们 `tools/air/` 已有 `cpuref.py`。
- QuartzCore 的 `default.metallib` 是 fat 文件（AIR slice 加 Apple GPU 的 Mach-O slice），我们的 air2nir 报 unknown，玻璃与 SDF 着色器因此从未进过离线语料。抽出 AIR slice 后 189 个函数里 171 个能翻译；不能翻译的是 `fixed_frag_lph_cph`、`fixed_frag_lph_cpf`（指针 phi）和 16 个用 imageblock 的 tile 与 compute 函数。对方 glassref 的注释同样写的是「AIR slice」。
- glassref：在 Mac 上让 Apple GPU 和主机版 libredwoodair（softpipe 或 llvmpipe）画同一个 draw，逐像素比较，支持 `--tex sdf` 输入；glasscase 把这些用例连同 Apple 的像素带到手机上经 ir3 重画后比较；ir3cost 在 Mac 上测 ir3 编译成本（`dada:userland/tools/air/glassref.m`、`glasscase.c`、`glasscases.sh`、`ir3cost.m`）。时钟、玻璃和 custom effect 可以离线查，不占真机轮次。前提是 Mac 的 Metal 能加载 iOS 26 的 AIR metallib；`glasscases.sh` 用了 macOS 没有的 `timeout` 命令。约 1300 行，许可为 MIT。

### 3.5 多重采样与附件级别

- 对方的 `supportsSampleCount` 也只回答 1（`dada:userland/userland/src/redwoodmetal.m:2806`），resolve 同样用 `pipe->blit`。A830 上 4 倍多重采样 resolve 为全零的问题，从对方那里拿不到答案。
- 附件级别：对方直接设置 `fb.cbufs[i].level` 和 `first_layer`，渲染区域取最小附件（`dada:userland/tools/mesa/air/air_metal.c:7564-7578,7645`）。我们用临时视图达到同样效果（`tools/userland-driver/redwoodmetal_texture.inc` 的 `rw_attachment_level`），不支持 slice。

### 3.6 我们有、对方没有的

- 逐 draw 状态去重（`tools/mesa/air/air_metal_state.inc`）和异步完成线程；对方每次 commit 都同步等 finish（`dada:userland/userland/src/redwoodmetal.m:4848`）。
- Mesa 补丁：SSBO 4 字节偏移（`tools/mesa/freedreno-ssbo-offset-4.patch`），以及 draw-perf、fd-submit-merge 等性能补丁；对方靠拷贝和回写。
- Stitching 图和链接函数内联（`tools/mesa/air/air_link.inc`）；对方只支持片段阶段的 linked function。
- 共享内存的 BytesNoCopy、建在缓冲上的纹理、heap；对方这几处都是拷贝。
- 格式与采样：RGB10A2 等打包格式、BC、ASTC LDR、带级别范围的视图、按 mip 写 image、运行时选纹理。
- `air_gather_quad_helpers`（`tools/mesa/air/air_intrinsics.c:1149`）。

### 3.7 对方的两条 Metal 路径

- 两条路径都在仓库里，打镜像时选（`dada:userland/userland/build.sh:527-551`）：
  - 默认放 AIR 路径的 `RedwoodMetal.bundle`，即和我们同源的 redwoodmetal.m 加 libredwoodair（AIR→NIR→freedreno/ir3）。
  - 设了 `GPU2_PLUGIN=` 时换成 gpu2 的 NativeAdrenoMetal 包：UniXNU 的 ObjC++ 前端（MIT）→ Rust 写的 metal2vulkan 运行时与 AIR→SPIR-V 翻译器（GPL-2.0+ 或 LGPL-3.0+）→ 带 darwin 内核接口的 Turnip（MIT）→ RedwoodGPU。
- `dada-ios.sh:38` 的 `metal_procs=backboardd` 只有 AIR 驱动读（`dada:userland/userland/src/redwoodmetal.m:1544-1590`），注释写 RenderBox 走 AIR 时主屏是黑的，所以 SpringBoard 走 CPU。gpu2 包按 `NativeAdrenoMetal.clients` 决定，写的是 `*`。
- 日常用哪条，仓库里没有能确认的命令行（推断偏向 gpu2：工作树名、取回 gpu2 管线缓存的脚本、10-29～10-31 的内核提交都在服务多进程的 Turnip 客户端）。
- gpu2 的读数只有注释里的零散数字，没有整体帧率：合成器每次提交 13～44 ms GPU 时间；壁纸 4 倍 MSAA 每帧 135～195 ms，改单采样后 40～55 ms；开机时 backboardd 建 213 条管线用 7.7 秒；QuartzCore 的 `fixed_frag` 约 46000 条 SPIR-V 指令，每条管线编译约 1 秒（`dada:gpu2/patches/nativemetal-dada.patch:727-754`，`dada:gpu2/patches/metal2vulkan-720ef1c-dada.patch:20`）。`dada:gpu2/M2V-NEXT.md` 记录 metal2vulkan 升级后只在 Mac 上跑过，待办是 Turnip/A830 编译检查、上手机、量合成器帧时间。
- 取舍：gpu2 换来 Turnip 现成的通道内 resolve、GMEM 选择、管线缓存和时间线同步，能在 Mac 上经 MoltenVK 与 Apple GPU 对比；代价是管线编译慢、内存与地址空间占用大、每次 draw 多一层桥、需要 Rust nightly 加 arm64e 工具链。我们的 Gallium 路径层次少、全部 APSL，翻译语义要自己保证。以对方现有读数看，切换路线没有性能上的依据，本文不建议切换。

gpu2 一侧另有几处做法可用于我们的 AIR 路径，NativeMetal 补丁为 MIT。

- 编码器级别的 LOD 范围：对方实现了 `setFragmentSamplerState:lodMinClamp:lodMaxClamp:atIndex:`（`dada:userland/userland/src/redwoodmetal.m:3833-3870`），注释写没有它时模糊金字塔采样到正在写的那一级，出现阶梯状色块（glass3、glass4）。我们把这两个参数丢掉（`tools/userland-driver/redwoodmetal.m` 的同名方法）。已核实差异；和 Dock 玻璃的关系是推断。约 40 行。
- 链接函数：对方读 `groups`，只链接了一个函数时把 `custom_fn` 解析到它（`dada:userland/userland/src/redwoodmetal.m:1791-1838`，`dada:userland/tools/mesa/air/air_to_nir.c:4081-4090`）。我们不读 `groups`，只按名字精确匹配（`tools/userland-driver/redwoodmetal_stitch.inc:549-590`，`tools/mesa/air/air_link.inc:39-46`）。可以先用 `air2nir --link` 在主机上验证。
- 纹理 swizzle：对方不透明图层的表面经 alpha 固定为 1 的视图读取，没做时壁纸发白（`nativemetal-dada.patch:1317-1318,1365-1366,3243`）。我们忽略 swizzle（`tools/userland-driver/redwoodmetal_texture.inc:347-373`）。
- `newTextureLayoutWithDescriptor` 与 ASTC 的 `newTextureWithBytesNoCopy`：对方实现了，注释写 backboardd 会要全屏 ASTC 4x4 图，RenderBox 交来的 ASTC 长度为 0（`nativemetal-dada.patch:2204-2240,2304-2330,2470-2480`）。我们都返回 nil；`bo42`、`bo43` 的 SpringBoard 各打印过「newTextureLayoutWithDescriptor returns nil」。锁屏时钟由 SwiftUI 经 RenderBox 绘制，这一条列入时钟的怀疑项。
- `RGB10A8_2P_XR10`（550/551）：对方注释写 RenderBox 用它套在表面上，拒绝时图标背景和时钟表盘画不出来（`nativemetal-dada.patch:2534`）。我们的库把 550/551 当作不认识的格式拒绝（`tools/mesa/air/air_metal.c` 的格式说明），`bo42`、`bo43` 的日志里没有出现。
- 其他：`currentAllocatedSize` 回答真实值（我们返回 0）；`CAEnableIOSurfaceCompression=false`；ir3 磁盘缓存与多进程共享缓存目录（我们在 `tools/mk-mesa.sh` 关掉了着色器缓存）。

### 3.8 内核 GPU 驱动

- 调频（`bo47` 实测与帧率无关）：
  - 对方：每 20 ms 统计一次忙碌占比，超过 75% 升一档，连续 10 个窗口低于 35% 才降一档，最低 342 MHz；触摸后 1.5 秒内不低于 734 MHz；过热时每 100 ms 把上限降一档（`patch` 中 `hakios_dada_cpu.c:600-660,730-736,821-890`）。
  - 我们：按负载在 160 MHz 与 607 MHz 之间二选一。100 ms 内负载折算到 160 MHz 达到 20% 就直接升到 607 MHz，低于 10% 持续 500 ms 就回 160 MHz，触摸提频只保持 300 ms，GPU 温度到 70 °C 回 160 MHz、低于 60 °C 恢复（`hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_hfi.c` 的 `adreno8_speed_tick`）。
  - 读数：`bo42` 一轮切换 40 次、`bo43` 8 次。两轮留下的温度读数最高约 49 °C（每轮只剩 4～5 条），没到 70 °C。
  - 结果：`12377-cmd50` 加了 `adreno8_floor`（默认 342 MHz）、`adreno8_touch_ms`（默认 1500）和逐档的温度限制。间隔 3 秒的 20 次翻页，旧参数（`bo46`）平均 53.4 帧／秒，新默认值（`bo47`）53.6 帧／秒；今天视图滚动 49.0 与 50.2 帧／秒。帧率不受 GPU 频率限制，与[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §3 里 `bo3` 的结论一致。
  - 建议：保留 70/60 °C 阈值，加频率下限、延长触摸窗口、过热时逐档下调，约 40 行。
- 地址空间（价值中高）：对方所有进程共用 15.5 GB，8192 张末级表按物理地址哈希查找，提交时只写回改过的表；之前 3.5 GB 时海报全开就耗尽，壁纸变黑。我们的地址范围 3.25 GB，1024 张表只覆盖 2 GB（`hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_memory_private.h`、`adreno8_bo.c`），IB 地址限制在 4 GB 以内，buffer 从 `kernel_task` 分配。应用黑屏时先在日志里查 `no GPU addresses`、`no page table for GPU address`、`no memory for a buffer`；`bo42`、`bo43` 里没有出现。
- 新表面清零后写回（价值低到中）：对方 `bzero` 后紧跟 `dc civac`，注释写扫描输出前的清理把缓存里的零写回、盖掉 GPU 刚画的帧，出现黑块（`MiniIOSurface.cpp:167-181,197-199,235-247`）。我们只清零（`hackios-xnu-kernel/xnu/files/iokit/Kernel/MiniIOSurface.cpp`）。k90auto 用 `gpu_coherent=1`，风险只在关掉它时出现。约 10 行。
- 提交与优先级（价值中）：对方两条环加 CP 抢占，backboardd 固定在 ring 0；可选 `gpu_fair_ms` 让其他进程先等自己上一次提交完成。我们所有进程共用一个 HWSCHED context。对方的环与抢占代码转写自 Linux，为 GPL-2.0；`gpu_fair_ms` 约 15 行，可以自写。
- 提交末尾的缓存处理（假设）：对方在每个 IB 后追加 `CCU_INVALIDATE` 和带时间戳的 `CACHE_CLEAN`，fence 在写回之后才前进。我们只写 HFI 描述符，收尾由 GMU 固件决定，固件实际做了什么未查。
- 帧缓冲等新提交（价值中低）：对方在 swap 早于这一帧的提交到达内核时，最多等 33 ms 看有没有新提交指向这个表面。我们只等最后一次提交完成；只在提交被合并或推迟时有影响。
- UCHE_CCHE 基址：对方写了 UCHE 和 UCHE_CCHE 两组，我们只写 UCHE 一组（`adreno8_gpu.c`）。后果未知，可以作为单独一轮的变量。
- 我们领先的部分：fence 经非缓存别名读取；EOP 超时后做 hang dump，并等 GMU 的 HFI 150 消息；用 GMU 中断而不是轮询。两边都没有 GPU 复位。
- 对方读 qfprom 0x138 的速度档熔丝时整颗 SoC 停住；我们在 step 1 读同一地址（`0x221c8138`），K90 上至今正常，改动这段时要留意。

## 4. 应用与用户态

### 4.1 应用 abort 的异常文本

- 对方：`applog` 选中的程序在 exec 时加上 `OS_ACTIVITY_DT_MODE`、`ACTIVITY_LOG_STDERR`、`CFLOG_FORCE_STDERR`（`patch:56222-56223`，`dada:userland/userland/mkjobs.py:283`），注释说 iOS 26 的 libsystem_trace 还要看 `ACTIVITY_LOG_STDERR`。`inject_app.c` 给应用接上标准错误输出，收到信号时打印栈（`dada:userland/userland/src/inject_app.c:1-9`）。
- 我们：内核在 `exec_extract_strings` 的 applog 分支只加 `OS_ACTIVITY_DT_MODE`（`hackios-xnu-kernel/xnu26/patches/09-bsd%kern%kern_exec.c.patch`）。`applog=1` 已经把所有程序的标准输出和错误转到控制台。`inject_app.c` 两边相同，但 iOS 26 的 `INJECT` 不含任何应用（`tools/k90auto/package.py:106-111`）。
- 与 `bo43` 黑屏的关系：MobileSMS、KeyboardSettings、`com.apple.Safari` 都在画出第一帧前以 SIGABRT 退出，栈在 CoreAutoLayout、SafariCore 与 Foundation 抛异常处，异常文本没有输出，因为应用的标准错误输出接到 `/dev/null`（[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md)）。
- 已改：内核 `12377-cmd49` 在同一分支里加上 `ACTIVITY_LOG_STDERR=1` 与 `CFLOG_FORCE_STDERR=1`，未上真机。用法是启动参数 `applog=1 applog_name=NAME[,NAME...]`。

### 4.2 CoreAnimation 开关

- 对方日常启动参数带 `caenv=CA_DISABLE_FILTER_MERGING=1 caenv=CA_DISABLE_TILE_SHADERS=1 caenv=CA_DISABLE_INLINE_SDFS=1`，注释写 inline SDF 经他们的编译器画成黑色（`dada:base/tools/dada-ios.sh:9-10,38`）。这些变量在 backboardd、SpringBoard、PosterBoard 三个进程里生效（`dada:userland/userland/src/inject26.c:764-791,1710`）。
- 我们：`caenv` 只设进 backboardd（`hackios-xnu-userland/userland/src/inject.c:1291-1307`）。锁屏时钟的 SDF 输入是空的（[壁纸与锁屏时钟](2026-10-31-mercury-wallpaper.md) §8）。
- 价值高，改动极小，一轮可验证。关掉后 CA 走哪条替代管线未知。

### 4.3 IOSurfaceSharedEvent

- 对方：MiniIOSurface 实现了共享事件，selector 36、38、39、40、41，约 400 行（`patch:78989-78993`，说明在 `79778-79800`，实现从 `80896` 起）。注释写缺它时海报的 AddEventListener 返回 e00002c7，快照不完成。
- 我们：没有实现（`hackios-xnu-kernel/xnu/files/iokit/Kernel/MiniIOSurface.cpp:56-61,1615-1620`）。`bo42` 里 SpringBoard 从开机起报 8 次 `IOSurfaceSharedEventAddEventListener failed: e00002c7`。
- 当前配置下的影响（反汇编 23G90 的 QuartzCore 与 IOSurface 得出）：
  - 这行日志来自 `-[IOSurfaceSharedEventListener initWithDispatchQueue:]` 调 selector 40 失败。CAMetalLayer 初始化时总会建这个监听者，失败后返回 nil。
  - CoreAnimation 的跨进程表面同步有两道开关：NVRAM 里的 `disable_ca_shared_event`，以及 `[device supportsFamily:MTLGPUFamilyApple7]`。两道都通过才调 `newSharedEvent`。我们的 Metal 设备 `featureProfile` 默认为 0，只声明 Apple1/Common1（`hackios-xnu-kernel/tools/userland-driver/redwoodmetal.m` 的 `supportsFamily:`），k90auto 不带 `metal_profile`，所以这套等待没有启用。日志里没有 selector 36、38、39 的未实现记录，也说明没有进程建过事件。
  - CAMetalLayer 上屏时如果 drawable 带 sharedEvent，会先走 trap 10 发信号，失败后直接上屏。我们的 trap 表只到 5，越界不记日志。
  - 结论：按当前配置，backboardd 读 SpringBoard 的 SDF 表面前不等任何共享事件，e00002c7 与时钟 SDF 为空没有直接关系。只有把 profile 提到 Apple7 时，才需要实现 selector 36～41、trap 6/7/10。
- 相关风险：我们的 `encodeSignalEvent:value:` 和 `encodeWaitForEvent:value:` 是空实现（`hackios-xnu-kernel/tools/userland-driver/redwoodmetal_commandbuffer.inc:426-427`），对方在命令缓冲完成后调 `setSignaledValue:`（`dada:userland/userland/src/redwoodmetal.m:5245-5258`）。RenderBox 的 RBDrawable 上屏时调 `encodeSignalEvent:value:`；如果有进程等这个值，会一直等不到。未在真机核实。
- 价值：当前配置下中低；改动中。

### 4.4 Metal 设备给所有进程

- 对方 `gpu2` 路线：`NativeAdrenoMetal.clients` 写 `*`，每个进程都能拿到设备（`dada:gpu2/build_plugin.sh:50`，`dada:gpu2/patches/nativemetal-dada.patch:678`）；backboardd 与 SpringBoard 的内存块 16 MiB，其余沙盒进程 8 MiB，因为内核拒绝给它们 64 MiB（同一补丁 `:725-731`）。注释记录过半成品设备会触发断言，launchd 随后反复重启这些进程（`patch:78653-78681`）。
- 我们：只给 SpringBoard、backboardd、iconservicesagent、MercuryPosterExtension 注入登记库（`hackios-xnu-userland/userland/src/sb_metal_registration_sequence.inc:7-13`），应用里 `MTLCreateSystemDefaultDevice` 返回 nil。
- 价值高，改动中。和 4.1 的异常文本对照后再定是否做。

### 4.5 iOS 26 的任务拒绝列表与首次开机标记

- 拒绝列表：对方只拒绝没有硬件或不能运行的服务，放行 bluetoothd、音频、locationd、keybagd、lockdownd、datamigrator、ReportCrash 等，拒绝 syncdefaultsd、osanalytics、PerfPowerServices（`dada:userland/userland/mkjobs.py:231-241`）。放行 bluetoothd 的理由：拒绝时 audiomxd 每秒查找约 16000 次。我们仍用 16.5 的列表（`hackios-xnu-userland/userland/mkjobs.py:218-229`），只额外放行 dmd。
- 激活与设置助理：对方只按选择子替换 `isActivated` 和 `_setSetupRequiredReason:`（`dada:userland/userland/src/inject26.c:793-920`），purplebuddy 写 `SetupFinishedAllSteps`、`SetupVersion=99`（`dada:userland/userland/build.sh:581-594`）。我们按 23G90 的地址和字节校验后替换（`hackios-xnu-userland/userland/src/inject_sb26.c:254-257`）。
- 迁移完成标记：对方写了 `com.apple.migration`、`com.apple.DataMigration`、root 名下的同名文件和 host id 为空串的 ByHost 文件（`dada:userland/userland/build.sh:595-616`），我们只写了 mobile 的一份。放行 datamigrator 之前要先补齐。
- `SBAutoLockTime=-1`：对方的 `com.apple.springboard.plist` 有这个键，无人值守轮次不会自动锁屏。
- 价值中，改动小；每放行一个任务都要观察是否出现崩溃循环。

### 4.6 着色器缓存与 `/private/var` 导出

- 着色器缓存：对方 mobile 用户的所有进程共用 `com.redwood.m2v-shared`，镜像带上一轮导出的管线包（`dada:gpu2/patches/nativemetal-dada.patch:747-800`，`dada:gpu2/tools/m2vpack.py`）。注释记录 backboardd 一个进程建了 213 次管线，用时 7.7 秒。我们的驱动和 AIR 库都没有磁盘缓存。
- 状态导出：`stateexport` 在文件静止 15 秒后经 GPU 导出通道发出 PosterBoard 数据、着色器缓存和图标缓存，由 `varpack.py` 合并，init 在 launchd 之前解包（`dada:userland/userland/src/stateexport.c:1-46`，`dada:userland/userland/src/init.c:597-701`）。带 GPU 的轮次也能取回。我们取种子的轮次必须不带 GPU，PosterBoard 数据因根镜像容量没放进去（[每次开机都是首次开机](2026-10-31-every-boot-is-first-boot.md) §3）。我们的访问控制表恢复比对方完整，这部分保留我们的。
- 价值中，改动中。

### 4.7 exec 期参数

- 对方有 `exec_env`、`exec_swap`、`exec_log`、`exec_deny`，按程序名注入环境变量、替换程序、记录、拒绝启动（`patch:55711-55728,56067-56179`），系统盘本身不改。`inject_strict=1` 让注入库加载失败时 dyld 停住（`patch:56507`）。
- 我们只有 `JOB_ENV` 和 `EXT_ENV`（`tools/k90auto/package.py:140-160`），对应用没有通用入口；`bbmetal16` 曾因注入库没签名整轮无效。
- 价值中，改动小（约 150 行）。蓝牙（6.2）需要前两个。

## 5. 引导与迭代效率

### 5.1 loader 武装虚拟看门狗

- 对方：loader 常驻期间用 SMC 0x86000005～8 武装 Gunyah 虚拟看门狗，30 秒触发复位；主机 180 秒内发过命令才喂狗（`dada:base/xnuloader/loader.c:1132-1139,2826-2898`）。内核运行期由 core 0 每 5 秒喂一次，最多到预算加 60 秒（`:2767-2774`）。`oem hang` 主动触发复位（`:4920`），`dada:base/tools/dada-run.sh:182-192` 把 `oem stop` 加 `oem hang` 作为每轮的标准复位。
- 我们：`wdt_arm()` 在非 redwood 平台直接返回（`hackios-xnu-kernel/xnuloader/loader_04_fault_payload_nvram.inc:58-63`），K90 上从未武装。AGENTS.md §5 记录的 10-29 事故属于主机失联后 loader 无人复位。
- 需核实：首次武装时日志里应出现 `pet=0`；复位后 ABL 进 A 槽要再扣一次 `slot-retry-count:a`，扣完回落 B 槽 Android；复位能否清掉 GMU 与 RPMh 状态未知。
- 已实现（loader v11 起）：K90 上武装，内核运行期由 `hv_wdt_pet=1` 自行喂狗。实测结果见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §5。

### 5.2 系统盘放进 Android DSU

- 对方：用 Android 的 DSU 安装器装 `system.apfs`，装好后不启用，手机照常进 Android。libfiemap 用 dm-linear 绕过元数据加密写入，盘上是明文。loader 在 metadata 分区按 liblp 魔数找到 `lp_metadata`，取 `system_gsi` 的 extent，`oem dsu load` 约 1.5 秒读完 5 GB；`oem ramdisk crc` 按 256 MB 一段比对 CRC；`dsu patch` 只发与手机上不同的 1 MB 块（`dada:base/tools/dada-dsu.sh:1-15,40-100`；`dada:base/xnuloader/loader.c:2113-2215,4498-4640,4729-4748`）。
- 我们：每轮经 USB 上传 4.9 GB，约 2 分钟。之前把系统盘写进 userdata 尾部，事后 Android 侧缓存损坏（[系统界面修复记录](2026-10-23-android-systemui-recovery.md)）。loader 已有 super 分区的 liblp 解析（`hackios-xnu-kernel/xnuloader/loader_02_platform_cpu_ufs_survey.inc:796-822`）。系统盘因体积排除了 506 MB 的模型，这是 Spotlight 崩溃循环的来源（[Spotlight 崩溃循环](2026-10-31-spotlight-crash-loop.md)）。
- 需核实：HyperOS 是否保留 DSU（`gsi_tool status`、`com.android.dynsystem`）；userdata 剩余空间；装好后 DSU 处于未启用状态；UEFI BlockIo 块大小为 4096（对方 `loader.c:2356` 依赖这一点）；读入后的 CRC 和主机一致。
- 已实现：`hackios-xnu-kernel/xnuloader/loader_dsu.inc`、`tools/k90auto/dsu.py`，`run-auto.py` 优先从 DSU 读系统盘。HyperOS 保留 DSU。对方的 `dsu patch` 没有移植，系统盘改动后整盘重装。实测结果见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §5。

### 5.3 根卷按需读取（DSU=2）

- 对方：内核只带小根镜像启动，`stage0dsu` 把 `/dev/ufs_dsu` 只读挂到 `/flash`，再用 `kern.redwood_switch_root` 切根；块读经 loader 的块服务，core 0 一次处理一个请求（`dada:userland/userland/src/stage0dsu.c:1-50`；`dada:base/xnuloader/loader.c:2347-2372,2412-2422`）。`redwood_ufs_close()` 收尾时停发新请求，最多等 2 秒让在途请求完成（`patch:47655`）。
- 我们：内核侧块服务、`/dev/ufs_*` 节点和 `switch_root`（`hackios-xnu-kernel/xnu/files/bsd/dev/redwood_apfs_check.c:510-558`）都有。内核和根镜像要在 128 MB 内放下（`RESIDENT_RD_OFFSET`），种子大小因此受限。
- 在 5.2 之后做。需核实按需读对开机和应用启动的延迟；`dada-run.sh:22` 记录跑完后 loader 要 40 秒以上才应答。
- 价值高（省下约 4.9 GB 内存，解除 128 MB 限制），改动中。落地后种子可以带上 PosterBoard 数据。

### 5.4 `fastboot boot` 起只含 loader 的镜像

- 对方不刷分区：`adb reboot bootloader` 后 `fastboot boot dada-usb.img`（BootShim、3 MB FD、只含 loader 的 XNUP，mkbootimg header v4），看门狗复位后手机回到 Android（`dada:uefi-dada/README.md:1-30`；`dada:base/tools/dada-build.sh:10-18`）。
- 我们：loader 刷在 A 槽，每次启动扣 2 次 `slot-retry-count:a`（[引导目标切换 SOP](../plan/device-boot-target-sop.md)）。10-28 两次 `fastboot boot` 没带起 loader；打包脚本写死 header v1（`hackios-xnu-kernel/mkxnuimg.py:204`）；FD_BASE、FD_SIZE 与对方相同，PAYLOAD_BASE 不同（`hackios-xnu-kernel/common/devices/annibale.conf:13-15`）。
- 需核实：10-28 失败时的镜像内容；LK 约 2 MB 的大小上限；header v4 是否是关键差别，现有材料判断不了。
- 实测：完整的 loader 镜像（header v1，2.18 MB）从 LK `fastboot boot` 能起 loader；10-28 失败的那两次引导的是 handoff 载荷。见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §5。

### 5.5 运行期调试手段

- 对方：另开 96 KB 缓冲按前缀和 `keep_words` 保留关键日志行，避免被内核日志环覆盖（`patch:86330`）；进程因信号退出时打印寄存器、24 层帧链和自有库的加载地址（`patch:87072`）；收尾时按 `stacks=` 对指定进程逐线程取回溯，先放锁再读用户内存（`osfmk/arm64/loader_return.c` 的改动，`patch:86230` 起）；`cputop=S` 每 S 秒打印 CPU 时间最多的 12 个进程（`patch:1537`）。
- 我们有 prof 采样和 `rwsh dump`（[launchd 任务与开机处理器占用](2026-10-31-launchd-jobs-and-boot-cpu.md) §4），没有保留行缓冲和崩溃寄存器帧链。
- 价值中，改动小。

### 5.6 带 GPU 的内核回到 loader

- 对方收尾时复位 GMU CM3、关 GPU 的 SMMU context、停 CP，然后照常返回 loader，返回后能截屏和取导出数据（`bsd/dev/hakios_dada_gpu.c:3270-3292`，`patch:6236` 起；`dada:base/tools/dada-run.sh:155-176`）。
- 我们 `hackios-xnu-kernel/xnu/files/bsd/dev/adreno8.c` 的 `adreno8_quiesce` 做了同样的四步，但遇到需要保留资源时停在 wfe，理由是 GMU 留下的 RPMh 投票没有撤销。对方没有处理这项，我们的顾虑仍然成立。
- 建议做成只用于取数轮的启动参数，并确认返回后 GX 供电状态。价值中，改动小，风险中。

### 5.7 检查手段的自检

`dada:base/docs/checks.md:1-82` 列了十一种自检会出错的情形。其中「先证明检测手段确实能报出问题」（`:23-30`）和「同一张表的不同列用了不同版本的工具」（`:36-43`）两条，和我们 10-29 用错内核树的事故同类。只涉及文档。

## 6. 平台驱动

### 6.1 充电状态：ADSP 与 pmic_glink

- 对方经 GLINK 通道 `PMIC_RTR_ADSP_APPS` 询问充电信息。小米固件对标准 battmgr 请求答 unsupported，要用小米 MCA 协议：0x2001 充电状态、0x2002 充电器类型、0x2026/27/2a 电池包电压电流温度、0x20002 总线电压（大于 4 V 判定接了充电器）。电量百分比仍取 BQ27Z561。ADSP 启动需要 `adsp.mdt` 和 `adsp_dtb.mdt`（PAS 0x24）。证据：`patch:21571-21577,24511-24531,24623-24628,26026-26033`。
- 我们：充电状态按电流方向推断，cmd48 加了 ±50 mA 阈值（`hackios-xnu-kernel/xnu/files/bsd/dev/annibale_battery.c`）。路线图写明这一项依赖 ADSP。
- 对方使用的 smem、cmd_db、ADSP 内存、IPCC、RSC 地址与 K90 设备树逐项吻合（[K90 硬件地址表](annibale-hw-map.md)）。需核实 K90 Android 是否加载 `mca_adsp_glink.ko`；RPMh DRV2 要和 GPU 驱动共用一把锁。
- 价值高（也是音频的前置），改动大（约 1500～2000 行，APSL 代码可移植）。

### 6.2 蓝牙

- 硬件侧：SE14 UART（0x898000，GPIO24～27），BT_EN 是 PM8550VE GPIO3，经 SPMI 拉高；串口时钟 7.3728 MHz 得到准确的 115200；按 btqca 流程下载 rampatch 和 NVM。
- iOS 侧：bluetoothd 连接内核控制套接字 `com.apple.uart.sk.bluetooth`，开 Skywalk 通道走 H4；`exec_swap` 把 BlueTool 换成 73 行的替身，报告厂商 Broadcom；内核代答 0xFCxx 厂商命令和 0x0c5a/0x0c5b；`exec_env` 给 bluetoothd 注入 `BT_HCI_TRANSPORT=H4:POSIX;BT_CHIP=ACI~BT`。实测 PoweredOn，LE 扫描正常。证据：`patch:12489-12493,13104,13388,3696`；`dada:userland/userland/src/bluetool.c:1-13`；`dada:base/tools/dada-ios.sh:18-19,40-41`。
- 我们计划先录音一轮弄清 iOS 26 要哪种传输和芯片身份（[Wi-Fi 与蓝牙可行性](2026-10-28-wifi-bluetooth-feasibility.md)）。对方的结果直接回答了这个问题，引脚与 K90 完全一致。差别是 K90 芯片为 kiwi，固件前缀 `hmt`，对方是 `gng`。
- 价值高，改动中到大（约 1200 行）。

### 6.3 SMMU 直通与 4 GB 以下 DMA 内存

- 对方把外设的流（音频 0x1001、Wi-Fi 0x1401）匹配到最后一个 context bank，并让它不做翻译；loader 在 4 GB 以下预留 128 MB，用 `lowdma=` 告诉内核（`patch:12025-12075`；`dada:base/xnuloader/loader.c:3115,3172-3185,3814-3827`）。
- 我们：「apps SMMU 怎么处理 PCIe 端点 DMA」仍是 Wi-Fi 的前置问题，只读探针还没上机（[总账](../plan/2026-10-23-tracking.md)）。需先列出现有 SMR/S2CR，确认 GPU 驱动没占用最后一个 bank。
- 价值中高，改动小。音频与 Wi-Fi 共用这一层。

### 6.4 CPU 核数与频率上限

- 对方调速器按域取最忙的核，窗口 20 ms，留 1.25 倍余量，连续 4 个窗口可降才降频；触摸后 1.5 秒内拉到顶档；温控 CPU 85/80/95 °C、GPU 75/70/85 °C；默认上限 CPU 2.4 GHz、GPU 660 MHz（`patch:5009-5063,5141,5155`）。`small_cores` 设为 0（`dada:base/xnuloader/loader.c:617`）。
- 我们 `cpus=4 bootcpu=7`，上限 3100 MHz，温控 70/65/75 °C（`hackios-xnu-kernel/xnu/files/bsd/dev/annibale_cpufreq.c:74-88`）。
- 建议保持现有温控阈值，在现有护栏下对照 `cpus=4` 3100 MHz 与 `cpus=7` 2400 MHz 两组，比较最高温、翻页帧率和开机时间。
- 价值中高，改动小。

### 6.5 显示控制器直接扫描 iOS 帧

- 对方在 splash 区里启动帧缓冲后面放两块整帧缓冲，每帧按行拷进后台缓冲，再把 SSPP 指过去，下一次刷新时生效（`patch:5351`）。iOS 分辨率 1206x2622（`dada-ios.sh:37`）。
- 我们每帧把 1125x2436 缩放到 1156x2510，静止时 1.6 ms、翻页时 5.4 ms，用两个线程（[合成路径的处理器开销](2026-10-31-compositor-cpu-path.md)）。K90 的 splash 区同样从 0xfc800000 起 43 MB，放得下两块整帧；两边分辨率差 31 列、74 行，要么留边，要么用 SSPP 缩放器。
- 价值中高，改动中（约 500 行）。先只读确认 loader 交接时 DPU 的现场状态。

### 6.6 其他

- 电池温度封顶：对方实测电池 43～45 °C 时 iOS 把整屏亮度压到接近全黑，上报值封顶 35 °C 后恢复，日志保留真实温度（`patch:24812`）。我们原样上报。价值中，约 10 行。
- DDR/LLCC 投票：对方经 SCMI 厂商协议 0x80 把 memlat 表交给 CPUCP（默认关），没开时给 MC0、SH0 一个固定 BCM 投票；注释记录 DDR 停在最低档时每次全屏 pass 多花约 2 ms（`patch:4516,4980`）。我们只有 GPU 经 GMU 投带宽。建议先做静态投票对照，约 20 行。
- 扬声器：AudioReach 两张图加 CS35L43 功放（`patch:1930,1676`）。K90 功放是 tfa98xx 和 Sia91xx，不同；对方没接 `redwood_guard.c` 的扬声器保护，移植时要接上。改动大。
- 麦克风：WCD9395 模拟麦经 SoundWire 进 TX macro，K90 同为 WCD9395。改动大。
- Wi-Fi：对方芯片 peach，用 Linux ath12k 通到 WMI，多数轮次固件在第一次射频操作时死掉。`mk-ath12k.sh` 构建时拉取 GPL-2.0 代码，用它构建的内核不宜分发二进制。可复用的是 `hakios_mhi_boot.c`（BSD-2-Clause-Patent）、6.3 的 SMMU 直通和排查顺序。
- 相机、手电、马达：对方没有超过我们。

## 7. 许可

- 对方 `kernel/`、`base/`、`userland/` 是 HakiOS 的 APSL 2.0（`dada:NOTICE.md:6-8`），和我们同源，移植时保留版权声明。
- libdeflate、libzbitmap 是 MIT；UniXNU 来源的文件和 `uefi-dada.patch` 是 BSD-2-Clause-Patent；`tools/` 是 MIT。
- `gpu2/` 里 metal2vulkan 是 GPL-2.0-or-later OR LGPL-3.0-or-later，发布链接它的插件时要附源码（`dada:NOTICE.md:29`）。本项目只参考做法，不搬代码。
- ath12k 构建时拉取的 GPL-2.0 代码不能进要分发的内核。
- 对方脚本硬编码了家目录下的路径，移植时按 AGENTS.md §3 改成相对路径或参数。

## 8. 建议的下一批真机轮次

判据在读数之前登记。本批不刷写分区，按 AGENTS.md §5 最多 3 轮。

### 8.1 第 1 轮：时钟与应用异常文本

- 载荷：内核 `12377-cmd49`；userland 为当前提交加本文 §3.1 的两处改动。
- 启动参数加 `applog=1 applog_name=MobileSMS,KeyboardSettings,MobileSafari,com.apple.Safari`。
- 观测：SpringBoard 打开缩略图（`REDWOOD_THUMBS`，含 `res` 角色）；backboardd 的 `in` 缩略图看 `RGhA` 654x270 表面。
- 同一次开机内的对照（`tools/k90auto/respin.py`，`--env` 每次整体替换 `kern.redwood.env`）：先读一遍；再 `--env SpringBoard:REDWOOD_RESOLVE_BLIT=1 --restart SpringBoard` 读一遍；再 `--env backboardd:AIR_COARSE_DERIVATIVES=1 --restart SpringBoard backboardd` 读一遍。
- 判据：
  - 锁屏截图出现时间数字，且 backboardd 读到的 SDF 表面非空，记为时钟修好。
  - 关掉 resolve 改动后时钟消失，记为 resolve 是原因；关掉导数改动后时钟或玻璃变化，记为导数参与。
  - 三个应用里至少一个在日志里打出异常原因，记为异常文本可读。
  - 管线被拒次数与 `bo43` 对比，指针存储类为 0 记为指针槽改动生效。

### 8.2 第 2 轮：视第 1 轮结果

- 时钟仍不显示：backboardd 与 SpringBoard 都设 `CA_DISABLE_INLINE_SDFS=1`、`CA_DISABLE_TILE_SHADERS=1`、`CA_DISABLE_FILTER_MERGING=1`（SpringBoard 用 `JOB_ENV`），读法同上。
- 时钟已显示：按第 1 轮读到的异常文本处理应用黑屏。

### 8.3 第 3 轮：GPU 调频

- 内核加频率下限（342 MHz）、触摸窗口延长到 1.5 秒、过热时逐档下调，70/60 °C 阈值不变。
- 判据：翻页时 `tl:` 帧间隔的 P50/P95 与 `bo43` 对比；GPU 与 CPU 最高温度不超过护栏；`GPU at N MHz` 行里 160 MHz 的占比下降。

### 8.4 结果

- 第 1 轮（`bo44`、`bo45`）：时钟与异常文本两项判据都满足，见 §1。`bo44` 没有重编 AIR 库，`bo45` 才是有效读数。
- 第 2 轮改为验证系统盘补齐后应用能否打开（`bo46`）：应用进程正常运行，屏幕仍黑，原因见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §6。
- 第 3 轮（`bo47`）：GPU 调频改动对帧率没有影响，见 §3.8。
- 看门狗、DSU、`fastboot boot` 三项经用户同意后已实现，见 §5。

### 8.5 离线队列

glassref 移植；只清屏的通道与逐附件清屏；编码器级别的 LOD 范围；拷贝不等 GPU；链接函数 `groups`；纹理 swizzle；`newTextureLayoutWithDescriptor`；应用的 Metal 设备；`exec_env`/`exec_swap`。
