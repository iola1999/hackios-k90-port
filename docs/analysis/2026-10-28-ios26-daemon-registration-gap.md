# 应用与扩展登记不完整：`lsd` 够不到 `installd`（2026-10-28）

桌面只有 2 个图标、没有页码圆点、小组件是占位块、翻页没有可翻的目标，这四件事在 `bbm26` 的截图与日志里指向同一处：应用与扩展没有登记进 LaunchServices，而 LaunchServices 够不到 `installd`。

## 1. 现象汇总

`bbm26` 的 105 张截图里，桌面只有 Photos 与 Settings 两个图标，Dock 是空的，`Search` 胶囊与 Dock 之间没有页码圆点，左上小组件是纯白块加 SpringBoard 自带的「Waiting…」标签。

镜像里可上桌面的应用远不止这些：`ios26/rootfs/Applications` 的 209 个应用里 193 个带 `SBAppTags = hidden`，只有 14 个不上桌面的例外；`ios26/rootfs/private/var/staged_system_apps` 的 50 个应用一个 `hidden` 都没有，构建时被搬进 `/Applications`。合计 64 个应用有资格占一个图标位，打包后的 `system.manifest` 里共有 259 个 `.app`。

## 2. 直接证据

`lsd[29]` 在 `bbm26` 里对 `com.apple.mobile.installd` 发出 8 次查找，全部返回 `failed lookup … error = 3: No such process`。同一个进程对 `com.apple.mobileactivationd` 还有 3 次失败查找。

`com.apple.mobile.installd` 不在我们那份 30 条的启动清单里，而这个清单是从 628 个 LaunchDaemon plist 里挑出来的。plist 与程序本身都在镜像里：`ios26/rootfs/System/Library/LaunchDaemons/com.apple.mobile.installd.plist`、`/usr/libexec/installd`（811,216 字节）；`com.apple.mobileactivationd.plist` 与 `/usr/libexec/mobileactivationd` 同样都在。

这条链的两端都有旁证：`pluginkit.pkd` 起来了（pid 41），`iconservicesagent` 起来了（pid 37），用户域 `user/501` 里有 67 个进程。缺的是它们依赖的服务，不是它们自己。

失败的规模：`bbm26` 整轮 `failed lookup` 中请求方为 SpringBoard 的有 8207 次，最多的是 `com.apple.sleepd.sleepserver` 3806 次、`com.apple.commcenter.xpc` 2218 次，其余 `com.apple.audio.AudioSession` 411 次、`com.apple.donotdisturb.service` 231 次、`com.apple.coremedia.*` 四类约 300 次、`com.apple.SystemConfiguration.configd` 121 次。这套 payload 在只跑 30 个守护进程的条件下运行。

## 3. 当时的因果推断（已作废，见 §11）

当时写的是：LaunchServices 的应用库由 `installd` 提供、`pluginkit.pkd` 从 LaunchServices 取扩展记录，`installd` 不在就两头都取不到，于是图标模型只建得出少数应用、页码圆点不出现、扩展记录缺失、小组件没有内容可画。这条推断在 §11 被实测推翻，保留在此只为说明后面几节的测量是按什么假设做的。

## 4. 「建完」这个信号看不到

`lsd` 这一轮只打了 548 行，绝大多数是 launchd 的 spawn 记录与那几条 failed lookup；`pkd` 一行日志都没有。串口转发只覆盖 6 个进程的默认级别 os_log，所以现在无法从日志判断应用枚举进行到哪一步，也无法判断它会不会自己建完。要看这个信号，得把 `lsd` 与 `pkd` 的日志级别打开。

## 5. 下一步

按 replicatord 的做法补进我们的 job 清单。两个候选：

`com.apple.mobileactivationd` 的 `UserName` 是 `root`，没有障碍，先加它风险最低，但它是激活状态的服务，与应用枚举的关系比 `installd` 弱。

`com.apple.mobile.installd` 的 `UserName` 是 `_installd`。`/private/var` 是每次开机重建的内存盘，`_installd` 这个用户很可能不在本地用户库里，spawn 会停在找不到用户上；`bbm26` 的日志里 `_installd` 出现 0 次，无从确认。加它之前要把 `UserName` 改成 `root`，或者先确认用户库里有没有这个用户。

成功判据按顺序看三件事：`lsd` 对 `com.apple.mobile.installd` 的失败查找归零；截图里图标数从 2 个增加、页码圆点出现；`chronod` 不再报 `Extension not found`、出现 `.appex` 宿主进程。第一条是本轮的直接判据，后两条要更多轮次才可能看到。

## 6. 未验证的部分

`installd` 在只有内存盘 `/private/var` 的条件下能否起来，没有验证。它依赖 `/private/var/mobile/Library/` 下的数据库文件，首启时会自己建库，但建库需要时间与写权限；如果它以 root 起来后立刻退出，这条链要改从 `mobileactivationd` 或者其他服务入手。

常量缓冲与圆角那两项与这条链无关，各自的结论在[圆角分析](2026-10-28-ios26-corner-aa-seams.md)。
## 7. `JOB_USERS`：为什么我们的 job 清单与 Apple 的 plist 不一致

`tools/k90auto/package.py` 里有一个显式映射表 `JOB_USERS`，把「plist 指定的用户在本环境不存在」这件事集中记录：键是 job 名，值是它在本环境里应该以谁的身份运行。目前只有一条，`com.apple.mobile.installd.plist` 对应 `root`。

这么做有两个理由。一是 plist 保持原样，与镜像里的那份逐字节相同，改动集中在一处，读的人一眼能看出我们改了哪条。二是 `/private/var` 是每次开机从根盘的 `etc/var.skel` 重建的内存盘，其中的用户库只含 root 与 mobile 这类必要条目，`_installd` 不在里面，直接照 plist 起会停在找不到用户上；这个前提以后如果变了，只改映射表一行就够。

以后再补需要换用户的 job，按同样方式加一行，不要改 `jobs/` 里那份 plist。判据是 `jobs/` 目录里的 plist 与 `ios26/rootfs/System/Library/LaunchDaemons/` 下同名文件逐字节相同。

## 8. `bbm27` 的结果：installd 到位，图标模型没有动

`bbm27` 与 `bbm26` 的唯一差别是把 `com.apple.mobile.installd`（`UserName` 改 root）与 `com.apple.mobileactivationd` 补进任务清单，`LaunchDaemons` 从 30 条到 32 条。

第一条判据成立：`lsd` 对 `com.apple.mobile.installd` 的失败查找从 8 次降到 0，installd 全程只有 pid 13 一个，没有重生、没有退出，`crashes 0`。`mobileactivationd` 是另一回事：`Service only ran for 0 seconds. Pushing respawn out by 10 seconds`，退避 10→20→40→80→160→320 秒，整轮换了 15 个 pid，属于启动即退。它已从任务清单里去掉。

第二条到第四条全部没有变化：`bbm27` 最后一张截图（`shot-04197`）桌面仍是 2 个图标、没有页码圆点、Dock 空、小组件仍是 `Waiting…`、壁纸全黑；`.appex` 宿主进程 0 条；`Extension not found` 仍是 2 条，时间点仍是开机后约 8 秒与 39 秒。

## 9. 时序读数：不是「lsd 查的时候 installd 还没起」

`bbm27` 的 spawn 时刻：SpringBoard `01:55:55.919761`、backboardd `01:55:56.182059`、lsd `01:55:56.696096`、installd `01:55:57.543593`、iconservicesagent `01:55:58.604726`、pkd `01:56:03.453296`。

`bbm26` 里 lsd 的失败查找发生在它自己起来后约 2.1 秒（lsd `01:16:46.773933`，失败 `01:16:48.880970`）。按同样的节奏，`bbm27` 里 lsd 那次查询落在 `01:55:58.8` 前后，此时 installd 已经存在 1.3 秒，所以失败消失是必然的。

在这之前 lsd 与 installd 都已经在了，图标仍然只有 2 个，说明缺的不是「lsd 查的时候 installd 还没起」。也就是说 installd 的连通性修好之后，图标模型依然不建。

## 10. 为什么这个问题现在答不了

要看 SpringBoard 什么时候、向谁要应用列表，需要它自己的日志。`bbm27` 整轮里 SpringBoard 只有 6 行，`lsd` 只有 launchd 层面的 spawn 与那几条记录，`pkd` 一行都没有，`installd[13]` 自己一行都没有（不是被转发的那几个进程）。串口转发只覆盖 6 个进程的默认级别 os_log。

所以「有没有第二次枚举」「失败后会不会重试」这两问，用现有日志无法回答。要回答要先把可见性做出来，两条路：把 `lsd`、SpringBoard、`MobileInstallation` 这几个子系统的 os_log 级别在系统镜像里调高（`/System/Library/Preferences/Logging/Subsystems/` 加一份配置，属于改镜像内容），或者把 `lsd` 与 `installd` 加进内核控制台转发的那 6 个进程名单里。

在这两条之前，能确定的只有：installd 可达性不是充分条件，420 秒内图标模型不会自己重建。`bbm27` 里 `swipe-right` 从「没有动画」变成 68 个间隔（32.2 帧/秒），是这一轮唯一的用户可见变化，记在[翻页定性](2026-10-28-ios26-page-turn-absent.md) §7。

## 11. 更正：主因是启动参数丢了缓存，不是缺守护进程

2026-10-28 由 desktop 找到的反例推翻了本文第 3 节的因果判断。同一份根盘 `33ed5fc9`、同一份 `system26`、同样 27 条任务的另一轮（10-27 12:40，`§39`）桌面是完整的：15 个应用、2 个带名字的小组件、4 个 Dock 图标、Search 胶囊。差别在启动参数——`rootdev=md0 launchd_unsecure_cache=1` 在 k90auto 工具链重写时丢了，`bbm18`～`bbm28` 全部没有这两个参数。

日志两侧可复核：好轮有 `Using unsecure cache: /System/Library/xpc/launchd.plist` 与 `Cache sent to launchd successfully`，`bbm27`／`bbm28` 这两句各 0 条，而 `launchd_cache_loader` 的 `Skipping boot-task` 在 `bbm28` 一轮里出现 1000 次。缓存没送到 launchd，那 733 条 `AppExtensions` 也一起丢了，`.appex` 宿主 0 条、`chronod` 的 `Extension not found`、小组件 `Waiting…`、壁纸的 posterkit provider 全在同一条路上。

因此：本文第 8～9 节关于 `installd` 的测量本身是对的（查找 8→0、进程 pid 13 稳定、`crashes 0`），但「补 `installd` 是解」这个判断错了；`installd` 与缺口无关。第 3 节那条从 8207 次失败查找推出的因果链要按本节读。补 `installd`、`replicatord` 两个 job 是否有副作用、是否保留，由 desktop 判定。

## 12. 方法教训：用失败查找次数定位缺服务，在缓存不完整时会得到一整套假因果

`bbm29`（启动参数带上 `rootdev=md0 launchd_unsecure_cache=1`）的实测把这条方法本身判掉了：`failed lookup` 从 `bbm27` 的 11306 次（其中 SpringBoard 9439 次）掉到 **0** 次。缓存送进 launchd 之后，服务命名空间就完整了，连「查不到」这条警告都不再打。

也就是说那 11306 次失败是缓存缺失的**后果**，不是缺服务的**证据**。按失败次数排序去补守护进程，在这个环境下会把整套缺失都归到错误的进程上：`sleepd.sleepserver` 3806 次、`commcenter.xpc` 2218 次看起来最像缺口，实际它们的名字在缓存里，只是缓存没送到 launchd。

保留下来的是测量本身：哪些查找失败过、补上 `com.apple.replicatord` 与 `com.apple.mobile.installd` 之后各自的查找归零、两个进程 pid 稳定且 `crashes 0`。作废的是从这些数字出发的因果推断。

同类教训适用于任何「按日志计数排优先级」的做法：先确认产生这些日志的那一层自己是对的（这里：launchd 有没有收到缓存），再拿计数当线索。

## 13. 扩展链路的当前状态：身份查找通了，进程拉起还没观察到

`bbm29` 里 `Extension not found` 为 0、`Unknown extension process` 为 0，`chronod` 能读到真实扩展名（`AdaptiveMusicWidget`、`CalendarWidget`、`FindMyWidgetItems` 等）。420 秒内没有宿主进程被拉起。

这两件事要分开记：「扩展身份能不能查到」已经通了，「扩展进程会不会被拉起」还没有观察到。前者是本文件 §2～§10 在追的那一半，后者是新的观察项，不能因为前者通了就认为小组件会出内容。
