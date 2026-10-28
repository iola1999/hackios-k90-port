# k90auto 真机轮申请协议

本协议规定真机轮怎么申请、一轮跑什么、失败怎么处理、回报哪些数字。设备由 device 独占，其他队友只读日志。收尾路径的实测与人工边界见[无人值守收尾](2026-10-28-unattended-teardown.md)，工具用法见 [k90auto 说明](../../tools/k90auto/README.md)。

## 1. 谁可以碰设备

只有 device 执行任何会碰设备的命令：`fastboot`、`adb`、`tools/k90auto/run-queue.sh`、`run-auto.py`、`recover-loader.py`、`reboot-lk.py`、`hackios-xnu-kernel/tools/stage-system.sh`。其他队友提交申请，由 device 排队执行并把原始输出回报。同一时刻只允许一个 fastboot／adb 客户端；并发访问会留下未终止的 IN 请求，把 USB 命令通道卡住（2026-10-28 出现过一次，两个客户端同时 `getvar` 后设备只能靠复位恢复）。

## 2. 申请格式

一条申请写清下面六项，缺一项我会退回补齐：

| 项 | 内容 | 例 |
|---|---|---|
| 变量 | 这一轮唯一要改的东西；一轮只改一个变量 | `adreno8_speed=2` 对照 `3` |
| 载荷 | 内核记录名、根盘路径、`make-payload.py` 的 EXTRA BOOT-ARGS | 见第 3 节 |
| 指标 | 要回答的问题，以及日志里的哪几行能回答 | `rwa bind:` 行的 constant buffer 列 |
| 判据 | 什么结果算通过，什么结果算不通过，都要写 | `copy` 计数非 0 |
| 时长 | 建议 300～420 秒；更长的轮次说明原因 | 420 |
| 证据标签 | `<LABEL>`，小写字母数字与连字符 | `mipmap-cc` |

## 3. 载荷怎么生成

`make-payload.py` 的固定参数已经包含 GPU 阶段 23 与安全交接、双核、触摸屏、按键、电量计，申请只提供 `EXTRA BOOT-ARGS`。示例里的 `GPU_SPEED=3` 是本轮操作值（roundb 与 round C 实测档位 3）；旧示例曾写 `1`，那是 `34209c1` 之前的内核要求（`make-payload.py` 注释原文：「default 3: up to 342 MHz with load; kernels before 34209c1 need 1」），照抄会把 GPU 固定在 160 MHz。示例是会被照抄的模板，档位要按操作值显式写、不依赖默认值：

```sh
SYSTEM=hackios-xnu-kernel/userland/system26.apfs SYSTEM_WINDOW=0x300000000 \
MEMSIZE=300000000 IDENTITY=v57 GPU_SPEED=3 \
python3 tools/k90auto/make-payload.py 12377-attr <LABEL> <RAMDISK> "<EXTRA BOOT-ARGS>"
```

- `GPU_SPEED` 是 `adreno8_speed`：1 固定 160 MHz，2／3 按负载与触摸在 160 MHz 与 222／342 MHz 之间切换。要与既有轮次对照就显式写，不要依赖默认值 3。
- `EXTRA BOOT-ARGS` 里常用的：`metal=1`、`cpufreq=1`、`fb_threads=2`、`gpu_log=1`、`touch_lat=1`（`gestures.py` 需要）、`touch_lat=1 glslow=3000`（同时要窗口服务器的每帧绘制时间）。
- `CPU_ARGS` 可换掉默认的 `cpus=2 bootcpu=7 small_cores_after=0`，只在确实要对照 CPU 配置时才换。
- `SYSTEM` 与 `SYSTEM_WINDOW` 只换系统盘时才改，换盘同时改 `root.apfs` 时必须重写 `manifest.json`，我会核对哈希。
- 工具会在 `docs/progress/evidence/k90auto/kernel-12377-attr-<LABEL>/manifest.json` 写下 payload、根盘、系统盘的字节数与 SHA-256，`run-auto.py` 据此校验，不能手改。
- **工作树状态只记录，不拦打包**：打包前查两处工作树的未提交改动，`common/ugit status --short` 覆盖 `.userland.git` 下的 userland、Mesa 与 AIR 源码，顶层仓库只看 `tools/k90auto`（打包代码）。结果写进 `manifest.json` 的 `worktree_status`（`dirty_worktree: true`）并打印一行提示，打包继续进行。这一项原先会拦下打包，2026-10-28 改成只记录，因为它挡住过一轮真机测试，而设备时间比这条检查的价值高。未提交改动会进入这一轮的驱动这件事仍然成立：两个库每次从工作树重编，2026-10-28 03:48 的打包是 `f8c9042f`，04:00 从同一个工作树再打包变成 `3d7ea90e`，中间只有 display 未提交的头文件改动。所以记录留着，事后查这一轮由什么构成读 `worktree_status` 那一份清单。
- **基线闸管「库变了没有」**：`tools/k90auto/library-baseline.json` 记着驱动的 `driver_sha256` 与 AIR 的 `air_sha256`，本轮的构建值与之不符就**打包失败**，报错给出两个哈希。确实要接受变化时，提交那次改动，单次打包设 `ALLOW_DRIVER_CHANGE=1`，并把两个哈希写进该轮的归档说明（`manifest.json` 里记 `library_change_accepted: true`）。可以用 `EXPECT_DRIVER_SHA256`／`EXPECT_AIR_SHA256` 临时覆盖期望值。基线文件不存在时，第一次打包会写出来并打印，那一次就是基线；这个文件在干净检查里被排除，避免「谁先打包谁定基线」之外再出现「基线未提交就永远打不了包」。
- 「本轮到底跑了什么」由两件事说明：基线检查管编译产物的哈希，`worktree_status` 管源码侧有哪些未提交改动。建立基线的做法是改动先提交，再打包一次，把那一次的哈希作为基线。
- **打印节流的计数不是事件计数**。`tl: p` 只在 2 的幂次打印（`RW_AGAIN`），`gestures` 轮去重后 426 条移动样本对应 `rwtouch.c` 的 `SAMPLE_MS = 8`、实际约 3,750 次移动；`no-copy served as a copy` 同样是打印数量。这两个数只能判「有没有发生」，判不了「发生了几次」。需要次数时读不节流的计数器（`kern.redwood.frames` 每次 swap 递增）。
- **性能轮的手势必须落在会重绘的界面上**。静态界面不重画，帧数与每帧耗时都没有意义：2026-10-28 的主屏轮里 `command buffers` 在 3,520 次之后不再增长，画面是好的，因为主屏静止。测性能要在主屏上翻页或拖动，或者打开会持续动画的界面；判「有没有画过」用截图分档（`round-stats.py` 的 `screens` 一节，黑／锁屏／主屏三档），不判「是否一直在画」。
- **判据依赖「某机制会留下痕迹」时，先验这个前提，再排轮次**：读源码、读格式定义、或在主机上做一次可做的验证，都排在设备轮次之前。2026-10-28 有一例：判「SpringBoard 是否读了 `IconState.plist`」时考虑过读 `st_atimespec`；先确认该路径落在哪个文件系统上，再读那一份实现——`/private/var` 在这个移植里是 ramfs（`bsd/miscfs/ramfs/ramfs.c:5`、`bsd/dev/redwood_apfs_check.c:400`），`rn_atime` 只在创建（`ramfs.c:147`）、`setattr`（`ramfs.c:177`、`ramfs.c:969`）、取值（`ramfs.c:890`）三处出现，没有读路径上的更新；APFS 那侧同样只有解析路径一个赋值点（`bsd/miscfs/apfs/apfs_lib.c:1564`）。两个实现都证实读一次 `st_atimespec` 不会变，这条路从源码上作废，一次设备轮次与一次主机 `stat` 都省掉了。挂载选项类的判断（`noatime`）不能在主机上验，主机的挂载选项与设备无关。
- **结论写在未被忽略的位置**：`AGENTS.md` 与各仓 `.gitignore` 决定一个文件进不进版本控制，写进一个被忽略的路径等于没写。写结论前先 `git check-ignore -v <目标路径>`，有输出就是被忽略，换位置或加白名单；比记住 `.gitignore` 的规则可执行。2026-10-28 的 `userland/`（在 `hackios-xnu-kernel` 的白名单之外）与 `tools/k90auto/` 之外新加的脚本都属于「位置对了没被忽略」与「位置错了写不进仓库」两种情形，判法相同。
- **口径先声明，再报数**：同一个量有三种口径，读出来的数差几倍。2026-10-28 三次实例：`Code=4099` 按跨快照求和是 172、按唯一行是 45、按服务名分开才是可比的 44／26（前两个数进过判据）；`nil buffer from memory` 按行内出现次数是 712、按唯一行是 61～68（「数百条」这个数因此被写错）；宿主崩溃按跨快照求和是 12 条、按唯一行是 4 条。**报告里写清「唯一行」还是「跨快照」、写清是不是按名字分开**，不确定就用 `tools/round-stats.py` 的输出。
- **这个工作区有三个 git dir，提交前先看文件在哪一个**：顶层（文档、`tools/`、`tools/k90auto/`）、`hackios-xnu-kernel`（脚本、`common/`）、`hackios-xnu-kernel/out/xnu12377`（内核源码，分支 `redwood26`）、以及 `hackios-xnu-kernel/.userland.git`（`userland/` 与 `tools/mesa/`，经 `common/ugit` 访问）。2026-10-28 连续两次因此出问题：内核源码的提交在 `out/xnu12377` 里、顶仓 `git log --all` 查不到，被当成提交丢失；`userland/src/redwoodmetal.m` 的改动在 `.userland.git` 里，`hackios-xnu-kernel` 的 `.gitignore` 是白名单、`userland/` 不在其中，`git add` 直接报 ignored。**改完先 `common/ugit status` 或 `git -C out/xnu12377 status` 看一眼**，`userland/` 的提交写成 `common/ugit add -f <路径>` 再 `common/ugit commit`。
- **行数一律来自 `tools/round-stats.py`**：任何报给团队的行数都写成 `python3 tools/round-stats.py <证据目录>` 的输出，报告里注明「唯一行」。原因不是形式：`s0xx.log` 是重叠快照，`cat s0*.log | grep -c` 会把同一行数三到四遍，2026-10-28 有一批数（`Code=4099` 的 172／92／156、宿主崩溃 12 条）因此虚高 3～4 倍，其中两组已经进了判据。这条规则本来就写在 `docs/analysis/2026-10-28-ios26-extension-host-exit-and-icon-cache.md:118`（跨快照求和能把同一份日志读出 1,516），做成工具之后不再靠人记得。工具在 `tools/` 顶层，不在 `tools/k90auto/` 的工作树状态记录范围内。**两套读取口径的文件集合不同**：`merged_log()` 比 `round-stats.py` 的 `read_lines()` 多读 `returned.log`／`hung-held.log`／`running.log` 一类快照之外的拉取，2026-10-28 `bbm29` 就因此多出一条 `tl: a` 心跳行，把 `tl:` 首末差从 330.4 秒推到 405.7 秒。**心跳行不携带环内容，覆盖与行数都用 `round-stats.py` 的口径**，两套数不一致时以它为准并写明差异来源。
- **「存在」与「生效」分开写**：探针的 `-1`／`0`／`>0` 与 `stat()` 的 0／1 只回答「目录能不能打开」「文件在不在」，不回答「谁读了它、读了之后系统行为变没变」。今晚两次为此返工：`bsd/conf/files` 里有那一行而文件编不进去；`var.skel` 改过而 `package.py` 只拷程序、骨架没变。判据要落到行为上：`libsystem_secinit` 有没有解析到容器、SpringBoard 有没有把图标排上去、某进程有没有真的起来。**写判据时用「文件存在 + 谁读了它」两句，不写一句「已生效」。**
- **报累计量前先按服务名分开**：`Code=4099` 这类行整轮原始条数会被最大的那个提供者决定。2026-10-28 的 `continuous` 轮是 189 条、`persona3` 轮 191 条（快照重叠已去重），只看总数像「没有变化」；按服务分开分别是 `com.apple.appprotectiond.read` 45→44、`com.apple.duetactivityscheduler` 25→26、`com.apple.coreduetd.context` **3→0**。**不去重的原始拼接会把这几个数放大三到四倍**：同一轮按原始日志串统计得到的是 172、74、9。注册 `com.apple.contextstored` 之后最后一项归零，这一条在总数里看不出来。判据写成「某个服务名的条数」，不写「4099 总数」。
- **改 `userland/build.sh` 里的骨架内容后必须重跑 `build.sh`**：`root/etc/var.skel` 由 `build.sh:632` 起逐行追加生成，`package.py` 只把 `BASE/root` 拷到产物、再放程序与 plist，不重建骨架。2026-10-28 的 `persona3` 轮就撞在这上面：`0ff060a` 往 `var.skel` 加了两行（`mobile/Library/MobileInstallation` 与 `mobile/Library/SpringBoard`），源码是对的，而产物与来源的 `root/etc/var.skel` mtime 都停在 Oct 26 23:08、里面两个串各 0 次，探针读到的 `mobileinstallation_dir=-1` 是打包没生效，与 `installd` 的行为无关。**判据是「产物里 `grep -c` 相关串非零」，源码改过不算。** 这与「`conf/files` 有那一行仍可能编不进去」是同一类：配置或模板写在一个地方，生效点在另一个地方。
- 内核不在这两项检查的覆盖范围内：`out/xnu12377` 长期带着未提交的 Apple 文件改动（`bsd_init.c`、`kern_exec.c`、`devfs_vfsops.c` 等）与未跟踪的移植源码（`bsd/dev/adreno8*.c` 一串），所以内核无法从仓库 HEAD 复现，这一节也不要求它。判读内核相关结论时以 `manifest.json` 里的 `kernel` 段哈希为唯一凭据，HEAD 号只说明用哪份源码起编。库这一侧相反：源码由 HEAD 号定，产物由打包侧的两个哈希定，两边各自成立。
- 核工作树状态不要用 `touch`：git 只看文件内容不看 mtime，`touch` 一个源文件之后 `status --short` 仍是空的，记录里会显示干净。要真的追加一行内容，它才会出现在 `worktree_status` 里。
- 一轮里除申请变量之外还有别的变化时（换库、换内核、换探针），用 `ROUND_NOTES="变化一;变化二"` 打包，它会写进 `manifest.json` 的 `round_notes`，归档读的是这个字段。
- 打包输出里的 `new_driver_sha256`／`new_air_sha256` 要记进这一轮。两轮之间驱动哈希不同时，性能与画面差异不能全算到申请里那个变量上：2026-10-28 03:48 的打包是 `f8c9042f`，04:00 从同一个工作树再打包是 `3d7ea90e`，中间只有 display 工作树里的改动，没有提交。
- 系统盘的传输成本实测是 **123 秒**，不是一小时：`stage-system.sh` 按 256 MiB 分 19 块上传（18 块各 6.7 秒、最后一块 2.3 秒，约 40 MB/s），`run/system-upload.log` 里每个 `stage` 的 `Total time` 相加即得。一轮的构成是 123 秒上传 + 420 秒跑 + 18 秒复位，约 9.4 分钟。
- 系统盘目前**无法跳过重传**，不是缺一个哈希判断的问题：`oem ramdisk begin <total> <window>` 会把 `resident_rd_size` 归零，而 `reboot-lk.py` 在收尾时要求 `ramdisk-state` 是 `idle 0 0 <window>`，也就是跑完一轮后 loader 手里没有任何常驻镜像。要跳过重传得让 loader 在跑完之后保留那块窗口并提供一个可比的摘要，这需要改 `xnuloader/loader_ramdisk.inc` 并重刷 loader；收益约 2 分钟一轮，不值得现在做。

## 4. 证据目录与固定收尾

一轮的目录固定为 `docs/progress/evidence/k90auto/kernel-12377-attr-<LABEL>/`（Git 忽略），里面 `manifest.json` 加 `run/`：`s###.log` 日志快照、`shot-#####.raw` 截图、`commands.jsonl`、`reboot.json`。每轮结束时固定执行：

```sh
python3 tools/k90auto/run-queue.sh docs/progress/evidence/k90auto/kernel-12377-attr-<LABEL>
python3 tools/k90auto/summary.py --verify docs/progress/evidence/k90auto/kernel-12377-attr-<LABEL>
python3 tools/k90auto/summary.py --markdown docs/progress/evidence/k90auto/kernel-12377-attr-<LABEL>
python3 tools/k90auto/gestures.py docs/progress/evidence/k90auto/kernel-12377-attr-<LABEL>/run
```

`summary.py` 与 `gestures.py` 由 perf 维护，我不改这两个文件。`--verify` 检查「每份快照里出现过的窗口行与帧行并集等于合并结果」且「合并结果无重复」。`--verify` 返回非 0 时本轮不计成功，我直接把 `--verify` 的原文输出回报给申请人和 lead，不贴任何帧率数字。

## 5. 回报什么

- `summary.py` 的整行表格（每轮一行）与 `gestures.py` 每个手势一行，原样贴，不做二次加工。
- 帧率三列分开写：`fps`（整轮）、`fps_mv`（活跃段）、`static`（静止段）。2026-10-28 之前的 `fps` 因合并缺陷失真，旧文档里的帧率数字不能与新口径混用。
- 三列都不能跨轮次比，能排序的只有手势口径。`fps` 的分母含静止期：s23 那几轮窗口多、`static` 77%～81%，`fps` 只有 15 上下，和 iOS 26 的 25.9～47.7 直接比会得出相反的结论。`fps_mv` 排除了不小于 90 ms 的空档，只剩「动的时候有多快」，静止期越多越好看：s23 的 `fps_mv` 44～49 低于 iOS 26 的 56～59，这个对比定不了 s23 的快慢。排轮次、判验收都用 `gestures.py` 的手势口径。
- `gestures.py` 在每个手势那一行之后多给一行逐次下拉的判据：每次下拉的帧率、`至少 55` 与 `至少 60` 各几次、窗口内最长间隔，以及对照 target 的 `pass`／`fail`。加 `--each` 再给出每次下拉用了多少帧、窗口多长、几个不小于 90 ms 的空档。
- `reboot.json` 里 `left`、`reset`、`seconds`、`mode` 四个字段，用来判断收尾走的是哪条路。
- 申请里指定的日志行（例如 `rwa bind:`、`command buffers:`、`copy` 计数）按原样贴，标明是哪份快照。
- `--verify` 只证明「合并结果与各快照的并集一致」，它不证明「合并结果覆盖了整轮」。两者不一致时它会失败（合并漏行、重复段），但所有快照都缺同一段时间时它会通过——例如日志环被写满后，每份快照都只装最后一截，并集与合并互相一致，前一段永远不在任何快照里。判断覆盖要另看三个数：合并后最早与最晚的 `tl:` 时间戳（相减就是覆盖跨度）、本次轮次的起止时刻、以及 `帧数 ÷ 覆盖跨度` 是否与实测帧率相符。跨度为 330 秒而轮次是 420 秒、或帧数与跨度算出来的速率与 summary 差得远，都说明有整段缺失，此时按时间排序的结论（与快照对齐、与手势对齐、掉槽分布）只在那一段内成立。
- 每轮的 `--verify` 会打一行 `registration:`：合并日志里出现 `memorystatus_perform_idle_demotion() timed out stuck process` 且被判进程属于 `pkd`／`extensionkitservice`／`iconservicesagent` 时，标注为「登记链路劣化」，该轮的帧率数字只作参考。单独一行 `stuck` 不构成异常（`AudioConverterService` 被判过卡的那一轮桌面完全正常），判据是这一批进程，以及它与最后一个合成帧的先后关系。
- **旧证据目录不能再用 `run-auto.py` 重跑。** 原因是有意设计：`GUARD` 核对的是「payload 目录里的 manifest 与盘上文件是否仍然一致」，而打包每次都会重建 `root.apfs`，旧目录指向的那个文件早已不是它记录的版本，于是重跑一律拒跑。这不是缺陷；要重跑某一轮，重建那个载荷并更新它的 manifest，不要绕过核对。
- `run-auto.py` 跑轮开始前核对载荷：它按 `manifest.json` 重新算 payload 与打包根的 sha256，与记录不一致就拒跑；`EXPECT_PAYLOAD_SHA256`／`EXPECT_ROOT_SHA256` 给了值而与之不符也拒跑，并在运行日志第一行打 `GUARD payload=<前 16 位> root=<前 16 位> dir=<目录名>`。这条覆盖的是 2026-10-28 的一次真实故障：`make-payload.py` 因目标目录已存在而失败，`run-queue.sh` 仍按那个目录开始一轮，跑的是上一版载荷（`rc.jobs.desktop`）。打包失败而流程继续，与启动参数静默丢失、驱动静默更换是同一类。
- 跑轮期间有成员动仓库时，下一轮开始前核两项（lead 10-28 定，round F 开始一轮时的实测样板）：构建树 `out/xnu12377` 的 mtime 未变（round F 核值 1792995674）、内核 sha 与本轮期望逐位一致（round F 核值 `cf1502f5…`）。这两项把「跑轮期间往仓库落文件不影响本轮」从推断变成实测。
- 中途 kill 一轮时，必须确认 python 子进程已死，并手动 teardown 到 fresh idle 三项验证（10-28 定，round F abort1 的教训）：那次 `job_kill` 杀掉 QUEUE 后 python 子进程又活了约 4 分钟，坏 payload 实际 boot、内核无人监督运行约 31 分钟，直到手动 `oem stop`（41 s 后 hung-held）；teardown 补存证三份（loader-held.log、hung-held.log、hung-held-serial.log），fresh idle 的验证判据是 result idle 加 ramdisk-state idle 0 0 0。开始前断言只拒不修：`run-auto.py` 遇到 loader not fresh idle 会正确拒绝开始，恢复动作由人做，断言不自己修状态。
- **开始一轮之前必须核设备不在 `hung-held`，并核 `fresh_loader()` 那个合取条件**（lead 10-28 晚定，fixguard 启动失败后更正的口径）。机制（一般性质，不是本轮特例）：任何 panic 都会走到交还 loader 的路径（`osfmk/arm64/loader_return.c:416` 在交还路上调 `adreno8_quiesce()`），而 `xnu/files/bsd/dev/adreno8.c:470-483` 的 `adreno8_quiesce()` 在 `:475` 那个条件（`adreno8_reset_required || adreno8_memory_retained()`）为真时进了 `:480-482` 的 `for (;;) { __asm__ volatile ("wfe"); }` 就不返回——**所以一次 panic 之后设备必然停在 `hung-held` 并需要主机冷复位**；`hung-held` 是 panic 的必然后果，不是设备遗留状态。`:477-479` 把 `adreno8: GPU probe requires host cold reset before reusing kernel memory` 逐字符经 `loader_log_putc()` 写出，走 loader 的日志通道而不是内核 printf 的环形缓冲，所以它排在环形缓冲输出之后是预期内的；声明处 `bsd/sys/redwood_audio.h:72` 的注释写着「at the run's end and on a panic's way out」。这一个机制同时解释三件今天各自被当成独立问题追过的事：`hung-held` 的来历、失败时刻那 50.85 与 50.68 秒为什么不是随机的（loader 数满自己的 50 秒，`run-auto.py:71` 与 `:176` 写明的就是这个机制）、以及为什么必须做主机冷复位。合取条件：`run-auto.py:100-103` 的 `fresh_loader()` 要求 `result == idle` 且 `ramdisk-state` 匹配 `idle 0 0 `，而 `:127` 的开始断言只看 `result`——两处口径不同，round F 收尾那三项验证要按合取重核。实测教训：fixguard 轮 `QUEUE start 21:07:44` 开始断言通过（**开始一轮时设备状态是干净的**），`hung-held` 是 loader 在内核静默满 50 秒后的字面应答（display 核清：`state()` `:94-97` 只读 `getvar result` 一个量、`:152-158` 在不等于 `running` 时打印它），`run-auto.py` 在打印 `NOT_RUNNING` 之前采样了 50.85 秒——那段时间没有白花：它就是 loader 等内核静默满 50 秒的那一段，`NOT_RUNNING` 是它结束时打的；内核静默期间没有输出，这一段由 loader 的 50 秒超时负责，存活检查的 150 秒阈值看不到它。失败原因未定，三件待查项在 [fixguard 归档说明](../progress/2026-10-28-fixguard-archive.md)。
- **两种失败的分工**（lead 10-28 晚定）：执行体消失而内核继续跑，由 `liveness-watch.sh` 负责（阈值 150 秒停滞；round F 第二次异常那类）；内核静默而 loader 在 50 秒后报状态，由 `run-auto.py` 自己负责，存活检查看不到它（50 秒小于 150 秒）。fixguard 实测：21:05:35 起每 30 秒一拍、21:08:05 起报 age，`QUEUE stop` 在 21:09 就写了，21:12:35 在停滞 159 秒时落 `LIVENESS-ALERT`，告警比失败晚约 3 分钟——对快速失败这一类，告警不产生额外信息。
- 打包产物里的 `etc/var.skel` 来自基础根（`out/.../on/root`），而基础根要跑 `userland/build.sh` 才会更新。**改了 `build.sh` 里往骨架追加的行，不重跑 `build.sh` 就不会进载荷。** 2026-10-28 的 `persona3` 轮就是这样：程序是新的、`etc/var.skel` 还是 10-26 的，`mobileinstallation_dir=-1` 说明目录没进载荷。现在这些行写在 `userland/var.skel.extra`，`build.sh` 追加它，`package.py` 打包时检查并补上基础根缺的行，补了就打印一行并把行数记进 manifest 的 `skeleton_appended`。看到那行打印说明基础根过期，应当重跑 `build.sh`。
- 每轮打包前把 pack 记录里的全部字段与本轮配方逐字段对一遍，凡是不设的开关要写出「不设」的依据（lead 10-28 定的常设步骤，device 查法，round F abort1 的教训）：`package.py` 共 15 个环境开关，漏一个开关不会报错，它只会让镜像多一个或少一个文件。样板：从 roundb 的 pack 记录反推出 `PROBE=1 VARSTORE_SHOW=1 JOBS_DROP="com.apple.appprotectiond.plist" GPU_SPEED=3 JOBS_SOURCE=<本轮 jobs 文件> ROUND_NOTES=<本轮说明>`，MSAA、REDWOOD_DIAG、`EXPECT_*`、`ALLOW_*` 均不设，依据是 roundb 记录 msaa None、redwood_diag false。漏设 `JOBS_DROP` 的实际代价（round F abort1）：`jobs_effective` 37 对 36，新镜像多了 `/LaunchDaemons/com.apple.appprotectiond.plist`、launchd 缓存随之不同（0607c615→ce9d6b08），超出「只改 jobs」的变量边界。配方对账写成两层（lead 10-28 定）：第一层是上述字段逐项对；第二层是把 pack 记录 `changes` 里每个 `null→sha` 的 added 条目逐个归到一个通道（`EXTRA_JOBS`／`PROBE`／`PAYLOAD_PROGRAMS`），归不到通道的就是配方缺口——第二层能抓到第一层抓不到的东西，因为 added 条目是镜像的实际内容、字段是配方的声明，`PAYLOAD_PROGRAMS` 正是失效在两层之间（pack 记录里没有它的专门字段，见 device `3278bf9`）。反推 roundb 完整配方时按第二层补上 `PAYLOAD_PROGRAMS`（含 framewatch），历轮 framewatch 都经此通道进镜像。
- 打包时把新镜像对已知良好的备份镜像做全条目 diff（lead 10-28 定的固定检查，round F abort1 恢复方案第③步升级）：预期差异恰好列出（round F 恢复轮预期只有 `/etc/rc.jobs` 与 `/xpc/launchd.plist`）、条目数两边相等（136=136）、关键条目两边都在（`framewatch`）、两边都不在（`appprotectiond`），多一处就停。它补的是 `package.py` 现有闸的盲区：现有闸只比 `driver_sha256` 与 `air_sha256` 加 `dirty_sources()` 那两处，从不比 staging 树的条目集合，于是 base root 的哈希对上、驱动与 AIR 的哈希对上，而 `/bin` 里少了一个文件（`framewatch`，配方漏设 `PAYLOAD_PROGRAMS`；且 `:525`／`:527` 两个断言以 base 镜像为参照、framewatch 从来不在 base 镜像里，通道一掉 before 与 after 都没有它），闸全过——**闸能看见什么由它的参照物决定：以固定基线为参照的闸，查不出「本来就不在基线里的东西消失了」**，所以 `image-diff.py` 拿上一轮实际跑过的镜像作参照；两闸分工并列记：`package.py:526` 的断言管多出来的文件，`image-diff.py`（device `e7955f5`，根因更正 `3278bf9`）管少掉的文件，只有 `:526` 不够。配方对账防止漏设，条目 diff 防止漏设的后果进镜像，两个步骤互为兜底。条目 diff 比 mode，不比时间戳与属主：`tools/apfs/mkapfs.py:908` 把镜像里每个时间戳强制成 `--time`（默认 1683900000）、`:118` 强制 uid=gid=0、`:126-135` 只有 mode 取宿主机值。这道闸的依据（lead 10-28 定，原样）：「这一轮会看起来活着地跑完 420 s，收尾才发现全部采样为零。」缺文件不会让轮次失败，只会让轮次产出一份全零的数据，而全零的数据在收尾之前看不出异常。

**源与产物之间的四处缝**（`GUARD` 只管「打包之后被换」，这四处是「源改了、产物没跟上」，各有各的判法）：

| 缝 | 怎么判断它过期 |
|---|---|
| `build.sh` 追加的骨架行 | `package.py` 拿 `userland/var.skel.extra` 与打包根的 `etc/var.skel` 比对，缺行会打印 `... rerun userland/build.sh to rebuild the base root`；manifest 的 `skeleton_appended` 非空就说明基础根旧了。产物里缺 `MobileInstallation` 或 `SpringBoard` 时打包直接失败。 |
| 内核子树 | `make-payload.py` 用 `kernel.json` 记录的 sha256 核对实际内核文件，不一致就断言失败；内核改了却没重新记录，装不出载荷。 |
| AIR 副本 | `package.py` 把 `libredwoodair.dylib` 与 `out/ios26-resume/mesa-arm64e/air-build-record.json` 的 `library_sha256` 比对，不一致断言失败并提示跑 `build-air.py`；`PAYLOAD_AIR_STRINGS` 里的格式串在库里找不到也失败。 |
| plist 拷贝 | `tools/k90auto/jobs/*.plist` 是 Apple 原件的副本。**今天没有自动判据**：要手工与 `ios26/rootfs/System/Library/LaunchDaemons/` 下的原件比对 sha256。没有自动判据的原因是这个副本本来就要被 `add_extra_jobs` 改写（`RunAtLoad`、`UserName`），改写后的产物不能与原件比较，只能比较「进入改写前的输入」。 |

- **归档里查不到脚本时，用 `tl: p` 的按下事件起点坐标去认脚本。** 每条 `swipe`／`drag` 行有一个起点 `(x, y)`，日志里 `tl: p 1 …` 的第三、四个字段就是它。2026-10-28 用这个方法认出 `airindex` 轮跑的是 `rc.jobs.continuous`（起点 `y=0.985` 与 `y=0.55`）、`gestures` 轮跑的是已删除的 `rc.jobs.gestures`（有 HOME 键事件、手势 0.42 秒）。**认出之后在两轮 manifest 里补 `jobs_source_reconstructed`，写清依据并标 `post_hoc: true`**：事后认定与打包时记录是两件事，不能混写。
- **每一轮归档要能回答「这一轮跑的是什么」。** 六项：内核、驱动、AIR 库、作业集合、手势脚本、探针版本。`pack` 里对应 `kernel`、`driver_sha256`、`air_sha256` 与 `air_sources`、`jobs_effective` 与 `jobs_dropped`、`jobs_source`（路径、`sha256`、是否显式指定 `JOBS_SOURCE`）、`probe_sources`。**加载荷里有什么能查到，「载荷怎么生成的」查不到，这个缺口出现过两次**：`air_to_nir.c` 不在复制清单里、`airindex` 轮没有 `air_sources`；两轮 3550 帧与 17 帧的差别只在手势脚本，而两轮 manifest 都没记脚本名。
- **打印节流后的条数不能当事件数。** `tl: p` 走 `RW_AGAIN`，只在第 1、2、4、8…… 次调用时打印，所以一次 30 秒拖动（约 3750 个样本）在日志里只有约 12 行；`served as a copy` 的打印次数同样不是调用次数。要事件数就用工具侧的计数，不要用日志行数。
- **截图读数要写清「整轮」还是「某个窗口」。** 2026-10-28 `gestures` 轮 94 张截图的 sha256 只有 1 个（整轮逐字节相同），而当时转述的「39 张相同」是某个窗口的数。今晚已有两次把局部窗口当整轮（探针 0 条、`tl: p` 0 条）。
- **跨快照计数必须先去重，报数时写出用的是哪一列。** 2026-10-28 我在给 display 的消息里报了 `tl: p` 各类型的条数（`1=76 2=3849 3=75 4=19 5=19`），那是把重叠的 `s0xx.log` 快照直接相加，去重后是 `1=8 2=426 3=8 4=1 5=1`，偏高约九倍。同一轮 `round-stats.py` 先按整行去重再计数。**数字出口前先问一句「这是唯一行还是快照和」。**
- **每轮必跑 `round-stats.py` 的三段固定输出**：`fence timeouts`、`ring coverage`、`swap holes`。**零命中要附环覆盖率才可作排除依据，并写明是并集口径还是单份口径**：日志区是 263,349 字节的头加 1,048,576 字节的环（§6），写满之后只保留最近的约 1.31 MB，覆盖不到的时段里，「没出现」不能作为「没发生」的证据。**单份快照与并集差 2.2 倍**（`freeze` 轮单份约 178 秒、并集 398 秒），两个数不能互相代替。**三个数一律以 `round-stats.py` 的 `ring coverage` 段为准**（行数、跨度、单份环可容纳的日志时长），自己另算一套会与别人对不上。判据两条，**互相独立、都满足才算可采信**：第一条是单份环可容纳的日志时长要大于快照间隔（约 20 秒），防「两份快照之间掉过行」；第二条是并集要覆盖该轮空洞时刻，防「空洞落在采集之外」，且按 `swap holes` 的 `tl:` 基线逐点对齐，墙钟不能直接相减。九轮 `did not finish the` 零命中两条例都满足，`perf1` 仍标弱证据，差在密度，逐轮数字见[差距分析第 2.23 节](../analysis/2026-10-28-ios26-perf-gap.md)。
- **轮次目录在 device 宣布收尾之前不读；读了必须标 partial 与截至的快照号。** 2026-10-28 的实例：perf 在 roundb 还在跑的时候读目录，得出「0 触摸、0 截图、45 帧」并据此判「两轮都不能判」，与收尾后的数（36 条触摸、85 张截图、99 条提交）冲突。**未收尾的读数只能说明「到第几个快照为止如此」**，写法是 `partial, through s0NN`。
- **`run-*.log` 只有 GUARD／RUN_STARTED／SAMPLED_SECONDS 三行是正常的**：采样循环的输出在别处，行数不能当进度。**判断一轮是否跑完看 `SAMPLED_SECONDS` 行存在且秒数约等于 `RUN_SECONDS`**，不看 run log 行数。
- **manifest 记的是「应该跑什么」，apfs 记的是「实际跑了什么」。核对象是 apfs 里解出的文件。** 2026-10-28 device 在一轮作废的 round A 上实测：manifest 的 `new_driver_sha256` 是新的，而 apfs 里的 `lsprobe` 是旧的。两者不一致时以 apfs 为准，并把差异写进那一轮的说明。
- **拼接字符串时要检查行边界。** 2026-10-28 `rc.jobs.perf` 追加手势行时上一行没有换行符，最后一行被拼成 `wait 10/redwood/bin/rwtouch …`，脚本时长校验当场报错。属「改了但没生效」的同类：写进去的东西没有按预期成为一行，靠校验才发现。
- **「改了但没生效」这一类每次都要记下实例。** 2026-10-28 又添两例，都在同一天：`package.py` 的 `add_diag` 只改内存缓存、没写回 `xpc/launchd.plist`，job plist 有 `REDWOOD_DIAG`、打包后的缓存没有；`job` 变量取自 `add_switch`，`add_diag` 重写了盘上那份之后没有重读，校验比的是旧对象。前四例是 `lsprobe.m` 改了但基础根没重建、`conf/files` 有行编不进去、`var.skel` 改了没进载荷、内核提交落在另一个仓。共同点：改动落在某一处，判定却读另一处；所以任何「改了」都要跟一个「从产物读回来」的验证。

第五例更隐蔽，单独写：`tools/k90auto/build-air.py` 只把 `air_metal.c` 与 `air_metal.h` 复制进构建树，`air_to_nir.c` 不在清单里，于是**只改 `tools/mesa/air/` 不会进构建，构建读到树里旧副本，而且不报错**。前四例至少产物与源会不一致，这一例是源与产物都自洽、只是产物来自另一份源。判法：**复制清单本身也要有断言**——现已加「`tools/mesa/air` 下任何 `.c/.h/.inc/.metal` 与构建树不一致即失败并列出文件名」，不能只断言清单内的文件一致。
- **凡以 0 作否定的结论，必须写明统计覆盖的时段。** 局部快照的 0 只能说「截至那一刻没有」，不能说「整轮没有」。2026-10-28 这一类出现过四次：探针 `0` 条、`tl: p` `0` 条、`died on signal` `0` 条、`crash_files` `0`。其中 `tl: p` 那次是 150 秒的 6 份快照读到 0，被转述成整轮 0，而整轮按行去重是 349 行。写结论时把口径写成「截至 t=150 没有」或「整轮唯一行 349」，不要写「没有」。
- **新增的日志行在它被编进去之前，缺席不构成证据。** 2026-10-28：`crashed:`／`Too many corpses`／`died on signal`／`corpse refused` 在 `persona4` 轮全为 0，而内核还没有 display 新加的三行，所以「三行没打」只能说明旧日志没出现。判据顺序是先立「有进程死亡」（看旧的两条），再用新的行分死因；反过来会把空结果当结论。这与「判据要靠产物内容、不靠源码改过」是同一类。
- `JOBS_DROP` 是**一轮之内临时排除，不是长期配置**：它的用途是让一轮只带一个作业变量，用过的轮次必须在归档说明里提到它，且 manifest 的 `pack.jobs_dropped` 非空。看「这一轮到底带了哪些作业」只读 `pack.jobs_effective`（从 launchd 缓存的键读回来的完整名单，`jobs_effective_count` 是条数），不要靠把 `EXTRA_JOBS`、`ON_DEMAND_JOBS`、`JOBS_DROP` 三个开关在脑子里过一遍。
- 轮次归档看 `pack` 段：`make-payload.py` 把打包产物 manifest 的关键字段抄进证据 manifest，字段是 `probe`、`varstore_show`、`skeleton_appended`、`gpu_speed`、`round_notes`、`driver_sha256`、`air_sha256`、`expected_driver_sha256`、`expected_air_sha256`、`jobs_sha256`、`root_sha256`、`root_bytes`、`library_change_accepted`、`dirty_worktree`、`jobs_dropped`、`jobs_effective`、`jobs_effective_count`。抄的时候核对两条：`root_sha256` 必须等于被打包根文件的哈希，`gpu_speed` 必须与 cmdline 里的 `adreno8_speed` 一致。
- **库的身份记源码摘要，不记库的 sha。** `libredwoodair.dylib` 的 sha256 只证明「这台机器这一次建出来的字节」：2026-10-28 同一套补丁、`mk-mesa.sh` 不带 `--batch` 建出 `a9d028a1…`、带上 `--batch` 建出 `86f379dc…`，两者都对，差异来自 patch 的失败处理方式，从库的 sha 上看不出原因。源码摘要按补丁打好之后的树算：`cd mesa-$VERSION && find src \( -name '*.c' -o -name '*.cc' -o -name '*.h' \) | LC_ALL=C sort | xargs cat | shasum -a 256`，`86f379dc` 那一版的树是 `be696abdc09d3f309920cdd763a275aebde2d329fede91b630e0bdb1f29cf8e2`。摘要的覆盖范围是 `src` 下的 `.c`／`.cc`／`.h`／`meson.build`／`meson_options.txt`（2026-10-28 起把后两类算进来：构建配置由它们决定，不含它们时摘要可以先相同而库不同）。取法固定为 `find src \( … \) -print0 | LC_ALL=C sort -z | xargs -0 cat | shasum -a 256`：不排序则顺序随文件系统而变，`xargs cat` 不带 `-0` 则在文件多时分批，两者都会让摘要本身不稳；**不含 `meson.build` 与 `meson_options.txt`**，所以摘要相同不能证明构建输入相同；树里存在两处 `meson.build.rej` 就是这个缺口的具体形态。每轮的 `manifest.json` 同时记源码摘要、库 sha 与 `out/patch.log`。

库 sha 本身在同一棵树上重链是可复现的：2026-10-28 删掉 `libredwoodair.dylib` 再 `ninja` + `llvm-strip`，两次都是 `8c90b8de6b7b24db…`。所以库 sha 相同能说明是同一份产物，不同则说明构建输入里有摘要没覆盖到的东西，不值得当成「签名随机」放过。
- **判某段代码在不在树里，只看符号存在与否，不看出现次数。** 两条补丁带同一块时树里会出现两次，被拒绝的那一块不生效，所以次数既证明不了应用次数，也证明不了代码被写了两遍。`.rej` 只说明「某条补丁的某块没打上」，那块提供的能力可能由另一条补丁提供。2026-10-28 的实例：`fd6_draw.cc` 的 `prev_draw_read_fb` 在 `freedreno-darwin.patch` 与 `rebase-26/0003-restore-osmesa-26.x-drift-adaptations.patch` 里都有，树里出现两次，而在重新解包、从头打过的干净树上仍然是两次。
- **说明性文字写进文档，不写进补丁头。** `tools/mesa/*.patch` 的正文参与 `.redwood-patches` 的哈希，改一行注释就会让下一次 `mk-mesa.sh` 重新解包、重打整条链、重编整个库，而应用结果一个字都不变。2026-10-28 因此把「`ir3-shift-split.patch` 对 26.x 不适用、块 1 是死代码」记进 `docs/plan/2026-10-28-widget-stall-control-round.md` 的补丁表，没有改动补丁文件；要改补丁时与本来就动补丁链的那一轮一起改。
- **符号化 pc 走 stub 的系统调用号，不按偏移猜名字。** `libsystem_kernel` 里的 stub 是 `mov x16,#imm` 加一条 `svc`，取那个立即数查内核的 `mach_trap_table` 与 `syscalls.master` 就得到系统调用名；`0xffffffff` 的 slide 表示该任务没有设置过，此时 `pc` 不可读。2026-10-28 用这个方法读出的六个主导 `pc` 全是普通阻塞调用（`mach_msg2_trap`、`workq_kernreturn`、`semaphore_wait_trap`、`psynch_cvwait`、`__semwait_signal`、`ulock_wait`），没有一条落在 CoreAnimation 或 `backboardd` 的提交路径上。这套方法应落成工具（输入 slide 与 pc 列表、输出镜像与函数名或系统调用名），每轮的 dump 才能直接读。已落成：`tools/k90auto/stubsym.py`（2026-10-28，`e566027`，sha256 `01fc7148f7a9ea0bd223a641841ed5263ba2aa825cb11e8d3ba8c8f655a5da6a`），纯参数加 stdin/stdout、不依赖轮次目录布局、可被用例调用；解码步骤与 `.46` 子缓存 mapping 表定位文件偏移的办法记在 docstring。
- **「窗口内命中数」没有基率对照时没有信息量。** 告警与事件流常有高基率：`commit has run for` 由少数长期运行的 commit 反复打印，`biomed` 的 commit 4101 一轮打了 236 次、最大值 171,184 ms，全流约 3 条/秒，任何 3 秒窗口必然命中。2026-10-28 按「空洞起点 ±1.5 秒内有 ≥2000 ms 告警」筛出 65～325 条，差一点被读成「空洞是一次 commit 卡住 3 秒」，实际那些空洞内告警为 0。判据要写成「洞内命中数与洞外同样长窗口的命中数之比」，或「洞内是否出现洞外没有的取值」；只报命中条数不报基率的结论不成立。
- **轮次目录在 device 宣布收尾之前不读，读了要标「partial」。** 快照是轮次进行中陆续拉取并汇总的，读一个未收尾的目录会把「还没到」读成「没有」。2026-10-28 我在 roundb 未收尾时读到 45 帧、0 条 `tl: p`、0 张截图，据此判「本轮没跑到手势脚本」，而收尾后的完整目录是 99 次交换交接（971.0～1235.9 秒）、36 条 `tl: p`（1060.3～1070.8 秒）、94 张截图。判据建在部分数据上时，先写「截至第 N 份快照」，再给结论。
- **比两轮的 `nil buffer` 条数之前，先证明两轮停在同一界面。** 界面状态读 `python3 tools/round-stats.py <证据目录>` 的 `screens` 段：它按亮样本比例分档（`<0.005` 黑、`>0.10` 主屏、其余锁屏），并给出 `order: home screen x94` 这类游程，比看截图可靠，也让「界面一致」这个前提本身可复核。要求是**同一界面**，不是「都不是黑屏」：`perf1` 的 109 条 16 KiB 大多带 `w:256 h:1 bpr:2048`，是线性纹理形状，换个界面就会改变这种绘制的次数，与改动无关。
- 补服务、补目录、补记录这类改动的验收只看效果，不看 `memorystatus_perform_idle_demotion() timed out stuck process` 是否消失。2026-10-28 的统计：58 个证据目录里被判卡的只有五个名字，而当时最干净的一轮（11,015 帧、无停帧）这五个里出现了三个，所以 stuck 是背景状态，不区分好轮坏轮。验收项写具体读数：`mobilelibrary=` 里出现某目录、`containers_entries=` 非 0、某个服务的 `Code=4099` 归零。
- 缩短轮次不能代替修复。验收轮本身就是 420 秒（32 秒解锁加 8 轮下拉与翻页），把轮次压到 300 秒只是把劣化推后：用户手上的机器跑十几分钟仍会遇到。轮次时长属于验收口径，不随故障调整。
- 任何性能结论先过 `coverage` 行。跨度不足轮次时长的一半时，只允许报「该跨度内的局部值」并写明跨度，不得报「本轮 fps」；手势同理，识别到的手势少于注入次数时报「样本不足」。bbm29 就是这样一轮：`fps 47.4 / fps_mv 59.5 / static 21%` 只覆盖 141 秒、最大空档 18.3 秒、8 次下拉里 1 次可测，所以这三个数都不是「本轮」的数。
- 读任何一轮的帧率与手势数字之前，先看 `--verify` 的 `coverage:` 行：它给出合并日志里最早与最晚的 `tl:` 时间戳、跨度、以及相邻 `tl:` 行之间最大的空档。`--verify` 通过只说明合并与快照并集一致，跨度与空档说明这份日志覆盖了哪一段；空档远超快照间隔时，按时间排序的结论（与快照对齐、与手势对齐、掉槽分布）只在那一段内成立。`gestures.py` 的 `coverage:` 行同时给出识别到的触摸次数与其中 Control Center 下拉的次数：识别到的手势少于注入次数时，结论只能是「样本不足」，不能报「失败」，也不能拿剩下那几次去谈「每次下拉」。
- 打包前必须比对 AIR 源与构建树副本的哈希：`tools/mesa/air/*.c` 与 `out/ios26-resume/mesa-arm64e/mesa-26.2.5/src/compiler/air/*.c` 不一致时先同步（或直接失败并要求同步），并在 `manifest.json` 里同时记下 AIR 源哈希与 `libredwoodair.dylib` 的哈希。arm64e 构建只读构建树里那份副本，`tools/mesa/air/` 的改动不同步过去就不会被编。库是否合格要在打包时对库文件做静态检查，不要靠跑完一轮在日志里找字段：`rwa draw_vbo:` 与 `clock pair adds` 只在开机后打一次，而日志环只留最近约二十秒，它们进不了证据；`perf flush totals` 每 1024 次 flush 才打一行，帧数不到 1024 的轮次天然没有。判据按可用性分级：库文件里必须同时存在 `calls %llu in`、`clock pair adds`、`batch cuts`、`verts %llu`、`perf flush totals`、`resolve %llu`；日志里 `calls in` 与 `batch cuts` 必须出现，`perf flush totals` 在帧数达到 1024 时才要求出现，否则记 `n/a`。
- 报「某个字段、某行或某项数据缺失」时，必须附上实际用的匹配串与匹配位置（行首还是行中）。v6 那次把 `calls N in` 当成缺失，真实原因是检查写成 `l.startswith('calls ')`，而该字段在 `perf flush` 行中间：「缺失」与「匹配写错」在报告里必须一眼可分。
- 同一个错法的第二个实例：2026-10-28 有人数 `installd[` 得 0 次，据此判「`installd` 从来没跑过」，而判卡那条日志写的是 `[installd]`，方括号方向相反。实际它每轮都被拉起，只是被判卡。**报「某物不存在」时写清匹配串的全貌与它的位置**，`进程名[` 与 `[进程名]` 是两个不同的串，前者只匹配日志前缀，后者匹配内核的方括号形式。
- 任何按行计数的结论都要说明统计口径：单份快照、跨快照求和、还是 `merged_log()` 合并去重。跨快照求和会因日志环重叠把同一行重复计入，只能用于「有没有出现过」这类定性判断；要比较两轮的量，必须用合并去重后的行数。`grep -c` 对 21 份快照逐个求和曾把 `CMPhotoCompressionSessionAddImage` 数成 1,516 行，合并去重后是 86 行。
- 报次数要说明是「行数」还是「同一个串在行内的出现次数」，这与「唯一行 vs 跨快照求和」是两个独立的口径问题。同一行里可能列多个服务名，`com.apple.linkd.registry` 的行数是 412、串出现次数是 824。复算过：含这个名字的唯一行 413 行（多出的一行没有 `service named` 前缀），这些行内该名字共出现 826 次，约为每行两次，所以 824 这个数是串出现次数，不是行数。
- **默认口径定死：报任何按行计数的结论，默认报 `merged_log()` 合并去重后的唯一行数；需要比较量级时同时给 raw（跨快照求和）并在同一句里写明两个数各自是什么。** 「串出现次数」只在确有必要时使用，且必须写明「串出现次数」四个字。三种口径混用是 2026-10-28 当晚三次报错数的共同原因，读的人不应需要猜。
- **对 `docs/` 的递归检索必须限定范围**：`grep -rn` 要带 `--include='*.md'`，或显式排除 `docs/progress/evidence/` 与 `.git`；优先用 `rg`，它默认吃 `.gitignore`，被忽略的目录不进扫描范围，内存有界。`| head -N` 不构成内存保护：匹配数不足 N 时 head 一直在等，grep 不会被 SIGPIPE 提前终止，要限量用 `rg -m N` 或先缩小路径范围。理由：`docs/progress/evidence/` 被 Git 忽略，存的是轮次快照的原始日志、二进制回读与 git pack，单文件可达数百 MB 且几乎无换行（实测最大无换行区间约 408 MB）。2026-10-28 事故：`grep -rn '35 ms 的帧\|不超过 9 个' docs/ 2>/dev/null | head -5` 第二段没带 `--include`，递归扫了 evidence 目录，内存吃到 186 GB、任务被取消。这处事故有一点未解：按 BSD grep 的 3 倍开销，408 MB 只到 1.2 GB 量级，解释不了 186 GB，grep 内部哪块分配在涨要采样才能定论，这里不给机制。
- 检索安全的两组实测数，供判断哪些搜索是安全的：BSD grep 的内存开销约等于最长无换行段的 3 倍（64 MiB 全无换行文件峰值 RSS 71 MB；同样 64 MiB 切成 64 字节一行只有 1.9 MB；1 MiB 单行 2.9 MB；2 MiB 单行 6.1 MB），所以一个文件能不能 `grep -a` 取决于它最长的无换行段，不取决于文件总大小；多 GB 二进制（`userland/system26.apfs` 4.9 GB、`out/` 下的 `root.apfs`、`hackios-xnu-kernel/ios26/23G90__iPhone18,3/` 的共享缓存 85 个文件 4.9 GB）一律先 `strings` 或用 python 流式 `bytes.find`。带上下文窗口的正则在二进制上是 CPU 问题：`grep -a -o -E '.{0,30}<串>.{0,30}'` 在 14 MB 的 `libredwoodair.dylib` 上耗时 6.31 秒、1,307 亿条指令，同样的搜索用 `-F` 是 0.08 秒，差 79 倍；峰值内存 2.9 MB 对 2.4 MB。取偏移用 `grep -a -b -o -F`，取上下文用 `dd if=<file> bs=1 skip=<偏移-40> count=120 | strings`。
- 两个现象时刻重合时只能得出「同时出现」，不能得出因果。要判因果必须有一个能单独移除其中一个的对照，例如 `linkd.registry` 报错归零之后 15 秒周期是否仍在。三次反面例子：`draw` 与 `pipe->draw_vbo` 相减归给 clear、字段缺失判成旧库、`linkd` 与空档重合判成因果。
- `cpufreq:` 有两类行：`in 30 s:` 是整段三十秒窗口的直方图，`hot ticks N of 593 …` 是热 tick 时段内的另一份直方图。两者在同一轮里交织出现，取数必须说明是哪一类，且必须按 domain 分开后再读。
- 帧间隔落在 16.67 毫秒的整数倍上（33.3、50.0）说明是刷新率分频，不是计算变慢；`24 fps` 这种平均值不能区分两者，判据要看间隔分布。
- `tl: p` 的字段是 `tl: p TYPE FINGER X Y at US`：`$3` 是 TYPE（1 按下、2 移动、3 抬起），`$4` 是 FINGER（单指恒为 0），`$5` 是 X、`$6` 是 Y，坐标是 0～65535 的归一化值。把 FINGER 当成 TYPE 会得出「日志里没有 TYPE」的错误结论。
- `tl: p` 有打印节流（`RW_AGAIN`），所以「唯一行」数小于实际采样数。报触摸事件数时写「唯一行」并注明节流。
- 判一轮有没有出帧，用 `tl: v` 的帧号与 `tl: s`（每次 swap 交接）两条一起看，不看 `ready` 的相邻时间间隔。同一批帧的 `ready` 可以挤在很窄的区间里，用它算间隔会得出「五十九秒空档」这类误导性的数。 实例（`kernel-12377-attr26-continuous`）：帧号 7852 的 `ready` 是 1581.0 秒、7853 是 1640.3 秒，`tl: s` 同样是 7852→7853，所以这 59.3 秒里一帧都没有；而 `ready` 落在 1580.3～1581.0 的 7831..7852 共 22 帧属于空档之前那一批，按 `ready` 求间隔会把这 22 帧算进空档。
- 报累计量（`X us waiting… in all`、`N buffers unmapped in M ms` 这类）之前先除以次数、再算它占墙上时间的比例。1,028 个 buffer 的 `99,486 us` 摊到每次是 97 微秒、占窗口 1.3%、整轮 0.25%；直接读成「一次等 99 毫秒」会得出相反的结论。
- 报「平均」「总量除以样本数」这类数之前，先看分布：同时给出中位数与「哪几个样本占了大部分总量」。bbm29 的 `rwa draw` 总量 16.38 秒里有 89% 集中在 6 个窗口（合计 1,455 个窗口样本中的 6 个），用总量算每帧 draw 时间是 3.27 毫秒，用中位数算是 0.23 毫秒，两者差 14 倍而都算得对；那 6 个窗口的时刻落在停帧前后，不是稳态成本。
- 拿日志行数当调用次数之前，先看那一行的完整文本，再确认这条路径在当轮的二进制里存在。`grep -c "resolve "` 把 `colour attachment 0 asks for a multisample resolve ... and this driver resolves nothing` 这句警告也算成了 354 次调用，据此得出的「每次 draw 一次全屏 resolve」是错的，代价是一轮分析方向。`--verify` 与 `pipeline seen:` 这类只在特定版本才有的行，可以用来确认当轮跑的是哪一份二进制。
- 插桩轮的判据按「覆盖全轮」判，不按行数的绝对值判。`perf frames` 这类汇总行每 128 帧一行，420 秒的一轮只有约 19 行、合计 2432 帧，与 `--verify` 的帧数吻合即为通过；写「行数不少于 100」是把每行当成一帧的标度错误，12800 帧在 420 秒里不存在。
- 与判据对照的一句话结论，以及这一轮是否算通过。

## 6. 日志环容量与快照频率

内核日志区是 263,349 字节的固定头加 1,048,576 字节（1 MiB）的滚动环，单份快照最大 1,311,925 字节（`263,349 + 1,048,576 = 1,311,925`，与 roundb、round C、round D 三轮实测上限逐字节相等；文档原记 1,311,895，30 字节的差来源未查），写满之后快照不再变大、只保留最近的 1.31 MB。头的大小由两条独立路径定：display 从空洞几何推出约 259 KB（估计值），perf 逐字节比对得 263,349（准确值：三轮各 21 份快照里 20 份共享同一前缀哈希、排除短于该长度的快照后，round C 与 round D 的第一份与最后一份满额快照第一个不同位置都在偏移 263,349），取后者；roundb 的接缝在 263,350，接缝位置不是常量、按轮次实测。`256 KB + 1 MB = 1,310,720` 与实测上限差 1,205 字节，正是头比 262,144 多出的部分（263,349 − 262,144 = 1,205），没有别的余量；`round-stats.py` 的 `RING_BYTES = 1024 * 1024` 就是环的准确大小。实测增长：开机后 20 秒的第一份完整快照 645 KB，160 秒时 1,305 KB，约 180 秒后一直是 1,311,925 字节。分界落在一条日志行中间（round C 的 s002 与 s020 在偏移 263,349 处，s002 是 `... Clearing stale icon attempt to escape CPU monitor (missing `、s020 是 `... Clearing stale iconredwoodmetal[backboardd 38]: commit 1752`，头在 `(missing ` 之后截断、环紧接着从那里写），重叠拼接在这一处对不上是预期行为、环结构的必然结果，判读见[读数规则 §13.6](../analysis/2026-10-28-roundc-reading-criteria.md)；按行数报环内容时这半行要单独说明。

所以每轮必须按 20 秒一次拉快照（`run-queue.sh` 的 `RUN_TIMING` 默认 `3,100,20`，最后一项就是间隔）。按最快增长段约 32 KB/s 计算，20 秒新增约 640 KB，相邻快照的重叠仍有 600 KB 以上，全轮窗口的并集才完整。间隔拉到 60 秒时新增约 1.9 MB，超过环容量，中间会出现覆盖不到的时间段。

2026-10-28 的 `bbm29` 量了一次环里各来源的占比（取写满环的最后一份快照，1,311,925 字节、26,549 行）：`tl:` 时间轴 827,870 字节、63.1%，我们自己驱动的 `cpufreq:`／`battery:`／GPU 打印 8.7%，`backboardd`（含 TouchEvents）7.3%，`launchd` 0.9%，扩展与 pluginkit 0.5%。把环吃满的是插桩代码本身，iOS 侧日志合计不到 10%。因此带 `tl:` 的轮次里环只能装约 20 秒，20 秒一拉刚好接上；把间隔缩到 8 秒不会增加可见内容，只会让每轮多传三倍字节。要拉长历史只能调大 loader 侧的环，或者减少插桩输出。

设备内核与容器内核是两棵树：`tools/k90auto/build-kernel.py` 在容器里编的是 `xnu-src/xnu-8796.121.2`（iOS 16.5 线），真机跑的内核由 `xnu26/build-macos.sh` 从 `out/xnu12377` 在 macOS + Xcode clang 上编。同名函数在两棵树里可以有不同签名与可见性（2026-10-28 的 `ctl_enable` 只在 8796 缺失、`ctl_bind` 只在 12377 的 `kern_control_private.h` 里）。所以：凡说「这个 API 存在／不存在」，必须写明是哪棵树；`build-kernel.py` 记录不了 26 线的产物，26 线内核的记录只能手写并注明。

`rc.jobs` 由 `init.c:run_rc()` 逐行执行、每行 `wait4` 等结束，行尾 `&` 只做 fork 不等待。所以要在整轮期间并行运行的行必须放在文件最前：追加在末尾时，前面每一行都要先跑完，整轮拿不到读数。2026-10-28 前十轮「探针零输出」就是这个原因——`lsprobe 60 &` 排在几百秒手势之后，等轮次结束才启动。早期轮次偶尔有 `t=60` 而无 `t=300`，是因为那版 `rc.jobs` 只有 8 轮下拉、手势跑得快，`t=60` 还来得及在轮次内触发，`t=300` 一定来不及。同类的防呆还有两条：`run-queue.sh` 跑轮开始前核对 `manifest.json` 里的 `payload.path` 存在（`make-payload` 失败时不许沿用旧产物），以及 `run/` 目录非空时拒跑（宁可拒跑，不覆盖证据目录）。

推论：**从控制台日志里取「开机后头几十秒发生的事」不成立**。2026-10-28 量过一次：`com.apple.xpc.launchd` 开头的行在 `bbm28` 有 33,721 条（日志约 30 KB/s，环能覆盖整轮），在 `bbm29` 与 `v6` 各只有 880 条、两轮完全相同、全在开机后两秒内（65 KB/s，环只覆盖约 15 秒，`Successfully spawned`／`user/501/` 这类开机后 0.5 秒的行在第一次拉快照之前就被挤掉）。所以「某进程是否被拉起」「某个扩展身份有没有被查到」这类判据，必须由载荷里的探针在运行时取（`PROBE=1` 的 `lsprobe`），日志缺席只能记成「该轮未保留」，不能记成「没有发生」。

`RUN_SECONDS` 因此不宜超过 420 秒。需要更长的观测就把 `RUN_TIMING` 的日志间隔改成 10 秒，不要只拉长时长。`oem logwrite` 写到 `boot_a` 开头，与日志容量无关，不能拿来扩大捕获范围；把环改大要同时改内核与 loader 的内存布局，本轮不做。

## 7. 失败与重试

同一轮失败先分类，再决定重跑还是停下。

自动重试，不占申请人的轮次：

- 单条 `getvar`／`oem log` 超时一次：重试该命令，最多 2 次。
- 复位落到 B 槽 Android：`recover-loader.py` 自动恢复（40 秒内等 `adb devices`，最多 3 次），复位后 `set_active a` 把 A 槽重试次数复位为 7，本轮数据仍有效。
- `reboot` 后 90 秒既没回到 idle 也没进 Android：重试 `reboot` 2 次。
- 快照缺失一两份但收尾正常：本轮有效；缺得多到 `--verify` 不过，按下一组处理。

停下并报 lead，不自行重试：

- `--verify` 不过且重拉一次快照仍不过。这说明合并或采集有工具缺陷，继续跑只会产出不可信数字。
- 出现需要按键、切槽、重刷的动作，或 `reset-failed`、`firmware_fault`。
- 同一路径连续失败 3 次（goals 的要求）：停下，把三次的原始输出一起报 lead，换思路或改代码后重新排队。
- 载荷、根盘、系统盘哈希与 `manifest.json` 不符。
- 打包或编译失败。

## 8. 我会回绝的申请

能用现有日志回答的不占用真机：已经跑过的轮次里有的行（`rwa draw:`、`command buffers:`、`copy` 计数、设备枚举、槽位状态）、只涉及源码阅读或 Mesa／freenode 上游对照的问题、能在 QEMU 复现的用户态问题。回绝时会说明用哪份证据的第几行回答，或指出该问题缺的是哪份数据，请申请人把判据改到能在一次真机上区分两三种假设。

## 9. 排队与占位

申请按到达顺序排队，一次一轮，一轮跑完把设备复位回 idle loader 再开始下一轮。需要 A 槽重试次数补充时插入一次 `reboot-lk.py --return-loader`（约 26 秒）。需要改 `root.apfs` 或系统盘的申请，先说明是否与其他人的打包冲突；`hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs` 是共享产物，改它要串行。
## 10. 长跑轮（静置观测）

超过一小时的轮次单独算一类，排在整个队列最后，因为它占用设备最久。

- 时长 4200 秒以上，必须覆盖开机后第 62 分钟那个点（`[timeline.store]` 把扩展身份的重试排在开机后 1 小时）。
- 不跑手势循环，只解锁；需要屏幕不灭时每 20～30 秒点一次状态栏，这不算手势循环。
- 温度护栏：大核读数超过 78 °C 立即中止。中止时记录当时的温度、时刻与已跑时长，这一轮按有效结果入库，不重跑。判定用 `cpufreq=1` 的 30 秒窗口 `hottest`，连续两次窗口超过 78 °C 才中止，单次尖峰不算。
- 快照间隔 180 秒。静置段日志增长约 2～7 KB/s，10 分钟会涨到 1.3 MB 上限而丢窗口；180 秒一份同时满足「至少每 10 分钟一份」与不丢窗口。
- 这一轮开跑后不再安排其他真机任务，`reboot.json` 与快照照常记录。
- 判据以日志为准（第二次查询有没有出现、拿到的是身份还是又一次 `Extension not found`），截图是辅助证据；静置轮的帧率与手势数字不引用。

## 「改了但没生效」第七例：编译在条件分支里，装箱不在

`userland/build.sh` 里 `obj/libredwoodmetal.dylib` 的编译位于 `if [ -d $IOS/rootfs/usr/lib ]` 与 `if [ -z "$PREBUILT" ]` 两层之内（第 258 行起），而把它拷进 `root/lib/` 的那一步（第 556 行）在这两层之外。两个条件都会静默地不成立：`IOS` 默认是 `../ios165`，本机没有它的 rootfs；`ld64` 不在 `PATH` 时第 158 行会把 `PREBUILT` 自动置 1。任一情形下编译被跳过，装箱照做，镜像是上一次留下的目标文件。2026-10-28 的 `freeze` 之后正是如此：`obj/libredwoodmetal.dylib` 的时间戳停在 10 月 23 日，而 `src/redwoodmetal.m` 已改。

同一族还有一处更彻底的漏：`obj/lsprobe` 既没有编译规则，也不在第 455 行的装箱清单里，所以 `src/lsprobe.m` 里的 `cpu procs=` 从未进过任何 apfs。

判据：编译步骤与装箱步骤出现在不同的条件作用域时，「没生效」不会有任何提示。修法是装箱前断言目标文件比源文件新（`[ obj/x -nt src/x.m ]`），并且在装箱清单与编译规则之间保持一一对应；`build.sh` 现已按此断言，`lsprobe` 也补上了规则与清单项。

**`out/ios26-resume/bbmetal-device/` 不是 `build.sh` 的产物目录**。写它的脚本就在仓库里，两个都被顶层仓跟踪（display task-11 逐行查实并只读验证，见 [arm64e 构建路径](../analysis/2026-10-28-arm64e-userland-build-path.md)）：驱动与程序走 `tools/k90auto/package.py`（最近改动 `ffda571`）——`:168` 用 `xcrun -sdk iphoneos clang -arch arm64e -miphoneos-version-min=26.0`，`:274-282` 的 `build()` 把命令行写进 `<out>.build.log`、以 `cwd=SRC_ROOT`（默认 `hackios-xnu-kernel`）编译，随后 `codesign --force --sign -` 做 adhoc 签名，roundb 那次的三条命令行逐字记在该轮 `manifest.json` 的 `build_commands` 里；AIR 库走 `tools/k90auto/build-air.py`（`9c4405a`），是 `package.py:57-61` 指名的唯一入口——把 `tools/mesa/air/` 的三个源复制进 `out/ios26-resume/mesa-arm64e/mesa-26.2.5/src/compiler/air/`、断言两侧一致且目录内无未复制文件，然后 `ninja -C build -j8 src/gallium/drivers/freedreno/libredwoodair.dylib`，输出写到 `bbmetal-device/libredwoodair.dylib` 并 adhoc 签名、写 `air-build-record.json`，工具链在 `cross.ini`：c／cpp／objc 都是 Xcode toolchain 的 clang 加 `-arch arm64e -isysroot …/iPhoneOS27.1.sdk -miphoneos-version-min=26.0`，`[host_machine]` 是 darwin／ios／aarch64／arm64e。要写清的区分：**AIR 库的 arm64e 来自宿主 meson 交叉构建，与容器里 `tools/mk-mesa.sh` 那条 theos 路径是两回事**，这就是容器修不好也不影响 26 线产物的原因。round A 起，驱动与库以 `userland/obj/` 与 apfs 解出的值为准。

真构建前后的两条操作纪律（display task-11）：任何真构建之前，把 `out/ios26-resume/bbmetal-device/` 整个目录备份到 Git 忽略的目录——`build-air.py:30` 的 `OUT` 硬编码指向 `bbmetal-device/libredwoodair.dylib`、没有环境变量能改，不带 `--check` 运行会就地覆盖（`:99`），而那正是 roundb 装车那份的身份。`hackios-xnu-kernel/out/ios26-resume/mesa-arm64e/` 树里有三个同名 `libredwoodair.dylib`，字节数与哈希各不同：`build/src/gallium/drivers/freedreno/` 下 13,956,392／`0c9b9a9f`（ninja 输出）、树根下 13,949,888／`7b8e29ed`（来历未查）、`bbmetal-device/` 下 13,983,936／`d7b9ced5`（装车那份）；OUT 比 ninja 输出大 27,544 字节，与 adhoc 签名的 CodeDirectory 尺寸 27,471 相符。引用这个文件名时必须带路径。
