# 开机后的处理器占用与 launchd 任务集（2026-10-31）

用户在 2026-10-31 反馈：开机后主屏没有图标，打开一个应用后图标才出现；没有壁纸和右上角电池图标；滑动卡、机身发热。本文记录处理器占用的来源、修法与修后读数。图标的原因与处理器占用无关，单列在 §5。

## 1. 结论

- 处理器占用来自 launchd 任务集之外的服务。这一启动只登记 37 条任务，Apple 的 23G90 缓存有 691 条；几个客户端在服务查找失败后立即重连，中间没有等待。SpringBoard 主线程在 Sleep.framework 里重建到 `com.apple.sleepd.sleepserver` 的连接，`com.apple.MapKit.SnapshotService` 在 GeoServices 里重连 `geod`，`appprotectiond` 与 `ScreenTimeAgent` 在 DeviceManagement 里重连 `com.apple.dmd`。launchd 为每次查找应答，IPI 随之升到每个处理器每秒约 1.1 万到 1.3 万次。
- 修法是按需登记其余任务。`tools/k90auto/package.py` 的 `REST=1` 调用 `userland/mkjobs.py --rest`，把带 Mach 服务、程序在系统盘上的 LaunchDaemon 与 LaunchAngel 全部登记，去掉 `RunAtLoad`、`KeepAlive` 等启动条件，只在有进程查找它的服务时才启动。16.5 能出完整桌面的载荷用的是同一种任务集（[任务缓存分析](2026-10-28-ios26-icon-model-and-launchd-cache.md) §2）。
- `mkjobs.py` 的 `DENY` 是 16.5 时期写的，这一启动改两处：放行 `com.apple.dmd`，去掉 `com.apple.PerfPowerServices`。理由见 §3。
- 修后（`kernel-12377-cmd24-rest2`）没有进程持续占用处理器，20 秒中断采样数从 315249 降到 34872。天气小组件显示「Location Access Needed」，`geod` 与定位服务开始应答。
- 图标、壁纸与电池图标没有随之出现，三者另有原因。

## 2. 读数

三轮都用内核 `12377-cmd24`，巡检相同：解锁后 1 秒截图，40 秒后再截一张，随后取一次 `ps`。表中是这次 `ps` 的累计用户态／内核态秒数。`rest2` 的巡检在第二张截图前重启了 SpringBoard，表中 SpringBoard 一行是重启后的新进程，不参与比较。

| 进程 | `xpc1`（37 条任务） | `rest1`（`REST=1`） | `rest2`（再改 `DENY`） |
|---|---|---|---|
| SpringBoard | 34.6／24.2 | 10.8／6.0 | 重启过 |
| launchd | 8.8／19.0 | 4.5／6.4 | 2.2／1.8 |
| appprotectiond | 5.5／2.1 | 45.5／12.8 | 0.1／0.1 |
| ScreenTimeAgent | 未运行 | 6.3／1.6 | 0.3／0.1 |
| PerfPowerServices | 未登记 | 24.3／0.7 | 未登记 |
| logd | 3.1／5.9 | 1.2／1.6 | 0.7／0.7 |
| 进程数 | 129 | 254 | 238 |

- `xpc1` 的 SpringBoard 主线程 12 次回溯都在同一条链上：libxpc 同步发送 ← Sleep+0x57d4 ← Sleep+0x58b0 ← Sleep+0x5518 ← Sleep+0x52bc ← Sleep+0x54d64（dispatch 块）。Sleep.framework 的 `sub_274B2E574` 在连接为空时打「rebuilding connection」并新建连接，`sub_274B7DB70` 逐条重发待发消息（「retrying message」）。服务不存在时每次发送立即失败，失败又清空连接，循环没有退避。
- 2026-10-28 的 `bbm26` 已记下 SpringBoard 对 `com.apple.sleepd.sleepserver` 有 3806 次失败查找（[服务登记缺口](2026-10-28-ios26-daemon-registration-gap.md) §2），当时没有归到处理器占用上。
- 中断采样（`kern.redwood.prof`，20 秒）：`rest1` 共 315249 个样本，空闲占 74%，主要占用者是 PerfPowerServices、ScreenTimeAgent、appprotectiond；`rest2` 共 34872 个样本，空闲占 84%，没有单个进程超过 4%。

## 3. `DENY` 的两处改动

- `com.apple.dmd`：16.5 时因「启动、崩溃、再被查找」列入 `DENY`。在 23G90 上它不登记的代价更大：`rest1` 的 appprotectiond 与 ScreenTimeAgent 的回溯都在 Catalyst 与 DeviceManagement 的连接代码里，DeviceManagement 只查找 `com.apple.dmd` 与 `com.apple.dmd.policy`。`rest2` 放行后 dmd 启动一次、累计 0.2 秒，两个客户端回到 0.1 到 0.4 秒。
- `com.apple.PerfPowerServices`：`rest1` 里它的一个线程停在 `dispatch_once` 内逐个读取 SMC 键（libSMC `SMCGetKeyFromIndex`，调用方 PowerlogLiteOperators），占半个处理器且不结束。它是功耗日志服务，本启动没有需要它的功能，所以不登记。
- 两处都写在 `package.py` 的 `REST_ALLOW`、`REST_DENY`，`mkjobs.py` 本身不变，16.5 的构建不受影响。

## 4. 观测工具

这一批为定位占用加了四样东西，用法写在各文件头。

- 内核 `12377-cmd24`：`kern.redwood.prof_on`／`prof_pid`／`prof` 在每次中断时采样被打断的 PC 与 LR，按进程汇总；`rwsh dump PID` 打印进程每个线程的用户态回溯与共享缓存 slide；`kern.redwood.cpus` 按类型统计 IPI；`kern.redwood.say` 让任意进程写一行内核日志。
- `tools/k90auto/prof.py`：把一轮里最新的采样表按共享缓存映像与导出符号命名；`--threads PID` 把 `dump` 的回溯按相同方式命名并合并相同的栈。
- `tools/k90auto/cycle.py --tour`：每轮可指定巡检步骤，`--hold` 之后用 `rsh.py`、`tour.py` 继续在同一次启动里取数。
- 驱动的每行输出带 `[进程名 pid]` 前缀（`redwoodmetal_console.inc`）。

`userland/src/xpcwatch.c` 用 `__interpose` 统计服务名，实测只抓到 1 次调用：共享缓存内部的调用不经过插入表。定位最后靠的是回溯与 IDA。

## 5. 开机图标不出现与处理器占用无关

- `rest1` 里 SpringBoard 已经空闲，开机后 3 分钟内图标仍不出现，翻页也不出现。图层读数（`notify com.redwood.layers.Icon`）显示 17 个 `SBIconImageView` 都没有子图层；从设置返回主屏后，每个 `SBIconImageView` 下都有 `SBHIconLayerView` → `ICRIconLayer` → `ICRIconRenderingLayer`，图标全部出现。
- `rest1` 在开机约 7 分钟时 `kill -9` SpringBoard，`rest2` 在解锁后约 10 秒 `restart SpringBoard`，两次重启后的 SpringBoard 都在解锁后直接显示全部图标和两个小组件。
- Wi-Fi 地址的假设已排除（`mac1`）。根因是每次开机 `/private/var` 都是空的，见[每次开机都是首次开机](2026-10-31-every-boot-is-first-boot.md)。

## 6. 待办

- 壁纸：PosterBoard 仍报 `PBFPosterExtensionDataStoreErrorDomain -2222`、`FBProcessManager 2`。另一个 23G90 移植（Bergamota `tools/sweetnet/sweetpb26.m`）对 PosterBoard 做了四处改动，与本项目已做的文件保护与 purgeable 两处有重叠，其余两处待对照。
- 电池图标：`STUIStatusBarBatteryView` 由两个 `CAShapeLayer`、一个填充层和一个 `compositingFilter` 为 `destOut` 的百分比文字层组成，软件合成下显示，GPU 合成下不显示。
