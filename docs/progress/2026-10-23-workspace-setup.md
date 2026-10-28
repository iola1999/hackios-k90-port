# 进展日志

## 1. 2026-10-23（晚）— 机型纠偏：K90 ≠ K90 Pro Max

- 用户指出 KernelSU 开着**机型伪装模块**；禁用重启后真实身份：**REDMI K90** （model 2510DRK44C，代号仍 `annibale`）。**myron = K90 Pro Max 是另一款机器**。
- 全量复查受影响结论：
  - **保持有效**（硬件层，props 伪装无法伪造）：kernel `/sys/devices/soc0`=soc_id 618/"SUN"、本机 dtb `model="Annibale based on SM8750"`+`msm-id 0x26a(618)`、GPU `/sys/class/kgsl`= Adreno830v2、GIC/MPIDR/UFS/触摸 dtb 结论、分区备份（目录名本就是 annibale）、fastboot boot 实测（bootloader 层）。
  - **修正**：市场型号全链（README/规划/可行性/UEFI 调研/子模块 conf NAME）；gbl-chainload-myron 归为**姊妹机型**先例（同 SoC，参考价值仍在，本机待同款确认）；分辨率 1156×2510=Android 渲染值（禁用伪装后不变），物理面板 1200×2608@480dpi（社区树）。
  - **新增情报**：MissMyTime/twrp_device_sm8850 树含 annibale 完整设备资料（面板/kiwi_v2 Wi-Fi/Goodix 触摸/wrappedkey 加密）——移植参考富矿，已录入 UEFI 调研文档。
- iOS 素材 fetch 全部完成（rootfs 2.9G + cryptex + DSC 2.6G），转入 QEMU 构建。

## 2. 2026-10-23 — 工作区建立 + Docker 环境（M0）


- 工作区目录重组为 docs/{analysis,backup,fastboot,plan,progress} + docker + tools；原 hackios-k90-notes 内容按类别并入 docs。
- git init（main）；`hackios-xnu-kernel`、`hackios-xnu-userland` 注册为 submodule：origin 指向私有仓库（含上游完整历史），upstream 保留 oosexgang 地址；两边各开 `k90-port` 分支。
- 父仓库推送至 GitHub 私有仓库（分批提交）。
- Docker：OrbStack linux/arm64；`docker/Dockerfile` 安装 qemu-system-aarch64、7zip、edk2-aarch64、dtc 等（官方 host 依赖按 arm64 适配）；`docker/dev.sh` 进容器。QEMU 无窗口运行（run-ios.sh 本身支持：ramfb + monitor 4444 + QMP 4445，配 screendump.sh/touch.py，不需要 -display gtk）。
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成 `common/devices/annibale.conf` + `annibale.platform.c`（内核 submodule 的 k90-port 分支）。
- 持久化明确不做（目标=到 iOS 开机，RAM 模式）。

### 环境路线改为 macOS 原生（用户提问触发核查）
- 核查结论：**不必用 Linux**——`qemu/run.sh` 硬编码 `-accel tcg`（Mac 与 Linux 行为一致，hvf 无关）；APFS 镜像纯 Python（tools/apfs/mkapfs.py）；交叉编译走仓库自带 xnu-clang + iPhoneOS SDK，与宿主无关。Docker 保留作疑难对照环境（apt 已换 USTC 源）。
- Mac 侧补齐：brew qemu（已装 11.0.1，自带 edk2-aarch64 固件 → 拷成 tools/qemu-efi/ QEMU_{EFI,VARS}.fd）、sevenzip（7zz→tools/hostbin/7z 软链）、coreutils（gnubin 提供 GNU timeout/stat/cp）；`tools/mac-env.sh` 一键 source。
- 唯一代码补丁（k90-port）：qemu/run-ios.sh 的 os.copy_file_range 加 macOS 回退路径。
- `common/setup.sh` 已在 Mac 完成双仓合一棵树；`ios165/fetch.sh` 后台下载中。

### UEFI 调研（M2 提前启动，子代理全量报告已入库）
- 复核：`getprop ro.soc.model` = **SM8750** 确认（排除 SM8850 疑云）；本机社区别名 **myron** （repo 内代号 annibale）。
- 核心发现：**Mu-Silicium 主线已支持 SM8750**（PakalaPkg，OnePlus 13 显示/存储/Linux boot 已支持）= 与 hackios 上游同栈；本机自制 EFI 入口已被 gbl-chainload-myron（EFISP+ABL 链入）打通。
- 路线定稿：① Mu-Silicium 基座出 annibale pkg（主）；② 原厂 UEFI 内存 patch（快验入口）；③ 跟 SunUEFI 社区（piano 同 SoC 旁证）；④ edk2-msm 从零（放弃，其 SM8750=零）。
- 详见 docs/analysis/uefi-sm8750.md（全部链接与 M2 待办）。

### 上一日背景（详见 docs/analysis 与 docs/backup）

- 123 分区备份完成并与 NAS 4 月备份互证（113/119 逐字节一致，6 差异可解释）。
- `fastboot boot` 在 K90 Pro Max 实测可用；活动槽 `_b`，实验用 `_a`。
