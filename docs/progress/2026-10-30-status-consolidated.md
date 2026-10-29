# iOS 26 桌面：2026-10-30 凌晨进展汇总

本文汇总 2026-10-29 22:44 至 2026-10-30 03:07 这一段的工作状态，供提交说明与后续接手使用。技术细节留在各轮记录与分析文档里，本文只写结论、身份与指针。

## 1. 范围与时间点

- 汇总时刻：2026-10-30 03:10 左右，设备在 loader idle，无轮次在跑。
- 覆盖的轮次：`render1` 至 `render10`，其中 `render9` 于 03:02 起跑、03:07 收尾，`render10` 至 `render13` 在汇总之后补记。
- 本文不代表验收结论。当前没有一轮同时满足「画面正确」与「不重启」，见第 4 节。

## 2. 三条会话线的状态

- DSH 的一条会话：10-29 14:45 停止，未收尾。它的未提交改动与后两条会话的改动混在同一工作树里，已无法按会话切分。
- Claude Code 的第一条会话：10-29 22:40 停止。20:06 至 20:55 的离线分析提交出自这条会话。
- Claude Code 的第二条会话：10-29 22:44 起接手，汇总时刻仍在运行。`render1` 至 `render10` 与本文引用的工具、文档由这条会话产出。
- 三条线共用同一工作区与同一台设备，因此下文所有「未提交」清单指的是工作树当前状态，不区分归属。

## 3. 今夜的轮次与读数

| 轮次 | 内核 | 画面结果 |
|---|---|---|
| `render1` | `12377-cmd1` | 开机自动解锁；主屏没有图标、电池图标与壁纸 |
| `render2` | 同上，`ICON_METAL=1` | `iconservicesagent` 第 6 次提交时 GPU 挂起；软件合成下图标出现，回主屏后 backboardd 断言崩溃，转菊花 |
| `render3` | 同上 | 巡检 12 步都执行；回主屏那一步截到锁屏 |
| `render4` | 同上 | 定位到没有完成的绘制；SpringBoard 的 os_log 占满环，解锁行丢失 |
| `render5` | 同上 | GPU 在解锁前停用；取到挂起绘制的两个着色器模块 |
| `render6` | 同上，`FD_MESA_DEBUG=sysmem` | 仍挂起；设置页可用，回主屏转菊花 |
| `render7` | 同上 | GPU 在解锁前停用；只截到两张主屏 |
| `render8` | 同上 | `HFI fatal message 150` 仍在；新增 `fpba2ma11bemha4 reads texture 1 and 1 texture was bound` |
| `render9` | `12377-cmd2` | GPU 挂起：内核报 `last timestamp 12, retired 10`，第 11 次提交（`iconservicesagent` 的 `primitive__vertex` 绘制）没有完成；HFI 150 到得晚，没有打印，也就没有 `submissions closed`，巡检 12 步因此都执行；巡检到第 7 步仍是菊花 |
| `render10` | `12377-cmd3` | GPU 挂起在第 12 次提交（SpringBoard，含 `primitive__vertex` 绘制）；超时后再读 3 秒 HFI，取到 HFI 150 全文；PosterBoard 的数据存储初始化返回 nil |
| `render11` | 同上 | 图元重启修正上机后仍挂起，第 9 次提交（SpringBoard 的 57 缓冲提交）；PosterBoard 的迁移返回 0 |
| `render12` | 同上 | 两个进程同步模式，挂起的是 SpringBoard 的 `primitive__vertex+ffea2ba11dhmha4` 绘制 |
| `render13` | 同上 | 去掉 `discard_fragment` 仍挂起，挂起的是 `iconservicesagent` 的 `primitive__vertex+ffia2ba3ca7dhmha4` 绘制；PosterBoard 从 59 迁移到 61 失败 |

- `render9` 的身份：内核 `49434cdc…`（20,243,288 字节），载荷 `2e96194a…`（25,503,080 字节），cmdline 含 `cpus=4 rootdev=md0 launchd_unsecure_cache=1 adreno8_speed=3`。
- `render9` 与 `render8` 的内核差异只有诊断打印：HFI 致命消息逐字打印、`adreno8_context_retired()`、把 retired EOP 时间戳加进 `RedwoodGPU … no answer` 行。
- `render9` 没有 HFI 致命消息，是因为消息在驱动的两秒等待超时之后才到，内核这时已停止读 HFI 队列；GPU 在这一轮同样挂起。`render10` 的内核（`12377-cmd3`）在超时后再读 3 秒，取到了这条消息，读法见[桌面记录](2026-10-30-ios26-usable-desktop.md) §8.6。

## 4. 现在卡在哪

- 硬挂起每轮都出现。`render2` 至 `render10` 每轮都在开机约 40 秒内挂起一次，一次挂起即结束本轮全部 GPU 工作。挂起的批次都含 `primitive__vertex` 绘制；有时间戳确认的两个挂起绘制，片段着色器都读帧缓冲，见[桌面记录](2026-10-30-ios26-usable-desktop.md) §8.4～8.6、§8.9。
- `THE GPU DID NOT FINISH` 是同一次挂起在驱动侧的读数：挂起之后，等 GPU 的提交都在 2 秒后超时。
- 回主屏必然转菊花。`render6` 与 `render9` 都在巡检第 7 步（从设置上划回主屏）之后画面变黑加菊花，同时 SpringBoard 与 backboardd 各有三次进程实例（`render9`：SpringBoard `[31, 94, 234]`、backboardd `[37, 91, 230]`）。这一步只发生在 GPU 停用之后，软件合成路径上的 backboardd 断言崩溃仍是最可能的门。
- 壁纸没有内容。图层树里 `_SBWallpaperSecureWindow` 没有子层；PosterBoard 报 `could not initialize data store: … unknown reason which evades explanation`，另有 `Start wallpaper migration` 与 `reapSnapshots` 报错。`render10` 的注入探针读到 `-[PBFPosterExtensionDataStore initWithURL:...]` 返回 nil 且没有错误；`render13` 读到从 59 到 61 的迁移每次失败，推断是数据存储目录的文件保护等级在不支持数据保护的卷上不相符，见[桌面记录](2026-10-30-ios26-usable-desktop.md) §8.8。
- 充电不可用。电量计读到约 -841 mA，插着 USB 在放电；loader 读充电器状态 49 次全失败。充电控制归 PMIC／ADSP，属独立硬件移植，已推迟。

## 5. 本次提交包含什么

- 顶层仓：`cycle.py`／`tour.py`／`rsh.py`／`render-health.py` 四个工具与两份 jobs 文件、`package.py` 去掉库基线并加架构与签名断言、`run-auto.py` 与 `build-air.py` 的修补、四份 plan 文档与 README 同步、两个子模块指针、本文与 `2026-10-30-ios26-usable-desktop.md`。
- 内核仓：`xnu/files/` 六个文件（HFI 消息逐字打印、retired EOP 时间戳、IOSurface 58 号查询、线程转储触发、loader 返回路径、GPU 派发），`xnuloader/` 两个文件的屏显与 USB 等待，驱动侧改动。
- 用户态共享仓（`.userland.git`）：AIR 与 Mesa 探针、`air_to_nir` 指针 phi 与动态线程组内存、驱动侧绘制描述、`inject_sb26.c` 的 Metal 注册序列。
- `hackios-xnu-userland` 子模块：`inject.c` 的 51 行（backboardd 主循环观察器）。
- 未包含：`docs/progress/evidence/` 下的原始日志与截图（`.gitignore` 覆盖），以及构树、备份、venv 等本地目录。

## 6. 下一步

- 挂起：下一轮换内核 `12377-cmd4`，挂起报告之后打印 CP 的各级 IB 位置与前后命令字，用 `tools/k90auto/cp-words.py` 判断 CP 停在帧缓冲读取的哪一处特殊处理上（[桌面记录](2026-10-30-ios26-usable-desktop.md) §8.9）。
- 回主屏的必然性单独排一轮：把「回主屏」这一步从巡检里拆出来做单次动作，确认是软件合成路径的 `push_surface` 断言还是 GPU 停用后的事务时序。
- 壁纸：注入库让 PosterBoard 的三个预期资源值方法返回空字典（§8.8），作为下一轮的变量。
- 设备入 loader 与重试次数按 [引导目标切换 SOP](../plan/device-boot-target-sop.md) 与 [跑轮协议](../plan/k90auto-run-protocol.md) 执行；loader 未枚举即停手。