# 小组件停帧对照轮：四件仪器与各自的判据

背景：`kernel-12377-attr26-continuous` 里 `tl: v` 与 `tl: s` 在 1581.0、1641.0、1701.0 秒三处各有 59.2～59.3 秒完全没有一帧（帧号与 swap 号都差 1），同一时段 `chronod` 在刷 `[Intents] -[INCWidgetIntentProvider _provideAppIntentWithOptions:…`（59 秒窗口内 342 条）与 `LNFetchOptionsDefaultValueConnectionOperation`（342 条）。这一轮要把「小组件每分钟抓取 Intent」与「合成器不提交」之间的因果定下来。

## 1. 四件仪器

- **`rwsig`**（`userland/src/rwsig.m`，`/redwood/bin/rwsig`）：同一轮里交替冻结与恢复 `chronod`、`extensionkitservice`、`pluginkit`，每次切换打 `rwsig: phase stop|resume round N at <us>`。它给的是**因果**：变量只有那几个进程在不在跑。
- **`kern.redwood.thread_dump`**（`osfmk/kern/redwood_threads.c`）：在空洞窗口内写一次 `backboardd` 的 pid，打每个线程的 `state`／`wait`／`pri`／`pc`。它给的是**谁在等谁**。
- **`chronod`／`linkd`／`pluginkit` 的日志**：Intents 抓取有没有返回，还是等一个不存在的目标进程（`Specified target process does not exist` 那条线的延续）。
- **`lsprobe`**：开机后各阶段的外部观测（扩展宿主数量、`posterboard` 目录、`pluginkit` 目录），用来描述这一轮处于什么状态。

## 2. `rc.jobs` 的排法

```
/redwood/bin/lsprobe 60 300 &
/redwood/bin/rwsig 60 60 3 chronod extensionkitservice pluginkit &
```

`rwsig` 在每个冻结相位的第 5 秒主动要一次 `backboardd` 的线程 dump（`kern.redwood.thread_dump`），写失败打 `rwsig: thread dump refused errno E`，同一相位只写一次，`backboardd` 的 pid 在相位内变了按新 pid 再写一次。理由：库里那条观察线程只在某个 commit 超过 2500 ms 未前进时触发，而空洞期间 `backboardd` 根本没有 commit 在跑，触发条件不成立。一轮下来有 3 次主动 dump，加上真有 commit 卡住时的触发式 dump。

两行互不依赖，一个死了另一个照跑。`rwsig` 的相位时刻与 `tl: v` 同一个时钟（`mach_absolute_time` 微秒），判读时按 `rwsig: phase …` 切口，不用墙钟。

## 3. 判据：每一件看什么

`rwsig` 给出三组对照，每组的读法固定为「冻结相位与恢复相位的帧率之比」：

- **冻结相位帧率明显低于恢复相位** → 冻结 `chronod` 让合成器更堵。方向与「抓取把合成器堵住」相反，说明合成器在等 `chronod` 的回包；这一条成立时下一步查 `chronod` 的 XPC 服务端。
- **冻结相位帧率明显高于恢复相位** → 抓取期间确实在挤占合成器；因果成立，下一步是让那些抓取不发生在主线程路径上。
- **两相位差不多** → 59 秒空洞与这几个进程无关，回到驱动与合成器内部找。

相位对齐还回答 15 秒级空洞与 59 秒级空洞的关系（两者都是 `tl: s` 空洞）：两者都在冻结相位消失或都在恢复相位出现，算同源；两种相位里都出现，算不同源。上一轮的时间结构已经把这条缩小到「同一节拍器的两种频率」：15 秒级空洞结束于 1427.9～1580.3 秒、间隔 15.0 秒，最后一个之后换成结束于 1640.3、1700.3、1760.3 秒的 59.2 秒空洞、间隔 60.0 秒，两种不重叠。

`thread_dump` 的读法沿用三类：全部线程同一个 `wait` 地址（等同一个事件）、`wait` 不同但 `pc` 落在同一函数段（同一条串行路径）、`state` 不在等待态而 `pc` 不动（自旋或被挂起）。**dump 要在空洞内取**：`commit` 观察线程只在一个 commit 超过 2500 ms 未前进时才写 sysctl，所以空洞期间才有内容。

日志侧的判据只有一条：那 59 秒里 `chronod` 的 Intents 行有没有对应的完成行。只有发起没有完成，说明它卡在等回来；发起与完成都有，说明抓取本身很快，问题在它与合成器的资源竞争。

## 3.1 已经量到的两条（供这一轮对照）

**同一个实例。** 这一轮全部 2,931 行 `INCWidgetIntentProvider` 与 `LNFetchOptions*` 都来自 `chronod` pid **51**，分布在该进程 39 个线程上；整轮日志里 `chronod[` 只出现过 pid 51（10,818 行）。**没有重起**，所以那些行是同一个进程的周期性工作，不是「重起后重新抓取」。

**两种空洞在时间上接续，不重叠。** 15 秒级的 3.02 秒空洞从 1405 秒左右起，结束时刻为 1427.9、1442.9、1457.9、1472.9、1488.4、1506.0、1520.3、1536.0、1551.0、1566.0、1580.3 秒，**间隔 15.0 秒**；最后一个 15 秒级空洞在 1580.3 秒结束，此后 15 秒的节拍消失，换成结束于 1640.3、1700.3、1760.3 秒的 **59.2 秒空洞，间隔 60.0 秒**。也就是 1580.3 秒前后是同一现象的两种节拍，第一种停、第二种起。这一条写进判据：**两种空洞是否同源，看它们在 `rwsig` 的相位里是否一起消失**；时间上的接续本身已经说明它们至少被同一个节拍器驱动。

## 3.2 退避假设与判伪它的观测

**假设**：某个客户端在等一个回包，等不到就重试，重试间隔从 15 秒退到 60 秒。15 秒级与 59 秒级空洞是同一问题的两个阶段。

**已经找到的对应行**（`kernel-12377-attr26-continuous`，`chronod` pid 51）：

- `[descriptor] [com.apple.stocks::com.apple.stocks.widget] query failed - retrying in 3 seconds (1 attempts remaining): Error Domain=CHSErrorDomain Code=1001 "Watchdog provision violated for getAllDescriptors"` —— 88 次；
- `[session] [stocks.widget-4F9A91C1DB57] Session operation: getAllDescriptors watchdog fired. Cancelling session.` —— 99 次；
- 另有 `[XPCErrors] [C:76] Error received: Connection interrupted.`、`[com.apple.stocks.widget] Remote object proxy error`、`Could not get attrs using bssendp for connection com.apple.xpc.anonymous.…, pid -1` 与 `Unable to resolve default intent (appintent:…)` 成组出现。

也就是：**`chronod` 向小组件扩展要描述符，`getAllDescriptors` 的 watchdog 到期，会话被取消，3 秒后重试一次，再一次就到下一轮**。`pid -1` 那条说明连接的另一端没有进程。

**能判伪它的观测**（这一轮按这四条取数）：

1. `retrying in` 的 `attempts remaining` 是否出现过大于 2 的次数，以及相邻两次重试的间隔是否出现 15 秒与 60 秒两档；只有 3 秒一档且没有第二档，退避假设不成立。
2. `watchdog fired` 的时刻与空洞的起止是否对齐。对齐说明「会话卡住」就是「不提交帧」的那个原因；只是同周期则未必。
3. `bssendp` 失败里的 `pid` 是否恒为 `-1`。恒为 `-1` 说明目标进程从未存在；出现真实 pid 说明目标起过又退出了。
4. 冻结 `chronod` 之后，`watchdog fired` 与 `retrying in` 是否一起消失。一起消失说明这两类行全部来自被冻结的那个进程；仍然出现说明另有来源。

第 4 条与 §3 的相位判据同源：**如果 15 秒与 60 秒两种空洞都在冻结相位消失，就可以把它们当一个问题处理**。

## 3.4 两轮的停帧档位不同（待判）

`kernel-12377-attr26-continuous` 里先出现 15 秒级空洞（结束于 1427.9～1580.3 秒、间隔 15.0 秒、3.02 秒长），1580.3 秒之后换成 60 秒级（1640.3、1700.3、1760.3 秒、59.2 秒长），两档接续不重叠。`kernel-12377-attr26-persona` 到 2400 秒为止**只有 15 秒级**（8 处、2.0～3.0 秒、结束于 2316.5～2397.2 秒、间隔 15.0 秒），没有进 60 秒级。

两轮的差别在于有没有人在要内容：60 秒档若只在页面或小组件被实际刷新时出现，它比 15 秒档更依赖「有客户端在请求」。判据放在 ①b、①c 两轮：如果补了 `contextstored` 之后 15 秒档仍在、60 秒档消失，两档就是不同来源；如果两档一起消失，它们是同一条链上的两个阶段。

## 4. 中止与重起

- `rwsig` 在冻结相位里连续 90 秒没有新帧（读 `kern.redwood.frames`）就恢复全部并退出，打 `rwsig: abort, no frames for 90 s`。这一条按主动放弃记录。
- 如果设备在冻结 `chronod` 期间重起，按「本轮因冻结 chronod 重起」归档并保留。`rwsig: abort`（我们主动放弃）与重起（设备侧）在日志里可区分。
- 冻结用 `SIGSTOP`：这些 job 有 KeepAlive，`SIGKILL` 会让 launchd 立刻拉起，测到的是重启而不是守护进程本身。

## 3.5 ①d：`appprotectiond` 一轮已取消

**这一轮取消**：`nochronod` 轮的空洞仍在 493.1／508.2／523.2／538.2 秒、间隔精确 15.0 秒，说明 15 秒周期与 chronod 无关，`com.apple.appprotectiond.read` 的 4099 计数不在这个节律的上游，单独一轮没有可判伪的读数。下面保留的是取消之前的计划，作为「为什么当时打算跑」的记录。

## 3.6 ①d（已取消）：`appprotectiond` 一轮的前置条件与双读数

`com.apple.appprotectiond.read` 是 `Code=4099` 计数里最大的单个服务名（去重后 `persona3` 44、`continuous` 45）。一个作业提供它全部八项 `MachServices`（`read`、`write`、`guard`、`maintenance`、`extensionmonitor`、`extensioninfo`、`viewsubjectmonitor`、`viewsubjectinfo`），所以注册 `com.apple.appprotectiond.plist` 就是让这个查找有对端。原 plist 没有 `RunAtLoad`，因此按需形态、与 `contextstored`／`dasd` 同样处理。

前置条件：那一轮的内核必须带 `8776c5d` 的三行日志（`died on signal`、`corpse slots full`、`corpse refused`）。理由是 `appprotectiond` 的 `extensionmonitor` 与 `viewsubjectmonitor` 盯的正是扩展与视图主体，与宿主崩溃同一片；没有这三行，「`read` 归零」是唯一读数，副作用看不见。

两条判据一起读。`com.apple.appprotectiond.read` 归零而 watchdog 违反条数不变，说明 4099 与 watchdog 是两条独立的线；两者一起下降，说明 `appprotectiond.read` 在 watchdog 的上游。watchdog 按扩展统计的口径见第 3.4 节那一轮的分布：7 个扩展、22 条，`stocks.widget` 7 与 `AdaptiveMusicControl` 6 合计占 59%。

## 3.6 三行死因日志的读法与空结果的边界

`8776c5d` 加了三条：`redwood: proc … died on signal … code …`（`exit1`，不依赖 corpse）、`redwood: corpse slots full at …`（`task_mark_corpse` 失败分支）、`redwood: corpse refused pid … footprint … limit …`（`memorystatus_allowed_vm_map_fork` 拒绝）。

读之前要先确认这一轮到底有没有宿主死。`kernel-12377-attr26-persona3` 有 4 条 `Process[<pid>] crashed: <comm>. Too many corpses being created.`（去重后），`kernel-12377-attr26-persona4` 在**同一个旧内核**上是 **0 条**（`crashed:`、`Too many corpses`、`died on signal`、`corpse refused` 全为 0）。所以宿主崩溃不是稳定复现的现象，**「三行都没打」不能直接读成「没走到 `exit1`」**——先要确认这一轮宿主有没有起、有没有退。

**固定判读顺序**（先立有死亡、再分死因）：

1. 三行里有 `died on signal`：直接按信号分类。11 指段错误（我们侧的库或驱动）、4 指非法指令（缺的能力或指令特性）、6 指 abort（断言），`code` 给基原因码。
2. 只有 `corpse refused`：看 `footprint` 与 `limit` 的比值。接近或超过 `limit` 说明是进程体积被拒；远小于 `limit` 却出现，说明前面有崩溃占着名额。
3. 三行都没有，且 `Process[… ] crashed:` 也没有：这一轮没有记录到宿主死亡。要另找「宿主起过没有、退过没有」的读数（探针进程表里有活的宿主，`chronod` 的 descriptor 记录里有拉起与超时），**不能据此推断崩溃路径**。

一句话的判据：**先立「有宿主死亡」，再用三行分死因**；顺序反过来会把空结果当结论。

## 3.65 60 秒档可复现，但与 core 进程重启不在同一时间段

两轮都出现「先 15 秒级、后 60 秒级」的接续：`continuous` 轮 15 秒级结束于 1427.9～1580.3 秒、之后 60 秒级在 1640.3／1700.3／1760.3 秒；`persona4` 轮 15 秒级在 264.6、267.6、282.6、297.6、312.6、342.6 秒，60 秒级从 414.2 秒起（59.3 秒、59.2 秒、51.8 秒三处）。形态一致，因此这是可复现的现象。

`persona4` 里 `backboardd` 从 36 换成 131、`SpringBoard` 从 30 换成 136，新 pid 首现 06:25:36.839 与 06:25:37.295，**重启发生在轮次约 190 秒处，而 60 秒档从 414 秒才开始**。两件事都在同一轮里，但不是同一时间段，**不作为一条因果**；要判它们是否相关，需要两个读数：重启前后各一段的帧空洞位置，以及 `335953f` 那一行 `exited` 出现的时间戳与空洞的先后。

## 3.7 ①c 的判据：归零只算第一句

`com.apple.duetactivityscheduler` 的 `Code=4099` 三轮读数（去掉快照重复后）：`continuous` 25、`persona3` 26、`persona4` 24。注册 `com.apple.dasd` 之后判据分两句写：

1. **主判据**：该服务名的 4099 从 24 归零；
2. **旁证**：`dasd` 是否出现在探针的进程表里（`dasd=NNN`），以及 `chronod` 的刷新预算查询是否还在发——即 `/device/dasd/widgetBudget`、`widgetSystemAdded`、`widgetOverride` 那三个键路径是否仍有记录。

归零只算第一句通过。第二句要回答的是「查询还在发，只是有人接了」还是「查询本身不发了」。两句合起来才说明这一轮改到了什么。

这条与几条同类规则同形：日志里某个错误消失，可能因为修好了，也可能因为那件事不再发生。`iconstate=1` 只说明文件在、不说明 SpringBoard 读了它；`mobileinstallation_dir=0` 只说明目录在、不说明 `installd` 写了东西。「错误消失」与「行为改变」分开看，前者是第一句，后者是第二句。

## 3.75 驱动 no-copy 缓冲这一轮的判据

`redwoodmetal.m` 的 `newBufferWithBytesNoCopy:length:options:deallocator:` 原来无条件返回 nil，现在用 `newBufferWithBytes:` 复制一份并在复制后调用调用方传入的 `deallocator`。依据是 `kernel-12377-attr26-dasd` 的时间线：`06:37:41.368038` 的 `nil buffer from memory`，`61` 毫秒后两条 `Metal failed to build render pipeline`，同一毫秒 `backboardd` 的 `signal 6 code 4`，`114` 毫秒后新 `backboardd` 起来，随后 `1.4` 秒内 49 个前台进程被 `SIGKILL`。

判据四条，`round-stats.py` 的「Metal refusals and the no-copy path」一节直接给前两条的数：

1. `no-copy served as a copy` **非零**且 `nil buffer from memory` 归零。改动前三轮 `nil buffer from memory` 的唯一行数是 `dasd` 68、`persona4` 61、`persona3` 67。**不写「同量级」**：前者是 `RW_AGAIN` 的打印条数，实际调用几百次也只打印几条，用同量级会假失败。
2. `nil buffer from memory` 归零。
3. `Metal failed to build render pipeline` 归零（改动前三轮都是 2 条），`backboardd` 的 `signal 6 code 4` 归零（`dasd` 轮 1 条），`signal 9 code 0` 那批集体杀归零（`dasd` 轮 49 条）。
4. 分叉：`served as a copy` 有而第 3 条仍有，说明管线失败另有来源；`served as a copy` 与 `nil buffer from memory` 都归零，说明调用方没走这条路，回去查 `newBufferWithIOSurface:`，看日志里写的是 memory 还是 surface。

`served as a copy` 这一行是 `RW_AGAIN` 打印（首次、2、4、8…），**它的条数是打印次数、不是调用次数**，不能当成调用总数读。

## 3.8 宿主被看门狗杀死的直接证据与 ①d 的可判伪假设

`kernel-12377-attr26-dasd` 是第一次拿到死因本身的一轮，新内核那三行里 `died on signal` 出了 9 条，其中 7 条是宿主：

```
redwood: proc AccessibilityCon pid 105 died on signal 9 code 1001
redwood: proc BridgeWidgetExte pid 76 died on signal 9 code 1001
redwood: proc com.apple.mobile pid 78 died on signal 9 code 1001
redwood: proc FitnessWidget pid 108 died on signal 9 code 1001
redwood: proc NewsTag pid 74 died on signal 9 code 1001
redwood: proc PassbookWidgetsE pid 109 died on signal 9 code 1001
redwood: proc ScreenTimeWidget pid 106 died on signal 9 code 1001
```

七条与本轮 `Watchdog provision violated` 的七个扩展一一对应（`AccessibilityControlsExtension`、`BridgeWidgetExtension`、`mobilenotes.WidgetExtension`、`FitnessWidget`、`news.tag`、`PassbookWidgets`、`ScreenTimeWidgetExtension`）。`signal 9` 是 SIGKILL，`code 1001` 就是 `CHSErrorDomain Code=1001`。所以宿主不是段错误、非法指令或 abort，是策略杀：宿主没在 watchdog 时间内回答 `getAllDescriptors`，`chronod` 取消会话并按 15 秒／60 秒两档重试，到期后宿主被 SIGKILL。

**①d 的假设**：`appprotectiond` 是宿主回答描述符查询时要调用的服务，它从来不在我们的作业表里，所以七次查询超时与七次击杀是同一件事的两端。

看门狗杀的数量随轮次与驱动变化很大：`persona4` 0 条、`driver1` 8 条、`dasd` 26 条。所以 ①d 判「24／26 → 0」必须在**同一驱动、同一轮次形态**下比较，不能跨轮取数；这与「帧 id 断档」是一条规则的两种用法——断档多说明整轮被切碎，那时连同轮内的数也要按段看。

**可判伪形态**：①d 那一轮跑完，如果 `com.apple.appprotectiond.read` 的 4099 归零而 `died on signal 9 code 1001` 仍是 7 条，假设不成立，`appprotectiond` 只是被查找的一方、不在描述符查询路径上。

判据三条，前两条是主判据：

1. `died on signal 9 code 1001` 从 7 条降到 0；
2. `Watchdog provision violated for getAllDescriptors` 归零；
3. `com.apple.appprotectiond.read` 的 4099 从 36～45 降到 0。

**SIGKILL 不产生崩溃报告**：这一轮 `crash_files=0`、`DiagnosticLogs` 目录消失，而七个宿主确实被杀了。所以「把崩溃报告带回来」对这类死亡没有用，`died on signal` 是唯一记录，下一轮不必等报告文件。

## 3.76 `9/0` 那 49 条集体杀的名单

按名字聚合（`kernel-12377-attr26-dasd`，唯一行 49 条、48 个不同名字，`com.apple.mobile` 两条是两次启动的两个容器）：

`AdaptiveMusicCon`、`AdaptiveMusicWid`、`AppStoreWidgetsE`、`BarcodeScannerWi`、`BatteriesAvocado`、`BatteriesWidgetE`、`BatteriesWidgetI`、`BooksWidgetExten`、`CalendarWidgetEx`、`com.apple.mobile`×2、`ControlCenterCon`、`FindMyWidgetItem`、`FindMyWidgetPeop`、`GAXAppWidgetExte`、`GeneralMapsWidge`、`HealthBalanceWid`、`HealthMedication`、`HealthMentalHeal`、`HomeWidget`、`HomeWidgetLockSc`、`IntentsExtension`、`MirroredWidgetEx`、`MusicRecognition`、`MusicWidgets`、`NewsTag`、`NewsToday2`、`NewsTodayIntents`、`PassbookLockedWi`、`PhotosReliveWidg`、`RecordWidgetExte`、`RemindersIntents`、`RemindersWidgetE`、`SafariWidgetExte`、`ShortcutsWidgetE`、`SleepWidgetExten`、`Spotlight`、`SpringBoard`、`TipsWidget`、`ToggleAirplaneMo`、`TrackingUIServic`、`TranslationWidge`、`TVRemoteWidgetEx`、`TVWidgetExtensio`、`TypeToSiriWidget`、`VoiceMemosSettin`、`WeatherIntents`、`WeatherWidget`、`WidgetRenderer_D`。

名单里除 `SpringBoard` 与 `WidgetRenderer_D` 之外都是扩展宿主，另有一个 `com.apple.mobile`（两个容器实例）。`chronod`、`pkd`、`installd`、`containermanag`、`lsd`、`iconservicesagent`、`replicatord`、`PosterBoard`、`backboardd` 都不在其中，`backboardd` 是上一毫秒 abort 的那个。这份名单与「`SpringBoard` 与扩展是 `backboardd` 的客户端」一致：渲染服务器 abort 之后，前台会话的客户端被一起结束。

## 3.77 驱动 `92d383b` 那一轮的判据与两条读数纪律

`driver1` 轮用 `bef13a3` 跑，结果分成两半：`nil buffer from memory` 从 61～68 归零、`served as a copy` 9 条（1,277,952 / 62,464×2 / 32,768×3 / 16,384 字节），说明复制这条路走通；同一轮 `backboardd` 连死五次、间隔约 10 秒，全部 `signal 11 code 11`，原因是在创建 buffer 时就调用了 `deallocator`，把调用方还在用的内存提前释放。`92d383b` 把释放挪到 buffer 销毁时。

下一轮单一变量是 `92d383b`，判据三条：

1. `signal 11 code 11` 归零（`driver1` 跑完全轮是 **13 条**，全是 `backboardd`）；
2. `nil buffer from memory` 保持 0、`served as a copy` 非零。旁证（不作判据）：`32,768` 那一档的打印次数应降到个位数——`driver1` 是 13 次、与它 13 次重启数相同，因为 `RW_AGAIN` 的静态计数在每个新进程里从 0 开始；这个数还受进程数影响，只看趋势；
3. `Metal failed to build render pipeline` 归零（基线 2 条）、`backboardd` 的 `6/4` 归零、`9/0` 回到 `dasd` 轮的量级（48 个名字；`driver1` 是 113 条、`SpringBoard` 死 13 次）。

分叉：第 1、2 条达成而第 3 条仍有，转向 `MTLCompilerService`；三条全达成，这条重启链到此结束。`MTLCompilerService` 单独一轮，因为 `MTLCompilerServi` 被 `9/9` 杀 3 次可能是 `backboardd` 反复重启的结果，并列进来分不清。

两条读数纪律：

- **帧 id 断档次数是「这一轮能不能作基线」的第一判据**：`round-stats.py` 摘要行末尾的 `id gaps` 是帧 id 的跳变次数，一次跳变对应一次重启（新的合成器从新计数开始）。四轮读数：`persona3` 1、`persona4` 1、`dasd` 1、`driver1` **13**，与 `backboardd` 的 13 次段错误、`SpringBoard` 的 13 次死亡完全对应。这个数大于个位数时，整轮被切成多段，帧率与空洞都不能跨轮比。
- **一轮里重启超过一次时，空洞统计没有跨轮可比性**。`driver1` 轮 `tl: s` 3,589 次、空洞 7 处、最长 16.5 秒、没有 60 秒档，看着比前三轮好；那是 `backboardd` 死五次、`SpringBoard` 死三次把整轮切成六段的假象，**不写成「停帧变短」**。
- 1.2 MB 那块按字节复制对每帧预算有代价，但**在崩溃链存在时任何性能数都无法解释**。这条记成待办：等重启链断掉之后再评估阈值或另作处理。

## 3.78 三次驱动实现的读数与两次实现错

同一个接口上我犯了两次错，两轮都留下证据，两轮都不可作基线。

| 轮次 | 驱动 | `nil buffer from memory` | 管线建立失败 | `11/11` 段错误 | `9/0` | 帧 id / id gaps |
|---|---|---|---|---|---|---|
| `driver1` | `bef13a3`（创建时调用 `deallocator`） | 0 | 2 | 13（`backboardd`） | 113 | 3623 / 13 |
| `driver2` | `92d383b`（`deallocator` 存原指针，销毁时调用） | 0 | 0 | 18（`backboardd` 14、`SpringBoard` 4） | 109 | 49 / 7 |
| `driver3` | `2866235`（`deallocator` 存堆副本） | 0 | 0 | 15（全是 `backboardd`） | 118 | 44 / 8 |

三次实现的共同点是「返回一个真实 buffer，而先前返回 nil」；`dasd` 轮（改动之前）`11/11` 是 0、只有 1 条 `6/4`。所以段错误与这次改动有关，但三次实现都没消掉它，说明原因不在 `deallocator` 的时机与生命周期。`e932...` 那次打点在 `handle_user_abort()` 里输出了故障地址与 pc，用来区分三种可能：故障地址落在调用方 buffer 区间（不可读内存或释放后被读）、pc 落在 `libredwoodmetal`（用到失效指针）、pc 落在分配器（重复释放）。

`driver3` 的每一代 `backboardd` 寿命是 10.2 秒，死亡紧贴最后一条日志（1 毫秒内），而最后那条日志每次不同（`Orientation`、`Backlight`、`Display`、`TouchEvents` 都有），所以 10 秒更像定时路径。

两次错的形态：第一次把调用方的内存在创建时就释放，调用方随后访问那块内存；第二次保存了调用方传入的 block 原指针，而 CA 传的多是内联栈 block，buffer 销毁时调用它等于跳进已释放的栈帧。`759d45e` 存堆副本并在调用后释放。

`driver2` 也给出一个正向结论：**`nil buffer from memory` 归零之后，`Metal failed to build render pipeline` 从 2 条归零**。「`nil buffer` 是管线失败的上游」这条成立，剩下的是段错误这条链。

判据（`driver3`，用 `759d45e`）：`11/11` 归零（基线 18）、`nil buffer` 保持 0 且 `served as a copy` 非零、管线保持 0、`9/0` 回到 48 个名字的量级（`driver1`／`driver2` 是 113／109）、`id gaps` 回到 1。

## 3.79 no-copy 契约（改驱动之前先写）

写在 `redwoodmetal.m` 的 `-newBufferWithBytesNoCopy:length:options:deallocator:` 上方，同一份抄在这里：

- **`deallocator` 谁调用、什么时候调用**：调用方传入，驱动调用；在返回的 buffer 被销毁时调用一次。这是 Metal 契约里调用方内存不再被需要的那一刻，不是创建时。
- **block 存原指针还是副本**：存堆副本。调用方常传内联 block，那在调用方栈上，buffer 销毁时指针已失效。
- **所有权三个时刻**：创建时调用方把内存交出来并不再使用；驱动复制字节，因此从不以所有者身份持有那块内存；销毁时调用 block 释放调用方交出的内存。分配失败时立即调用 block，因为内存同样已交出、且没有对象会活过这次调用。

前两条各花掉一轮才学到（`driver1` 与 `driver2`，都是 `backboardd` 的 `SIGSEGV`）。读这段的成本是零，用轮次去试的成本是一轮十分钟加一条可能被覆盖的证据。

## 3.80 挂起：`nil buffer` 这条线退回到返回 nil

`90c3df0` 把 `userland/src/redwoodmetal.m` 恢复到 `f973d37` 的内容（`newBufferWithBytesNoCopy:` 返回 nil），一次提交说明恢复，没有生成反向提交链。

**挂起时的现状**（`dasd` 轮，改动之前）：

- `nil buffer from memory` 68 条唯一行；
- `Metal failed to build render pipeline` 2 条；
- `backboardd` 一次 `signal 6 code 4`；
- `11/11` 段错误 0 条；
- `tl: s` 7,600、帧 id 1..7601、空洞 15 处。

**三次实现的结果，同口径四轮**：

| 轮次 | 帧数 | `11/11` | `9/0` | `nil buffer` | 管线失败 |
|---|---|---|---|---|---|
| `dasd`（改动前） | 7,600 | **0** | 49 | 68 | 2 |
| `driver1` | 3,626 | 14 | 114 | 0 | 2 |
| `driver2` | 49 | 19 | 115 | 0 | 0 |
| `driver3` | 44 | 15 | 118 | 0 | 0 |

段错误是这次改动引入的，收益只有「管线失败 2 条归零」，代价是渲染基本停住。这个交换不成立，因此退回。

**挂起时最有价值的观测**（`kernel-12377-attr26-badaccess`，内核带 `e933479` 打点）：

```
redwood: backboardd bad access at 0x3a7265766c6f7365 pc 0x2abead9c0   → "esolver:"
redwood: backboardd bad access at 0x4e5a5f203a6e6f69 pc 0x2abead9c0   → "ion: _ZN"
redwood: backboardd bad access at 0x696c632e7373656e pc 0x2abead9c0   → "ness.cli"
redwood: backboardd bad access at 0x767265536472616f pc 0x2abead9c0   → "oardServ"
redwood: backboardd bad access at 0x80000c00000000   pc 0x2abead9c0
redwood: backboardd bad access at 0x80000c000c0000   pc 0x2abead9c0
redwood: backboardd bad access at 0x51fff4f7eba5832  pc 0x2abeadad4
```

故障地址里装的是符号名或路径的片段，说明某个指针字段被字符串内容覆盖后又被解引用；`pc` 六次同为 `0x2abead9c0`，而同进程的 `driver code at` 在 `0x100c40164`／`0x101304164`（约 4.3 GB），所以崩点不在 `libredwoodmetal` 里。写坏的动作发生在我们返回真实 buffer 之后。

这一对日志（`bad access at` 与 `driver code at`）保留在代码里，是这次四轮驱动唯一留下来的工具。在重开这条线之前，任何 `backboardd`／`SpringBoard` 的段错误都会带这两行，可以直接用 `tools/symbolize.py` 判归属，不必再改代码。

**重开条件与第一步**：若将来要修 `nil buffer`，第一步加两行打印——`rw_print` 的 `served as a copy` 带上 `[buffer contents]` 指针与 `length`，`-dealloc` 打一条 `released %p/%zu`。**同一个 `(contents, length)` 出现两次就是重复释放；否则是 `memcpy` 越界写**（`mesa.buffer_map` 的映射短于 `length`）。

## 3.81 桌面线第一问：解锁那一刻之后不再提交

不依赖截图的读数，全部来自 `kernel-12377-attr26-driver-revert`（驱动已回退，`usable as a performance baseline`）。

**读数一：`command buffers: N committed` 的斜率**。驱动每秒打一次累计提交数，同一进程内单调递增，差分就是提交速率：

| 时间段 | 提交速率 | 画面（截图对照） |
|---|---|---|
| 18.3～181.3 s | 每行 `+64`，约 64 次/秒 | 103.2～182.1 s 锁屏可见 |
| 181.3～259.3 s | 78 秒里 `+64`，约 0.8 次/秒 | 185.6 s 起纯黑 |

**读数二：`tl: s` 与面板帧率在 181 s 之后继续**，`tl: s` 全轮 7,751 次、空洞 13 处最长 17 s，`MiniIOMobileFramebuffer` 的 5 秒窗口一直是 20～60 帧/秒、没有零帧窗口。**合成器继续提交换出，但驱动侧的提交停了**：面板拿到的是重复或空的帧。

**读数三：转折点紧贴手势**。`[TouchEvents] contact 1 presence: touching` 在 178.8 s，触摸投递到 `contextID:EB6313CD` 在 179.5 s，`contact 1 presence: none` 在 181.3 s；**最后一次 `+64` 也在 181.3 s**。同一段里出现 6 条 `nil buffer from memory`（179.5～180.4 s）。

**判据（改 AIR 之后跑一轮）**：

1. `Metal failed to build render pipeline` 与 `this render pipeline is refused` 都归零；
2. `backboardd` 的 `6/4` 归零、`SpringBoard` 与 `backboardd` 的 pid 全程只有一个值；
3. 最终判据是截图里出现主屏，档位由 `round-stats.py` 的 `screens` 一节判（`order:` 一行给出整轮的档位顺序）。

**一处计数口径**：`command buffers: N committed` 每行都是累计值，同一进程内单调递增；换进程会从 0 重来（93.0 s 新 `backboardd` 从 64 重新开始），所以**只比较同进程内的相邻两行**。它判「有没有东西被画过」，判不了「是否一直在画」——静态主屏画完之后不再提交新的 command buffer（§3.82）。

## 3.82 结论：桌面停在解锁之后的根因在着色器编译器

单一变量是 AIR 的 `AIR_OP_INSERTELT`（库 `d7b9ced5a115c08c`，改前 `c26e86ec7367f7ad`；`air_to_nir.c` 摘要 `35b6f62ef90982f9`），其余不动。

**根因链**：一个片元着色器用运行时下标做 `insertelement` → 翻译器只接受常量下标，整个片元模块被拒 → 渲染管线建不起来（`Metal failed to build render pipeline`）→ `backboardd` abort（`signal 6 code 4`）→ 会话重起，`SpringBoard` 与全部前台扩展被 SIGKILL → 桌面停在解锁之后，屏幕由锁屏变为纯黑。

**过程判据四条全归零**（`kernel-12377-attr26-airindex`）：

| 判据 | 回退轮 | `airindex` |
|---|---|---|
| `this render pipeline is refused` | 1 | 0 |
| `Metal failed to build render pipeline` | 2 | 0 |
| `signal 6 code 4`（`backboardd` abort） | 1 | 0 |
| `signal 9 code 0`（集体杀） | 54 | 0 |
| `signal 11 code 11` | 0 | 0 |
| 帧数 / 帧 id 断档 | 7,751 / 1 | 3,550 / 0 |
| 截图最高档 | 锁屏（`black x1 -> lock x24 -> black x69`） | 主屏（`home screen x94`） |

**最终判据达成**：`shot-01384`（138.4 秒）起是主屏，状态栏 `8:17`、天气与日历两个小组件、四列图标、`Search` 胶囊、底部四格 dock。

**同一轮被否掉的另外四个候选**，都曾在不同时间被当作可能原因：

- **buffer 分配**：`nil buffer from memory` 在这轮仍有 21 条，而桌面画出来了。三次把 no-copy 请求改成复制的轮次（`driver1`／`driver2`／`driver3`）反而让帧数从 7,600 掉到 3,626／49／44 并引入 `signal 11`。这条线挂起（§3.80）。
- **容器**：`containers_mobile=240`、`containers_plugin=866`、`workspace=258`、`workspace_extensions=296` 从 `persona4` 起没变，而 `persona4` 与 `airindex` 的画面完全不同。
- **图标模型**：`iconstate=1`、`icondomain=1` 从 `persona4` 起没变，主屏这轮画出来了，图标位置与数量由 SpringBoard 画出。骨架里 `grep -c IconState` 为 0 且 `/private/var` 是每次开机重建的 ramfs，说明这个文件是本次开机写出来的；它与「画不画得出来」无关。
- **persona**：`persona4` 轮修的是 `mobileinstallation_dir=-1→0`，之后帧数仍在 7,700 量级但画面只有锁屏。**「帧数正常而画面是锁屏」这一点本身就把两种情形分开了：渲染没工作，与渲染工作了但画出来的内容不对。** `persona4` 属于后者的一种——它每秒交出的帧数不少，交出去的内容却不是主屏。

四类的共同点：它们都能解释「某个东西缺失」，但没有一类能解释「为什么 `backboardd` 每隔一段时间以 `signal 6 code 4` 退出一次」。**abort 才是这条链的观测入口，而 abort 的原因在管线建立失败，管线建立失败的原因在一条 `insertelement`。**

**一处口径修正**：`command buffers: N committed` 只判「有没有东西被画过」，不判「是否持续在画」。这一轮它在 3,520 次、86.4 秒之后不再增长，而主屏是好的——**静态主屏画完之后不需要重画**。回退轮里它从 64 次每秒掉到 0.8 次每秒才是真停。

## 3.83 渲染停住而系统活着：要现场

`kernel-12377-attr26-gestures` 与 `kernel-12377-attr26-airindex` 的帧数差两个量级（17 对 3,550），**而两份归档里都查不到本轮用的是哪个 `rc.jobs.*`**：`pack` 段有 `jobs_effective` 与 `round_notes`，没有作业脚本名与哈希。所以「两轮的差别只有手势脚本」这句话不成立；**观测到的只有帧数差异本身**，作业脚本一项已请 desktop 补记。

**注入这一侧可以排除**，按 `tl: p TYPE FINGER X Y at US`（`bsd/dev/redwood_input.c:208`，常量在 `bsd/sys/redwood_input.h:20-27`）逐条核对 `gestures` 轮的去重记录：

| 类型 | 含义 | 条数 |
|---|---|---|
| 1 | 手指按下 | 8 |
| 2 | 移动 | 426 |
| 3 | 抬起 | 8 |
| 4／5 | 按键按下／抬起（`finger` 是键号，坐标固定为 0） | 1／1 |

8 次手势都是完整的「按下—移动—抬起」，`finger` 恒为 0（单指），相邻样本间隔 8 毫秒（`rwtouch.c` 的 `SAMPLE_MS = 8`），时间戳是内核在投递时取的 `mach_absolute_time`。**所以「每个采样被当成独立按下」「缺移动事件」「时间戳失真」三个候选都不成立，问题在注入之后。**

一条同步的前置事实：`tl: p` 只在 2 的幂次打印（`RW_AGAIN`），**日志里的 426 条移动不代表 426 次移动**，按 8 毫秒与手势时长推算实际约 3,750 次。所以这一列只能判「有没有发生」。

**`framewatch` 的作用与 `rwsig` 分开**：`rwsig` 主动冻住进程、问它此刻卡在哪；`framewatch` 等系统自己停下、在停下那一刻要 dump。这一轮是系统自己停的（`backboardd` 与 `SpringBoard` 的 pid 全程未变、没有死因记录），所以需要后者。

```
framewatch STILL_SECONDS MAX_DUMPS [名字...]
```
每秒读一次 `kern.redwood.frames`；连续 `STILL` 秒不增长时对每个名字各要一次 `kern.redwood.thread_dump`，打 `framewatch: no frames for %d s at %llu, dump asked for %s pid %d`；超过 `MAX_DUMPS` 后继续每秒打 `framewatch: still no frames, %d s at %llu`；帧数恢复时打 `framewatch: resumed at %llu after %d s`；退出时打 `framewatch: done, %d stalls, longest %d s at %llu`。

**判「停住」只用 `kern.redwood.frames`（每次 swap 递增、不节流），判「停了多久」只用 `mach_absolute_time`。** 程序不读任何打印节流的计数。`resumed` 那一行是分开超时与死锁的唯一读法：自己恢复的停住是等待超时，永不恢复的才是死锁。

**下一轮配置**：`framewatch 5 3` 加 `rc.jobs.perf` 的拖动脚本。判据：线程栈停在哪一个锁或 fence；`resumed` 的条数与每次时长；帧数总量是否回到千级。

## 3.84 性能打点：已有的两套与它们各自能回答的问题

`tools/mesa/draw-perf.patch` 加 `util/perf_draw.h`，默认开启，每一轮的日志里都有（`airindex` 轮 248 行）。两套行量的是不同的东西：

| 行 | 频率 | 采样方式 | 能回答 |
|---|---|---|---|
| `perf driver <N> us: %u draws in <N> us, tracking %llu prog %llu emit %llu draw %llu us, max %llu us` | 帧耗时超过阈值时一行 | **只在慢帧上采样** | 慢帧长什么样 |
| `perf flush 128: <N> us/flush max <N>; %llu draws; batch submit <N> max <N>; driver <N> max <N>; own <N> (track %llu prog %llu emit %llu draw %llu); submit <N> max <N>; client <N> max <N>; sync <N> max <N>, pass <N> max <N>; calls %llu in (condition %llu, multi %llu); prog_calls %llu prog_variants %llu` | 每 128 帧一行 | **无条件采样** | 占比与均值 |

**所以占比只能读 `perf flush` 的 `own (track prog emit draw)`。** `perf driver` 只在超过 6 ms 的帧上打点，拿它的 `prog` 除 draw 数会系统性高估：同日同一轮里 `perf driver` 给出每 draw 的 `prog` 是 83～259 µs，而 `perf flush` 的 128 帧窗口里每次提交（约 7 个 draw）一共只有 320 µs。

**两个环境变量**：`FD_PERF_DRAW=0` 全关；`FD_PERF_SLOW_US=<微秒>` 只改慢帧明细的门槛，设得比任何一帧都大就只留 `perf flush`（默认 6000）。

**`prog_calls` 与 `prog_variants` 是窗口增量**，不是累计值：前者是 `get_program_state` 的调用数，后者是其中真正走 `ir3_cache_lookup` 再造变体的次数。两者接近说明每次都在造新变体，缓存没有复用；差得远说明成本在键计算与查找上。

## 3.85 补丁链的 reject 逐条判定与源码摘要口径

`mk-mesa.sh` 在 26.x 上允许旧补丁的块失败，失败会写成 `.rej`；`--batch` 之后不再出现交互提示。**`.rej` 只说明「某条补丁的某块没打上」，能力可能由另一条补丁提供，判断某段代码在不在的唯一依据是去树里查符号是否存在，不查出现次数。** 六个 reject 的判定：

| reject 文件 | 判定 | 依据 |
|---|---|---|
| `a6xx/fd6_draw.cc` | 已生效 | `prev_draw_read_fb` 在树里，由 `freedreno-darwin.patch` 与 `rebase-26/0003-restore-*` 各提供一次 |
| `freedreno/freedreno_batch.c` | 已生效 | `fd_perf_batch_cuts` 在树里，同上两条补丁 |
| `freedreno/freedreno_screen.c` | 过期 | 26.2.5 里没有 `ram_size`、没有 `sys/sysinfo`，块要改的代码已不存在 |
| `freedreno/meson.build` | 已生效 | `idep_air` 在树里出现两次，三条补丁都带 |
| `freedreno/drm/meson.build` | 已生效 | `virtio` 的 `link_with` 在树里 |
| `ir3/ir3_nir_lower_io_offsets.c` | 过期 | 26.2.5 的 `ir3_nir_try_propagate_bit_shift` 只处理 `ishl`／`ishr`／`ushr`，`nir_op_iadd` 与 `create_shift` 都不存在，守卫没有对象 |

`ir3-shift-split.patch` 的块 1 因此成为死代码，靠 `-Wno-unused-function` 不出警告；**该补丁整体对 26.x 不适用**。

**库的身份记源码摘要，不记库的 sha。** 同一棵树两次构建的库字节不同（`a9d028a1`／`86f379dc`／`371eacfd`），差异来自未纳入摘要的构建输入；重链同一目标可复现，说明差异不在签名。摘要覆盖 `.c`／`.cc`／`.h`／`meson.build`／`meson_options.txt`：

```
cd mesa-26.2.5 && find src \( -name '*.c' -o -name '*.cc' -o -name '*.h' -o -name 'meson.build' -o -name 'meson_options.txt' \) -print0 | LC_ALL=C sort -z | xargs -0 cat | shasum -a 256
```

2026-10-28 的值是 `ae0dc59becb76b43585302e1c142a3cedacf5f2401d951179f95e551b226ee9c`。每轮 manifest 同时记源码摘要、库 sha 与 `out/patch.log` 三样。
