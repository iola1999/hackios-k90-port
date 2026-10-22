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

### M2 — annibale 真机准备（进行中）
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成 profile + platform 骨架（已完成，见 k90-port）
- UEFI 调研：✅ 已出结论（docs/analysis/uefi-sm8750.md）——**Mu-Silicium 主线已支持
  SM8750**（dodgePkg/paganiPkg 实测在跑），姊妹机型 myron（K90 Pro Max）入口已被
  gbl-chainload 打通（本机 annibale 待同款确认）
- **构建线已开**（docs/analysis/annibale-uefi-build.md）：
  镜像仓 `iola1999/hackios-mu-silicium`（main=上游快照，k90-port=工作分支）；
  `annibalePkg` 骨架已提交（dodgePkg 改名 + **我们 dtbo_a 备份里提取的正主 DTB**）
- 待办：子模块浅拉（Binaries/Mu/Basecore/ACPI/openssl）→ 设备 UEFIReader 转储
  → MemoryMap/面板核对 → `uefi/mu-silicium.patch` 双补丁 → docker 内 stuart 构建
- 验收：`fastboot boot`（未实测过能力上限，先试）或 gbl-chainload 起 annibale UEFI，
  GOP 出图 + `annibale.conf` 补全 FB_BASE/FD_BASE

### M3 — 真机 bring-up（M2 通过后展开）
- loader 平台（数字已在体检文档：GIC 0x16000000/0x16080000、8 核、shift 8、前 6 核 small）
- 内核平台层：UFS 时钟、pinctrl/SPMI、cpufreq、Goodix SPI 触摸改造
- 第一里程碑 = loader USB 日志 + verbose 启动文本；第二 = 锁屏（软渲染，无 GPU/Wi-Fi/音频）
- `fastboot boot` 未在真机实测过（文档 docs/fastboot/ 只验证过 getvar）；实验优先走暂存镜像、用 `_a` 槽，不刷 `_b`

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
