# 移植规划（annibale / REDMI K90）

制定于 2026-10-23。总目标：**先到 iOS 开机**；**不需要持久化**（全程 RAM 模式，
`var_store`/`ufs_write` 不启用，跳过 userdata-carve 适配）。

## 里程碑

### M0 — 工作区 + Linux 环境（进行中）
- [x] git 工作区 + 两个 submodule（origin=私有仓库，upstream=oosexgang，工作分支 `k90-port`）
- [ ] Docker（OrbStack, linux/arm64）装齐 qemu-system-aarch64 / 7zip / edk2-aarch64 / dtc
- [ ] 双仓合一棵树（`common/setup.sh` 在容器内执行）
- 验收：容器内 `qemu-system-aarch64 --version`、`dtc --version`、脚本 `--help` 可跑

### M1 — QEMU 链路 iOS 开机 ← **“先到 iOS 开机”的主体**
- `ios165/fetch.sh` 拉 7.4GB IPSW 并解包
- `common/build.sh qemu-virt` 出 root.apfs / system.apfs（无需交叉工具链，走 prebuilt）
- headless 跑 QEMU（ramfb + 4444 监控 + 4445 QMP，`screendump.sh` 出图）
- 验收：截图见 iOS 16.5 锁屏
- 风险：Mac 内存（QEMU 实例 ~3GB，OrbStack VM 内存上限要够）；VirtioFS 大文件性能

### M2 — annibale 真机准备（可与 M1 并行）
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成 profile + platform 骨架（已完成，见 k90-port）
- UEFI 调研：✅ 已出结论（docs/analysis/uefi-sm8750.md）——**Mu-Silicium 主线已支持
  SM8750**（PakalaPkg，OnePlus 13 系已验证），姊妹机型 myron（K90 Pro Max）入口已被
  gbl-chainload 打通（本机 annibale 待同款确认）；
  首选与上游同栈出 annibale pkg，次选原厂 UEFI 内存 patch
- 决策点：M2 开 annibale-pkg 分支（Mu-Silicium fork），先用 gbl-chainload 模式快验 loader+GOP
- 验收：annibale UEFI 起壳截图（GOP 出图）+ `annibale.conf` 补全 FB_BASE/FD_BASE

### M3 — 真机 bring-up（M2 通过后展开）
- loader 平台（数字已在体检文档：GIC 0x16000000/0x16080000、8 核、shift 8、前 6 核 small）
- 内核平台层：UFS 时钟、pinctrl/SPMI、cpufreq、Goodix SPI 触摸改造
- 第一里程碑 = loader USB 日志 + verbose 启动文本；第二 = 锁屏（软渲染，无 GPU/Wi-Fi/音频）
- `fastboot boot` 已实测可用（docs/fastboot/），实验优先走暂存镜像、用 `_a` 槽，不刷 `_b`

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
