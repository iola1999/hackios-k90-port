# 扩展宿主起了就退、图标缓存写不进 HEVC（2026-10-28）

`bbm29` 补齐缓存之后桌面完整（15 个应用、2 个带名字的小组件、4 个 Dock、2 个页码圆点），随后约两分钟合成停帧。本文把这一轮的两条缺口分开写、给 733 条扩展的用途清单、给 HEVC 写图标缓存的判断，并给一个「稳定但缺小组件」的降级方案。

## 1. 摘要

三个数先记住：**733 条扩展里只有 35 条会走到「拉起宿主进程」这条路**（33 个 `com.apple.widgetkit-extension` 加 2 个 `com.apple.posterkit.provider`），所以「735 条压住进程」这个怀疑的正确对象是 35 条；**图标缓存写不进 HEVC 是平台能力缺口**，列为已知限制，不是待办；**观察宿主为什么退出要靠 `ReportCrash`**，它是唯一能把退出原因写到盘上的东西。

`bbm29` 补齐 launchd 缓存之后桌面完整：15 个应用、2 个带名字的小组件（Weather／Calendar）、4 个 Dock、2 个页码圆点。约两分钟之后合成停帧。停帧之前有两个独立缺口同时成立，修掉任何一个都只解决一半。

## 2. 修正一条前提：宿主被拉起过，然后在断言窗口内退出

上一轮我依据 `.appex` 宿主进程名为 0 条，判断宿主从未被拉起。这条不成立。

内核日志里有 74 个不同进程各一条 `triggered unnest of range 0x203200000->0x205400000 of DYLD shared region in VM map`，名字是 `CalculatorWidget[173]`、`HomeWidget[99]`、`SleepWidgetExten[100]`、`TypeToSiriWidget[98]`、`AdaptiveMusicWid[143]`、`BarcodeScannerWi[174]`、`FitnessWidget`、`CalendarWidgetEx`、`HealthBalanceWid` 等。进程确实存在过，`unnest` 是它拆掉共享缓存映射时的记录。

随后 `chronod` 报 `[launch] Launch failed with error: Error Domain=com.apple.extensionKit.errorDomain Code=4`、`Failed to create extensionProcess for extension 'com.apple.calculator.CalculatorWidget'`，最内层是 `RBSAssertionErrorDomain Code=2 "Specified target process 173 does not exist"`。`RBSAssertion` 是后发生的动作，它失败是因为目标进程已经没了，不是它把进程拦住了。

这 74 个宿主在全轮日志里**一行自己的输出都没有**：按 `名字[pid:` 前缀搜，命中 0。同一份日志里 `secinit`、`container_object`、`abort`／`Abort` 各 0 条。进程在能写日志之前就退了。

device 的同一条提醒要一起记：这一轮日志量约 65 KB/s，1 MB 的环只覆盖约 15 秒，`Successfully spawned` 这类开机头半秒的行整段没进证据。所以「宿主有没有被 spawn」这一栏在 `bbm29`／`v6` 上只能报「该轮未保留」，不能报「未拉起」；判这一栏要靠下一轮载荷里的探针。

## 3. 两个缺口是并联关系

两条缺口各自都能造成「小组件空白」，修掉任何一条都只解决一半：

- **`biomed` 缺失**（已加进 job 清单，见下一节）：`chronod` 每次打开 Biome 流都拿 `NSCocoaErrorDomain Code=4099 "The connection to service named com.apple.biome.access.user was invalidated."`。这是内容数据取不到。
- **宿主起完就退**：即使数据取到，也没有进程渲染。

所以下一轮 `biome` 报错归零之后，小组件仍可能是空白。判据要分开：`com.apple.biome.access.user` 报错数归零（第一条），宿主是否有存活 pid（第二条）。写成功时两处都要看。

时序上还有一条：`chronod` 的 `[session]` 报错最早出现在 02:53:21（`siri.TypeToSiriWidget`），早于桌面完整内容出现，所以「宿主起了就退」不是内容出现之后被触发的。

## 4. 宿主为什么退出：实测读数与直接记录

`kernel-12377-attr26-persona3` 的探针（t=60）给出的容器与名录读数：

```
lsprobe t=60 files_applications=260 files_staged=-1 mobileinstallation_dir=-1 iconstate=1 icondomain=1 posterboard_dir=-1 posterboard_db=0 pluginkit_dir=-1 containers_system=-1
lsprobe t=60 darwindir_entries=3 showing_first=3 tree=/local/2 /local/groups/0 /local/users/0
lsprobe t=60 mobilelibrary=… SpringBoard/3 MobileContainerManager/6 …
lsprobe t=60 containers_mobile=240
lsprobe t=60 workspace=258 workspace_extensions=296
```

`/private/var` 是每次开机从骨架重建的内存盘，骨架里只有 `/private/var/mobile/Containers`、`/Data`、`/Shared` 三个空目录（`out/ios26-resume/air-arm64e-device/on/root/etc/var.skel:86-88`），`Data/Application` 与 `Data/PluginKitPlugin` 都不在骨架里。运行到 60 秒时 `Data/Application` 下已有 240 项，LaunchServices 看到 258 个应用与 296 个扩展，`IconState.plist` 也已存在。**mobile 侧这几个目录是运行时填上的；system 侧那四个 `-1`（`containers_system`、`posterboard_dir`、`pluginkit_dir`、`files_staged`）才是骨架里根本没有的。**

宿主退出的直接记录在同一轮：**4 条 `Process[<pid>] crashed: <comm>. Too many corpses being created.`**（快照重叠已去重），出自 `bsd/kern/kern_exit.c:2188`，即 `task_mark_corpse()` 返回了 `KERN_NO_SPACE`／`KERN_NOT_SUPPORTED`／`KERN_TERMINATED` 以外的错误，进程名只有三个——`BarcodeScannerWi` 2 次、`CalculatorWidget` 1 次、`LauncherControlE` 1 次。宿主被拉起过，然后崩掉，corpse 名额被耗尽。**但崩溃的是少数**：同一轮 t=300 的进程表里有 67 个进程，小组件与扩展宿主一片在跑——`WeatherWidget`、`WeatherIntents`、`TipsWidget`、`SleepWidgetExtension`、`TVRemoteWidgetExtension`、`ScreenTimeWidgetExtension`、`BooksWidgetExtension`、`CalendarWidgetExtension`、`BatteriesAvocadoWidgetExtension`、`HomeWidget`、`HomeWidgetLockScreen`、`HomeEnergyWidgetsExtension`、`FindMyWidgetPeople`、`GeneralMapsWidget`、`HealthBalanceWidgetExtension`、`AdaptiveMusicWidget`、`AdaptiveMusicControl`、`MobileNotes` 的 widget 与 intents 两个扩展、`MapKit.SnapshotService`、`MobileInstallationHelperService`。所以现象是「少数宿主崩溃，多数在跑」；宿主活着而小组件不显示，问题在布局与登记，不在宿主能不能启动。

同一轮的 watchdog 违反按扩展分开（去掉快照重复后共 22 条，涉及 7 个扩展）：`com.apple.stocks.widget` 7、`com.apple.AdaptiveMusicApp.AdaptiveMusicControl` 6、`ScreenTimeWidgetExtension` 2、`PassbookWidgets` 2、`FitnessWidget` 2、`AccessibilityControlsExtension` 2、`BooksWidget` 1。分布集中在两个扩展上，`stocks.widget` 与 `AdaptiveMusicControl` 合计 13 条，占 59%。

宿主崩溃时没有 stderr：扩展宿主没有 `StandardOutPath`，控制台一行都没有。`com.apple.ReportCrash` 已在 `tools/k90auto/jobs/`（Apple 原 plist，`MachServices` 里 `com.apple.ReportCrash` 带 `ExceptionServer` 子类型，因此按需处理、不覆盖 `RunAtLoad`）。它不在清单里时，corpse 通知没有人接，`/private/var/mobile/Library/Logs/CrashReporter` 一直是空的；加上它之后，崩溃原因从不可查变成可查。

已验证（`persona4` 轮）：`containers_plugin=866`、`containers_mobile=240`、`workspace=258`、`workspace_extensions=296`、`iconstate=1`。**容器与登记都不缺，宿主起来就死的原因不在容器这一层。**

同一轮另有一条：`mobileinstallation_dir=` 从 `-1` 变成 `0`（目录在了、`installd` 还没写），`mobilelibrary=` 里出现 `MobileInstallation/0` 与 `SpringBoard/3`。

## 5. 733 条按用途分类

按每条扩展 `Info.plist` 的 `NSExtensionPointIdentifier` 分类，数字是 `xpc/launchd.plist` 里 `AppExtensions` 的实测条数。

| 条数 | 用途 | 是否会走到「起了又退」 |
|---|---|---|
| 220 | ExtensionKit（`EXAppExtensionAttributes`，没有 `NSExtension` 点） | 会，由 `extensionkitservice` 拉起 |
| 214 | 诊断与遥测（`diagnosticextensions-service` 131、`diagnostics-service` 49、其余 diagnostics 34） | 请求时才拉起，平常不走 |
| 125 | 其他单点（`message-payload-provider` 19、`ui-services` 18、`amsengagementd-extension` 9、`sidecarui-service` 6、`mlruntime.*` 10、`storekit.*` 4 等） | 按需，用户操作触发 |
| 77 | 通知 UI（`cfusernotification` 26、`usernotifications.content-extension` 26、`followup-extension` 24） | 按需 |
| 34 | Intent 与 Spotlight（`intents-service` 23、`spotlight.import` 5、`spotlight.index` 3、`intents-ui-service` 2、`appintents-extension` 1） | 按需，`chronod` 会在解 `AppIntent` 时触发 |
| 33 | 小组件与控制中心（`com.apple.widgetkit-extension`） | **会，开机后就被 `chronod` 要求内容** |
| 17 | QuickLook 与编辑（`quicklook.thumbnail` 5、`thumbnail.secure` 3、`preview` 3、`preview.highmemory` 3、`photo-editing`、`markup-private`、`pdfkit-private`） | 按需 |
| 11 | 文件提供者（`fileprovider-nonui` 6、`fileprovider-actionsui` 2、`fileprovider-ui`、`DocumentManager.Service`、`fskit.fsmodule`） | 按需 |
| 2 | 壁纸（`com.apple.posterkit.provider`：`InfographPoster.appex`、`MonogramPosterExtension.appex`） | 选中 poster 相关时才走 |

会被 SpringBoard／`chronod` 主动要内容的只有 33 条 widgetkit 加 2 条 posterkit，共 **35 条，35 个不同宿主**：`CalculatorWidget`、`HomeWidget`、`SleepWidgetExtension`、`TypeToSiriWidgetExtension`、`AdaptiveMusicWidget`、`AdaptiveMusicControl`、`BarcodeScannerWidgetExtension`、`BatteriesWidgetExtension`、`BatteriesAvocadoWidgetExtension`、`CalendarWidgetExtension`、`FindMyWidgetItems`、`FitnessWidget`、`HealthBalanceWidget`、`ScreenTimeWidgetExtension`、`PrintCenterWidgetExtension`、`PeopleWidget_iOSExtension`、`GCWidgets`、`TVRemoteWidgetExtension`、`TrackingUIServiceWidgetExtension`、`VPNAppIntentWidgetExtension`、`AccessibilityControlsExtension`、`ControlCenterControlsExtension`、`ToggleAirplaneModeExtension`、`ToggleCellularDataModeExtension`、`WiFiSettingsControlsExtension`、`WirelessModemSettingsControlsExtension`、`PersonalHotspotControlExtension`、`SoundAndHapticsControls`、`MusicRecognitionControls`、`BatterySettingsIntentsExtension`、`DefaultAppsSettingsIntentsExtension`、`GeneralSettingsIntentsExtension`、`NotificationsSettingsExtension`、`IntelligenceIntentsExtension`、`AirDropSettingsIntentsExtension`、`MessagesSettingsWidgetKitExtension`、`InfographPoster`、`MonogramPosterExtension`。

这份清单的第二个用途：降级时正好是这 35 条要摘掉，其余 698 条不参与「起了就退」。

## 6. 宿主 `Info.plist` 里的加载前提：没有可疑项

35 个宿主里没有一条带 `NSExtensionPrincipalClass`，也没有一条带 `RequiredDeviceCapabilities`。也就是说「主类名写错」与「设备能力不满足」这两条常见原因排除。剩下的前提就是容器与启动上下文，见第 3 节。

## 7. 图标缓存写不进 HEVC：平台能力缺口

`chronod` 把图标编码成 HEVC 写缓存时每次失败，`kCMPhotoError_InvalidParameter [-16990]` 配 `codec: 'hvc1'`；`iconservicesagent` 同一条路径报 `Failed to serialize finalized icon`。

判断是「平台不可用」而不是「偶发参数错误」，依据三条：

- 镜像里 `com.apple.videocodecd.plist` 带 `"Disabled": {"#IfFeatureFlagDisabled": "CoreMedia/SeparateCodecProcess", "#Then": true}`，这份构建上进程外编解码守护进程默认是关的，加进 job 清单也没用；iOS 26 的 `LaunchDaemons` 里也没有 `mediaserverd`。
- Apple 平台上的 HEVC 编码是硬件编码器（AVE），走 Apple 自己的视频驱动。SM8750 没有这个硬件，我们的内核也没有带 Apple 的视频编解码驱动，因此没有编码器可以注册。
- 失败点在 `CMPhotoCompressionSessionAddImage`，即会话已建立、参数按目标编码校验时才失败。86 次调用、两个不同客户端（`chronod` 与 `iconservicesagent`）、两轮（`bbm29` 与 `v6`）、图标内容各不相同，错误码始终是同一个——这排除了「某个图标的尺寸或色彩空间传错」。

写失败本身也不解释 15 秒周期。perf 核了五个 3.0 秒空档（288.5／303.6／318.6／333.6／348.6 秒）前后三秒的 `writeImageAtIndex`：前三个分别 12／24／39 次，后两个 **0** 次，最后一次写失败在 317.8 秒。所以写失败只对应前三次空档，第四、五次没有它。`chronod` 的图标写在这之后就停了，而空档按 15 秒周期继续。那条周期另有来源，没有定下来。

待查：`FigXPC >> signalled err=-16155` 在 `bbm29` 出现 649 次（跨快照求和的原始计数），没有归因。

能不能让图标缓存避开 HEVC：没有找到开关。而且 `/private/var` 是开机重建的内存盘，图标库即使写成功也活不过一次重启，预置一份缓存只在当次开机有效，而库是按图标内容哈希与设备特征建的，外来的库会被重新生成。结论是这条路不值得投入。

**这条在验收清单里写成已知限制，不留成待办。** 它不影响显示正确性，是重试带来的性能开销。

这条错误是**性能问题，不是功能问题**。`bbm29` 里 15 个图标全部正常显示，而同一轮 86 次 HEVC 写全部失败，说明首页图标走的是 `Assets.car` 的内存路径，不依赖这个库。代价是每次请求都重新生成，外加每 15 秒一次约 3 秒的空档。应用启动不受它阻塞，图标请求是为了显示。

## 8. 降级方案：只登记不拉宿主的那部分

短期目标是拿到一个稳定、可跑满整轮的状态给性能线验收，不是放弃小组件。

做法：在 `package.py` 生成缓存的那一步，从 `AppExtensions` 里删掉 `NSExtensionPointIdentifier` 为 `com.apple.widgetkit-extension` 与 `com.apple.posterkit.provider` 的条目，733 条留 698 条。用环境变量控制（例如 `DROP_EXTENSION_POINTS=com.apple.widgetkit-extension,com.apple.posterkit.provider`），默认关。

预期：应用图标、页码圆点、Dock、壁纸以外的静态资源都来自 `LaunchServices` 的应用清单，与这 35 条无关，应当保留；小组件退回 `bbm26`／`28` 的占位形态；不再有宿主被拉起，`RBSAssertion` 那条链消失。

降级后**缺的东西**，验收时要逐条划掉：小组件内容（有名字、内部空白或占位）、壁纸（仍为黑）、控制中心里的扩展类控件（`ControlCenterControlsExtension`、`ToggleAirplaneModeExtension` 等 11 个开关与滑块）、锁屏 poster 相关界面。保留的东西：15 个应用图标与名称、4 个 Dock、页码圆点、Control Center 本体、翻页与手势。

**这一条现在不启用。** 它是最后手段，排在「拿到宿主退出的原因」与「按原因修」之后。触发条件写明：如果 `biomed` 那一轮宿主仍在退，先解决容器与退出原因，降级不参与那一轮，避免两个变量分不清。

要跑的实验对象也因此变了：任何减量实验的正确对象是这 35 条，不是 733 条。

## 9. 计数口径

本文所有行数都是 `merged_log()` 合并去重后的**唯一行**数，不是跨快照求和。`bbm29`：`CMPhotoCompressionSessionAddImage` 唯一行 **86**（跨快照原始计数 118）、`writeImageAtIndex` **172**（原始 236）、`Failed to serialize finalized icon` **256**（原始 1311）。跨快照求和会把环重叠区重复计数，同一份日志能读出 1,516 这种数。以后所有人报行数都用唯一行，并在报告里写明口径。

## 10. 未验证

- 宿主退出的具体原因（第 3 节）没有直接证据，只有容器缺失这一条与「不写任何日志」吻合。
- 降级方案没有跑过，698 条保留项是否仍会让 `pkd`／`extensionkitservice`／`iconservicesagent` 被判卡，未知。
- `memorystatus_perform_idle_demotion() timed out stuck process` 的含义按内核源码读是「持有重要性断言或标记 dirty，且跨过两个 aging 期限仍未 idle」，不是进程忙。相关判读见 `kern_memorystatus.c` 的 `_memstat_perform_idle_demotion_for_band`：第一次进 `JETSAM_PRIORITY_AGING_BAND1_STUCK`，第二次超时才打出这一行并降到 `JETSAM_PRIORITY_IDLE`。所以它不能用来区分「在算」与「在等」。
## 11. `persona4` 的两个新读数：核心进程换 pid、60 秒档复现

探针 `procs=` 在 t=60 与 t=300 各一次，两次对比只有一个变化：`backboardd` 从 36 变成 131、`SpringBoard` 从 30 变成 136，其余十个进程 pid 全未变。新 pid 的日志首现时间是 `backboardd[131]` 的 06:25:36.839 与 `SpringBoard[136]` 的 06:25:37.295；旧 `backboardd[36]` 的最后一条是 `MiniIOMobileFramebuffer: backboardd[36] selector 6`。这一轮没有任何 `Process[<pid>] crashed:` 行，也没有 `died on signal`（内核当时还没有那三行），所以这两个进程的退出没有走 corpse 通知路径，是否为信号致死无从判断；换 pid 之后进程继续存活、帧继续产生到 586.8 秒。

同一轮 `tl: s` 7,704 次、空洞 16 处，其中三处是 59.3 秒（id 7667→7668，466.8→526.1 秒）、59.2 秒（id 7685→7686，526.8→586.1 秒）、51.8 秒（id 7639→7640，414.2→466.1 秒），另有启动初期 18.8 秒一处（id 1→2，232.8→251.6 秒）。60 秒档从 414 秒开始，之前是 15 秒级的一串（264.6、267.6、282.6、297.6、312.6、342.6 秒）。这与此前 `continuous` 轮「先 15 秒级、后 60 秒级」的接续形态一致，说明两档接续可复现。

## 12. 死因的五类与 `backboardd` abort 之后的集体杀

`kernel-12377-attr26-dasd` 是第一次带死因内核的一轮，`died on signal` 共 91 条唯一行，按信号与 `code` 分成五类：

| 信号 | `code` | 条数 | 时间 | 判读 |
|---|---|---|---|---|
| 9 `SIGKILL` | 1001 | 24 | 从 06:36:36.321 起断续出现 | 看门狗到期杀，与 `Watchdog provision violated` 同源 |
| 9 | 0 | 49 | 06:37:41.553～06:37:42.979 | 一次集体杀，`SpringBoard pid 30` 与全部前台扩展在其中 |
| 9 | 9 | 4 | 06:37 前后 | `ACCHWComponentAu`、`AudioConverterSe`、`MTLCompilerServi` 两条 |
| 5 `SIGTRAP` | 5 | 9 | 06:38:21.892～06:38:27.836 | `CalculatorWidget`、`LauncherControlE`、`BarcodeScannerWi` 各三次，每次间隔 1～2 秒 |
| 6 `SIGABRT` | 4 | 1 | 06:37:41.430535 | `backboardd pid 38` |

`backboardd` 那条的前后 62 毫秒是这次 aborted 的全部线索：

```
06:37:41.368038 backboardd[38:358] [Metal] nil buffer from memory: [b:10a0a4000 o:0000 l:004000], w:256 h:1 bpr:2048 bpi:2048
06:37:41.429338 backboardd[38:358] [Metal] Metal failed to build render pipeline
06:37:41.430535 backboardd[38:358] [Metal] Metal failed to build render pipeline
06:37:41.430535 redwood: proc backboardd pid 38 died on signal 6 code 4
06:37:41.545075 backboardd[136:965] [Common] starting /usr/libexec/backboardd...
```

新 `backboardd[136]` 在 114 毫秒后启动，随后 1.4 秒内 49 个进程被 `SIGKILL`（`code 0`），包括 `SpringBoard pid 30`、`chronod` 之外的全部前台扩展与 `WidgetRenderer_D`；`SpringBoard` 以 pid 144 重新起来。所以这次集体杀是渲染服务器 abort 的下游：`SpringBoard` 与各扩展是 `backboardd` 的客户端，渲染服务器重启时它们被一起结束并重新拉起。

这一条把 `persona4` 里 `backboardd 36→131`、`SpringBoard 30→136` 那个重启的机制说清了：`backboardd` 因管线建立失败 abort，不是被策略杀。同一轮里先前那条「`nil buffer` 按现状挂着」的处置现在有了直接后果，即 abort 前最后一条 Metal 日志就是它。

## 13. 一条被两轮独立验证的因果，与我先前怎么否掉它的

`nil buffer from memory` 归零之后，`Metal failed to build render pipeline` 从 2 条归零：`driver1` 轮还有 2 条（当轮 `nil buffer` 已归零但 `deallocator` 用错时机），`driver2` 轮两处都是 0。所以「`nil buffer` 是管线建立失败的上游」成立。

先前否掉过它。2026-10-28 早些时候我用的是跨轮条数相关性：某一轮 `nil buffer` 条数高而管线失败条数不高，就判断两者无关。那个判断有三个问题：跨轮比较把驱动、负载、轮次长度都当成了不变；条数是跨快照求和，同一行被数了三四遍；「相关」本身也不是因果。**改判的依据换成了同一条时间线内的本地顺序**：`06:37:41.368038` 的 `nil buffer`，`61` 毫秒后的管线失败，同一毫秒的 `SIGABRT`。这类证据不需要跨轮。

方法论上留下两条：**否掉一个因果假设，要用同一轮内的顺序或一次受控改动，不用跨轮条数**；**一个假设被否掉之后，若出现同轮内的时间线证据，要重新开启，而不是拿旧的否掉结论去挡**。第二条今晚在 `nil buffer` 上走了一遍，处置从「按现状挂着」改成重开。

## 14. 系统活着、画面冻住：`gestures` 轮的四条读数

`kernel-12377-attr26-gestures` 这一轮里：

- **94 张截图的 sha256 只有 1 个**（`313e03d2…`），整轮逐字节相同，连状态栏的时钟都没变；
- **帧 id 只有 17 个**；
- `backboardd` 与 `SpringBoard` 的 pid 全程未变（`procs=` 行）；
- 没有 `6/4`、没有 `9/0`、没有 `11/11` 的死因记录。

四条合起来说明这台机器在开机之后画了一帧，之后不再往面板送帧，**而系统本身在运行**：进程没有重起、没有中止、探针仍在回答。**这把「渲染停住」与「渲染崩溃」分开了。**

同内核、同驱动（`31f2d6b7`）、同 AIR 库（`d7b9ced5`）的 `airindex` 轮是 3,550 帧、94 张截图全是主屏。两轮的差别在手势脚本：`airindex` 跑的是 2.5 秒一段的连续横滑（从 `tl: p` 的两个不同起点 `y=0.985` 与 `y=0.55` 认出），`gestures` 跑的是 0.42 秒一段的短滑。**帧是在手指按住期间产生的**，所以 17 与 3,550 的差别首先要用「手指按住的总时长」解释，而不是用「渲染坏了」解释。逐次触摸的时长无法从日志里读出：`tl: p` 走 `RW_AGAIN` 节流，一次 2.5 秒拖动约 300 个样本，日志里只有几行。

## 15. `touchdiag` 轮的冻结时刻：09:23:16.7，冻的是提交，不是内容

四条流在 `kernel-12377-attr26-touchdiag` 里的范围：

- `tl: v`（帧）3,551 条唯一行，id 1 到 3550，`done` 从 798.496 秒到 895.057 秒（mach 时间）；
- `tl: s`（提交）3,550 条唯一行，同一区间；
- `tl: p`（触摸样本）1,228 条；
- `tl: td` 一条也没有（这一轮的脚本没有打这条流）。

用一条同时带墙钟与帧号的行锚定：`09:22:08.6416` ↔ 帧 647／`done` 827.029 秒，所以 mach 895.057 秒是 **09:23:16.67**。**最后一帧在 09:23:16.67，之后 `tl: v` 与 `tl: s` 都不再有新行。**

**同一条日志在此之后还继续写了 2 分钟**（最后一行墙钟 `09:25:17.253`），其中 `chronod` 3,402 行、`iconservicesagent` 1,591 行、`backboardd` 122 行。`backboardd` 那 122 行里有 27 条 `[TouchEvents] Touch entered (insideExclusive)` 与 27 条 `contact 1 presence: touching`：**手指仍然进到窗口服务器、命中测试仍然通过，但没有一帧被提交。**

所以冻结的形态是「提交整条停了」，不是「内容不更新」：

| 流 | 冻结后 |
|---|---|
| 帧（`tl: v`） | 停 |
| 提交（`tl: s`） | 停 |
| 触摸到 `backboardd` | 继续 |
| 其它守护进程的日志 | 继续 |

冻结前 30 毫秒有一条 `nil buffer from memory`（`09:23:16.6359`）。这一轮里 `nil buffer` 唯一行 23 条，前 22 条在 `09:21:57`～`09:23:10`，第 23 条正好落在最后一帧之前。**时间上贴着，但一条事件不足以定因果**，要定得看 `nil buffer` 之后那条路径为什么不再提交。

冻结前还有一处节律：`tl: v` 的间隔每 15 秒出现一次约 3 秒的空档（29.9→32.9、44.9→47.9、59.9→62.9、74.9→77.9 秒），与既有的 15 秒周期记录一致；平均帧率 36.8 帧/秒。

## 16. 桌面停在锁屏之后的原因：AIR 翻译器不支持运行时下标的 `insertelement`

`driver-revert` 轮 `run/s005.log` 第 20137 行与第 20138 行连着两条，中间没有别的：

```
redwoodmetal[backboardd 38]: this render pipeline is refused: the fragment module: instruction: insertelement at a run-time index (block 6, instruction 1, opcode 10)
2026-10-28 07:49:12.897117+0800 backboardd[38:353] [Metal] Metal failed to build render pipeline
```

同一轮的 AIR 字节以 `AIRFAIL` 前缀分块打印（271 个不同的块），失败的那一片元着色器是 `TmuaA2Xhfn_IsrcN3Oc3mtc4nlnlnl_Isqr`，管线标签是 `spec=PBGRABscnXm_TmuaA2Xhfn_IsrcN3Oc3mtc4nlnlnl_Isqr`。汇总行的形状是：

```
redwoodmetal[backboardd 38]: render pipelines: 49 built, this one 1811 us (refused) vertex VfxU11Xh fragment TmuaA2Xhfn_IsrcN3Oc3mtc4nlnlnl_Isqr
redwoodmetal[backboardd 38]: render pipelines: 50 built, this one 1686 us (refused) vertex VfxU11Xh fragment TmuaA2Xhfn_IsrcN3Oc3mtc4nlnlnl_Isqr
```

同轮另有 `... and that is the 2'th pipeline asking for exactly that` 与 `(first time)` 两种标记，说明这条管线被反复请求、每次都失败。

**链条**：着色器里 `insertelement` 的索引在运行时取值 → AIR 翻译器不支持 → 片元模块被拒 → `Metal failed to build render pipeline` → `backboardd` 中止（同轮 `redwood: proc backboardd pid 38 died on signal 6 code 4` 一次）→ 会话重起 → 桌面停在锁屏之后。

**已在 `airindex` 轮验证**（`kernel-12377-attr26-airindex`，AIR 库 `d7b9ced5`，`air_to_nir.c` 为 `35b6f62e`）：`this render pipeline is refused` 0、`Metal failed to build render pipeline` 0、`signal 6 code 4` 0、`signal 9 code 0` 0，帧 3,550、id gaps 0，截图 `run/png/shot-01384.png` 是主屏（状态栏 `8:17`、天气与日历小组件、四列图标、`Search` 胶囊、dock 四格）。**这一处就是桌面停在锁屏之后的原因。**

所以「为什么锁屏之后停住」的答案是着色器编译器的一处能力缺口，与 buffer 分配、容器、图标模型都无关。要顺着这条查，先看 `insertelement` 那一行的 block 6 instruction 1，再看同一个片元着色器在 `RedwoodMetal` 的 AIR 生成路径上是怎么产生这个指令的。

## 17. 截图里的两种画面：锁屏出现过，主屏从未出现

`dasd`／`persona4`／`driver1` 三轮各 94 张 `shot-*.raw`，转成 PNG 后只有两种画面：约 100 秒处是锁屏（黑底、白色 `6:37`、`Wed 28 Oct`、底部白条），约 199 秒之后整屏纯黑。**主屏（图标、页码圆点、壁纸）一次都没出现。**

判定「SpringBoard 加载了 `IconState.plist`」目前没有观测。探针的 `iconstate=1` 与 `icondomain=1` 读的是目录与文件的存在性；`IconState` 与 `IconDomain` 两个词在 `persona3`、`persona4`、`dasd`、`driver1` 四轮的日志里各出现 **0** 次（`grep -hac "IconState" run/*.log` 四轮都是 0）。所以现在的表述是「配置数据在盘上、屏上没画出来、日志里没有出现它的路径」，不要写成「已加载」。

**`iconstate=1` 说明图标模型这一层是活的**：`/private/var` 是 ramfs、每次开机从骨架重建，而骨架里没有这个文件（`grep -c IconState` 得 0），所以它是**本次开机才被写出来的**。这句话比「文件在盘上」强一档，是判断「断在模型到画面之间」的依据。

**桌面线的第一问是「为什么锁屏之后停住」，不是「图标为什么不显示」。** 依据是三轮各 94 张截图里只有锁屏与之后的纯黑，主屏一次都没出现；问题必须在「画了一次之后停住」这个已观测到的现象上问。`iconstate=1` 说明图标模型这一层是活的（本次开机有进程写了这个文件），断的那一段在模型到画面之间。

**「谁写了 `IconState.plist`」列成可查项，排在「锁屏之后为什么停住」之后。** 前者在不显示的情况下没有用：即使知道写入者，也解释不了黑屏。

**「在盘上」在这里要说得更准确**：`/private/var` 是 ramfs，每次开机从骨架重建，打包根的 `/etc/var.skel` 里没有 `IconState` 这一项（`grep -c IconState` 得 0，骨架只有 143 行，`/private/var/mobile/Library/SpringBoard` 是一个空目录）。所以 `iconstate=1` 说明**本次开机有进程写了它**，这比「盘上有这个文件」强。谁写的目前没有观测，那仍是上一段说的空白。SpringBoard 读文件走 `open`／`mmap`，BSD 层默认不打印，所以这个 0 既不能证明读过，也不能证明没读。

要观测「有没有读」，三条路按代价排：~~探针加读 `st_atimespec`~~（**已作废，见下**）；`kdebug` 的 `FS_` 事件（`bsd/kern/kdebug.c` 在，但要把 `kern.kdebug` 开起来再写消费者，不是一行打印的量级）；在该路径的 `open` 上加一行只匹配该文件名的内核查打印（最直接，要一轮重编）。

**`atime` 这条路作废，而且不是因为挂载选项。** `/private/var` 在这个移植里是 ramfs（`bsd/miscfs/ramfs/ramfs.c:5` 写明「bring-up system has no storage driver, so /private/var and /tmp are kept」在内存里；`bsd/dev/redwood_apfs_check.c:400` 写「/private/var is a ramfs that userland's init mounts」），所以这个文件不在 APFS 上。ramfs 的 `rn_atime` 只有三处：创建时 `nanotime`（`ramfs.c:147`）、`setattr` 显式设置（`ramfs.c:177`、`ramfs.c:969`）、取值返回（`ramfs.c:890`），**没有读路径上的更新**。APFS 那一侧同样只有一个赋值点（`apfs_lib.c:1564`，解析 inode 记录），但那个文件根本不走 APFS。

两条现在都不做：这条判据的目的是判 SpringBoard 有没有拿到图标配置，而主屏还没画出来，即使证明它读了文件也解释不了黑屏；反过来，桌面画出来而图标位置与文件不一致时再上观测手段也不迟。这条判据的前置与性能基线相同，都是「主屏画出来」。

这一条限制两条判据：

- `summary.py` 里「home screen: unknown without reading the screenshots」这类判定，读出来只能是「没有主屏」，不能用来反推 `IconState` 或 PosterBoard 的行为；
- 判「图标位置与 `IconState.plist` 是否一致」这条，在桌面画出来之前不可用。

正面的部分是锁屏那张说明渲染通路是通的（时间、日期、底部白条都画出来了），黑屏那张说明后来停了。现象是「画了一次锁屏之后停住」，比帧数更能描述现状。

要做截图判据，转换命令可用（`ffmpeg -f rawvideo -pix_fmt bgra -s 1156x2510`），但要等 `signal 11 code 11` 归零、主屏回来之后再用。

三档可以用亮像素比例自动分开，不必人眼看图：锁屏约 102/2911（只有时间与底部白条）、主屏约 1163/2911（静态，整轮数值相同）、纯黑 0/2911。判据是「这一轮画到了哪一档」，不是「一直在画」：主屏内容不变就不提交新的 command buffer，`command buffers: N committed` 会停住而画面是好的；`driver-revert` 轮 181.3 秒后掉到 0.8 次/秒才是真停（解锁之后没有内容可画）。

尺寸 `1156x2510` 用文件字节数核过：`shot-01032.raw` 是 11,606,240 字节，`1156 × 2510 × 4 = 11,606,240` 完全相等，单通道 4 字节、无行填充。常见的 1220x2712（13,234,560）、1170x2532（11,849,760）、1206x2622（12,648,528）都与文件字节数不等。所以截图里的「纯黑」是真黑，不是转换参数把画面切错；`oem screenshot` 输出的是我们自己的帧缓冲。

## 18. 一次完整的受控验证：改写前后的同一个 `.metallib`

2026-10-28 修 `insertelement` 时用到的写法，可以当作后续同类改动的范例：**取真实输入 → 在宿主上复现 → 改 → 同一个输入通过**。

1. 输入取自真实轮次。`airfail-extract.py` 把 `kernel-12377-attr26-driver-revert` 里被拒的模块从日志的 base64 段还原出来：`fragment-TmuaA2Xhfn_IsrcN3Oc3mtc4nlnlnl_Isqr-cba624ef.metallib`（10,032 字节）、`vertex-VfxU11Xh-ed5ad954.metallib`（4,368 字节），字节数与 FNV-1a 都与 begin 行一致。
2. 在宿主上复现。`/private/tmp/mesa-air-host/build/src/compiler/air/air2nir` 跑同一个模块，输出与设备日志一字不差：`instruction: insertelement at a run-time index (block 6, instruction 1, opcode 10)`。
3. 改。`air_to_nir.c` 的 `AIR_OP_INSERTELT` 改调 `nir_vector_insert`。
4. 同一个输入通过。重建 `air2nir` 后同一模块退出码 0，输出 `num_textures: 10 / num_ubos: 6 / inputs: 3 / outputs: 1`。

这个验证之所以成立，是因为宿主树的 `src/compiler/air` 是指向 `tools/mesa/air` 的符号链接，验证的就是将要进构建的那一份源码；若它是副本，第 4 步证明的会是另一份代码。arm64e 侧的旁证：`libredwoodair.dylib` 重建后 `strings` 里 `insertelement at a run-time index` 出现 0 次。
