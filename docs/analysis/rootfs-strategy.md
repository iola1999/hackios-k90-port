# rootfs / 存储策略（annibale 真机 root 从哪里来）

> 调研起草于 2026-10-23（取代同日早期草稿；旧稿勘误见 §0.1）。目标里程碑：**真机开机到锁屏，不要求持久化，文件系统可读即可**。所有行号/数字均为当日在工作区实测（gzip 在 host 直跑，`system.apfs` 为 `userland/build.sh` 当前产物）。

## 0. 一页结论

- **现状**：内核只认 RAM 盘 root（`rd=md0` + 设备树 `chosen/memory-map` 的 `RAMDisk` 属性）。QEMU 把 system.apfs 预放在 guest 物理内存里；真机上这块内存目前只能由 PC 经 USB（`xl ramdisk`）灌入，而 K90 的 loader USB 通道还没修好——**这就是"真机没有 root"的全部原因**。
- **全量进 boot.img 被数字否决**：system.apfs gzip -6 后 **2,406,100,090 B（2.24 GiB）**（内容已是压缩态，只缩 3.5%），而 boot_a 分区实测 **100,663,296 B（96 MiB）**，LK `fastboot boot` 上限 ~2 MiB，payload 容器上限 `PAYLOAD_MAX`=64 MiB——差 24 倍；且 DSC（dyld 共享缓存 ~2 GB）是不可裁的下限。
- **推荐主路线（路线 D）**：loader 在起内核**之前**用 EDK2 BlockIo（读已真机实测可用）把 system.apfs 从 UFS 分区批量预读进内核内存窗口的固定偏移（`RESIDENT_RD_OFFSET`），置 `resident_rd_size`——即把 QEMU `run-ios.sh` 的 `rdres` 布局在真机上复刻。**内核零改动**，boot.img 仍是 ~8 MB。镜像落盘用 Android 侧 `dd`（EDK2 写不落地只影响写，与读路径无关）。
- **快速通路（并行）**：修好 QCOM_USB_DEVICE 的 OUT 通知后，`xl ramdisk userland/system.apfs` 今天就能给真机一个完整的 md0 root（upstream redwood 手机的标准开发模式），零新代码。
- **二线/长期（路线 B1）**：FLASHBOOT——root 直接放 flash 上的 iOS 卷（`redwood_ufs.c` 中转 + `root_apfs=` + `kern.redwood_switch_root`），upstream 已在 POCO X5 Pro 上跑到全 iOS；是持久化时代的正解，但对"锁屏"目标多一层（loader 常驻核 0 全程服务 I/O + darwin 分区备料）。
- 寄存器级 UFSHCI 驱动（路线 B2）**本期不做**：现有 `redwood_ufshc.c` 是"寄生"驱动（借 UEFI 已拉起的控制器换传输列表，只读、无初始化），SM8750 还有 UFSHCI 4.0/MCQ 差异；从零做全套 PHY/时钟/link/SCSI 是周级工作量，锁屏不需要。

### 0.1 对早期草稿的勘误（以代码/日志为准）

| 旧稿说法 | 实测结论 |
|---|---|
| "cmdline `rd=` 是镜像绑定的哈希" | `rd=` 只是**设备名**（`rd=md0`），root 物理来源是 `chosen/memory-map` 的 `RAMDisk` 属性（loader.c:3062-3071、3183-3197；日志 `logs-qemu-run.log:32,115`） |
| "system 经 `-drive`/virtio-blk 进 guest；RamDiskDxe 把 payload 伪装成 BlockIo 盘" | run-ios.sh 的 system **不走任何 virtio 盘**：它是 `memory-backend-file` 直接映进 guest RAM（0xFC000000），loader 只登记 `RAMDisk` 属性；内核走 **mdev（/dev/md0）**，不是 BlockIo。`-drive fat:rw:esp` 只是 loader 的 FAT 启动盘 |
| "system gz ≈1.35 G" | 实测 `gzip -6` = **2,406,100,090 B**（-3.5%）；-9 只再省 0.01% |
| "boot_a ≥64 MB" | 我方 GPT 备份实测 **96 MiB**（`annibale-backup/20261022-2355/partitions.txt:20`，sde14） |
| "system ext4 化 22 MB" | 盘上不存在 ext4 路线；fork 自带**完整自研 APFS 驱动**（读为主+root mount+switch_root），无需换格式 |

## 1. QEMU 里 root 到底怎么进内核（问题 1）

### 1.1 总链路

```
qemu/run-ios.sh
  ├─ IMG(system.apfs 2.32G) ──reflink──▶ qemu/ram.img 偏移 0xBC000000
  │     （memory-backend-file 整块映射 guest RAM，镜像落在 guest 物理 0xFC000000）
  ├─ ROOT(root.apfs 4M) ──▶ mkpayload.py 的 ramdisk= 条目（进 XNUP payload）
  ├─ --rdres 948c0000   ← system.apfs 的字节数（十六进制，不带 0x）
  └─ qemu/run.sh: -device loader,file=payload.bin,addr=0xF0000000
        （-drive fat:rw:esp 只是 loader 的 FAT 启动盘；system/root 两个镜像都不走 -drive）
xnuloader/loader.c (run_kernel)
  ├─ choose_window(): 取 UEFI 内存图最大空闲块作内核窗口
  │     实测（logs-qemu-run.log:25）：base=0xf4000000 size=0xc6000000
  ├─ 常驻镜像 = win_base + RESIDENT_RD_OFFSET(0x08000000) = 0xfc000000 —— 与 run-ios.sh 的摆放对齐
  ├─ payload 的 ramdisk(root.apfs) 拷到内核+常驻盘之后 → 第二块盘
  ├─ 设备树 chosen/memory-map：RAMDisk=<pa,size>（大/常驻=md0=root）、RAMDisk1=<pa,size>（小=md1）
  └─ cmdline 拼装（loader.c:3042-3105）：
        "debug=0x8 serial=3 "（有 UART 时）+ "cpus=1 "（payload 没写 cpus= 时）
      + "rd=md0 "（有 ramdisk 且 payload 没自带 rd= 时，loader.c:3062-3071）
      + ["hv_wdt_pet=1"]["ufs_shared_pa=0x…"]["battery_shared_pa=0x…"] + payload 自己的 cmdline
xnu 内核
  ├─ IOFindBSDRoot()（iokit/bsddev/IOKitBSDInit.cpp，redwood.patch:1685 起）
  │     读 chosen/memory-map 的 "RAMDisk" → mdevadd()（bsd/dev/memdev.c，mdSize 已被
  │     patch 成 64 位，≥4 GB 盘不溢出）→ /dev/md0；"RAMDisk1"（fork 新增）→ /dev/md1
  ├─ boot-arg `rd=` 只是设备名字符串（"md0"），不是 iBoot 式 disk0s1s1/哈希；
  │     fork 还加了 `rd=md*` 时把等 BSD root 的 30 s 超时缩到 0.1 s（内存盘不需要等 fs kext）
  └─ vfs_mountroot → vfstable 里 fork 注册的 "apfs"（bsd/vfs/vfs_conf.c patch，
        自带 apfs_mountroot；自研 APFS 驱动在 bsd/miscfs/apfs/，含 libdeflate/libzbitmap）
```

实测指纹（`logs-qemu-run.log`）：

```
25: largest free block f4000000 size c6000000
29: resident image at pa fc000000 size 948c0000: it is the root (md0), the payload ramdisk is md1
32: cmdline: debug=0x8 serial=3 cpus=1 rd=md0 loader_return_after=10800 epoch=… virtio_input=1 virtio_sound=1
115: BSD root: md0, major 1, minor 0
118: apfs: volume 0 "System" … 45138 files, … 605719 blocks of 4096 used
```

### 1.2 要点备忘

- `run-ios.sh:43` 的 `RD_ADDR=0xFC000000` 是**结果不是输入**：phys_base 由 UEFI 内存图选出来，QEMU 这次恰好选出 0xF4000000，+128 MB 偏移正好命中。真机上 loader 必须**先** `choose_window()` **再**往 `win_base+RESIDENT_RD_OFFSET` 写数据（USB 路径已经这么做，见 §3.D）。
- 两块盘的分工：**md0=root（大 system）**，md1=小 root.apfs（挂 `/redwood`，userland 的注入物）；launchd/内核只把 md0 当 RAM 盘启动看（loader.c:3183-3188 注释、init.c）。
- 常驻区约束（loader.c:26-34、3731）：镜像要在内核静态映射覆盖范围内（dt/bootargs 排在镜像之后，`topOfKernelData` 自动盖住；bootstrap 页表覆盖 8 GB，内核窗口上限 `MAX_MEM_SIZE`=6 GB）；可用大小 = `win_size − 128 MiB − RESIDENT_RD_RESERVE(768 MiB)`。
- loader 返回后常驻区不再被写（root 只读），**一次灌入可多次 run**——QEMU 与 `xl ramdisk` 共同的复用模式。
- `redwood_virtio_blk.c`（`/dev/rvblk0`，boot-arg `virtio_blk=1`）在 run-ios.sh 的启动路径里 **没有启用**——它是 APFS 驱动研发期读 host 大镜像（5.6 G rootfs.dmg）用的旁路，与 root 无关。

## 2. fork 现有存储驱动盘点（问题 2）

| 组件 | 位置 | 实态 |
|---|---|---|
| md/memdev | `xnu/redwood.patch`（memdev.c 段） | Apple 原码 + 64 位尺寸修正 + `mdevgetkernelrange()`；`rd=md0` root 的底座 |
| **APFS 文件系统** | `xnu/files/bsd/miscfs/apfs/`（**整个目录都是 fork 自研**，Apple OSS 不含 APFS） | 读为主（含写路径 apfs_write.c）、透明压缩 deflate/zbitmap、容器/多卷、`,c=N` 选容器、root mount、`kern.redwood_switch_root`（redwood_apfs_check.c:1733-1780） |
| virtio-blk | `xnu/files/bsd/dev/redwood_virtio_blk.c` | 仅 QEMU：MMIO 基址硬编码 0x0a000000（virt 机器），`virtio_blk=1` 才启用，只读；另有 `/dev/rsp0`（redwood_sparse.c，读大镜像的一段）。**与真机无关**（文件头注释自明） |
| **UFS 中转（loader 代读）** | `xnu/files/bsd/dev/redwood_ufs.c`(1.6k 行) + loader 端 `block_shared`（loader.c:1540-2260） | 内核→loader 共享页（magic "RDWBLOCK" v3）：请求(分区/LBA/读写)→loader 核 0 `block_poll()`（loader.c:2166，在核 0 看守循环里被调，loader.c:2441/2451）用 **EDK2 BlockIo** 服务→4 MiB 缓冲回传。生成 `/dev/ufs_<GPT名>` 每分区一个 + `/dev/ufs_unitN` 整 LUN；单请求深度、只读（写仅 `ufs_write=1` 限 darwin 分区一段）。**SoC 无关**（不碰任何寄存器） |
| **UFSHCI 原生（寄生式）** | `xnu/files/bsd/dev/redwood_ufshc.c`(1.3k 行)+`.h` | "借"UEFI 已拉起的控制器：停 UTRL 环→换内核自己的 32 槽传输列表→跑白名单只读命令（READ10/TUR…，逐条读回校验）→退出时换回 UEFI 的环。**无 reset/PHY/UIC/时钟初始化**。`UFSHC_PHYS=0x1d84000` |
| 中转开关（boot-args） | loader.c:2952-2976 | `ufs=1` 仅 survey；`ufs=2` = `hc_init()`+发布共享页（内核经 `ufs_shared_pa=` 接上）；`ufs_native=N` 内核自己的环；`ufs_probe=1` BlockIo 写探针；`ufs_check`/`ufs_bench`/`var_save_ms` 为测试 |
| Apple IOStorageFamily | — | **没有**：内核里无 IOBlockStorageDriver/IOMediaBSDClient/AppleANS kext（redwood.patch 仅一处取类名上下文），全部走 BSD cdevsw + 自研 APFS |

**真机 EDK2 侧（annibale 实测，docs/progress/2026-10-23-annibale-device-trials.md）**：

- Mu-Silicium FD（QcomPkg 全量 DXE）→ UFS BlockIo **读正常**；对 boot_a/misc/metadata/logfs/ xbl_sc_logs 五分区块 0 的写探针**全部不落地**（回 Android dd 验证保持原内容）——只影响 loader/内核侧**写**（日志分区、持久化），**不影响本里程碑的读路径**。
- annibale 目前 `skip_ufs_arbitration=1`（loader.c:4039，"ramdisk 内核，不交接 UFS"），`BOOTARGS` 里没有 `ufs=2`：中转链路在 K90 上**还没跑过**，但两端代码都是现成的。
- 巧合但重要：**SM8750 的 UFSHC 寄存器基址与 redwood（SM7325）同为 0x1d84000** （我方合并 DT：`/soc/ufshc@1d84000`，reg `1d84000/3000` + ice + `mcq_sqd 1da5000`——注意 UFSHCI 4.0 **MCQ**，见 §3.B/§4 风险）。loader 的 `HC_PA` 与内核 `UFSHC_PHYS` 常量都对得上。
- K90 无 `logdump` 分区：loader 日志回退写 boot_a（会写污染启动槽），且 BlockIo 写本来就不落地——调试期日志走"RAM 留痕 + warm reset 桥"（annibale-uefi-build.md 已立项）。

## 3. 真机选项评估（问题 3，全部给数）

### 3.0 关键容量数字（实测）

| 对象 | 字节 | 备注 |
|---|---|---|
| userland/system.apfs | **2,492,203,008**（2.32 GiB） | 选取后的 iOS root（7.9 G 全 root 裁到 45,138 文件）；605,719 个 4 KiB 块在用——**几乎是满的**，不是稀疏图 |
| system.apfs `gzip -6` | **2,406,100,090**（2.24 GiB） | 只缩 3.46%（APFS 内容/DSC 已是压缩态） |
| system.apfs `gzip -9` | 2,405,878,254 | 再省 0.01%，无意义 |
| root.apfs → gzip -6 | 4,194,304 → **200,650** | 小盘本来就在 payload 里，现 ~8 MB boot.img 的构成没问题 |
| dyld 共享缓存素材 | ~2.5 GiB（`ios165/20F66__iPhone10,3_6/dyld_shared_cache_arm64.*`） | 锁屏必用（所有进程链接它），system.apfs 的大头——**裁剪下限** |
| boot_a / boot_b 分区 | **100,663,296（96 MiB）** | `annibale-backup/…/partitions.txt:20`（sde14）；boot.img 现 8,034,304 B |
| LK `fastboot boot` 镜像上限 | ~2 MiB | 真机实测（超限 Load Error）；大镜像须 `fastboot flash boot_a` |
| XNUP payload 容器 | ≤ 0x04000000 − 4 KiB（**64 MiB**） | mkxnuimg.py assert + loader `PAYLOAD_MAX_SIZE` |
| 常驻盘可用 | `win_size − 128 MiB − 768 MiB` | loader.c:3731；K90 12/16 GB RAM、窗口上限 6 GB ⇒ 3.3 GiB 需求可满足，**T2 需实测 Mu 最大空闲块** |
| K90 可用大分区 | userdata 247,904,317,440；super 13,421,772,800；**rescue 仅 128 MiB、rawdump 仅 300 MiB、整个 LUN0(sde) 2,067,791,872 < system.apfs** | partitions.txt；镜像只能进 sda（244 GiB 那个 LUN）上的 super/userdata 域 |
| loader→内核中转 | 4 MiB 缓冲、单深度同步、≤160 分区 + 16 整 LUN | K90 全表 ~135 分区 + 6 LUN，在限内 |

### 3.A 全量 system.apfs 塞进 boot.img 当 ramdisk —— **否决（数字）**

- 需要 boot.img ⊇ payload ⊇ gzip(system)= **2.24 GiB**：vs boot_a **96 MiB → 差 23.9×**；vs payload 容器 64 MiB → 差 36×；vs LK boot 2 MiB → 差 1146×。（即便从 boot_a 起、gzip 由 LK 解包，LK 的解压暂存区也远小于 2.24 GiB。）
- 裁内容也救不了：锁屏 = launchd+SpringBoard+backboardd… 全走 DSC，**DSC 单独就 ~2 GB**，gzip 不动它（整盘实测才缩 3.5%）。
- 唯一变体：连 DSC 都不要的"迷你 root"只能回到 4 MB root.apfs 的世界（无 iOS UI），那是现状而不是方案。**结论：A 只适用于小 boot 卷，不适用于全系统。**

### 3.B XNU 直驱 SM8750 UFS —— 两个档

**B1. 中转式 flash-root（fork 已有全链路，upstream 已验证到全 iOS）**

- 做法：boot-args `ufs=2`（loader 发布共享页，内核 `redwood_ufs.c` 出 `/dev/ufs_*`）
  + RAM 里放 `flashboot.apfs`（FLASHBOOT=1 产物：boot 卷 [+可选 cryptex]）
  + stage0 `root_apfs=/dev/ufs_darwin`：挂 iOS 卷→bind 我们的 LaunchDaemons/HAL→ `sysctl kern.redwood_switch_root` 把 root 换成 flash 卷（userland/src/init.c:118-270、1436）。upstream 在 flash 上的布局：iOS 卷（4 KiB 块 0..1374207，即 5.6 G rootfs 卷）+ OS/App cryptex （=同设备容器 1/2）+ var 区。
- 需要写/移植的：**几乎只有数据面**——K90 上要造一个 darwin 类分区并 dd 全量镜像（redwood 用 `tools/android/f2fs-resize.c` + GPT 改写从 userdata 切 20 GiB；K90 userdata 同为 f2fs，可行性文档记录同法，纪律：同一次 Android 会话内缩容+改 GPT，GPT 已有备份）；写入口用 **Android 侧 dd**（`tools/darwin-write.py` 模式），绕开 EDK2 写不落地。
- 代价/风险：运行期**每个 read 都过单深度同步中转**，DSC 冷读全走这条路，锁屏时间会是分钟级；加速靠 `ufs_native=1`（内核换环），但 SM8750 是 UFSHCI 4.0+MCQ——redwood 的"slot 0 证明" 白名单法基于 legacy UTRL 假设，**需真机验证**（风险中）。loader 必须常驻核 0（内核 `bootcpu=` 跑另一核）。
- 定位：**持久化时代的正解 + 本里程碑的稳健二线**（比 D 多：分区备料、flashboot 镜像、中转链路首跑）。

**B2. 从零的寄存器级 UFSHCI 驱动（内核独立拥有控制器）**

- 要写：PHY bring-up（qmp-v4-sun，DTS `ufsphy_mem@1d80000`）、GCC 时钟/GDSC （`gcc_ufs_mem_phy_gdsc` 等）、regulator/VCC 时序、UniPro/link startup、UIC commands、SCSI INQUIRY/READ(16)、中断或轮询、与 EDK2 的交接或 ExitBootServices 后独立初始化；SM8750 还有 MCQ、HWKM（`qcom,ice-use-hwkm`）等差异。
- 现成资产只有"寄生"驱动 redwood_ufshc.c（无 init 路径）+ JESD223 寄存器定义。
- 工作量：**周级**，且 K90 日志通道未通（黑盒调寄存器极痛）。**本期不做**，写入远期。

### 3.C loader 预读进 RAM（推荐主路线，"路线 D"）

把 QEMU/`xl ramdisk` 已在用的"常驻 md0"布局搬到真机自举：

```
boot.img(不变, ~8 MB) ─▶ BootShim ─▶ Mu UEFI(DXE: UFS/GOP/…) ─▶ loader
  loader: choose_window() → 从 BlockIo 找到镜像所在分区/区段
          → 顺序读 2.32 GB 到 win_base+128 MiB（分块 + 缓存维护）→ resident_rd_size = 大小
  run_kernel(): RAMDisk=<pa,size>（md0=root）+ payload 的 root.apfs（md1=/redwood）
          → 与 logs-qemu-run.log 指纹逐字一致的路径进 iOS
```

- **内核零改动**、boot.img 尺寸零变化；现变体 B 的 payload 只含 loader+kernel（~15.7 MB），照 `xl run` 的做法把 root.apfs 加回 payload 条目即可（`ramdisk=root.apfs`，仍远小于 64 MiB 上限）。loader 新增 ~200-300 行：新 payload/cmdline 条目（如 `rdpart=<GPT名|unitN>[@起始LBA]:<块数>`）、BlockIo 循环读、进度打点、抽样读回校验。
- 镜像落盘：Android(root) `dd` 到选定区段，再 dd 回读比对：首选 **super 尾部空闲 extent**（super 13.4 GiB 在 sda；`tools/ufs-super.py` 就是"super 里哪里没有主"的现成工具——loader `ufs=1` survey 的日志喂它即得空闲区间；不碰 GPT、不伤 Android 动态分区，回退=刷回 super）；次选按 upstream 法从 userdata 切小分区。注意别选 LUN0（整 LUN 才 1.93 GiB < 镜像）；rescue/rawdump 都放不下。
- 时长账：读的是未压缩 dd 的 2.32 GiB ÷ EDK2 UFS 读带宽——QcomPkg DXE 通常 100-500 MB/s，即 **5-25 s**；现在 EDK2 全量 DXE 本来就要 ~40 s，占比可接受。T2 打点实测。
- 内存账（K90 待实测，T2 第一步）：Mu 内存图最大空闲块 ≥ 128 MiB+2.32 GiB+768 MiB ≈ 3.3 GiB。不够则调 annibalePkg MemoryMapLib/`choose_window`（K90 12 GB RAM，理论轻松；QEMU 7 GB 客体内都跑通了同布局）。
- 复用红利：预读逻辑与 USB `oem ramdisk` 下载写的是同一个常驻区（loader.c:3744-3775 已有 dest/limit 计算），两种灌法一套代码；镜像进 RAM 后可反复 run、内核重启不重读。

### 3.D PC 经 USB 灌常驻区（现状即有，等 USB 修复）

- `xl ramdisk userland/system.apfs` → `oem ramdisk` + `download:` 直写 `win_base+RESIDENT_RD_OFFSET`，置 `resident_rd_size=总长`，**已实现且 upstream 天天用**；上限 = `win_size−128 MiB−768 MiB`（`max-download-size: 0xffffffff`）。
- K90 卡点：gadget 枚举 OK（18d1:d00d）但 OUT 端点数据不进 `usb_rx` （QCOM_USB_DEVICE TransferNotification 疑似不触发，trials 文档 §2）。修好即为 **零新存储代码的"锁屏"通路**，同时解锁 loader 日志（`xl log`）——这也是 §4 把它列为 T0 的原因。
- 定位：调试期主力 + C 路线的对照组；"不依赖 host 文件"最终由 C 满足。

### 3.E 其它被考虑过的小方案

- **小 initramfs 只到 panic 前**：现状（root.apfs 4 MB 当 root）就是它——能验证内核起没起，到不了锁屏（没有 launchd 全家 + DSC）。作为 B/C 的回归基准保留。
- md1 的用途提醒：完整启动时 root.apfs 不是 root 而是 `/redwood`（注入物），方案 C/D 都保留"payload 带 root.apfs"的形态，不要只发 system 不发 root。

## 4. 推荐路线与任务分解（问题 4）

**推荐：D 为主线（loader BlockIo 预读 → 常驻 md0），A 否决，B2 缓行；B1 二线，D-USB 先行。** 与 `docs/progress/2026-10-23-annibale-device-trials.md` 既定的"rootfs 路线 D"一致，本文补齐数据与落点选择。

| # | 任务 | 产物/验收 | 依赖 | 预估 |
|---|---|---|---|---|
| T0 | **修 loader USB**（QCOM_USB_DEVICE OUT 通知，idalib 查 QcomPkg 端点路径） | `xl state/log/run` 全通；`xl ramdisk system.apfs && xl run` 真机进 iOS 桌面（= 锁屏达成，host 在场） | — | 1-3 天，卡点已有明确嫌疑 |
| T1 | **镜像落盘区段选定 + 备料脚本**：`ufs=1` survey → `tools/ufs-super.py` 找 super 空闲 extent；写 K90 版 darwin-write（区段身份核验 + dd + 回读 sha256） | system.apfs 在 super 尾部可用区，Android 下 dd 回读哈希一致 | — | 0.5-1 天 |
| T2 | **loader 预读**（xnuloader/loader.c）：新条目 `rdpart=`；choose_window 后定位 BlockIo→分块读（1-4 MiB/次）→ 置 `resident_rd_size`；进度/耗时经 RAM 留痕日志桥回读；启动前抽样读回校验 | `flash boot_a` 后**无 PC** 开机；loader 段日志出现 `resident image at pa … size 948c0000`，内核日志复现 `BSD root: md0 … "System" 45138 files` | T1（面板/日志桥并行） | 2-4 天 |
| T3 | **端到端联调：真机锁屏**（verbose/GOP 屏显 + `xl screenshot` 或日志桥；`loader_return_after` 长跑到 SpringBoard） | 锁屏/桌面图归档 docs/progress/evidence | T2；面板 M3 | — |
| T4 | 回归护栏：QEMU `run-ios.sh` 与 root.apfs/md1 路径逐字不变；boot.img ≤ 9 MB（boot_a 内） | CI/手工清单 | T2 | 0.5 天 |
| T5 | **二线 B1 备料**（持久化前站）：K90 版 userdata 缩容切 darwin；FLASHBOOT=1 全量 rootfs.apfs+cryptex dd；`ufs=2 root_apfs=/dev/ufs_darwin` 首跑（顺带验证 K90 中转链路） | flash 上 iOS 卷作 root 起 launchd | T0/T1 | 3-5 天，可与 T2 并行 |
| T6 | （可选）`ufs_native=1` 在 SM8750 的可行性探针：UEFI 环是否 legacy UTRL、MCQ 语义 | 结论回写本文 §3.B | T5 跑出性能痛点后 | 2 天+ |

**角色建议**：T0/T2 需要熟 loader/QcomPkg 的人；T1 熟 Android 侧（dd/f2fs/GPT）的人；T5 与 GPT/持久化规划统一人；面板（M3 主线）与 T0 并行，T3 汇合。

**风险登记（存储相关）**

| 风险 | 影响 | 缓解 |
|---|---|---|
| Mu 内存图最大空闲块 < 3.3 GiB（或内核窗 6 GiB 上限吃紧） | D 路线放不下常驻盘 | T2 先 `oem memmap`/Mu 内存图实测；必要时调 annibalePkg MemoryMapLib carveout |
| super 尾部 extent 被 HyperOS 重刷改变 | 镜像错位读成花 | 写镜像时在区段头落 magic+长度副本；loader 校验不过即 FAIL 不盲挂 |
| EDK2 UFS 读带宽过低（<30 MB/s） | 开机 +80 s 量级 | T2 打点；退化方案=B1（flash root） |
| BlockIo 写不落地未修 | loader 日志/持久化受阻（**不阻 D 读路径**） | 日志桥先行；修复另案 |
| SM8750 MCQ 使 native 换环假设失效 | B1 性能手段受限 | 中转单深度仍可用；T6 探明后再决定是否投 B2 |

## 5. 证据索引

- 摆放/参数：[qemu/run-ios.sh](../../hackios-xnu-kernel/qemu/run-ios.sh)（39-43、87-88 行）、[qemu/run.sh](../../hackios-xnu-kernel/qemu/run.sh)、[xnuloader/loader.c](../../hackios-xnu-kernel/xnuloader/loader.c)（26-34、2585-2634、2752-2806、2862-2927、3042-3105、3183-3197、3690-3775、4039）
- 内核侧：`hackios-xnu-kernel/xnu/redwood.patch`（memdev.c、IOKitBSDInit.cpp RAMDisk/RAMDisk1、bsd_init、vfs_conf APFS vfstable）；`xnu/files/bsd/dev/redwood_{virtio_blk,ufs,ufshc}.c`、`redwood_apfs_check.c:1733-1780`；`userland/src/init.c:37-270,1436`
- 运行指纹：`logs-qemu-run.log:25-32,113-128`（md0=0xfc000000/0x948c0000、`rd=md0`、"System" 卷）
- 真机事实：[docs/progress/2026-10-23-annibale-device-trials.md](../progress/2026-10-23-annibale-device-trials.md) （读 OK/写不落地、USB 卡点、LK 容量上限）、[docs/analysis/annibale-uefi-build.md](annibale-uefi-build.md)、[docs/plan/porting-plan.md](../plan/porting-plan.md)
- 分区表：`annibale-backup/20261022-2355/partitions.txt`（boot_a=100,663,296、super、userdata）
- SoC 事实：`docs/analysis/data/annibale.dts.gz` 合并 DT：`/soc/ufshc@1d84000` （与 loader `HC_PA`/内核 `UFSHC_PHYS` 同值；含 mcq 寄存器）
- 尺寸实测：`gzip -6/-9` 于 `hackios-xnu-kernel/userland/{system,root}.apfs`（本文 §3.0 表）
