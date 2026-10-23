# hackios-k90-port — HackiOS 移植工作区（REDMI K90 / annibale）

把 [HackiOS](https://github.com/oosexgang/hackios-xnu-kernel)（XNU + 未修改 iOS 16.5 用户态跑在安卓机上）移植到 **REDMI K90**（SM8750 骁龙 8 Elite，代号 `annibale`；曾被子系统伪装模块误报为 K90 Pro Max=myron，已纠偏，见 docs/analysis/）。本仓库是移植工作的**顶层工作区**：文档、脚本、配置都在这里，上游代码以 submodule 引入。

## 1. 上游来源、致谢与仓库关系

本项目基于 [OOSEX GANG 的 HackiOS 内核仓库](https://github.com/oosexgang/hackios-xnu-kernel)和[用户态仓库](https://github.com/oosexgang/hackios-xnu-userland)开展 K90 移植。感谢原作者与贡献者开放 XNU 移植、EFI loader、用户态适配、镜像构建、图形工具及相关文档；本项目沿用这些实现，并在其基础上维护 annibale 适配和调试修复。

| 仓库 | 职责与来源 | 本项目分支 |
|---|---|---|
| [hackios-k90-port](https://github.com/iola1999/hackios-k90-port) | 本顶层工作区，保存文档、辅助脚本及两个子模块的具体版本 | `main` |
| [hackios-xnu-kernel](https://github.com/iola1999/hackios-xnu-kernel) | 保留原内核仓库历史，维护 K90 的 XNU、loader 和固件相关修改 | `k90-port` |
| [hackios-xnu-userland](https://github.com/iola1999/hackios-xnu-userland) | 保留原用户态仓库历史，维护用户态适配、APFS 与图形构建工具 | `k90-port` |

两个代码仓库当前以独立仓库保存上游历史，GitHub 的 fork 关联尚未建立。源码来源由本节及各仓库 README 明确说明；GitHub 的 fork 标记单独处理。原有许可证和版权声明保留，各组件许可范围见所属仓库的 `LICENSE` 及文件声明。上游的 POCO X5 Pro／QEMU 功能说明按其原有设备范围阅读，K90 的验证结果见本工作区的调试文档。

## 2. 当前目标（见 docs/plan/）

先到 **iOS 开机**（QEMU 链路先通，真机后置）；**不做存储持久化**（RAM 模式，不启用 `ufs_write=1`/`var_store`）。Linux 构建环境用 Docker（OrbStack，linux/arm64 + QEMU TCG）。

## 3. 目录布局

```
hackios-k90-port/
├── docs/
│   ├── analysis/     可行性分析、硬件体检（data/ 存 annibale 设备树原件）
│   ├── backup/       分区备份与 NAS 互证记录
│   ├── fastboot/     fastboot boot 实测证据（getvar/输出）
│   ├── plan/         移植规划、里程碑
│   └── progress/     按日期的进展日志
├── docker/           Linux 构建/QEMU 运行环境（Dockerfile + 脚本）
├── tools/            我们自己的辅助脚本
├── annibale-backup/  123 分区 gzip 备份（748MB，git 忽略，NAS 有副本）
├── hackios-xnu-kernel/    [submodule] 内核侧（我们分支: k90-port）
└── hackios-xnu-userland/  [submodule] 用户态侧（我们分支: k90-port）
```

## 4. 子模块与上游跟进

两个 submodule 的 `origin` 指向本项目的代码仓库，`upstream` 指向 OOSEX GANG 的原仓库。本项目在 `k90-port` 分支维护移植修改，顶层仓库记录子模块的具体 commit。是否合并上游变更按当前移植工作安排评估，计划见 `docs/plan/porting-plan.md`。

kernel 的 `common/setup.sh` 将 userland 作为第二套 Git 元数据 `.userland.git` 放进同一构建树；该 overlay 与顶层并列的 userland 子模块需要分别检查版本。脚本的上游默认值保持原样，创建 K90 构建树时显式指定 `USERLAND_URL=https://github.com/iola1999/hackios-xnu-userland.git USERLAND_REF=k90-port`。已有构建树先检查状态，再决定更新，避免覆盖未提交修改。

## 5. 快速开始

**主路线：macOS 原生**（QEMU 上游本就硬编码 `-accel tcg`，Mac 上行为与 Linux 完全一致；APFS 镜像由纯 Python 生成，交叉编译走仓库自带的 xnu-clang，均不依赖宿主发行版）：

```sh
brew install sevenzip coreutils qemu          # 7zz→tools/hostbin/7z 已做软链
source tools/mac-env.sh                        # GNU timeout/stat + AAVMF 固件路径
cd hackios-xnu-kernel
common/setup.sh                                # 双仓合一棵树（已完成）
ios165/fetch.sh                                # 拉 iOS 16.5（进行中）
common/build.sh qemu-virt && common/run.sh qemu-virt
```

**备用路线：Docker**（环境复现/疑难对照；apt 已换 USTC 源）：

```sh
docker/build.sh && docker/dev.sh               # 容器内 /work 即本工作区
```

关键结论/实测速查：`docs/analysis/k90-annibale-feasibility.md`（体检 + fastboot boot 可用 + 移植分解）；恢复分区看 `annibale-backup/README.md` 与 NAS `supplement-20261022/`。

## 6. 备份（重要，勿删）

- Mac：`annibale-backup/20261022-2355/`（123 分区 + 6 LUN GPT 头尾，含哈希清单）
- NAS：`${BACKUP_DIR}/`（2026-04 raw 124 个 + 本次补充 `supplement-20261022/`）——两份互证互备，见 `docs/backup/`。
