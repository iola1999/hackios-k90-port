# REDMI K90（annibale）× HackiOS — 可行性分析与实测记录

> 整理自 2026-10-22 会话。**2026-10-23 机型纠偏**：此前 KernelSU 开着「机型伪装」模块，把它上报成了 K90 Pro Max（25102RKBEC）。禁用重启后真实身份：**REDMI K90** （model **2510DRK44C**，代号 **annibale**；Pro Max 的代号是 **myron**，是另一款机器）。
>
> - SoC 结论**不受影响**：kernel 侧 `/sys/devices/soc0`（soc_id 618 / 「SUN」）、本机 dtb（`model="Annibale based on SM8750"`，`msm-id=0x26a`=618）、GPU compatible （gen8-0-1=a830）与社区 TWRP 树（platform `sun`）四方独立一致 = **SM8750 属实**。
> - 受影响的是市场型号命名、以及凡**取自 Android props/display 的服务层数值**（如屏幕分辨率）需以禁用伪装后的读数为准，本文档相关处已就地修正。
> - HyperOS / Android 16，build `BP2A.250605.031.A3`，KernelSU root，**当前活动槽 `_b`**。涉及工程：`hackios-xnu-kernel` + `hackios-xnu-userland`（OSEOX GANG 的 HackiOS，把 iOS 16.5 的 XNU 内核 + 未修改的 iOS 用户态跑在安卓手机 / QEMU 上）。

---

## 1. 结论速览

1. **可行性**：架构上无死结，同高通家族、GICv3+PSCI 骨架与 redwood 同路；但 778G→8 Elite 跨 4~5 代，**最大门槛是给 SM8750 做 UEFI**（Mu-Silicium 尚无 SM8750 平台包），GPU（Adreno 830 / Mesa 无 a8xx 后端）和 Wi-Fi（WCN785x = ath12k，非 ath11k）是第二梯队工作。第一阶段目标：无 GPU/无 Wi-Fi，framebuffer+触摸软渲染进锁屏（与 QEMU 形态等价）。
2. **调试不需要格式化手机存储**：日常全部跑 RAM；持久化测试才需要「缩容 + 改 GPT」（非格式化）；唯一真正的清数据事件是解锁 bootloader 那一次。
3. **`fastboot boot` 实测通过**（此前存疑）：本机（K90）的 XBL fastboot 接受 `boot` 命令，发原厂 boot 镜像 `Sending/Booting OKAY`，手机随即正常回到 Android，无任何损伤。
4. **分区备份完成且与 NAS 四月备份互证一致**：本地 123 个分区（全部 ≤2GiB）+ 6 个 LUN 的 GPT 头尾；与 NAS 旧备份共同的分区 113 个逐字节一致，6 个差异全部可解释（见 §4.3）。

---

## 2. 两个仓库的关系（背景摘要）

| 仓库 | 作用 |
|---|---|
| `hackios-xnu-kernel` | XNU 补丁（基于 iOS 16.5 的 `xnu-8796.121.2`）、EFI loader（`xnuloader/`）、Mu-Silicium UEFI 移植（`uefi/`）、ath11k 兼容层（`wifi/lx/`）、QEMU 脚本、`xl` 手机工具、`common/` 构建脚本、预编译产物 |
| `hackios-xnu-userland` | 1 号进程 init、注入 backboardd/SpringBoard/mediaserverd 的库、launchd jobs、APFS 镜像工厂（`userland/build.sh`）、IPSW 抽取脚本、Mesa/AIR（Metal）工作 |

两仓库**合成同一棵树**构建（`common/setup.sh` 把 userland 以 `.userland.git` 检出到 kernel 仓库目录，`common/ugit` 操作之）；仓库内不含任何 Apple 文件（`ios165/fetch.sh` 现场从苹果 CDN 拉取）。启动链：`fastboot boot` → UEFI（Mu-Silicium）→ xnuloader（驻留，提供 USB fastboot 通道/看门狗/日志）→ XNU（驱动替身：APFS、AMFI/Sandbox 替身、IOSurface、输入、GPU、Wi-Fi、音频）→ 原版 iOS launchd → SpringBoard。

## 3. 本机（K90 annibale）硬件体检

| 项目 | 实测值 | 对移植的意义 |
|---|---|---|
| SoC | SM8750（骁龙 8 Elite），dtb `qcom,sun` | 比 redwood（SM7325）新 4~5 代 |
| CPU | 6×`0x514f0014` + 2×`0x513f0014`（Oryon），PSCI(SMC)，MPIDR `0,0x100..0x500 / 0x10000,0x10100` | `core_shift=8` 与 loader 假设一致；`small_cores`=前 6 核；armv9.2，PAC/BTI 齐（arm64e OK）；**无 AArch32**（iOS 16 全 64 位，无害） |
| GIC | `arm,gic-v3` @0x16000000，redist @0x16080000，+ITS | loader 平台表直接可填；XNU 现成支持 |
| GPU | **Adreno 830**（`qcom,adreno-gpu-gen8-0-1`），固件 `gen80000_gmu.bin/sqe.fw/aqe.fw/zap.mbn` 在机 | freedreno/Mesa 25.0.7 无 a8xx → 第一阶段不启用 GPU |
| Wi-Fi/BT | PCIe `17cb:1107` = WCN785x（FastConnect 7900，Wi-Fi 7） | 需要 **ath12k** 移植（现有是 ath11k）+ PCIe gen4 PHY |
| 触摸屏 | **Goodix @ SPI**（dtb `xiaomi,touch-spi` + `goodix,*`，irq/reset GPIO 有节点） | 与 redwood Goodix-GT9916 驱动同族，可改造复用 |
| 屏 | DSI 1156×2510 @120Hz（SDE，Android 渲染分辨率，禁伪装后不变；社区树载**物理面板 1200×2608@480dpi**——比值为渲染缩放，面板驱动以真实时序为准） | UEFI 需驱动此面板出 GOP（最大难点） |
| 存储 | UFS 4.1（`1d84000.ufshc` 同基址，LUN0 238GB） | `redwood_ufshc.c` 同源可改 |
| RAM | 16 GB | 2.5GB 镜像灌 RAM 无压力 |
| hypervisor | Android 侧跑在 Gunyah 下（`gunyah_rm` 中断、`vm-bootsys`） | XBL 直接引导我们的镜像，Gunyah 不构成前置；细节待 UEFI 起来后验证 |
| 引导 | A/B 槽；`xbl`(LUN1/2)、`uefi_a/b`(5MB!)、`abl`、`init_boot` 分离布局；活动槽 `_b` | `uefi_a` 库存 UEFI 已备份，移植参考资料；实验可用空闲的 `_a` 槽 |
| root | KernelSU（`u:r:ksu:s0`），patch 的是 **init_boot_b** | boot_a/b 内核仍是纯原厂（备份哈希与 4 月 NAS 一致） |

设备树已归档：`annibale.fdt`（原件）与 `annibale.dts.gz`（反编译）在本目录。

## 4. `fastboot boot` 实测（本次会话核心验证）

背景：此前「小米 fastboot 不支持 `fastboot boot`」是老机型（LK 时代）的传闻；redwood（POCO X5 Pro，同为小米系）的 `xl enter` 就是靠 `fastboot boot` 起 UEFI 的（[xl:88](../hackios-xnu-kernel/xl)，且注释提示「刚进 fastboot 第一次 boot 偶尔不生效，需重试」）。本机（K90）上实测：

```text
$ fastboot getvar unlocked            → unlocked: yes
$ fastboot boot boot_a.img            → Sending 'boot.img' (98304 KB)  OKAY [2.260s]
                                        Booting                       OKAY [0.167s]
（~10s 后 adbd 重新出现，boot_completed=1，root 正常，bootmode 正常）
```

- **协议层面完全支持**，一次 OKAY，无 redwood 的重试怪癖。产物：`fastboot-test/getvar-all.txt` （含 cpuid、Xiaomi token——**token 属认证信息，勿外传**）、`fastboot-test/fastboot-boot.txt`。
- **一个诚实的保留项**：`boot_a` 与 `boot_b` 的内核字节级同版（6.6.77 GKI 同构建），因此本次测试无法区分「XBL 真正引导了暂存镜像」还是「回落到槽上镜像正常启动」。这个区分要等自制的 BootShim/UEFI 镜像——其特征（USB 上出现 `xnuloader` fastboot 设备）一眼可辨。按 HackiOS 的风险模型，「命令被拒」这一否决项已排除。
- `getvar all` 还显示：`awu:yes`、`parallel-download-flash:yes`、擦除/逻辑块 4096（GPT dd 恢复按此对齐）。

## 5. 分区备份

### 4.1 本次备份（Mac 本地）

- 位置：`../annibale-backup/20261022-2355/`（gzip-1，每分区一个 `*.img.gz`）
- 范围：全部 ≤2GiB 的具名分区共 **123 个**（含 `modemst1/2`、`fsg/fsc`、`persist`、`modem_a/b`、`modemfirmware_a/b`、`bluetooth`、`dsp`、`tz/hyp/xbl/abl/uefi`、boot 全家桶、校准/密钥小分区），跳过 `super`/`userdata`（>2GiB）与日志dump类（blackbox/rawdump/oops/logfs/mdcompress/rescue/qmcs/gsort/ffu/mtdblk）。
- 校验：每个包 gunzip 完整性 + 解出字节数与分区大小一致；关键 7 分区（modemst1/2、fsg、persist、keystore、devinfo、secdata）另存**设备侧** sha256（`sha256-device.txt`）；本地包哈希在 `sha256-local.gz.txt`。
- **GPT**：6 个 LUN 的头、尾各 32KB（`gpt/sdX-head.bin`、`gpt/sdX-tail.bin`，4K 扇区×8；尾部第一次抓取因 toybox blockdev 不支持 `--getnumsectors` 而落空，已用 `/sys/block/*/size` 重抓）。
- 清单：`partitions.txt`、`by-name-ls.txt`、`backup.log`、对比结果 `nas-compare.txt`。

### 4.2 NAS 上的旧备份（2026-04-26）

`${BACKUP_DIR}/adb_partition_backup_annibale_20260426_022802/` （124 个 raw img + SHA256SUMS + meta/ 全套，当时活动槽也是 `_b`，选取思路与本次一致）。

### 4.3 对比结论：一致

- **113 个分区逐字节一致**（含所有关键静态分区：modem/modemfirmware/fsg/fsc/bluetooth/dsp/tz/hyp/xbl/uefi/abl/boot_a/b…）。
- 6 个不一致，全部可解释：
  | 分区 | 原因 |
  |---|---|
  | `init_boot_b` | KernelSU 刷入（4 月之后打的补丁）——KSU 只动活动槽 init_boot，与 boot_a/b 未变互相印证 |
  | `modemst1`/`modemst2` | 基带 NV/字库是运行时会写入的，活机备份必然变化 |
  | `persist`/`metadata`/`vm-persist` | 厂商守护进程状态 / dm-key 元数据 / Gunyah VM 状态，属动态数据 |
- 4 个「NAS 缺失」（dbg、xbl_ramdump_a/b、xbl_sc_logs）是 NAS 当时有意跳过的日志区，本次已补。
- 结论：两份备份互为印证、可互为恢复源。恢复方法见 `../annibale-backup/README.md`。

## 6. 存储/格式化三档结论

1. **日常调试：零写入**。镜像走 `xl ramdisk` 进 RAM，`/private/var` 是 ramfs；内核 UFS 驱动默认全部分区 `EROFS`（`redwood_ufs.c`："Without ufs_write=1 nothing writes at all"）。
2. **入场写入（一次性/可逆）**：解锁 bootloader 清一次用户数据；（若 fastboot boot 实测后仍需刷）UEFI 只占 boot 分区——且 K90 有 A/B 双槽，可固定用空闲的 `_a` 槽做实验，`_b` 原样保留。
3. **持久化测试（可选，非格式化）**：`var_store=1 ufs_write=1` 需要一块自己的分区——`userdata-carve.py` 用 Android 内核 ioctl 原地缩容 f2fs + 重写双份 GPT 切出 `darwin`。**K90 适配点**：本机 `/data` 是 **dm-default-key（inlinecrypt 加密）之上的 f2fs**，redwood 工具 「超级块裸奔在 flash」的前提不成立，脚本会拒收，需要改造；"缩容+改 GPT 必须在同一次 Android 会话内完成（防 fs_mgr 自动长大）"这条纪律依然适用。动手前先备份 GPT（已有）。

## 7. 移植工作分解（对应上游 docs/PORTING.md 五步，K90 具体化）

| 步骤 | 内容 | 量级 |
|---|---|---|
| 1 UEFI | ~~Mu-Silicium 无 SM8750 包~~（2026-10-23 更新：主线已有 PakalaPkg=SM8750，见 uefi-sm8750.md）→ 以其为基座出 annibale pkg：本机 `xbl`/`uefi_a` 抽 DXE、DSI 面板 bring-up、BootShim+XNUP 容器、内存图（FD_BASE/PAYLOAD_BASE） | 中（1–3 月，有 dodge/pagani 先例） |
| 2 Loader | `common/new-device.sh annibale annibale.fdt` 出骨架；GIC/核数/core_shift/small_cores/psci_smc 已具备数字；fb_base 等 UEFI 起来后抄 | 天级 |
| 3 内核 | 通用件直接复用（GICv3/timer/PSCI/APFS/返回 loader）。需改：ufshc 时钟参数、pinctrl/SPMI/PMIC（PMK8850 系）、cpufreq（8 Elite 时钟路径）、按钮/看门狗地址、Goodix SPI 驱动（新控制器协议）、PCIe gen4 QMP PHY；后置：Adreno830/gen8（等 Mesa a8xx）、ath12k、ADSP/wcd 新音频 | 周级~月级 |
| 4 固件 | 从本机拉：`gen80000_*`（GPU）、`adsp.*`（音频）、WCN785x wifi/bt 固件；路径写进 `annibale.conf` | 天级 |
| 5 跑 | `common/build.sh annibale && common/run.sh annibale`；里程碑：loader USB 日志 → 内核 verbose → 锁屏 | — |

## 8. 风险与下一步

**风险**：SM8750 UEFI 无现成底子是最大不确定性（可跟进 WoA/edk2-msm 社区 SM8750 进展）；Gunyah 环境下 EL2/内存图细节；modemst 等校准分区恢复顺序；HyperOS 升级可能改分区表（改前先 diff `partitions.txt`）。

**下一步清单**：
- [ ] `common/setup.sh` 合并两仓库为一棵树（当前本地是并列目录，跑构建前必须做）
- [ ] 跟进/评估 SM8750 的 UEFI 底子（edk2-msm 社区分支、原厂 `uefi_a` 逆向）
- [ ] `common/new-device.sh annibale hackios-k90-notes/annibale.fdt` 生成 profile + platform 骨架
- [ ] 若做持久化：先改造 `userdata-carve.py` 适配 dm-default-key f2fs
- [ ] Mac 上先跑 QEMU 链路验证整套工具（`ios165/fetch.sh` 需 7.4GB 下载与 Linux 环境）

## 9. 附录：文件索引

- 本目录：`README.md`（本文）、`annibale.fdt`、`annibale.dts.gz`、`fastboot-test/{getvar-all.txt,fastboot-boot.txt}`
- 本次备份：`../annibale-backup/20261022-2355/`（含 `nas-compare.txt`）、恢复说明 `../annibale-backup/README.md`
- NAS 旧备份：`${BACKUP_DIR}/adb_partition_backup_annibale_20260426_022802/`
- 上游仓库：`hackios-xnu-kernel`、`.../hackios-xnu-userland`
