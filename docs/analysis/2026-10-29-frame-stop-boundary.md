# 帧流永久停止的边界：末帧后的停止次序与 3 秒空洞的对照（2026-10-29）

本文只读 `docs/progress/evidence/k90auto/` 下已有的轮次日志，回答两个问题：永久停止前最后几秒各动作按什么次序停下；这个停止过程与 15 秒周期的 3 秒空洞在进入方式上是否同一类。本轮没有设备，没有新增探针，也没有改代码。前两份复盘见[会话复盘](2026-10-29-session-review.md) §6 与[15 秒周期跨轮统计](2026-10-29-15s-period-cross-round.md)，本文不重复它们的结论，只补停止次序与边界读数。

## 1. 结论

1. 次序。13 个观察窗 ≥100 秒的轮次里，末帧前后各族最后一条的次序一致：GPU 提交 `tl: Q`（末帧 `ready` 前 1.9～10.4 毫秒）、fence 等待结束 `tl: f`（前 0.1～0.5 毫秒）、交换交接 `tl: s`（前 0.1 毫秒）、上屏 `tl: v`（末帧）、`tl: w`（末帧 `ready` 前 48.8 毫秒到后 29.0 毫秒），此后只有 `tl: p`／`tl: a`／`tl: i`／`tl: c` 继续。末帧之后没有任何 `tl: s` 或 `tl: v`。实测。

2. 层。甲组 13 轮里，末帧之后没有 backboardd 的新 commit 行、新 `tl: Q`、新 `tl: s` 或新 `tl: v`；10 轮还调用过下一次 `tl: w`，3 轮没有。乙组有两轮给出另一种形态：`diag3x-fd6inner` 在末帧后 16.075 秒提交 6 条 `tl: Q`（fence 962～967），`pid-sustain-fix` 在 0.454 秒后提交 9 条（fence 3644～3652），随后两轮的看门狗分别报 `commit 882 has not moved for 2667 ms` 与 `commit 3609 has not moved for 3015 ms`，此后没有 `commit N took`。甲组的下一帧没有进入提交，乙组这两轮进入提交后没有回来；停在哪个调用仍没有读数。实测加推断。

3. 同形。3 秒网格空洞的延迟位置在 262 个 2.9～3.1 秒间隔里有 256 个落在同一步：上一帧 `done` 之后、下一次 `tl: w` 之前，随后以一对 `tl: w`、一条 `tl: Q`、一条 `tl: s`、一帧 `tl: v` 在 5.1～6.9 毫秒内结束。永久停止前的终末碎片至少在 5 个不同子步骤上出现（`done→w1`、`w2→Q1`、`Q1→Qlast`、`w2→Qlast`、fence 等待），末帧本身停在 `done→w1`（3 轮）、`w1→w2`（1 轮）、`w2→Q1`（9 轮）。两类现象在「帧循环里出现多秒静默、其它进程照常」这一点上同类；网格洞每次在同一位置静止并立即恢复，终末阶段的静止位置分散且不恢复。实测。

4. 不能回答。哪一段用户态代码在等、等什么；线程快照全部被拒（`thread dump for pid 38 refused (errno 1)`）；8 个 `diag3x` 轮与 `pid-sustain-align` 在末帧后 9.6～25.7 秒还有一次 SwapWait，此后到日志结束没有新的 `tl: v`，「永久」在这些轮不能证实；15 秒网格的锚点与唤醒源仍不在日志里。

## 2. 数据与口径

### 2.1 读法

- 合并用 `tools/k90auto/summary.py` 的 `merged_log(run)`；`log_files()` 定合并顺序，`overlap()` 按 256 KB 到 64 字节的降序片段找接点。没有另写合并。
- 归档里有 179 个 `kernel-*` 轮次目录，121 个含帧行，58 个没有日志或没有帧。本文只统计这 121 个。
- 时间戳是设备 `mach_absolute_time` 的微秒。同一行在相邻快照里会重复，末条按最大时间戳取，不按文本位置。少数轮的合并文本有重复段落，这类轮只使用带时间戳的读数，`rwa draw`／`cpufreq`／`MiniIOMobileFramebuffer` 的行序结论不用于这些轮。
- `tl: v` 的四个字段是帧 id、`ready`（present 进入）、`shown`（等到显示节拍）、`done`（像素写进面板内存）。本文的「末帧间隔」是末帧 `ready` 与上一帧 `ready` 之差。

### 2.2 各族含义与源码位置

| 族 | 打印位置 | 含义 |
|---|---|---|
| `tl: v` | `hackios-xnu-kernel/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp` 的 `present()` | 一帧写进面板内存之后 |
| `tl: s` | 同一文件的 `present()` 入口 | 客户端调用 SwapEnd，交换交给内核 |
| `tl: w` | 同一文件的 `kFBMethodSwapWait` | SwapWait 方法入口，方法立即返回成功 |
| `tl: Q` | `hackios-xnu-kernel/xnu/files/iokit/Kernel/RedwoodGPUSubmit.inc` | 一次 GPU 提交被接受，行内带提交者进程名 |
| `tl: f` | `hackios-xnu-kernel/xnu/files/iokit/Kernel/RedwoodGPU.cpp` 的 `slowWait()` | 一次 ≥1 毫秒的等待结束时打印，`at` 是等待结束时刻 |
| `tl: p` | `hackios-xnu-kernel/xnu/files/bsd/dev/redwood_input.c` 的 `touch_post()` | 驱动收到一个触摸样本并投递 |
| `tl: a` | `hackios-xnu-userland/userland/src/inject_sb.c` | SpringBoard 主循环一圈，四个数是醒来、commit 开始、commit 结束、本圈微秒 |
| `tl: i` | `hackios-xnu-userland/userland/src/inject.c` | 输入服务读到一个样本并向事件系统投递 |
| `tl: cnt` | `hackios-xnu-kernel/tools/userland-driver/redwoodmetal_commandbuffer.inc` 的看门线程 | 每秒一条心跳，计这一秒的 commit、wait、texwrite |
| `framewatch: still no frames` | 轮次作业启动的 framewatch（源码不在两个子模块的跟踪文件里） | 监视 `kern.redwood.frames`，10 秒不动就每 10 秒报一次 |
| `rwa draw`／`cpufreq`／`MiniIOMobileFramebuffer` | 用户态驱动、内核调频、内核帧缓冲统计 | 不带设备时间戳，按合并文本的行序定位 |

### 2.3 判据

「永久停止」在本文按三条件判定：末帧之后合并日志里没有新的 `tl: v`；`tl: p` 或 `tl: a` 在末帧之后仍有行；观察窗（末帧到最后一条 `tl: p`／`a`／`i`／`c`）≥10 秒。按窗长分三组：甲组 ≥100 秒，乙组 10～100 秒，丙组没有 `tl: p` 只有 `tl: a`。窗长只说明观察到多久没有新帧，不说明系统以后会不会恢复。

## 3. 永久停止的轮次

### 3.1 分组

甲组 13 轮：`roundc`、`roundd`、`nochronod`、`fixguard6`、`fixguard7`、`airindex`、`perf1`、`touchdiag`、`gestures`、`poster-stores`、`bbm29`、`perf-draw-v6`、`roundf-abort1`。`roundf-abort1` 是被中止的轮次，`tl: a` 在末帧后继续 1776 秒，列在这里并单独标注；它的合并文本末尾另有一段重复的启动帧，行序结论不使用这一轮。

乙组 33 轮：`diag3x-` 前缀 19 轮（`arm64e`、`banner`、`batchcheck`、`cavbl`、`drawcall`、`dumponstall`、`fd6entry`、`fd6inner`、`fddraw`、`inject`、`injectpath`、`pairing`、`rdpair`、`revertcheck`、`segflt`、`statefault`、`tcslow`、`tddump`、`verdict`）、`diag3-` 前缀 4 轮（`heartbeat`、`heartbeat2`、`heartbeat3`、`waitprobe2`）、`fixguard5`、`pid-fixverify`、`pid-pid`、`pid-q2probe`、`pid-sustain-align`、`pid-sustain-fix`、`pid-perf-sustain-pid`、`restored-perf-sustain-cf`、`unlockprobe`、`pid-copyrect`。

丙组 7 轮：`freeze`、`perf-draw-v4`、`speed3`、`continuous`、`driver-revert`、`persona3`、`probe-age`。这 7 轮在观察窗内没有 `tl: p`，结束前的最后一针触摸比末帧早 24.8～219.9 秒，`tl: a` 仍继续 12.9～290.3 秒。

另有 4 个 10-25 的调频轮（`cpufreq-report-airarm64e-a`／`b-metal`／`c-metal3`、`cpufreq-tsens-airarm64e-a`）在末帧后 `tl: p` 继续 104.6～106.5 秒；这些轮没有 SpringBoard shim，没有 `tl: a`。它们的构建与本文其余轮不同，只作为「跨构建同样出现」的旁证。

### 3.2 各组读数

甲组逐轮。

| 轮次 | 帧数 | 观察窗 | 最后 p | 最后 a | 末帧后 w | 末帧后 backboardd Q |
|---|---|---|---|---|---|---|
| roundc | 3609 | 317.9 s | 3.3 s | 317.9 s | 0 条 | 0 条 |
| roundd | 3620 | 320.5 s | 5.2 s | 320.5 s | 2 条，首条 +1.5 ms | 0 条 |
| nochronod | 3608 | 323.6 s | 88.3 s | 323.6 s | 2 条，首条 +12.3 ms | 0 条 |
| fixguard6 | 3616 | 141.4 s | 128.5 s | 141.4 s | 2 条，首条 +1.4 ms | 0 条 |
| fixguard7 | 1574 | 150.6 s | 142.7 s | 150.6 s | 2 条，首条 +1.3 ms | 0 条 |
| airindex | 3549 | 315.8 s | 85.8 s | 315.8 s | 2 条，首条 +2.5 ms | 0 条 |
| perf1 | 2111 | 354.1 s | 354.1 s | 347.0 s | 2 条，首条 +1.9 ms | 0 条 |
| touchdiag | 3548 | 133.6 s | 41.0 s | 133.6 s | 2 条，首条 +1.6 ms | 0 条 |
| gestures | 17 | 338.1 s | 291.3 s | 338.1 s | 0 条 | 0 条 |
| poster-stores | 3519 | 322.9 s | 7.6 s | 322.9 s | 2 条，首条 +1.4 ms | 0 条 |
| bbm29 | 5005 | 262.1 s | 186.8 s | 262.1 s | 1 条，+7.7 ms | 0 条 |
| perf-draw-v6 | 682 | 379.0 s | 293.1 s | 379.0 s | 0 条 | 0 条 |
| roundf-abort1 | 3561 | 1775.9 s | 1.2 s | 1775.9 s | 2 条，首条 +1.9 ms | 0 条 |

乙组逐轮。

| 轮次 | 帧数 | 观察窗 | 最后 p | 最后 a | 末帧后 w | 末帧后 backboardd Q |
|---|---|---|---|---|---|---|
| diag3x-arm64e | 46 | 29.0 s | 29.0 s | 28.2 s | 0 条 | 0 条 |
| diag3x-banner | 120 | 27.9 s | 27.9 s | 27.2 s | 0 条 | 0 条 |
| diag3x-batchcheck | 918 | 22.0 s | 22.0 s | 17.2 s | 2 条，首条 +19.0 s | 0 条 |
| diag3x-cavbl | 114 | 21.0 s | 21.0 s | 20.5 s | 0 条 | 0 条 |
| diag3x-drawcall | 968 | 30.0 s | 30.0 s | 29.6 s | 2 条，首条 +23.3 s | 0 条 |
| diag3x-dumponstall | 766 | 27.0 s | 25.7 s | 27.0 s | 2 条，首条 +345.3 ms | 0 条 |
| diag3x-fd6entry | 1016 | 27.0 s | 27.0 s | 26.6 s | 0 条 | 0 条 |
| diag3x-fd6inner | 880 | 25.8 s | 25.8 s | 25.1 s | 3 条，首条 +1.8 ms | 6 条，首条 +16.1 s |
| diag3x-fddraw | 991 | 30.3 s | 30.3 s | 30.1 s | 0 条 | 0 条 |
| diag3x-inject | 671 | 26.5 s | 26.5 s | 25.3 s | 0 条 | 0 条 |
| diag3x-injectpath | 1 | 27.5 s | 27.5 s | 无 | 2 条，首条 +1.8 ms，另一条 +13.3 s | 0 条 |
| diag3x-pairing | 1045 | 26.3 s | 26.3 s | 25.5 s | 0 条 | 0 条 |
| diag3x-rdpair | 901 | 26.9 s | 26.9 s | 26.4 s | 0 条 | 0 条 |
| diag3x-revertcheck | 716 | 27.3 s | 27.3 s | 26.6 s | 2 条，首条 +12.8 s | 0 条 |
| diag3x-segflt | 920 | 27.1 s | 27.1 s | 26.0 s | 2 条，首条 +25.7 s | 0 条 |
| diag3x-statefault | 912 | 24.0 s | 24.0 s | 23.9 s | 0 条 | 0 条 |
| diag3x-tcslow | 1038 | 29.0 s | 29.0 s | 27.3 s | 2 条，首条 +18.2 s | 0 条 |
| diag3x-tddump | 1023 | 27.0 s | 27.0 s | 25.8 s | 2 条，首条 +20.9 s | 0 条 |
| diag3x-verdict | 955 | 26.2 s | 26.2 s | 25.3 s | 2 条，首条 +20.1 s | 0 条 |
| diag3-heartbeat | 138 | 22.0 s | 22.0 s | 20.3 s | 0 条 | 0 条 |
| diag3-heartbeat2 | 100 | 29.3 s | 29.3 s | 28.1 s | 0 条 | 0 条 |
| diag3-heartbeat3 | 1034 | 21.4 s | 21.4 s | 20.6 s | 0 条 | 0 条 |
| diag3-waitprobe2 | 115 | 26.0 s | 26.0 s | 24.4 s | 0 条 | 0 条 |
| fixguard5 | 79 | 81.3 s | 81.3 s | 无 | 3 条，首条 +30.9 ms | 0 条 |
| pid-fixverify | 3602 | 24.7 s | 3.0 s | 24.7 s | 1 条，+10.0 ms | 0 条 |
| pid-pid | 3591 | 23.6 s | 2.6 s | 23.6 s | 2 条，首条 +1.3 ms | 0 条 |
| pid-q2probe | 130 | 20.6 s | 20.6 s | 0 s | 4 条，首条 +13.5 ms | 0 条 |
| pid-sustain-align | 541 | 23.2 s | 23.2 s | 22.2 s | 2 条，首条 +9.6 s | 0 条 |
| pid-sustain-fix | 3608 | 26.7 s | 26.7 s | 22.0 s | 1 条，+14.0 ms | 9 条，首条 +0.454 s |
| pid-perf-sustain-pid | 74 | 21.9 s | 21.9 s | 无 | 4 条，首条 +47.7 ms | 0 条 |
| restored-perf-sustain-cf | 69 | 23.9 s | 23.9 s | 无 | 2 条，首条 +47.6 ms | 0 条 |
| unlockprobe | 454 | 16.8 s | 16.8 s | 无 | 4 条，首条 +13.2 ms | 0 条 |
| pid-copyrect | 46 | 25.2 s | 25.2 s | 无 | 3 条，首条 +29.9 ms | 0 条 |

乙组表里 `fixguard5`、`pid-q2probe`、`pid-copyrect`、`pid-perf-sustain-pid`、`unlockprobe` 的末帧后 `tl: w` 含帧 id 为 0、标量 `0x80000003` 的另一个客户端行，见 §5.2。

丙组逐轮。

| 轮次 | 帧数 | 观察窗 | 最后 p | 最后 a | 末帧后 w | 末帧后 backboardd Q |
|---|---|---|---|---|---|---|
| freeze | 3423 | 290.3 s | 无（−24.8 s） | 290.3 s | 2 条，首条 +1.3 ms | 0 条 |
| perf-draw-v4 | 2578 | 28.6 s | 无（−58.2 s） | 28.6 s | 0 条 | 0 条 |
| speed3 | 6917 | 37.2 s | 无（−50.7 s） | 37.2 s | 0 条 | 0 条 |
| continuous | 7920 | 53.1 s | 无（−184.2 s） | 53.1 s | 0 条 | 0 条 |
| driver-revert | 7816 | 35.2 s | 无（−198.8 s） | 35.2 s | 0 条 | 0 条 |
| persona3 | 7477 | 16.6 s | 无（−216.2 s） | 16.6 s | 0 条 | 0 条 |
| probe-age | 7923 | 12.9 s | 无（−219.9 s） | 12.9 s | 0 条 | 0 条 |

乙组与丙组各轮末帧之后没有 backboardd 的 `tl: s` 或 `tl: f`；`pid-q2probe` 在 +284.8 毫秒有一条 `tl: f`（pid 197），进程是 SpringBoard，见 §5.2。末帧之后的 `tl: i` 只在 `diag3x-injectpath`（+3.122 秒）、`diag3x-segflt`（+13.528 秒）、`diag3x-statefault`（+2.845 秒）、`diag3x-verdict`（+10.896 秒）、`pid-sustain-fix`（+0.271 秒）有行。`fixguard5`、`pid-q2probe`、`pid-perf-sustain-pid`、`restored-perf-sustain-cf`、`unlockprobe`、`pid-copyrect` 与丙组各轮没有 `tl: i` 这一族，其余乙组轮有这一族但末帧之后没有行。

## 4. 末帧与末条时间戳

### 4.1 末帧原文

下面每行是各轮最后一条 `tl: v`，照抄合并日志，字段为 id、`ready`、`shown`、`done`。甲组：

```
roundc        tl: v 3611 ready 12941686231 shown 12941686231 done 12941687476
roundd        tl: v 3620 ready 4623976423 shown 4623976423 done 4623977843
nochronod     tl: v 3608 ready 554971079 shown 554971079 done 554972816
fixguard6     tl: v 3616 ready 245826443 shown 245826443 done 245827663
fixguard7     tl: v 1575 ready 231142730 shown 231142730 done 231143988
airindex      tl: v 3550 ready 308650265 shown 308650265 done 308652643
perf1         tl: v 2112 ready 586622627 shown 586622627 done 586624386
touchdiag     tl: v 3550 ready 895055825 shown 895055825 done 895057269
gestures      tl: v 17 ready 295047206 shown 295047206 done 295048432
poster-stores tl: v 3522 ready 599610697 shown 599610697 done 599612072
bbm29         tl: v 5008 ready 381592383 shown 381600017 done 381603302
perf-draw-v6  tl: v 682 ready 610720099 shown 610720099 done 610721492
roundf-abort1 tl: v 3559 ready 3577339263 shown 3577339263 done 3577341081
```

乙组：

```
diag3x-arm64e       tl: v 46 ready 701792820 shown 701792820 done 701794058
diag3x-banner       tl: v 120 ready 419435071 shown 419435071 done 419436354
diag3x-batchcheck   tl: v 918 ready 217225370 shown 217225370 done 217226647
diag3x-cavbl        tl: v 114 ready 419968562 shown 419968562 done 419969805
diag3x-drawcall     tl: v 968 ready 300426947 shown 300426947 done 300428175
diag3x-dumponstall  tl: v 767 ready 254438075 shown 254438075 done 254439297
diag3x-fd6entry     tl: v 1016 ready 275142263 shown 275142263 done 275143728
diag3x-fd6inner     tl: v 880 ready 375926586 shown 375926586 done 375928070
diag3x-fddraw       tl: v 991 ready 340982674 shown 340984331 done 340985544
diag3x-inject       tl: v 671 ready 318739128 shown 318754256 done 318755531
diag3x-injectpath   tl: v 1 ready 318014344 shown 318014344 done 318015576
diag3x-pairing      tl: v 1045 ready 193056112 shown 193058555 done 193059814
diag3x-rdpair       tl: v 901 ready 778418112 shown 778434403 done 778437635
diag3x-revertcheck  tl: v 716 ready 194006167 shown 194007487 done 194009027
diag3x-segflt       tl: v 920 ready 584063384 shown 584064751 done 584066050
diag3x-statefault   tl: v 913 ready 334028172 shown 334028172 done 334029426
diag3x-tcslow       tl: v 1038 ready 217709283 shown 217709283 done 217710520
diag3x-tddump       tl: v 1024 ready 284358472 shown 284371432 done 284372936
diag3x-verdict      tl: v 955 ready 197641914 shown 197644931 done 197646144
diag3-heartbeat     tl: v 138 ready 704359329 shown 704359329 done 704360638
diag3-heartbeat2    tl: v 100 ready 782912480 shown 782912480 done 782913788
diag3-heartbeat3    tl: v 1034 ready 260472254 shown 260474370 done 260475645
diag3-waitprobe2    tl: v 115 ready 1116444049 shown 1116444049 done 1116445290
fixguard5           tl: v 91 ready 294852464 shown 294852464 done 294853743
pid-fixverify       tl: v 3603 ready 245923317 shown 245923317 done 245924594
pid-pid             tl: v 3592 ready 245784779 shown 245784779 done 245786050
pid-q2probe         tl: v 138 ready 228053221 shown 228053221 done 228054541
pid-sustain-align   tl: v 542 ready 191689435 shown 191692081 done 191693356
pid-sustain-fix     tl: v 3608 ready 238252713 shown 238260239 done 238261565
pid-perf-sustain-pid tl: v 83 ready 250318993 shown 250318993 done 250320247
restored-perf-sustain-cf tl: v 81 ready 291085731 shown 291085731 done 291086993
unlockprobe         tl: v 463 ready 469770107 shown 469778571 done 469778886
pid-copyrect        tl: v 57 ready 268870139 shown 268872931 done 268874223
```

`diag3x-injectpath` 全程只有这一帧。`pid-perf-sustain-pid` 与 `restored-perf-sustain-cf` 的末帧行取自最大时间戳，文本里另有更早的重复段。

丙组：

```
freeze         tl: v 3425 ready 273031985 shown 273031985 done 273033198
perf-draw-v4   tl: v 2578 ready 622250543 shown 622250543 done 622251943
speed3         tl: v 6930 ready 2303672097 shown 2303680843 done 2303683279
continuous     tl: v 7921 ready 1761025910 shown 1761025910 done 1761027313
driver-revert  tl: v 7819 ready 601108368 shown 601108368 done 601109621
persona3       tl: v 7481 ready 595025813 shown 595025813 done 595027259
probe-age      tl: v 7929 ready 931925491 shown 931925491 done 931927019
```

### 4.2 甲组：末帧后的末条时刻

单位毫秒或秒，相对末帧 `ready`；负值表示该族最后一条在末帧之前。`tl: v` 之后没有新帧，该列省略。

| 轮次 | 末帧间隔 | shown−ready | done−ready | 最后 w | 最后 Q | 最后 f | 最后 s | 最后 p | 最后 a | 最后 i |
|---|---|---|---|---|---|---|---|---|---|---|
| roundc | 106.4 ms | 0 | 1245 | −48.8 ms | −3.6 ms | −0.2 ms | −0.1 ms | +3.3 s | +317.9 s | 无 |
| roundd | 386.4 ms | 0 | 1420 | +6.9 ms | −4.6 ms | −0.3 ms | −0.1 ms | +5.2 s | +320.5 s | 无 |
| nochronod | 66.0 ms | 0 | 1737 | +29.0 ms | −2.1 ms | −0.1 ms | −0.0 ms | +88.3 s | +323.6 s | +86.6 s |
| fixguard6 | 260.2 ms | 0 | 1220 | +6.9 ms | −6.2 ms | −0.2 ms | −0.1 ms | +128.5 s | +141.4 s | +113.2 s |
| fixguard7 | 27.6 s | 0 | 1258 | +7.3 ms | −3.3 ms | −0.2 ms | −0.1 ms | +142.7 s | +150.6 s | +127.3 s |
| airindex | 1.6 s | 0 | 2378 | +16.4 ms | −7.2 ms | −0.5 ms | −0.1 ms | +85.8 s | +315.8 s | +84.0 s |
| perf1 | 460.0 ms | 0 | 1759 | +10.7 ms | −6.0 ms | −0.2 ms | −0.1 ms | +354.1 s | +347.0 s | +3.4 s |
| touchdiag | 4.5 s | 0 | 1444 | +10.9 ms | −6.2 ms | −0.2 ms | −0.0 ms | +41.0 s | +133.6 s | +20.0 s |
| gestures | 1.3 s | 0 | 1226 | −16.8 ms | −2.5 ms | −0.2 ms | −0.1 ms | +291.3 s | +338.1 s | +90.1 s |
| poster-stores | 137.2 ms | 0 | 1375 | +6.0 ms | −10.4 ms | −0.2 ms | −0.1 ms | +7.6 s | +322.9 s | 无 |
| bbm29 | 20.5 ms | 7634 | 10919 | +7.7 ms | −2.3 ms | −0.2 ms | −0.1 ms | +186.8 s | +262.1 s | 无 |
| perf-draw-v6 | 98.1 ms | 0 | 1393 | −2.9 ms | −1.9 ms | −0.1 ms | −0.0 ms | +293.1 s | +379.0 s | +99.2 s |
| roundf-abort1 | 5.3 s | 0 | 1818 | +10.8 ms | −6.9 ms | −0.3 ms | −0.0 ms | +1.2 s | +1775.9 s | 无 |

`bbm29` 与 `perf-draw-v6` 的构建没有 `tl: i`／`tl: a` 的四字段格式，`tl: a` 只有三个数。

### 4.3 甲组末条原文

下面照抄每轮末帧后最后一条 `tl: p` 与 `tl: a`。`tl: a` 的四个数依次是醒来、commit 开始、commit 结束、本圈微秒。

```
roundc        p +3.309 s    tl: p 5 4 0 0 at 12944995169
roundc        a +317.894 s  tl: a 13259580616 13259580645 13259580646 30
roundd        p +5.167 s    tl: p 5 4 0 0 at 4629143448
roundd        a +320.460 s  tl: a 4944436886 4944436905 4944436906 20
nochronod     p +88.329 s   tl: p 3 0 27525 36044 at 643300345
nochronod     a +323.579 s  tl: a 878549844 878549859 878549860 16
fixguard6     p +128.520 s  tl: p 3 0 32768 60292 at 374346107
fixguard6     a +141.434 s  tl: a 387260540 387260547 387260547 7
fixguard7     p +142.704 s  tl: p 3 0 32768 60292 at 373846615
fixguard7     a +150.620 s  tl: a 381762823 381762838 381762838 15
airindex      p +85.792 s   tl: p 3 0 27525 36044 at 394442582
airindex      a +315.765 s  tl: a 624414834 624414847 624414848 14
perf1         p +354.056 s  tl: p 2 0 32768 39606 at 940678354
perf1         a +346.987 s  tl: a 933609641 933609670 933609671 30
touchdiag     p +41.004 s   tl: p 3 0 32768 197 at 936060190
touchdiag     a +133.608 s  tl: a 1028663965 1028664003 1028664005 40
gestures      p +291.275 s  tl: p 3 0 32768 64880 at 586322178
gestures      a +338.077 s  tl: a 633123958 633123977 633123979 21
poster-stores p +7.646 s    tl: p 5 4 0 0 at 607256247
poster-stores a +322.895 s  tl: a 922505700 922505713 922505714 14
bbm29         p +186.842 s  tl: p 3 0 55705 36044 at 568434667
bbm29         a +262.148 s  tl: a 643740023 643740032 643740032
perf-draw-v6  p +293.117 s  tl: p 3 0 55705 36044 at 903836738
perf-draw-v6  a +379.022 s  tl: a 989741967 989741979 989741980 13
roundf-abort1 p +1.228 s    tl: p 5 4 0 0 at 3578567016
roundf-abort1 a +1775.887 s tl: a 5353225772 5353225787 5353225788 16
```

`tl: p` 的两个坐标是 x、y（0～65535）。`p 4`／`p 5` 是 home 键按下与抬起；`roundc` 与 `roundd` 在末帧后只有这两条，是手势脚本在停止之后按的 home 键。`fixguard6`／`7` 在末帧后的 `tl: p` 是脚本后续两段拖动的采样，坐标 `32768 60292` 是按住不放的位置。

### 4.4 乙组与丙组末条原文

下面照抄乙组与丙组每轮末帧后最后一条 `tl: p` 与 `tl: a`，时刻相对末帧 `ready`。`tl: a` 的第四个数是本圈微秒；`perf-draw-v4` 的构建只打三个数，该列没有第四个数。

| 轮次 | 最后 p | 最后 a |
|---|---|---|
| diag3x-arm64e | +28.961 s  tl: p 2 0 54551 32768 at 730754198 | +28.160 s  tl: a 729952329 729952461 729952462 133 |
| diag3x-banner | +27.944 s  tl: p 2 0 18061 32768 at 447378837 | +27.152 s  tl: a 446587559 446587566 446587566 7 |
| diag3x-batchcheck | +21.975 s  tl: p 2 0 52245 32768 at 239200191 | +17.153 s  tl: a 234378565 234378621 234378622 57 |
| diag3x-cavbl | +20.989 s  tl: p 2 0 27289 32768 at 440957796 | +20.503 s  tl: a 440471114 440489989 440489990 18876 |
| diag3x-drawcall | +29.965 s  tl: p 2 0 42965 32768 at 330392289 | +29.642 s  tl: a 330069317 330083972 330087962 18645 |
| diag3x-dumponstall | +25.705 s  tl: p 3 0 58982 32768 at 280143379 | +26.993 s  tl: a 281431308 281482571 281482578 51270 |
| diag3x-fd6entry | +26.999 s  tl: p 2 0 54761 32768 at 302141582 | +26.645 s  tl: a 301787107 301855818 301855819 68712 |
| diag3x-fd6inner | +25.788 s  tl: p 2 0 9647 32768 at 401714545 | +25.143 s  tl: a 401069129 401069185 401069185 56 |
| diag3x-fddraw | +30.268 s  tl: p 2 0 36647 32768 at 371251140 | +30.109 s  tl: a 371091950 371091994 371091994 44 |
| diag3x-inject | +26.480 s  tl: p 2 0 52192 32768 at 345219344 | +25.349 s  tl: a 344087631 344087676 344087676 45 |
| diag3x-injectpath | +27.502 s  tl: p 2 0 37093 32768 at 345516765 | 无 |
| diag3x-pairing | +26.344 s  tl: p 2 0 52245 32768 at 219400130 | +25.487 s  tl: a 218543526 218543572 218543573 47 |
| diag3x-rdpair | +26.867 s  tl: p 2 0 53267 32768 at 805285568 | +26.405 s  tl: a 804823556 804882563 804882564 59008 |
| diag3x-revertcheck | +27.286 s  tl: p 2 0 54709 32768 at 221292505 | +26.625 s  tl: a 220631223 220657574 220657574 26351 |
| diag3x-segflt | +27.136 s  tl: p 2 0 54237 32768 at 611199084 | +25.963 s  tl: a 610026013 610026122 610026122 109 |
| diag3x-statefault | +23.954 s  tl: p 2 0 53739 32768 at 357982529 | +23.867 s  tl: a 357894997 357895070 357895070 73 |
| diag3x-tcslow | +28.966 s  tl: p 2 0 44302 32768 at 246675766 | +27.265 s  tl: a 244974378 244974868 244974874 496 |
| diag3x-tddump | +27.045 s  tl: p 2 0 53896 32768 at 311402980 | +25.759 s  tl: a 310117625 310130165 310130165 12540 |
| diag3x-verdict | +26.244 s  tl: p 2 0 52611 32768 at 223885935 | +25.337 s  tl: a 222978978 223054533 223054534 75556 |
| diag3-heartbeat | +21.971 s  tl: p 2 0 19923 32768 at 726330430 | +20.308 s  tl: a 724667096 724667154 724667154 58 |
| diag3-heartbeat2 | +29.303 s  tl: p 2 0 19582 32768 at 812215142 | +28.112 s  tl: a 811024915 811042308 811042309 17394 |
| diag3-heartbeat3 | +21.376 s  tl: p 2 0 7995 32768 at 281848003 | +20.598 s  tl: a 281070309 281070366 281070366 57 |
| diag3-waitprobe2 | +25.981 s  tl: p 2 0 52821 32768 at 1142425284 | +24.436 s  tl: a 1140880017 1140880091 1140880091 74 |
| fixguard5 | +81.264 s  tl: p 3 0 32768 60292 at 376116265 | 无 |
| pid-fixverify | +2.994 s  tl: p 5 4 0 0 at 248917248 | +24.666 s  tl: a 270589167 270589234 270589235 68 |
| pid-pid | +2.640 s  tl: p 5 4 0 0 at 248424605 | +23.591 s  tl: a 269375970 269376012 269376013 43 |
| pid-q2probe | +20.619 s  tl: p 5 4 0 0 at 248672648 | +0.015 s  tl: a 228068466 228079060 228079061 10595 |
| pid-sustain-align | +23.206 s  tl: p 2 0 7882 32768 at 214895837 | +22.219 s  tl: a 213908687 213908745 213908745 58 |
| pid-sustain-fix | +26.675 s  tl: p 2 0 36081 32768 at 264927779 | +22.039 s  tl: a 260291254 260299262 260299263 8009 |
| pid-perf-sustain-pid | +21.949 s  tl: p 3 0 58982 32768 at 272267808 | 无 |
| restored-perf-sustain-cf | +23.945 s  tl: p 2 0 56968 32768 at 315031060 | 无 |
| unlockprobe | +16.788 s  tl: p 3 0 32768 19661 at 486557659 | 无 |
| pid-copyrect | +25.158 s  tl: p 5 1 0 0 at 294027656 | 无 |
| freeze | 无（最后一条 −24.8 s） | +290.291 s  tl: a 563322630 563322640 563322641 11 |
| perf-draw-v4 | 无（最后一条 −58.2 s） | +28.620 s  tl: a 650870399 651060660 651060661 |
| speed3 | 无（最后一条 −50.7 s） | +37.234 s  tl: a 2340906438 2340906513 2340906513 75 |
| continuous | 无（最后一条 −184.2 s） | +53.116 s  tl: a 1814142220 1814142359 1814142359 139 |
| driver-revert | 无（最后一条 −198.8 s） | +35.209 s  tl: a 636317866 636317945 636317945 79 |
| persona3 | 无（最后一条 −216.2 s） | +16.641 s  tl: a 611666619 611666734 611666735 116 |
| probe-age | 无（最后一条 −219.9 s） | +12.861 s  tl: a 944786728 944786787 944786787 59 |

### 4.5 不带时间戳的族

- `rwa draw`：甲组各轮最后一条汇总行都在末帧之前，最近的时间锚（`tl: Q` 或 `tl: w`）在末帧前 8.8 毫秒到 47.6 秒。`roundc` 最后一条是 `rwa draw: 256 draws, ... total 4008037 us`，时间锚 12,939,181,889（末帧前 2.50 秒），对应停止前的 4.0 秒慢 draw。
- `MiniIOMobileFramebuffer`：最后一条统计行在末帧前 27.6 秒到末帧后 0 秒之间；这个统计在 present 路径里每 5 秒打印一次，帧停之后不再有新的窗口。`airindex` 与 `touchdiag` 的最后一条紧挨末帧（文本位置 +2 行），其余轮在末帧前。
- `cpufreq`：甲组各轮都有末帧之后的 `cpufreq` 行，最近的 `tl:` 锚在末帧后 103～350 秒（`roundf-abort1` 为 1850 秒）。内核的 30 秒调频统计一直打到日志结束。
- `framewatch`：`roundc` 最后一条 `framewatch: still no frames, 318 s at 13261301922`，`roundd` 是 `320 s at 4945782076`，`fixguard6` 是 `141 s at 388576733`，`fixguard7` 是 `156 s at 388420725`，`perf1` 只有 6 条，最后一条 `no frames for 5 s at 592247255`。其余甲组轮没有这一族。
- `tl: cnt`：甲组 13 轮全部没有这一族，这些 AIR 不带这个心跳。`diag3x-` 前缀有 19 轮这一族（含不在乙组的 `diag3x-noinput`，`diag3x-injectpath` 没有），`diag3-heartbeat2` 与 `diag3-heartbeat3` 也有；末帧之后心跳继续，`hb_commit` 在紧接末帧的一条之后全为 0（`diag3x-fd6inner` 在 +16.81 秒另有一条 1）。

乙组与丙组的这几族不带设备时间戳，按文本行序定位；`speed3` 的合并文本有重复段，不在该轮取行序读数。`cpufreq` 在 40 轮里 30 轮有末帧之后的行，其余 10 轮的观察窗都短于 30 秒，与日志在下一个统计点之前结束一致。`MiniIOMobileFramebuffer` 在 10 轮有末帧之后的行：`diag3x-fd6inner` 2 条紧接末帧，`diag3x-injectpath` 5 条，其余 8 轮各 1～2 条。`rwa draw` 只有 `diag3x-fd6inner` 在末帧之后还有 1 条（`rwa draw: 256 draws, … total 549896 us`，位置在 6 条 `tl: Q` 之间），其余 39 轮都在末帧之前。`framewatch` 在乙组 33 轮都有末帧之后的行（2～98 条），丙组 7 轮没有这一族。

## 5. 停止次序

### 5.1 跨轮一致的次序

以甲组 13 轮为准，末帧前后各族的最后一条按时间排出如下，括号里是跨轮范围。

1. `tl: Q`：末帧 `ready` 前 1.9～10.4 毫秒。这是最后一帧自己的 GPU 提交。
2. `tl: f`：前 0.1～0.5 毫秒。fence 等待结束，行上的等待量在 1,742～10,154 微秒之间。
3. `tl: s`：前 0.1 毫秒。最后一帧交给内核 present。
4. `tl: v`：末帧。`done − ready` 1,220～2,378 微秒（`bbm29` 为 10,919）。
5. `tl: w`：末帧 `ready` 前 48.8 毫秒到后 29.0 毫秒。10 轮有 1～2 条，3 轮没有。
6. `tl: p`／`tl: a`／`tl: i`／`tl: c`：继续到观察窗末尾，分别到 +1.2～354.1 秒、+133.6～1775.9 秒、+3.4～127.3 秒、+42.2 秒（只有 `fixguard6` 有 `tl: c`）。

`tl: w` 的这一条与常规帧周期里的两条不同。常规周期每帧在上一帧 `done` 之后打两条 `tl: w`，第二个标量依次是 `0x80000001` 与 `0x80000000`；末帧之后的 `tl: w` 全部是 `0x80000001`，第二条也是 `0x80000001`。所有甲组轮在末帧之后都没有再出现 `0x80000000` 的那次调用。

### 5.2 不一致的地方

- 乙组 8 个 `diag3x` 轮（`batchcheck`、`drawcall`、`injectpath`、`revertcheck`、`segflt`、`tcslow`、`tddump`、`verdict`）与 `pid-sustain-align` 的 `tl: w` 落在末帧后 9.6～25.7 秒。这些 `tl: w` 的第二个字段都是 `0x80000001`，帧 id 等于末帧 id。它们是帧循环在长静默之后的一次重试，重试之后仍没有 commit 与 GPU 提交。
- `diag3x-fd6inner` 与 `pid-sustain-fix` 在末帧后有 backboardd 的 `tl: Q`，分别为 6 条（首条 +16.1 秒）与 9 条（首条 +0.454 秒）。两轮都没有随后的 `tl: f`／`tl: s`／`tl: v`。
- `unlockprobe`、`rounde`、`pid-q2probe`、`dealloc-r2`、`fixguard8`、`pid-helpermap`、`restored-perf-sustain-cf`、`pid-ringtrace` 在末帧后有 SpringBoard 的 `tl: Q`（首条 +0.103～0.862 秒，`pid-ringtrace` 为 +0.093 秒）。这些提交不属于桌面帧，说明 GPU 提交路径在桌面帧停止之后仍可用。`pid-q2probe` 在 +284.8 毫秒还有一条同一进程的 `tl: f 197 1618 fence 1168 at 228338003`，后面没有 `tl: s`。
- `fixguard5` 在末帧后 40.3 秒有一条 `tl: w 0 0x80000003 0`，帧 id 为 0、标量与桌面帧的不同，来自另一个客户端，不并入次序表。`pid-q2probe`、`pid-copybox`、`unlockprobe`、`pid-perf-sustain-pid`、`pid-bomap`、`pid-copyrect`、`pid-stagingmap` 在末帧后 0.8～21.3 秒也有同样的 `tl: w 0 0x80000003 0`，同样来自另一个客户端。

### 5.3 末帧之后仍在继续的动作

- `tl: p`：`roundc` 与 `roundd` 只有 home 键的两次采样（+3.2／+3.3 秒、+5.1／+5.2 秒）。`fixguard6`／`7` 继续到 +128.5／+142.7 秒，是脚本后面两段拖动的 120／130 个样本。`perf1` 继续到 +354.1 秒。`diag3x-statefault` 从 +6 毫秒起每 8 毫秒一个样本，继续 24.0 秒。
- `tl: a`：SpringBoard 主循环每 5 或 10 秒一圈；末帧后共 1,155 圈，圈耗时中位 31 微秒，269 圈超过 1 毫秒，最长 90.7 毫秒。`roundc` 的 44 圈从 +2.9 秒到 +317.9 秒，`nochronod` 的 39 圈到 +323.6 秒，`roundf-abort1` 的 179 圈到 +1775.9 秒。
- `tl: i`：输入服务在 `nochronod` 继续 86.6 秒、`fixguard6` 113.2 秒、`fixguard7` 127.3 秒、`perf-draw-v6` 99.2 秒、`gestures` 90.1 秒、`airindex` 84.0 秒。最后一条都形如 `tl: i 2 posted ... read ... sent ...`，投递照常完成。
- `tl: c`：`fixguard6` 的 7 条继续到 +42.2 秒，最后一条 `tl: c before 287981333 seen 287990346 read 287990638`。这一族是用户态某条提交路径的首次观测，本文不解释它。
- `cpufreq` 与 `framewatch`：见 §4.5。

## 6. 与 3 秒网格空洞的对照

### 6.1 网格洞的落点

把相邻两帧之间 ≥1 秒的间隔按 `done→w1`、`w1→w2`、`w2→Q1`、`Q1→Qlast`、`Qlast→s` 等子步骤拆开，取跨度最大的那一步。全部 121 轮里共有 1,724 个 ≥1 秒的间隔，其中 1,331 个的最大子步骤是 `done→w1`；把范围收窄到 2.9～3.1 秒，262 个间隔里 256 个是 `done→w1`，其余 6 个是 `w1→w2`（2 个）、`Q1→Qlast`（2 个）、`w2→Q1`（1 个）、`w2→Qlast`（1 个），且都落在启动后第 16～21 帧或终末段。

四个 3 秒洞的边界，从上一帧 `done` 起算：

| 轮次 | 洞宽 | w1 | w2 | Q1 | s | 下一帧 ready |
|---|---|---|---|---|---|---|
| roundc 帧 730→731 | 3.041 s | +3036.2 ms | +3036.5 ms | +3037.5 ms | +3041.2 ms | +3041.3 ms |
| roundd 帧 736→737 | 3.008 s | +3003.0 ms | +3003.4 ms | +3004.4 ms | +3008.1 ms | +3008.1 ms |
| fixguard6 帧 737→738 | 3.009 s | +3002.4 ms | +3002.9 ms | +3004.8 ms | +3008.7 ms | +3008.8 ms |
| statefault 帧 634→635 | 3.043 s | +3036.5 ms | +3037.2 ms | +3040.1 ms | +3043.4 ms | +3043.4 ms |

四个洞里从 w1 到下一帧 ready 是 5.1～6.9 毫秒，`tl: f` 都没有打印（fence 等待不到 1 毫秒）。这四轮的 `tl: s` 都在洞结束的那一侧。

### 6.2 终末碎片的落点

停止前最后 10 帧里 ≥1 秒的间隔，按最大子步骤列出。这些间隔都出现在第 5 个网格点之后的终末段。

| 轮次 | 间隔 | 帧号 | 最大子步骤 | 最大跨度 | 同段其它子步骤 |
|---|---|---|---|---|---|
| roundc | 2.186 s | 3605→3606 | done→w1 | 1.688 s | w2→Q1 0.463 s |
| roundc | 3.415 s | 3607→3608 | Q1→Qlast | 3.111 s | w1→w2 0.288 s |
| roundc | 2.369 s | 3609→3610 | done→w1 | 2.271 s | 无 |
| roundd | 1.419 s | 3615→3616 | done→w1 | 0.887 s | w2→Q1 0.486 s |
| roundd | 2.947 s | 3616→3617 | Q1→Qlast | 2.682 s | w1→w2 0.259 s |
| roundd | 1.161 s | 3618→3619 | w2→Q1 | 1.144 s | 无 |
| fixguard6 | 1.899 s | 3612→3613 | done→w1 | 1.602 s | w2→Q1 0.257 s |
| fixguard6 | 2.473 s | 3614→3615 | w2→Qlast | 2.049 s | 无 |
| fixguard7 | 27.625 s | 1574→1575 | w2→Q1 | 27.592 s | 无 |

`fixguard7` 的末帧本身来自这 27.6 秒的停顿：两次 `tl: w` 在末帧前 27.6 秒就打完了，直到 27.592 秒后才有第一条 `tl: Q`，随后 `tl: f` 等待 3,062 微秒、`tl: s`、末帧。末帧之后只有两条 `tl: w`，都是 `0x80000001`（+1.3 与 +7.3 毫秒），没有 `0x80000000`。

### 6.3 两类现象的差别

共同点有三条。两类现象里帧循环都出现多秒静默，静默期间没有 `tl: Q`／`tl: s`／`tl: v`。静默期间其它进程照常：`tl: p`、`tl: a`、`tl: i` 都有行，`cpufreq` 继续。静默前后的帧都是完整走完 present 的帧。

差别有两条。第一，网格洞的静默位置单一：262 个 2.9～3.1 秒间隔里有 256 个卡在 `done→w1`，恢复时以固定的五个步骤在 5～7 毫秒内完成，`shown − ready = 0`。终末阶段的静默位置分散：同一轮的相邻帧可以分别卡在 `done→w1`、`Q1→Qlast`、`w2→Q1`，`fixguard6` 还有一次 2.05 秒的 fence 等待。第二，网格洞每次都恢复，终末段的一次不恢复；13 个甲组轮里末帧停在 `done→w1` 的 3 轮、`w1→w2` 的 1 轮、`w2→Q1` 的 9 轮。

宽度上，甲组末帧到上一帧的间隔是 20.5 毫秒到 27.6 秒：10 轮在 1.6 秒以内，3 轮超过 3 秒（`touchdiag` 4.5 秒、`roundf-abort1` 5.3 秒、`fixguard7` 27.6 秒）。网格洞固定为 2.9～3.1 秒。

因此「两种结局」这个说法只在静默这一层成立。网格洞固定在同一处静止并恢复，永久停止的位置与帧循环当时走到哪一步有关，终末段本身还在多个子步骤上轮流停顿。现有日志不能把这两种静默归到同一个具体的等待对象。

## 7. 停止落在哪一层

### 7.1 没有新的 commit

判据取驱动自己的 commit 记录。甲组 13 轮里，末帧之后没有一条 `redwoodmetal[backboardd …]: commit N has run for`、`commit N took`、`draw of commit`、`rd in`、`rd out`。最后一条 commit 行都是末帧自己的 `commit N took … over K recorded works`，例如 `roundc` 的 `commit 3611 took 48 ms over 38 recorded works`、`fixguard6` 的 `commit 3616 took 223 ms over 115 recorded works`。

乙组有 `tl: cnt` 的轮次给出另一份读数：末帧之后心跳继续，`hb_commit` 只在紧接末帧的那一条里非零（末帧后 0.04～1.45 秒，1～11 条；`diag3x-cavbl` 在 +38.8 毫秒报 1，`diag3x-tcslow` 在 +49.4 毫秒报 8），其余各项到日志结束全为 0。`diag3x-fd6inner` 另有一条：+16.81 秒的心跳报 1，与 +16.075 秒的 6 条 `tl: Q` 在同一段。`diag3x-statefault` 的最后一条是 `tl: cnt 0 0 0 0 0 357191495`，距末帧 23.2 秒。心跳由用户态驱动的看门线程打印，统计上一条心跳之后进入的 commit。

驱动还有一条 commit 看门狗：commit 超过 2.5 秒没有推进就打印 `commit N has not moved for M ms inside …` 并请求线程转储。全部 121 轮里 24 轮有这一行，17 轮在末帧之前，7 轮在末帧之后。末帧之后的 7 条里 5 条报的是 SpringBoard 的 `commit 3`（`fixguard6`、`nochronod`、`perf1`、`poster-stores`、`pid-copybox`），与桌面帧无关；另外 2 条是 backboardd 的下一笔 commit（`diag3x-fd6inner` 的 882、`pid-sustain-fix` 的 3609），见 §7.2。甲组末帧之后没有 backboardd 的看门狗行，这一条把「甲组有一个 commit 卡在半路」排除在停止时刻之外。

### 7.2 两次「发起后没有回来」

`diag3x-fd6inner` 在末帧后 1.8 与 6.8 毫秒打了两条 `tl: w`（都是 `0x80000001`），16.073 秒时打了第三条 `0x80000000`，随后连续 6 条 `tl: Q`（fence 962～967，进程 `backboardd`），此后到轮末再无 `tl: f`／`tl: s`／`tl: v`。`pid-sustain-fix` 在末帧后 14.0 毫秒一条 `tl: w`，0.454 秒后 9 条 `tl: Q`（fence 3644～3652），此后再无 `tl: f`／`tl: s`／`tl: v`。

两轮的 commit 看门狗随后各报一条。`diag3x-fd6inner` 的 `commit 882 has not moved for 2667 ms inside a recorded work` 出现在末帧后 18.76 秒，报出时刻在 394,682,610～394,690,514 之间，减去 2,667 毫秒得到最后一次推进在 392,015,610～392,023,514，与最后一条 `tl: Q` 的 392,016,237 对齐。`pid-sustain-fix` 的 `commit 3609 has not moved for 3015 ms inside a recorded work` 出现在末帧后 3.47～3.48 秒，报出时刻在 241,724,794～241,733,755 之间，减去 3,015 毫秒得到最后一次推进在 238,709,794～238,718,755，与最后一条 `tl: Q` 的 238,712,321 对齐。

两轮都没有对应的 `commit N took`；`diag3x-fd6inner` 的 commit 882 连一条 `has run for` 都没有，`pid-sustain-fix` 的 commit 3609 有 32～135 毫秒的一组。

这两轮是「下一帧已经发起、GPU 命令已经提交，但没有走到交换交接」的唯一直接读数，看门狗把停止点落在 commit 的工作循环里。`pid-sustain-fix` 的 `tl: i` 在提交之后仍继续到 +26.7 秒，`tl: a` 到 +22.0 秒；`diag3x-fd6inner` 的 `tl: p` 到 +25.8 秒。进程与输入都没有停。

### 7.3 仍然活着的部分

- 帧循环本身：甲组 10 轮在末帧后还有一次或两次 `tl: w`；乙组 8 个 `diag3x` 轮与 `pid-sustain-align` 共 9 轮还有 9.6～25.7 秒后的 `tl: w`。`pid-q2probe`、`pid-copybox`、`unlockprobe`、`pid-perf-sustain-pid`、`pid-bomap`、`pid-copyrect`、`pid-stagingmap` 在同一时间窗里的 `tl: w` 帧 id 为 0、标量 `0x80000003`，来自另一个客户端。`tl: w` 是 SwapWait 方法入口，方法立即返回，说明帧循环至少又转了一次。
- 驱动库：乙组有 `tl: cnt` 的轮次心跳到日志结束，除紧接末帧的一条外 `hb_commit` 为 0；`framewatch` 在 `roundc`／`roundd`／`fixguard6`／`fixguard7` 里把 `still no frames` 计到 318／320／141／156 秒，`kern.redwood.frames` 没有增长。
- SpringBoard：`tl: a` 照常，末帧后 1,155 圈里 269 圈超过 1 毫秒，最长 90.7 毫秒，主循环仍在跑。
- 输入：`tl: p` 与 `tl: i` 照常，`roundc`／`roundd` 的 home 键在停止后 3.2／5.1 秒仍被驱动收到。
- GPU：SpringBoard 的 `tl: Q` 在末帧后 0.09～0.86 秒仍有提交（8 轮），GPU 命令路径可用。
- 内核：`cpufreq` 的 30 秒统计打到日志结束，`MiniIOMobileFramebuffer` 的 5 秒统计随最后一个 present 停止。

### 7.4 结论的边界

甲组的读数支持「backboardd 的帧循环没有产出下一帧」，落点在一次交换交接之前；末帧之后没有在途 commit，也没有 ≥1 毫秒的 fence 等待（`tl: f` 末条都在末帧前 0.1～0.5 毫秒），`tl: w` 的方法立即返回。`diag3x-fd6inner` 与 `pid-sustain-fix` 把落点推到 GPU 提交之后：下一笔 commit 已经进入工作循环、提交了剩余命令缓冲，随后停止推进，看门狗报出后也没有 `commit N took`。这两轮属于「发起后没有回来」，看门狗只给出 `inside a recorded work`，具体停在 draw 调用、锁还是调度里，没有读数。

## 8. 探针读数与缺口

### 8.1 `rd in` 与 `rd out`

19 个 `diag3x` 轮里 18 轮带这一对驱动行，`diag3x-injectpath` 只有一帧、没有 `rd in`／`rd out`。格式为 `redwoodmetal[backboardd 38]: rd in <commit> <work 数> <texture 数> <render>` 与 `rd out <commit> <work 数> <texture 数> <vertex 数> <color 数> <render> binds=… draw=… total=… slow=…`。

按 commit、work 数、texture 数与 render 指针配对，16 轮里每一条 `rd in` 都有同键的 `rd out`。`diag3x-segflt` 有一条 `redwoodmetal[backboardd 38]: rd in 914 7 4 0x14atl: p 2 0 52087 32768 at 582683515`，`rd in` 行被同一行的 `tl: p` 截断，没有可配对的 `rd out`，属于日志交错。`diag3x-rdpair` 用另一个驱动构建（`96fda2af`），21 条 `rd out` 都没有 `slow=` 字段、draw 时间都在 66 毫秒以上，169 条 `rd in` 只有 21 条 `rd out`；这与「这一版只在 draw 慢时打印 `rd out`」一致，缺的 `rd out` 不能读成没有返回。

最后一对都在末帧之前 6～3,473 行（`fd6entry` 6 行、`statefault` 332 行、`fd6inner` 3,473 行），末帧之后没有 `rd in` 或 `rd out`。这一族的触发条件限制了覆盖：`rd in` 只在 commit 已经跑了 50 毫秒以上时、在 draw 入口打印；末帧前的几帧没有达到这个条件，所以「末帧之后没有 rd in」不能证明下一帧没有进入 draw。

### 8.2 `stall pc`

全部 121 轮里 `redwood: stall pc` 0 行。带 draw 停顿触发的只有 3 轮：`diag3x-statefault` 2 次、`diag3x-dumponstall` 7 次、`diag3x-segflt` 2 次。原文如下。

```
diag3x-statefault: draw 103 has run for 474 ms; dumping threads
diag3x-statefault: thread dump for pid 38 refused (errno 1)
diag3x-statefault: draw 6632 has run for 341 ms; dumping threads
diag3x-statefault: thread dump for pid 38 refused (errno 1)
```

`diag3x-dumponstall` 的 7 次与 `diag3x-segflt` 的 2 次形态相同，每次后面都是 `thread dump for pid 38 refused (errno 1)`。另有 24 轮各有一条 `commit N has not moved for …` 后同样跟着拒绝行。转储请求走 `sysctlbyname("kern.redwood.thread_dump")`，内核侧的处理函数在 `hackios-xnu-kernel/xnu/files/bsd/dev/redwood_threads.c`，sysctl 声明为 `CTLFLAG_RW` 且没有 `CTLFLAG_ANYBODY`。非 root 进程写这个节点在进入处理函数之前就被拒，`errno 1` 是 EPERM。这一条是推断，需要一次以 root 运行的转储确认。

`diag3x-fddraw` 有一条约 2.42 秒的 draw（`rwa draw slow: 2420400 us in all; ... draw_vbo 2420378`），这一轮没有 `draw … has run for` 行，说明这一版 AIR 没有装每 draw 的停顿转储。

归档里的 draw 停顿转储走内核 sysctl，被拒的是这条老路径。`f69b1b8` 之后（`7b102de`）的驱动把 draw 停顿改成进程内快照：`redwoodmetal_commandbuffer.inc` 的 `rw_print_threads()` 用 `task_threads(mach_task_self())` 读本进程每个线程的寄存器，先打印 `draw %u has run for %llu ms; reading this process's threads`，随后每个线程一行 `redwood: stall pc <pc> lr <lr> fp <fp> sp <sp> (<image>) tid <tid>`，不写 `kern.redwood.thread_dump`。

commit 停顿那条路径仍然走 sysctl（同一文件里 `commit %u has not moved …` 之后调用 `sysctlbyname("kern.redwood.thread_dump", …)`），`thread dump for pid 38 refused (errno 1)` 只对这条路径成立。

下一轮装车的驱动是 `libredwoodmetal.dylib`，sha256 `529d19bf36271609afc020e20bdc080b36b9a28af62c49ec9c9323dd0a11f40e`，242,512 字节；按 `tools/k90auto/package.py` 的命令从当前工作树重编，产物逐字节相同，`strings` 里有 `redwood: stall pc`。所以「全部 121 轮 0 行」只说明归档，下一轮会出现进程内的线程快照。

### 8.3 `tl: fw`、`tl: cnt` 与构建差异

- `tl: fw`（fence 等待 ≥2 秒时打印）在全部 121 轮里 0 行。停帧前后没有出现长时间 fence 等待。
- `tl: cnt` 出现在 22 轮：`diag3x-` 前缀 19 轮（含不在乙组的 `diag3x-noinput`）、`diag3-heartbeat2`、`diag3-heartbeat3`、`diag3-one-tap`。甲组 13 轮与 `fixguard`、`pid-*` 各轮都没有这一族。甲组的「没有新 commit」只能由 commit 行与帧行推出，不能用心跳复核。
- `tl: s` 的字段随构建不同：`cf1502f5` 是 `tl: s <id> <who> at <us>`，`f055cc0a` 是 `tl: s <id> <pid> <tid> <who> at <us>`。两代都按行尾 `at` 取时间。
- `tl: f` 的字段同样两代不同：`f055cc0a` 是 `tl: f <pid> <tid> <kind> <us> at <us>`，`cf1502f5` 是 `tl: f <kind> <us> at <us>`。
- `roundc`、`roundd`、`fixguard6`、`fixguard7` 用的 AIR 构建不带 `tl: cnt` 心跳；同一批构建的 `framewatch` 与 commit 行都在。

## 9. 不能回答的部分

- 停止时线程停在哪个用户态函数。归档里 11 次 draw 停顿触发与 24 次 commit 停顿触发都拿到了拒绝，没有一份寄存器快照；下一轮的 draw 停顿由进程内快照回答（§8.2）。
- commit 停顿的转储被拒，原因是否就是 sysctl 权限。`errno 1` 与 `CTLFLAG_RW` 的声明一致，需要一次 root 下的写入确认。
- 8 个 `diag3x` 轮与 `pid-sustain-align` 在末帧后 9.6～25.7 秒的那次 SwapWait 之后会不会再出帧。这些轮在最后一次 SwapWait 之后还有 1.5～14.4 秒的日志，第二次重试没有出现。
- 15 秒网格的唤醒源，以及终末段为什么停止恢复。网格洞的锚点不在日志里，这一点与[15 秒周期跨轮统计](2026-10-29-15s-period-cross-round.md) §4 的结论一致。
- 会话复盘里「A 轮 39 秒、B 22 秒、C 21 秒、D 不到 1 秒」的具体轮次。归档里找不到能同时对上这四个数的四元组；可测的三种口径（首帧到末帧、首个触摸样本到末帧、末帧到日志末尾）在各轮的值都不相同，这一句需要会话记录本身补充轮次名。
- `roundc` 里 `commit 3611 has run for 863 ms` 与 `commit 3611 took 48 ms` 对不上。当前源码里 `commit_started` 是进程级静态变量（`redwoodmetal_commandbuffer.inc:32`），`has run for` 用它算耗时，`took` 用本次 commit 的局部起点算；源码在两次提交重叠时会打印 `commit N started while commit M was still running`，`roundc` 的日志里没有这一行。两个数为什么差 815 毫秒，现有日志不能判定。

## 10. 相关文档

- 会话复盘与当前卡点：[会话复盘](2026-10-29-session-review.md) §6
- 15 秒周期与 3 秒空洞：[15 秒周期跨轮统计](2026-10-29-15s-period-cross-round.md)
- 冻结形态与四时刻表：[冻结形态分析](2026-10-28-roundc-freeze-form.md)
- 冻结前的共同征兆：[冻结征兆对照表](2026-10-29-freeze-symptom-table.md)
- 慢 draw 的读数判据：[慢 draw 下一轮的读数判据](2026-10-29-slow-draw-reading-criteria.md)
- 下一轮方案里的停止形态判据：[下一轮方案](../plan/2026-10-29-next-round-plan.md) §3.6