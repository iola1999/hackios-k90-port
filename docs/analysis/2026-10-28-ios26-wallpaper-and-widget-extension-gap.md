# 壁纸与小组件的扩展发现缺口复核（2026-10-28）

目标是判定 K90 上壁纸全黑、桌面小组件停在「Waiting…」的缺口位置。第一版把原因归到「运行时 `/private/var` 是内存盘、模板 `etc/var.skel` 里没有 `staged_system_apps`」，经核对构建产物与 QEMU 对照，这个结论不成立。第二版把原因归到「launchd 缓存的 `AppExtensions` 没有跟着应用搬家改写」，也不成立。现在排除掉这两层之后，剩下的证据指向解锁时机与扩展注册就绪之间的先后，属于我们自己的手势脚本时序，修法落在脚本而不在镜像内容。本文保留两次排除的过程，因为两条错误路径都会在下一轮被重新提起。

## 1. 已排除的两层

结论先写：

- `staged_system_apps` 不是缺口。
  - 构建时 `ios26/select-system.py` 已经把目的路径写成 `Applications/`，`build.sh` 只是把提取出来的文件搬到那里。
  - 直接读 `userland/system26.apfs`，`/Applications` 里 `Photos.app`、`Camera.app`、`Music.app`、`Weather.app`、`Passbook.app`、`MobileCal.app`、`MobileSafari.app` 都在，`Photos.app/PlugIns/PhotosReliveWidget.appex` 与 `Camera.app/PlugIns/LauncherControlExtension.appex` 也都在。
  - 运行时 `/private/var` 是内存盘这件事仍然成立（`mount a memory filesystem on /private/var`，129 目录 10 文件 2 链接，来自 `etc/var.skel`），但它盖住的只是系统镜像里那份空的 `private/var`，对这 50 个应用没有影响。
- launchd 缓存的 `AppExtensions` 不是缺口。QEMU 对照用的是同一份系统镜像（SHA-256 `d11083be02820507f5639e0a29c6f35256a48d1d4f3cf4cd265eb4b8e346efe4`）和同一份 733 条 `AppExtensions`，它成功拉起了 8 个扩展进程，其中 7 个的 appex 根本不在那份清单里。

## 2. 缓存的实际来源与构成

iOS 26 的 launchd 从 `/System/Library/xpc/launchd.plist` 取任务，不读 `LaunchDaemons` 目录。这份缓存由 `hackios-xnu-kernel/userland/mkcache.py` 生成：读 Apple 自己的缓存（`ios26/rootfs/System/Library/xpc/launchd.plist`，2,280,931 字节），把 `LaunchDaemons` 整体换成 `mkjobs.py` 的输出，`AppExtensions`、`AppRemovalServices`、`Symlinks`、`SystemLibraryTreeState`、`VersionNumber` 原样保留。产物 785,328 字节，`LaunchDaemons` 29 条。

733 条 `AppExtensions` 的分布是 584 条在 `/System/Library/...`、149 条在 `/Applications/...`、0 条在 `/private/var/staged_system_apps`。那 584 条不是坏条目：拿它们逐条去 `rootfs` 里找 `Info.plist`，728 条找得到，5 条找不到。所以「584 条不可解析」这个说法是我上一版数错分组得出的，站不住。

真正没有被这份清单覆盖的是被搬进 `/Applications` 的那 50 个应用的扩展：Photos、Camera、Music、Weather、Passbook、MobileCal 等，Apple 的缓存对它们 0 条。

- 原因是 Apple 生成缓存时这些应用还在 `private/var/staged_system_apps` 里没有安装。
- 如果要从我们这边补齐，`_infoPlist` 生成镜像内 plist 的规则可以从现有 728 条反推：它是真实 `Info.plist` 去掉固定的一批键（`DTSDKBuild`、`CFBundleSupportedPlatforms`、`DTXcodeBuild`、`UIRequiredDeviceCapabilities`、`BuildMachineOSBuild`、`DTXcode`、`MinimumOSVersion`、`DTPlatformVersion`、`DTSDKName`、`DTCompiler`、`DTPlatformBuild`、`DTPlatformName`、`UIDeviceFamily` 等 728/728 全部命中的键），缓存里没有出现任何磁盘上没有的键。

这一项现在不需要做。

## 3. QEMU 对照否掉了缓存假设

`out/ios26-resume/chronod-qemu/` 那一轮只有根盘任务集不同（只加了 `com.apple.chronod`），根盘缓存同样是这份 733 条 `AppExtensions`、28 条 `LaunchDaemons`。

- 日志里被拉起的扩展进程有 `SafariWidgetExte[165]`、`MusicWidgets[166]`、`PassbookWidgetsE[167]`、`BarcodeScannerWi[168]`、`TVWidgetExtensio[169]`、`TypeToSiriWidget[170]`、`HomeWidgetLockSc[171]`、`WorldClockWidget[172]`。
- 按 `CFBundleIdentifier` 回查那份缓存，`com.apple.Music.MusicWidgets`、`com.apple.mobilesafari.SafariWidgetExtension`、`com.apple.Passbook.PassbookWidgets`、`com.apple.tv.TVWidgetExtension`、`com.apple.Home.HomeWidget`、`com.apple.weather.widget`、`com.apple.mobileslideshow.PhotosReliveWidget`、`com.apple.camera.LauncherControlExtension` 八项里只有 `com.apple.BarcodeScanner.BarcodeScannerWidgetExtension` 在清单上。

扩展能不能启动因此和这份清单无关，补齐清单也解决不了 K90 的报错。

## 4. K90 与 QEMU 剩下的差异是时间

两边同一份系统镜像、同一份缓存。差别在第一次查扩展身份的时间点。

QEMU 的 chronod 在 10:02:24 起来，第一批扩展进程出现在 10:11:58，`getAllDescriptors` 的看门狗报错紧随其后（10:12:05 起）。整轮 600 秒，扩展启动落在内核时间 589.7 秒。日志里 SpringBoard 第一次报 `isUnlocked: 1` 是 10:05:53，chronod 第一次是 10:11:55，所以扩展启动和解锁之间还隔了几分钟，这轮也不能用「解锁触发」解释。

K90 的五轮都短得多。`bbmetal21` 的 launchd 在 23:03:48.9 起，`chronod` 在 23:03:56.815（开机后约 8 秒）报 `[extensions] Extension not found for com.apple.camera::com.apple.camera.LauncherControlExtension`，23:04:27.487（约 39 秒）报 `com.apple.mobileslideshow::com.apple.mobileslideshow.PhotosReliveWidget` 找不到，两条都跟着 `ChronoCoreErrorDomain (1) "Unknown extension process"` 与 `0 retries remaining`，下一次尝试被排到次日。`bbmetal25` 一样：launchd 00:17:30 起，00:17:37.454 与 00:18:08.198 是同样两条。`bbmetal21`～`bbmetal25` 五轮全都只有这两条。

`bbmetal20`／`bbmetal21` 用的诊断脚本 `jobs/rc.jobs.ccdrag` 写着「Unlock at 32 s」，第一句是 `wait 32 swipe …`；日志里 23:03:56.446 的 `SBCoverSheetPrimarySlidingViewController` 转场在解锁之前，不能当作解锁时刻。所以 K90 的第一批扩展查询发生在开机后 8 秒与 39 秒，QEMU 发生在约 580 秒，两者差了将近十分钟的系统就绪时间。

最符合的解释是：K90 在 `pluginkit.pkd` 与 LaunchServices 把 259 个应用的扩展登记完之前就去问，拿到「没有这个扩展」，随后按一天的重试间隔退避，300～420 秒的轮次里不会再试。

## 5. 未定性与下一步

这个解释覆盖了现有全部证据，但还没有直接证明。缺的一步是「让第一次扩展查询晚到系统就绪之后，扩展能不能起来」。

最省的验证不需要改任何镜像内容：同一个根盘、同一个系统盘，只把 `jobs/rc.jobs.ccdrag` 的第一句从 `wait 32` 改成 `wait 240`（其余手势与截图间隔不动），跑一轮 420 秒。判据三条：启动日志里出现 `.appex` 宿主进程（进程名形如 `MusicWidgets`、`PhotosReliveWidget`）；chronod 不再出现 `[extensions] Extension not found`，改出现 `[descriptor]` 或 `[placeholder]` 的后续行；截图里小组件不再是纯白块。若推迟后仍然报 `Extension not found`，这个假设作废，下一步要抓 `pkd` 与 `lsd` 的日志（当前串口只转发到 6 个进程的默认级别 os_log，`pkd` 一行都没有），而不是继续在缓存或 `var.skel` 上找。

需要说明的是这条路径的收益有限：即使扩展起来了，QEMU 那一轮的 `getAllDescriptors` 也撞上看门狗、没拿到 descriptor，壁纸与小组件内容还有下一步。是否花这一轮由 lead 决定。

## 6. 记录更正

§44 写「`bbmetal21` 在根盘里加了两个 launchd job」。核对 `bbmetal20` 的证据目录，它 22:57:29 那一轮的日志里就已经有 `PosterBoard[18]` 与 `chronod[8]`，`LaunchDaemons` 清单与 `bbmetal21` 逐行相同，`com.apple.posterboardservices.services` 的失败查找也已经是 0 次。两个 job 在 `bbmetal20` 之前就进了根盘。

`LaunchDaemons` 是 29 条（含 4 条 `com.redwood.*`），不是 27 条。系统镜像里有 628 个 `LaunchDaemons`、32 个 `LaunchAngels`，日志里每一条 `failed lookup` 都对得上一个存在于镜像却没进缓存的 plist：`com.apple.sleepd.sleepserver`（SpringBoard 331 次）对 `com.apple.sleepd.plist`，`com.apple.replicatorservices`（chronod 17 次）对 `com.apple.replicatord.plist`，`com.apple.biome.access.user`（102 次）对 `com.apple.biomed.plist`，`com.apple.duetactivityscheduler` 对 `com.apple.coreduetd.plist` 与 `com.apple.duetexpertd.plist`。这些是任务清单本身的缺口，与扩展能否启动没有直接关系。
## 7. 缓存补齐后的实测：壁纸仍是黑的，小组件仍是白块

`bbm29`（启动参数补回 `rootdev=md0 launchd_unsecure_cache=1`、`failed lookup` 整轮 0 次）的桌面已经完整：15 个应用图标、两个带名字的小组件（Weather、Calendar）、4 个 Dock 图标、两页与页码圆点。

壁纸这一项没有变化，仍然是黑的。同一帧 `shot-03226` 取样：图标之间的背景、顶部状态栏区域、小组件与 Dock 之间的区域，像素值全部是 `(0, 0, 0, 255)`；只有 Dock 自身底色是 `(47, 47, 47, 255)`。也就是说桌面背景被画成了纯黑，没有壁纸图像参与合成。

小组件这一项也没有变化：两块白块有了名字，内部没有内容。第三轮实测里 `Extension not found` 与 `Unknown extension process` 都归零、`chronod` 读到真实扩展名（`AdaptiveMusicWidget`、`CalendarWidget`、`FindMyWidgetItems`），但 420 秒内没有宿主进程被拉起。所以扩展身份查找这一段通了，扩展进程拉起这一段还没有观察到。

结论分两行写：壁纸未达成：桌面背景仍是纯黑，缓存补齐没有带来壁纸；小组件未达成：名字出现了、白块内部仍无内容，缺口在扩展进程拉起。

## 8. PosterBoard 是被拉起的，缺口在记录与渲染

`kernel-12377-attr-bbm28` 的 launchd user 域日志里有完整启动过程：`pending spawn, domain in on-demand-only mode` → `WILL_SPAWN` → `spawn scheduled` → `spawning` → `launching: speculative` → `Successfully spawned PosterBoard[17]` → `service spawned with pid 17`。所以「PosterBoard 没有被拉起」这条排除，镜像里 `_ExperimentalNonLaunching` 被去掉、`RunAtLoad` 为真之后这个 job 确实跑起来了。

壁纸仍然是黑的，缺口因此落在两处之一：PosterBoard 起来之后没有可用的 poster 记录（本文 §7 查到的记录存在它容器里的 SQLite，空骨架里没有），或者记录有了但渲染方（`com.apple.WallpaperKit.CollectionsPoster` 这个 `com.apple.posterkit.provider` 扩展）没有被宿主拉起。

同一轮的 38 个被拉起进程里没有一个 `.appex` 宿主。这一条是「宿主未拉起」的第一次记录，但要注意样本条件：那一轮桌面只有 2 个图标，launchd 缓存还没有补齐。

## 9. 宿主进程被拉起后立刻消失：74 个进程与一条断言失败

`bbm29` 的内核日志里有 74 个不同的 `.appex` 宿主进程各留下一条 `triggered unnest of range 0x203200000->0x205400000 of DYLD shared region in VM map …`，包括 `CalculatorWidget[173]`、`HomeWidget[99]`、`SleepWidgetExten[100]`、`TypeToSiriWidget[98]`、`AdaptiveMusicWid[143]`、`BarcodeScannerWi[174]`、`FindMyWidgetItem`、`FitnessWidget`、`CalendarWidgetEx`、`HealthBalanceWid`。桌面上两块小组件的 provider 都在这个名单里。

随后它们不存在了。`chronod` 的原文是 `[session] [com.apple.calculator.CalculatorWidget] Unable to create new WidgetExtensionSession because begin request failed: … Code=4 "Failed to acquire assertion for pid: 173"`，最内层是 `RBSAssertionErrorDomain Code=2 "Specified target process 173 does not exist"`。RunningBoard 给这个 pid 挂断言时它已经不在。

所以「ExtensionKit 宿主从来没有被拉起」这条要撤回：宿主是被拉起的，问题在起来之后立刻退出。判据相应改成两栏——有没有 spawn 记录（有），宿主有没有活过断言窗口（没有）。

壁纸这一侧的 provider 是 `com.apple.WallpaperKit.CollectionsPoster`（扩展点 `com.apple.posterkit.provider`），走同一条 ExtensionKit 宿主路径。它是否同样起完就退，日志里没有它的名字，需要看 PosterBoard 一侧有没有同样的 `Failed to acquire assertion`。在这条确认之前，「壁纸与小组件同一个缺口」只是假设。

那 74 条内核文本里被降级的区间是 `0x203200000->0x205400000`，约 34 MB，内核的措辞是「debugger 常见，会增加内存占用」。它出现在每一个启动进程上（`analyticsd`、`mount`、`fsck`、`xpcproxy` 也有），说明内核在子进程身上对共享缓存的处理比 macOS 更激进。它是不是宿主退出的原因，本文不作判断。

## 10. 一个宿主的完整生命周期，以及退出原因为什么查不到

挑 `CalculatorWidget[173]`（`chronod` 里 `com.apple.calculator.CalculatorWidget`，桌面上没有它，但它与桌面那两块走同一条路径）把日志里所有相关行摊开，全部只有三条：

1. 内核：`CalculatorWidget[173] triggered unnest of range 0x203200000->0x205400000 of DYLD shared region in VM map 0x1a803a2347d14dcb`。
2. `02:54:48.587624 chronod[51:1110] [default] Failed to create extensionProcess for extension 'com.apple.calculator.CalculatorWidget' …`，最内层 `RBSAssertionErrorDomain Code=2 "Specified target process 173 does not exist"`。
3. `02:54:48.587678 chronod[51:1110] [session] … Unable to create new WidgetExtensionSession because begin request failed`。

没有第四行。整轮日志里没有任何 dyld 加载失败、没有 per-process 退出记录、没有退出码或信号。

**唯一与退出有关的记录是崩溃通知失败**：`Failed to send exception EXC_CORPSE_NOTIFY. error code: 5 for pid N`，出现过的 pid 是 36（backboardd 重起时）、103、140（`LauncherControlE`）、146、150、172（`LauncherControlE`）、173。`error code: 5` 是 ESRCH，意思是通知发出去时目标已经不在，也就是**没有崩溃报告器在听**。另外 pid 173 那条落在 uptime 360.47 秒（约 02:58:30），比 `chronod` 发现它不存在晚了约 3.7 分钟，pid 会被复用，所以不能把那条崩溃通知一定归给 `CalculatorWidget`。

**为什么查不到原因**：镜像里有 `/System/Library/CoreServices/ReportCrash`（479,376 字节）与 `com.apple.ReportCrash.plist`，缓存里也有这个 job，但它不在我们打包的 31 条 job 里。没有崩溃报告器，`EXC_CORPSE_NOTIFY` 就没人接，崩溃原因不落盘。要拿到原因，得把这个 job 加进载荷，崩溃日志会写到 `/private/var/mobile/Library/Logs/CrashReporter`。

**一条不构成原因的观察**：`triggered unnest of range …` 出现在每一个启动的进程上（`analyticsd`、`mount`、`fsck`、`xpcproxy` 都有），系统还能跑到出桌面，所以它不解释宿主退出。它是「我们的内核在子进程身上对共享缓存的处理比 macOS 更激进」的实证，将来查内存占用会用到。

## 11. 探针实测：PosterBoard 在服务，poster 存储目录不存在

`kernel-12377-attr-biomed` 那轮的 `lsprobe` 在 t=60 秒给出四行，其中一行是壁纸的判据：

```
lsprobe t=60 poster_service=present kr=0
lsprobe t=60 files_applications=260 files_staged=-1 mobileinstallation_dir=-1 iconstate=1 icondomain=1 posterboard_dir=-1 posterboard_db=0 pluginkit_dir=-1 containers=-1
lsprobe t=60 workspace=258 workspace_extensions=296
lsprobe t=60 mobileinstallation=symbol-missing
```

- `poster_service=present`：`com.apple.posterboardservices.services` 有订阅者，PosterBoard 活着并接受连接。与 §8 的 spawn 记录一致。
- `posterboard_dir=-1`：PosterBoard 的存储目录不存在。
- `posterboard_db=0`：那个目录下没有任何文件，也就是没有 SQLite 库。

所以壁纸黑的原因是「有一个能工作的 PosterBoard，没有任何 poster 记录可渲染」，不是服务缺失、不是 PosterBoard 没被拉起。这与 §7 查到的「记录是 PosterBoard 写在它容器里的 SQLite」对得上。

同一轮 t=60 的另外三条对本文件之外也有意义：`workspace=258`（LaunchServices 看到 258 个应用）、`workspace_extensions=296`（296 个扩展身份），说明扩展与应用的身份查找这一层是通的；`mobileinstallation=symbol-missing` 说明 `MobileInstallationLookup` 这个符号在本环境不可用，探针改走 `LSApplicationWorkspace`。

一条限制：t=300 那次探针的输出没有出现，日志里有 t=60 的六行、没有 t=300 的任何一行。这一轮的截图也全部停在锁屏（黑底转圈），所以上述结论只用 t=60 的数据，没有与画面交叉验证。

## 12. 宿主崩溃已到内核的崩溃循环阈值

`kernel-12377-attr-linkd` 那轮的内核日志里有四条崩溃记录：

```
Process[198] crashed: BarcodeScannerWi. Too many corpses being created.
Process[199] crashed: CalculatorWidget. Too many corpses being created.
Process[200] crashed: LauncherControlE. Too many corpses being created.
Process[201] crashed: BarcodeScannerWi. Too many corpses being created.
```

`Too many corpses being created` 是内核的崩溃循环保护：短时间内崩溃的进程数超过阈值后，内核不再为后续崩溃生成 corpse。§10 那条 `Failed to send exception EXC_CORPSE_NOTIFY. error code: 5` 因此有了更准确的读法——崩溃通知发不出去，原因是内核已经停止生成 corpse，与「没有崩溃报告器」是两件叠加的事。

这对 `ReportCrash` 的定位有影响：它能收第一批崩溃，但崩溃一旦密集到触发阈值，后续崩溃就不再有 corpse，`ReportCrash` 也收不到。所以它只有在崩溃开始之前就已运行时，才拿得到第一份日志。

同一轮还有一件影响判读的事实：`backboardd` 在 03:40:12 与 03:41:51 各重起一次（`start clearing the board for /usr/libexec/backboardd respawn`）。所以截图里先出现锁屏（`shot-01409`，3:40 的时钟）、随后回到黑底转圈（`shot-01995`），后者是 backboardd 重起后的画面，不是开机画面。锁屏背景同样是纯黑，与 §11 的「没有 poster 记录」一致。

崩溃名单里 `BarcodeScannerWi` 与 `LauncherControlE` 各两次、`CalculatorWidget` 一次，三个都是 `.appex` 宿主——崩溃的是宿主这一类，不是某一个特定扩展。

## 13. 线程状态 dump：卡住期间取证的工具

`backboardd` 停三秒这条，缺的是「那三秒里每个线程停在哪」。为此加了两半：

- 内核：`out/xnu12377/osfmk/kern/redwood_threads.c`（提交 `ade518a` 建在 `bsd/dev/`，`b68408d` 移到 osfmk），注册 `kern.redwood.thread_dump`。写一个 pid，打印该进程每个线程一行 `tl: td <pid> tid <n> state <n> wait <ptr> pri <n> pc <hex>`，头一行给 `threads`，尾一行给条数。字段在他线程的锁之外读，因为等锁的 dump 会晚于卡住结束。
- 用户：`redwoodmetal_commandbuffer.inc`（提交 `c0dce36`）里的观察线程。检查放在 commit 的工作循环里只能在阻塞调用返回之后才发现，所以改成每 250 ms 检查一次「commit 在跑且工作循环超过 2500 ms 未前进」，命中时写一次 sysctl，同一个 commit 只写一次。

判读分三类：全部线程同一个 `wait` 地址（等同一个事件）、`wait` 不同但 `pc` 落在同一函数段（同一条串行路径）、`state` 不在等待态而 `pc` 不动（自旋或被挂起）。

内核这一半在本机无法编译验证：这棵树没有内核的 `compile_commands.json`，`xnu-build.sh` 是 Linux 上的构建，`out/xnu12377/BUILD/obj/...` 是从那边同步回来的产物。用户那一半用 `xcrun clang -c -target arm64-apple-ios14` 编过，0 错误。

### 13.1 为什么文件在 osfmk 而不是 bsd/dev

第一版放在 `bsd/dev/redwood_threads.c`，device 用 `compile_commands.json` 里 `redwood_input.c` 的命令单独编它，报了 18 个 error：`struct task` 是前向声明（完整定义在 `osfmk/kern/task.h:117` 的 `#ifdef MACH_KERNEL_PRIVATE` 段里）、`task_lock` 与 `task->threads` 都不可见，而这棵树没有 `kern/task_private.h` 可补。这是结构问题：BSD 侧的文件只带 `XNU_KERNEL_PRIVATE`。

所以实现移到 `osfmk/kern/redwood_threads.c`，在 `osfmk/conf/files` 注册。移动时同时去掉了唯一一处要读 `struct proc` 私有字段的地方：头一行原本打印 `p->p_stat`（来自 `bsd/sys/proc_internal.h` 的私有段），现在只打印 `threads`。**用不到就不读私有字段**：`proc_find()` 给 pid 的进程、`proc_task()` 给任务，线程事实全部来自 task 一侧，这样这个文件只依赖一个私有条件的头，而不是两个。

`/dev/redwood-touch` 的环满丢最旧、`write()` 永不报没人读这一条记在 `bsd/sys/redwood_input.h` 的接口说明里（提交 `2cf75a5`），它当晚两次把判断带偏。
