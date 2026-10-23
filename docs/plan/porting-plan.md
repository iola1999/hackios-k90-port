# 移植规划（annibale / REDMI K90）

制定于 2026-10-23。总目标：**先到 iOS 开机**；**不需要持久化**（全程 RAM 模式，
`var_store`/`ufs_write` 不启用，跳过 userdata-carve 适配）。

## 里程碑

### M0 — 工作区 + 构建环境 ✅ 2026-10-23 完成
- [x] git 工作区 + 两个 submodule（origin=私有仓库，upstream=oosexgang，工作分支 `k90-port`）
- [x] 环境：macOS 原生跑通（qemu/7z/dtc/coreutils via brew + tools/mac-env.sh）；
      Docker（OrbStack linux/arm64，hackios-dev 镜像）作对照环境备用
- [x] 双仓合一棵树（`common/setup.sh`，经 `common/ugit` 管理 userland 侧）

### M1 — QEMU 链路 iOS 开机 ✅ 2026-10-23 达成（进桌面）
- [x] `ios165/fetch.sh` 素材：2.9G rootfs + 26M/13M cryptex + 2.6G DSC
- [x] `common/build.sh qemu-virt` → root.apfs(4M) + system.apfs(2.3G) + loader.efi
- [x] `qemu/run-ios.sh <secs> -display cocoa` 带窗口启动 → **SpringBoard 桌面**
- 存证：docs/progress/evidence/2026-10-23-qemu-ios-homescreen.png
  过程：docs/progress/2026-10-23-ios-booted-qemu.md（含 5 个 macOS 适配点）

### M2 — annibale 真机准备（✅ 2026-10-23 核心达成，USB 通道收尾中）
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成 profile + platform 骨架（已完成，见 k90-port）
- UEFI 调研：✅ 已出结论（docs/analysis/uefi-sm8750.md）——**Mu-Silicium 主线已支持
  SM8750**（dodgePkg/paganiPkg 实测在跑），姊妹机型 myron（K90 Pro Max）入口已被
  gbl-chainload 打通（本机 annibale 待同款确认）
- **构建线已开**（docs/analysis/annibale-uefi-build.md）：
  镜像仓 `iola1999/hackios-mu-silicium`（main=上游快照，k90-port=工作分支）；
  `annibalePkg` 骨架已提交（dodgePkg 改名 + **合并 DTB**：vendor_boot base DT ⊕ 自家 dtbo
  overlay，`fdtoverlay` 合成 956KB）
- **真机实测结论（2026-10-23）**：`fastboot boot` 我方 FD → BootShim/EDK2/大部分 QcomPkg
  驱动/XNU loader **全链路跑通**，最后走"无 OS → shutdown"（设备从 USB 消失 = 成功指纹）。
  黑屏 = dodge 面板 XML 与 K90 面板不符（预期内）。LK 的 fastboot boot 有容量上限
  （~2MB，7.5MB 镜像被拒 Load Error）且状态偶发脏（重进 LK 即愈；`reboot fastboot`
  进的是 fastbootd=假故障，回 LK 用 `reboot bootloader`）。
- 待办：boot_a 日志分区通道首次取证（xnu-annibale-log.img 已备好）→ USB 协议
  (QCOM_USB_DEVICE) 卡点定位 → 面板点屏（XML 已按自家 DTS 生成，见 M3）
- **2026-10-23 下午真机轮结**（详见 docs/progress/2026-10-23-annibale-device-trials.md）：
  gadget 18d1:d00d 确认为 loader 描述符但命令通道无响应；EDK2 BlockIo 对五个候选
  分区（boot_a/misc/metadata/logfs/xbl_sc_logs）写全部不落地；串口线是桌上无关
  设备（真 console pad=QUP4 SE10）；**修掉 GOP 缺失时平台停留 qemu_virt 的选择 bug**
  （kernel 仓 872da86，此前所有真机轮都带着错平台跑）。
- **rootfs 策略已定路线 D**（docs/analysis/rootfs-strategy.md）：root.apfs 4.6MB +
  system 转 ext4 ≈22MB 随 payload 走，loader 经 EDK2 BlockIo 批量读进 RAM 交给
  内核虚拟盘；不要求内核带 UFS 驱动，与"不需要持久化"匹配。

### M3 — 真机 bring-up（M2 通过后展开）
- loader 平台：✅ **platform_annibale 已进 loader.c**，参数经合并 DT 实证：
  GIC 0x16000000/0x16080000(stride 0x40000)、PSCI=SMC、8 核 MPIDR 0..500+10000/10100、
  small_cores=0x3f、io 窗 0x00400000+0x3FC00000；`-DDIRECT_PHONE_PLAT` 免 fb 匹配直接选中
- **面板 XML 已生成**：`tools/dts2panelxml.py` 从自家 DTS 转 DisplayDxe XML
  （1156×2510 DSI 时序、DSC1.2 slice 578×10、339 条初始化命令、cmd mode 4 lane），
  已挂进 annibalePkg RAW。**唯一悬念**：DisplayDxe 按 DDIC ID 匹配 `<PanelName>`，
  K90 的 DDIC 自报 ID 未知——USB 日志到手后看 DisplayDxe 打印再定名
- 内核平台层：UFS 时钟、pinctrl/SPMI、cpufreq、Goodix SPI 触摸改造
- **图形路线定案（2026-10-23 晚，离线轮）**：内核显示唯一入口是 **BootArgs.video**
  （QEMU 锁屏 = ramfb BAR 全靠它，chosen 里根本没有 framebuffer 属性）。真机上 loader
  在 GOP 缺失时把 **LK splash 区 0xFC800000**（DT 的 cont_splash_region，与我方
  Display_Reserved 同址）填进 BootArgs.video（commit a6bdbab）——**开机到图形锁屏
  不需要 MDSS/DSI 驱动**；DisplayDxe 的 PanelName 悬念降级为"快进路径不再必需"。
  前提：用 `--set-active=a + reboot` 启动让 LK 点屏（playbook 陷阱 8）。
  GPU 加速（Adreno 830/gen8）维持不做；redwood 的 a660 GPU 驱动（redwood_adreno.c，
  含面板扫描）是将来 perf 的参考蓝本。
- **外设驱动盘点**（fork 的真机驱动全是 bsd/dev/redwood_*.c 裸寄存器 + boot-arg 开关，
  无 IOKit 框架）：触摸 `redwood_goodix.c`（GT9916/FT3680 @GENI SE，轮询 IRQ 125Hz）→
  annibale 改 = SE2 **0xa88000**（勘误：非 a8c000）+ pinctrl-sun GPIO40-43/161/162 +
  gcc-sm8750 时钟位 + RPMh LDO（L12B/avdd），GENI FIFO 协议跨代一致，天级；
  振动 `redwood_haptic.c`（SPMI→LRA）→ annibale hv-haptics SPMI@c42d000 从设备7 f000；
  Wi-Fi `redwood_wifi.c/wlfw`（QWC NVM 加载 MHI）→ WCN7850 kiwi PCIe RC0，月级；
  相机（camera_*.c 用户态 + redwood_camera.c）→ annibale CSI/IFE 连资源都未映射，
  排在开机之后。root 传输变体 C（rdfile 读 userdata 尾，loader 72bbea4 +
  tools/stage-system.sh）编译就绪，等真机窗口。
- 第一里程碑 = loader USB 日志 + verbose 启动文本；第二 = 锁屏（软渲染，无 GPU/Wi-Fi/音频）
- `fastboot boot` 已实测：≤2MB 镜像可用（LK 侧容量上限），大镜像走 `_a` 槽 `fastboot flash boot_a`
  （unlocked 橙牌放行；回退 = `--set-active=b`）

## 明确不做（本期）

- 存储持久化（carve d 分区、APFS 写路径）；GPU（gen8/Adreno 830 等 Mesa a8xx）；
  Wi-Fi ath12k；音频 ADSP；相机。都排在 iOS 开机之后。

## 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| ~~SM8750 无现成 UEFI~~ → Mu-Silicium main 已含 SM8750（Pakala），姊妹机型 EFI 入口已通（本机待移植确认） | M2 风险中低 | annibale pkg 移植 + XBL 协议地址随 HyperOS 漂移逐版重扫 |
| Gunyah 占 EL2 | UEFI 运行层级未知 | UEFI 起来后实测 |
| OrbStack VM 内存默认偏小 | QEMU 起不来（需 ≥3GB） | 调 OrbStack 配置 / `QEMU_RAM_GB` |
| VirtioFS 慢 | fetch/解包/构建耗时 | 必要时挪进容器卷 |
| HyperOS 更新改分区表 | 备份失效 | 更新后 diff `partitions.txt` |
