# iOS 26 开机次序、处理器占用与滑动性能（2026-10-31）

用户在 2026-10-31 反馈：开机后主屏没有图标，打开一个应用后图标才出现；没有壁纸和右上角电池图标；滑动卡、机身发热；希望查架构层面的原因，并改进观测与迭代耗时。本文记录这一天的轮次与读数。处理器占用的分析见 [launchd 任务集分析](../analysis/2026-10-31-launchd-jobs-and-boot-cpu.md)，开机次序与性能的分析见 [每次开机都是首次开机](../analysis/2026-10-31-every-boot-is-first-boot.md)。

## 1. 轮次与身份

`kernel-12377-cmd16-heap1` 至 `kernel-12377-cmd23-state1` 的改动与读数写在内核子模块提交 `3899a53` 与 `.userland.git` 提交 `6d6f0abab` 的说明里，本表从 `xpc1` 开始。表中的轮次都用 `cycle.py`，四核，`gpu_coherent=1`。

| 轮次目录 | 内核 | 与上一轮的差别 | 结果 |
|---|---|---|---|
| `kernel-12377-cmd24-xpc1` | `12377-cmd24` | 基线：launchd 任务集 37 条 | SpringBoard、launchd、appprotectiond 持续占用处理器，回溯在服务查找失败后的重连上 |
| `kernel-12377-cmd24-rest1` | 同上 | `REST=1`：登记其余带 Mach 服务的任务，按需启动 | 进程数 254；PerfPowerServices、appprotectiond、ScreenTimeAgent 占用处理器 |
| `kernel-12377-cmd24-rest2` | 同上 | 放行 `com.apple.dmd`，不登记 `com.apple.PerfPowerServices` | 没有进程持续占用处理器，20 秒中断采样数从 315249 降到 34872 |
| `kernel-12377-cmd24-align1` | 同上 | 驱动把只读纹理的对齐要求报为 64 字节 | 仍有 SpringBoard 的 IOSurface 经拷贝采样；从主屏点设置没有打开，点备忘录能打开，原因未查 |
| `kernel-12377-cmd24-hash1` | 同上 | AIR 对 buffer 纹理按内容哈希，内容未变时跳过上传 | backboardd 每 1024 次刷新里 202 次上传、105517 次跳过；手势帧率 28～49 帧／秒，最长间隔 60～208 毫秒 |
| `kernel-12377-cmd25-mac1` | `12377-cmd25` | 内核在 `/chosen` 发布 Wi-Fi 地址 | 开机图标仍不出现，这条假设排除 |
| `kernel-12377-cmd26-wait1` | `12377-cmd26` | 等 GPU 时健康检查最多每毫秒一次；`CPU_PREP` 只等该 buffer 最后一次使用 | 手势帧率 30～55 帧／秒，最长间隔 44～93 毫秒；控制中心打开由 197 毫秒 2 帧变为 25 毫秒 |
| `kernel-12377-cmd26-delay1` | 同上 | SpringBoard 在 `main` 前等 40 秒（`SB26_START_DELAY=40`） | 开机后的第一个 SpringBoard 显示全部图标 |
| `kernel-12377-cmd26-log1` | 同上 | SpringBoard 打开 os_log（`OS_ACTIVITY_DT_MODE=YES`） | 取到首个 SpringBoard 的开机日志，见 §4；保持期间重启 SpringBoard，图标出现 |
| `kernel-12377-cmd27-bo1` | `12377-cmd27` | GPU buffer 地址改为 next-fit 分配；采样器记录内核样本的 LR | 手势帧率与 `wait1` 相当；开机约 10 分钟后滑动时 backboardd 因 SIGSEGV 退出，SpringBoard 随之重启 |
| `kernel-12377-cmd27-style1` | 同上 | SpringBoard 注入 `inject_sb26_iconstyle.c`；`systrace=1` | 图标样式状态拿到了，图标仍不出现；`systrace=1` 每个系统调用一行，日志环被冲掉，`boot unlock done` 一行丢失，巡检被跳过 |
| `kernel-12377-cmd28-style2` | `12377-cmd28` | 开机约 60 秒后发 `com.apple.LaunchServices.applicationIconChanged`；`usertrap=1` | 图标仍不出现；第二页文件夹图标里的小图标能画出来 |
| `kernel-12377-cmd29-seed1` | `12377-cmd29` | 不带 GPU（`GPU_STAGE=0`）；换上文件模式的 `var_store` | 新的 `var_store` 没有签名，launchd 以「non-platform binary」触发 userspace panic；签名后重跑 |
| `kernel-12377-cmd29-seed2` | 同上 | 同上，`var_store` 加 ad hoc 签名 | 不带 GPU 的首个 SpringBoard 同样没有图标；重启 SpringBoard 后图标、小组件、Dock 和电池图标都在。种子 329 MB，iOS 运行后申请不到这么大的连续内存，`outbox` 失败 |
| `kernel-12377-cmd30-seed3` | `12377-cmd30` | `outbox_mb=400` 开机预留 | 取回完整种子 329 MB、27865 项，`get_staged` 用 7.4 秒 |
| `kernel-12377-cmd30-warm1` | 同上 | 带 GPU，种子含图标缓存 | 根镜像 29 MB 超过内核之后的余量，loader 报「kernel and ramdisk overlap the resident image」，没有启动 |
| `kernel-12377-cmd30-warm2` | 同上 | 种子去掉图标缓存 | `varseed.py` 写出的种子没有补齐到整块，`var_store load` 读到文件尾报错，种子没有装上 |
| `kernel-12377-cmd30-warm3` | 同上 | 补齐整块、限定读取范围 | 种子装上；系统容器目录的访问控制表没有恢复，SpringBoard 建不了缓存目录，abort 后反复重启 |
| `kernel-12377-cmd30-warm4` | 同上 | 访问控制表经 `chmod_extended` 恢复 | 首个 SpringBoard 显示全部图标与 Dock；lsd 处理器时间 24.5 秒降到 0.6 秒，containermanagerd 8.9 秒降到 0.15 秒；两个共享容器的恢复遇到 ENOMEM |
| `kernel-12377-cmd31-warm5` | `12377-cmd31` | 收件箱 16 MB；ramfs 放锁后分配扩展属性的内存；种子含图标缓存 | 恢复没有报错，首个 SpringBoard 显示全部图标；iconservicesagent 仍画了 22540 次；8 次翻页里 3 次 52～55 帧／秒，4 次 15～34 帧／秒、最长间隔 125～217 毫秒 |
| `kernel-12377-cmd31-warm6` | 同上 | 种子加回 PluginKitPlugin 容器（`seed-plugins.bin`） | 天气与日历小组件显示内容；壁纸仍黑，没有电池图标 |
| `kernel-12377-cmd32-bo2` | `12377-cmd32` | GPU buffer 地址在 512 MB 内循环，单个 buffer 拿不到地址时只拒绝这一个；80 次翻页 | 80 次翻页 GPU 没有停用。打包时漏了 `REST=1`，launchd 任务集只有 37 条，见 §2 |
| `kernel-12377-cmd32-bo3` | 同上 | `REST=1` 改为默认；`var_store` 对存档里没有访问控制表的项去掉继承来的表；`seed-icons.bin` | 图标缓存保留，iconservicesagent 开机后绘制 2557 次；全轮处理器时间 309 秒；翻页帧率在约 54 与约 23 帧／秒两档之间切换，见 §3；第 70 次翻页前后进入了图标编辑模式 |
| `kernel-12377-cmd33-bo4` | `12377-cmd33` | 处理器温度限制改为逐档升降；巡检末尾去掉电池百分比文字层的 `destOut` | 集群 1 最高 70～71 °C，不再长时间停在最低档；第 40 次翻页前已进入图标编辑模式，图标持续抖动，backboardd 绘制 282 万次，帧率不能与 `bo3` 比较。去掉 `destOut` 后百分比文字显示，电池外框与填充仍不显示 |

内核身份：`12377-cmd25`～`12377-cmd33` 的二进制、哈希与改动写在各自的 `docs/progress/evidence/k90auto/kernel-12377-cmdN/kernel.json`。

## 2. 处理器占用

结论与读数见 [launchd 任务集分析](../analysis/2026-10-31-launchd-jobs-and-boot-cpu.md) §1～§3。`REST=1` 是 `package.py` 的开关，`bo3` 起默认打开，`REST=0` 关闭。

`bo2` 打包时环境里没有 `REST=1`，复现了 37 条任务的状态：

- 全轮 `ps` 的处理器时间 1386 秒，`bo3` 为 309 秒。占用最多的是 SpringBoard 423 秒、launchd 340 秒、appprotectiond 176 秒、MapKit 的快照服务 126 秒、logd 84 秒。
- 空闲时 20 秒中断采样里空闲只占 43%。appprotectiond 的回溯在 DeviceManagement 与 Catalyst 的连接代码里，MapKit 快照服务在 GeoServices 新建连接，launchd 的样本多在内核态。
- 集群 0 有约 70% 的时间在 3072 MHz，最高 77 °C。翻页帧率中位数 20 帧／秒，第 21～80 次多在 9～11 帧／秒。

## 3. GPU 路径的等待与上传

`roundstat.py` 对比的每次绘制驱动耗时（微秒，SpringBoard／backboardd／iconservicesagent）：

| 轮次 | SpringBoard | backboardd | iconservicesagent |
|---|---|---|---|
| `rest2` | 1233.9 | 131.2 | 381.9 |
| `hash1` | 415.6 | 127.9 | 373.7 |
| `wait1` | 383.9 | 96.1 | 370.3 |
| `bo1` | 385.1 | 98.8 | 344.6 |

- `hash1` 之前，backboardd 每次刷新都重新上传 buffer 纹理；跳过未变内容后上传次数降到约 1/500。
- `wait1` 之前，`adreno8_context_done` 每次查询都读三套 SMMU 故障寄存器、GMU 中断与 HFI 队列，`hash1` 的采样里这部分占 SpringBoard 滑动时处理器时间的大半；改为每毫秒最多一次后，控制中心打开从 197 毫秒降到 25 毫秒。
- `bo1` 的 next-fit 分配没有带来可见变化，buffer 分配本身不是瓶颈。
- 内核每 5 秒的 GPU 统计（`bo1`）：GPU 频率 342 MHz；每 5 秒 460～490 次提交，平均每次 GPU 执行约 1 毫秒，其中 15～22 次超过 4 毫秒；约三分之一的提交要等队列空位。

`bo3` 的 80 次翻页按十次一组取中位数：53.5、22.9、22.8、22.8、44.7、54.6、53.5、26.4 帧／秒。帧率与 GPU 频率无关，160 MHz 时也有 56 帧／秒的翻页。慢的时段对应集群 1 的温度限制：30 秒窗口里有 2 个滴答读到 70 °C，按当时的规则集群降到最低档 1017 MHz，直到所有传感器低于 60 °C，窗口里 63%～75% 的时间停在最低档。`12377-cmd33` 把这条规则改为逐档升降：读数达到 70 °C 时每 50 毫秒降一档，低于 65 °C 时每 200 毫秒升一档，两者之间保持，75 °C 或没有读数时直接到最低档。`bo4` 里集群 1 的最高读数在 68～71 °C，没有再出现长时间停在最低档的窗口。

`bo3`、`bo4` 都在翻页途中进入了图标编辑模式。主屏图标按住约 700 毫秒才进入编辑模式，翻页的手指在 300 毫秒内移开，所以进入编辑模式说明触摸期间有超过 700 毫秒的停顿；`bo3` 第 45 次翻页的窗口里只有 1.8 帧／秒。编辑模式下图标持续抖动，backboardd 一直在画，之后的帧率读数不能用。下一轮的翻页从屏幕边缘起手，每 10 次按一次主屏键。

## 4. 开机图标

- `log1` 的首个 SpringBoard 从 02:48:48 起 26 秒没有日志，02:49:14.408 恢复；PosterBoard 的 `performPosterBundleIdentifierMigrationIfNeeded` 在同一时刻返回，它从 02:48:44 起阻塞了 30 秒。
- `bo1` 开机早期的线程回溯（每 10 秒一次）：PosterBoard 一个线程停在 LaunchServices 的同步 XPC 上；SpringBoard 主线程停在 CoreServices 的锁上，另一个线程停在 LaunchServices 的同步 XPC 上。`style1` 的 lsd 回溯在 InstalledContentLibrary 逐个读应用的 Info.plist，其余线程等待数据库就绪。
- 首个 SpringBoard 的图标样式协调器在 02:49:16～02:49:17 之间 12 次拿到空的海报样式状态（`[_postersStyleStateDidChange] still nil; bailing`）。`style1` 补上「海报样式到达后通知协调器」之后状态拿到了，图标仍不出现，所以样式状态不是唯一缺的东西。
- iconservicesagent 在 02:48:43～02:49:14 之间把 `Scheduling: CacheOperation - GarbageCollect` 打了 1148 次，02:49:18～02:50:43 之间逐个写入 267 个图标缓存条目；SpringBoard 在 02:51:14 重启后图标全部出现。
- `style2` 在图标缓存写完后发 `com.apple.LaunchServices.applicationIconChanged`，图标仍不出现。`seed2` 不带 GPU，首个 SpringBoard 同样没有图标。
- 根因是每次开机 `/private/var` 都是空的，LaunchServices 数据库要重建，SpringBoard 主线程在启动阶段等它的锁。带开机种子的 `warm4` 首个 SpringBoard 显示全部图标。分析与改法见[每次开机都是首次开机](../analysis/2026-10-31-every-boot-is-first-boot.md)。

## 5. 观测与迭代工具

- `rwsh` 新增 `cat PATH [OFFSET]`、`ls PATH`、`rm PATH`；`tools/k90auto/fetch.py` 用 `cat` 把设备上的文件按偏移分段取回，缺行时停止。
- `tools/k90auto/roundstat.py`：按轮次并排打印手势帧率、每次绘制的驱动耗时、慢的 buffer 准备、经拷贝采样的 surface 与 buffer 纹理上传次数。
- `tools/k90auto/prof.py --threads PID`：把 `dump PID` 的用户态回溯按共享缓存映像命名并合并相同的栈；`12377-cmd28` 起回溯超过 12 帧时续在 `bt+` 行上，最多 32 帧。驱动在加载 AIR 时打印两个库的加载地址（`images: driver ... air ...`），`prof.py` 据此给驱动与 AIR 里的地址命名。
- `12377-cmd28` 新增 `usertrap=1`：只打印用户态异常（`usertrap: ...`），不带 `systrace` 的系统调用行。
- 每轮约 10 分钟，其中系统盘上传约 123 秒（4.9 GB，256 MB 一块，每块 6.7 秒，约 39 MB/s）。在同一次启动里改设置、重启进程用 `cycle.py --hold` 加 `respin.py`。
- `kern.redwood.outbox` 加 rwsh 的 `outbox PATH`：把设备上的文件交给 loader，内核回到 loader 后 `run-auto.py` 取回 `run/outbox.bin`，约 44 MB/s。只在不带 GPU 的轮次可用，带 GPU 的内核收尾时不回到 loader。大文件要在开机时用 `outbox_mb=N` 预留连续内存。
- `tools/k90auto/varseed.py`：列出、裁剪 `var_store` 种子；`package.py` 的 `SEED=` 把种子放进根镜像；`make-payload.py` 的 `GPU_STAGE=0` 不带 GPU 启动，并在上传前检查根镜像是否放得下。

## 6. 未解决

- 壁纸：MercuryPosterExtension 渲染出 1125x2436 的 surface，屏幕上仍是黑色；PosterBoard 仍报 `-2222`、`FBProcessManager 2`、`Gallery configuration is nil`。不带 GPU 的 `seed2`、`seed3` 也是黑色。
  - `bo2` 的图层树：`_SBWallpaperSecureWindow` 里有 `PBUIPosterSceneLayerHostView`，其下的 `_UISceneLayerHostContainerView` 只有 `_UITouchPassthroughView`，没有承载海报场景的图层。
  - 两个 MercuryPosterExtension 进程的主线程停在 `UIApplicationMain` 的 run loop 里，处理器时间 0.2 秒左右。
  - PosterBoard 在 `bo3` 里 28 次报 PosterKit 的 `not available`，28 次报 `XPC service invalidated`，另有一次 `FBProcessManager` 的 `already-exists`（MercuryPoster 的进程已存在，忽略执行上下文）和两次 `Scene was invalidated`。
- 翻页卡顿：`warm5` 翻页时 GPU 统计窗口从 5 秒拉长到 7～8 秒，提交中约一半要等队列空位；GPU 最高 342 MHz。
- 电池图标：GPU 合成下不显示。`bo2` 上 backboardd 改用 sysmem（`FD_MESA_DEBUG=sysmem`）、或加上 AdrenoMetal 用的四个 `CA_*` 环境变量后，电池图标仍不显示。SpringBoard 被 AIR 拒绝的那条管线是 SwiftUI 的 `custom_effect:distanceGradient_v1`，与电池图标的关系未确认。`bo4` 用 `notify com.redwood.battery.nofx` 去掉百分比文字层的 `destOut` 后，文字「73」显示出来，两个 `CAShapeLayer` 外框和填充层仍不显示，下一步查 backboardd 画路径形状的那条路。
- backboardd 在 `bo1` 滑动时 SIGSEGV，没有崩溃记录；`usertrap=1` 之后的轮次会打印回溯。
