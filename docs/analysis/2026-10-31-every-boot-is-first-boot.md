# 每次开机都是首次开机（2026-10-31）

用户在 2026-10-31 反馈：开机后主屏没有图标，打开一个应用后图标才出现；滑动卡、机身发热；改了几十轮都是小修小补，希望查架构层面的原因。本文记录开机图标问题的根因、改法与验证，以及同一根因对开机期处理器占用的影响。逐轮读数见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md)。

## 1. 结论

- `/private/var` 是 init 在每次开机时新挂的内存文件系统（`userland/src/init.c` 的 `mount_writable`），里面只有 `etc/var.skel` 列出的空目录。真机上 `/private/var` 跨重启保留，这里每次开机都相当于刷机后的第一次开机。`var_store`（把 `/private/var` 存进 darwin 分区）在 K90 上从未启用（[已装应用记录盘点](2026-10-28-ios26-installed-apps-records-inventory.md)）。
- 首次开机时 LaunchServices 要从头建数据库，iconservicesagent 要从头画图标缓存，PosterBoard 要做数据迁移。SpringBoard 主线程在启动阶段等 LaunchServices 的锁，主屏在这些数据就绪前就建好了，之后没有再取图标。
- 图标缺失与 GPU 无关：不带 GPU 的 `seed2` 首个 SpringBoard 同样没有图标；重启 SpringBoard 后全部出现。
- 改法是给 `/private/var` 一份开机种子：在一次已经稳定的开机里用 `var_store save FILE` 打包 `/private/var`，经新增的 `kern.redwood.outbox` 取回宿主机，打进根镜像的 `etc/var.seed`，下次开机由 init 解包到骨架之上。全程不写闪存。验证结果见 §4。

## 2. 证据

- 图标与样式状态无关：`style1` 补上「海报样式到达后通知图标样式协调器」后，协调器拿到了样式状态，图标仍不出现。`style2` 在开机约 60 秒后发 `com.apple.LaunchServices.applicationIconChanged`，图标仍不出现；第二页文件夹图标里的小图标能画出来。
- SpringBoard 主线程（`style2`，`dump 32`）：日志开始后第 3 秒与第 19 秒的两次转储里，主线程都停在 `_SBSystemAppMain` → `FBSystemShellInitialize` → `CCSControlCenterServicesManager start` → CoreServices 的锁（`__ulock_wait2`）；同一进程的另一个线程持有这把锁，正在 `_LSSetSchemeHandler` 里向 lsd 发同步 XPC。第 53 秒的转储里主线程已回到 run loop。`log1` 从日志看到的停顿是 26 秒（02:48:48～02:49:14）。
- lsd（`style2`，`dump 60`）：一个线程在 InstalledContentLibrary 里逐个读应用的 `Info.plist`（`_MILoadInfoPlist`），并向 containermanagerd 发同步查询；其余线程在 dispatch group 里等数据库就绪。
- 开机约 4 分钟时的处理器时间（`seed2`，不带 GPU）：lsd 用户态 20.69 秒，iconservicesagent 用户态 56.06 秒。带 GPU 的轮次里 iconservicesagent 的绘制走 GPU，`style2` 记了 225 条「commit N took N ms」。
- `log1`：PosterBoard 的 `performPosterBundleIdentifierMigrationIfNeeded` 从 02:48:44 起阻塞 30 秒；iconservicesagent 在 02:49:18～02:50:43 之间逐个写入 267 个图标缓存条目。
- 已排除：Wi-Fi 地址（`mac1`）、图标样式状态（`style1`）、`applicationIconChanged` 通知（`style2`）、GPU 合成（`seed2`）。

## 3. 改法

- `var_store` 增加文件模式（`userland/src/var_store.c`）：`save FILE`、`load FILE`、`show FILE` 用文件代替 darwin 分区，单槽，头在文件开头。`load` 不带文件时，如果自己所在镜像里有 `etc/var.seed`，就从它解包，不读闪存。init 只在启动参数带 `var_store=1` 时调用 `var_store load`（`restore_var`）。
- `kern.redwood.outbox`（`bsd/dev/redwood_threads.c`）：rwsh 的 `outbox PATH` 把文件分段写进一块物理连续的内存，写满后登记到 `loader_recording`。内核回到 loader 后，loader 把它当作录屏暂存，`run-auto.py` 在收尾时用 `oem recording` 加 `get_staged` 取回 `run/outbox.bin`。iOS 运行后找不到 328 MB 的连续内存（`seed2`），所以由启动参数 `outbox_mb=N` 在开机时预留。
- 带 GPU 的内核在收尾时停在 `adreno8_quiesce` 等冷复位，不会回到 loader，所以取种子的轮次不带 GPU（`make-payload.py` 的 `GPU_STAGE=0`）。
- `tools/k90auto/varseed.py`：列出种子里各目录的大小，按路径前缀删掉不需要的部分，重写头部校验。`package.py` 的 `SEED=` 校验种子后放进根镜像的 `etc/var.seed`。
- 取种子的轮次在保存前重启一次 SpringBoard，种子里的 SpringBoard 状态来自图标完整的那次启动。
- 根镜像的容量：loader 把根镜像放在内核之后，两者都要在常驻系统盘的 128 MB 处之前结束（`RESIDENT_RD_OFFSET`）。`12377-cmd30` 的静态部分到 104 MB，根镜像最多约 24 MB，超出时 loader 报「kernel and ramdisk overlap the resident image」（`warm1`）。`make-payload.py` 在上传前检查这一项。
- 种子的裁剪：`seed3` 取回的完整种子 329 MB、27865 项，压缩后约 92 MB。图标缓存（`systemgroup.com.apple.lsd.iconscache`）57 MB，PosterBoard 的数据（`PRBPosterExtensionDataStore`）52 MB，其余是定位、符号化、Biome、智能平台等缓存。`seed-trim.bin` 去掉这些缓存、PosterBoard 的数据与 PluginKitPlugin 容器（小组件扩展的数据），约 117 MB；`seed-noicons.bin` 再去掉图标缓存，留下 LaunchServices 数据库、其余容器、偏好设置与 SpringBoard 的布局，约 59 MB，压缩后约 7 MB。删除清单与种子放在本地证据目录。
- 访问控制表：containermanagerd 把系统容器的目录建成权限 0、属主 uid -2，靠 `com.apple.system.Security` 里的访问控制表放行进程。`setxattr` 拒绝写 `com.apple.system.` 开头的属性，只按属主和权限恢复时 SpringBoard 建不了缓存目录，在启动时 abort 并反复重启（`warm3`）。`var_store` 改为把这个属性转回 `kauth_filesec`，交给 `chmod_extended` 写回（`userland/src/var_store_acl.inc`）。

## 4. 验证

- `warm4`（`12377-cmd30`，带 GPU，`seed-noicons.bin`）：开机后第一张截图里首个 SpringBoard 显示全部图标、两个小组件的位置与 Dock，没有重启 SpringBoard，也没有打开应用。
- 早期线程转储里 SpringBoard 主线程在 run loop 里，没有停在 CoreServices 的锁上。
- 巡检结束时的 `ps`（`style2` → `warm4`）：lsd 用户态加系统态 24.5 秒降到 0.6 秒，containermanagerd 8.9 秒降到 0.15 秒。iconservicesagent 没有变化（约 32 秒），种子里没有图标缓存。
- `warm5`（`12377-cmd31`，`seed-trim.bin`，含图标缓存）：恢复 2713 个目录、1513 个文件，没有报错。首个 SpringBoard 同样显示全部图标。iconservicesagent 仍在开机后约 45 秒内画了 22540 次，处理器时间约 34 秒，种子里的图标缓存没有被直接用上，原因未查。
- `warm4` 有两个共享容器恢复时遇到 ENOMEM：ramfs 读扩展属性时在锁内用 `Z_NOWAIT` 分配内存，突发读取时会失败。`12377-cmd31` 改为放锁后可等待地分配（`bsd/miscfs/ramfs/ramfs_xattr.inc`），`warm5` 没有再出现。

仍未解决的问题：

- 壁纸仍是黑色，不带 GPU 的 `seed2`、`seed3` 也是黑色。
- 带 GPU 时右上角没有电池图标。
- 带种子开机后两个小组件显示为白色方块。种子去掉了 PluginKitPlugin 容器；chronod 的 `icons` 目录里只有零字节的临时文件，取种子的那次开机就是这样。

## 5. 使用与限制

- `cycle.py --seed FILE`（或环境变量 `K90_SEED`）带种子开机，自动加 `var_store=1`。种子和删除清单放在本地证据目录，不入库。
- 取新种子：`GPU_STAGE=0`、`outbox_mb=400` 起一轮，开机稳定后重启 SpringBoard 并解锁，再 `var_store save /private/var/tmp/var.seed` 与 `outbox /private/var/tmp/var.seed`，停轮后在 `run/outbox.bin` 取到，用 `varseed.py drop` 按删除清单裁剪。
- 种子绑定这一版系统盘里的应用集合与容器编号。系统盘的应用变化后要重新取种子。
- 根镜像余量：`12377-cmd31` 把 loader 收件箱从 32 MB 减到 16 MB（仍放得下约 15 MB 的 AIR 库），根镜像余量从 24 MB 增到 40 MB。PosterBoard 的数据压缩后约 34 MB，加上其余部分仍放不下；要带上它，种子需要改放进系统盘镜像，或者调整 loader 的 `RESIDENT_RD_OFFSET`，后者要刷写 loader。
