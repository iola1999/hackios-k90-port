# K90 图形加速恢复工作计划

## 1. 暂停判断与目标

2026-10-24 用户确认可接受 iOS 17 或更新版本，并允许在剩余工作较多时整理后暂停。当前距离可用硬件加速仍有较大缺口，本轮暂停实现与真机实验。已实现内容、最后成功步骤、失败请求、产物及设备恢复状态见[HWSCHED 实测记录](../progress/2026-10-24-gpu-execution.md)；总状态只维护在[总账](2026-10-23-tracking.md)。

当前首次失败发生在 iOS 用户态启动之前：HWSCHED START 要求 kind 5 安全资源，分配器尚未实现。其后仍需验证 GPU 执行，再实现用户态提交与桌面合成。GMU 阶段数量无法用于估算完整图形栈的完成比例；尚无真实 GPU 命令耗时、渲染结果或帧率数据，暂不给完成百分比与固定工期。

完成目标是 K90 实际执行 shader，结果读回正确，桌面使用 GPU 绘制，触摸和动画延迟有测量结果，并能在故障后恢复。联网、摄像头、振动和充电标志继续按原有优先级留待交互可用后处理。

## 2. 系统版本选择

建议保留当前 iOS 16.5 作为硬件与用户态基础提交的验证环境；长期 Metal 路径先评估与 UniXNU 参考实现一致的 iPadOS 17.7.11（`iPad7,1`、`21H461`）。iOS 26/27 纳入后续候选，先检查系统移植条件，再决定是否采用。用户已放宽系统版本要求，后续无需以 16.5 为固定限制。

| 候选 | 已有依据 | 升级后的工作 |
|---|---|---|
| 当前 iOS 16.5 | K90 已进入桌面；触摸、按键、双高性能核心已验证；Mesa 26.2.5 已构建 | 完成 A830 内核服务即可测试现有 GLES/OSMesa 路径；NativeMetal 的私有接口仍需适配 |
| 参考目标 iPadOS 17.7.11 | UniXNU 的 sheng/A740 文档报告 Metal 桌面，NativeMetal 对应该系统布局 | 评估 K90 的 XNU、启动及显示与输入迁移；实现 A830 提交与 Darwin KMD 接口；验证 iPad 身份与手机界面需求 |
| iOS 26/27 | 用户允许采用；本项目尚无对应镜像、内核或 GPU 运行验证 | 先审查 Mach-O 架构、指针认证相关要求、XNU/IOKit、dyld、系统镜像、Metal 私有接口及 AIR 兼容范围，再与 17.7.11 路径比较 |

UniXNU 当前固定快照的 [sheng 配置](https://github.com/UniXNU/UniXNU/blob/1a01c2afa197d975d04da892325c56b6b14aaecb/docs/devices/sheng.md)使用 iPadOS 17.7.11。Turnip、Rust bridge、Metal 插件的构建目标均为 iOS 17.0；17.0 是 deployment target。NativeMetal 还在运行期检查 [`_MTLDevice` 的实例大小必须为 536](https://github.com/UniXNU/NativeMetal/blob/c6d29caad6d880cc8204ebe3bc34d77479a3255d/NativeBridgeMetalFrontend.mm#L1559-L1560)，注释明确对应 iPadOS 17.7.11。当前核对未取得所有 iOS 17+ 版本的兼容结果。

选择参考系统可能减少 16.5 的 Metal SPI 与 AIR 兼容工作，收益仍需代表性样本验证。系统升级无法消除当前的 HWSCHED 安全资源缺口，也无法替代 A830 页表、命令提交、fence、IOSurface 共享及故障恢复。更新系统本身不会提供 K90 的 GPU 驱动。

UniXNU 的[内核构建说明](https://github.com/UniXNU/UniXNU/blob/1a01c2afa197d975d04da892325c56b6b14aaecb/docs/guide/build-kernel.md)固定 XNU `10063.141.1`、Darwin 23.6.0 和 4 KiB 页，并预链接原版 kernelcache。本项目当前使用 XNU `8796.121.2` 和 16 KiB 页。完整采用该启动方式涉及内核、预链接、平台驱动和系统镜像，需作为独立移植任务评估。优先复用已经需要的图形组件，暂不整体替换已工作的启动环境。

## 3. 恢复后的阶段与验收

| 阶段 | 工作 | 独立验收条件 | 当前状态 |
|---|---|---|---|
| HWSCHED 完整启动 | 安全内存归属、SID2 独立映射、SCM 参数内存与 QTEE bridge 前提 | kind 5 获得符合归属要求的地址；START 最终 ACK；错误后保留资源并能 USB 重启 | 当前阻塞项；协议已解析，实际分配未实现 |
| GPU 首次执行 | GPU CB0、OOB、寄存器与 SQE/AQE、CP 初始化、zap 认证和 secure exit | CP 初始化和空闲检查通过；scratch 内容正确；无新增 SMMU fault | 已写代码并通过主机测试，未真机执行 |
| 用户态绘制 | BO/VA 生命周期、提交上下文、fence、CPU/GPU 缓存同步、Mesa A830 参数 | 用户态 shader 在 A830 执行，renderer、GL 错误与像素读回均正确；异常提交可停止并恢复 | 现有 RedwoodGPU 仍调用旧硬件后端，新后端未接入 |
| 当前桌面加速 | IOSurface 导入、合成提交、完成同步与显示 | 壁纸、半透明、时钟、滑动和应用切换可测；比较 softpipe、首次编译与缓存后耗时 | 未实现 |
| Metal 与版本迁移 | 固定目标系统、Turnip Darwin KMD、NativeMetal、metal2vulkan、着色器缓存 | 代表性系统 AIR 与 Metal 渲染通过；桌面合成及资源同步正确；再扩大 API 覆盖 | 已调研，未集成 |

scratch 写回只验证命令执行与内存可见性，后续仍需 shader 渲染。用户态最小测试优先复用现有 `/redwood/bin/gl_test 0 64 64`，同时检查实际 renderer、错误和像素，不能仅按进程退出码判定成功。采用现有 GLES 路径可以先验证 A830 服务，长期方向继续评估 Metal→metal2vulkan→Turnip。

## 4. 第一阶段的实现边界

恢复工作先阅读[HWSCHED 实测记录第 4 节](../progress/2026-10-24-gpu-execution.md#4-安全资源的下一步)，核对固定版本厂商源码与实际设备状态。下一次真机实验仍止于第 14 阶段；START 完成后再逐步增加后续阶段。

- 明确 QTEE bridge 是否已启用以及扩展参数区的注册要求，补充 MP_ASSIGN 所需参数布局、返回状态和 WAITQ/EBUSY 处理。失败保持资源，禁止继续后续初始化。
- 先检查 SID2/CB3 候选资源占用，在尚未启用的地址空间完成页表共享与映射，再移交数据页。移交后不再从 CPU 读取、清零或发布该数据区。
- 复用现有按 `(kind, handle)` 索引的分配记录与总预算，仅增加已观测到的 kind 5/flags `0x1007`。完成安全归属与映射后才设置 `result.secure=true`。
- 数据页、页表和 SCM 元数据分别记录生命周期。任何部分成功后的错误都保留资源至冷重启；完整关闭尚未验收，当前阶段不增加取消归属或回收路径。
- 先以主机测试覆盖物理不连续、页大小、参数边界、部分移交失败和重复请求，再做真机测试。每轮记录实际固件、内核与 payload 哈希。

## 5. 提交接口与 Metal 的取舍

当前 Mesa 26.2.5 已包含 Freedreno/A8xx 路径；已构建的 OSMesa 可选择 GPU 或 softpipe。`RedwoodGPU.cpp` 与 `redwood-drm` 仍调用旧 `redwood_gpu_*` 服务。最小 A830 用户态实现要提供 BO 分配、映射、导入和释放，提交与 fence，以及 chipid、12 MiB GMEM、GMEM base `0x04000000`、HBB 16 等对应参数。具体接口复用范围以调用方为准，避免同时维护两套等价的内存与任务状态。

厂商 `ISSUE_CMD_RAW` 已用于 CP 初始化和退出 secure mode。普通用户任务使用注册上下文、上下文指针及 `ISSUE_CMD`；RAW 是否适合持续渲染尚未验证。scratch 成功后，应按标准用户任务提交验证 IB 与 fence，不能仅扩大 RAW 消息代替整个提交服务。

UniXNU 的 Turnip Darwin 补丁使用 `NativeAdrenoABI`，本项目使用 msm DRM 风格的 IOKit 选择子。长期接入前先列出 BO、IOSurface、提交、等待及错误码的实际消费者，再选择一个内核资源所有者与对应适配位置。当前构建的 OSMesa 未包含 Turnip Vulkan；更换系统版本后仍需构建并连接这些组件。

完整调频、GMU PLL、主机 DDR 投票、RSC 关闭、设备内部故障恢复与长期运行均有缺口。当前验证只使用最低频率点、19.2 MHz GMU 时钟和继承的 DDR 投票。首次正确渲染后分别测量与处理，不能提前承诺最终帧率。

## 6. 交接与恢复入口

- 设备留在已验证可启动的 iOS 16.5 配置，当前为软件绘制。重新接手先读[真机手册](device-test-playbook.md)，查询 USB 与运行状态；不依赖暂停时的画面推断当前状态。
- 当前源码通过主机检查和构建；`handoff-mach-gpu-pause` 尚未真机执行，安全分配仍缺失。已测产物与最新构建分别保存在实测记录和本地 manifest。
- 原始日志、截图、源码副本与产物清单位于忽略目录 `docs/progress/evidence/2026-10-24-gpu-execution/`。交接时内核提交为 `57066c7`，父仓提交为 `89a93c3`，后续文档变更仍在工作树；推送状态未核对。共享工作树中其他任务的修改需要继续保留。
- 恢复后由一个任务管理 USB 与共享内核构建；可并行安排安全内存实现审阅、用户态接口研究和系统版本兼容检查。各任务分别交付来源、改动与未验证条件，由设备负责人串行整合。
- 本轮已经暂停，无后台 GPU 实验或后续自动执行安排。恢复指令可直接要求从 kind 5 安全资源开始，沿本页验收顺序推进。
