# annibale 真机试跑记录（2026-10-23 下午）

设备：REDMI K90（annibale，SM8750），slot b = 用户 Android，slot a = 实验区。
镜像：变体 A `xnu-annibale-log.img`（1.26MB，fastboot boot 用）、
变体 B `xnu-annibale-auto.img`（8.0MB，flash boot_a 用）。

## 已证实的事实

1. **全链路 EDK2 接管成立**：`fastboot boot` OKAY 后 ~1s USB 消失（GONE）= LK 把
   设备交给我们 FD 的 BootShim；运行窗口 >100s。
2. **loader 的 USB 描述符确实枚举了**：驻留期主机侧出现 gadget `18d1:d00d`
   （=loader.c `usb_dev_desc` 的 fastboot 标准 VID/PID；此前记 0xCFFD 是十进制
   53261 换算错）。但 LK fastboot 同为 18d1:d00d，**区分方法是 `getvar product`：
   LK 秒回 `annibale`，loader 不响应**（驻留窗口内 getvar 挂 45s+，OUT 端点数据
   没进 loader 的 usb_rx——QCOM_USB_DEVICE 的 TransferNotification 在 SM8750 上
   疑似不触发，待查）。
3. **驻留期发 `fastboot reboot` 后设备确实回了 Android**（20s 内 adb 可见）。
   注意 fastboot 工具对 reboot 不等 OK，不能据此断言 loader 命令通道活着，
   也可能是主机侧 USB 复位触发了 EDK2 路径。
4. **五分区写探针全灭**：变体 A 探针依次对 boot_a/misc/metadata/logfs/xbl_sc_logs
   块 0 写 `XNUPROBE-<名>-001`，回 Android dd 验证：全部保持原内容（misc 还是
   Android 自己的 `bootonce-bootloader`）。BlockIo **写** 在 QcomPkg/SM8750 上不落地，
   读正常。原因待查（写探针打印在 loader 日志里，日志通道恰好就是卡点，鸡生蛋）。
5. **串口线是假目标**：`/dev/cu.wchusbserial3120` 921600 波特抓到的是桌上另一台
   设备（desk-01，周期 JSON）；手机 debug pad 实测在 **QUP4 SE10 UART**（见
   docs/analysis/annibale-hw-map.md），当前未飞线。
6. **blackbox 分区不收录 `fastboot boot` 会话**：整分区 154MB 扫完，只有 XBL 的
   `B-/D-` 与内核 printk，没有我方 EDK2/loader 输出。pstore 空。
7. **变体 B 首刷观察**：`flash boot_a + --set-active=a + reboot` 后 100s 内 USB
   全静默（无 gadget/adb/LK）——与下述平台选错 bug 的表现吻合（内核拿着 QEMU 的
   GIC/核心参数起，早期即死，循环重启且不到 fastboot）。

## 当天修掉的根因：GOP 缺失 → 平台选择停留在 qemu_virt

`loader.c` 的 `DIRECT_PHONE_PLAT` 回退只写在"找到 GOP"分支里；K90 面板 XML 未匹配
（PanelName 悬念未解）→ DisplayDxe 没产 GOP → `locate_protocol` 失败 → **PLAT 一直是
platform_qemu_virt**。连锁后果：

- 内核拿错 GIC/MPIDR/PSCI → 变体 B 静默死（现象 7）；
- `skip_ufs_arbitration = (PLAT == &platform_annibale)` 恒为假 → 写日志仍走 redwood
  UFS 仲裁门被跳过（现象 4 里 write_logs 那一半）——注意 find_partition_named 的
  裸探针写不受该门控，仍失败，所以 BlockIo 写本身还有第二个问题，修复后下一轮复测。

修复（kernel 仓 commit 872da86）：GOP 缺失时 DIRECT_PHONE_PLAT 也强制选 annibale；
`fb_base=0xFC800000`（我方 FD MemoryMapLib 的 `Display_Reserved`；设备自家 DT 的
显示保留区是 0xF2400000，两套 carveout 并存，取 EDK2 实际告知 GOP 的那个）。

## LK fastboot 行为备忘

- `fastboot boot` 容量上限 ~2MB；超限/状态脏报 `Load Error`，`reboot bootloader`
  重进 LK 再试基本第 2 次就 OKAY。
- LK 不支持 `fetch`；`reboot fastboot` 进的是 fastbootd（拒收未签名镜像），
  回 LK 用 `reboot bootloader`。
- boot_a 只有 Android 侧可读（su dd /dev/block/sde14）；XBL 对反复启动失败
  多久掉 fastboot 未观察到（变体 B 循环 20+ 分钟未见 LK）。

## 下一步（按依赖排序）

1. 带 PLAT 修复的 A 镜像重跑：若 `usb: started` 后 getvar 仍不应 → 用 idalib 查
   QcomPkg USB 端点通知路径；同时探针复测（PLAT 修好后 write_logs 路径应通）。
2. 变体 B 重刷（boot_a 已是新镜像，等设备可见后 --set-active=a reboot 即可）。
3. rootfs 路线 D（loader BlockIo 批量读 → 内核虚拟盘）落地后变体 C = 真机锁屏冲刺。
