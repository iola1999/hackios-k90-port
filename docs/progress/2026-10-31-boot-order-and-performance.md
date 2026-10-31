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
| `kernel-12377-cmd33-bo5` | 同上 | 翻页从屏幕边缘起手，每 5 对按一次主屏键；巡检加六个测试图层 | 快档 49.3、慢档 28.0 帧／秒（中位数，下同）；慢档对应今天视图，每帧约 410 次绘制 |
| `kernel-12377-cmd33-bo6` | 同上 | AIR 光栅化状态线宽 1 | 电池外框与填充显示；快档 49.2、慢档 26.3 帧／秒 |
| `kernel-12377-cmd34-bo7` | `12377-cmd34` | 内核 `kRedwoodMemory`：调用方内存直接做 GPU buffer | backboardd 在 `buffer_texture_upload` 崩溃 16 次：同进程映射返回原地址，释放时把调用方的内存解除了映射 |
| `kernel-12377-cmd35-bo8` | `12377-cmd35` | 第二次映射加 `kIOMapUnique` | 解除映射时内核在 `IOGeneralMemoryDescriptor::doMap` data abort |
| `kernel-12377-cmd36-bo9` | `12377-cmd36` | 改用 `kIOMapGuardedSmall`；只读区域按只读方向 wire | 没有崩溃，打印出的 no-copy buffer 全部直接使用调用方内存；快档 52.9、慢档 30.0 帧／秒 |
| `kernel-12377-cmd36-bo10` | 同上 | freedreno 提交合并（`fd-submit-merge.patch`），`rwa_flush` 不等待 | 今天视图每个显示间隔的提交从约 33 次降到 3 次；快档 52.8、慢档 35.1 帧／秒 |
| `kernel-12377-cmd36-bo11` | 同上 | 驱动探针只读时钟（`fd-probe-wall-only.patch`） | 每次绘制的 `draw_vbo` 从 38.3 降到 9.1 微秒；backboardd 全轮处理器时间 158.6 秒降到 97.2 秒；快档 54.3、慢档 36.8 帧／秒 |
| `kernel-12377-cmd37-bo12` | `12377-cmd37` | AIR 导入调用方内存 buffer 时带上大小（`fd-import-size.patch`）；采样器给内核样本多记两层返回地址 | 三个进程打印出的 48 次纹理导入全部成功（`bo11` 打印出的 47 次里失败 40 次）；快档 54.3、慢档 38.8 帧／秒 |
| `kernel-12377-cmd37-bo13` | 同上 | freedreno 不再为 buffer 缓存调用 `madvise`（`fd-madvise-skip.patch`）；`redwood_drm.c` 按 ioctl 计数；rwsh 加 `maps` | 快档 54.3、慢档 36.9 帧／秒；今天视图翻页时 GPU（342 MHz）忙碌 94% |
| `kernel-12377-cmd38-bo14` | `12377-cmd38` | 面板只重画源图像里变了的行（`fb_rows`，默认打开） | 屏幕静止时每帧面板拷贝中位数从 8.2 降到 1.6 毫秒，翻页时从 8.6 降到 5.4 毫秒；快档 54.3、慢档 41.1 帧／秒 |
| `kernel-12377-cmd39-bo15` | `12377-cmd39` | GPU 按设备树增加 389～607 MHz 四档，`GPU_SPEED=7` | 今天视图翻页时 GPU 忙碌 56%，GPU 最高 49.8 °C，没有 GPU 故障；快档 56.1、慢档 38.2 帧／秒 |
| `kernel-12377-cmd40-bo16` | `12377-cmd40` | 等 GPU 的线程睡到 GMU 消息中断（INTID 336）；看门狗在手势中无帧时转储线程 | 静止时每 5 秒约 50 次中断；快档 56.2（60 个窗口）、慢档 36.9 帧／秒；84 步里 7 次滑动没有出帧；看门狗 8 次转储都在静止后的第一次触摸，属误报 |
| `kernel-12377-cmd41-bo17` | `12377-cmd41` | freedreno 与 AIR 的计时点默认不读时钟（`fd-perf-off.patch`，`FD_PERF_DRAW=1` 打开） | backboardd 全轮处理器时间 54.7 秒（`bo16` 124.7 秒），全部进程 195.7 秒（`bo16` 259.9 秒）；进今天视图的一步失败，今天视图的段落在主屏 |
| `kernel-12377-cmd42-bo18` | `12377-cmd42` | 巡检改为每组先按主屏键再左右各滑一次，今天视图里上下滚动；看门狗在手势开始 400 毫秒后仍无帧时转储；`REST_ALLOW=duetexpertd` | 今天视图滚动时 backboardd 因 AIR 缺 `air.fmax3` 退出 4 次；duetexpertd 与 SpringBoard 共用一个服务名，没有登记，壁纸这一变量没有生效；3 次转储里 SpringBoard 主线程都在 run loop 等待 |
| `kernel-12377-cmd43-bo19` | `12377-cmd43` | AIR 增加三元最值；`REST_ALLOW` 的任务让出别的任务已登记的服务名 | backboardd 没有退出；duetexpertd 启动后报「Failed to initialize datavault for DuetExpertCenterAsset」退出 16 次；今天视图下滑打开搜索后 Spotlight 崩溃 399 次，ReportCrash 用了 66.9 秒处理器时间；壁纸仍黑 |
| `kernel-12377-cmd43-bo20` | 同上 | 翻页起手位置从 x 0.97／0.03 改为 0.85／0.15，不带 duetexpertd | 40 次翻页里 1 次没有出帧（`bo18` 4 次、`bo19` 3 次）；td2 之后 Spotlight 崩溃 664 次，ReportCrash 72.5 秒，处理器集群升到 66～69 °C，见 [Spotlight 崩溃循环](../analysis/2026-10-31-spotlight-crash-loop.md) |
| `kernel-12377-cmd44-bo21` | `12377-cmd44` | 系统镜像加入 SpotlightResources 的 root 与 English 资源包（含模型）；看门狗只按手指采样计手势，卡顿转储要求手指仍在屏上 | Spotlight 没有崩溃，ReportCrash 7.1 秒，今天视图段处理器集群 41～51 °C，滚动每步 29～36 帧的有 11 步；40 次翻页里 5 次没有出帧，8 次转储都对应没有反应的手势 |
| `kernel-12377-cmd44-bo22` | 同上 | 驱动改用 AIR 的 `rwa_dispatch_nowait`，计算着色器派发不等 GPU | 巡检没有走到用计算着色器的界面，派发次数为 0；今天视图进了编辑模式（一次丢了抬起的触摸被当成长按）；40 次翻页里 5 次没有出帧 |
| `kernel-12377-cmd44-bo23` | 同上 | `libredwood.dylib` 在有 `input26-service` 任务时不起输入线程；巡检末尾加一次下拉搜索 | backboardd 只有一块触摸屏；40 次翻页每次 30～33 帧，今天视图 16 次滚动每次 27～32 帧，看门狗没有转储；搜索页派发每次 22～79 微秒；全轮处理器集群最高 43.8 °C |
| `kernel-12377-cmd44-bo24`～`bo32` | 同上 | 壁纸：MercuryPosterExtension 拿到 Metal 设备（`POSTER_METAL=1`），逐轮补输出通道、AIR 翻译器、顶点纹理、压缩格式、blit 与派发 | `bo31` 起扩展的提交不再出错，屏幕仍黑；backboardd 拒收 SpringBoard 壁纸窗口的 commit。逐轮读数见[锁屏壁纸](../analysis/2026-10-31-mercury-wallpaper.md) §4 |
| `kernel-12377-cmd45-bo33`、`kernel-12377-cmd46-bo34` | `12377-cmd45`、`12377-cmd46` | 内核打印失败的拷贝型 memory entry | 被拒的是 ATX 格式的海报快照，memory entry 大小为 0 |
| `kernel-12377-cmd46-bo35` | `12377-cmd46` | 海报快照存成 PNG | commit 不再被拒；快照与屏幕仍黑 |
| `kernel-12377-cmd46-bo36` | 同上 | 扩展在提交末尾采样 resolve 目标 | 扩展的 4 倍多重采样 drawable 全部为 0 |
| `kernel-12377-cmd47-bo37` | `12377-cmd47` | 扩展用单采样直接画进 drawable；`redwood_tl` 一行 319 字节 | 主屏与锁屏显示壁纸 |
| `kernel-12377-cmd47-bo38` | 同上 | 单采样与 `POSTER_METAL` 改为默认，巡检同 `bo23` | 全程有壁纸；59 次滑动平均 52.7 帧／秒（`bo23` 52.9），最慢的两次 21.0 与 24.4 帧／秒，与 `bo23` 最慢的两次是同两步（40.3 与 28.0）；30 秒窗口内处理器最高 71.3 °C（`bo23` 73.3 °C）；扩展只在开机时提交，之后不再提交 |
| `kernel-12377-cmd47-bo39` | `12377-cmd47` | 图层转储加 `DateView`、`Time`、`SDF` 三个过滤 | 时间由 SwiftUI 的 SDF 图层交给 backboardd 的玻璃管线绘制，见[锁屏壁纸](../analysis/2026-10-31-mercury-wallpaper.md) §8 |
| `kernel-12377-cmd47-bo40` | 同上 | backboardd 逐 draw 采样玻璃与模糊管线 | 模糊金字塔的各级都画进第 0 级，玻璃读到的背景为空 |
| `kernel-12377-cmd47-bo41` | 同上 | 驱动按颜色附件的 `level` 建级别视图；修正立方体纹理的类型编号 | 第二个附件与级别视图尺寸不同，库拒绝，96 个命令缓冲失败，锁屏闪烁，提前结束 |
| `kernel-12377-cmd47-bo42` | 同上 | 库按所有附件共有的区域绘制 | 没有绘制失败，Dock 玻璃显示；时钟仍不显示，时间的 SDF IOSurface 在 backboardd 读出为空 |
| `kernel-12377-cmd48-bo43` | `12377-cmd48` | 电量计电流在 ±50 mA 以内不算充放电；管线被拒时导出链接进来的函数 | 取得 SwiftUI 的 `custom_fn`；用户反馈从主屏打开应用是纯黑屏，原因没有查 |
| `kernel-12377-cmd49-bo44` | `12377-cmd49` | `applog` 选中的程序加 `ACTIVITY_LOG_STDERR`、`CFLOG_FORCE_STDERR`；驱动把单采样 storeAction 2 的附件直接画进 resolve 目标（AIR 库没有重编，翻译器改动不在这一轮） | 读到应用的异常文本：MobileSMS 缺 ChatKit 的 `Assets.car` 后抛出「Trying to create an LPImage with nil data」，`com.apple.Safari.History` 抛出 `NSInvalidArgumentException`（字典 key `WFLinkEntityContentPropertyUserInfoEnumMetadata` 的值为 nil）；锁屏时钟仍不显示 |
| `kernel-12377-cmd49-bo45` | 同上 | 重编 AIR 库：指针存进局部的槽、导数按 32 位逐像素；loader v11 首次用 `oem dsu load` 读系统盘（主机读不到 CRC，退回 USB 上传） | 锁屏时钟显示；SpringBoard 的管线拒绝为 0。同一次开机内设 `AIR_COARSE_DERIVATIVES=1` 或 `REDWOOD_RESOLVE_BLIT=1` 后重启进程，时钟仍显示，时钟由指针槽改动修好 |
| `kernel-12377-cmd50-bo46` | `12377-cmd50` | 系统盘按放宽后的规则重建（5217959936 字节）并装进 DSU；loader v12 读入后按 1 GiB 分段比对 CRC；GPU 用旧调频参数（`adreno8_floor=1 adreno8_touch_ms=300`） | 系统盘 1.43 秒读入、5 段 CRC 用 1.92 秒全部一致；MobileSMS 不再中止，Safari 与短信的场景进入 `running-active-Visible`，屏幕仍全黑；同一次开机内打开设置、备忘录、时钟也全黑；间隔 3 秒的 20 次翻页平均 53.4 帧／秒 |
| `kernel-12377-cmd50-bo47` | 同上 | GPU 用新调频默认值（最低 342 MHz、触摸后 1.5 秒）；巡检末尾打开设置并转储 SpringBoard 的图层 | 翻页 53.6 帧／秒、今天视图滚动 50.2 帧／秒，与 `bo46` 相当，调频切换由 54～62 次降到 30 次；被拒的 commit 来自 `SBMainSwitcherWindow`，其中壁纸快照是 ATX 格式的 CGImage，见 §6 |
| `kernel-12377-cmd50-bo48` | 同上 | 驱动实现纹理布局与 `newTextureWithBytesNoCopy`（`redwoodmetal_texture_layout.inc`） | 没有 serialization error，Safari、短信、设置都画出内容；设置首次打开时有成块的旧内容，解锁后日历小组件空白、回到首页时天气小组件是蓝色方块。同一次开机内给 backboardd 设 `CA_DISABLE_DIRTY_REGIONS=1` 并重启后，这几处都正常；Dock 玻璃只有边缘高光 |
| `kernel-12377-cmd50-bo49` | 同上 | backboardd 设 `CA_DISABLE_DIRTY_REGIONS=1`（`JOB_ENV`） | 翻页 53.6 帧／秒、今天视图 51.2 帧／秒，与 `bo47` 相当；GPU 每次提交 3.38 毫秒（`bo47` 1.96），多数时间在 607 MHz；每帧送面板 910 行（`bo47` 393）；最高 72.1 °C（`bo47` 71.7） |

内核身份：`12377-cmd25`～`12377-cmd50` 的二进制、哈希与改动写在各自的 `docs/progress/evidence/k90auto/kernel-12377-cmdN/kernel.json`。`bo12` 起的改动与读数见 [backboardd 合成路径的处理器开销](../analysis/2026-10-31-compositor-cpu-path.md) §7～§13。

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
- 每轮约 10 分钟，其中系统盘上传约 123 秒（4.9 GB，256 MB 一块，每块 6.7 秒，约 39 MB/s）；DSU 读入可代替上传，见下文。在同一次启动里改设置、重启进程用 `cycle.py --hold` 加 `respin.py`。
- `kern.redwood.outbox` 加 rwsh 的 `outbox PATH`：把设备上的文件交给 loader，内核回到 loader 后 `run-auto.py` 取回 `run/outbox.bin`，约 44 MB/s。只在不带 GPU 的轮次可用，带 GPU 的内核收尾时不回到 loader。大文件要在开机时用 `outbox_mb=N` 预留连续内存。
- `tools/k90auto/varseed.py`：列出、裁剪 `var_store` 种子；`package.py` 的 `SEED=` 把种子放进根镜像；`make-payload.py` 的 `GPU_STAGE=0` 不带 GPU 启动，并在上传前检查根镜像是否放得下。
- 系统盘放进 Android DSU（`tools/k90auto/dsu.py install`，16 GiB 槽，不启用）：loader v11 起的 `oem dsu load` 把系统盘从闪存读进常驻区，4.94 GB 用 1.29 秒（`bo45`）；`oem dsu crc` 加 `getvar dsu-crc`（v12）供 `run-auto.py` 按 1 GiB 分段比对 zlib CRC-32，不一致就退回 USB 上传。系统盘改动后要回到 Android 重装（`dsu.py install --replace`），手机开机后需要先解锁一次。
- loader v11 起在 K90 上武装看门狗：主机 180 秒不发命令就停止喂狗。`oem hang` 实测第 37 秒复位、第 60 秒回到 loader，不需要按键。`cycle.py` 起轮时发现手机在 Android，就经 `recover-loader.py` 回到 loader。
- 完整的 loader 镜像（`out/handoff-loader-v12.img`，2.18 MB）可以从 LK 用 `fastboot boot` 直接引导，18 秒后 loader 枚举，不刷 `boot_a`，也不扣 A 槽的重试次数。

## 6. 未解决

- 壁纸：`bo37` 起主屏与锁屏显示壁纸，缺口与改法见[锁屏壁纸](../analysis/2026-10-31-mercury-wallpaper.md)。锁屏时钟 `bo45` 起显示；4 倍多重采样得到全 0、Dock 玻璃时好时坏见该文档 §9。
- 打开应用黑屏：
  - `bo44` 读到的两处异常都是系统盘缺文件。`ios165/select-system.py` 的资源目录上限从 4 MB 提到 32 MB、XPC 服务的字符串表与图片改按普通规则取，新增 191 个文件；`bo46` 起 MobileSMS 不再中止，应用进程正常运行，屏幕仍黑。
  - 第一次打开应用时 backboardd 拒收 SpringBoard 一个窗口的 commit（「CompressedImage port is MACH_PORT_NULL!」，内核同时打印 SpringBoard 的拷贝型 memory entry 失败）。`bo47` 的图层转储里这个窗口是 `SBMainSwitcherWindow`，所有应用的场景都挂在它下面；它的 `PBUIFakeBlurView` 里有一张 846x1827 的 ATX 格式壁纸快照。
  - ATX/KTX 图像由 ImageIO 按驱动的纹理布局（`newTextureLayoutWithDescriptor`）解码，驱动返回 nil 时数据长度为 0，与 `bo34` 海报快照的失败相同（[锁屏壁纸](../analysis/2026-10-31-mercury-wallpaper.md) §6）。驱动在 `redwoodmetal_texture_layout.inc` 实现了纹理布局与 `newTextureWithBytesNoCopy` 后，`bo48` 起应用正常显示。
- 局部重绘留下旧内容：backboardd 只重画变化区域时，设置里有成块的灰白旧内容，解锁后小组件空白或变色，用户另报解锁后顶部闪烁条带、进入今天视图和滚动结束时撕裂、日历与时钟图标先空白再出现。`CA_DISABLE_DIRTY_REGIONS=1` 下截图里的这几处都正常（`bo48` 同一次开机对照），`package.py` 起默认整帧重画（`DIRTY_REGIONS=1` 恢复）。原因未查：CoreAnimation 在 surface 1、2 之间交替，内核按整行哈希把变化的行送到面板，没有用 swap 里的脏区域。
- Dock 玻璃只有边缘高光，内部直接透出壁纸，没有模糊、着色和边缘折射（`bo48`、`bo49` 截图）；设置底部搜索栏下的文字也没有模糊。与局部重绘无关，`bo49` 用 `REDWOOD_THUMB_MATCH=glass_background_sdf` 取了 16 个 draw 的 32x32 采样，分辨率不够判读。
- 充电提示：电量计在 USB 上读到 +17 mA 时内核报告接上充电器，iOS 显示一次「充电」随即结束（用户反馈，`bo42`）。`12377-cmd48` 起 ±50 mA 以内不算充放电，`bo43` 里没有再报告充电器，用户侧还没有确认。
- 翻页与滚动：今天视图翻页 37～40 帧／秒，每帧约 410 次绘制的处理器时间分配还没有按帧的读数，见 [backboardd 合成路径的处理器开销](../analysis/2026-10-31-compositor-cpu-path.md) §16。没有反应的滑动已查明并修复（§12，`bo23`）。
- ScreenContinuity 从 `bo18` 起每轮 SIGTRAP 退出 12～16 次，见 [Spotlight 崩溃循环](../analysis/2026-10-31-spotlight-crash-loop.md) §6。
- backboardd 在 `bo1` 滑动时 SIGSEGV，没有崩溃记录；`usertrap=1` 之后的轮次会打印回溯。
