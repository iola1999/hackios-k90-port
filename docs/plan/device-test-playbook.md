# 设备回归测试手册（annibale 真机验证 playbook）

写于 2026-10-23（设备关机等待人工开机时准备）。所有镜像已构建，即插即测。
一键化：`tools/device-test.sh`（本手册的自动化版）。

## 当前设备状态（预期）

- 上一轮 `fastboot boot` 后走"无 OS → shutdown"= 固件全链路健康的指纹，设备**关机**。
- Android 完好在 `_b` 槽；`_a` 槽 = 实验田（现在存的是旧实验 boot 镜像）。
- `xnu-annibale-log.img` 会把日志写进 `boot_a` 分区（GPT 名匹配），随时可 fetch 取证。

## 变体清单（备好待测）

| 镜像 | payload | 用途 | 传输方式 |
|---|---|---|---|
| `xnu-annibale-log.img` (A) | loader.efi(-DDIRECT_PHONE_PLAT) + `--usb` | **首选**：诊断——loader 驻留等 USB；USB 失败则日志落 boot_a | `fastboot boot`（1.26MB，LK 容量内；DTB 槽用 empty.dtb，真 DT 在 FD 内） |
| `xnu-annibale-auto.img` (B) | loader.efi + kernel(=QEMU 同款 mach.development.bcm2837) | 自动起 iOS 内核（盲跑），panic 日志落 boot_a | `fastboot flash boot_a` + `--set-active=a` + `reboot` |
| （C，并入 A/B） | — | 面板 XML（自家 DTS 转的 `xiaomi p11 42 0d 0a`）已在 FD 内，屏幕可能点亮 | 随 A/B |

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

- **A 有 USB（getvar=xnuloader）**：`xl log` 看 `usb:` 行；顺路 `xl ramdisk`+`xl run`
  直接冲内核启动 → 目标 M4 锁屏。面板黑 → 用 `xl screenshot` 验证 GOP 是否实际可用。
- **A 无 USB，boot_a 有日志**：读 `usb: device protocol not found` vs `usb: start failed`：
  - `not found` → apriori 的 UsbDeviceDxe 没装协议 → 查 QcomPkg USB 依赖链（UsbfnDwc3/
    QcomSysInterface），或考虑 loader 自带 DWC3 驱动（红杉路线之外的 Plan C）。
  - `start failed` → 控制器起来了但 gadget 起不来 → 对照 dodge 的 Fastboot 用法
    （Mu-Silicium 手机线本家场景就是 fastboot!查 QcomPkg FastbootDxe 如何触发 USB）。
- **A 无 USB 且 boot_a 全零**：GPT 分区名与 `boot_a` 不符 → 从 Android 侧
  `adb shell su -c 'ls -l /dev/block/by-name/ | head'` + gpt 名字改 XnuLoader.c/loader.c 重试。
- **B 起屏显（哪怕乱码）**：GOP 生效 → 回填 FB_BASE 进 annibale.conf，内核 simplefb 直写。
- **B boot_a 出现内核 log**：内核已在 SM8750 硬件上跑起来（GIC/串口交接 OK）→ 里程碑：
  真机 iOS 启动文本。之后按 panic 点逐个修（大概率：UFS 时钟/平台识别→用 ramdisk 就绕开 UFS）。

## 已知陷阱（务必遵守）

1. `fastboot boot` 报 Load Error：先 `fastboot reboot bootloader` 重进 LK 再试（LK 状态偶发脏，
   与镜像无关）；`fastbootd` 一律拒未签名 boot（getvar 后 `ioreg` 见 "2510DRK44C" 即 fastbootd 假象）。
2. `fastboot boot` 容量上限 ≈2MB（7.5MB 被拒）；大镜像走 flash `_a` 槽。
3. 设备"无响应地从 USB 消失" ≈ shutdown = 固件跑到最后一步，是好消息。
4. 一切以 `_b` 槽完好为前提；`_a` 槽和它的 boot_a 分区随我们折腾。
5. 驻留期主机侧 `18d1:d00d` 可能是 LK 也可能是 loader（同款 PID）。用
   `getvar product` 区分：秒回 `annibale`=LK；不响应=loader 命令通道未通。
   `fastboot reboot` 回显 Finished 不作证据（工具对 reboot 不等 OK）。
6. EDK2 BlockIo **写** UFS 当前不落地（五分区探针全灭；读正常）——"写分区再回
   Android 取证"的手段暂不可用；可用间接指纹 = payload bytesum、镜像容量、
   GONE 时长。rootfs 路线 D 只依赖读，不受影响。
7. 桌面 wch 串口（921600）是桌上另一台设备（desk-01 JSON）。手机真 console =
   GENI uart **0xa9c000 / 115200n8**（docs/analysis/annibale-hw-map.md），
   QUP 时钟默认 gating，未飞线前别在串口上耗时间。
8. **面板点亮取决于进入方式**：`reboot`/开机进 slot_a → LK 跑 splash →
   0xFC800000 区域被 DMA 驱动，loader 的 SCREEN fallback 把我们文字和内核
   BootArgs.video 都落在真屏上；`fastboot boot` 不经 LK splash → 面板全黑
   （写 fb 无害）。想看画面必须用 `--set-active=a` + `reboot`。

## 变体 C（rdfile，图形锁屏冲刺）流程

```bash
# 0) Android 在 slot _b 上正常开机，KernelSU 授权 adb
hackios-xnu-kernel/tools/stage-system.sh            # 2.4G system.apfs → userdata 尾部，~2min
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
注意：variant C 的暂存区随时可能被 slot b 的 f2fs 写花——**每次试 C 前重跑 stage**。
super 尾部空闲 extent 是更稳的落点（f2fs 不会碰），偏移要等设备的 loader
`ufs=1` 日志 + tools/ufs-super.py 解析出 lp 空闲区后固化进 rdfile= 参数。
