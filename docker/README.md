# Docker 环境（M0）

linux/arm64 的 Ubuntu 24.04，装齐 HackiOS 构建 + QEMU 运行依赖（python3 / 7z / clang+lld / dtc / qemu-system-aarch64 / edk2-aarch64，另带 nasm+iasl+uuid-dev 备后将来源码编 Mu-Silicium UEFI）。QEMU 在 OrbStack 里仍是 TCG （虚拟机内无嵌套 KVM），与上游 Linux 主机一致，无影响。

iOS 交叉链也已入镜像：theos + ld64（x86_64，靠 OrbStack 的 Rosetta 跑，故镜像开了 amd64 multiarch）+ iPhoneOS16.5.sdk，版本与 sha256 钉在 Dockerfile 里，`hackios-xnu-kernel/tools/mk-mesa.sh` 开箱即用（详见 docs/analysis/mesa-rebase-2026-10.md 第 9 节）。

```sh
./build.sh            # 产出 hackios-dev:latest
./dev.sh              # 进容器，工作区挂在 /work
```

## 1. 容器内首次初始化（一棵树 = 两个 submodule）

```sh
cd /work/hackios-xnu-kernel          # k90-port 分支
common/setup.sh                      # 把 userland 仓收进 .userland.git，双仓合一棵树
ios165/fetch.sh                      # 7.4GB IPSW，解包到 ios165/extract/
userland/build.sh                    # 产 userland/{root,system}.apfs（REST=1 可换源）
```

## 2. headless 跑 QEMU（验收 iOS 开机的标准姿势）

```sh
cd /work/hackios-xnu-kernel
QEMU_RAM_GB=4 ios165/../qemu/run-ios.sh 600 &      # 600 秒后自动关机；默认无窗口
qemu/screendump.sh /tmp/ios.png                    # 锁屏截图 = “开机”证据
qemu/touch.py drag up                              # 上滑解屏；qemu/stop.sh 提前停
```

内存：每个 QEMU 实例吃宿主机 ~3GB；`run-ios.sh` 会在可用内存 <3GB 时拒启（OrbStack 虚机内存是真实上限，不够就调 OrbStack 设置或 `QEMU_RAM_GB=3`）。端口：monitor 4444 / QMP 4445（多实例 `-e QEMU_INSTANCE=1`）。

## 3. 性能备注

/workspace 走 VirtioFS，大文件（IPSW 解包、apfs 打包）可能慢；若明显拖速，把树挪进容器卷再干活，回写 git 改动即可。
