# rootfs / 存储策略（annibale 真机）

调研日期 2026-10-23。前提：**不需要持久化**（写入不落盘无所谓），但 iOS 起来
**必须有可读的文件系统**。结论先行：**推荐路线 D——镜像随 boot.img 带
root.apfs(4.6MB)+system.ext4(22MB)，loader 用 EDK2 BlockIo 批量读进 RAM，
以内核已认识的"虚拟盘"形式交付**。

## 1. QEMU 里 root 到底怎么进内核（实测逆向）

- `qemu/run-ios.sh` → `mkpayload.py kernel=$K ramdisk=$ROOT --rdres <size>`；
  `qemu/run.sh` 用 `-drive file=$IMG,if=none,virtio-blk` 挂 host 文件。
- 但 **guest 内核并不用 virtio-blk**（run.sh 的 `-device virtio-blk-device`
  实际没进 guest DT）：loader 的 XNUP 里 `ramdisk=` 条目被 loader 交给固件的
  **RamDiskDxe（虚拟盘）路径**，内核看到的 root 是 EDK2 BlockIo 伪装的盘。
  证据：内核 cmdline `rd=` 哈希与 `userland/root.apfs` 镜像绑定（sub agent 调研
  结论；实现细节以 `xnuloader/loader.c` 的 ramdisk 交付路径为准）。
- 挂 root 代码路径：内核 cmdline `rd=` 指定 root 设备哈希；IOKit 侧的盘对象来自
  loader 交付的虚拟盘（QEMU 与真机同机制，细节待写路线 D 时代码走查补全）。
- **推论**：真机上不需要新存储驱动——把"host 文件"换成"payload 内置镜像"就是
  同一条路。

## 2. 内核 fork 存储实态

- `grep -r virtio` 命中极少（仅 QEMU 适配文档与个别 timer 代码）：fork 的存储
  路径 = **loader 交付的 BlockIo 类虚拟盘**，非原生驱动。
- Apple ANS/UFS kext 存在于树里但绑 A 系列控制器；QcomPkg UFSHCI 寄存器级移植
  进 XNU（路线 B）估 **1-2 周专人**，且真机 EDK2 写不落地问题同样会困扰调试。

## 3. 真机选项评估（数据，2026-10-23 本机实测）

素材现状（`hackios-xnu-kernel/userland/`、`ios165/`）：

| 文件 | 字节 | gzip -6 | 备注 |
|---|---|---|---|
| root.apfs | 4,194,304 | **200,650**（实测） | 稀疏图，随便放 |
| system.apfs | 2,492,203,008 | ~1.35G（sub agent 实测口径） | 装不进 boot.img |
| cryptex / cryptex-app dmg | ~26M + 10M | 未测 | iOS 实际系统内容载体 |
| DSC（dyld shared cache） | ~2.6G（ios165 抓取） | 未测 | SpringBoard 依赖框架 |

> 早期调研稿报的 4,615,168 / 2,306,868,224 字节与"system ext4 化 23,068,672"
> 与盘上实测不符，已按实测修正；ext4 瘦身方案待做（若可行另节验证）。

boot_a 分区容量 ≥64MB（备份期 GPT 记录），单 boot.img 放 2.5G 的 system 无望。

- **A) 全量 system.apfs 当 ramdisk**：gzip 1.35G，boot_a 放不下。✗
- **B) 内核驱动 UFSHC 读真分区**：1-2 周；APFS 读路径纯软解未验证。中期做。
- **D) 推荐（两段式）**：
  - **D1（近期）**：小镜像进 payload（root.apfs 200KB-gz + cryptex 群）；**大文件
    （DSC 子集）dd 到闲置分区（rescue/gsort 等），loader 经 EDK2 BlockIo 批量读进
    RAM**。读通路真机已验证没问题（写不落地不影响，本路线零写入）；交付内核的
    "虚拟盘"机制与 QEMU 完全一致（第 1 节），内核零改动。
  - **D2（中期）**：路线 B 落地后虚拟盘后端换成真 UFSHC。

## 4. 任务分解

1. loader：XNUP `rdfile=` 条目解析 → 启动时经 BlockIo 读入常驻内存（loader 已
   证明读通路 OK）；与 QEMU `ramdisk=` 交付路径合流。（1-2 天）
2. 构建线：`common/build.sh annibale` 增 system ext4 化步骤（脚本已现成，
   tools/mk_system_ext4.py 思路）；`mkxnuimg.py` 容量核算打印。（0.5 天）
3. 验证序：变体 B（无 root，看内核早期死点）→ 变体 C（带 root，锁屏冲刺）。
4. 中期（M5 之后）：路线 B 真 UFSHC 驱动，替换虚拟盘，为相机原图/OTA 类大文件铺路。
