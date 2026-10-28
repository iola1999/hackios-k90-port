# 移植规划（annibale / REDMI K90）

制定于 2026-10-23。总目标：**先到 iOS 开机**；**不需要持久化**（全程 RAM 模式，`var_store`/`ufs_write` 不启用，跳过 userdata-carve 适配）。

## 1. 里程碑

### M0 — 工作区 + 构建环境 2026-10-23 完成
- [x] git 工作区 + 两个 submodule（origin=私有仓库，upstream=oosexgang，工作分支 `k90-port`）
- [x] 环境：macOS 原生跑通（qemu/7z/dtc/coreutils via brew + tools/mac-env.sh）；Docker（OrbStack linux/arm64，hackios-dev 镜像）作对照环境备用
- [x] 双仓合一棵树（`common/setup.sh`，经 `common/ugit` 管理 userland 侧）

### M1 — QEMU 链路 iOS 开机 2026-10-23 达成（进桌面）
- [x] `ios165/fetch.sh` 素材：2.9G rootfs + 26M/13M cryptex + 2.6G DSC
- [x] `common/build.sh qemu-virt` → root.apfs(4M) + system.apfs(2.3G) + loader.efi
- [x] `qemu/run-ios.sh <secs> -display cocoa` 带窗口启动 → **SpringBoard 桌面**
- 存证：docs/progress/evidence/2026-10-23-qemu-ios-homescreen.png 过程：docs/progress/2026-10-23-ios-booted-qemu.md（含 5 个 macOS 适配点）

### M2 — annibale 真机准备（2026-10-23 核心达成，USB 通道收尾中）
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成 profile + platform 骨架（已完成，见 k90-port）
- UEFI 调研：已出结论（docs/analysis/uefi-sm8750.md）——**Mu-Silicium 主线已支持 SM8750**（dodgePkg/paganiPkg 实测在跑），姊妹机型 myron（K90 Pro Max）入口已被 gbl-chainload 打通（本机 annibale 待同款确认）
- **构建线已开**（docs/analysis/annibale-uefi-build.md）：镜像仓 `iola1999/hackios-mu-silicium`（main=上游快照，k90-port=工作分支）；`annibalePkg` 骨架已提交（dodgePkg 改名 + **合并 DTB**：vendor_boot base DT ⊕ 自家 dtbo overlay，`fdtoverlay` 合成 956KB）
- **UEFI 进构建输入记录（待办，独立评估 F08）**：Mu 工作树在被忽略的独立目录（HEAD `87416d23…`，含 BootShim/Mu_Basecore 等本地状态），顶层两 submodule 指针记不住这些输入。要把 Mu 提交与子模块状态、应用的补丁清单、合并 DTB 与 FD 哈希写进同一份构建输入记录，并在独立目录验证一次完整恢复（本轮未重建 FD，未判定本地状态是否全部可由现有脚本恢复）。
- **真机实测结论（2026-10-23）**：`fastboot boot` 我方 FD → BootShim/EDK2/大部分 QcomPkg 驱动/XNU loader **全链路跑通**（阶段归属为间接推断，F07 分级：设备从 USB 消失只是间接指纹，支持"跑到最后一步"但不能唯一确定到达阶段，待四阶段阶段标记收账），最后走"无 OS → shutdown"。黑屏 = dodge 面板 XML 与 K90 面板不符（预期内）。LK 的 fastboot boot 有容量上限（~2MB，7.5MB 镜像被拒 Load Error）且状态偶发脏（重进 LK 即愈；`reboot fastboot` 进的是 fastbootd=假故障，回 LK 用 `reboot bootloader`）。
- 待办：boot_a 日志分区通道首次取证（xnu-annibale-log.img 已备好）→ USB 协议 (QCOM_USB_DEVICE) 卡点定位 → 面板点屏（XML 已按自家 DTS 生成，见 M3）
- **2026-10-23 下午真机轮结**（详见 docs/progress/2026-10-23-annibale-device-trials.md）：gadget 18d1:d00d 确认为 loader 描述符但命令通道无响应；EDK2 BlockIo 对五个候选分区（boot_a/misc/metadata/logfs/xbl_sc_logs）写全部不落地；串口线是桌上无关设备（真 console pad=QUP4 SE10）；**修掉 GOP 缺失时平台停留 qemu_virt 的选择 bug** （kernel 仓 872da86，此前所有真机轮都带着错平台跑）。
- **rootfs 策略已定路线 D**（docs/analysis/rootfs-strategy.md）：root.apfs 4.6MB + system 转 ext4 ≈22MB 随 payload 走，loader 经 EDK2 BlockIo 批量读进 RAM 交给内核虚拟盘；不要求内核带 UFS 驱动，与"不需要持久化"匹配。

### M3 — 真机 bring-up（M2 通过后展开）
- loader 平台：**platform_annibale 已进 loader.c**，参数经合并 DT 实证：GIC 0x16000000/0x16080000(stride 0x40000)、PSCI=SMC、8 核 MPIDR 0..500+10000/10100、small_cores=0x3f、io 窗 0x00400000+0x3FC00000；`-DDIRECT_PHONE_PLAT` 免 fb 匹配直接选中
- **面板 XML 已生成**：`tools/dts2panelxml.py` 从自家 DTS 转 DisplayDxe XML （1156×2510 DSI 时序、DSC1.2 slice 578×10、339 条初始化命令、cmd mode 4 lane），已挂进 annibalePkg RAW。**唯一悬念**：DisplayDxe 按 DDIC ID 匹配 `<PanelName>`，K90 的 DDIC 自报 ID 未知——USB 日志到手后看 DisplayDxe 打印再定名
- 内核平台层：UFS 时钟、pinctrl/SPMI、cpufreq、Goodix SPI 触摸改造
- **图形路线定案（2026-10-23 晚，离线轮）**：内核显示唯一入口是 **BootArgs.video** （QEMU 锁屏 = ramfb BAR 全靠它，chosen 里根本没有 framebuffer 属性）。真机上 loader 在 GOP 缺失时把 **LK splash 区 0xFC800000**（DT 的 cont_splash_region，与我方 Display_Reserved 同址）填进 BootArgs.video（commit a6bdbab）——**开机到图形锁屏不需要 MDSS/DSI 驱动**；DisplayDxe 的 PanelName 悬念降级为"快进路径不再必需"。前提：用 `--set-active=a + reboot` 启动让 LK 点屏（playbook 陷阱 8）。GPU 加速（Adreno 830/gen8）本期维持不做，但资源已备好：`gpu-plan.md`——上游 v7.3 已收 a8xx（288a9320），SM8750 全套基址已从设备树拆齐可抄，redwood蓝本（redwood_adreno.c 22 步上电 + Mesa freedreno 桩 + Mini IOSurface/FB 替身 + Metal 半成品）链路已盘点清楚；L1 2D/L2 GLES/L3 Metal 三级都不动 iOS 用户态。
- **外设驱动盘点**（fork 的真机驱动全是 bsd/dev/redwood_*.c 裸寄存器 + boot-arg 开关，无 IOKit 框架）：触摸 `redwood_goodix.c` **已完成 annibale 参数化**（2026-10-23 离线轮，kernel cc9ff58）：开机参数 `touchscreen=2` 即换用 annibale 表——SE2 **0xa88000**（勘误：非 a8c000）、GPIO40-43(mux1)/161/162/avdd114、TLMM 0x0f000000、RPMh drv-2 0x16520000 （TCS 偏移同 0xd00）、供电名 ldob12、SMEM 扫 cmd_db 魔数、引擎时钟=vote 位 24 纯分支 + qspi_ref(0x188c4)/固定分频(0x1828c) 读速（无 DFS，GENI_CLK_SEL=0）；redwood 常数零改动。振动 **已完成新驱动 redwood_haptic_hv.c**（kernel 2006f81，等真机）：K90 马达在 PMIC 内置 hv-haptics（SPMI 外设 0xf0 驱动/0xf1 图案/0xf2 boost；arbiter **v7** 布局：读通道 obsrvr+0x8000·ee+0x20·apid、写 chnls+0x1000·apid、外设表 core+0x2000、属主 cnfg+4n，与 redwood buttons 的 v5 完全不同）——boot-arg `hv_haptic=1..4`：查表读 revision→配置（5714us 周期/1300mV/brake ff 3f 1f/正弦波，全部读回校验）→30ms 直驱自检→iOS 反馈直通（/dev/redwood-haptic，DIRECT_PLAY 跟随响度，tap/长震切分沿用 redwood 语义）；redwood_haptic.c 零改动。Wi-Fi：redwood = WPSS-PIL+GLINK/QMI+ath11k(ahb)（勘误：无 MHI）；annibale WCN7850 = PCIe RC0@0x1c00000 + MHI + ath12k 蓝本，fork 内核 PCIe host 与 MHI host 两块全新增，4–8 周真机窗口起步/保守 1.5–3 个月（详见 wcn7850-plan.md）；相机 **调研完成（camera-plan.md）**：redwood 是完整方案（redwood_camera.c cam=1..5 裸寄存器 + mediaserverd 注入顶替 H10ISP + 软 ISP，预览/拍照/AF 真机回归过）；annibale CAMSS 全套基址已从设备树拆齐（camcc 0xade0000、CSIPHY×6、CSID980、IFE×3、CPAS 0xac13000、CCI×3；主摄 OV50E 走 CCI0/CSIPHY3），iOS 用户态零改动，门在 mediaserverd 不在 camerad。L1a TPG 通路 ~3 周/4–6 窗口；首要行动项=真机 `adb pull /vendor/lib64/camera`（sensormodule bin，拿不到就冻结 sensor 阶段）。root 传输变体 C（rdfile 读 userdata 尾，loader 72bbea4 + tools/stage-system.sh）编译就绪，等真机窗口。
- **本期扩容（2026-10-23 功能扫描，详见 docs/analysis/2026-10-23-feature-scan.md）**：按键/电池/手电三项加入离线准备与真机测试排期——按键=红杉语义平移（annibale 音量上实测在 TLMM GPIO6，电源/音量下走 PMK8550 PON，SPMI 层复用 hv 驱动的 v7 通道）；电池改走内核 SPMI 直读 PMIH010X FG（红杉的 loader-UEFI 缓存路线在 annibalePkg 上没有 charger 驱动可缓存，放弃）；手电=PMI 闪光灯块（DT camera-flash 节点指认），相机 L1b 共用。音频维持不碰（SM8750 换 ADSP+SoundWire WCD9395，月级）。Wi-Fi 固件前提消解：linux-firmware `ath12k/WCN7850/hw2.0/` 有包。hackios 上游（oosexgang 两仓）main 零新提交，replydev 三个未合并 PR 暂不摘取、合入后再同步。
- **上游关系改章（2026-10-23，用户拍板）**：不再跟进 hackios 上游——能给上游贡献的就做，贡献不了的我们自己发开源，我们自己来做最工程化的体验。执行含义：①内核层机制按我方工程判断改（redwood.patch 单体拆按文件 series=task-8；将来 per-device 内核画像、redwood_* 命名治理也可动），apply.sh/export.sh 的本地分歧不再是顾虑而是产品能力；②上游扫描降级为不主动，通用修复（ppid 修正、patch series 工具这类）攒着反向送 PR，不收就随我们自己的开源发布；③"最工程化"的验收面=构建链可复现（指纹表/幂等脚本）+ 队友写范围零冲突 + AGENTS.md 文档纪律。
- **命名三层制（2026-10-23，用户批准）**：①架构级/ABI 名冻结不新增——`kern.redwood.*` sysctl、`/dev/redwood-*`、`RedwoodAudio.driver`、`redwood_audio.h` 枢纽保持原样（内核↔userland 注入的 ABI，等真机一把过后另做带别名的改名波）；②老机型文件保名——POCO X5 Pro（redwood）的真驱动（redwood_buttons.c 等）不改，它们是蓝本不是本机代码；③新文件按复用层级命名（立即生效）——SoC/IP 级可移植不带前缀（adreno8.c、mhi_pcie.c），板级绑定用 `annibale_` 前缀（annibale_buttons/battery/torch/haptic.c，已入库的 `_hv` 四件套由 task-10 归队）；boot-arg 名机型中立（buttons/torch_secs/adreno8/pcie…）。`redwood.patch` 之名随 task-8 的 patches/series 自然退役。
- 第一里程碑 = loader USB 日志 + verbose 启动文本；第二 = 锁屏（软渲染，无 GPU/Wi-Fi/音频）
- `fastboot boot` 已实测：≤2MB 镜像可用（LK 侧容量上限），大镜像走 `_a` 槽 `fastboot flash boot_a` （unlocked 橙牌放行；回退 = `--set-active=b`）

## 2. 明确不做（本期）

- 存储持久化（carve d 分区、APFS 写路径）；GPU（gen8/Adreno 830 等 Mesa a8xx）；Wi-Fi ath12k；音频 ADSP；相机。都排在 iOS 开机之后。

## 3. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| ~~SM8750 无现成 UEFI~~ → Mu-Silicium main 已含 SM8750（Pakala），姊妹机型 EFI 入口已通（本机待移植确认） | M2 风险中低 | annibale pkg 移植 + XBL 协议地址随 HyperOS 变化逐版重扫 |
| Gunyah 占 EL2 | UEFI 运行层级未知 | UEFI 起来后实测 |
| OrbStack VM 内存默认偏小 | QEMU 起不来（需 ≥3GB） | 调 OrbStack 配置 / `QEMU_RAM_GB` |
| VirtioFS 慢 | fetch/解包/构建耗时 | 必要时挪进容器卷 |
| HyperOS 更新改分区表 | 备份失效 | 更新后 diff `partitions.txt` |
