# 设备回来后的下一轮实验方案（2026-10-29）

这份方案写设备从 USB 消失之后的第一轮怎么起、这一轮取哪些读数、按什么判据读，以及由这一轮结果决定的后续动作。所有判据写在读数到手之前。文中「实测」指今天在宿主机上读到的文件、哈希与源码，「推断」指由这些读数推出、还没有真机验证的部分。设备在 2026-10-29 13:42 前后从 USB 消失，恢复只能由人长按电源键。

## 1. 设备恢复的顺序

### 1.1 长按电源之后先只做枚举

恢复从枚举开始，先看清设备以哪种身份出现，再决定发哪条命令。上一次掉线前的最后几秒里，序列号为空的设备收到过一次 `adb reboot bootloader`，返回 `unknown command`，此后四路枚举连续为空。

- 长按电源键之后等 30 秒，再跑 `fastboot devices` 与 `adb devices` 两条只读命令。
- `adb devices` 列出一行而序列号读不出来时按未枚举处理，除轮询外不发任何命令。判据是能原样读出序列号。
- 枚举只用 `fastboot devices`。不要对尚未出现的 `xnuloader` 发 `fastboot -s xnuloader …`，那条命令会进入等待并挂成后台客户端，卡住同一设备的命令通道。
- 五分钟内两侧都为空，停在这里报用户，不重复长按，也不试其它按键组合。

### 1.2 认清身份后记下这些字段

| 身份 | 判别 | 必须记下的字段 |
|---|---|---|
| Android | `adb -s "${ANDROID_SERIAL}" get-state` 答 `device` | `sys.boot_completed`、`ro.boot.slot_suffix`、`dumpsys battery` 的电量与温度 |
| LK fastboot | `getvar product` 答 `annibale` 且 `getvar is-userspace` 答 `no` | `current-slot`、`slot-retry-count:a`、`slot-retry-count:b`、`slot-unbootable:a`、`slot-unbootable:b`、`slot-successful:b`、`build-id` |
| 驻留 loader | `fastboot devices` 出现 `xnuloader` | `product`、`result`、`ramdisk-state`、`build-id`、`ramdisk-protocol` |

这些字段是这一批能不能起轮的依据。`slot-retry-count:a` 决定还能跑几轮，每起一次 loader 扣 2。`slot-unbootable:a` 与 `current-slot` 说明掉线之后有没有回退到 B 槽。`ramdisk-state` 非空说明上一轮的内核没有正常收尾。`build-id` 用来对上下一次枚举到的是不是同一份 loader。

### 1.3 进 loader 的条件与动作

四条全部满足才继续：能在 LK 侧执行 `set_active a`（设备在 LK 或还在 Android），`slot-unbootable:b` 答 `no`，1.2 的字段已经记完，同一时刻没有其它主机任务占用 USB。

```sh
adb -s "${ANDROID_SERIAL}" reboot bootloader
fastboot -s "${ANDROID_SERIAL}" getvar product
fastboot -s "${ANDROID_SERIAL}" set_active a
fastboot -s "${ANDROID_SERIAL}" reboot
fastboot devices
fastboot -s xnuloader getvar result
fastboot -s xnuloader getvar ramdisk-state
```

`set_active a` 同时把 `slot-retry-count:a` 复位到 7、把 `slot-unbootable:a` 清回 `no`，所以恢复之后的第一轮从满预算开始。设备回来时已经停在 loader 的情形有过一次记录：10-29 16:37 设备在安卓且核过可用，16:40 再查时 `adb devices` 为空、`fastboot devices` 列出 `xnuloader`，A 槽在这三分钟内被切过并复位过一次。这种情形先读 `result`、`ramdisk-state`、`product` 三项，再用 `tools/k90auto/reboot-lk.py <新目录> --return-loader` 走一次到 LK 的往返，在 LK 侧补齐 1.2 的槽位字段。

### 1.4 恢复失败的停止条件

三条任一条成立就写标记文件、报用户，不自行 `reboot`、不换槽重来：loader 在 3 分钟内没有枚举出来；`result` 不是 `idle` 或 `ramdisk-state` 不是 `idle 0 0 0`；`set_active a` 之后读回的计数不是 7，或 `slot-unbootable:a` 仍是 `yes`。

## 2. 第一轮的载荷与探针组合

### 2.1 身份与取处

| 项 | 值 | 取处 |
|---|---|---|
| 内核 | `f055cc0a928e6b3a69f1043a419105362a71ea46ac1789e05387dea1db54c2c3`，20,226,616 字节 | `hackios-xnu-kernel/out/xnu12377-f055cc0a-restored.bin`，与 `out/xnu12377/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837` 同哈希 |
| AIR | `57fdb85c38bcf6892de3394ffa184963d881a99a091dae828c85dba5cb22e8eb`，14,051,376 字节 | `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/libredwoodair.dylib`，同时记在 `tools/k90auto/library-baseline.json` 的 `air_sha256` |
| 驱动 | `529d19bf36271609afc020e20bdc080b36b9a28af62c49ec9c9323dd0a11f40e`，242,512 字节 | 同目录 `libredwoodmetal.dylib`；`package.py` 每次从 `hackios-xnu-kernel/tools/userland-driver/` 现编，编出来的哈希与 baseline 不符就拒绝打包 |
| 注入库 | `1d7278335752c53cee5e43294136f52ddafb6442b542aa9db61258372911421b`，91,232 字节 | `hackios-xnu-kernel/userland/root/lib/libredwood.dylib`；源码 `hackios-xnu-kernel/userland/src/inject.c` 为 `e71cdc00eac7e6f7fb986c6525ccbad429861b204576c54c1585bf8fb5a7f224`，`package.py` 只拷贝不重编 |
| 系统盘 | `d11083be02820507f5639e0a29c6f35256a48d1d4f3cf4cd265eb4b8e346efe4`，4,925,816,832 字节 | `hackios-xnu-kernel/userland/system26.apfs` |
| 基础 root | `33ed5fc9cb18367c124e6fd26a2fc982f7d80b3a44e04754f87cf74b5aa381f0`，5,156,864 字节 | `hackios-xnu-kernel/out/ios26-resume/air-arm64e-device/on/root.apfs`，`package.py` 的 `base_root_sha256` |
| 作业 | `16462e32fe0c47f3df95fd17124d589c64c2b77cba08b7e471503c762d986248` | `tools/k90auto/jobs/rc.jobs.perf-sustain`，与 `statefault` 轮同一份 |

上面七项今天逐个读过（实测）。内核记录用 `docs/progress/evidence/k90auto/kernel-12377-attr26-diag3x/kernel.json`，它指向 `out/xnu12377-f055cc0a-restored.bin`。同级的 `kernel-12377-attr26/kernel.json` 还写着 `cf1502f5…` 与 20,210,232 字节，`make-payload.py` 的第一条断言会拒绝它，不要拿它当 `NAME`。

### 2.2 打包与校验

```sh
cp -a hackios-xnu-kernel/out/ios26-resume/bbmetal-device hackios-xnu-kernel/out/ios26-resume/bbmetal-device-1029n1
JOBS_SOURCE=tools/k90auto/jobs/rc.jobs.perf-sustain GPU_SPEED=3 python3 tools/k90auto/package.py
MEMSIZE=300000000 IDENTITY=v57 JOBS_SOURCE=tools/k90auto/jobs/rc.jobs.perf-sustain GPU_SPEED=3 \
  python3 tools/k90auto/make-payload.py 12377-attr26-diag3x statecursor2 out/ios26-resume/bbmetal-device/root.apfs "gpu_log=1 metal=1 cpufreq=1 fb_threads=2 touch_lat=1"
```

第一行是备份，因为 `package.py` 会覆盖 `bbmetal-device/` 下的 root 与清单，而那份 AIR 二进制没有第二份。备份已在 2026-10-29 离线期间做好，目录是 `bbmetal-device-1029n1`，AIR 哈希复核为 `57fdb85c…`，起轮时跳过第一行：目标目录已存在时再执行 `cp -a` 会在它下面生成一层 `bbmetal-device/`。`package.py` 现编驱动，AIR 只拷不编。作业用 `perf-sustain` 而不用默认的 `rc.jobs.desktop`：产生那 24 条慢 draw 的 `statefault` 轮用的就是这一份，换掉作业就换了要解释的现象。

```sh
python3 hackios-xnu-kernel/tools/apfs/apfs.py cat hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs /lib/libredwoodair.dylib | shasum -a 256
python3 hackios-xnu-kernel/tools/apfs/apfs.py cat hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs /lib/libredwoodmetal.dylib | shasum -a 256
python3 hackios-xnu-kernel/tools/apfs/apfs.py cat hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs /lib/libredwood.dylib | shasum -a 256
python3 hackios-xnu-kernel/tools/apfs/apfs.py cat hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs /etc/rc.jobs | shasum -a 256
```

四项与轮次 `manifest.json` 的 `pack` 段逐项相等才起轮，`/etc/rc.jobs` 的哈希应当是 `16462e32…`。打包之前再核对四条格式串还在各自的库里，一条不在就停：AIR 的 `fd draw state segs` 与 `fd bo prefault slow`，驱动的 `redwood: stall pc`，注入库的 `tl: b`。

### 2.3 这一轮同时回答的问题

| 问题 | 探针 | 行 | 触发条件 |
|---|---|---|---|
| 慢 draw 停在 `state` 段的哪一步 | `state` 分段游标 | `fd draw state segs: total … <段名> <µs>` | `total` > 50,000 µs |
| 同一段的总墙钟、CPU 与缺页 | 分段计时 | `fd draw seg slow: state wall … cpu … flt … us` | `wall` > 50,000 µs |
| 首次映射的预落页花了多少 | 预落页 | `fd bo prefault slow: %p %u bytes %llu us` | ≥ 5,000 µs |
| 慢 draw 那一刻各线程在哪 | 进程内线程快照 | `redwood: stall pc … (%s) tid %llu` | 一次 draw ≥ 300,000 µs，每 draw 一份 |
| 3 秒洞里 backboardd 主循环是否在转 | 主循环观察器 | `tl: b WOKE COMMIT DONE` | 需要 `touch_lat=1` |
| 驱动侧同一时刻在做什么 | 看门线程与绘制外层 | `tl: cnt …`（每 1 秒）、`rd in`／`rd out … draw=… slow=…` | 心跳常开；`rd` 行在 `draw` > 50,000 µs 或 `rd in` 已打时出现 |

六组探针在同一份 AIR、同一份驱动、同一份注入库里，一轮取完。这一轮相对上一轮换了 AIR（`04f25e4c…` 换成 `57fdb85c…`）与驱动（`86867766…` 换成 `529d19bf…`），内核与注入库没变。读这一轮时不能把它当成预落页的开关对照，预落页在这一版里常开。

### 2.4 起轮

前置条件是设备停在 idle loader（`result` 答 `idle`、`ramdisk-state` 答 `idle 0 0 0`），轮次目录由 `make-payload.py` 建好并且打印出来的路径就是下面这一条。

```sh
python3 tools/k90auto/round-run.py docs/progress/evidence/k90auto/kernel-12377-attr26-diag3x-statecursor2 420
```

`round-run.py` 起轮前读一次 `slot-retry-count:a`，低于 3 就停下，先按 §5.2 复位。每个尝试都是一次完整的 `run-auto.py`，收尾把设备带回 idle loader。`run-auto.py` 在帧流停止 20 秒后提前收尾（`K90_FREEZE_SECONDS` 默认 20），`statefault` 轮因此在 70.06 秒结束，这一轮也可能提前结束，收尾时间不参与判据。

## 3. 读数与判据

### 3.1 判据零：这一轮算不算数

- 五项身份从轮次 root 实算，与 §2.1 逐项相等。
- 日志里有 `redwood lib loaded pid <n> name backboardd`，注入在 backboardd 里跑起来了。
- 日志里有 `redwoodmetal[backboardd` 一类的驱动行，驱动加载成功。
- `fd draw calls` 计数打到 1,000 以上，分段探针在跑（`statefault` 打到 8,000）。
- `tl: cnt` 每 1 秒一行、整轮不断，看门线程在跑。
- 至少 1 条 `fd draw seg slow: state`。0 条按 §4.3 处理，不能读成「这一轮没有慢 draw 现象」。

### 3.2 判据一：`state` 段内的落点

量是每一对相邻打印的 `fd draw state segs` 与 `fd draw seg slow: state` 两行。五段依次是 `vsc_sizes`、`prog_state`、`fixup_state`、`cs_begin`、`emit_3d_state`，`T` 取 segs 行的 `total`，`W` 取 slow 行的 `wall`。

五段之和恒等于 `T`：`cursor` 从 `entry.wall` 起，每个 `mark()` 之后推到当次读数，`total` 就是最后一个 `mark()` 减 `entry.wall`。可算的两个量是各段占 `T` 的份额 `s_i`，以及 `W − T`，后者是最后一个 `mark()` 到取 `now` 之间的时间。

| 判据 | 通过条件 | 结论 |
|---|---|---|
| D1 | 存在 `s_i` ≥ 0.60 | 落点在该段，按 §4.1 走 |
| D2 | 所有 `s_i` < 0.40 | 落点分散，按 §4.2 走 |
| D3 | `W − T` ≥ 0.30 × `W`，或 slow 行前面没有配对的 segs 行 | 落点在 `emit_3d_state` 之后、取 `now` 之前的那几条语句上 |

配对规则按相邻行，不按时间：`say_state()` 与 `fd_draw_seg_say("state", …)` 在源码里前后相邻调用，segs 行紧贴在 slow 行前面。`T` ≤ 50,000 而 `W` > 50,000 时只有 slow 行，这种样本本身满足 D3。旧判据文档 §3.2 里「各段都小、`total` 大」那一行在构造上不可达，这次换成 D1／D2／D3。

### 3.3 判据二：首次落页的成本落在哪一段里

量是 `fd bo prefault slow: %p %u bytes %llu us`。页数 `n = ceil(bytes / 4096)`，单页成本 `c = us × 4096 / bytes`。预落页在 `__fd_bo_map` 里执行，第一次映射发生在哪一段之内，这笔成本就还在那一段里。

| 判据 | 通过条件 | 结论 |
|---|---|---|
| P1 | 与某条 `state` 慢 draw 同一秒内的 prefault 行，`us` 之和 ≥ 0.20 × `W` | 首次落页在这一段里有可观的量；预落页把缺页换成了显式触碰，成本没有离开这一段 |
| P2 | 0 条，或 `us` 之和 < 0.05 × `W` | 首次落页解释不了这一段，落点在别处 |
| P3 | 出现 `fd bo prefault slow` 而该窗口内没有慢 draw | 成本已经搬到映射时刻，这一段没有受到影响，按 P2 记 |

单页成本 `c` 是派生量，照抄原始 `bytes` 与 `us` 两个数，不四舍五入。

### 3.4 判据三：慢 draw 那一刻线程在哪

量是 `draw <n> has run for <m> ms; reading this process's threads` 之后每个线程一行 `redwood: stall pc <pc> lr <lr> fp <fp> sp <sp> (<image>) tid <tid>`。触发条件是 `render_draw` 超过 300,000 µs，每次 draw 最多一份。

| 判据 | 通过条件 | 结论与动作 |
|---|---|---|
| S1 | 绘制线程的 pc 落在 `libsystem_kernel` | 睡在系统调用。用 `python3 tools/k90auto/stubsym.py --slide <slide> --pc <pc>` 解名，按名字分流 |
| S2 | pc 落在 `libredwoodair.dylib` 或 `libredwoodmetal.dylib` | 在库内等待。把 pc 减 slide 后用 `nm -n` 反解到函数与偏移 |
| S3 | 一份 dump 都没有 | 快照没有触发（这一轮没有 ≥300 ms 的 draw，或驱动没加载）。不能读成「线程没有睡」 |

`stubsym.py` 的默认 `--load`（`0x232f09000`）与 `--file-off`（`0x6661000`）是按 `.46` 子缓存量的，解出的名字与 pc 所在库对不上时先核这两个参数，再采信名字。slide 取同一次线程 dump 里的 `tl: td <pid> slide <0x…>` 行。绘制线程按 pc 落在 `libredwoodair.dylib` 那一条认。

### 3.5 判据四：3 秒洞里谁还在动

洞的算法沿用[15 秒周期统计](../analysis/2026-10-29-15s-period-cross-round.md)：相邻两帧 `tl: v` 的 `ready` 差 ≥ 1 秒。洞宽与 15 秒网格那一套不在这里重复。

| 判据 | 通过条件 | 结论 |
|---|---|---|
| H1 | 每条 ≥ 1 秒的洞内 `tl: b` ≥ 1 条，相邻 `tl: b` 的 `WOKE` 差中位 ≤ 30 ms | 主循环在转，帧没有被发起，阻塞在显示链路回调一侧 |
| H2 | 洞内 0 条 `tl: b` | 主循环没有进入等待（没有醒来，或一直在跑而没有睡） |
| H3 | `tl: cnt` 在洞内每 1.0 秒 ±0.1 秒一条 | 驱动的看门线程活着，进程没有死；这一条是 H1／H2 成立的前提 |

### 3.6 判据五：帧流永久停止时的形态

- 末帧之后仍有 `tl: b`：主循环在转，停的那一侧不在主循环。`statefault` 轮末帧 `done` 之后还有 12 条 `tl: b`，最后一条在 17,276,987 µs 之后。
- 末帧之后 `tl: cnt` 的 commit 计数为 0：没有新的提交发生。
- 出现 `rd in` 而同一 `commit_count` 没有对应的 `rd out`：停在那一次 draw 里没有返回，这是比超时更有信息的一条。
- 以上三条都没有、`tl: cnt` 也停了：进程或驱动线程不在了，先查 `died`／`exited`。

### 3.7 取法与去重

- 八份以内的 `s0*.log` 与 `hung-held.log` 是同一条控制台流的累积拷贝，按最长后缀重叠合并，再按行去重。
- `fd draw seg slow` 与 `fd draw state segs` 按整行去重；同一秒里的 prefault 行不去重，按 `%p` 与 `us` 逐条记。
- 帧号与时间取 `tl: v` 的 `ready`，与归档里的其它轮同口径。

## 4. 结果分支

### 4.1 结果 A：分段给出唯一落点

条件是 D1 成立。下一轮的动作固定为：在 `hackios-xnu-kernel/out/ios26-resume/mesa-arm64e/mesa-26.2.5/src/gallium/drivers/freedreno/a6xx/fd6_draw.cc` 里，把命中那一段按调用点再插 3 到 5 个 `mark()`，段名用调用名，同一份改动另存为 `hackios-xnu-kernel/tools/mesa/fd6-state-segs-2.patch` 备查；随后用 `tools/k90auto/build-air.py` 重编并签名。作业、内核、驱动、注入库一律不动，只换 AIR。

新 AIR 的哈希与 `library-baseline.json` 的 `57fdb85c…` 不同，打包时用 `UPDATE_BASELINE=1` 把新值写进 baseline，并在轮次注记里写新旧两个哈希。期望的读数是同一作业下出现 ≥ 60% 的单一子段。子段仍然分散时，落点按 D2 处理，转 §4.2。

### 4.2 结果 B：分段分散，或快照指向系统调用

条件是 D2 成立，或 S1 成立。下一轮按 `stubsym.py` 解出的系统调用名分三路，写死：

- 等锁（`psynch_cvwait`、`ulock_wait`、`ulock_wait2` 一类）：在驱动里给这把锁的地址加一行打印，下一轮看同一个地址上有谁持有。
- 等 mach 消息（`mach_msg2_trap`、`mach_msg_trap` 一类）：先打发送方与端口名，再定对端。
- 等映射或 I/O（`mmap`、`madvise`、`IOConnect…` 一类）：按判据二的结果走，先做预落页开关，这要新编一版 AIR。
- 解不出名字：先核 `stubsym.py` 的两个缓存参数，再决定，不按猜测分流。

### 4.3 结果 C：这一轮没有慢 draw，或帧流没有起来

条件是判据零任一条不成立，或 `fd draw seg slow: state` 0 条。

- 先按判据零逐条查是哪一条不成立，不换载荷重跑。
- `fd draw calls` 计数正常而慢 draw 0 条：把作业换成 `rc.jobs.desktop`，同一份库再跑一轮，作业是这一轮的唯一变量。
- `tl: v` 帧数不到 100：按 §1 重做一次检查点，再起一轮；两轮都不行就停。
- 出现 `bad access` 且 pc 落在 `fd_bo_prefault`：预落页的写触碰到了只读映射，停下报用户，这一版 AIR 不再上机。

### 4.4 几组读数同时成立时

D1 与 S1 同时成立而落点对不上时，按 S1 走。P1 与 D1 同时成立时，先按 D1 定位段，再用 P1 说明这一段里的时间是不是首次落页。判据互相矛盾的那一轮按结果 C 处理，记录矛盾本身。

## 5. 轮次预算与检查点

### 5.1 A 槽重试的算术

`slot-retry-count:a` 在 `set_active a` 之后读回 7。每起一次 loader 扣 2 且不标记成功，7 → 5 → 3 → 1，第四次起轮前计数已经到 1，LK 会把 A 槽标成不可引导并回退到 B 槽。

| 时点 | `slot-retry-count:a` |
|---|---|
| `set_active a` 之后、起轮之前 | 7 |
| 第 1 轮收尾 | 5 |
| 第 2 轮收尾 | 3 |
| 第 3 轮收尾 | 1 |
| 下一次起轮之前 | 必须复位 |

检查点本身要起一次 loader，复位之后读回 5，所以一个「复位 + 两轮」周期把计数从 7 走到 3。实际扣减按 5.2 的前后读数记，不用这张表代替。

### 5.2 检查点动作

触发条件：起轮前 `slot-retry-count:a` 低于 3，或距上次检查点已满 3 轮。动作固定为[引导目标切换 SOP](device-boot-target-sop.md) §5.3 的整轮重启，理由只有一条：目前只有这条路被实测证明能把设备带进与上一轮无共享运行时状态的入口（`fixguard6`、`fixguard7` 走这条路且桌面健康，直接从上一轮收尾的 loader 起的那一轮从第 4 份快照起就报 `bad access`）。

1. 在 LK 侧读 `slot-successful:b` 与 `slot-unbootable:b`，任一不满足就停，回 Android 的路不可用。
2. `fastboot -s "${ANDROID_SERIAL}" set_active b`，再 `reboot`，等 `adb` 出现且 `sys.boot_completed=1`（实测 15 到 19 秒）。
3. `adb -s "${ANDROID_SERIAL}" reboot bootloader`，等 LK 出现（实测 8 到 11 秒）。
4. 读 `current-slot`、`slot-retry-count:a`、`slot-retry-count:b`、`slot-unbootable:a`、`slot-unbootable:b`，写进检查点记录。
5. `set_active a`，再 `reboot`，等 `xnuloader` 出现（实测 17 秒）。
6. 读 `result`、`ramdisk-state`、`product`，三项通过才允许下一轮。

Android 进不去时，用 `tools/k90auto/reboot-lk.py <新目录> --return-loader` 代替第 2 到 5 步，并在记录里注明这次检查点走的是回退路径。这条路径能把 A 槽计数复位，能不能清掉上一轮的运行时状态没有实测对照。

### 5.3 批次上限与停止条件

- 一个批次最多 3 轮，到数停下汇报，不靠加轮次堆读数。
- 任何一轮收尾三项不满足、任何一次枚举为空、任何一次身份与起轮时读到的不一致，整条队列立刻停，写标记文件并报用户。
- 每轮只改一个变量。这一批的三轮里，第一轮是探针轮，后两轮由第一轮的结果按 §4 决定；没有结论之前先改测法，不加轮次。

### 5.4 每轮收尾

`fastboot -s xnuloader getvar result` 答 `idle`、`getvar product` 答 `xnuloader`、`getvar ramdisk-state` 答 `idle 0 0 0`，三项都满足才允许下一轮。收尾停在 loader，不回 Android。

## 6. 这一轮不回答的问题

- `AppleCLCDDisplay::ignore_update_p` 是否造成帧流永久停止。26 上的槽位是静态推断（`0x150`），钩子不在这一轮的库里；运行期取虚表基址那一版让 backboardd 连续 15 次 `signal 11`。上机前要先有一轮只读的虚表基址校验，用[26 虚表定位](../analysis/2026-10-29-quartzcore-vtable-26.md)里的差值断言。
- 15 秒周期锚在哪一层。这一轮只给洞内 `tl: b` 与 `tl: cnt` 的活动，把「用户态等一次不再到来的通知」与「内核节拍没投递」分开需要 `ca_vbl=1`（一轮，单变量，不改任何产物）或 `tl: n`（改内核，另一轮）。
- 预落页是不是慢 draw 的成因。这一版 AIR 里预落页常开、没有运行期开关，只能给成本行的量级，开关对照要新编一版 AIR，属于后面的一轮。
- 缺页是否发生在绘制线程。XNU 没有按线程的缺页计数接口，`flt` 仍是整个进程的口径（见[缺页口径核对](../analysis/2026-10-29-slow-draw-fault-accounting.md) §1.2）。
- 单次缺页的真实成本。要有微基准或在 `vm_fault_internal()` 里给 `current_thread()` 计数，这一轮拿不到这个量。
- 120 Hz 面板与验收门槛。与这一轮的问题不同层，而且需要一段稳定的帧流才能量。
- `is_ready` 在 26 上的槽位、`EAGLServer` 与 `GLESContext` 的常量。静态没有确认，需要真机单步读对象虚表，或把 QuartzCore 抽成独立 Mach-O 再用 IDA。

## 7. 风险与已知缺口

- `57fdb85c…` 这份 AIR 从没有上机跑过：归档里只有一轮引用它，那一轮起轮失败、没有收尾记录。崩溃修法在它的源码里（`air_metal.c` 的 `rwa_buffer_texture` 摘链与刷新两处），整份库第一次跑，`bad access` 的可能性不能排除。
- 预落页对每个首次映射的 BO 逐页写一个字节。任何只读映射都会在这一次写上取 `bad access`，判据里按 §4.3 最后一条处理。大纹理（1206×2622×4 为 12,648,528 字节、3,089 页）在映射时刻要触碰三千多页，慢 map 会出现在这一轮，属于要观测的现象。
- 线程快照只在一次 draw 超过 300,000 µs 时触发。`statefault` 的 24 条里只有 4 条超过这个值，样本会少。
- AIR 的构建记录 `air-build-record.json` 只记 `air_metal.c`、`air_metal.h`、`air_to_nir.c` 三个源文件，两条分段与预落页探针在 `a6xx/fd6_draw.cc`（`edb4521a8eb62db9f689bdc77a66e7e4debef3ec4ffc7699f93126dab230252b`）与 `src/freedreno/drm/freedreno_bo.c`（`ac3922dcc071835a091eb9d9c268d8490830d0aa956812f72522aad4ac8b93ec`）里，两个哈希记在这里，重建时按它们核对。
- 驱动的 `pack.sources` 没有列 `redwoodmetal_commandbuffer.inc` 等六个 `#include` 文件，这一轮的身份靠产物哈希，重建时按 `library-baseline.json` 的 `529d19bf…` 核。
- `package.py` 会重建驱动。重编出来不是 `529d19bf…` 就停下核源码，不要用 `ALLOW_DRIVER_CHANGE=1` 绕过。

## 8. 相关文档

- 会话复盘与当前卡点：[会话复盘](../analysis/2026-10-29-session-review.md)
- 慢 draw 的缺页口径与替代判据：[缺页计数口径核对](../analysis/2026-10-29-slow-draw-fault-accounting.md)
- 15 秒周期与 3 秒空洞：[跨轮统计](../analysis/2026-10-29-15s-period-cross-round.md)
- 26 上的虚表与槽位：[QuartzCore 虚表定位](../analysis/2026-10-29-quartzcore-vtable-26.md)
- 离线产物核对：[产物与算术核对](../analysis/2026-10-29-offline-artifact-checks.md)
- 引导目标切换：[device-boot-target-sop](device-boot-target-sop.md)
- 真机操作陷阱：[device-test-playbook](device-test-playbook.md)
- 运行协议：[k90auto 运行协议](k90auto-run-protocol.md)