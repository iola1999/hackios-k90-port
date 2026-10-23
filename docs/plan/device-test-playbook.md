# 设备回归测试手册（annibale 真机验证 playbook）

写于 2026-10-23（设备关机等待人工开机时准备）。所有镜像已构建，即插即测。一键化：`tools/device-test.sh`（本手册的自动化版）。

## 当前设备状态（预期）

- 上一轮 `fastboot boot` 后走"无 OS → shutdown"= 固件全链路健康的指纹，设备**关机**。
- Android 完好在 `_b` 槽；`_a` 槽 = 实验田（现在存的是旧实验 boot 镜像）。
- `xnu-annibale-log.img` 会把日志写进 `boot_a` 分区（GPT 名匹配），随时可 fetch 取证。

## 变体清单（备好待测）

| 镜像 | payload | 用途 | 传输方式 |
|---|---|---|---|
| `xnu-annibale-log.img` (A) | loader.efi(-DDIRECT_PHONE_PLAT) + `--usb` | **首选**：诊断——loader 驻留等 USB；USB 失败则日志落 boot_a | `fastboot boot`（1.26MB，LK 容量内；DTB 槽用 empty.dtb，真 DT 在 FD 内） |
| `xnu-annibale-auto.img` (B) | loader.efi + kernel(旧 prebuilt) | 自动起 iOS 内核（盲跑），panic 日志落 boot_a；已被 C 取代，留作对照 | `fastboot flash boot_a` + `--set-active=a` + `reboot` |
| `xnu-annibale-c.img` (C) 8,036,352 B | loader(-DDIRECT_PHONE_PLAT) + 自建 kernel(3c4c534，含 hv_haptic 修正 + buttons/battery/torch 三驱动) + root.apfs + `--rdfile userdata:2492203008:tail`，cmdline `debug=0x10e serial=3` | **主推**：图形锁屏冲刺（暂存步骤先过暂停门）。payload bytesum=566a1d37（boot_a 日志里的对账指纹） | `fastboot flash boot_a` + `--set-active=a` + `reboot`（见下方流程） |

FD 均含：XNUP 补丁 + boot_a 日志回退 + 合并 DTB（vendor_boot base ⊕ dtbo overlay）+ K90 面板 XML。

## 标准流程

```bash
# 0) 用户开机进 Android 后：
adb -s ${ANDROID_SERIAL} wait-for-device
adb -s ${ANDROID_SERIAL} reboot bootloader          # 进 LK fastboot（勿用 reboot fastboot=fastbootd）

# 1) 变体 A：诊断
fastboot boot hackios-xnu-kernel/xnu-annibale-log.img
#    若 8~40s 内 `fastboot getvar product` 返回 xnuloader → USB 成了：
timeout 2 fastboot getvar product
hackios-xnu-kernel/xl log                    # 全量 loader 日志
hackios-xnu-kernel/xl ramdisk hackios-xnu-kernel/userland/system.apfs   # 大 root 走 USB
hackios-xnu-kernel/xl run                    # 起内核 + 自动收 log
#    若 USB 无响应/回到 fastboot → 直接取证 boot_a：
fastboot fetch boot_a /tmp/logdump.bin 2>/dev/null || fastboot oem dump
head -c 4096 /tmp/logdump.bin               # 前 256KB = loader 文本日志

# 2) 变体 B：A 不通或想看内核盲跑
fastboot flash boot_a hackios-xnu-kernel/xnu-annibale-auto.img
fastboot --set-active=a && fastboot reboot
#    看屏 30-60s（黑屏属预期）→ 回 Android 取证：
adb -s ${ANDROID_SERIAL} shell su -c "dd if=/dev/block/by-name/boot_a bs=4096 count=64" > /tmp/logdump.bin
head -c 2048 /tmp/logdump.bin
#    回滚：adb -s ${ANDROID_SERIAL} shell su -c 'bootctl set-active-boot-slot 1'（或 fastboot --set-active=b）
```

## 决策树（结果 → 下一步）

- **A 有 USB（getvar=xnuloader）**：`xl log` 看 `usb:` 行；顺路 `xl ramdisk`+`xl run` 直接冲内核启动 → 目标 M4 锁屏。面板黑 → 用 `xl screenshot` 验证 GOP 是否实际可用。
- **A 无 USB，boot_a 有日志**：读 `usb: device protocol not found` vs `usb: start failed`：
  - `not found` → apriori 的 UsbDeviceDxe 没装协议 → 查 QcomPkg USB 依赖链（UsbfnDwc3/ QcomSysInterface），或考虑 loader 自带 DWC3 驱动（redwood路线之外的 Plan C）。
  - `start failed` → 控制器起来了但 gadget 起不来 → 对照 dodge 的 Fastboot 用法（Mu-Silicium 手机线本家场景就是 fastboot!查 QcomPkg FastbootDxe 如何触发 USB）。
- **A 无 USB 且 boot_a 全零**：GPT 分区名与 `boot_a` 不符 → 从 Android 侧 `adb shell su -c 'ls -l /dev/block/by-name/ | head'` + gpt 名字改 XnuLoader.c/loader.c 重试。
- **B 起屏显（哪怕乱码）**：GOP 生效 → 回填 FB_BASE 进 annibale.conf，内核 simplefb 直写。
- **B boot_a 出现内核 log**：内核已在 SM8750 硬件上跑起来（GIC/串口交接 OK）→ 里程碑：真机 iOS 启动文本。之后按 panic 点逐个修（大概率：UFS 时钟/平台识别→用 ramdisk 就绕开 UFS）。

## 已知陷阱（务必遵守）

1. `fastboot boot` 报 Load Error：先 `fastboot reboot bootloader` 重进 LK 再试（LK 状态偶发脏，与镜像无关）；`fastbootd` 一律拒未签名 boot（getvar 后 `ioreg` 见 "2510DRK44C" 即 fastbootd 假象）。
2. `fastboot boot` 容量上限 ≈2MB（7.5MB 被拒）；大镜像走 flash `_a` 槽。
3. 设备"无响应地从 USB 消失" ≈ shutdown = 固件跑到最后一步，是好消息。
4. 一切以 `_b` 槽完好为前提；`_a` 槽和它的 boot_a 分区随我们折腾。
5. 驻留期主机侧 `18d1:d00d` 可能是 LK 也可能是 loader（同款 PID）。用 `getvar product` 区分：秒回 `annibale`=LK；不响应=loader 命令通道未通。`fastboot reboot` 回显 Finished 不作证据（工具对 reboot 不等 OK）。
6. EDK2 BlockIo **写** UFS 当前不落地（五分区探针全灭；读正常）——"写分区再回 Android 取证"的手段暂不可用；可用间接指纹 = payload bytesum、镜像容量、GONE 时长。rootfs 路线 D 只依赖读，不受影响。
7. 桌面 wch 串口（921600）是桌上另一台设备（desk-01 JSON）。手机真 console = GENI uart **0xa9c000 / 115200n8**（docs/analysis/annibale-hw-map.md），QUP 时钟默认 gating，未飞线前别在串口上耗时间。
8. **面板点亮取决于进入方式**：`reboot`/开机进 slot_a → LK 跑 splash → 0xFC800000 区域被 DMA 驱动，loader 的 SCREEN fallback 把我们文字和内核 BootArgs.video 都落在真屏上；`fastboot boot` 不经 LK splash → 面板全黑（写 fb 无害）。想看画面必须用 `--set-active=a` + `reboot`。
9. **loader.efi 有两种构建，谁用谁现编**：手机镜像必须 `EXTRA_CFLAGS=-DDIRECT_PHONE_PLAT bash xnuloader/build.sh`；QEMU 回归（run-ios.sh 直接用 xnuloader/loader.efi）必须用默认构建。手机版喂给 QEMU，内核 5.8s 卡在 pe_arm_init_debug 之后（GIC 基址对不上）；默认版喂给手机，平台按 framebuffer 基址匹配不到 annibale。烧机前和跑 QEMU 前各编一次。

## 变体 C（rdfile，图形锁屏冲刺）流程

> **暂停门（2026-10-23 评审 + 用户指示）**：第 0 步 `stage-system.sh` 向 userdata 尾部写 ~2.4G，事先不校验这些块是否被 f2fs 占用，且现有备份不含 userdata。当前策略 = 调试只做 RAM 启动、不落持久数据 → 跑第 0 步前必须先经用户同意（或先坐实 super 尾部空闲 extent 方案，见下"窗口数学"）。boot_a 槽是我们的自留地，flash 它不受此限。

```bash
# 0) Android 在 slot _b 上正常开机，KernelSU 授权 adb
hackios-xnu-kernel/tools/stage-system.sh --yes       # 2.4G system.apfs → userdata 尾部，~2min（⚠ 先过暂停门，用户点头才加 --yes）
# 1) 烧 c 镜像并切槽（c.img 8.2MB：loader+kernel+root.apfs；system 靠暂存区）
fastboot flash boot_a hackios-xnu-kernel/xnu-annibale-c.img
fastboot --set-active=a && fastboot reboot
# 2) 观察（无 USB/串口也能看）：
#    - 屏亮出 iOS 图形（SpringBoard 或纯黑渐变）→ BootArgs.video 通了，里程碑
#    - 屏出乱码 → fb 几何/stride 不对，改 loader.c 里 1440x3200 重试
#    - 屏维持 REDMI splash 后 30s 重启循环 → 内核早期死；回 slot b 取证：
#      读 boot_a 头部确认是我们的镜像，重刷 auto.img 看是否同样循环
fastboot --set-active=b && fastboot reboot          # 任何时候回用户 Android
```
注意：variant C 的暂存区随时可能被 slot b 的 f2fs 写花——**每次试 C 前重跑 stage**。窗口数学：变体 C 要 loader 找到 **≥3.35G 单块连续空闲**（resident 2.49G + 内核自身 768M 预留 + 64M，choose_window 取最大自由块，MAX_MEM_SIZE 封顶 6G）。splash 循环不黑屏 = 大概率块不够 → 用 payload `physbase=<地址>` 强制指定（候选 0x100000000，前提是那块确实整段空闲；届时看屏指纹或修好的日志通道确认）。super 尾部空闲 extent 是更稳的落点（f2fs 不会碰），偏移要等设备的 loader `ufs=1` 日志 + tools/ufs-super.py 解析出 lp 空闲区后固化进 rdfile= 参数。

## 外设开关（改 payload cmdline，重打包 c.img 即可）

C 的图形里程碑达成后，逐个外设加旗标复测（payload `--cmdline` 追加）：

- `touchscreen=2`：annibale Goodix 触摸（cc9ff58 参数化）。锁屏上手指的滑动解锁就是验收；坏了指纹=日志落 boot_a 里 `goodix:` 前缀行。
- `hv_haptic=3`：PMIC 震动自检——起内核后 30 ms 直驱一次马达，**手感就是验收** （屏幕/串口都看不到它）。注意 059a59e 修正了 ppid（0x0f0→0x7f0，TI 块在 slave 7，DT 路径裁决），**旧镜像这步必然无感，必须用新 kernel**。没感觉再加 `haptic_amp=128` 试更大；仍无 → boot_a 读 `haptic:` 前缀（arbiter 表、revision、fault 都在里面）。
- `hv_haptic=4`：iOS 反馈直通马达（/dev/redwood-haptic，DIRECT_PLAY 跟随响度）。桌面点击该有震感。上限 1 s/次，fault 自动弃疗。
- `buttons=1`：音量/电源键（已入库 redwood_buttons_hv.c，纯读零写入 PMIC）。音量上=PMI GPIO slave1 function 0x18d 低有效带上拉（DT #L9164/#L21098，**不是**任务书早先写的 TLMM GPIO6——若真机无事件先查这条）；电源/音量下=PMK8550 PON（KPDPWR/RESIN）。按键事件进 boot_a 日志 `buttons:` 行 + `/dev/redwood-input`。细分步 `buttons_hv_steps=1..5`。
- `torch_secs=3`：手电盲测——亮 3 秒自己灭，肉眼即验收（redwood_torch_hv.c；先验 TYPE/SUBTYPE+无 fault 才写，每写必回读；`torch_ma=1..500` 调电流默认 125；实时 fault 直接拒亮不猜）。
- `battery=1`：电量（redwood_battery_hv.c，纯读）——SDAM 校验 VALID=1 才发布，电量图标出数即验收；step2 全总线 TYPE/SUBTYPE 普查是**勘察红利**（FG=0x0d/SDAM=0x2e 命中自动采用，slave7 优先），boot_a 里 `battery:` 前缀可回收全部 PMIC 外设表。细分步 `battery_hv_steps=1..5`。
- **真机一把过批次**：cmdline 一次带全 `touchscreen=2 hv_haptic=3 buttons=1 battery=1 torch_secs=3`，观察顺序 看屏→搓屏→手感→音量键→手电→电量图标，收尾 `adb pull /vendor/lib64/camera`（纯拷贝，不动块）。
- 触摸/震动都惰性于默认 cmdline（不带旗标=零动作），QEMU 同理不需要它们。
