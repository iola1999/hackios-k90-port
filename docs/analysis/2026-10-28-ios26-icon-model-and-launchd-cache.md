# 桌面只有 2 个图标：启动参数丢了 launchd 缓存（2026-10-28）

用户在 2026-10-28 问「为什么 iOS16 的时候可以出？问题出在哪里」。本文按差集回答这个问题，并给出一条把现象解释掉大半的实证：从 `bbmetal17` 那轮起，载荷不再带 `rootdev=md0 launchd_unsecure_cache=1`，iOS 26 的 launchd 因此从未收到 `/System/Library/xpc/launchd.plist`，缓存里 733 条 `AppExtensions` 一起丢了。

## 1. 结论

四件事分开记，因为它们的证据强度不同。

- ✅ **守护进程数量不是桌面内容的决定项。** 同一份根盘（`33ed5fc9`）、同一份 `system26.apfs`（`d11083be`）、同样 27 条任务的 2026-10-27 12:40 那轮，桌面是 15 个应用、2 个带名字的小组件、4 个 Dock、Search 胶囊。这一条把「只跑 30 条所以撑不起依赖网」关掉。
- ✅ **启动参数丢了 launchd 缓存，这是确定的回归。** `bbmetal18` 起的每一轮，日志里都没有 `Using unsecure cache` 与 `Cache sent to launchd successfully`，`launchd_cache_loader` 的 `Skipping boot-task` 一轮出现 1000 次；`§38`／`§39` 那两轮三行齐全。
- 🔍 **缓存缺失能解释扩展那一半，图标数 15→2 那一半尚未归因。** 扩展：没有 `AppExtensions` 就没有 `.appex` 宿主进程，chronod 只能报 `Extension not found`，小组件停在 `Waiting…`，壁纸的 posterkit provider 走同一条路。应用数：待验。
- 🔍 **16.5 那边是数量级的差别，但那条差别在 26 上不是必要条件。** 16.5 那份能出 15 个图标的载荷是 `REST=1` 建的，`/redwood/LaunchDaemons` 里有 388 个 plist，`com.apple.mobile.installd` 是由 Mach 查找按需拉起的。

## 2. 差集：16.5 的 388 条与 26 的 31 条

16.5 那份 working payload 的 job 生成走 `userland/build.sh` 的 `IOS_JOBS` 加 `mkjobs.py --rest`。`--rest` 只有 `REST=1` 时才生效，默认不带。默认的 `IOS_JOBS` 是 21 条（`notifyd`、`cfprefsd`×2、`logd`、`syslogd`、`distnoted`、`diagnosticd`、`fseventsd`、`containermanagerd`×2、`runningboardd`、`backboardd`、`mobile.usermanagerd`、`mobilegestalt.xpc`、`lsd`、`powerd`、`analyticsd`、`logd_helper`、`iconservicesagent`、`pluginkit.pkd`、`SpringBoard`），加 `wifid` 是 22 条；`--rest` 把 491 个 LaunchDaemon 与 12 个 LaunchAngel 里剩下的、带 MachServices 且程序在盘的全部加上，产物是 388 条。

直接证据在 `docs/progress/evidence/2026-10-25-codex-gpu-resume/kernel-queue-wait-s23-auto-default/run/s002.log`：启动时会打印 `/redwood/LaunchDaemons` 的内容，去重后 388 个 `.plist`。同一份日志里 `com.apple.mobile.installd` 是 `launching: ipc (mach)` 拉起在 `user/501` 域，也就是它不在那 21 条显式清单里，是被 `lsd` 或别人问起来才起的。`--rest` 保留 MachServices、删掉 `RunAtLoad`／`KeepAlive`／`StartInterval` 与其余启动触发器，所以「388 条」只说明登记条目数，说明不了同时运行的进程数。

iOS 26 侧现在跑 31 条：`build.sh` 的 23 条（21 条加 `systemstatusd`、`wifid`）加 4 条 `com.redwood.*` 加 `package.py` 的 4 条（`chronod`、`PosterBoard`、`replicatord`、`mobile.installd`）。把同一份 `mkjobs.py --rest` 套 iOS 26 的 628 个 LaunchDaemon 与 32 个 LaunchAngel，得到 535 条。差集是 504 条，其中与登记直接相关的都在里面：`installd`、`pkd` 的依赖、`containermanagerd` 之外的用户域服务、`ondemand`、`mobile.attachmentd` 一类。

**这条差集成立，但它不是 26 上桌面空的充分解释**，见下一节。

## 3. 反例：同样 27 条任务，桌面是完整的

`hackios-xnu-kernel/out/ios26-resume/air-arm64e-device/` 那轮（`§39`，2026-10-27 12:40 采样）用的是根盘 `33ed5fc9`，也就是 `package.py` 现在的 `BASE`；系统盘 `d11083be` 与今天各轮相同；`LaunchDaemons` 同样是 27 条，没有 `chronod`、没有 `PosterBoard`、没有 `installd`。那轮的原始帧缓冲 `device/screen-04.raw` 转成 PNG 后是完整桌面：15 个应用、2 个带名字的小组件（Weather／Calendar）、4 个 Dock、Search 胶囊。转好的图存在同一目录的 `device/screen-04.png`。

再往前 `§38` 那轮（`plane-ffma-redwood-drm-repeat/device/screen-07.png`）是控制中心打开时的画面，模糊背景里能数出 4 个 Dock 图标和成排的应用图标。`§22` 那轮（`native-display-device/device-45.png`）是同一套布局，两个小组件有名字，只有图标内容有灰块。

`air-arm64e-device/on/root.apfs` 与 `plane-ffma-redwood-drm-repeat/root.apfs` 逐文件比过，只差 `/lib/libredwoodair.dylib` 一个。也就是说「桌面从 15 个掉到 2 个」这件事，发生在这份根盘之后，根盘内容本身没有参与。

## 4. 丢失的是启动参数，不是守护进程

好轮与坏轮的 boot-args 差两个词：`rootdev=md0` 与 `launchd_unsecure_cache=1`。

iOS 26 的 launchd 不扫描 `LaunchDaemons` 目录，任务与扩展记录都来自 `/System/Library/xpc/launchd.plist`，这份缓存由 `mkcache.py` 用我们的任务表生成、不签名，`launchd_unsecure_cache=1` 让 `launchd_cache_loader` 跳过签名校验直接把它送进去（`userland/mkcache.py` 的文件头写了这条）。loader 自己的字符串表也印证：它读 `kern.bootargs`，读到 `launchd_unsecure_cache=` 就打 `Using unsecure cache: %s`，否则走 `SecStaticCodeRef` 加 AMFI 的信任缓存校验。

日志两侧对得上：

- 好轮（`air-arm64e-device/device/log-01.bin`）：`launchd_cache_loader Doing boot task`、`Using unsecure cache: /System/Library/xpc/launchd.plist`、`Cache sent to launchd successfully`。
- 坏轮（`bbmetal18`、`bbm26`、`bbm27`、`bbm28`）：上面三行各 0 条，`Skipping boot-task` 一轮 1000 条。整轮日志里也没有 `Code: …Sig: …`、`cdhash`、`Trying to send bytes` 这些签名路径的输出，loader 在更早的分支就退出了。

`AppExtensions` 是缓存里唯一与扩展有关的键，733 条。它没送到，launchd 就没有任何 `.appex` 的登记，这正是 `bbm27` 那轮的三个读数：`.appex` 宿主进程 0 条、chronod 的 `Extension not found` 两条、小组件 `Waiting…`。`Symlinks` 只有 2 条且都指向 framework 里的 dylib，`SystemLibraryTreeState` 是 framework 清单，两者与图标数无关，所以应用数那一半不能靠这一条解释。

## 5. 什么时候丢的

不是某次提交删掉的。`tools/k90auto/make-payload.py` 在 `dad51cb`（2026-10-26 09:19）进来时，固定 cmdline 里就没有这两个词，`docs/plan/k90auto-run-protocol.md` 第 3 节列「常用的 EXTRA BOOT-ARGS」时也没列它们。它们一直靠调用方写在第四个参数 `EXTRA BOOT-ARGS` 里。

按 `manifest.json` 的 `epoch` 排序，转折点在 `kernel-12377-cpufreq-report-airarm64e-c-metal3`（`epoch=1793081943`，有）与 `kernel-12377-step-airarm64e-a`（`epoch=1793084784`，没有）之间，也就是 2026-10-27 16:05 到 16:46 之间。再往后的四十多轮全部没有。谁在那一次忘了写进 `EXTRA` 没有记录：`run-queue.sh` 只把 `run-auto.py` 的输出留在 `run-<name>.log` 里，`make-payload.py` 的调用参数只进 manifest。

所以没有可修的单点。防线只能放在「关键参数必须在场就失败」上，已在 `make-payload.py` 里加：最终 cmdline 缺 `rootdev=md0` 或 `launchd_unsecure_cache=1` 就直接断言失败，并把 `required_cmdline` 写进 manifest，以后看一条 diff 就知道那轮带没带。

## 6. 这一条能解释什么、不能解释什么

能：扩展发现、`.appex` 宿主、chronod 的 `Extension not found`、小组件 `Waiting…`、壁纸的 posterkit provider。这几件事指向同一个缺失的表。

「SpringBoard 建图标模型时向谁要应用列表、那次请求发生在什么时刻、失败后会不会重拿」这三个问题要分开对待，而且前两个已经不需要再查。**向谁要**有定论：LaunchServices 的应用库，经 `LSApplicationWorkspace` 读到 `SBApplicationController` 的应用清单，`installd` 是这条链的上游之一。**什么时刻**与**会不会重拿**在「launchd 里根本没有扩展登记表」这个前提下没有意义——问题不在枚举的时机或重试，在表的缺失。只有缓存补齐之后扩展记录仍为 0，才轮到查这两个；那就是探针 `lsprobe` 要回答的问题的定义。

不能：为什么 LaunchServices 只认得 2 个应用。缓存里没有应用清单，`LaunchDaemons` 我们照样注入了 31 条，`installd` 与 `lsd` 都起得来。这一半的候选是同轮一起变的另外几项（内核从 `41888cad` 换到 `12377` 的 `c1f19249`／`647145b`、加 `metal=1`、backboardd 注入、`rc.jobs` 换脚本），需要一轮把它们分开。

另外要记的是 `bbm27` 补 `installd` 为什么完全没有效果：它修的是「`lsd` 够不到 `installd`」这一半，而 `lsd` 够不到 `installd` 并不是桌面空的原因。那一轮的测量本身成立（查找 8→0、pid 13 稳定、`crashes 0`），结论「补它就能出图标」不成立。

## 7. 下一步：一轮只改一处

下一轮把启动参数加回去，其余与 `bbm27` 相同，420 秒。判据按顺序：

1. 日志里出现 `Using unsecure cache` 与 `Cache sent to launchd successfully`，`Skipping boot-task` 不再每轮 1000 条。
2. `.appex` 宿主进程非 0，`Extension not found` 归零。
3. 探针 `lsprobe` 在 t=60 与 t=300 打印的应用数、bundle id、扩展记录数。
4. 截图里的图标数、页码圆点、小组件是否还是 `Waiting…`。

如果第 1 条成立而图标仍是 2 个，就说明图标数与缓存无关，第 6 节列的那几个候选要单独开一轮，不要在这里反复试。

## 8. 探针 `lsprobe`

`hackios-xnu-kernel/userland/src/lsprobe.m`，`PROBE=1` 时由 `package.py` 编成 `/bin/lsprobe` 并往 `etc/rc.jobs` 追加一行 `/redwood/bin/lsprobe 60 300 &`（结尾的 `&` 必须有：`init` 的 `run_command` 默认等前一行跑完，会把后面的手势脚本压到 300 秒之后）。它只读，不改系统镜像。

打印三组：`LSApplicationWorkspace allApplications` 的应用数与每个 bundle id（括号里是那个 proxy 携带的扩展记录数）、`MobileInstallationLookup` 的条数、`/Applications` 与 `/private/var/staged_system_apps` 的目录项数、`/private/var/mobile/Library/MobileInstallation` 的目录项数、`/private/var/mobile/Library/SpringBoard/IconState.plist` 是否存在。

## 9. 缺失服务 × 调用次数（每轮复用）

判据是日志里 `Code=4099`（`The connection to service named X was invalidated`）的服务名。口径写明：**raw** 是跨快照求和的原始行数，**unique** 是 `merged_log()` 合并去重后的唯一行数，报数用 unique。

`biomed` 那一轮（`kernel-12377-attr-biomed`）：`Code=4099` 原始 1568 行、唯一 470 行，全部来自 `chronod`。

| 服务 | raw | unique | plist 指向的程序 | 程序在盘上 | plist |
|---|---|---|---|---|---|
| `com.apple.linkd.registry` | 1376 | 412 | `/usr/libexec/linkd`（2,165,136 字节） | 是 | `com.apple.linkd.plist` |
| `com.apple.appprotectiond.read` | 84 | 31 | `/usr/libexec/appprotectiond`（73,584） | 是 | `com.apple.appprotectiond.plist` |
| `com.apple.duetactivityscheduler` | 55 | 15 | `/usr/libexec/dasd`（2,572,640 字节） | 是 | `com.apple.dasd.plist` |
| `com.apple.coreduetd.context` | 未测 | 6 | `CoreDuetContext.framework/Resources/contextstored`（106,256 字节） | 是 | `com.apple.contextstored.plist` |
| （行内没有服务名） | 35 | 10 | — | — | — |
| `com.apple.accountsd.accountmanager` | 未测 | 24 | InfrastructureAccounts 的 `accountsd` | 未查 | 未查 |
| `com.apple.accountsd.accountmanager` | 18 | 2 | `Accounts.framework/accountsd`（88,672） | 是 | `com.apple.accountsd.plist` |
| `com.apple.biome.access.user` | 0 | 0 | `BiomeStreams.framework/Support/biomed` | 是 | 已补（上一轮） |

`persona4` 轮（`kernel-12377-attr26-persona4`）去重后的 `Code=4099` 是 108 行：`appprotectiond.read` 36、`duetactivityscheduler` 24、`accountsd.accountmanager` 2、行内没有服务名 46。`accountsd.accountmanager` 是这一轮新出现的名字，**未处理**，排在 `appprotectiond.read` 之后。

**两类 4099 要分开**：`The connection to service named com.apple.X` 是 launchd 查找失败，与注册有关；`The connection to service created from an extension was invalidated` 是扩展连接断开，每行带扩展名，是「扩展进程起了又死」的旁证。上面这张表只统计第一类，第二类 `persona4` 有 46 行。

**注册两个作业的效果（去重唯一行）**：`coreduetd.context` 在 continuous 是 3，`contextstored` 进包后 persona3 与 persona4 都是 0；`duetactivityscheduler` 在 continuous 25、persona3 26、persona4 24，`dasd` 进包后（`kernel-12377-attr26-dasd`）为 **0**，同轮探针进程表里有 `pid=41 name=dasd path=/usr/libexec/dasd`，整轮日志里 `duetactivityscheduler` 三个字出现 **0** 次。`appprotectiond.read` 同轮从 36 变 40，未处理。

**口径提醒**：早期几处数字是把 `s0xx.log` 重叠快照直接相加得到的，虚高 3 到 4 倍（同一份日志能读出 156 这种数，去重后是 36）。以 `tools/round-stats.py` 的输出为准，它按行去重后再按服务名分组。

「程序在盘上」这一列按 plist 的 `ProgramArguments[0]` 去 `ios26/system.manifest` 与抽取出来的 `ios26/rootfs` 上找，不按名字猜目录：`accountsd` 的程序在 `Accounts.framework` 根目录下而不是 `/usr/libexec`，按名字找会误判成缺失。完整的「job 在、程序不在」对照见 [launchd 程序审计](2026-10-28-launchd-programs-audit.md)：661 个 job 里 19 个（18 个程序）的程序在抽取时被 `select-system.py` 的路径前缀与大小规则跳过，16 个只在共享缓存里。

`com.apple.linkd.registry` 占 unique 的 88%。它是 `com.apple.linkd`（`/usr/libexec/linkd`，`UserName` mobile）10 项 `MachServices` 之一，Apple 的 plist 没有 `RunAtLoad`、带 `EnablePressuredExit`，所以按需启动，处理方式与 `biomed` 相同。它的 `LaunchEvents` 监听 LaunchServices 的应用注册／注销通知，而这一轮开机头几秒内有约 259 个应用注册，因此它可能被反复唤醒。观察项：整轮里 `linkd[pid]` 出现过几个不同 pid。一两个说明它稳定；几十个说明它在开机那几秒被反复唤醒又回收，这条 `LaunchEvents` 在这个环境下代价很大，那时再谈摘掉它。

**这条线到此收尾，剩下的不补。** `biomed` 与 `linkd` 两个大缺口（412 行与 0 行）补完，剩下的都在几十行量级且各有副作用：

- `dasd`（提供 `duetactivityscheduler`）不补：它一启动就接管整个后台调度（`bg.system.task`、`dasd.end-prewarm`），会按自己的策略跑后台任务，把性能与温度两条线的测量搅乱。它的影响超出「多了负载」：它本身就是后续性能测量的干扰源；将来若必须补，测量口径要先改成「有后台任务在场」的版本。
- `contextstored`（提供 `coreduetd.context`）与 `coreduetd` 不补：挂在 CoreDuet 的上下文预测上，读同一批 knowledge 流，依赖面比 `dasd` 还深，各自只占 6 行与更少。
- `appprotectiond`（31 行）不补：属 App Protection／隐私面板，我们不走 `tccd` 那条线，补了大概率只换来另一个连接错误。

以后不要再把这三条当成待办。`com.apple.duetexpertd`（98,672 字节、33 项 `MachServices`，含 `proactive.HomeScreenSuggestion.xpc` 与 `proactive.SuggestedPages`）属于另一类：程序在盘上，但它在 `mkjobs.py` 的 `DENY` 里，是策略上排除，不进缺口统计。

本轮只补 `linkd`。`appprotectiond.read` 与 `accountsd` 各差一个量级以上，且每补一个都是一个变量；两者的程序都在盘上，后补只是加 plist 的事。这两项常被当成同一个进程提供的，实测不是：`com.apple.duetactivityscheduler` 是 `com.apple.dasd`（`/usr/libexec/dasd`，2,572,640 字节）的 `MachServices`，`com.apple.coreduetd.context` 是 `com.apple.contextstored`（`CoreDuetContext.framework/Resources/contextstored`，106,256 字节）的。`com.apple.coreduetd` 自己（`/usr/libexec/coreduetd`，361,696 字节）提供的是 knowledge、people、pairedsync 那一组，不含这两个名字。三个程序的 plist 与程序都在，所以都不是抽取缺口；`dasd` 一启动就会接管后台调度，副作用面比另外两个大。`com.apple.duetexpertd` 也在镜像里（`/usr/libexec/duetexpertd`，98,672 字节，33 项 `MachServices`），它在 `mkjobs.py` 的 DENY 里。

## 10. 未验证

- 缓存补齐之后应用数会不会从 2 变成 64，没有验证。
- `Skipping boot-task` 的具体判定分支没有读到。`launchd_cache_loader` 的字符串表能证明它读 `kern.bootargs` 里的 `launchd_unsecure_cache=`，但它在本轮日志里连 `Using default cache paths` 都没打出来，说明退出位置更早；参数补回后这条自然消失，不值得先逆。
- 26 这三轮的回弹帧数（`bbm26` 不出帧、`bbm27` 32.2 帧/秒、`bbm28` 34.1 帧/秒）与「多跑几个守护进程」相关还是与缓存相关，要等这一轮之后再看，前后三个数一起引。
