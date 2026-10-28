# iOS 26 镜像里「job 在、程序不在」的全量对照

起因是 B0 那一轮要放开 `bluetoothd`：`System/Library/LaunchDaemons/com.apple.bluetoothd.plist` 在镜像里，它指向的 `/usr/sbin/bluetoothd` 不在。查下来这是抽取规则的结果，同类文件不止一个，所以做了一次全量对照。

## 1. 结论

661 个 launchd job 里，616 个的程序在盘上，19 个 job（18 个程序）的程序在原始镜像里有、抽取时被跳过，16 个的程序只在 dyld 共享缓存里、原始镜像的 OS 卷里没有，8 个 plist 的程序写的是裸名字、无法按路径核对，1 个是没有程序键的配置 plist。

抽取流程从不读 launchd plist。它按**路径前缀加文件大小**挑文件，所以哪些 daemon 能跑，取决于它们多大多小、放在哪个目录，与 iOS 认为它们该不该跑无关。三个阈值：`usr/libexec/` 与 `usr/sbin/` 下的程序不超过 10 MB，framework 里 `XPCServices`／`Support`／`Helpers` 下的不超过 32 MB，framework 根目录下的不超过 4 MB。`usr/sbin/bluetoothd` 12,151,072 字节，正好属于第一类的超限项。

这张表之前没被发现，是因为 `userland/mkjobs.py` 的 `DENY` 恰好覆盖了其中大部分：`CommCenter`、`bluetooth`、`locationd`、`backupd`、`audio` 都在 `DENY` 里。B0 要放开 `bluetooth`，才第一次撞上。

## 2. 方法与可信度

工具是 `tools/check-launchd-programs.py`，扫 `System/Library/LaunchDaemons`、`LaunchAgents`、`LaunchAngels` 三处（这个镜像里没有 `LaunchAgents` 目录），取每个 plist 的 `ProgramArguments[0]`、`Program` 或 `BundleProgram`，先看文件在不在 `ios26/rootfs`，再看路径在不在 `ios26/rootfs.slt`（`7z l -slt` 的技术清单，代表设备上的原始 OS 卷）。

判断某个 daemon 在不在盘上只有这一条路：读它的 plist 拿到程序路径，再去盘上找。按名字猜目录会错——`com.apple.accountsd` 的程序是 `/System/Library/Frameworks/Accounts.framework/accountsd`（88,672 字节），不在 `/usr/libexec/` 下，按名字搜 `/usr/libexec/accountsd` 会得出「缺失」的错结论。

四个已确认在跑的服务当反例：`linkd`（`/usr/libexec/linkd`）、`appprotectiond`（`/usr/libexec/appprotectiond`）、`accountsd`（`Accounts.framework/accountsd`）、`biomed`（`BiomeStreams.framework/Support/biomed`）全部判为 present，说明这张表没有把「在跑的」判成缺失。

## 3. 表一：镜像里有、抽取时被跳过（19 个 job，18 个程序）

按触发它的规则分组，大小取自 `rootfs.slt`。

`usr/libexec/` 与 `usr/sbin/` 下超过 10 MB 的程序（`BIG_PROGRAM = 10 << 20`）：

| job | 程序 | 字节 |
|---|---|---|
| `com.apple.locationd` | `/usr/libexec/locationd` | 40,226,848 |
| `com.apple.icloud.searchpartyd` | `/usr/libexec/searchpartyd` | 27,497,168 |
| `com.apple.lskdd` | `/usr/libexec/lskdd` | 21,085,072 |
| `com.apple.lskdP7d` | `/usr/libexec/lskdP7d` | 18,145,952 |
| `com.apple.fairplayd.H2` | `/usr/sbin/fairplayd.H2` | 17,931,488 |
| `com.apple.bluetoothd` | `/usr/sbin/bluetoothd` | 12,151,072 |
| `com.apple.sharingd` | `/usr/libexec/sharingd` | 11,567,744 |
| `com.apple.remindd` | `/usr/libexec/remindd` | 11,426,192 |
| `com.apple.nearbyd` | `/usr/libexec/nearbyd` | 10,878,496 |

framework 的 `Support/` 下超过 32 MB（`size <= 32 << 20`）：`com.apple.CommCenter` 与 `com.apple.CommCenter-noncellular` 两个 job 指向同一个 `/System/Library/Frameworks/CoreTelephony.framework/Support/CommCenter`，35,338,304 字节。

framework 根目录下超过 4 MB（`SMALL = 4 << 20`，非 `Support`／`XPCServices`／`Helpers` 的子路径只按 4 MB 判）：

| job | 程序 | 字节 |
|---|---|---|
| `com.apple.identityservicesd` | `IDS.framework/identityservicesd.app/identityservicesd` | 15,382,336 |
| `com.apple.passd` | `PassKitCore.framework/passd` | 10,566,528 |
| `com.apple.telephonyutilities.callservicesd` | `TelephonyUtilities.framework/callservicesd` | 7,906,144 |
| `com.apple.threadradiod` | `CoreThreadRadio.framework/threadradiod` | 9,600,688 |
| `com.apple.assistantd` | `AssistantServices.framework/assistantd` | 6,496,624 |
| `com.apple.backupd` | `MobileBackup.framework/backupd` | 4,549,904 |
| `com.apple.akd` | `AuthKit.framework/akd` | 4,439,824 |

整个前缀被跳过（`SKIP_SYSTEM_LIBRARY` 里有 `Audio`，于是 `System/Library/Audio/` 下什么都不取）：`com.apple.usbaudiod` 指 `/System/Library/Audio/Plug-Ins/usbaudio.bundle/usbaudiod`，1,744,400 字节。

## 4. 表二：只在 dyld 共享缓存里（16 个 job）

这些路径在设备 OS 卷的技术清单里根本没有，抽取规则改了也取不出来，要用就得从共享缓存取出来再写到盘上。

App cryptex（`/System/Cryptexes/App/...`，这个镜像里本来就没有那个卷）9 个：`AuthenticationServicesAgent`、`com.apple.Safari.History`、`passwordbreachd`、`SafariBookmarksSyncAgent`、`webbookmarksd`、`browserkitd`、`safarifetcherd`、`webinspectord`、`webpushd`。

OS cryptex（`/System/Cryptexes/OS/...`）1 个：`com.apple.webkit.adattributiond` 指 `WebKit.framework/Daemons/adattributiond`。

OS 卷命名空间里但清单没有的 6 个：`/usr/local/bin/cellularcertd`、`/usr/sbin/sntpd`、`/usr/sbin/dietapplecamerad`、`DeviceInterface.framework/Support/deviceinterfaced`、`HealthContent.framework/healthcontentd`、`RealityCamera.framework/realitycamerad`。

## 5. 另外两类

8 个 plist 的程序是裸名字，launchd 按路径 spawn，这类 job 起得来与否要看 launchd 是否在别处补全：`OTACrashCopier`、`aslmanager`、`assetsd`、`cloudphotod`、`ftp-proxy`、`com.apple.photos.ImageConversionService`、`com.apple.photos.VideoConversionService`、`CoreServices/ScreenSharingServer.app/ScreenSharingServer`（最后一个是相对路径）。

1 个 plist 没有程序键：`com.apple.jetsamproperties.V57.plist`，是配置项。

还有一类容易被误判成缺口：**服务名与 job 名不同**。`com.apple.duetactivityscheduler` 没有以它命名的 plist，但它是 `com.apple.dasd` 的一项 `MachServices`（程序 `/usr/libexec/dasd`，2,572,640 字节，在盘上）；`com.apple.coreduetd.context` 由 `com.apple.contextstored` 提供（`CoreDuetContext.framework/Resources/contextstored`，106,256 字节，在盘上），而 `com.apple.coreduetd`（`/usr/libexec/coreduetd`，361,696 字节，在盘上）提供的是 `knowledge`、`people`、`pairedsync` 这另一组名字。所以判定某个服务缺不缺，不能按服务名找同名 plist，要先把每个 plist 的 `MachServices` 列全再反查；`tools/check-launchd-programs.py --service NAME` 做的就是这一步。

另有一种「策略上排除」：`com.apple.duetexpertd`（`/usr/libexec/duetexpertd`，98,672 字节，33 项 `MachServices`，其中 `com.apple.proactive.HomeScreenSuggestion.xpc` 与 `com.apple.proactive.SuggestedPages` 与桌面建议相关）程序在盘上，但它在 `userland/mkjobs.py` 的 `DENY` 里，从来没起过。它不进本文的缺口统计。

## 6. 抽取规则在代码里的位置

`ios26/select-system.py`：`BIG_PROGRAM = 10 << 20`（第 138 行）只看 `usr/libexec/` 与 `usr/sbin/`；`SMALL = 4 << 20`（第 52 行）与 framework 分支（第 200 行起）决定 framework 内的程序；`SKIP_SYSTEM_LIBRARY` 里列了 `Audio` 等整个前缀。启动 `wanted_file()` 的入参只有路径与大小，没有任何一处读过 launchd plist 或 daemon 名字。

## 7. 抽取规则这一版不改

改 `ios26/select-system.py` 会改变 `system26.apfs` 的内容与哈希，而那份约 4.9 GB 的系统盘是现在所有实验的基线：换了它，此前所有轮次的可比性作废，显示与性能要重新建基线重测。换来的 18 个程序里，与当前目标相关的只有 `bluetoothd`，而它只影响 B0 的第四个问题（`bluetoothd` 在组合未知时是否反复重启）。`locationd`、`CommCenter`、`backupd`、`usbaudiod` 都不在显示与性能的路径上。

所以抽取规则按现状保留，本文记下这三条作为以后真要重做抽取时的依据：规则是按路径前缀与文件大小挑文件，不读 launchd plist；按这一版规则有 19 个 job 的程序取不出来；放宽阈值会让系统盘换哈希、把现有基线作废。

表二那 16 个同样先不动，它们要的是「从 dyld 缓存取出程序再写到盘」，比改阈值动得多。

## 8. 对当前工作的影响

B0 那一轮按「只跑 `BlueTool`」走：`/usr/sbin/BlueTool` 在盘上（5,255,248 字节，远低于 10 MB），够回答传输编号与三元组。`bluetoothd` 是触发者，等以后单独立项。

`locationd`、`CommCenter`、`backupd`、`usbaudiod` 这几个恰好都在 `DENY` 里，所以短期内不挡任何事；一旦要放开其中任何一个，都会撞上同一类缺口。`nearbyd`、`sharingd`、`remindd` 同理。

阶段 6 那轮（Wi-Fi 只读）与这张表无关，不受影响。

## 9. 打包时的断言（已交 device）

防止再出现「job 有、程序没有」，在 `tools/k90auto/package.py` 里加一条检查：写进 job 清单的每个 label，其 `ProgramArguments[0]`（或 `Program`、`BundleProgram`）必须在打包的根文件系统里存在，缺一个就让打包失败，报错里给出 label、程序路径，并指向本文第 3 节的表。

这一条与改抽取规则的收益相同，代价是几行代码，不动系统盘、不作废基线。

## 10. 待确认

- 表二的 16 个里，`WebKit.framework/Daemons/adattributiond` 只在 OS cryptex 里；两个 cryptex 卷是否被内核挂载、挂在哪，这次没有查。
- `fairplayd.H2` 在 18 个缺口内，未验证其行为。
- 8 个裸名字的 job 里有没有真在跑的，没有查；它们要么早已废弃，要么由别的机制补全路径。
- 三个阈值是这一版的规则，`select-system.py` 改动后要重跑 `tools/check-launchd-programs.py` 才知道缺口有没有变。