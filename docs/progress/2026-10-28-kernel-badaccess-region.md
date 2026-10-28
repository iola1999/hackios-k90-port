# 内核给 bad access 的 pc 补上镜像名（2026-10-28）

roundb 的 212 条 bad access 共用一个 pc（`0x2b0fb59c0` 204 条、`0x2b0fb5ad4` 8 条），减掉当轮 slide 之后仍在共享缓存上界之上，而日志里没有任何一行带这些镜像的加载地址，所以判不出它属于哪个文件。这一页记录为此加的打印、它们的字段含义、实现上的取舍，以及重建出来的内核身份。**新内核 `cf1502f5632284af…`、20,210,232 字节，源码提交 `5c9f563`（`out/xnu12377` 分支 `redwood26`），取代 `81f544688809a2e8…`。**

## 1. 两处打印的格式串原文

```
redwood: %s bad access at %#llx pc %#llx region %s %#llx-%#llx lr %#llx x0 %#llx x1 %#llx x2 %#llx
tl: td %d exec %#llx %s
```

两条都在最终镜像里 `strings` 得到。按空白拆分后的字段位置：

| 行 | 字段 | 含义 |
|---|---|---|
| bad access | `$2` | 进程名，仍只有 `backboardd` 与 `SpringBoard` 会打 |
| bad access | `$6` | 故障地址 |
| bad access | `$8` | pc |
| bad access | `$10` | pc 所在 region 的后备文件名，取不到时是 `-` |
| bad access | `$11` | 该 region 的起止，两个十六进制数中间一个 `-`（`%#llx-%#llx`）；pc 不在任何 region 里时是 `0-0`，因为 `#` 标志只在值非零时加 `0x` 前缀 |
| bad access | `$12`／`$14`／`$16`／`$18` | 字面量 `lr`／`x0`／`x1`／`x2`，用来定位它们后面那个值 |
| bad access | `$13` | `lr`（x30），故障指令的返回地址，即调用方的镜像加偏移 |
| bad access | `$15` | `x0`，拷贝例程的 dst |
| bad access | `$17` | `x1`，拷贝例程的 src |
| bad access | `$19` | `x2`，拷贝例程的 len |
| exec | `$3` | pid |
| exec | `$4` | 字面量 `exec`，用来与同前缀的 `tl: td <pid> slide …`、`tl: td <pid> tid …` 区分 |
| exec | `$5` | 基址 |
| exec | `$6` | 该 region 的后备文件名，取不到时是 `-` |

`$10`／`$6` 是 basename（`vnode_getname` 从 VFS namecache 取的那一份），basename 里没有空格，所以按空白拆字段是稳定的。exec 行每次线程 dump 打一条，紧跟在既有的 slide 行之后；基址为 0 表示这个 task 里没有「有 vnode 后备且权限含 execute」的 region。

`$13`／`$15`／`$17`／`$19` 四个值是保存状态的原始内容，内核不剥 PAC：真出现带签名的 `lr`，用户地址范围以上的那些位自己会说明，判读时按「高位非零且不像本进程任何镜像的加载地址」识别，不要在设备侧猜它签的是什么。取值前判 `is_saved_state64(state)`，32 位的保存状态没有这四个寄存器，那种情况下四个值都是 0。

## 2. 判读要点

- region 名直接给出答案时按名记：落在 `libredwoodmetal.dylib`／`libredwoodair.dylib` 是拷贝路径实现自身引入段错误，落在系统库是拷贝路径让 CA 走过了原先 nil 失败的点。两种结果对拷贝路径的处置不同，由 lead 判 P2。
- region 名是 `-` 而起止有值时，按 `__TEXT` 的 vmsize 反推归属，**不要用文件字节数**：region 打的是 vm_map entry 的起止，对应映射尺寸，两者差一到两个量级。数据来源是 perf 对本轮实际装车产物的 `otool -l` 实测，见[判读口径 §3.3](../analysis/2026-10-28-roundc-reading-criteria.md)：`libredwoodmetal` `0x20000`＝131,072（文件 241,488 字节）、`libredwoodair` `0xc0c000`＝12,632,064（文件 13,983,936 字节）、`backboardd` `0x100000`＝1,048,576（文件 1,366,064 字节）。三个 vmsize 互不相同，size 精确匹配就能定归属；entry 被切分时再用 `off = pc − lo` 的上限排除（`off ≥ 0x20000` 排 `libredwoodmetal`，`off ≥ 0x100000` 再排 `backboardd`）。前提也成立：bad access 走用户态数据异常路径、pc 正在执行，region 必然带 execute，候选集合就是这三个 `__TEXT`，`__DATA`／`__DATA_CONST`／`__LINKEDIT` 都不在里面。反推不成立就写「判不了」。
- region 名是 `-` 且起止是 `0-0` 时，pc 当时不在任何 map entry 里，这一条与「取不到文件名」是两种情形，不要合并计数。
- exec 基址覆盖的是 dyld 为这个进程映射的镜像，slide 行覆盖的是共享缓存里的 pc，两行合起来才能给 dump 里每个 pc 命名。上一轮判读里 tid 306 的 pc `0x105f00cd8` 缺的就是这一项。
- `$17`（`x1`）应当等于同一行的 `$6`（故障地址）。离线分析给出的两处故障指令都是拷贝例程的第一次源访问（`_platform_memmove` 的 `+0x9c0` 是 `ldnp q2, q3, [x1]`、`+0xad4` 是 `ldr x6, [x1], #8`），所以这两个字段相等就是归属结论在设备侧的交叉验证；不相等说明故障指令不是那两处之一，`$8` 的归属要重判。
- `$19`（`x2`，长度）用来核对离线推出的两个长度分支：`+0x9c0` 只在 64 ≤ len < 16384 到达，`+0xad4` 只在 len < 64 到达。`$8` 的偏移与 `$19` 的区间对不上时，两条读数里至少有一条错，不要各取一半拼结论。
- `$13`（`lr`）给调用方的镜像加偏移，三个预期落点按 [驱动 no-copy buffer 记录 §8.6](2026-10-28-driver-nocopy-buffer.md) 判：落在 `libredwoodair.dylib` 说明是 Mesa 侧在上传或拷贝 buffer 内容时调的 memmove（那一侧的输入我们能在驱动里加校验）；落在共享缓存用离线方法（imagesText 加 export trie）命名调用方，不需要 dSYM；落在 `libredwoodmetal.dylib` 与那份镜像的导入表冲突（`nm -u` 里只有 `_memcpy`，没有 `_memmove`），出现这一种就说明「`_platform_memcpy` 与 `_platform_memmove` 是两个独立实现」这条离线结论要重查。

## 3. 实现上的取舍

改动落在三个文件：`hackios-xnu-kernel/out/xnu12377/osfmk/arm64/sleh.c`（打印点，原第 2091 行）、`osfmk/kern/redwood_threads.c`（dump 的 exec 行）、`bsd/dev/redwood_threads.c`（两个新助手）。

- 地址翻镜像名走 `fill_procregioninfo`／`fill_procregioninfo_onlymappedvnodes`（`osfmk/vm/bsd_vm.c`，声明在 `bsd/sys/bsdtask_info.h`），它们是 `proc_pidregioninfo` 一族用的同一入口：map 的加锁、submap 与 shadow chain 的解析、vnode pager 的识别都在 vm 层里做完了。自己遍历 `vm_map_entry` 要把这些重做一遍，还要自己拿 vm_map 锁。
- 这两个函数把 vnode 以裸地址交出来（它们是为 copyout 写的，不持引用），所以取名要用它同时交出的 vid 走 `vnode_getwithvid`：从 map 遍历到取名之间 vnode 可能被回收，vid 是判断还是不是同一个的手段。
- 文件名取 namecache 的 basename，不走 `vn_getpath` 的全路径。全路径要逐级 `build_path`，代价与失败模式都多一类，而归属只需要文件名；region 起止已经把偏移的信息留在行里。
- region 归属自己判 containment。`fill_procregioninfo` 在地址落进洞里时返回它上面的那个 region，直接信它会把「pc 当时没有映射」读成「pc 在下一个镜像里」，两种情形的处置相反。
- exec 基址在 bsd 那半边算好，再把基址与文件名传进 osfmk 半边打印。`fill_procregioninfo*` 自己取 `task_lock`，而 `redwood_thread_dump` 整个线程遍历都持着它，在里层调用会自锁。
- exec 的遍历以 `fill_procregioninfo_onlymappedvnodes` 为一步：它只在真正有 vnode pager 的 region 上停（匿名内存、internal object、非 vnode pager 都返回 0），所以「第一个有 vnode 后备」这个条件由它保证，外面只加 execute 权限的判断。步数上限 64，并且下一步地址不前进就退出。
- 打印范围沿用既有的 `backboardd`／`SpringBoard` 限定，exec 行只在有人写 `kern.redwood.thread_dump` 时出现。bad access 每条从约 60 字节增到约 110 字节，每次 dump 多一条，日志环的覆盖时长没有可观变化（roundb 全轮 15 起事件）。
- 四个寄存器直接读 `saved_state64(state)->lr` 与 `->x[0..2]`，取值前判 `is_saved_state64(state)`：打印点在 `handle_user_abort` 里，这个函数服务的保存状态不保证是 64 位的。不剥 PAC 是有意的：剥一个用户态返回值要在内核里选一个 key，选错会得到一个看起来正常、实际错掉的地址；原始值的高位形态自己会说明有没有签名。
- 新字段追加在行尾，为的是让已发布的判读口径继续可用：字段位置是按空白拆分的下标，追加保持 `$1` 到 `$11` 不变，region 那几项的下标跟着不动，读的人只加四行。

`osfmk/kern/redwood_threads.c` 里的 slide 行此前只在树里、没有提交，而内核 `9a7a118a` 已经把它编进去了，这次随 `690e36a` 一起提交，提交说明里写明了这一点。

## 4. 构建与产物

命令是 `cd hackios-xnu-kernel && XNU26_SRC=out/xnu12377 xnu26/build-macos.sh -j10 BUILD_DSYM=0`，宿主机 macOS 加 Xcode clang，退出码 0，日志里没有一行匹配 `error:`。同一天跑了两次：第一次改三个文件（region 名与 exec 行），产出 `81f544688809a2e8…`；第二次只改 `osfmk/arm64/sleh.c`（加四个寄存器），5 秒跑完，产出下表的 `cf1502f5632284af…`。两次的 `osfmk/DEVELOPMENT/sleh.o` 都是当次产物。

`BUILD_DSYM=0` 是第一次加的，原因是 dsymutil 那一步的 recipe 用进程替换（`2> >(grep -v …)`），跑构建的这个 shell 打不开 `/dev/fd`，报 `bash: /dev/fd/62: Operation not permitted`，默认参数下构建在链接之后停住、最终镜像还是旧的。最终镜像的规则是 `strip .unstripped.noctf`，而 `DO_CTFMERGE=0` 时 dSYM 与 `.ctf` 都不参与它的字节，所以这个开关不改变装进设备的内核。偏离及其后果（lead 已批准）：**本轮 dSYM 未更新**，`BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.dSYM` 停在旧内容、与 `cf1502f5632284af` 这份镜像不同源；后续要对新内核的 pc 做符号化，需要单独补一次跑完 dSYM 那一步的构建，不要拿现有 dSYM 直接符号化。

| 项 | 值 |
|---|---|
| 路径 | `hackios-xnu-kernel/out/xnu12377/BUILD/obj/mach.development.bcm2837`（符号链接，指向 `DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837`） |
| 字节数 | 20,210,232（旧内核 20,210,112） |
| sha256 | `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492` |
| 源码提交 | `5c9f563`（`out/xnu12377`，分支 `redwood26`） |
| 取代 | `81f544688809a2e8`（同日的上一次构建，源码 `690e36a`），再上一版是 `9a7a118a1545fba4` |

记录里那个路径是符号链接，量它的字节数要看命令跟不跟链接。同一个路径上的实测：`ls -l` 与 `stat -f %z` 给链接自身长度 **50**；`stat -f %z -L` 与 `wc -c <` 给 **20,210,232**；`shasum`、`od` 跟链接，对链接与对目标给出同一个 `cf1502f5632284af…`。这次先读到 50 字节才发现，写在这里免得下一次照抄。

`docs/progress/evidence/k90auto/kernel-12377-attr26/kernel.json` 已按实际构建改写，`make-payload.py` 的 digest 断言在宿主机上复算通过（record 与文件都是 `cf1502f5632284af…`、20,210,232 字节），并把两条格式串与字段位置抄进了 `new_prints` 段，随每轮 manifest 一起归档。两次构建的日志分别是 `docs/progress/evidence/k90auto/kernel-12377-attr26/build-region.log` 与 `docs/progress/evidence/k90auto/task14-build.log`。

上一份记录有一处对不上：`build.command` 写的是不带 `BUILD_DSYM=0` 的 `-j10`、`exit` 是 0，而 `sources` 又说 dSYM 那一步失败，且 dSYM 目录的 `Contents` 停在 10-26。`BUILD_DSYM` 在 `makedefs/MakeInc.def:410` 是无条件的 `:= 1`，默认构建会跑 dsymutil。本次按实际执行的命令记录，不再沿用上一条的写法。

由此得到一条具体实例：**旧内核 `9a7a118a` 那份记录的 `command` 字段不可信**，它要么少写了参数，要么另有一次没有记下来的重跑。判读内核相关结论时以每轮 manifest 的 `kernel` 段哈希为唯一凭据（协议 §3 已有这条口径），`command` 与 `sources` 只当参考；要复现某个内核，先核对哈希，再照 `command` 跑一遍并预期可能对不上。

## 5. 未验证的部分

- 两处打印本身没有真机验证，要等 round C 跑出来才知道 basename 取得到取不到（namecache 里没有名字时打 `-`，这在真机上出现的频率未知）。
- exec 基址取的是「第一个有 vnode 后备且权限含 execute」的 region，在 iOS 上通常是主二进制的 `__TEXT`，但这一点由行里打出来的文件名自证，不靠假设；第一次读到时要核一眼 `$6` 是不是预期的那个镜像。
- `lr` 有没有带 PAC 签名要等真机读数。离线分析用的 pc（`0x2b0fb59c0`）是不带签名的形态，同一份保存状态里的 `lr` 大概也不带，这一条没有验证；带签名时 `$13` 会在用户地址范围以上有值。
- `$17` 等于 `$6`、`$19` 落在两个长度分支之一，两条都是离线分析的推论，round C 是第一次在设备上验它们。
- 四个值在 32 位保存状态下全是 0。这一轮的 `backboardd` 与 `SpringBoard` 都是 arm64e，走不到那个分支，但读数为 0 时先排除它再当成「寄存器里就是 0」。
- 两次构建都没有跑任何设备命令。`root26.apfs`、`system26.apfs` 与 staging `root/` 在 task-7 那次容器运行前后哈希一致；`userland/obj/input26-service` 被那次运行覆盖过，已从 `out/ios26-resume/bbmetal-device/root/bin/` 取回逐字节相同的宿主那份（`5d682cc3729a9cd1`）。

## 6. round C 实测（device，2026-10-28）

轮次身份：payload `ebdca4adfc9fb5f4…`（25,437,256 字节），内核 `cf1502f5632284af…`（roundc manifest 的 `kernel` 段与 task-14 记录一致），apfs 复用 roundb 的 `e36caefb…`（打包后复算未变），`pack.driver_sha256` `9d66dd36…`、`pack.air_sha256` `d7b9ced5…`、`jobs_source.sha256` `a4af9a9f…` 与 `jobs_sha256` `88326d5e…` 两项都等于 roundb 值，cmdline 除 `epoch=1793167025` 外与 roundb 逐字段相同，`gpu_speed` 3。13:59:17 起跑，`SAMPLED_SECONDS 420.4473890408408`、`failed_call None`；teardown 走 `"mode": "android"` 分支，run-queue 的 recover-loader 自动恢复到 loader A（`identified Android B to LK to existing loader A`），`fastboot getvar result` idle 通过，收尾时设备在 loader、无按键介入。证据在 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundc/`（21 份 s*.log 加 hung-held.log），判读脚本与输出在同级 `analysis-roundc/`。

**全轮 bad access 为零**：raw（跨快照求和）0、唯一行 0、物理事件 0，s*.log 与 hung-held.log 都是 0 条。`lr`／`x0`／`x1`／`x2` 四个新值没有数据，§2 的三条自我否证判据（`$17`=`$6`、`$19` 对 pc 区间、`lr` 三类归属）与 §5 的 PAC 形态、32 位排除两条在本轮都未获得验证，region 后备文件名（`$10`）同样没有执行记录。

形态与 roundb 相反，按判读口径 §8 的判据归入冻结形态：`backboardd` 与 `SpringBoard` 的 `exited code` 行都是 0 条；帧号 id 1..3611 无断裂、3611 次交换交接；交换空档 8 个（首个 15.4 s，随后 15 s 周期的约 3 s 空档，最后一次交换在 tl 12941.7 s，其后到轮末约 300 s 提交永久停止，framewatch `still no frames` 计到 297 s）；截图 101 张全部 home screen、`bad_shots=0`（roundb 是 black x94）；`SpringBoard` pid 30 与 `backboardd` pid 38 全轮存活，lsprobe t=60 与 t=300 两次 `procs=` 读数相同。对照 roundb（内核 `9a7a118a`、同一份 apfs、同一份 jobs）：15 代 backboardd 死于 11/11、212 条 raw bad access、黑屏重启循环。

exec 与 slide 两处打印验证成立（§5 第二条）：exec 行有真实值且 `$6` 正是预期的主二进制，`tl: td 30 exec 0x100fb4000 SpringBoard`、`tl: td 38 exec 0x100c78000 backboardd`；slide 两个 pid 都是单值 `0x105a4000`。dump 正常发生：`periodic dump` 行在，`tl: td pid 30 threads 18..57`、`tl: td pid 38 threads 12..14` 随时间增长，`tl: td pid 30 printed <K>` 行齐。

拷贝路径这一轮走到了但零故障：`rwa buffer: copied` raw 230（s*.log 口径）、唯一行 21，尺寸分布 16384×16、65536／62464／49152／32768／15360 各 1（49152 是 roundb 没出现过的尺寸；roundb 以 32768 为主，raw 1487/1675）。驱动侧 nil 两种：`rwa buffer: 1081344 bytes left nil, over the 65536 this path copies` ×3、`1163264` 同款 ×13；CA 侧 `nil buffer from memory` raw 16。roundb 里 `copied` 与故障的相邻率是 11.8%（209/1775），本轮 230 条 `copied` 对应 0 起故障。round-stats 的「no-copy served as a copy: 0」数的是旧驱动的打印串 `no-copy buffer of N bytes served as a copy`，与 `9d66dd36` 的 `rwa buffer: copied` 是两个指标，不冲突。

AIR 身份运行时核对通过：`perf draw: timing on, frames over 6000 us are printed, 128 frames per summary` 出现（raw 100、唯一 1 条），装车 AIR 确为 `d7b9ced5`；`perf driver` 行 raw 162。本轮帧数据在插桩开着的条件下采集。

死亡行：`died on signal` 唯一行 28 条，全部是 widget 与系统任务（signal 9 code 1001 四个进程 10 行、signal 5 code 5 三个进程 9 行、signal 1 code -1 的 launchd.ios 与 MSUEarlyBootTask 各 1 行），signal 11 零条，backboardd／SpringBoard 零条。崩溃报告收集：`crash_files=0 crashes=root=-`（t=60 与 t=300 相同），按判读口径 §6 属第一类「目录空」；配 28 条死亡行读作「有进程死了但 ReportCrash 目录里没有报告」，通道修复仍排 round D。

热与频率：`thermal: 3072 MHz held for 390 s (13 of 13 windows, domain 1), hottest 72.1 C in the first window, still there in the last of 13 windows (peak 78.3 C)`，`ff_s=390`；上限全程未掉，属判读口径 §9.2 三种去向里的第一种。`summary.py --verify` 的 coverage 跨度 418 s（tl 12841497838..13259580616 µs）、最大 tl 间隔 10.0 s。

解释边界（协议 §5）：本轮与 roundb 的唯一变量是内核（`9a7a118a` → `cf1502f5`，差异是 task-1 的 region/exec 打印加 task-14 的四个值），但本轮零故障意味着 bad access 打印路径上的新代码一次都没有执行，执行过的新代码只有 dump 的 exec 行。「内核差异导致形态翻转」这个因果在本轮数据里立不起来，重启循环形态是否仍可由 `9a7a118a` 复现、以及拷贝路径与故障的相关性（roundb 的 11.8% 相邻率对 round C 的 230 条零故障）都还是未决问题，归 lead 与 perf 判。

## 7. roundb 与 round C 两份内核的源码差异（display，2026-10-28）

本节回答一个问题：round C 从重启循环翻成冻结，有没有可能来自内核。四点全部离线核出，没有构建、没有碰设备、没有跑 `package.py` 与 `build-air.py`。结论在 7.5。

### 7.1 roundb 那份内核出自哪个源码状态

roundb 的内核是 `9a7a118a1545fba4…`、20,210,112 字节。`docs/progress/evidence/k90auto/kernel-12377-attr26-roundb/manifest.json` 的 `build.sources` 逐字记着「out/xnu12377 at e933479 with the thread dump printing the task's shared-region slide; the image links, the dSYM step of build-macos.sh fails on a missing intermediate」，`build.command` 是 `XNU26_SRC=out/xnu12377 xnu26/build-macos.sh -j10`，`build.host` 是 macOS with Xcode clang。同一份 manifest 的 `record_written_by_hand` 说明这条记录是手写的：`tools/k90auto/build-kernel.py` 在 kbuild 容器里对 xnu-8796 那棵树构建，记不了 macOS 上从 `out/xnu12377` 出的内核，而 `kernel.sha256` 是产物的实际哈希。

所以 roundb 的内核是**提交 `e933479`（2026-10-28 07:21:54）加当时工作树里未提交的改动**，其中已知的一项是 thread dump 打 slide 那行，后来由 `690e36a` 提交。构建时刻只能夹在区间里：`e933479` 提交于 07:21:54，freeze 那轮的 manifest（同一个内核 sha）写于 09:44:16，roundb 的载荷 `out/handoff-12377-attr26-roundb.bin` 打包于 10:17:17、跑轮在 10:27，所以构建发生在 07:21:54 到 09:44:16 之间。

round C 的内核 `cf1502f5632284af…` 出自 `5c9f563`（提交时间 13:31:14），构建 13:28:58 到 13:29:03，比提交早约两分钟：镜像由工作树编出，随后才提交，两者的对应关系靠 task-14 收尾时核过的那三个文件在 `git status` 里干净。

### 7.2 两份内核之间的源码 delta：三个文件，没有第四处

`git diff --stat e933479 5c9f563`：

| 文件 | 增删 | 内容 |
|---|---|---|
| `bsd/dev/redwood_threads.c` | +127 | 新增 `redwood_task_region_image()` 与 `redwood_task_exec_image()`，sysctl 里在 dump 之前读 exec 基址 |
| `osfmk/arm64/sleh.c` | +43 | bad access 打印的 region 名与 `lr`／`x0`／`x1`／`x2` |
| `osfmk/kern/redwood_threads.c` | +19 | dump 多打 `slide` 与 `exec` 两行，函数签名加两个参数 |

三个提交各自的范围：`690e36a` 改这三个文件（+160/-10），`ff5a9cb` 只改 `sleh.c` 的注释（+2/-1），`5c9f563` 只改 `sleh.c`（+21/-3）。**delta 里没有第四处**，与 lead 的预期一致。

### 7.3 那 27 个未提交的已跟踪改动，在两次构建之间没有变

`out/xnu12377` 的 `git status --short` 有 147 行，其中 ` M` 的 27 行是已跟踪文件的改动，其余是未跟踪文件（含 `BUILD/`）。这 27 个的 mtime 最大是 `osfmk/conf/files` 的 2026-10-28 05:18:47，其余都在 2026-10-27 15:18:59 及更早，全部早于 roundb 内核的构建窗口。

按时间窗扫全树是直接核法：`find . -path ./BUILD -prune -o -type f -newermt "2026-10-28 07:21:54" ! -newermt "2026-10-28 13:28:58" -print`，命中的源文件正好是那三个（`bsd/dev/redwood_threads.c`、`osfmk/kern/redwood_threads.c`、`osfmk/arm64/sleh.c`），其余命中全在 `.git/objects/` 下。两次构建之间没有任何第四个源文件被写过，27 个未提交改动的内容在两份内核里是同一份。

`osfmk/conf/files` 那处改动是加一行 `osfmk/kern/redwood_threads.c	standard`，作用是把 thread dump 的 osfmk 那一半注册进构建，两份内核都带着它。

一个读构建产物时会遇到的现象：round C 那次 5 秒的增量构建写了 16 个目标文件，除 `sleh.o` 之外还有 15 个与本次改动无关的（`bcopy.o`、`bzero.o`、`memset_s.o`、`cc_clear.o`、`cc_dit.o`、`ccdigest_final_64be.o`、`ccdigest_init.o`、`ccdigest_update.o`、`cchmac.o`、`cchmac_final.o`、`cchmac_init.o`、`cchmac_update.o`、`ccsha256_initial_state.o`、`ccsha256_K.o`、`sha256_compress_arm64.o`）；task-1 那次同样窗口里是 2 个。同一份源码在不同构建里重编的目标文件集合不同，这一条与 7.4 的确定性有关。

### 7.4 构建确定性：两处明确的来源，都不在本轮的差异里

「同源两次构建」未实测（一次要几分钟到十几分钟，lead 要求不为此跑两次）。按构建系统的输入核出两处会让字节变的东西。

**一、生成的 `version.c` 里嵌了构建时间、构建者登录名与 `git describe --dirty`。** 规则在 `makedefs/MakeInc.kernel:285`（`$(OBJPATH)/version.c: $(SRCROOT)/config/version.c.template $(NEWVERS) $(XNU_VERSION)`），产物 `version.o` 链进镜像。镜像里的串原文：

```
@(#)VERSION: Darwin Kernel Version 25.6.0: Mon Oct 26 12:50:44 CST 2026; fan:xnu12377[xnu-12377.121.6-1-gaec10a9-dirty]/BUILD/obj/DEVELOPMENT_ARM64_BCM2837
```

它的依赖是模板、`NEWVERS` 与 `XNU_VERSION`，所以增量构建会复用：`version.c` 与 `version.o` 的 mtime 都是 2026-10-26 12:50:44，而 roundb 载荷里那份内核与 round C 那份的这行串逐字相同（对 `out/handoff-12377-attr26-roundb.bin` 用 `strings -a` 加 `grep -F` 核过）。同一条增量构建序列里它不变；换时间、换构建者、换 git 状态做一次干净构建，它就变，镜像字节随之变。

两条读法上的后果：串里的 `aec10a9` 是移植线的基提交（2026-10-26 11:55:04，`redwood: Apple-file changes rebased onto xnu-12377.121.6`），所以**镜像里的版本串不指认产出它的源码提交**，roundb 与 round C 两份镜像的版本串完全一样，来历只能靠 manifest 一类外部记录；`-dirty` 说明生成它时工作树已带未提交改动。

**二、镜像里嵌了源文件的绝对路径。** `strings -a` 在 round C 的镜像里读到形如 `<检出目录>/osfmk/kern/machine.c`、`<检出目录>/osfmk/kern/processor.c`、`<检出目录>/osfmk/tests/kernel_tests.c` 的串（源码里的 `__FILE__` 用法带进来的，此处按隐私约束写成占位符）。换一个检出目录构建，镜像字节就不同。这一条同时是发布前的一道检查：内核镜像与载荷里带着本机用户目录，镜像在 git 忽略的 `out/` 下、载荷也不进仓库，所以现有提交没有泄露；要对外发布镜像或载荷，先处理这些串。

没有找到的来源：整棵源码树（排除 `BUILD/`）里 `__DATE__` 与 `__TIME__` 零命中；上面那 15 个目标文件里也没有绝对路径（对 `bcopy.o` 查过）。未验证的是那 15 个与本次改动无关却重编的目标文件输出是否逐字节稳定，它们不含时间戳与绝对路径，但没有做同源两次构建的对照。

### 7.5 结论与下一轮该测什么

先把「round C 执行过哪些新代码」定死，这是全部推理的支点。

bad access 打印那条路径（`sleh.c` 的 region 名与四个值，加 `bsd/dev/redwood_threads.c` 的 `redwood_task_region_image()`）**一次都没有执行**。依据是 device 的零命中与我这次对全部 22 份日志的复核：`bad access at` 每份都是 0 条。这条路径的唯一进入条件是进程名等于 backboardd 或 SpringBoard（`sleh.c:2107-2108`），没有节流、没有预算、没有 once 标志，所以「0 条」等于「没执行」，读不出「执行了但被压住」。

执行过的新代码只有 dump 那一条：`kern.redwood.thread_dump` 这个 sysctl（`bsd/dev/redwood_threads.c:176-178`）先在 `:170` 调 `redwood_task_exec_image()`，走最多 `REDWOOD_EXEC_IMAGE_PROBES` = 64 次 `fill_procregioninfo_onlymappedvnodes()` 找第一个带 execute 权限且有 vnode 的 region，再在 `:171` 调 `redwood_thread_dump()` 多打两行。

这条执行过的路径有没有可能把重启循环变成冻结，日志给了三条否证。

1. **最后一次 dump 完整收尾。** `s020.log` 里最后一次请求在第 18297 行（`periodic dump 15 of 15, asked for backboardd pid 38`），随后 18298 到 18314 是它的完整输出：`tl: td pid 38 threads 13`、`tl: td 38 slide 0x105a4000`、`tl: td 38 exec 0x100c78000 backboardd`、13 行线程、`tl: td pid 38 printed 13`。日志里没有半截的 dump。
2. **请求方没有阻塞也没有被拒。** dump 由 `framewatch` 请求，两条来源都在日志里走到头：周期模式（`framewatch.m:159-191`，每 20 秒一次、共 15 次、2 个名字）打到 `periodic dump 15 of 15`；停滞模式那个实例的启动行是 `watching kern.redwood.frames from 3611, still after 2 s, at most 6 dumps`，它在 `stalled == still_seconds` 那一刻触发一次 `dump_all`（`framewatch.m:270-272`），产出第 17332 与 17355 行两条 `dump asked for`，此后 `stalled` 单调增长、`== 2` 的条件不再成立，只剩 `:275-276` 那句 `still no frames` 每秒一条，打到 297 s。`dump refused` 全轮 0 条。最后一次请求之后还有 159 行输出，其中 89 条是 `still no frames`。**dump 停止的原因是两个用户态预算：周期模式 15 次用完，停滞模式每次停滞只在跨过阈值那一秒触发一次。**
3. **那次 sysctl 的加锁语义不构成全局阻塞。** `CTLFLAG_LOCKED` 在 `bsd/sys/sysctl.h:166` 的定义是「node will handle locking itself」，处理器不持内核锁运行。`redwood_task_exec_image()` 放在 dump 之前调用，原因是 `fill_procregioninfo*` 自己取 `task_lock`，而 osfmk 那一半在线程遍历期间持着它（`bsd/dev/redwood_threads.c:168-169` 的注释）。

据此：**本轮数据里没有任何一条能把形态翻转归到内核差异上。** 零故障使 bad access 那条路径的新代码完全没执行；执行过的那条路径有界（64 次探测）、跑完了、输出齐全、请求方存活；两次构建之间除那三个文件没有第四个源文件被写过，所以「唯一变量是打印代码」这个前提成立。7.4 那两处不确定性来源在两份内核里取值相同（版本串逐字一致），也不构成本轮的差异。

剩下的解释按可能性排，三条都未证。

1. **同一个缺陷在两轮换到不同结局。** task-15 那两处窗口（`redwoodmetal.m` 的 `:4811` 到 `:4915` 之间零引用，与 `setBytes:` 三处把唯一持有者交给 autorelease pool）成立与否取决于时序与槽位是否被复用。roundb 的 15 次崩溃需要释放掉的槽位被别的分配复用成非法指针；复用没发生时拷贝会成功而内容错，表现就可以是提交卡住、没有帧。round C 的形态（末次交换后提交永久停止、`still no frames` 到 297 s、两个进程全程存活、零 bad access）与这个读法一致，它也解释了为什么本轮拿不到 `lr`：bad access 需要拷贝真的踩到非法地址。
2. **轮次之间的变化本身有随机成分**，与内核无关。两轮的 apfs 与 jobs 相同，但启动时的分配布局、热状态（round C 全程 3072 MHz 未降频、最高 78.3 C）与 GPU 侧状态都不受控。
3. **内核差异起了作用，但作用点不在打印路径上。** 目前没有支持它的观测：执行过的新代码只有 dump 路径，而它有上面三条否证。要让它重新成为候选，需要一条本轮没有的观测，例如别的轮次里 dump 输出被截断。

下一轮该测什么，按性价比排。

1. **同一份 round C 内核再跑一轮**，不重新构建、不改载荷。它直接分开「翻转来自内核」与「翻转来自轮次间的变化」：形态仍是冻结说明与内核差异无关，形态回到重启循环说明本轮零故障是随机结果，而那一轮就能拿到 `lr`／`x0`／`x1`／`x2` 的读数。这是唯一不需要新构建就能推进 P1 的一步。
2. **把 dump 的覆盖补到冻结末尾**，改的是 jobs 与 `framewatch` 的参数，不改内核也不改 apfs 里的库。周期模式在预算内每 20 秒给一个采样点，round C 那 15 次覆盖启动后约 300 秒，最后一次请求 `periodic dump 15 of 15` 落在日志结束前 159 行、其后还有 89 条 `still no frames`，所以**缺口是冻结的最后 89 秒，冻结的前约 208 秒有周期采样，那部分数据现在就能读**。停滞模式那个实例在一次连续停滞里只触发一次，之后沉默；实例与预算的对应关系见 §8。要读「最后一次提交卡在哪」，把周期模式的 `--count` 提到覆盖整轮就够。
3. 若 1 与 2 之后仍然零故障，再动内核，且只加一条不限进程名的 bad access 计数：累计值随周期性打印输出一行，每次故障单独一行的形式在 1 MB 的环里装不下，环只装约 20 秒，计数要连节流一起设计。当前的进程名过滤让「全系统零故障」与「这两个进程零故障」在日志里读起来一样，这条计数把两者分开。

## 8. framewatch 的采样覆盖与 jobs 行的对应（display，2026-10-28）

§7.5 第 2 项要改的是 jobs，改之前先把现状写清：谁在请求 dump、请求多少次、日志里怎么认出来。这一节是后面读 `tools/k90auto/jobs/` 的入口。

### 8.1 现状：三个实例并发，每个的预算不同

`tools/k90auto/jobs/rc.jobs.freeze` 现在起三个 `framewatch` 实例：

| jobs 行 | 命令 | 模式与预算 |
|---|---|---|
| `:11` | `framewatch 5 0 backboardd SpringBoard &` | 停滞模式，阈值 5 秒，`MAX_DUMPS` 0：只报停滞，不占 dump |
| `:12` | `framewatch --every 20 --count 15 SpringBoard backboardd &` | 周期模式，每 20 秒一次，共 15 次，覆盖启动后约 300 秒 |
| `:19` | `framewatch 2 6 backboardd SpringBoard` | 停滞模式，阈值 2 秒，最多 6 次；前台行 |

`:19` 那行没有自己的启动延迟，init 按行顺序执行、等上一行返回，所以是 `:13` 的 `rwtouch wait 90 … wait 10 … wait 50` 把它推到约 150 秒才启动，`:14-18` 的注释记了这个手法与选阈值 2 秒的理由（轮次里从约 180 秒起每 15 秒有一个 3 秒洞，5 秒阈值在 3 秒洞里不会触发）。

**日志行怎么对回 jobs 行**：每个实例启动时打一行自己的参数，读这一行就能认出是哪个实例、还剩多少预算。round C 的 `s020.log` 里三行原文：

```
framewatch: watching kern.redwood.frames from 0, still after 5 s, at most 0 dumps
framewatch: periodic dumps every 20 s, 15 of them, 2 names
framewatch: watching kern.redwood.frames from 3611, still after 2 s, at most 6 dumps
```

第一行是 `:11`（`from 0`：启动时帧计数是 0），第二行是 `:12`，第三行是 `:19`（`from 3611`：它在约 150 秒启动，那时帧号已经到 3611，也就是本轮最后一个帧号）。周期模式每次请求前还打一行 `framewatch: periodic dump i of count, asked for NAME pid N`（`framewatch.m:177-178`），所以 `i of count` 直接给出预算用到第几次。§7.5 判断「dump 为什么停了」用的就是这两类行。

### 8.2 参数接口与触发语义

参数（`framewatch.m:200-232`）：停滞模式 `framewatch STILL_SECONDS MAX_DUMPS [NAME...]`（用法行在 `:210-211`），周期模式 `framewatch --every SECONDS --count N [NAME...]`（`:200-208`），名字最多 8 个（`MAX_NAMES`，`:50`），不传名字时默认 backboardd 与 SpringBoard（`:52`）。

停滞模式的触发条件（`:265-276`）：每秒轮询一次 `kern.redwood.frames`（`:89`），帧号没长就把 `stalled` 加一，长了就归零并打一条 `resumed`；`stalled == still_seconds` 那一刻调一次 `dump_all` 并把 `dumps` 加一（`:270-272`）。条件用的是相等，所以**一个实例在一次连续停滞里只给一个采样点**，`MAX_DUMPS` 剩下的次数留给之后的停滞。`stalled > still_seconds && dumps >= max_dumps` 时每秒打一条 `still no frames`（`:275-276`）。

周期模式的触发（`:159-191`）：睡 `every_seconds` 秒，然后对每个名字请求一次 dump，共 `count` 轮，与帧号无关。

### 8.3 round C 的缺口怎么算出来的

`s020.log` 里最后一次周期请求是 `periodic dump 15 of 15`（第 18297 行），预算到此用完；它之后还有 159 行，其中 89 条是 `still no frames`，编号从 209 连续到 297，一秒一条。所以周期采样覆盖到冻结的第约 208 秒（297 减 89），**最后 89 秒没有线程状态**。`dump refused` 全轮 0 条，说明 15 次请求都被内核接受。

`:19` 那个实例在停滞第 2 秒触发了一次 `dump_all`，产出第 17332 与 17355 行两条 `dump asked for`，此后 `stalled` 单调增长、相等条件不再成立，它剩下的 5 次预算一次也没用上，也不打 `still no frames`（`dumps=1 < max_dumps=6`，`:275` 的条件不成立）。日志里那些 `still no frames` 全部来自 `:11` 那个实例（`MAX_DUMPS` 0，`dumps=0 >= 0` 成立）。

### 8.4 环预算

一个 pid 的一次 dump 约 17 到 22 行：3 行头（`tl: td pid N threads M`、`slide`、`exec`）加线程行加 1 行 `tl: td pid N printed K`。round C 的 pid 38 是 13 行线程、pid 30 是 18 行，两个名字合计约 40 行，周期模式每轮请求前还有 2 行 `periodic dump`。

冻结期的日志本来就稀，约每秒 1.5 行（`still no frames` 1 条，加 `cpufreq` 每 30 秒一组、`battery` 偶发、`tl: a` 每约 5 秒一条）。1 MB 的环装约 20 秒，按这个速率一次 40 行的 dump 约占 27 秒环容量，会把之前 27 秒顶出去。

要加密采样时的两条边界：一是快照间隔要短于相邻两个采样点的间隔，否则后一个采样点顶掉前一个，device 读不到；二是行数实在吃不下的退路是每个实例只盯一个名字，行数减半。

### 8.5 加实例时的两条约束

1. `MAX_DUMPS` 要大于 1。配 1 时实例打完唯一一次 dump 就进入 `:275-276` 那条每秒一行的分支，多个这样的实例会让环消耗成倍增长。`:19` 那个实例配 6 而只用掉 1，正是这个配置让它打完就沉默。
2. 停滞模式的阈值从实例自己启动那一刻起算（`:233` 启动时读一次 `last`，`stalled` 从 0 开始），要让采样点落在冻结里，实例必须在冻结之前就在跑，新加的行要放在 `:13` 的 `rwtouch` 之前。周期模式那行本来就在 `:13` 之前，不用移。

实例之间不互相干扰：都写同一个 sysctl `kern.redwood.thread_dump`（`:126`、`:182`），处理器无状态，按 pid 找 proc、走线程、打印；都读 `kern.redwood.frames`（`:89`），只读；都往 stdout 写（`say()` 是 `vprintf` 加 `fflush`，`:60-68`），init 把每行的 stdout 送进同一个日志环，共享的只有环预算。两个实例同一秒对同一个 pid 请求 dump 会让输出行交错，阈值错开就不会。

### 8.6 round E 的取法

round E 取提 `--count` 这一条：`:12` 改成 `framewatch --every 20 --count 30 SpringBoard backboardd &`，覆盖启动后 600 秒。轮次约 420 秒，600 秒有余量；轮内实际触发次数与配 25 或 40 相同（约 21 次），所以这个值只影响将来延长轮次时够不够，不影响本轮环压力。改动是一行 jobs，不重建 `framewatch`、不跑 `package.py`，它的哈希不变。

按停滞时长定点采样那条（配 30／60／120／240 秒四个实例，每个 `MAX_DUMPS` 2）本轮不取：20 秒网格的采样点在知道冻结起点之后可以换算成冻结相对时刻，而要对的时刻（例如「+106 秒起 runloop 不再泵」）用 20 秒网格足够分辨；定点采样要加四行、要把快照间隔压到 20 秒以内，是三处改动。若 round D 是重启循环形态，round E 的优先项会让位给 `lr` 读数的落地，jobs 的改法也不同。
