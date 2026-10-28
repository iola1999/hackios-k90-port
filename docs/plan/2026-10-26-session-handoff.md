# 会话交接（2026-10-26）：iOS 26 移植与后续路线

K90 上的 iOS 16.5 已经由 A830 绘制桌面，按负载调频、温控、触摸、按键、电量、手电和震动都有实测结果，见[GPU 桌面记录](../progress/2026-10-26-gpu-desktop-acceleration.md)与[路线图](2026-10-26-roadmap.md)。本轮按用户决定开始迁移到 iOS 26.6.2（`23G90`，iPhone 17 身份），目前只在 QEMU 中运行：内核 `xnu-12377.121.6` 能启动 iOS 26 的 arm64e 用户态，launchd 以正常模式（非恢复环境）执行全部启动任务；停止位置是 lsd 反复中止、屏幕全黑，backboardd 与 SpringBoard 是否启动待确认。iOS 26 的决策与进度见[iOS 26 移植计划](2026-10-26-ios26-port.md)。本轮的修改都还没有提交。

后续进度（10-27）：iOS 26 已在 K90 双核启动并显示软件桌面，全面屏上滑解锁、左右翻页和右上角控制中心已自动化验证；Metal 在 A830 完成计算、绘制和内容读回，SpringBoard 图标绘制仍有显示缺失及性能问题。用户暂时不方便查看设备，手指操作、顶部留白和控件大小保留为人工待确认项。软件 LK 往返第四轮通过；AIR fast FMA 陷阱已在宿主复现，精度边界修正进入 userland 跟踪源码，真机包待构建。Metal 线性对齐 getter 已在真机调用；surface 3 的 960 字节行距不满足 A830 对 RGBA16Float 的 128 字节布局要求，实际后端拒绝位置待确认。CA surface Home 登记修复通过两轮 QEMU，待真机验证。压缩开关、手势功能、帧率和完整 GPU 桌面继续验收。Wi-Fi MHI 固件下载、蓝牙、iOS 27 用户态及温控策略分析仍在队列。详细输入、参数与结果见[真机后续记录](../progress/2026-10-27-ios26-k90.md)，QEMU 适配见[启动记录](../progress/2026-10-26-ios26-qemu.md)。

本次接续：AIR fast／strict／contract-only lowering 回归三项通过；`redwood-drm` 的 IOSurface 导入错误映射覆盖 `NotFound`、`Unsupported`、`NoMemory` 三项宿主注入测试，源文件语法检查通过。当前设备为 `xnuloader` idle。新增源码尚未进入设备库；现有 AIR 75c0 包仍使用旧 AIR 和 1125×2436 几何，本轮未运行。容器中的 26.2.5 Mesa 源码与 SDK 可用，但增量构建所需的 `ninja`／`pip` 不在该容器内。Wi-Fi 固件下载前仍需确认 RID `0x100` 的 SID 及 apps SMMU 映射；当前 `mhi_pcie.c` 只读到 BHI／BHIe 和 PARF 状态。

本次后续：在隔离容器副本安装构建依赖并修正 C++ libc++ 头文件参数后，Mesa 26.2.5 交叉构建成功；新 AIR 与导入诊断库通过签名和 APFS／XNUP 差异检查，并在 K90 以 iOS `23G90`、V57、`fbwidth=1206 fbheight=2622 fbpitch=460` 运行约 180 秒。截图显示应用图标内容完整，天气与日历组件为空白；CPU 温度最高 73.6 °C，采样窗口 39～60 帧/秒，最长帧 83 ms；图标服务继续报告软件渲染错误，日志没有新导入错误行。停止后返回 `hung-held`，已按 playbook 获取挂死快照、软件复位并恢复 A 槽重试数；loader 当前为 idle、RAM 为空。详细参数、哈希和数据见[真机记录第 36 节](../progress/2026-10-27-ios26-k90.md#36-新-air-与-原生尺寸组合包真机验证)。

## 1. 目标描述

可直接作为下一轮 goal 使用的描述：

> 在 REDMI K90（`annibale`，SM8750）上持续完善 HackiOS。iOS 16.5 的 GPU 加速桌面保持可启动，并继续改进流畅度、显示正确性、功耗与温度；按[路线图](2026-10-26-roadmap.md)分阶段实现后续功能：系统迁移到 iOS 26.6.2（`23G90`，身份 iPhone 17 `iPhone18,3`／`V57AP`，内核基于 `xnu-12377.121.6`），先在 QEMU 中以软件渲染进入 SpringBoard，再上 K90 真机，之后决定 GPU 路线（`AccelServer` 换用 OGL 渲染器，或 Metal／Turnip）并评估 iOS 27 用户态在同一内核上的差异；外设继续推进 Wi-Fi（MHI 固件下载）和蓝牙。验收：性能与省电（60 帧/秒以上，报告帧率和长帧，随负载调频、空闲降频、温控降频，开机不固定大核约 3 GHz）；显示与稳定性（壁纸、翻页、控制中心反复验证，偶发断触可暂缓）；路线实施（落实路线图，Turnip／Metal 与系统升级分别验收，推进外设）；无人值守验证（结论附版本、参数和实测结果，需要人工确认的项目单独列出）。

执行时的约束：

- 温度：真机测试远离 90 °C，现行保护为 70 °C 降档、60 °C 以下恢复；宁可不完整验证，也不触发高温。
- 调频：优先由操作系统决策（路线图第 5.4 节的 CLPC 分析与复刻），无法避免时才沿用本项目自己的策略。
- 系统版本：iOS 27 内核源码未公开时用 26；若确认 27 的适配工作量小，可以改用 27。
- 隐私与提交：遵守 `AGENTS.md` 第 3 节；提交和推送需要用户同意，推送顺序先内核仓后父仓库。
- 主机：macOS 没有 `timeout`（用 coreutils 的 `gtimeout`）；不做全盘搜索；`rm` 被替换为移到废纸篓，需要释放空间时用 `/bin/rm`。

## 2. 当前进展

### 2.1 K90 上的 iOS 16.5

这是当前可用的环境，截止状态见[路线图第 7 节](2026-10-26-roadmap.md#7-验收目标与本轮截止位置)与总账中的 Claude 条目。控制中心下拉 58.7 帧/秒、翻页主动画 58.8～60.8 帧/秒；CPU 与 GPU 按负载调频并有 70 °C 温控；Turnip 在 iOS 上通过设备枚举、计算和三角形绘制读回；Wi-Fi 的 PCIe 链路已通并读到 WCN7850 的 MHI 寄存器（内核 `fadb3a2`）。本轮没有在真机上运行新内容。

### 2.2 iOS 26 移植（QEMU）

| 步骤 | 状态 | 说明 |
|---|---|---|
| 12377 内核构建 | 完成 | macOS 本机构建，补丁迁移见移植计划第 3 节 |
| 内核堆与写合并映射 | 完成 | 11 GB 内存窗口可以启动，见移植计划第 1 节 |
| 系统文件提取 | 完成 | `ios26/fetch.sh` 从解密的 IPSW 镜像生成根文件系统与 arm64e 共享缓存 |
| arm64e 用户态 | 完成 | 共享缓存与 dyld pager 的认证指针按普通指针处理，QEMU CPU 用 `neoverse-n2` |
| launchd 任务信任 | 完成 | stage0 把任务目录绑定到 `/System/Library/LaunchDaemons` |
| 正常启动 | 完成 | `rootdev=md0`，无签名 launchd 缓存加 `launchd_unsecure_cache=1`，自有程序 ad hoc 签名 |
| iPhone 17 身份 | 完成 | `IDENTITY=v57`，设备树取自 IPSW，chip-id 0x8150、board-id 0x08 |
| usermanagerd | 完成 | 写入空的第 1 版 persona 清单后不再退出 |
| lsd | 未解决 | 180 秒内中止 18 次，见第 2.3 节 |
| backboardd／SpringBoard | 待确认 | 正常启动的日志里没有这两个进程的记录 |
| 显示 | 未开始 | 截图全黑；`MiniIOMobileFramebuffer`／`MiniIOSurface` 的选择子仍按 iOS 16.5 |
| 注入库（arm64e） | 未开始 | 当前用 `INJECT=""` 构建，iOS 26 进程不加载 `libredwood*` |
| K90 真机 | 未开始 | 需要先在 QEMU 中看到界面 |

### 2.3 停止位置

最后一次运行（QEMU，180 秒，`IDENTITY=v57`，`CMDLINE="rootdev=md0 launchd_unsecure_cache=1"`）：init 的 36 项检查全部通过；keybag、usermanagerd、`launchd_cache_loader` 等启动任务执行完毕，日志出现 `Using unsecure cache` 与 `Cache sent to launchd successfully`；日志中可见 distnoted、wifid、powerd、containermanagerd、MobileGestaltHelper 在运行。lsd 每次都在同一位置中止，内核记录为 `userabort: lsd[48] aborts, shared cache slide 0x1ce68000; called from: 0x1abf42fcc 0x19e5ef390 0x19e5f541c 0x1dae901e4 0x1dae862e0 0x19e527c38 ...`，减去 slide 后在共享缓存中的地址依次为 `0x18f0dafcc`、`0x181787390`、`0x18178d41c`、`0x1be0281e4`、`0x1be01e2e0`、`0x1816bfc38`，尚未符号化。正常启动时 launchd 自身的日志没有输出到控制台，无法从日志判断用户域任务是否启动。

## 3. 仓库与产物状态

| 仓库 | HEAD | 状态 |
|---|---|---|
| 父仓库 | `4695135` | 本轮修改了 `docs/plan/2026-10-26-ios26-port.md`，新增本文；工作区里还有本轮之前未提交的文档修改和 4 个未跟踪文档 |
| `hackios-xnu-kernel` | `fadb3a2` | 有未提交修改，见下文 |
| `hackios-xnu-kernel` 工作树中的用户态仓库（`.userland.git`） | `31f5925` | 有未提交修改；该检出落后于父仓库子模块 `hackios-xnu-userland` 的 `24641cc` |
| `hackios-xnu-userland`（父仓库子模块） | `24641cc` | 本轮未修改 |

内核仓的未提交修改：

- `xnuloader/`：payload 条目 `identity` 与 `mkpayload.py --identity`，身份表 `identities[]`（`loader_01_base_log_dt.inc`），`mkidentity.py --prefix`，loader 接受 `rootdev=` 作为自带根设备。新文件 `xnuloader/identity_v57.h` 被 `.gitignore` 的白名单挡住，提交时要加 `!/xnuloader/identity_v57.h`；`loader.c` 已包含它，缺这个文件时 loader 无法构建。
- `qemu/run.sh`、`qemu/run-ios.sh`：`QEMU_CPU`、`KERNEL`、`MEMSIZE`、`IDENTITY`，内存大于 12 GB 时扩大 `ram.img`。
- `xnu/files/` 中与 8796 共用的 5 个文件：`kern_minimac.c`、`generic_arm64_support.c`、`loader_return.c`、`user_exception_trace.c` 为 12377 补充头文件和接口差异，`mhi_pcie.c` 把 `__bzero` 改为 `bzero`。改动后没有重新构建 8796 内核，下次真机运行前要先确认 8796 仍能构建。
- `xnu26/`（补丁、构建脚本、`export.sh` 导出的 71 个补丁和 2 个文件）没有进入 `.gitignore` 白名单，目前不受版本控制。内核工作树 `out/xnu12377`（基于 `aec10a9`）的修改已由 `XNU26_SRC=$PWD/out/xnu12377 xnu26/export.sh` 导出到 `xnu26/patches/`。

用户态仓库的未提交修改：`userland/build.sh`（`IOS=../ios26`、launchd 缓存、ad hoc 签名、persona 清单）、`userland/src/stage0.c`（绑定 LaunchDaemons 与 xpc 目录）、新文件 `userland/mkcache.py`（被工作树根目录的 `.gitignore` 挡住，提交时要 `git add -f`）、`ios26/fetch.sh` 与指向 `ios165/select-system.py` 的符号链接（`ios26/` 不在白名单）。`userland/rc.jobs`、`userland/rc.jobs.unlock` 与 `tools/mesa/rebase-26/0003-*.patch` 的修改早于本轮，来源未核对，不要随本轮提交。

产物（都在 Git 忽略的目录）：

- `out/ipsw/v57/26/`：解密后的 `os.dmg`、`systemos.dmg`、`appos.dmg`，`BuildManifest.plist`，`DeviceTree.v57ap.bin`。
- `ios26/`：`rootfs/`、`cryptex/`、`cryptex-app/`、`23G90__iPhone18,3/`（共享缓存）。
- `userland/root26.apfs`、`userland/system26.apfs`。
- `out/xnu12377/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837`。
- `xnuloader/loader.efi`（含身份选择）。
- 运行日志与截图在主机临时目录 `/tmp/x26tools/`（`q26-*.log`、`q26-y.png`），重启主机后丢失；需要保留的结论已写进本文和移植计划。

## 4. 构建与运行（macOS 主机）

主机临时目录里的辅助脚本重启后会丢失，按下面的说明重建：

- `macshim/`：`stat`、`timeout`、`realpath` 分别链接到 Homebrew coreutils 的 `gstat`、`gtimeout`、`grealpath`；`cp` 是去掉 `-u` 参数后调用 `/bin/cp` 的脚本。使用时放在 `PATH` 最前面。
- 静态程序（`init`、`stage0`）：`xcrun -sdk iphoneos clang -arch arm64 -Os -static -nostdlib -ffreestanding -fno-stack-protector -fno-builtin -Ilibmini`，先编译 `libmini/mini.c` 与 `libmini/start.S`，链接参数 `-Wl,-e,_start -Wl,-pagezero_size,0x100000000`，产物复制到 `userland/obj/` 后用 `PREBUILT=1` 构建镜像。

命令（在 `hackios-xnu-kernel/` 下执行，`PATH` 先加入 `macshim`）：

```sh
XNU26_SRC=$PWD/out/xnu12377 xnu26/build-macos.sh -j16 -Otarget          # 内核
PATH=/opt/homebrew/opt/llvm/bin:/opt/homebrew/opt/lld/bin:$PATH xnuloader/build.sh   # loader
(cd userland && IOS=../ios26 PREBUILT=1 INJECT="" ./build.sh)          # root26.apfs、system26.apfs
QEMU_EFI=/opt/homebrew/share/qemu/edk2-aarch64-code.fd QEMU_VARS=$PWD/qemu/vars.fd \
QEMU_CPU=neoverse-n2 QEMU_RAM_GB=14 MEMSIZE=300000000 IDENTITY=v57 \
IMG=userland/system26.apfs ROOT=userland/root26.apfs \
KERNEL=out/xnu12377/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837 \
CMDLINE="rootdev=md0 launchd_unsecure_cache=1" qemu/run-ios.sh 180 > LOG   # 日志在运行结束后一次写出
qemu/screendump.sh OUT.png                                             # 运行期间截图
```

`CMDLINE` 加 `systrace=1 systrace_name=NAME` 打印指定程序的 exec 失败原因。`rd=md0` 会让 launchd 进入恢复环境，iOS 26 一律用 `rootdev=md0`。

## 5. 后续计划

### 5.1 iOS 26 到 SpringBoard（按顺序）

1. 经用户同意后提交本轮修改：内核仓的 `.gitignore` 白名单加入 `xnu26/` 与 `xnuloader/identity_v57.h`，用户态仓库加入 `ios26/fetch.sh` 并 `git add -f userland/mkcache.py`；提交前按 `AGENTS.md` 第 3 节检查暂存差异。确认 8796 内核仍能构建。
2. 让 launchd 正常启动时的日志可见（检查 `QUIET`、launchd 的标准错误去向，或改读 logd 的输出），确认 backboardd 与 SpringBoard 是否启动、用户域 `user/501` 何时建立。
3. 定位 lsd 中止：用共享缓存符号化第 2.3 节的调用栈，找出中止前检查的条件。
4. persona：`/sbin/launchd` 的 `sub_100034354` 在作业 spawn 时查找 `PERSONA_SYSTEM_PROXY`（`bsd/sys/persona.h` 里 type 6），找不到只跳过 `posix_spawnattr_set_persona_np` 等三个属性，进程照常 spawn。见 [iOS 26 的安装记录、容器元数据与 persona](2026-10-28-ios26-installd-containers-and-persona.md) 第 5 节。
5. 显示：核对 iOS 26 的 IOMobileFramebuffer 与 IOSurface 框架使用的选择子和结构（16.5 的交换请求为 `0x46c` 字节），按差异修改 `MiniIOMobileFramebuffer.cpp`、`MiniIOSurface.cpp`。路线图第 3 节的静态分析表明 iOS 26 的 `AccelServer` 在没有 Metal 设备时直接使用软件渲染。
6. 注入库：用 Xcode 的 iOS SDK 按 arm64e 重新编译 `libredwood*`（SDK 中有 `IOKit` 与 `libMobileGestalt`）；`inject.c` 中按 iOS 16.5 共享缓存写死的地址都要重新确定，触摸需要的虚拟 HID 服务优先迁移。
7. 每个进程都出现 `triggered unnest of ... DYLD shared region`，会增加内存占用，原因待查。
8. `com.apple.jetsamproperties.V57.plist` 与 16.5 一样在 `mkjobs.py` 的 `DENY` 中，评估是否需要。
9. QEMU 中进入 SpringBoard 后上 K90：12377 内核需要带上 K90 的驱动与板级配置，loader 用 `IDENTITY=v57`，沿用 playbook 的温控参数。
10. 之后决定 GPU 路线（OGL 渲染器替换或 Metal／Turnip），并评估 iOS 27 在 12377 上的差异：8 个系统调用、4 个 MIG 编号、超过 6 GiB 的共享缓存、`posix_spawnattr` 新布局，见[内核接口差异分析](../analysis/2026-10-26-ios26-27-kernel-abi.md)。

### 5.2 路线图中的其他项目

按[路线图第 6 节](2026-10-26-roadmap.md#6-建议顺序)：

- GPU 收尾：拆分 `glFlush` 中 Mesa 的 CPU 耗时（每帧 7～13 ms），评估 sysmem 模式的功耗，补齐提交前后的缓存操作。
- GPU 温控的真机触发与功耗测量；CPU 持续高负载下的温控。
- 分析并复刻 CLPC，核对与 `thermalmonitord` 的职责（路线图第 5.4 节）。
- Turnip：运行 dEQP-VK 基础子集。
- Wi-Fi：读 BHI 寄存器确认网卡处于 PBL，按 Linux MHI 实现 BHI／BHIe 固件下载与状态切换，见 [PCIe 勘察记录](../progress/2026-10-26-wifi-pcie-survey.md)第 5 节。
- 蓝牙：GENI UART 与高通固件下载，见[蓝牙可行性分析](../analysis/2026-10-26-ios-bluetooth-feasibility.md)。
- 屏幕亮度（DSI 命令通道）、充电状态（依赖 ADSP）、120 Hz（低优先级，随 iPhone 17 身份评估）。

## 6. 已知问题与注意事项

- `xnu-deps/host/bin/codesign` 是 Linux 构建用的空脚本（直接返回 0），`PATH` 中排在系统 `codesign` 之前；`build.sh` 因此直接调用 `/usr/bin/codesign`。
- 用 IDA 分析 `ios26/rootfs` 中的程序会在原目录生成 `.i64`，随后被打进系统镜像；分析前先把程序复制到别处。
- `run-ios.sh` 的日志在 `loader_return_after` 到期后才写出，运行中途读不到。
- loader 的默认身份仍为 iPhone X（`d22`），16.5 的启动参数不用改。
- `platform-name` 写成 `t8150` 是按 chip-id 推定的，没有来源。
- iOS 26 的系统镜像构建约 100 秒；`obj/stage0`、`ios26/system.manifest`、`ios26/cryptex`、`ios26/cryptex-app` 比镜像新，或设置 `SYSTEM=1` 时才重建，只改小镜像（任务表、`init`、`var.skel`）约 2 秒。

## 7. 需要人工确认或决定的事项

- 本轮修改是否提交，以及 `xnu26/`、`ios26/fetch.sh`、`identity_v57.h` 进入版本控制的方式。
- 是否接受「无签名 launchd 缓存 + `launchd_unsecure_cache=1`」作为 iOS 26 的长期启动方式。
- 16.5 上待人工感知的项目沿用路线图：手电亮灯、震动手感、按键实际响应。
