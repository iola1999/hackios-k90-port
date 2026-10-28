# UniXNU 工程组织与 K90 GPU 适配对照

核对日期：2026-10-25。本次阅读 UniXNU 的迁移、移植步骤、GPU 与 Metal 指南及 myron 设备页，并核对固定版本的构建解析器和社区 GPU 源码。本项目目标设备为 REDMI K90（`annibale`，SM8750，A830）；myron 对应 K90 Pro Max／Poco F8 Ultra（SM8850，相关驱动分支标注 A840）。本次只整理文档和源码对照，真机操作仍由当前实现工作负责。

## 1. 判断与建议

UniXNU 对配置归属、组件依赖、系统 ABI 和构建输出的组织值得参考。其格式 2 已有配置解析器、组件目录和按目标生成的构建树，能够让维护者在运行硬件前查看实际使用的源码与配置。本项目已经有设备配置、输入清单和分阶段验收，可以先在现有文件中明确这些关系，再评估更换构建体系的收益。

当前优先完成 A830 的 CP 初始化、命令完成、用户态 shader 与桌面绘制。UniXNU 的 Metal 前端适合作为后续候选；采用它需要同时处理 GPU 内核 ABI、Turnip、系统私有接口和显示集成。完整迁移还涉及 SM8750 共享支持、目标系统、预链接和固件交接，适合在独立工作目录评估，并与当前可启动配置比较。

myron 的 A8XX 改动可以帮助核对寄存器和后续提交逻辑。公开页面尚未提供板级文件、defconfig 和真机结果；本次核对的代码也保留了 A7XX 默认值及 sheng 平台依赖。当前 RAW131 复位仍需以 annibale 的驱动、固件和运行结果定位。

## 2. 核对范围与固定版本

| 来源 | 固定版本或页面 | 本次用途 |
|---|---|---|
| UniXNU 主仓库 | [`16e592a`](https://github.com/UniXNU/UniXNU/tree/16e592abee8a550dec8154ed1f38b5ebc4f16213) | 格式 2 解析、组件、OS profile 和文档 |
| 官方 GPU 内核驱动 | [Adreno740 `4e0314d`](https://github.com/UniXNU/Adreno740/tree/4e0314df8ad29d52f6fa3f9383a540adcd618b87) | A740／SM8550 的接口和依赖范围 |
| 官方 Metal 前端 | [AdrenoMetal `454ff2c`](https://github.com/UniXNU/AdrenoMetal/tree/454ff2ce83766ce7b3e0f355e83f1d72907708b3) | Metal、Turnip 和系统 ABI 范围 |
| myron 核心分支 | [`myron-next`，`5deb5ed`](https://github.com/zg7681/UniXNU-myron/tree/5deb5ed2205ad2ccc19b5169f943cb17eb7e35c3) | CPU affinity 补丁和原有组件组织 |
| myron GPU 分支 | [`a8xx`，`9f13d3c`](https://github.com/zg7681/NativeAdreno-myron/tree/9f13d3c1613cba441ae4e09ea03df0b9194328b4) | A8XX 寄存器、ring 和提交改动 |
| myron GPU 对照基线 | [`main`，`26220f1`](https://github.com/zg7681/NativeAdreno-myron/tree/26220f1ab79fec643517336fbd81574bd1e0d05a) | 区分 A8XX 新增内容与既有 A740 实现 |

用户提供的入口为[迁移设备适配](https://unixnu.com/zh/porting/migration)、[移植步骤](https://unixnu.com/zh/porting/steps)、[GPU 与 Metal](https://unixnu.com/zh/porting/gpu)和 [myron](https://unixnu.com/zh/devices/myron)。网页已通过浏览器读取，文档源码按主仓库上述提交保存。原始快照与网页内容放在 Git 忽略的 `docs/analysis/local/unixnu-engineering-20261025/`。NativeUfs-myron 本次仅核对设备页中的职责，未评审其实现。

## 3. 工程组织值得采用的内容

| UniXNU 的实际组织 | 对本项目的用途 | 建议采用方式 |
|---|---|---|
| ARM64、SoC、OS、设备四层配置 | 分清通用修改、SM8750 控制器、iOS ABI 与 annibale 板级参数 | 先给现有配置和源码注明归属；有第二个消费者再决定是否提取共享实现 |
| `components.toml` 记录仓库、提交、硬件、OS ABI、依赖、输出和运行时标识 | 选择 Metal 组件前即可核对 A740、17.7.11 和板级依赖 | 在本专题维护候选依赖及接口差异，实际引入后再加入构建配置 |
| `feeds.toml`、固定提交和本地覆盖 | 区分上游实现与本地实验输入 | 继续使用现有输入清单，记录实际提交、本地修改、固件哈希与构建来源 |
| `out/<device>/<os_profile>/<config>/` | 隔离补丁后的源码、配置和产物 | 版本迁移试验使用独立目录；当前容器构建继续按已有源码清单核对 |
| 每步给出前提、输出和完成条件 | 交接者能判断停止在哪一步、下一步缺什么 | 在现有操作手册和专题中补充缺失项，进度继续维护在总账 |

上述配置合并规则可在 [`scripts/unixnu/profiles.py`](https://github.com/UniXNU/UniXNU/blob/16e592abee8a550dec8154ed1f38b5ebc4f16213/scripts/unixnu/profiles.py) 中核对：依次读取 ARM64、SoC、OS 和设备配置，字典递归合并，其他值整体替换。因此组件、补丁、archive 和配置片段数组的覆盖值必须包含完整列表。输出路径由 [`scripts/unixnu/config.py`](https://github.com/UniXNU/UniXNU/blob/16e592abee8a550dec8154ed1f38b5ebc4f16213/scripts/unixnu/config.py) 按设备、OS profile 和 defconfig 生成。

组件名称还与来源仓库关联。[`scripts/unixnu/components.py`](https://github.com/UniXNU/UniXNU/blob/16e592abee8a550dec8154ed1f38b5ebc4f16213/scripts/unixnu/components.py) 只为匹配官方来源的组件处理旧名称别名。社区分支需要保留自己的来源和版本，按其实际接口选择。组件目录中的硬件与 OS 范围仍需与目标设备逐项核对。

本项目已有 [`annibale.conf`](../../hackios-xnu-kernel/common/devices/annibale.conf)、[`annibale.platform.c`](../../hackios-xnu-kernel/common/devices/annibale.platform.c)、XNU 补丁与设备调试清单。现阶段的主要收益是明确这些输入的关系，以及把生成 XNU ADT 的硬件描述与启动镜像使用的固件 DTB 分开记录。源文件、展开树、容器构建输入、payload 和设备日志的核对继续按[协作手册](../plan/debugging-and-collaboration.md)执行。

完整采用格式 2 前，需要审查匹配 SM8750 的 SoC 输入和组件配方，并准备匹配的 OS profile。指南的模板选用 SM8550 和 iPadOS 17.7.11，模板中的控制器资源、固件、OPP 与预链接输入都需要重新核对。

## 4. GPU 与 Metal 的复用前提

官方 [`components.toml`](https://github.com/UniXNU/UniXNU/blob/16e592abee8a550dec8154ed1f38b5ebc4f16213/components.toml) 将 Adreno740 的硬件范围记录为 A740／SM8550，AdrenoMetal 的 OS ABI 记录为 `ipados-17.7.11-21H461`，验证设备均为 sheng。其依赖包括 AdrenoFirmware、AdrenoPM4、ArmSmmu4K 和平台实现。GPU 指南同时要求板级时钟、电压、互连请求、保留内存和签名固件满足目标设备的前提。

[`NativeAdrenoGmuPlatform.h`](https://github.com/UniXNU/Adreno740/blob/4e0314df8ad29d52f6fa3f9383a540adcd618b87/NativeAdrenoGmuPlatform.h) 提供已映射 MMIO 窗口和时间服务适配，时钟、复位与电源由调用方准备。SM8550／sheng 的固件与投票实现可供阅读，A830 的相应输入仍取自 annibale 运行设备树、实际 KGSL 模块和固定厂商源码。

| 接入部分 | UniXNU 当前契约 | 本项目需要核对的工作 |
|---|---|---|
| 内核请求 | `NativeAdrenoABI.h` 的版本化记录，包含 Query、BO、Submit、WaitFence 和设备信息 | 当前 `RedwoodGPU` 使用 msm DRM 请求选择子；需明确保留哪套接口并逐项转换 |
| BO 与地址 | 句柄、IOVA、权限、CPU 映射 token、导入页和生命周期 | 核对地址宽度、页粒度、缓存方向、导入方归属及失败后保留规则 |
| 提交与完成 | queue、IB 列表、输入 fence、超时和返回 fence | 接到 A830 标准 HWSCHED context；分别验证提交应答、EOP、idle 和结果读回 |
| Metal 运行时 | AdrenoMetal、metal2vulkan、Turnip、IOGPUFamily 和 IOSurface ABI | 核对目标系统的设备发现、类布局、资源共享、sandbox 与 trust cache |
| 显示 | 完成帧复制或合成到 scanout，随后交换并回收 | 接到现有显示实现，分别检查内存图像、完成同步和物理画面 |

请求结构见 [`NativeAdrenoABI.h`](https://github.com/UniXNU/Adreno740/blob/4e0314df8ad29d52f6fa3f9383a540adcd618b87/NativeAdrenoABI.h)，本地请求转换见 [`redwood_drm.c`](../../hackios-xnu-userland/tools/mesa/redwood-drm/redwood_drm.c)。本地 `drmOpenWithType("msm")` 查找 `RedwoodGPU`，`drmIoctl` 将请求低字节传为外部方法选择子。接口接通后仍需验证内存可见性、完成和退出处理。

Metal 的运行时编译路径为 AIR → SPIR-V → NIR → IR3；AirNir 提供离线 AIR → NIR → IR3 工具。新文档报告 sheng 已预编译系统镜像中的 162 个 Metal 库，见[该次文档更新](https://github.com/UniXNU/UniXNU/commit/16e592abee8a550dec8154ed1f38b5ebc4f16213)。库预编译、具体 pipeline 变体、API 覆盖和交互耗时需要分别验收。

系统版本继续按[版本评估](../plan/2026-10-24-gpu-handoff.md#2-系统版本选择)处理：当前 iOS 16.5／XNU 8796 与 UniXNU 的 iPadOS 17.7.11／XNU 10063、预链接及页大小相关工作存在差异。后续应先选择具体系统并验证必要 ABI，再扩大 Metal 集成范围。

## 5. myron 的 A8XX 源码核对

设备页链接到社区仓库；实际 A8XX 改动位于 NativeAdreno-myron 的 `a8xx` 分支，默认 `main` 仍为 `26220f1`。本次与该基线逐文件比较，共 18 个文件变化，其中包含主机测试。以下判断来自源码阅读，相关测试本轮未运行。

[`NativeAdrenoChip.h`](https://github.com/zg7681/NativeAdreno-myron/blob/9f13d3c1613cba441ae4e09ea03df0b9194328b4/NativeAdrenoChip.h) 将代际寄存器位置集中到表中，ring、IRQ、timer 和 CP 初始化对象通过 `useChip` 选择。四类对象的初始表均为 A7XX；本次读取的驱动生产源码和核心仓库非子模块文件中，`NativeAdrenoChipA8xx` 的选择调用只见于测试。核心仓库的其他子模块未展开，外部板级集成仍需另行核对。

以下数值均为 GPU 寄存器的 dword 索引，MMIO 字节偏移需乘以 4：

| 项目 | myron A8XX 表 | 本地 A830 定义 |
|---|---|---|
| `CP_SQE_INSTR_BASE` | `0x0816` | `GEN8_CP_SQE_INSTR_BASE_LO = 0x816` |
| `RBBM_INT_0_STATUS` | `0x006a` | `GEN8_RBBM_INT_0_STATUS = 0x06a` |
| `RBBM_INT_0_MASK` | `0x0062` | `GEN8_RBBM_INT_0_MASK = 0x062` |
| `CP_INTERRUPT_STATUS_GLOBAL` | `0x08b5` | `GEN8_CP_INTERRUPT_STATUS_GLOBAL = 0x8b5` |

本地定义见 [`adreno8_gpu_private.h`](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_gpu_private.h)。这四项与社区表一致。表内的其他项仍按具体 GPU 和厂商定义核对。

[`NativeAdrenoCpInit.cpp`](https://github.com/zg7681/NativeAdreno-myron/blob/9f13d3c1613cba441ae4e09ea03df0b9194328b4/NativeAdrenoCpInit.cpp) 与本地 `adreno8_pm4_cp_init` 均生成 10 个 PM4 dword：`CP_THREAD_CONTROL` 参数为 `1 << 27`，`CP_ME_INIT` mask 为 `0x14b`，context 数为 3，错误检测为 `0x20000000`，operation mode 为 2，末项为 `1 << 31`。本地还要求 powerup 地址位于 32 位范围，myron 允许非零高位。两者对 32 位范围内的 powerup 地址生成的这些字段一致。

两者的提交方式不同。myron 的 `NativeAdrenoCpInit::run` 调用 `NativeAdrenoRing::submit`，ring 最终发布 `CP_RB_WPTR`；本地 [`adreno8_gpu_cp_init`](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_gpu.c) 经 `gpu_raw` 发出 HWSCHED RAW131，再检查应答与 idle。因此直接 ring 的调用和完成处理需要额外适配，当前 HFI 队列、固件资源和电源时钟检查仍须继续。

[`NativeAdrenoSubmit.cpp`](https://github.com/zg7681/NativeAdreno-myron/blob/9f13d3c1613cba441ae4e09ea03df0b9194328b4/NativeAdrenoSubmit.cpp) 的 `setContinuationThread(true)` 用于已拆分的 Turnip 用户命令缓冲：首段含 `CP_THREAD_CONTROL BOTH` 就选 BOTH，后续段选 BR。README 将使用条件限定为客户端未启用 concurrent binning。该选项默认关闭，针对用户态提交阶段；当前首次 CP 初始化尚未完成，调查优先级较低。

myron 的 [`native-smp-wide-affinity.patch`](https://github.com/zg7681/UniXNU-myron/blob/5deb5ed2205ad2ccc19b5169f943cb17eb7e35c3/patches/xnu/native-smp-wide-affinity.patch) 保留 MPIDR 的 Aff0～Aff2。本地 `machine_routines.c`、`start.s` 补丁已采用对应范围，双高性能核心的实测见[输入和绘制记录](../progress/2026-10-24-input-and-rendering.md)。该部分可作为已有修复的对照。

## 6. 对当前实现工作的输入

本次读取实现会话的近期更新，最新阶段 5 候选停止在电源请求验证：CX 写请求收到完成应答，随后 ARC 读取返回 selector 0，与请求的 3 不符；MX、PLL 和后续时钟配置均未写入。实现工作正在核对 ARC 读回语义和请求格式，本专题只记录该读取范围，后续状态由实现工作更新。此前已记录 START 与阶段 15／16 通过、RAW131 索引发布后复位，以及 `31979ad` 的 BO／标准 context／服务接入准备，见[恢复审查记录](../progress/2026-10-25-gpu-resume-review.md)。

值得提供给实现工作的内容为：

1. 继续按 annibale 的 KGSL、运行设备树和实际模块验证 GMU／HUB 电源、时钟，再重测 RAW131。UniXNU 的平台适配也要求调用方先准备这些条件，myron 本轮快照未提供可用于替换它们的 SM8750 板级流程。
2. 把 myron A8XX 表和 CP 初始化包作为固定版本对照。四项已核对的寄存器与 CP 包关键字段一致；后续检查围绕尚未确认的条件选择实验。
3. continuation thread 留待真实用户态 IB 与 Turnip 工作负载阶段检查，并同时核对 concurrent binning 和 HWSCHED context 的语义。
4. CP、zap、scratch 和标准 context 通过后，继续验证现有 `RedwoodGPU`、用户态 shader、像素读回和桌面；Metal 集成另行确定系统 ABI、内核接口和显示完成处理。

用户态最小验收继续复用已有 `/redwood/bin/gl_test 0 64 64`，记录实际 renderer、GL 错误、像素内容、fence 和故障恢复。Metal 阶段再增加设备发现、IOSurface、pipeline、首次编译与缓存后测量，维持[GPU 命令执行专题](2026-10-24-a830-command-startup.md)的阶段定义。

## 7. 后续评估与本次边界

工程整理先使用现有设备配置、输入清单、操作手册和总账，补充确实缺失的源码归属、版本与接口关系。进一步引入配置解析器或共享仓库前，应确认它能减少哪些重复输入、覆盖哪些实际目标，以及维护所需成本。

若后续选择完整迁移，先在独立目录准备 annibale 的 SoC／设备配置与固定 OS 输入，完成配置解析、硬件 DTB／ADT、内核预链接、固件与 payload 的主机检查；再按既有设备操作约定验证启动、显示和输入，最后比较 GPU 集成和交互结果。迁移操作前需要另行确定范围与验收条件。

本次完成网页与固定源码阅读、社区 GPU 分支差异及本地相关定义对照。尚未构建或运行 UniXNU、myron 和新 Metal 组件，未进行设备命令、系统迁移或上游合并。公开页面中的 sheng 和 myron 结论按其设备、版本和公布范围保留。
