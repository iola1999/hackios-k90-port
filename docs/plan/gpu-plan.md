# GPU 计划（SM8750 / Adreno 830 "sun"）— 离线调研 2026-10

状态：调研文档。porting-plan.md 里 "GPU 加速维持不做" 维持不变；本文回答"将来要做时，从哪切、要什么、坑在哪"。
输入：redwood_adreno.c（4125 行）、RedwoodGPU.cpp（1295 行）、MiniIOSurface/MiniIOMobileFramebuffer、
hackios-xnu-userland tools/mesa（air/freedreno 补丁）、/tmp/hw_check.dts（本机 DT 实拆）、
torvalds/linux master（gh api 实查，当前 v7.3）。Mesa/linux-firmware 已于
2026-10-23 在线复核完毕（GitLab API），结论见 §2.1——原"最大外部未知"已收敛。

---

## 1. 红杉（SM7375 / Adreno 642L≈a660）GPU 链路盘点

### 1.1 内核 `bsd/dev/redwood_adreno.c`：22 步上电阶梯 + 常驻服务
- **不是常规驱动，是步进式探测机**：`adreno=N` 执行步骤 1..N 后停；每步"先说再碰、读先于写、失败即止"，
  专为"hypervisor 不喜欢就静默复位"的真机环境设计。配套 loader 侧旁路日志（`bootcpu=N`、`adreno_pause/fine/watch`）。
- 阶梯主干：①GCC 时钟 + cmd_db 扫 RPMh 资源名（gfx.lvl/cx.lvl/mx.lvl）②qfprom 读 speed bin
  ③GPUCC ④CX GDSC 上电 ⑤时钟 + DFS 频率计数器实测 ⑥–⑦GMU/GBIF 寄存器 ⑧–⑨GPU-SMMU 识别 + CB
  ⑩GMU 内存读写自测 ⑪–⑫⑲ TZ（qcom_scm，GPU PAS 13）验签/加载 **a660_zap.mdt** ⑬自建 SMMU 页表
  （39-bit、3 级、4K 页、**单 ctx0 全局 aspace**）⑭灌 **a660_gmu.bin** ⑮放 GMU reset ⑯RPMh 链路 + HFI 队列
  ⑰HFI 要表 + GX 上电（`adreno_speed=1..3` = speed bin）⑱GX CB + ring + **a660_sqe.fw** ⑳开 CP ㉑退出 secure
  ㉒三色填充直写面板（`MiniIOMobileFramebufferShow`）。
- **微码**：安卓 `/vendor/firmware/a660_{gmu.bin,sqe.fw,zap.mdt,zap.b00-02}` → boot image `fw-gpu/`（`userland/build.sh` 打包；缺则 "THE GPU IS NOT STARTED"）。
- boot-args 全集：`gpu=1`（开机点亮并常驻）、`adreno=N`、`adreno_only/skip/pause/fine/watch/return`、
  `adreno_keep=1`（做完 21 步不停电，交 RedwoodGPU 服务）、`adreno_blind/stream1`、`adreno_speed`、
  `gpu_recover=1`（挂死提交→GX 半区复位续命）、`gpu_log`、`gpu_va=0/1/2`（VA 描述/护栏页）、`gpu_cached`、`display_probe=1`。
- 地址分配器仿 msm：`msm_gem_get_iova` 语义，first-fit + coalesce（`gpu_free[1024]`），**所有 client 共享 ctx0**
  （一个程序 shader 能摸到别人的 buffer——driver 明确不防）。

### 1.2 `iokit/Kernel/RedwoodGPU.cpp`：msm DRM ioctl 伪装成 IOKit
- IOService `RedwoodGPU` + UserClient：**selector = Linux msm_drm 请求号**，结构体原样进出
  （GetParam 0x40 / GemNew 0x42 / GemInfo 0x43(MSM_INFO_GET_IOVA) / CpuPrep/Fini / GemSubmit 0x46 / WaitFence 0x47 / SubmitQueueNew 0x4a…）；
  `mmap()` → `clientMemoryForType`（buffer 句柄即 memory type）。**即 Mesa freedreno 原样能讲**。
- 额外一个非 Linux 请求：`surfaceBuffer()` —— **IOSurface 内存直接进 GPU**（iOS 无 fd 传递，用 sid 换）。
- buffer = 内核常驻内存挂进 GPU SMMU ctx0，write-combined；fence 无中断、轮询（5 次/ms）；CP_ALWAYS_ON_COUNTER 记提交耗时。

### 1.3 iOS 侧怎么被喂（关键结论）
- **Apple GPU HAL 整个绕开，不补丁、不替换**：IOGPU/AGXMetal* 不参与（实测对 IOAcceleratorES 用 Apple 的
  type-1 open 得 `kIOReturnUnsupported`，路死）。
- 显示/共享缓冲：**MiniIOSurface.kext 替身**（iOS 16.5 用户态反推协议，选择子/结构布局照抄）+
  **MiniIOMobileFramebuffer 替身**（swap=把图层像素 CPU 拷进 loader 留下的 fb，vsync=定时器）。
- **GL**：fork 的 Mesa gallium freedreno/ir3 编 darwin（`freedreno-darwin.patch`、`osmesa-es-profile`、3 个 ir3 补丁），
  libdrm 由 `tools/mesa/redwood-drm/redwood_drm.c` 桩替（IOServiceOpen→RedwoodGPU）。README 定案一句：
  **"OpenGL ES for CoreAnimation"** —— CA 渲进 IOSurface，MiniIMF 拷屏。App 的 GLES 也走这条（`src/eagl.c`+`redwood_gl.h`+`gl_osmesa.c`）。
- **Metal（进行中）**：`src/redwoodmetal.m` 用 `MTLAddDevice` 只测出 4 个必答方法注册 device（自声明类继承 `_MTLDevice`、
  `MTLDeviceSPI` 运行时 class_addProtocol 糊过 conformsToProtocol）；buffer=GEM+IOConnectMapMemory64；compute/render/depth/arg-buffer
  编码器都有；shader 编译 = **AIR→NIR→ir3** 自研前端（`tools/mesa/air`，`libredwoodair.dylib`，air.md：456 模块语料 321 出码、
  README 口径 **293/456 系统 shader 已在 Adreno 跑通**）。iOS 16 的 metallib/用户态二进制不改。
- 用户态注入只有 libredwood{,-tweaks,-app}.dylib（SpringBoard 等杂症），**GPU 相关无 iOS 侧 patch**。

## 2. SM8750 / Adreno 830（gen8）与 a6xx 的破坏性差异

### 2.1 上游现状（实查）
- **torvalds/linux master 已有 a8xx**：`288a9320`（2025-11-18，"drm/msm/adreno: Introduce A8x GPU Support"，
  作者日期）+ 后续；`a8xx_gpu.c` 1372 行 + `a8xx_preempt.c`，**复用 a6xx 的 GMU/HFI/SCM 框架**（a6xx_gmu.c 里 a8xx 分支）。
  catalog `a8xx_gpus[]`：`0x44070001`(gen80100 fw，21MB GMEM，无 zap)、`0x44050a01`(gen80200 fw **+ gen80200_aqe.fw**，18MB GMEM，无 zapfw)、
  `0x44010000`(gen80300 fw，zap=gen80300_zap.mbn)。⚠️ 本机 DT `qcom,chipid=0x44050000`（"Adreno830"，compatible
  `qcom,adreno-gpu-gen8-0-0`）——**不在上游 chip_ids 列表**，需自证与 gen80200 家族（0x4405xx）的关系并自扩 catalog / 自备固件命名。
- **Mesa/freedreno a8xx（2026-10-23 两轮 GitLab API 实查 main=27.0.0-devel）：Vulkan 成熟、GL 已起步但未证实可用**。
  turnip（已迁 `src/freedreno/vulkan`，tu 统一 CHIP 模板）A8XX 分岔密集（`tu_device_entrypoints_a8xx`、
  `CHIP >= A8XX` 的 viewport/blend/rast 发射），A8xx 修复提交一直到 2026-10-22 还在进——**生产可用级**。
  上游 devinfo（`freedreno_devices.py`）收有 A8XX gen1/gen2 条目，chipid 勘误补丁（Rob Clark 48be91d1，随 25.3 分发）
  把我们这颗 **0x44050000** 修成 0xffff44050000 "Adreno (TM) 830"（另有 830v1=0x44050001/KGSL 口径）——归属坐实。
  社区栈 whitebelyash turnip/gen8（tu_v20.2 起）实测 Adreno 830 Vulkan 可跑，部分已上游化。
  **gallium GL 并非"零"**（大写串 grep 的假阴性）：`fd6_hw.h` 已 include `a8xx_enums/perfcntrs/descriptors.xml.h`；
  a6xx 路径已 CHIP 模板化并有 `CHIP >= A8XX` 运行时分支（2ee0a5e6 "Indirect buffer needs WFM on a8xx+" 2026-07-17、
  779cdb8e "Fix query barriers for gen8+" 2026-07-15）；a8xx devinfo 带 gallium gmem/BV 参数（`gmem_vpc_bv_pos_buf_size`）
  ——说明有人在 a8xx 上真跑 GL。但**无 deqp/CI 农场佐证、无"GL gen8 完成"官方声明**，可用性未证实。
  **红杉栈（gallium GL）对应动作：先把 fork rebase 到 26/27 实测 GLES on a830（成本≈1 个离线轮），
  不通再转 turnip+GL-over-Vulkan 桥（备选路线，风险从"外部未知"变"可控工时"）。**
- **固件零风险（linux-firmware gitlab 镜像实查）**：`qcom/gen80000|80100|80200|81100`
  的 `_gmu.bin/_sqe.fw/_aqe.fw` 都在库上——**不需要真机 dump vendor 分区**，L1a
  的固件匹配风险降级（0x44050000 家族取 gen80200 三件套起步）。

### 2.2 gen8 相对 a6xx（红杉代码能直接复用的边界之外）
1. **Slice 架构**：GPU 内多 "slice"（mini-GPU）；寄存器访问要经 **CP_APERTURE_CNTL_HOST 选 pipe+slice**
   （`a8xx_write_pipe`），红杉式"直写寄存器"心智模型全变。slice 使能读 CX_MISC_SLICE_ENABLE_FINAL。
2. 3D 核外多 BV/BR 之外的新 CP pipe；性能计数器体系重做（PERFCTR_SRAM_INIT、SLICE_PERFCTR）。
3. **HFI 新增 perf_table 消息**（`a8xx_hfi_send_perf_table`），GMU 版本判定/芯片号写 GMU_GENERAL_8/9 变了。
4. **speed bin 从 CX_MISC SW_FUSE_FREQ_LIMIT 寄存器读**（qfprom 直读没了；DT 侧是 nvmem-cell `speed_bin`）。红杉 step2 的 qfprom 读法要换。
5. **AQE 微码**（gen80200）：CP 引导多一个固件对象；SQE 加载寄存器名不同（CP_SQE_INSTR_BASE/CP_SQE_CNTL 尚可对照）。
6. preempt/上下文切换格式变：CP_CONTEXT_SWITCH_SMMU_INFO + preempt_level/SKIP_SAVE_RESTORE（PPT 机制仍在，但我们仍可用单 ctx0 绕过）。
7. LLC slice 编程（`a8xx_llc_activate`，llcc-qcom 接口）；GBIF halt 多一个 RBBM_GBIF_HALT；UBWC mode 5；GMEM 18MB。
8. **供电**：CX GDSC 挪进 gpucc 窗口（0x3d99080，非红杉的 gpucc+0x106c 语义映射）；**GX 域独立成 gxclkctl@3d68024**；
   RPMh 名 `gfx.lvl` 仍在（cmd-db **0x81c60000**+0x20000，红杉是 0x80860000，驱动本来就扫 SMEM 魔数，可移植）。
   好消息：GMU+HFI+RPMh+SCM 的"世界观"没变，红杉 22 步阶梯**结构**可平移，常数全换。

### 2.3 SM8750 GPU 地址表（拆自 /tmp/hw_check.dts，均安全可抄）
| 块 | 基址 | 大小 | 备注 |
|---|---|---|---|
| 3D core regs | 0x3d00000 | 0x40000 | 与红杉同基址 |
| RSCC | 0x3d50000 | 0x10000 | |
| cx_dbgc | 0x3d61000 | 0x3000 | |
| gxclkctl | 0x3d68024 | 0x8 | GX 电源域（新式） |
| GMU | 0x3d37000 | 0x68000 | `qcom,gen8-gmu`；AO 块 0x3d40000+0x10000 |
| cx_misc | 0x3d9e000 | 0x2000 | speed bin / slice enable 在这 |
| GPUCC | 0x3d90000 | 0x9800 | `qcom,sun-gpucc`；vdd_cx/vdd_mx |
| CX GDSC | 0x3d99080 | 0x4 | hw_ctrl@0x3d99094 |
| GPU SMMU | 0x3da0000 | 0x40000 | qsmmu-v500+adreno-smmu，3 级表；CB0≈0x3da1000；SID：user 0 / lpac 1 / secure 2 / gmu 5 / gfx 7 |
| cmd-db | 0x81c60000 | 0x20000 | RPMh 资源表（gfx.lvl 在内） |
| 中断 | — | — | kgsl_3d0=GIC 300，cx_host=80，GMU hfi=304/gmu=305，SMMU 全局=674 |
- 本 bin GPU 频率表 27 档，最高 `0x35a4e900`=900 MHz；zap-shader 有 memory-region（gen80200 上游无 zapfw——真机 secure 状态待验，见 §5）。

## 3. iOS 侧兼容层判断（要不要动用户态）

| 目标 | iOS 16 用户态 | 实际工作量所在 |
|---|---|---|
| L1 2D 合成（blit 进 fb） | **不动**。MiniIOSurface/MiniIMF 协议不变，swap 从 CPU copy 换 GPU blit（内核里做） | 内核 GPU 底座 |
| L2 GLES 服务 | **基本不动**。CA/App 用被替换的 GL 库（osmesa/freedreno 路径），EAGL 垫片已是我们的 | **Mesa fork 认不认 A830/gen8（外部未知）** + RedwoodGPU 提交路径 gen8 化 |
| L3 Metal 全速 | **不动 Apple HAL**（本就被绕开，无需 AGX/IOGPU 进位）。redwoodmetal/air 前端硬件无关 | ir3 出 gen8 ISA（跟随 Mesa）+ 我们自己的提交/资源层 gen8 化 |

结论：三级都**不需要**给 iOS 16 打 GPU 补丁；风险全在我们内核↔Mesa↔硬件这条线。红杉已证明"CA 用 GLES 渲、CPU 拷屏"能撑起锁屏到日常 UI；2D 合成提速优先把 MiniIMF swap 的拷贝换成 GPU blit（红杉尚未做这步，`MiniIOMobileFramebufferShow` 仍是 CPU）。

## 4. 最小可行路线（分级）

| 级 | 内容 | 工作量 / 盲写比例 | 真机窗口 | 风险 |
|---|---|---|---|---|
| **L0** | 维持软渲染（现状）。GPU 不碰 | 0 | 0 | 无（perf 差是已知税） |
| **L1a** | gen8 上电阶梯：平移红杉步进机（adreno=1..21 语义），地址表 §2.3，寄存器语义抄上游 a8xx_gpu.c/a6xx_gmu.c；先做到"GMU 跑起来 + GX 上电 + 读到 slice 数" | ~2–3 周编码，**盲写 ~30–40%**（有上游逐寄存器对照，AQE 是新面孔但微码已在 linux-firmware，§2.1） | **高**：必须逐步跑（TZ/静默复位文化照抄红杉：pause+loader 旁路日志）。估 3–5 个窗口 | 中高：HFI 时序无第二来源、zap/secure 状态、hypervisor 权限（固件可得性已排除） |
| **L1b** | 2D blit 合成：ctx0 页表（照抄红杉）+ CP 发 copy/清屏包 + MiniIMF.swap 换 GPU blit | ~1–2 周，盲写 ~40%（a6xx CP 包格式对 gen8 大体在，但 aperture/slice 前置让每个包都要复核；UBWC5 先绕开，用线性像素） | 中 | 中：写花屏可恢复 |
| **L2** | GLES 服务：RedwoodGPU msm 协议层平移（改动小）+ **押 turnip(A8XX 上游有) 做底座 + GL-over-Vulkan 桥**（红杉 gallium GL 直译不可行，见 §2.1：Mesa GL 无 gen8） | **月级**，盲写高：要么自拖 gallium 过 gen8（无上游对照），要么 ANGLE/MoltenGL 式桥（GL→Vulkan→turnip）。外部未知已消除，剩下是工程量选型 | 中 | 路线重，但风险已从"外部未知"变"可控工时" |
| **L3** | Metal 全速：air/AIR→NIR 不动，跟随 Mesa **turnip gen8 的 fdl/ISAZ**（非 ir3——gen8 shader ISA 走新后端）；补 IOGPU-free 栈的缺课（红杉也未完成：456 语料里"真机跑通"README 口径 293） | 月级，跟随上游 | 中 | 深水区但**无 iOS 侧风险**；可长期演进 |

建议序（Mesa 结论已定）：**L1a → L1b →（选型：GL 桥 vs 自拖 gallium）→ L2**；若只求 UI 流畅，L1b 2D 合成性价比最高，可长期停在 L1b 不上 L2。

## 5. 放弃 / 推迟准则
- **立即推迟**：真机验证 L1a 步骤 14–17 连续 3 个窗口过不了（GMU 固件起不来 / 静默复位无解；固件本身已在
  linux-firmware 拿齐，若仍起不来就是 HFI 时序/权限问题，离线再抠边际收益低）→ GPU 回 L0，条目转"perf backlog"，与相机同级往后排。
- **放弃 L2/L3（保 L1b）**：GL-over-Vulkan 桥做到 2 个月 CA 还喂不饱，或 Mesa GL gen8 迟迟不来且桥风险失控 → 2D 合成 + CPU GLES 兜底即可撑 UI。
- **放弃整条 GPU 线**：locked/secure 状态下 TZ 拒绝我们碰 GX（红杉时代 `adreno=11/12` 一类探测步就是为此设计，
  先跑等价步）且无解刷方案 → 硬件 GPU 对本工程永久关闭。
- **止损线**：任何一级连续 2 个真机窗口无前进记录，降级回上一级并写 postmortem 进 docs/analysis/。

## TODO（留给在线轮）
1. ~~Mesa a8xx GL/ir3/turnip 支持面~~ **已办结（2026-10-23，§2.1）**：turnip 有、GL 无。
   余留：L2 选型调研（ANGLE-for-freedreno 桥 vs MoltenGL 式直译，红杉 EAGL 垫片改接 turnip 的改动面）。
2. ~~0x44050000 归属~~ **已办结**：上游 catalog 认得（a830，fuse 位勘误 48be91d1）；固件 = linux-firmware
   gen80200 三件套（gmu/sqe/aqe），下载即可，无需真机 dump。zap 是否需要仍看真机（上游 gen80200 无 zapfw）。
3. HFI 版本号（gen8 用哪个 MSGQ/HFI ver）与 `qcom,gmu-freq-table` 语义（dts 里 0x1dcd6500/0x26be3680）。
4. 上游 a8xx 合入的具体 tag 序列（当前已知 master v7.3 含）。
5. `docs/metal.md`（redwoodmetal.m 引用的测量文档）在本仓缺失——从 hackios-xnu-userland 上游仓库补档。
