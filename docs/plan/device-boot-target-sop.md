# 真机引导目标切换 SOP（Android／LK／loader）

本文件把 K90 上三种引导目标之间的切换写成固定命令加成功判据，用于避免每次重新摸索。全部条目来自 2026-10-28 23:37 至 10-29 00:17 的实测，其中「从 LK boot payload 进 loader」一条是当晚两次失败的读数，结论记在 §4.1。设备序列号通过环境变量 `ANDROID_SERIAL` 提供，loader 固定用 `xnuloader`；同一设备的命令串行执行。

## 1. 先判当前身份

枚举只用 `fastboot devices`。**不要**对尚未出现的序列号发 `fastboot -s xnuloader …`：该命令会进入 `< waiting for xnuloader>` 并挂成后台客户端，实测踩过一次，只能 `job_kill` 收场。

| 身份 | 判别命令 | 判别串 | 说明 |
|---|---|---|---|
| Android | `adb -s "${ANDROID_SERIAL}" get-state` | `device` | 进一步核 `getprop sys.boot_completed` 与 `getprop ro.boot.slot_suffix` |
| LK fastboot | `fastboot -s "${ANDROID_SERIAL}" getvar product` | `annibale`，且 `getvar is-userspace` 答 `no` | 能答 `current-slot`、`slot-*` 一组变量 |
| Android fastbootd | 同上 | `is-userspace` 答 `yes` | 本项目的实验不走 fastbootd |
| 驻留 loader | `fastboot devices` | 出现 `xnuloader` | 再核 `getvar result` 与 `getvar ramdisk-state` |

`getvar result`、`getvar build-id`、`getvar ramdisk-state` 三个变量只有 loader 答；LK 上问这三个会答 `GetVar Variable not found`。这条是「loader 是否驻留」的判别量，不要与 loader 答 `hung-held`／`idle` 混为一类：前者是 loader 没被带起来，后者是 loader 在跑而内核或运行态出了问题。

## 2. 五条切换路径

| 起点 → 目标 | 命令 | 成功判据 | 实测耗时 |
|---|---|---|---|
| Android → LK | `adb -s "${ANDROID_SERIAL}" reboot bootloader` | `fastboot devices` 出现该序列号，`getvar product` 答 `annibale` | 8～11 秒 |
| LK → Android | `fastboot -s "${ANDROID_SERIAL}" set_active b`，再 `reboot` | USB 断开后重新枚举，`adb -s "${ANDROID_SERIAL}" get-state` 答 `device`；`sys.boot_completed=1` | 15～19 秒 |
| LK → loader | `set_active a`，再 `reboot` | `fastboot devices` 出现 `xnuloader`，`getvar result` 答 `idle`，`getvar ramdisk-state` 答 `idle 0 0 0` | 17 秒 |
| loader → LK | `python3 tools/k90auto/reboot-lk.py <新目录> --payload hackios-xnu-kernel/out/ios26-resume/reboot-lk-prepare/annibale-reboot-lk-prepare.bin --sha256 6b81e800ae789cf30adbaaa9c98768012e264c66a4e56110c6449cecf93fb7d7 --serial "${ANDROID_SERIAL}"` | 工具输出 `LK FASTBOOT verified on slot <a\|b>`，`result.json` 的 `lk_entered` 为真 | 8 秒 |
| loader 复位（PSCI） | `fastboot -s xnuloader reboot` | 先断开约 10 秒，再重新枚举为 `xnuloader`，`result` 答 `idle`，`ramdisk-state` 答 `idle 0 0 0` | 11 秒 |

三条要点：

- 槽位归属：A 槽的 boot 分区是 loader，B 槽是 Android。两个方向都靠 `set_active` 换目标槽再 `reboot`，LK 的 `reboot` 本身只做 PSCI 复位。
- 切到 A 槽前先核 B 槽可用：`slot-successful:b=yes`、`slot-unbootable:b=no`。`reboot-lk.py` 在工具内已核这两个量，手工切槽时要自己核。
- 从 loader 回 Android 要两跳：先 `reboot-lk.py` 进 LK，再 `set_active b` 加 `reboot`。loader 自己的 `reboot` 只会回到 A 槽。

## 3. 一次进 loader 的最短序列

从 Android 出发，四条命令、约 30 秒：

```sh
adb -s "${ANDROID_SERIAL}" reboot bootloader
fastboot -s "${ANDROID_SERIAL}" getvar current-slot
fastboot -s "${ANDROID_SERIAL}" set_active a
fastboot -s "${ANDROID_SERIAL}" reboot
```

随后用 `fastboot devices` 等 `xnuloader` 出现，再核 `result: idle` 与 `ramdisk-state: idle 0 0 0`。

## 4. 陷阱（均为实测）

1. **LK `fastboot boot <handoff payload>` 不会把 loader 带起来。** 2026-10-28 两次实测：命令答 `Booting OKAY [0.112s]`／`[0.114s]`，之后 80 与 90 秒内 `xnuloader` 从未枚举，`result`／`build-id`／`ramdisk-state` 都答 `GetVar Variable not found`。这条路径的通病是把「命令 OKAY」当成「loader 驻留」；判别只看 `fastboot devices` 与那三个变量。完整的 loader 镜像（BootShim、FD、XNUP、DTB，例如 `hackios-xnu-kernel/out/handoff-loader-v12.img`）可以 `fastboot boot`：2026-10-31 实测 18 秒后 `xnuloader` 枚举，不刷 `boot_a`，也不扣 `slot-retry-count:a`，见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md) §5。
2. **对未枚举的序列号发 `fastboot -s xnuloader getvar …` 会挂住。** 该客户端进入 `< waiting for xnuloader>` 并可能成为后台作业，与其它 fastboot 客户端并发时会把 USB 命令通道卡住。枚举一律用 `fastboot devices`。
3. **LK 的 `reboot` 在目标槽被标为不可引导时无效。** 实测 `slot-unbootable:b=yes` 时 `reboot` 答 `OKAY` 而设备仍停在 LK；`set_active b` 会清掉这个标志（读回 `slot-unbootable:b=no`），同理 `set_active a` 清 A 槽。判断「到底复位了没有」看 USB 是否真的断开：`ioreg` 250 毫秒采样能看到消失再重现，只看命令返回值判不出来。
4. **`slot-retry-count:a` 每跑一轮扣 2 次，约三轮后归 0，LK 会把 A 槽标成不可引导并回退 B 槽 Android。** 2026-10-29 实测：`set_active a` 后读回 7，跑一轮（loader 起 iOS、进桌面、`hung-held` 收尾）后读回 5，同时 `slot-successful:a` 始终是 `no`。原因是经 loader 起 iOS 不写成功引导记录，计数器一路递减，与 panic 无关。起轮前先读 `slot-retry-count:a`，低于 3 时执行 `set_active a`（该命令把计数重置为 7 并把 `slot-unbootable:a` 清回 `no`），随后重启一次 loader 再起轮；每轮收尾前再读一次，已经掉到 0 时不要直接起下一轮，先按同样的方式复位。`tools/k90auto/round-run.py` 已把这套检查做成起轮前置。
5. **安卓侧点屏不能用 `input keyevent`。** adb shell 缺 `INJECT_EVENTS`，会抛 `SecurityException`；用 `svc power stayon usb` 能把屏幕点亮。`screencap` 全黑先看 `mWakefulness` 与 `Display State`，两者都是 OFF 时黑屏来自休眠，与面板无关。
6. **`reboot-lk.py` 的 `--payload` 必须是 prepare 载荷。** 本轮误喂轮次 payload 时，工具 `stage` 后把内核又起了一次并停在 `hung-held`，报 `Probe return timed out; reboot not sent`；那种引导的日志是 `Process 1 exec of /sbin/launchd failed, errno 2`（没有系统盘常驻）。
7. **loader 报 `hung-held` 时先取环再复位。** 顺序是 `get_staged <名字>.log`（内核快照）、`oem log`、`get_staged <名字>-serial.log`（loader 串行日志），最后才 `reboot`。反过来先 `oem log` 会把已组装好的快照覆盖掉。
8. **文档与提交里的设备序列号写 `ANDROID_SERIAL`。** 实测序列号不进仓库。

## 5. 三种复位的差别

同一台设备上「复位」有三种，清掉的东西不同，用错会让人把启动间差异当成实验差异。

### 5.1 PSCI 复位（`run-auto.py` 收尾做的那个）

- 命令：`fastboot -s xnuloader reboot`。annibale 上 loader 的 `reboot` 分支一律走 `psci_reset_attempt()`，源码在 `xnuloader/loader_06_usb_entry.inc:716-731`；同一分支里 EFI 冷复位那条路只在非 annibale 且没有持有资源或故障时才走。
- 判据：`fastboot devices` 先变空、随后重新列出 `xnuloader`，再读 `getvar result` 得 `idle`、`getvar ramdisk-state` 得 `idle 0 0 0`。`run-auto.py` 的 `reboot.json` 记 `off_seen: true`、`mode: loader`，实测断开到重新可用 16.9～17.8 秒。
- 适用：一轮跑完、崩完，要把设备从「内核在跑」拉回到可再用 loader。**不适用**于起轮前。

### 5.2 宿主冷复位

- 命令：这台设备上没有宿主侧命令能做到。`loader_06_usb_entry.inc` 的 `reboot` 分支在 annibale 上只有 PSCI 一条路，没有 `oem poweroff` 之类；要做到断电只能由人长按电源强制关机再开机。
- 判据：未实测，本项标推断。
- 何时需要：内核在 `adreno8_quiesce()` 里打印 `adreno8: GPU probe requires host cold reset before reusing kernel memory` 之后停在 `wfe` 循环（源码 `xnu/files/bsd/dev/adreno8.c:476-484`，触发条件是 `adreno8_reset_required` 或 `adreno8_memory_retained()`）。这条信息的意思是 GMU 的 RPMh 投票或 GMU 内存没有被收回，loader 不应把那段内存再分给下一个内核。实测到的事实是：fixguard6、fixguard7 收尾日志末行都有这句，而 PSCI 复位之后设备仍然回到可用 loader，本轮之后的轮次也起得来；所以「PSCI 复位是否足以清干净 GPU 状态」在没有功率计的对照之前只能记为未定。

### 5.3 走 LK 的整轮重启

- 命令：安卓侧 `adb reboot bootloader` → LK 侧 `fastboot -s "${ANDROID_SERIAL}" set_active a` → `fastboot -s "${ANDROID_SERIAL}" reboot`；反向（loader 回安卓）用 `tools/k90auto/reboot-lk.py` 进 LK，再 `set_active b` 加 `reboot`。
- 判据：LK 侧 `getvar product` 得 `annibale`、`current-slot` 与切换后一致；进 loader 后 `result: idle` 加 `ramdisk-state: idle 0 0 0`；回安卓后 `adb` 出现 `device`、`sys.boot_completed=1`。
- 实测耗时：安卓到 LK 8～11 秒、LK 到 loader 17 秒、loader 到 LK 8 秒、LK 到安卓 15～19 秒。
- 适用：**每一轮起轮之前**。这是目前唯一被实测证明能把设备带进「与上一轮无共享运行时状态」的入口：fixguard6、fixguard7 都从这条路进来且桌面健康，而 2026-10-29 那轮直接从上一轮收尾的 loader 起，同一库同一系统盘，从第 4 份快照（约 30 秒）起就报 bad access。

一份跑轮前的固定动作：先走 §5.3 进到 loader，再核 §5.1 的两项判据，然后才起轮。

## 6. 起轮前的状态审计

**第一条：起轮前必须走 §5.3 的整轮重启，不许直接从上一轮收尾留下的 loader 起。** 理由是 2026-10-29 那轮的直接对照：同一份 AIR 库（`cbf1689c…`）、同一份系统盘、同一份 cmdline，fixguard6 与 fixguard7 都从「安卓 → LK → 切 A → reboot」进入且桌面健康，而紧接着的 `unlockprobe` 直接从上一轮收尾的 loader 起，从第 4 份快照（约 30 秒）起就报 bad access、`died on signal` 是前两轮的约五倍。差别只有入口方式这一项。轮间设备停在 loader 仍然可以（屏幕黑、可软件恢复），但下一轮起轮前要再走一次完整复位。

身份核对要按**从 root 里实算**做，不能只读 staging 那一份：`package.py` 每次打包都会用 `hackios-xnu-kernel/tools/userland-driver/` 下的源码现场重编 `libredwoodmetal.dylib` 再拷进 root，所以 staging 里的那份、内核源码树的当前状态、以及上一轮 root 里的那份可以互不相同。三轮实测就出现过 `9d66dd36` 与 `d296b5a4` 交替。

从轮次 root 里实算四样的方式（AIR 与驱动两样最容易被覆盖，必须每轮算）：

```sh
python3 hackios-xnu-kernel/tools/apfs/apfs.py cat <root> /lib/libredwoodair.dylib | shasum -a 256
python3 hackios-xnu-kernel/tools/apfs/apfs.py cat <root> /lib/libredwoodmetal.dylib | shasum -a 256
```

AIR 与驱动之外，`system` 的 sha 与打包记录的 `root_sha256` 一并写进轮次报告。判据是四项与 `manifest.json` 的 `pack` 段逐项相等；不相等就停下核，不要起轮。

**第五项：内核路径必须落在 `out/xnu12377/BUILD/obj/`。** 本项目的目标内核由 `out/xnu12377` 这棵 12377 的树编出，产物是 `out/xnu12377/BUILD/obj/mach.development.bcm2837`（20,210,232 字节，`cf1502f5…`，`BUILD/obj/` 下是指向 `DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837` 的符号链接）。`tools/k90auto/build-kernel.py` 编的是容器里 `/work/repo/xnu-src/xnu-8796.121.2`，产物落在 `out/handoff-mach-attr26-*`（19,316,912 字节）。两条线是不同版本的 XNU。

读法：`manifest.json` 的 `kernel.path` 以 `out/handoff-mach-attr26-` 开头，这一轮就不是本项目的目标内核，读数只能描述 8796 那棵树。2026-10-29 有六轮踩在这上面（`5e044755`、`d1c91177`、`5491e0a4`、`3b856b57`、`77d3be3a` 与更早的 `e558dbd4`），它们给出的 0 帧与 `machine_routines.c:1237` 读数都不属于本项目内核。

```sh
python3 -c "import json;print(json.load(open('<轮次目录>/manifest.json'))['kernel']['path'])"
ls -l hackios-xnu-kernel/out/xnu12377/BUILD/obj/mach.development.bcm2837
```

五项（内核路径与 sha、AIR、驱动、system、`root_sha256`）全部相符才起轮。

每轮起轮前在 LK 侧读下面五项并记下：`current-slot`、`slot-retry-count:a`、`slot-retry-count:b`、`slot-unbootable:a`、`slot-unbootable:b`。这一组是下一轮出现异常时的对照基线，比事后回忆可靠。

```sh
fastboot -s "${ANDROID_SERIAL}" getvar current-slot
fastboot -s "${ANDROID_SERIAL}" getvar slot-retry-count:a
fastboot -s "${ANDROID_SERIAL}" getvar slot-retry-count:b
fastboot -s "${ANDROID_SERIAL}" getvar slot-unbootable:a
fastboot -s "${ANDROID_SERIAL}" getvar slot-unbootable:b
```

轮次中途若发现设备身份与预期不符（例如 `adb devices` 变空、`fastboot devices` 列出 `xnuloader`，或槽位与起轮时读到的不一致），立即停下并向协调人报告，不自行续跑；身份不符时继续发命令会让后续读数无法归因。

轮次收尾停在 loader，不回安卓。`run-auto.py` 的收尾已经把内核停掉并复位，落在 fresh idle loader。**下一轮起轮前仍要走一次 §5.3 的整轮重启**（见本节第一条的理由），所以「收尾停在 loader」只说明设备当前可软件恢复，不构成下一轮可以直接起轮的依据。回安卓只在两种情况下做：用户要用手机，或接下来较长时间不跑。收尾停在 loader 时核三项——`result: idle`、`ramdisk-state: idle 0 0 0`、`product` 为 `xnuloader`——三项都满足才算正常收尾，任一项不满足即停整条队列，见 [AGENTS.md](../../AGENTS.md) 第 5 节。

连续起轮有预算：loader 每次启动消耗 2 次 A 槽重试且不标记成功，连续轮次每满 3 轮做一次冷启动检查点再继续；一个诊断批次最多 3 轮，到数停下汇报。2026-10-29 一天连跑十几轮没有做任何检查点，最后一次起轮时 loader 已从 USB 消失，只能长按电源键恢复。

序列号为空时禁止发命令。`adb devices` 列出但序列号读不出来，按未枚举处理，除轮询外不发任何命令；`adb reboot bootloader` 这类命令在没有序列号时执行过一次并返回 `unknown command`，此后设备整段 USB 消失。

一条历史记录（原因未知，只记事实）：2026-10-29 16:37 设备已回到安卓并核过可用，16:40 再查时 `adb devices` 为空、`fastboot devices` 列出 `xnuloader`、loader 为 fresh idle（`result: idle`、`ramdisk-state: idle 0 0 0`），即 A 槽在这三分钟内被切过并复位了一次；`slot-retry-count:b=6` 与 `slot-unbootable:b=no` 两个值与切前相同，可排除「安卓反复启动失败后回退到 A 槽」。设备侧只有 device 被授权执行 `fastboot`／`adb`，其余成员为只读。

## 7. 与其它文档的关系

操作前后的陷阱清单见[真机操作手册](device-test-playbook.md) §6；异常后的资源保留与恢复判断见[USB 恢复经验](../analysis/2026-10-25-usb-recovery-lessons.md)；`reboot-lk.py` 的入口来源与三轮真机验证见[k90auto 说明](../../tools/k90auto/README.md)；轮次怎么跑见[k90auto 运行协议](k90auto-run-protocol.md)。