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

### 上一日背景（详见 docs/analysis 与 docs/backup）
- 123 分区备份完成并与 NAS 4 月备份互证（113/119 逐字节一致，6 差异可解释）。
- `fastboot boot` 在 K90 Pro Max 实测可用；活动槽 `_b`，实验用 `_a`。
