# 让 chronod 晚启动、把 replicatord 补进任务清单（2026-10-28）

这一轮要回答的是：K90 上壁纸与小组件没有内容，是不是因为扩展身份的查询发生在 pluginkit 登记之前。证据链的另一端已经排除过两次——构建时 staged 应用确实进了系统镜像的 `/Applications`，launchd 缓存里那 733 条 `AppExtensions` 也不是扩展启动的前提（QEMU 用同一份缓存拉起了 8 个不在清单上的扩展）。剩下的差异只有时间：QEMU 的第一次同类查询在内核时间约 590 秒，K90 五轮都在开机后 8 秒与 39 秒，失败后重试分别排到 +1 小时与 +24 小时。详见[壁纸与小组件的扩展发现缺口复核](../analysis/2026-10-28-ios26-wallpaper-and-widget-extension-gap.md)。

## 1. 两个变量

变量一：`com.apple.chronod` 的首次启动时刻从开机后约 2 秒挪到约 120 秒。它启动时才发出 `[controls.store]` 与 `[timeline.store]` 那两批扩展身份查询，启动时刻挪后，查询就整体落在 pluginkit 与 LaunchServices 完成登记之后。

变量二：把 `com.apple.replicatord` 补进 launchd 任务清单。chronod 日志里每轮 80 条 `[replicatorClient] ReplicatorClient: Failed to establish a connection` 与 `Client is not registered`，对应 `com.apple.replicatorservices` 的失败查找；这个 Mach 名字在 `com.apple.replicatord.plist` 的 `MachServices` 里，而它原先没进那 29 条 `LaunchDaemons`。壁纸要出内容需要这条链路。

两个变量互不依赖，判据分开看：变量一的证据是 chronod 进程首次出现的时间，以及那三行 Task 的 `next attempt due at` 是否改变；变量二的证据是 `com.apple.replicatorservices` 的 failed lookup 数量与 `ReplicatorClient` 的连接结果。共同的成功判据是三条：日志里出现 `.appex` 宿主进程、chronod 不再报 `Extension not found`、截图里小组件不是纯白块。

## 2. 为什么不用 launchctl

原定的做法是开机后约 90 秒对 chronod 做 `launchctl kickstart -k`。这个 payload 里没有 `launchctl`：`apfs.py stat userland/system26.apfs /bin/launchctl` 与 `/usr/bin/launchctl` 都是 no such path，`apfs.py tree` 全盘搜不到，`ios26/rootfs` 里也没有。根盘 `root.apfs` 的 `/bin` 只有我们自己的测试与工具二进制，没有 shell，`/bin/sh` 与 `/redwood/bin/sh` 都不存在。改成用 launchd 自己的 `StartInterval` 排首次启动，不需要任何新程序。

## 3. `package.py` 的改动（改前与改后原文）

`hackios-xnu-kernel/out/ios26-resume/bbmetal-device/package.py` 在三个仓库里都没有被跟踪，所以把改动前和改动后的原文都记在这里，下一轮可以照着改回来。

改动一，`EXTRA_JOBS` 那一行。改前：

```
EXTRA_JOBS = ["com.apple.chronod.plist", "com.apple.PosterBoard.plist"]
```

改后：

```
EXTRA_JOBS = ["com.apple.chronod.plist", "com.apple.PosterBoard.plist",
              "com.apple.replicatord.plist"]
# chronod is started late on purpose. Every run so far asked for widget and control extension
# identities eight and thirty-nine seconds after boot, before pluginkit and LaunchServices had
# registered the extensions of the 259 applications, and gave up for a day. StartInterval with
# RunAtLoad off puts its first start at about 120 s, after that registration.
LATE_JOBS = {"com.apple.chronod.plist": {"StartInterval": 120}}
```

改动二，`add_extra_jobs()` 里设置 `RunAtLoad` 的那几行。改前：

```
        # RunAtLoad for both: nothing else here asks for either of them early. KeepAlive off, so
        # a service that cannot run in this boot is seen dead once in the log rather than
        # restarted for the length of the run.
        job["RunAtLoad"] = True
        job["KeepAlive"] = False
```

改后：

```
        # RunAtLoad for all: nothing else here asks for them early. KeepAlive off, so a service
        # that cannot run in this boot is seen dead once in the log rather than restarted for the
        # length of the run. The jobs in LATE_JOBS are the exception: their first start is put off
        # by StartInterval instead, so it lands after pluginkit has registered the extensions.
        job["RunAtLoad"] = True
        job["KeepAlive"] = False
        late = LATE_JOBS.get(name)
        if late is not None:
            job["RunAtLoad"] = False
            job.update(late)
```

改动三，打包末尾的断言。改前：

```
    for name in EXTRA_JOBS:
        extra = plistlib.loads(bodies["/LaunchDaemons/" + name])
        assert extra["RunAtLoad"] is True and extra["KeepAlive"] is False, name
        assert cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] == extra, name
```

改后：

```
    for name in EXTRA_JOBS:
        extra = plistlib.loads(bodies["/LaunchDaemons/" + name])
        assert extra["KeepAlive"] is False, name
        if name in LATE_JOBS:
            assert extra["RunAtLoad"] is False and extra["StartInterval"] == 120, name
        else:
            assert extra["RunAtLoad"] is True, name
        assert cache["LaunchDaemons"]["/System/Library/LaunchDaemons/" + name] == extra, name
```

改动四，新增 `jobs/com.apple.replicatord.plist`，内容原样来自 `hackios-xnu-kernel/ios26/rootfs/System/Library/LaunchDaemons/com.apple.replicatord.plist`（2286 字节）。系统镜像里没有这个 plist（`build.sh` 把 `System/Library/LaunchDaemons` 从镜像里删掉，任务改由缓存提供），但程序 `/System/Library/PrivateFrameworks/ReplicatorCore.framework/Support/replicatord` 在镜像里，86240 字节。

## 4. 打包结果

`python3 package.py` 通过，退出码 0。新根盘 `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs`，5165056 字节，SHA-256 `563c308e4f43c6e539e7245c5af1fa8ee89a420e42651611674d200473b9bc9b`（上一轮 manifest 记的是 `5bc0bbd790fa37215dbcef0970d17cc1a94b9256e74476ab8ded136f72c2a859`）。shim `c3b7ee4df0509f82690219fdb651367e1bb53f7d5b27ec100b2904449c03d5e8`，driver `edbf6e20fc7c853305bb779f3a34b3fb914725b13c32bac7ca9399f249e0f41d`，两个库与上一轮相同。

回读 `root.apfs` 里的 `/xpc/launchd.plist`，`LaunchDaemons` 30 条。`com.apple.chronod` 是 `RunAtLoad=False`、`StartInterval=120`、`KeepAlive=False`；`com.apple.replicatord` 是 `RunAtLoad=True`、`KeepAlive=False`，`MachServices` 含 `com.apple.private.alloy.replicator-idswake`、`com.apple.private.alloy.widgets-idswake`、`com.apple.replicatorservices`；`com.apple.PosterBoard` 未变。

## 5. 这一轮要看的东西

变量一：启动日志里 `chronod[<pid>]` 第一次出现的时间从开机后约 2 秒变成约 120 秒；`[controls.store]` 与 `[timeline.store]` 那三行 Task 的 `next attempt due at` 要么不再出现，要么时间变了。

变量二：`com.apple.replicatorservices` 的 failed lookup 从每轮 17 条降到 0，`[replicatorClient] ReplicatorClient: Failed to establish a connection` 从 80 条降到 0 或明显减少。

共同判据：日志里出现 `.appex` 宿主进程（进程名形如 `MusicWidgets`、`PhotosReliveWidget`）；chronod 不再出现 `[extensions] Extension not found`；截图里小组件不再是纯白块，锁屏与桌面壁纸有实际内容。

这一轮不引用帧率。旧工具给出的 fps 数字已被判定失真，`bbm24 最好`、`bbm25 掉了 8 帧` 这类结论不成立；要引用帧率只用 `summary.py --verify` 通过之后的数字。

## 6. 如果失败

变量一失败（chronod 在 120 秒启动后仍报 `Extension not found`）说明就绪时间不是原因，下一步要抓 `pkd` 与 `lsd` 的日志；当前串口只转发到 6 个进程的默认级别 os_log，`pkd` 一行都没有。

变量二失败（replicatord 起来但 `ReplicatorClient` 仍连不上）说明缺口在 replicatord 依赖的其它服务上，需要看它自己的日志。
## 7. 实跑结果（`bbmetal26`）

一轮 420 秒，参数与 `bbmetal25` 相同，根盘 `563c308e…`。

变量一没有执行。launchd 的第一条日志在 `2026-10-28 01:16:45.840002`，chronod 的 `internal event: WILL_SPAWN` 在 `01:16:46.699629`，也就是开机后 0.86 秒，触发原因是 `launching: ipc (mach)`。chronod 的 job 声明了 MachServices，别的进程第一次查找它的服务时 launchd 就当场拉起，`RunAtLoad=False` 与 `StartInterval=120` 都只是另外两个触发条件，关不掉这一个。结果是两次查询照旧发生：`[controls.store]` 在 `01:16:53.410944`（开机后 7.6 秒）、`[timeline.store]` 在 `01:17:24.102993`（开机后 38.3 秒），与之前几轮的时间点一致。就绪时刻这个假设这一轮没有被检验。

变量二按设计生效。`com.apple.replicatord` 在 `01:16:45.906236` 被拉起，pid 8。整轮 21 次快照里 `com.apple.replicatorservices` 的失败查找是 0 次（之前每轮 17 次），`[replicatorClient] ReplicatorClient: Failed to establish a connection` 从每轮 80 条降到 1 条。

共同判据没有通过。小组件仍是纯白块（`shot-04195`）；`Extension not found` 仍是那两条，时间点如上；`Unknown extension process` 6 次；两个扩展都没有宿主进程。chronod 在 38.3 秒之后整轮没有再查一次，说明它把重试排到了 +1 小时与 +24 小时，420 秒的轮次够不到。

结论：replicator 链路是真缺口，这一轮把它补上了，它对小组件出内容是必要条件；它不是扩展身份查找失败的原因。要检验就绪时刻，得让触发 chronod 的那次 Mach 查找本身往后挪，或者让扩展在开机后 7.6 秒前完成登记。前者要找到触发者（launchd 的日志只记 `ipc (mach)`，不记请求方），后者要改 `pkd` 与 `lsd` 的登记时机。
