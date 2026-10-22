# hackios-k90-port — HackiOS 移植工作区（REDMI K90 Pro Max / annibale）

把 [HackiOS](https://github.com/oosexgang/hackios-xnu-kernel)（XNU + 未修改 iOS 16.5 用户态跑在安卓机上）
移植到 **REDMI K90 Pro Max**（SM8750 骁龙 8 Elite，代号 `annibale`）。
本仓库是移植工作的**顶层工作区**：文档、脚本、配置都在这里，上游代码以 submodule 引入。

## 当前目标（见 docs/plan/）

先到 **iOS 开机**（QEMU 链路先通，真机后置）；**不做存储持久化**（RAM 模式，
不启用 `ufs_write=1`/`var_store`）。Linux 构建环境用 Docker（OrbStack，linux/arm64 + QEMU TCG）。

## 目录布局

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

## 子模块与上游跟进

- 两个 submodule 的 `origin` = 我们私有仓库（iola1999/*，含完整上游历史 + 我们的 `k90-port` 分支）；
  `upstream` = oosexgang 原仓库。**跟进上游**：`git -C <mod> fetch upstream && git -C <mod> merge upstream/main`
  （在 `k90-port` 分支上），然后父仓库提交新的 pointer。
- 我们的改动只落在 `k90-port` 分支；父仓库记录 submodule 的具体 commit。

## 快速开始

**主路线：macOS 原生**（QEMU 上游本就硬编码 `-accel tcg`，Mac 上行为与 Linux 完全一致；
APFS 镜像由纯 Python 生成，交叉编译走仓库自带的 xnu-clang，均不依赖宿主发行版）：

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

关键结论/实测速查：`docs/analysis/k90-pro-max-feasibility.md`（体检 + fastboot boot 可用 +
移植分解）；恢复分区看 `annibale-backup/README.md` 与 NAS `supplement-20261022/`。

## 备份（重要，勿删）

- Mac：`annibale-backup/20261022-2355/`（123 分区 + 6 LUN GPT 头尾，含哈希清单）
- NAS：`${BACKUP_DIR}/`（2026-04 raw 124 个 + 本次补充
  `supplement-20261022/`）——两份互证互备，见 `docs/backup/`。
