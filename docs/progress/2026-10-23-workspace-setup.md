# 进展日志

## 2026-10-23 — 工作区建立 + Docker 环境（M0）

- 工作区目录重组为 docs/{analysis,backup,fastboot,plan,progress} + docker + tools；
  原 hackios-k90-notes 内容按类别并入 docs。
- git init（main）；`hackios-xnu-kernel`、`hackios-xnu-userland` 注册为 submodule：
  origin 指向私有仓库（含上游完整历史），upstream 保留 oosexgang 地址；两边各开 `k90-port` 分支。
- 父仓库推送至 GitHub 私有仓库（分批提交）。
- Docker：OrbStack linux/arm64；`docker/Dockerfile` 安装 qemu-system-aarch64、7zip、
  edk2-aarch64、dtc 等（官方 host 依赖按 arm64 适配）；`docker/dev.sh` 进容器。
  QEMU 无窗口运行（run-ios.sh 本身支持：ramfb + monitor 4444 + QMP 4445，
  配 screendump.sh/touch.py，不需要 -display gtk）。
- `common/new-device.sh annibale docs/analysis/data/annibale.fdt` 生成
  `common/devices/annibale.conf` + `annibale.platform.c`（内核 submodule 的 k90-port 分支）。
- 持久化明确不做（目标=到 iOS 开机，RAM 模式）。

### 环境路线改为 macOS 原生（用户提问触发核查）
- 核查结论：**不必用 Linux**——`qemu/run.sh` 硬编码 `-accel tcg`（Mac 与 Linux 行为一致，
  hvf 无关）；APFS 镜像纯 Python（tools/apfs/mkapfs.py）；交叉编译走仓库自带 xnu-clang +
  iPhoneOS SDK，与宿主无关。Docker 保留作疑难对照环境（apt 已换 USTC 源）。
- Mac 侧补齐：brew qemu（已装 11.0.1，自带 edk2-aarch64 固件 → 拷成 tools/qemu-efi/
  QEMU_{EFI,VARS}.fd）、sevenzip（7zz→tools/hostbin/7z 软链）、coreutils（gnubin 提供
  GNU timeout/stat/cp）；`tools/mac-env.sh` 一键 source。
- 唯一代码补丁（k90-port）：qemu/run-ios.sh 的 os.copy_file_range 加 macOS 回退路径。
- `common/setup.sh` 已在 Mac 完成双仓合一棵树；`ios165/fetch.sh` 后台下载中。

### UEFI 调研（M2 提前启动）
- SM8750 有活跃开源固件 **Project-SunUEFI**（小米平板 8 Pro 同 SoC，昨日有 commit）+
  edk2-gunyah（Gunyah 里跑 UEFI，对 K90 的 EL2 环境直接相关）。风险高→中。
- 详见 docs/analysis/uefi-sm8750.md（含方案排序与 M2 待办）。

### 上一日背景（详见 docs/analysis 与 docs/backup）

- 123 分区备份完成并与 NAS 4 月备份互证（113/119 逐字节一致，6 差异可解释）。
- `fastboot boot` 在 K90 Pro Max 实测可用；活动槽 `_b`，实验用 `_a`。
