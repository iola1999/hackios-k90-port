# GPU 计划（SM8750 / Adreno 830 "sun"）— 离线调研 2026-10

状态更新（2026-10-24）：用户已将交互卡顿和 GPU 加速列为当前重点。采样定位到 `softpipe` 软件着色器耗时；A830 的诊断阶段 1–15 已通过真机验证，包含 GMU 固件启动、HFI 2.7.1、频率／带宽表、CORE_FW_START 与最低档 DCVS 应答。Android 日志与厂商配置确认本机使用 `gen80000_*`，GMEM 为 12 MiB，先前按相似 chipid 选择 gen80200 的判断已修正。当前推进 GX、GPU 页表和命令处理器初始化，然后按 Metal→metal2vulkan→Turnip 路径接入硬件绘制。技术选择见[图形加速对照](../analysis/2026-10-24-metal-route.md)，分阶段结果见[GPU 初始化记录](../progress/2026-10-24-gpu-initialization.md)。下文的上游支持范围仍需按本机配置独立验证。

---

## 1. redwood（SM7375 / Adreno 642L≈a660）GPU 链路盘点

### 1.1 内核 `bsd/dev/redwood_adreno.c`：22 步上电阶梯 + 常驻服务
- **不是常规驱动，是步进式探测机**：`adreno=N` 执行步骤 1..N 后停；每步"先说再碰、读先于写、失败即止"，专为"hypervisor 不喜欢就静默复位"的真机环境设计。配套 loader 侧旁路日志（`bootcpu=N`、`adreno_pause/fine/watch`）。
- 阶梯主干：①GCC 时钟 + cmd_db 扫 RPMh 资源名（gfx.lvl/cx.lvl/mx.lvl）②qfprom 读 speed bin ③GPUCC ④CX GDSC 上电 ⑤时钟 + DFS 频率计数器实测 ⑥–⑦GMU/GBIF 寄存器 ⑧–⑨GPU-SMMU 识别 + CB ⑩GMU 内存读写自测 ⑪–⑫⑲ TZ（qcom_scm，GPU PAS 13）验签/加载 **a660_zap.mdt** ⑬自建 SMMU 页表（39-bit、3 级、4K 页、**单 ctx0 全局 aspace**）⑭灌 **a660_gmu.bin** ⑮放 GMU reset ⑯RPMh 链路 + HFI 队列 ⑰HFI 要表 + GX 上电（`adreno_speed=1..3` = speed bin）⑱GX CB + ring + **a660_sqe.fw** ⑳开 CP ㉑退出 secure ㉒三色填充直写面板（`MiniIOMobileFramebufferShow`）。
- **微码**：安卓 `/vendor/firmware/a660_{gmu.bin,sqe.fw,zap.mdt,zap.b00-02}` → boot image `fw-gpu/`（`userland/build.sh` 打包；缺则 "THE GPU IS NOT STARTED"）。
- boot-args 全集：`gpu=1`（开机点亮并常驻）、`adreno=N`、`adreno_only/skip/pause/fine/watch/return`、`adreno_keep=1`（做完 21 步不停电，交 RedwoodGPU 服务）、`adreno_blind/stream1`、`adreno_speed`、`gpu_recover=1`（挂死提交→GX 半区复位续命）、`gpu_log`、`gpu_va=0/1/2`（VA 描述/护栏页）、`gpu_cached`、`display_probe=1`。
- 地址分配器仿 msm：`msm_gem_get_iova` 语义，first-fit + coalesce（`gpu_free[1024]`），**所有 client 共享 ctx0** （一个程序 shader 能摸到别人的 buffer——driver 明确不防）。

### 1.2 `iokit/Kernel/RedwoodGPU.cpp`：msm DRM ioctl 伪装成 IOKit
- IOService `RedwoodGPU` + UserClient：**selector = Linux msm_drm 请求号**，结构体原样进出（GetParam 0x40 / GemNew 0x42 / GemInfo 0x43(MSM_INFO_GET_IOVA) / CpuPrep/Fini / GemSubmit 0x46 / WaitFence 0x47 / SubmitQueueNew 0x4a…）；`mmap()` → `clientMemoryForType`（buffer 句柄即 memory type）。**即 Mesa freedreno 原样能讲**。
- 额外一个非 Linux 请求：`surfaceBuffer()` —— **IOSurface 内存直接进 GPU**（iOS 无 fd 传递，用 sid 换）。
- buffer = 内核常驻内存挂进 GPU SMMU ctx0，write-combined；fence 无中断、轮询（5 次/ms）；CP_ALWAYS_ON_COUNTER 记提交耗时。

### 1.3 iOS 侧怎么被喂（关键结论）
- **Apple GPU HAL 整个绕开，不补丁、不替换**：IOGPU/AGXMetal* 不参与（实测对 IOAcceleratorES 用 Apple 的 type-1 open 得 `kIOReturnUnsupported`，路死）。
- 显示/共享缓冲：**MiniIOSurface.kext 替身**（iOS 16.5 用户态反推协议，选择子/结构布局照抄）+ **MiniIOMobileFramebuffer 替身**（swap=把图层像素 CPU 拷进 loader 留下的 fb，vsync=定时器）。
- **GL**：fork 的 Mesa gallium freedreno/ir3 编 darwin（`freedreno-darwin.patch`、`osmesa-es-profile`、3 个 ir3 补丁），libdrm 由 `tools/mesa/redwood-drm/redwood_drm.c` 桩替（IOServiceOpen→RedwoodGPU）。README 定案一句：**"OpenGL ES for CoreAnimation"** —— CA 渲进 IOSurface，MiniIMF 拷屏。App 的 GLES 也走这条（`src/eagl.c`+`redwood_gl.h`+`gl_osmesa.c`）。
- **Metal（进行中）**：`src/redwoodmetal.m` 用 `MTLAddDevice` 只测出 4 个必答方法注册 device（自声明类继承 `_MTLDevice`、`MTLDeviceSPI` 运行时 class_addProtocol 糊过 conformsToProtocol）；buffer=GEM+IOConnectMapMemory64；compute/render/depth/arg-buffer 编码器都有；shader 编译 = **AIR→NIR→ir3** 自研前端（`tools/mesa/air`，`libredwoodair.dylib`，`docs/air.md` 分别记录 456 模块中 321 个入口编译为机器码、30 个入口在旧设备 GPU 完成执行；K90 的 Metal 路径尚未实测）。iOS 16 的 metallib/用户态二进制不改。
- 用户态注入只有 libredwood{,-tweaks,-app}.dylib（SpringBoard 等杂症），**GPU 相关无 iOS 侧 patch**。

## 2. SM8750 / Adreno 830（gen8）与 a6xx 的破坏性差异

### 2.1 上游现状（实查）
- **torvalds/linux master 已有 a8xx**：`288a9320`（2025-11-18，"drm/msm/adreno: Introduce A8x GPU Support"，作者日期）+ 后续；`a8xx_gpu.c` 1372 行 + `a8xx_preempt.c`，**复用 a6xx 的 GMU/HFI/SCM 框架**（a6xx_gmu.c 里 a8xx 分支）。catalog `a8xx_gpus[]`：`0x44070001`(gen80100 fw，21MB GMEM，无 zap)、`0x44050a01`(gen80200 fw **+ gen80200_aqe.fw**，18MB GMEM，无 zapfw)、`0x44010000`(gen80300 fw，zap=gen80300_zap.mbn)。本机 DT 为 `qcom,chipid=0x44050000`、compatible `qcom,adreno-gpu-gen8-0-0`。本机 Android 日志和厂商 `adreno_gpu_core_gen8_0_0` 配置均选择 `gen80000_*`，不能从 chipid 的相似前缀推定固件兼容。
- **Mesa/freedreno a8xx（2026-10-23 两轮 GitLab API 实查 main=27.0.0-devel）：包含 A8xx Vulkan 与 GL 实现，K90 尚未实测**。turnip（已迁 `src/freedreno/vulkan`，tu 统一 CHIP 模板）A8XX 分岔密集（`tu_device_entrypoints_a8xx`、`CHIP >= A8XX` 的 viewport/blend/rast 发射），A8xx 修复提交持续到 2026-10-22；本次未取得 K90 的一致性测试与持续运行结果。上游 devinfo（`freedreno_devices.py`）收有 A8XX gen1/gen2 条目，chipid 勘误补丁（Rob Clark 48be91d1，随 25.3 分发）把我们这颗 **0x44050000** 修成 0xffff44050000 "Adreno (TM) 830"（另有 830v1=0x44050001/KGSL 口径）——归属坐实。社区栈 whitebelyash turnip/gen8（tu_v20.2 起）实测 Adreno 830 Vulkan 可跑，部分已上游化。**gallium GL 并非"零"**（大写串 grep 的假阴性）：`fd6_hw.h` 已 include `a8xx_enums/perfcntrs/descriptors.xml.h`；a6xx 路径已 CHIP 模板化并有 `CHIP >= A8XX` 运行时分支（2ee0a5e6 "Indirect buffer needs WFM on a8xx+" 2026-07-17、779cdb8e "Fix query barriers for gen8+" 2026-07-15）；a8xx devinfo 带 gallium gmem/BV 参数（`gmem_vpc_bv_pos_buf_size`）。这些代码确认实现存在，真机执行范围仍需独立验证。但**无 deqp/CI 农场佐证、无"GL gen8 完成"官方声明**，可用性未证实。当前 Mesa 已构建为 26.2.5；先完成 A830 内核提交，再优先评估 Metal→metal2vulkan→Turnip，现有 GLES 保留为验证与恢复路径。
- **固件来源**：已取得 linux-firmware 的 `gen80000_gmu.bin`、`gen80000_sqe.fw`、`gen80000_aqe.fw` 和 `qcom/sm8750/gen80000_zap.mbn`，保留许可、通知与文件哈希。版本来源和与手机固件的核对边界见 [固件说明](../../hackios-xnu-userland/firmware-gen8/README.md)。本机启动兼容性按分阶段实验验证。

### 2.2 gen8 相对 a6xx（redwood代码能直接复用的边界之外）
1. **寄存器访问范围**：gen8 的 pipe 和 aperture 选择按厂商 gen8.0.0 配置核对。先前从 gen80200 引入的 `CX_MISC_SLICE_ENABLE_FINAL` 读取已移除；本机 slice 拓扑待 GPU 提交阶段核对。
2. 3D 核外多 BV/BR 之外的新 CP pipe；性能计数器体系重做（PERFCTR_SRAM_INIT、SLICE_PERFCTR）。
3. **HFI 新增 perf_table 消息**（`a8xx_hfi_send_perf_table`），GMU 版本判定/芯片号写 GMU_GENERAL_8/9 变了。
4. **频率配置需区分 QFPROM `speed_bin`、`qcom,sku-codes` 和 CX_MISC 的 SW_FUSE_FREQ_LIMIT**。本机 DT 的 `speed_bin` 来自 `0x221c8138` 的低 9 位，32 位读取已返回 232；SKU 来自 socinfo 的 `feature_code/pcode`。当前尚未读取 SKU，启动只提供两套 DT 表共有的 125 MHz／0x32 电压级别。
5. **AQE 微码**：本机 gen80000 同时提供 AQE 和 SQE 固件；加载顺序及寄存器按厂商 gen8.0.0 实现核对。
6. preempt/上下文切换格式变：CP_CONTEXT_SWITCH_SMMU_INFO + preempt_level/SKIP_SAVE_RESTORE（PPT 机制仍在，但我们仍可用单 ctx0 绕过）。
7. LLC slice 编程（`a8xx_llc_activate`，llcc-qcom 接口）；GBIF halt 多一个 RBBM_GBIF_HALT；UBWC mode 5；厂商 gen8.0.0 配置的 GMEM 为 12 MiB。
8. **供电**：CX GDSC 挪进 gpucc 窗口（0x3d99080，非redwood的 gpucc+0x106c 语义映射）；**GX 域独立成 gxclkctl@3d68024**；RPMh 名 `gfx.lvl` 仍在（cmd-db **0x81c60000**+0x20000，redwood是 0x80860000，驱动本来就扫 SMEM 魔数，可移植）。好消息：GMU+HFI+RPMh+SCM 的"世界观"没变，redwood 22 步阶梯**结构**可平移，常数全换。

### 2.3 SM8750 GPU 地址表（拆自 /tmp/hw_check.dts，均安全可抄）
| 块 | 基址 | 大小 | 备注 |
|---|---|---|---|
| 3D core regs | 0x3d00000 | 0x40000 | 与redwood同基址 |
| RSCC | 0x3d50000 | 0x10000 | |
| cx_dbgc | 0x3d61000 | 0x3000 | |
| gxclkctl | 0x3d68024 | 0x8 | GX 电源域（新式） |
| GMU | 0x3d37000 | 0x68000 | `qcom,gen8-gmu`；AO 块 0x3d40000+0x10000 |
| cx_misc | 0x3d9e000 | 0x2000 | TCM retention 与 SW fuse；speed_bin 来自 QFPROM |
| GPUCC | 0x3d90000 | 0x9800 | `qcom,sun-gpucc`；vdd_cx/vdd_mx |
| CX GDSC | 0x3d99080 | 0x4 | hw_ctrl@0x3d99094 |
| GPU SMMU | 0x3da0000 | 0x40000 | qsmmu-v500+adreno-smmu，3 级表；ID 寄存器实测 CB0=0x3dc0000、CB1=0x3dc1000；SID：user 0 / lpac 1 / secure 2 / gmu 5 / gfx 7 |
| cmd-db | 0x81c60000 | 0x20000 | RPMh 资源表（gfx.lvl 在内） |
| 中断 | — | — | kgsl_3d0=GIC 300，cx_host=80，GMU hfi=304/gmu=305，SMMU 全局=674 |
- 本机 DT 包含多套 SKU 频率表；当前只使用共有的 125 MHz 点。zap-shader 有独立的 memory-region，实际认证与 secure 状态尚待验证。

## 3. iOS 侧兼容层判断（要不要动用户态）

| 目标 | iOS 16 用户态 | 实际工作量所在 |
|---|---|---|
| L1 2D 合成（blit 进 fb） | **不动**。MiniIOSurface/MiniIMF 协议不变，swap 从 CPU copy 换 GPU blit（内核里做） | 内核 GPU 底座 |
| L2 GLES 服务 | **基本不动**。CA/App 用被替换的 GL 库（osmesa/freedreno 路径），EAGL 垫片已是我们的 | **Mesa fork 认不认 A830/gen8（外部未知）** + RedwoodGPU 提交路径 gen8 化 |
| L3 Metal 全速 | **不动 Apple HAL**（本就被绕开，无需 AGX/IOGPU 进位）。redwoodmetal/air 前端硬件无关 | ir3 出 gen8 ISA（跟随 Mesa）+ 我们自己的提交/资源层 gen8 化 |

当前显示协议和用户态可继续使用已有实现；GPU 执行、Metal 接口和 shader 翻译分别验收。本机 `glDrawElements` 耗时约 0.3–1.9 秒，framebuffer copy 约 2–3 毫秒，下一阶段优先实现硬件渲染。具体采样方法和范围见[路径对照](../analysis/2026-10-24-metal-route.md)。

## 4. 当前实施顺序

| 阶段 | 内容 | 完成条件 |
|---|---|---|
| GMU 初始化 | 电源、时钟、SMMU、gen80000 固件、HFI 与供电表 | 各阶段回读通过，固件正常应答，退出后停止访问内存 |
| GPU 执行 | GX、GPU SMMU、zap 认证、SQE/AQE 与最小命令提交 | 离屏结果正确，fence 完成，异常可诊断和恢复 |
| Turnip 接入 | 复用现有 IOKit／缓冲接口，对照 NativeAdreno ABI 和 Mesa A830 参数 | 简单 Vulkan 任务在 K90 执行，结果与预期一致 |
| Metal 接入 | 对照 NativeMetal 与现有 redwoodmetal，评估 metal2vulkan 和缓存 | iOS 16.5 的代表性 Metal 渲染通过，并分别测量首次编译与缓存后耗时 |
| 桌面验证 | 接入合成和输入交互，保留软件绘制配置用于对照 | 滑动、应用打开、时钟动画延迟可测，持续运行可恢复 |

每阶段只增加已核对的硬件操作。真实固件、协议和地址映射先做主机边界测试，再进行真机验证。设备命令统一串行执行；其他任务可并行审阅独立模块。

GPU 执行阶段优先采用 gen8_0_0 厂商配置选择的 HWSCHED。普通 HFI 的初始化与最低档 DCVS 已取得 ACK，完整提交仍待验证；后续 START 内存请求、GPU 映射、SQE/AQE、CP 和 zap 顺序按[命令执行启动调研](../analysis/2026-10-24-a830-command-startup.md)推进。

## 5. 失败后的处理

先保留最后成功阶段、失败访问、原始日志和实际产物，再区分配置错误、固件响应、权限和资源状态。SMMU 关闭或 TLB 同步失败后保留映射内存，要求通过 loader 冷重启后再使用该内存。USB 可用就继续通过 USB 恢复；需要物理按键才联系用户。

某阶段失败后停止后续寄存器操作，核对厂商 gen8.0.0 与已验证输入。仅凭试验次数不能判定硬件不可用；继续调查应有能区分原因的新检查。

## 6. 尚待验证

- socinfo SKU 读取与完整频率表选择。
- host DDR 投票与 GMU PLL 时钟的独立初始化；当前沿用继承投票和 19.2 MHz 晶振。
- 普通 HFI 模式与 gen8_0_0 hwsched 路径的 GPU 提交兼容性；当前仅普通模式的初始化消息通过。
- GX、zap 认证、SQE/AQE、命令提交与 fence。
- A830 的 Mesa 设备参数、Turnip／Metal 接口和 iOS 16.5 桌面兼容性。
