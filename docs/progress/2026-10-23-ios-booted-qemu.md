# 进展日志

## 2026-10-23 — 🎉 M1 达成：iOS 16.5 在 QEMU 里开机进桌面

**目标里程碑（"先到 iOS 开机"）已在 QEMU 链路达成。** 屏幕截图存证：[evidence/2026-10-23-qemu-ios-homescreen.png](evidence/2026-10-23-qemu-ios-homescreen.png) ——SpringBoard 完整启动：状态栏时钟 12:46 在走、Weather/Calendar 大组件、FaceTime/照片/邮件/时钟/地图/设置等图标全部渲染、底部 Dock 与 Search 胶囊都在。

### 复现路径（macOS 原生，无 Docker）

```sh
brew install sevenzip coreutils qemu dtc
source tools/mac-env.sh
cd hackios-xnu-kernel                # k90-port 分支（子模块）
common/setup.sh                      # 双仓合一棵树
ios165/fetch.sh                      # 素材：2.9G rootfs + 26M cryptex + 13M App + 2.6G DSC
common/build.sh qemu-virt            # 出 root.apfs(4M) + system.apfs(2.3G) + loader.efi
qemu/run-ios.sh 900 -display cocoa   # 带窗口启动（Mac 用 cocoa，不是 gtk）
qemu/screendump.sh                   # 截图（经 monitor 4444）
```

### 过程中打掉的 5 个宿主差异（都在 k90-port 分支，均已推送）

1. `os.copy_file_range` 是 Linux-only CPython API → 加读写循环回退
2. PREBUILT 模式硬 `cp` 一个 prebuilt 里不存在的程序（`drawable_test`）→ 逐个判存在
3. `timedatectl` 在 macOS 下 `set -e` 直接杀死构建 → 回退 `/etc/localtime`，再退 UTC
4. GNU `sed -i`（BSD 需要备份后缀）→ 统一改临时文件写法
5. `qemu/run-ios.sh` 的 `/proc/meminfo` 内存闸门在 mac 上读不到——已容错（缺省放行）

`tools/mac-env.sh` 负责：GNU coreutils PATH、`7zz→7z` 软链、AAVMF pflash 固件路径（从 brew qemu 拷 64MiB 单元 + 空白 VARS，EDK2 首启自初始化）。

### 备注

- `-display cocoa`（macOS 原生窗口）可用；上游文档写的 `-display gtk` 是 Linux 的。
- 交互：鼠标左键按住拖动 = 手指触摸（`qemu/touch.py` 走 QMP 4445 可脚本化），L/H/方向键 = 锁屏/Home/音量。
- Docker 镜像（`hackios-dev:latest`，已换 USTC apt 源）同步构建完成，留作对照环境。构建与运行都在 macOS 上跑通后，Docker 已非必需路径。

### 下一步

- M2（真机）：`docs/analysis/uefi-sm8750.md` 的排序执行——Mu-Silicium PakalaPkg 基座出 annibale pkg；gbl-chainload-myron 作快速验证入口。
- 顺手可做：`ios165` 素材与 apfs 产物已就绪，任何真机内核改动都可直接复用这条构建线。
