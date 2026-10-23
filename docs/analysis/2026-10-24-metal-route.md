# K90 图形加速路径与 UniXNU 对照

本次核对日期为 2026-10-24。用户要求优先解决交互卡顿，并提供 UniXNU 项目作为技术选型参考。本文记录公开源码、本机采样及下一阶段的选择，K90 尚未运行 UniXNU 的 Metal 实现。

## 1. 当前卡顿的测量结果

K90 当前桌面通过 `eagl.c → OSMesa → softpipe` 绘制。五颗 CPU 在线的一轮中，`backboardd` 在连续两个 5 秒采样窗口分别占用约 90.3% 和 88.8% 的单核 CPU 时间。逐调用日志记录多次 `glDrawElements` 耗时 0.3–1.9 秒；另一轮最大值为 1,756,698 微秒。相同阶段帧缓冲上屏平均约 2–3 毫秒。各项属于不同采集窗口，不能合成为固定帧率或完整延迟分解。

临时诊断库用 `dladdr(OSMesaCreateContextAttribs)` 取得实际加载地址，再用对应未裁剪符号的 Mesa 二进制解析显示线程采样。17 个有效 PC 分别落在 `_fetch_source`、`_exec_vector_binary`、`_exec_tex`、`_tgsi_exec_machine_run`、`_store_dest`、`_fetch_texel_offsets`、`_fetch_src_file_channel`、`_exec_vector_trinary`、`_sp_tgsi_get_samples`。内核采集的是线程最近保存的用户寄存器，统计范围限于这段采样；结合进程 CPU 时间和慢调用日志，当前主要耗时可定位到软件着色器执行和纹理采样。

原始文件为本地调试目录中的 `input-confirmed.log`、`profile-live.log`、`gl-profile-live.log`、`profile-symbolized.txt`。正常镜像保留原 Mesa 库，临时诊断库仅用于定位地址。增加 CPU 数量和修正高性能核心映射均未消除软件绘制长耗时。

## 2. UniXNU 的公开实现

本次读取的版本为 [UniXNU `1a01c2a`](https://github.com/UniXNU/UniXNU/tree/1a01c2afa197d975d04da892325c56b6b14aaecb)、[NativeMetal `c6d29ca`](https://github.com/UniXNU/NativeMetal/tree/c6d29caad6d880cc8204ebe3bc34d77479a3255d)、[NativeAdreno `b686b90`](https://github.com/UniXNU/NativeAdreno/tree/b686b9054f57d393c80195b82568a09f8ca106a2)。仓库快照仅下载到本地调研目录，尚未纳入本项目依赖。

其[驱动说明](https://unixnu.com/drivers/native-adreno)报告 Xiaomi Pad 6S Pro（sheng，Adreno 740）已通过 Metal 合成桌面。公开代码将职责分为以下几层：

| 层次 | 实现与职责 |
|---|---|
| Metal 对象与系统发现 | NativeMetal 通过 `MTLAddDevice` 发布设备，处理编码器、资源、IOSurface、同步与缓存 |
| 着色器转换 | metal2vulkan 读取 AIR，生成 SPIR-V；Turnip 经 NIR 编译为 Adreno IR3 指令 |
| GPU 内核服务 | NativeAdreno 管理 BO、GPU 地址、SMMU、GMU、命令环和 fence |
| 显示提交 | GPU 复制或合成到 scanout，NativeMobileDisplay 管理交换和完成 |

NativeMetal 的 README 明确保留首次着色器编译较慢、预编译 UI 集合尚不完整的限制。驱动文档的一轮记录为 103 个 Metal pipeline 共 40.1 秒，单个最大 1.40 秒，并提供缓存导出、导入和编译记录。该项目报告的桌面可用范围属于 A740；本次没有在其设备上复测帧率、输入延迟或完整 API 覆盖。

## 3. 对本项目的影响

OpenGL ES 和 Metal 都可以由 GPU 执行。当前严重卡顿对应 CPU 上的 `softpipe`，图形 API 名称本身无法说明是否有硬件加速。UniXNU 提供了可复用的 Metal 前端、着色器转换与缓存实现，值得优先验证其与本项目 iOS 16.5 的兼容性。

Apple 已从 iOS 12 开始弃用 OpenGL ES，并[建议使用 Metal](https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/OpenGLES_ProgrammingGuide/Introduction/Introduction.html)。采用 Metal 前端可以提供系统和应用所需的 Metal 接口；具体 API、资源同步和着色器兼容范围仍需逐项验证。Turnip 的 Vulkan 驱动负责生成 GPU 工作，额外的 AIR→SPIR-V 编译开销需要通过首次运行与缓存后运行的分别测量评估。

本仓库已经有 [`redwoodmetal.m`](../../hackios-xnu-userland/userland/src/redwoodmetal.m) 和 AIR→NIR→IR3 实现，详见 [`docs/air.md`](../../hackios-xnu-userland/docs/air.md)。其中的旧设备实测、离线编译和 K90 验收分别记录；K90 当前运行的桌面仍使用 GLES 软件路径。

| 路径 | 已有基础 | 当前用途与剩余工作 |
|---|---|---|
| GLES→freedreno→A830 | 现有 EAGL 接入和 Mesa Darwin 支持 | 可保留为 GPU 基础绘制和回归对照；A830 内核提交仍需实现并验证 |
| Metal→本仓 AIR→NIR→IR3 | 已有 Metal 对象和着色器前端 | 保留已验证部分，核对系统 API、着色器、同步和 A830 适配范围 |
| Metal→metal2vulkan→Turnip→A830 | UniXNU 已公开 A740 桌面路径 | 优先评估的长期方向；需要 iOS 16.5 接口验证、Turnip 内核接口适配及 A830 真机结果 |

NativeAdreno 当前针对 A740。K90 的 GPU 电源、固件、GMU/HFI、SMMU 和命令处理器初始化仍需按 SM8750/A830 验证。UniXNU 的 Turnip Darwin 补丁使用 `NativeAdrenoABI.h`，本仓库的 `RedwoodGPU` 使用 msm DRM 风格选择子；两者的服务发现、BO 导入、提交和 fence 契约需要逐项对接。直接替换动态库无法完成这些工作。

## 4. 下一阶段顺序

2026-10-24 后续用户允许升级至 iOS 17 或更新版本，并同意整理后暂停。NativeMetal 固定快照的实际目标为 iPadOS 17.7.11，包含 `_MTLDevice` 实例大小检查；17.0 是构建部署目标。系统版本取舍和恢复工作顺序以[暂停计划](../plan/2026-10-24-gpu-handoff.md)为准，当前 iOS 16.5 保留为硬件与 GLES 验证环境。

1. 完成 A830 底层初始化和恢复检查，再验证命令提交、fence、离屏绘制与读回。这些工作同时服务 GLES 和 Metal。
2. 使用本机 iOS 16.5 的原始 QuartzCore AIR 验证 metal2vulkan、Turnip 编译、资源绑定和必要的 Metal API；保留具体成功项和失败项。
3. 接入 IOSurface、同步和桌面显示，验证壁纸、半透明、时钟、滑动、应用切换及持续运行。
4. 分别测量首次编译、缓存后运行、逐帧绘制和输入到显示延迟，再决定是否替换当前默认路径。

当前选择是继续推进 A830 硬件驱动，并优先评估 UniXNU 的 Metal→Turnip 路径。现有 GLES 实现保留为对照和恢复入口；现阶段没有导入新的大型运行时，也没有删除已有 Metal 实现。
