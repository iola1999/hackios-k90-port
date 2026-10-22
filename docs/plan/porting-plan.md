# 移植规划（annibale / K90 Pro Max）

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
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成 profile + platform 骨架
- UEFI 调研（最大不确定项）：
  - edk2-msm / Mu-Silicium 及社区 fork 有无 SM8750（"sun"）底子（用 gh/Google 查，不硬钻）
  - 解析备份里的原厂 `uefi_a`（5MB）内存图与 GOP 驱动可提取性
- 决策点：自研 sun UEFI 值不值，或先用 QEMU 完成演示目标
- 验收：`docs/analysis/` 新增 UEFI 可行性调研一篇 + `annibale.conf` 骨架入库

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
| SM8750 无现成 UEFI | M2/M3 阻塞 | 先 QEMU 达成开机目标；调研社区进展 |
| Gunyah 占 EL2 | UEFI 运行层级未知 | UEFI 起来后实测 |
| OrbStack VM 内存默认偏小 | QEMU 起不来（需 ≥3GB） | 调 OrbStack 配置 / `QEMU_RAM_GB` |
| VirtioFS 慢 | fetch/解包/构建耗时 | 必要时挪进容器卷 |
| HyperOS 更新改分区表 | 备份失效 | 更新后 diff `partitions.txt` |
