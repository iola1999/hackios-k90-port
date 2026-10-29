# 15 秒空洞的起止动作（2026-10-29）

本文回答一个问题：3 秒空洞**开始**和**结束**的那一刻，日志里分别哪一条动作；29 个洞逐个看，找共同签名或明确分类。宽度、周期、洞内各族计数与已排除的解释见 [15 秒周期与 3 秒空洞的跨轮统计](2026-10-29-15s-period-cross-round.md)，本文不重复那篇已做完的统计。全部读数来自 `docs/progress/evidence/k90auto/` 下九轮归档的合并日志，本轮无设备，也没有新增代码。

## 1. 结论

**释放是同一组动作，29/29 一致。** 洞结束后的第一条日志动作全部是 `tl: w <A 帧号> 0x80000001 0 at <µs>`；第二条是同一帧号的 `0x80000000` 变体；随后是 `tl: Q`（fence 号比洞前最后一条大 1）、可选的 `tl: f`、`tl: s <B 帧号>`、`tl: v <B 帧号>`。`tl: w` 在方法入口取时间并立即返回，所以这 3 秒发生在 backboardd 调用这次 swap-wait 之前。实测。

**开始没有专属行，缺的动作是 A 帧的 `tl: w`。** A 帧的 `tl: v` 行三时刻齐全、present 已走完，它之后 3.00 秒内没有出现 A 帧的 `tl: w`。A 行之后写进日志的第一条非帧行按轮次各不相同（系统日志 11 个洞、`redwoodmetal` 8 个、`tl: a` 4 个、`tl: p` 3 个、`lsprobe` 2 个、`MiniIOSurface` 1 个），没有一条只在洞前出现的行。实测。

**分型：找不出第二种机制。** 29 个洞的进入和释放同型。差别只有三处，都不改变机制：洞内无关行的组成；14 个洞的释放里有 `tl: f`、15 个没有（GPU 等待不足 1 ms 时不打印）；k=0 的洞宽约多一拍（跨轮统计 §3.3）。实测。

**A 帧与正常帧同分布。** `done − ready` 8,433–10,726 µs，在本轮分布的 11–98 百分位、中位 53；`shown − ready` 中位 48 百分位；`tl: f` 的 fence 等待 1,453–2,361 µs、中位 17 百分位。三项都落在本轮正常范围内。A 帧的 `tl: Q` 在 29/29 洞里写 `35 buffers`，35 是本轮约 25% 帧的取值，属于 48/35 交替的相位，见 §8。实测。

**边界位于 backboardd 同一线程的两次内核调用之间。** 前后做 present 的 pid/tid 不变（15 个可读 tid 的洞全部相同：pid 38，tid 368／360／363）；洞内只有释放段那一次 GPU 提交（fence 号比洞前大 1）；SpringBoard 回合 `tl: a` 与触摸采样 `tl: p` 照常。实测。

**新读数：洞的起点落在 48/35 提交周期的固定相位上。** 落在 15 秒网格上的 36 个间隔（29 个长洞、`noinput` 的 4 个短洞、终末段 3 个短洞）都开始于一条 35-buffer 提交之后，洞前最后一条提交距该 35-buffer 段的第一条提交 998,428–1,018,289 µs。非网格的洞不在这个相位上。实测，成因未定。

## 2. 数据与读法

九轮目录与读法沿用前文 §2：每轮只用 `run/` 下的 `s000.log`～`s0NN.log` 与 `hung-held.log`，经 `tools/k90auto/summary.py` 的 `merged_log()` 合并（`log_files()` 定顺序、`overlap()` 找接点）。本文所有行号、行序都在合并日志上，行序即写入顺序，时间戳取自行尾或 `tl: v` 的三个字段。

帧行格式 `tl: v <id> ready <us> shown <us> done <us>`。洞的定义：相邻两帧 `ready` 差 ≥ 1 秒且宽度 2.9～3.1 秒；排除 `roundd` 终末的 2,947,144 µs，得 29 个。`unlockprobe` 没有这一类的洞，本文不涉及。

两代构建的 `tl: s` 字段数不同，其余族一致。`f055cc0a`（`statefault`／`noinput`／`tcslow`／`drawcall`）写 `tl: s <id> <pid> <tid> <name> at <us>`，能读出做 present 的线程；`cf1502f5`（`fixguard6`／`fixguard7`／`roundc`／`roundd`）写 `tl: s <id> <name> at <us>`，没有 tid。判 tid 是否前后相同只在四个旧构建轮里可用。

四个探针的含义取自内核源码。`tl: s` 在 `IOMobileFramebuffer::present()` 入口打印，记录本次交接的帧号、调用方与时刻；`tl: v` 在 `present()` 画完、像素进入面板内存之后打印；`tl: w` 在 `kFBMethodSwapWait` 入口打印后立即 `return kIOReturnSuccess`；`tl: Q` 在 GPU 提交路径打印，字段是 fence 号、提交进程名、时刻、`buffers`（本次绑定的 GPU 缓冲数）、`big`、`words`；`tl: f` 只在一次 GPU 等待超过 1 ms 时打印。对应位置是 `xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp` 与 `xnu/files/iokit/Kernel/RedwoodGPUSubmit.inc`。

族按行首分：`tl: v`／`tl: f`／`tl: s`／`tl: w`／`tl: Q`／`tl: p`／`tl: a`／`tl: b`／`tl: td`，以及 `RedwoodGPU`、`adreno`、`redwoodmetal`、`sbmetal`、`lsprobe`、`MiniIOMobileFramebuffer`、`MiniIOSurface`、`cpufreq`、`rwa draw`／`rwa bind`、`perf flush`、`battery`、`buttons`，其余带 `YYYY-MM-DD hh:mm:ss.ffffff+0800 <进程>[pid:tid]` 前缀的行按进程名归组。带 `at <us>` 的时间取行尾。

## 3. 洞的结束：29 个洞同一组释放动作

每个洞从 A 帧的 `tl: v` 行到 B 帧的 `tl: v` 行之间，最后一段日志行是固定的五到六条，按写入顺序：

| 次序 | 行 | 29 洞上的取值 |
|---|---|---|
| 1 | `tl: w <A> 0x80000001 0 at <us>` | 全部以 A 的帧号出现，第三字段恒为 0 |
| 2 | `tl: w <A> 0x80000000 0 at <us>` | 与上一条相隔 209～664 µs |
| 3 | `tl: Q <fence> backboardd at <us>: 48 buffers, 5 big, 1473 words` | fence 号 = 洞前最后一条 Q 的 fence 号 + 1（29/29），`buffers` 恒为 48 |
| 4 | `tl: f <pid> <tid> fence <us> at <us>` | 只出现 14 次；15 个洞里 GPU 等待不足 1 ms、不打印 |
| 5 | `tl: s <B> <pid> <tid> backboardd at <us>` | 29/29，帧号恒为 B |
| 6 | `tl: v <B> ready <us> shown <us> done <us>` | 29/29，`shown − ready` 恒为 0 |

第 5 条是 B 帧的 `tl: v` 行之前最后一条非帧行，29/29 都是它。第 1 条之前的那条行不属于这一组，按轮次是 `redwoodmetal`（10 个洞）、chronod（7 个）、`tl: p`（3 个）、iconservicesagent（3 个）、`tl: td`（2 个）、`tl: a`（2 个）、`lsprobe`（1 个）、其他（1 个）。这八类在洞外同样出现，与洞无关。

时间关系：从 A 帧 `done` 到第 1 条 `tl: w` 是 3,002,367～3,038,955 µs；从第 1 条 `tl: w` 到 B 帧 `ready` 是 3,871～7,369 µs。洞宽 = `(done − ready) + (w − done) + (B.ready − w)`，中间那一项就是这 3 秒。

同一线程：四个旧构建轮的 15 个洞里，A 的 `tl: s` 与 B 的 `tl: s` 线程号全部相同（`statefault` tid 368、`noinput` tid 360、`tcslow`／`drawcall` tid 363），pid 都是 38（backboardd）。洞内没有出现其它进程的 `tl: s`。

`tl: w` 的字段与正常帧逐字同形：`0x80000001` 在前、`0x80000000` 在后、第三字段 0。两次调用的间隔在正常帧里中位 202～224 µs、p90 345～428 µs，洞后这两次是 209～664 µs，同一量级。

## 4. 洞的开始：A 帧之后缺的是什么

洞起点 = A 帧的 `ready`。A 帧本身完整走完：`done − ready` 8,433～10,726 µs，`tl: s <A>` 存在且帧号相同，`tl: f` 的 fence 等待 1,453～2,361 µs。

洞前正常的帧循环是 `tl: s <n>` → `tl: v <n>` → `tl: w <n>` ×2 → `tl: Q` → `tl: f` → `tl: s <n+1>`。洞里照旧走到 `tl: v <A>`，缺的是 `tl: w <A>` 以及它后面的三项。正常帧从 `done` 到同一帧 `tl: w` 的中位是 3,231～4,696 µs（各轮 p90 4,268～5,323 µs），洞里的同一项是 3,002,367～3,038,955 µs。

`tl: v <A>` 之后写进日志的第一条行按轮次分散，统计见下。没有任何一族的行在 29 个洞上都出现，也没有只在这种位置出现的行。

| 第一条非帧行 | 洞数 | 例子 |
|---|---|---|
| 系统日志（chronod／iconservicesagent 等） | 11 | `chronod[56:668] Could not get attrs using bssendp ...` |
| `redwoodmetal[<进程> <pid>]: tl: cnt ...` | 8 | `redwoodmetal[SpringBoard 30]: tl: cnt 0 0 0 0 0 277615614` |
| `tl: a <woke> <commit> <done> <n>` | 4 | `tl: a 12872872811 12872883671 12872883672 10861` |
| `tl: p <...> at <us>` | 3 | `tl: p 2 0 48024 32768 at 321031740` |
| `lsprobe ...` | 2 | `lsprobe t=60 poster_stores=0 first=- poster_stores_ios16=0` |
| `MiniIOSurface: selector 54 not implemented ...` | 1 | 见下 |

`MiniIOSurface` 那一例是 `fixguard6` k=0：`tl: v 737` 之后紧跟 `MiniIOSurface: selector 54 not implemented (scalars 0 in, 0 out; structure 468 in, 0 out)` 与 `kIOSurfaceMethodSetCoreVideoBridgedKeys failed: e00002c7`。这两条每轮各只出现一次，位置在首帧之后 28.4～36.0 秒；8 轮里有 5 轮落在某个洞里、3 轮落在洞外，且落在洞外时同一对错误行没有引起停顿。它是首洞附近的一次性 IOSurface 能力探测，与释放序列无关。

## 5. 逐洞表

「洞内行数」是 A 的 `tl: v` 行与 B 的 `tl: v` 行之间非空行的条数。「首行」是 A 之后第一条非帧行所属的族，「末行」是释放第 1 条之前最后一条行所属的族。29 行都取自合并日志原文。

| 轮次 | k | A→B | 宽度（µs） | 洞内行数 | 首行族 | 末行族 | 释放 fence 号 − 洞前 | fence 等待（µs） |
|---|---|---|---|---|---|---|---|---|
| statefault | 0 | 634→635 | 3,052,258 | 451 | `tl: p` | `tl: p` | +1 | 无（<1 ms） |
| noinput | 0 | 731→732 | 3,036,740 | 43 | 系统日志 | `redwoodmetal` | +1 | 无 |
| noinput | 1 | 1450→1451 | 3,048,667 | 95 | 系统日志 | `redwoodmetal` | +1 | 2,291 |
| noinput | 2 | 2169→2170 | 3,035,143 | 85 | `lsprobe` | `redwoodmetal` | +1 | 2,376 |
| noinput | 3 | 3626→3627 | 3,016,943 | 18 | `redwoodmetal` | `redwoodmetal` | +1 | 无 |
| noinput | 4 | 4346→4347 | 3,018,886 | 15 | `redwoodmetal` | `redwoodmetal` | +1 | 2,352 |
| noinput | 5 | 5066→5067 | 3,017,081 | 17 | `redwoodmetal` | `redwoodmetal` | +1 | 2,370 |
| noinput | 6 | 6524→6525 | 3,019,358 | 111 | `iconservicesagent` | 系统日志 | +1 | 无 |
| noinput | 7 | 7244→7245 | 3,033,378 | 24 | `redwoodmetal` | `iconservicesagent` | +1 | 2,580 |
| noinput | 8 | 7963→7964 | 3,032,870 | 26 | `redwoodmetal` | `redwoodmetal` | +1 | 2,574 |
| noinput | 9 | 9420→9421 | 3,019,511 | 18 | `redwoodmetal` | `redwoodmetal` | +1 | 无 |
| noinput | 10 | 10140→10141 | 3,017,625 | 16 | `redwoodmetal` | `redwoodmetal` | +1 | 2,311 |
| noinput | 11 | 10860→10861 | 3,017,597 | 13 | `redwoodmetal` | `redwoodmetal` | +1 | 2,571 |
| tcslow | 0 | 721→722 | 3,051,660 | 441 | `tl: p` | `tl: p` | +1 | 无 |
| drawcall | 0 | 660→661 | 3,053,745 | 458 | `tl: p` | `tl: p` | +1 | 无 |
| fixguard6 | 0 | 737→738 | 3,017,887 | 63 | `MiniIOSurface` | 系统日志 | +1 | 无 |
| fixguard6 | 1 | 1452→1453 | 3,017,959 | 79 | 系统日志 | `other` | +1 | 无 |
| fixguard6 | 2 | 2172→2173 | 3,015,492 | 99 | 系统日志 | `tl: td` | +1 | 2,585 |
| fixguard6 | 3 | 2892→2893 | 3,015,427 | 22 | 系统日志 | `tl: a` | +1 | 2,582 |
| fixguard7 | 0 | 731→732 | 3,033,297 | 63 | 系统日志 | `iconservicesagent` | +1 | 无 |
| fixguard7 | 1 | 1448→1449 | 3,034,565 | 97 | `iconservicesagent` | 系统日志 | +1 | 无 |
| roundc | 0 | 730→731 | 3,051,688 | 60 | `tl: a` | 系统日志 | +1 | 无 |
| roundc | 1 | 1449→1450 | 3,034,773 | 100 | 系统日志 | 系统日志 | +1 | 2,336 |
| roundc | 2 | 2165→2166 | 3,034,974 | 104 | `tl: a` | `tl: td` | +1 | 无 |
| roundc | 3 | 2885→2886 | 3,017,339 | 14 | `tl: a` | 系统日志 | +1 | 2,568 |
| roundd | 0 | 736→737 | 3,016,586 | 60 | `iconservicesagent` | `iconservicesagent` | +1 | 无 |
| roundd | 1 | 1456→1457 | 3,016,845 | 105 | 系统日志 | 系统日志 | +1 | 2,581 |
| roundd | 2 | 2175→2176 | 3,018,666 | 101 | `lsprobe` | `lsprobe` | +1 | 无 |
| roundd | 3 | 2895→2896 | 3,017,542 | 15 | `tl: a` | `tl: a` | +1 | 2,566 |

洞内行数的跨度是 13～458 行，差别来自触摸轮（每洞 381 条 `tl: p`）与 `lsprobe`／`tl: td` 的整段转储，与洞本身无关。29 个洞里 `tl: w` 各 2 条、`tl: Q` 各 1 条、`tl: s` 各 1 条，全部在释放段内；`tl: v` 各 0 条。

## 6. 边界原文两例

**例一，`noinput` k=1（帧 1450→1451，宽 3,048,667 µs）**。20 行按原样照抄，超过 200 字符的行截断并标注。

A 之前的 20 行：

```
tl: s 1447 38 360 backboardd at 277470250
tl: v 1447 ready 277470297 shown 277477780 done 277478983
tl: w 1447 0x80000001 0 at 277483357
tl: w 1447 0x80000000 0 at 277483594
tl: Q 1461 backboardd at 277484530: 35 buffers, 5 big, 1473 words
tl: f 38 360 fence 2301 at 277486847
tl: s 1448 38 360 backboardd at 277486885
tl: v 1448 ready 277486932 shown 277494390 done 277495598
tl: w 1448 0x80000001 0 at 277500021
tl: w 1448 0x80000000 0 at 277500220
tl: Q 1462 backboardd at 277501154: 35 buffers, 5 big, 1473 words
tl: f 38 360 fence 2297 at 277503466
tl: s 1449 38 360 backboardd at 277503501
tl: v 1449 ready 277503548 shown 277511009 done 277514242
tl: w 1449 0x80000001 0 at 277516712
tl: w 1449 0x80000000 0 at 277517120
tl: Q 1463 backboardd at 277519508: 35 buffers, 5 big, 1473 words
tl: f 38 360 fence 2326 at 277521871
tl: s 1450 38 360 backboardd at 277521956
tl: a 277514449 277524867 277524867 10418
tl: v 1450 ready 277522015 shown 277527659 done 277530847
```

洞内共 95 行，按族：`chronod` 50、`iconservicesagent` 20、`redwoodmetal` 7、`other` 7、`tl: a` 4、`battery` 1、`tl: b` 1，其余 5 行是释放段。洞尾的释放段原文：

```
tl: w 1450 0x80000001 0 at 280566704
tl: w 1450 0x80000000 0 at 280567103
tl: Q 1464 backboardd at 280568224: 48 buffers, 5 big, 1473 words
tl: f 38 360 fence 2291 at 280570578
tl: s 1451 38 360 backboardd at 280570633
tl: v 1451 ready 280570682 shown 280570682 done 280571903
```

B 之后的 20 行：

```
tl: w 1451 0x80000001 0 at 280583356
tl: w 1451 0x80000000 0 at 280583612
tl: Q 1465 backboardd at 280584590: 48 buffers, 5 big, 1473 words
tl: f 38 360 fence 2602 at 280587213
tl: s 1452 38 360 backboardd at 280587250
tl: v 1452 ready 280587301 shown 280588230 done 280589438
tl: w 1452 0x80000001 0 at 280600025
tl: w 1452 0x80000000 0 at 280600272
tl: Q 1466 backboardd at 280601260: 48 buffers, 5 big, 1473 words
RedwoodGPU: buffers: 0 made in 0 us each (0 getting the memory, 0 waiting for the GPU lock; 0 under 64 KB, 0 under 1 MB, 0 under 8 MB, 0 larger), 0 kept ones given again (1 MB kept)
RedwoodGPU: 119 submissions in 5000 ms: 1149 us each in the kernel, 40 of them waiting for room in the queue; 119 command buffers and 4919 buffers named, 10896 KB out of the cache in 1019 us a submission
RedwoodGPU: the GPU worked 1689 us on each of 119 (0 under 0.1 ms, 0 under 0.25, 0 under 0.5, 0 under 1, 119 under 2, 0 under 4, 0 longer; 201 ms in all)
RedwoodGPU: 119 waits of 2429 us, 0 over before they began; 0 IOSurfaces taken as buffers in 0 us each; 155 buffers, 85 MB
RedwoodGPU: GPU at 160 MHz, 2 speed changes since it started
tl: f 38 360 fence 2612 at 280603930
tl: s 1453 38 360 backboardd at 280603970
tl: v 1453 ready 280604015 shown 280605661 done 280606881
tl: w 1453 0x80000001 0 at 280616695
tl: w 1453 0x80000000 0 at 280616937
tl: Q 1467 backboardd at 280617907: 48 buffers, 5 big, 1473 words
```

**例二，`statefault` k=0（帧 634→635，宽 3,052,258 µs）**。这一轮有触摸采样，洞内 451 行里 381 条是 `tl: p`。A 之前 20 行里每帧都带一条 `tl: p`，帧循环不变：

```
tl: Q 644 backboardd at 320984572: 35 buffers, 5 big, 1473 words
tl: f 38 368 fence 1460 at 320986046
tl: s 632 38 368 backboardd at 320986079
tl: p 2 0 47893 32768 at 320991704
tl: v 632 ready 320986125 shown 320993705 done 320994965
tl: w 632 0x80000001 0 at 321000024
tl: w 632 0x80000000 0 at 321000228
tl: Q 645 backboardd at 321001246: 35 buffers, 5 big, 1473 words
tl: f 38 368 fence 1509 at 321002774
tl: s 633 38 368 backboardd at 321002871
tl: p 2 0 47919 32768 at 321004204
tl: p 2 0 47945 32768 at 321006663
tl: v 633 ready 321002932 shown 321010312 done 321013532
tl: p 2 0 47972 32768 at 321016022
tl: w 633 0x80000001 0 at 321016707
tl: w 633 0x80000000 0 at 321017096
tl: Q 646 backboardd at 321019708: 35 buffers, 5 big, 1473 words
tl: f 38 368 fence 1473 at 321021219
tl: s 634 38 368 backboardd at 321021304
tl: p 2 0 47998 32768 at 321022726
tl: v 634 ready 321021362 shown 321026965 done 321030206
```

释放段：

```
tl: w 634 0x80000001 0 at 324066726
tl: w 634 0x80000000 0 at 324067375
tl: Q 647 backboardd at 324070270: 48 buffers, 5 big, 1473 words
RedwoodGPU: buffers: 0 made in 0 us each (0 getting the memory, 0 waiting for the GPU lock; 0 under 64 KB, 0 under 1 MB, 0 under 8 MB, 0 larger), 0 kept ones given again (1 MB kept)
（另 4 行 RedwoodGPU 5 秒统计：submissions／GPU worked／waits／GPU 频率，原长 203～210 字符，此处省略）
tl: p 2 0 57985 32768 at 324070884
adreno8: 2 external buffers unmapped in 8081 ms, 1501 us waiting for the GPU to be idle in all
adreno8: 2 external buffers unmapped in 8081 ms, 1501 us waiting for the GPU to be idle in all
adreno8: page tables published 2 times in 8081 ms: 96 bytes cleaned, 0 us cleaning and 3 us in all on average
adreno8: page tables published 2 times in 8081 ms: 96 bytes cleaned, 0 us cleaning and 3 us in all on average
tl: s 635 38 368 backboardd at 324073559
tl: v 635 ready 324073620 shown 324073620 done 324076853
```

B 之后 20 行的开端是两条 `MiniIOMobileFramebuffer: N frames in N ms` 5 秒统计，然后是 `tl: w 635` 两次、`tl: Q 648 backboardd at 324086714: 48 buffers, 5 big, 1473 words`、`tl: f 38 368 fence 1475 at 324088240`、`tl: s 636 ...`，与例一同一形态。

其余 27 个洞用同一格式取过 20+20。表中的首行族、末行族、fence 号差与释放段六行已覆盖它们的全部差异，逐行原文不另贴。

## 7. A 帧与正常帧的差别

百分位是在本轮的全体帧里算的，`done − ready`、`shown − ready`、`tl: f` 的 fence 等待各一条曲线。

| 读数 | A 帧范围 | 本轮正常帧 | A 帧中位百分位 |
|---|---|---|---|
| `done − ready` | 8,433～10,726 µs | 中位 8,846～9,024 µs | 53 |
| `shown − ready` | 5,157～7,813 µs | 中位 7,223～7,462 µs | 48 |
| `tl: f` fence 等待 | 1,453～2,361 µs | 中位 1,466～2,564 µs | 17 |

三项都没有落在正常范围之外。fence 等待的 17 百分位是三项里最低的一项，方向是 A 帧等 GPU 的时间比典型帧短；29 个样本里落在 0～44 百分位，本文不把它当作机制差异。

A 帧还有两项结构读数：`tl: s <A>` 全部存在且帧号相同（29/29）；`tl: Q` 的 `buffers` 在 29/29 洞里是 35，见 §8。

## 8. 分型：一组机制，一个相位签名

29 个洞按释放序列、按 A 帧特征、按洞内族组成都分不出两组。三处差异都不影响机制：洞内无关行的组成（哪些后台进程在这 3 秒里打印）；释放段里有没有 `tl: f`（14 个洞有、15 个没有，取决于 GPU 等待是否达到 1 ms）；k=0 的洞宽多约一拍，跨轮统计 §3.3 已记。

能分开的是一组**相位**事实。`tl: Q` 的 `buffers` 字段在本轮里交替取值 48 和 35，成段出现：稳定段里 48 段 179～180 条提交（约 3.0 秒），35 段 60～62 条提交（约 1.0 秒），周期 240 条提交。整轮统计里最短的段只有 1～27 条，出现在快照接缝与终末段；上面的段长只取连续出现的完整段。

| 洞类别 | 数量 | 洞前最后一条 `tl: Q` 的 buffers | 该值在本段内的位置 |
|---|---|---|---|
| 15 秒网格长洞 | 29 | 35 | 第 61～62 条 |
| `noinput` 网格短洞（k=3／7／11／15） | 4 | 35 | 第 61～62 条 |
| 终末段网格短洞（`fixguard6` 3612、`roundc` 3605、`roundd` 3615） | 3 | 35 | 第 61～62 条 |
| 启动洞 | 8 | 22 | 第 1～2 条 |
| 其余 ≥1 秒间隔（非网格、非启动） | 16 | 14／26／32／48／51／52／53／54／55／287／297／300 | 第 1～63 条，位置不定 |

36 个网格间隔的共同点：从 35 段的第 1 条提交到洞前最后一条提交是 998,428～1,018,289 µs；释放段第 3 条 `tl: Q` 是下一段 48 段的第 1 条。按位置说，洞的起点总在 35 段结束处。

35 段在洞里变长：正常一轮 35→48 的间隔约 1.0 秒，洞里的这一段是 4.0 秒，多出来的 3 秒就是没有提交的那段。48 段的长度不受洞影响（2.98～3.00 秒）。

这条相位关系只说明洞与提交计数周期同步，没有说明谁触发谁：48／35 交替在洞外照常发生（`fixguard6` 全轮 14 次 35→48，其中 4 次带洞），洞只出现在其中一部分 35 段边界上。

## 9. 能推出与不能推出

**能推出。**

1. 洞结束接上的是已经上屏那一帧的 swap-wait：帧号、第二字段、第三字段与正常帧逐字相同，GPU fence 号连续，没有丢帧或重提交。
2. 洞开始时内核的 present 路径已经走完：A 帧的 `tl: v` 三时刻齐全，`done` 在 `ready` 之后 8.4～10.7 ms，与正常帧同一分布。
3. 停顿发生在 backboardd 的显示循环里：同一 pid、同一 tid 做洞前的 present 和洞后的 swap-wait；洞内除释放段外没有该进程的 `tl: Q`、`tl: s`、`tl: v`；SpringBoard 的 `tl: a` 与输入线程的 `tl: p` 照常。
4. 停顿的边界可以卡到两个内核调用之间：`tl: v` 在 `present()` 画完、像素进入面板内存之后打印，`present()` 之后还要走完 5 秒统计块才返回；`kFBMethodSwapWait` 一进入就打印并立即返回。3 秒落在 `present()` 返回之后、`swap_wait` 被调用之前，或者落在 `tl: v` 打印之后到 `present()` 返回之间的尾部，这两种切分日志本身分不开（洞内 0 条 `MiniIOMobileFramebuffer` 统计行，A 帧 present 的统计块没有在洞里打印过，也没有给出「present 已经返回」的直接读数）。

**不能推出。**

1. 这 3 秒具体在等什么。日志里没有任何一条带时间戳的行落在这段窗口内属于 backboardd 的路径上；能看到的只是同一进程没有发起新的 framebuffer 调用。
2. 有没有别的内核调用（不在探针范围内的 `mach_msg`、`IOSurface` 等）在这 3 秒里发生。`tl: td` 的线程转储只在 4 个洞里恰好落到，且显示驱动的 tid 与洞外多数转储状态相同（state 1、wait 0），区分不了洞内外。
3. 48／35 交替与洞谁是原因。两者相位固定，样本里没有能把它们分开的轮次。
4. 3.0 秒这个时长由什么决定。宽度已在前文量化到 181／182／183 个显示节拍，但节拍之外的常数项没有单独读数。

## 10. 没做成的部分

- `unlockprobe` 不在本文范围内：它没有 2.9～3.1 秒的洞，它的 8.35～8.76 秒空洞没有对应的 A／B 帧对可套用本文的释放判定。
- `tl: td` 的 pc 没有做符号化。四个洞的转储里，backboardd 的高优先级线程都停在减 slide 后同一个地址 `0x232f09cd4`，即 `libsystem_kernel.dylib+0xcd4`（`svc` 之后的 `ret`），与同一份转储里大量空闲线程同一个 pc；`noinput` 里做 present 的 tid 360 也是这个值（`pc 0x23b30dcd4`，slide `0x8404000`）。本轮没有据它判定等待对象。
- 27 个洞的 20+20 逐行原文没有写进本文件，只在 §5 的表里保留首行族、末行族与释放段读数。需要逐行原文时按 §2 的读法与 §5 的帧号重取。