# 2026-10-23 离线准备轮（设备 blackout，用户不在手机前）

背景：slot_a 变体 B（PLAT 修复后）在真机上静默循环，USB 无反应，用户不便操作
——按指示转向"准备好直到开机+图形+触摸/震动/联网资源"的离线工作。

## 完成

1. **rootfs 路线 D 落地（变体 C，transport 全链路就绪）**
   - loader `rdfile=<分区>:<字节>[:<偏移>|tail]` XNUP 条目：起内核前用 EDK2
     BlockIo（读实测可用）把 system.apfs 从分区批量预读进常驻窗
     （phys_base+RESIDENT_RD_OFFSET），先 memset 清零再填（QEMU 稀疏文件的
     洞=零，这边手工补），1MB 弹跳缓冲，进度打印。复用 QEMU rdres 的
     全部下游（md0=root/md1=ramdisk 语义在 loader.c DT writer 处实证一致）。
     kernel 72bbea4。
   - mkpayload `--rdfile`；`tools/stage-system.sh`（Android 侧 dd 到 userdata 尾，
     不动 f2fs 头部；每轮试前重跑防 f2fs 写花）。
   - `xnu-annibale-c.img` 8,237,056 B 编译就绪（boot_a 100,663,296 B 富余）。
   - 备选：super 尾部空闲 extent 更稳（f2fs 碰不到），偏移等 `ufs=1` 日志 +
     tools/ufs-super.py 解析后固化。
2. **图形直通定案（本轮最大发现）**：内核显示只认 BootArgs.video（QEMU ramfb
   实证；chosen 无 framebuffer 属性）。GOP==NULL 时 loader 现把 LK splash 区
   0xFC800000 当 fb 交给内核（kernel a6bdbab）→ **真机图形锁屏不需要 MDSS 驱动**。
   启动方式必须 `--set-active=a + reboot`（LK 点屏），`fastboot boot` 黑屏。
   splash_region@0xfc800000 与 DT/Display_Reserved 三方同址已在 hw-map 复核。
3. **sub agent 交付验收**（各 1 个，符合 ≤3 约束）：
   - rootfs-strategy.md 终版（含对我早期草稿 4 处勘误：gzip 只 -3.5%、boot_a
     实测 96MiB、rd=md0 只是设备名、B1 FLASHBOOT 二线定位）。数字已抽查复核。
   - annibale-hw-map.md 5553 节点重写版；**两处勘误被我在权威 DT 上证实**：
     触摸 SPI=spi@a88000(SE2)（a8c000 是 I2C SE3×fsa4480）；DT 确有
     splash_region 0xfc800000+0x2b00000（我此前"无显示 carveout"结论错误）。
4. **外设驱动盘点**进 porting-plan M3：fork 真机驱动 = bsd/dev/redwood_*.c 裸
   寄存器全家桶（goodix 触摸/haptic/wifi/ufshc/adreno 3800 行含面板），annibale
   适配 = 逐驱动换 gcc/pinctrl/PMIC 常数；触摸天级、震动天级、Wi-Fi 月级、
   相机未映射最后做。

## 下午追加（同一离线轮的后半段）

5. **内核自建流水线跑通**（详见 docs/analysis/kernel-build-linux.md）：Docker
   `kbuild` 容器（--platform linux/amd64）theos+clang-11 工具链全量构建 ~35min，
   增量构建只重编改动文件。首产物已替换 `prebuilt/mach.development.bcm2837`
   （kernel 8a86129；旧版 9239d4ad… 仍在 git 历史可 A/B）。
6. **触摸 annibale 参数化完成**（kernel cc9ff58，文档见 porting-plan 盘点）：
   `redwood_goodix.c` 常数改运行时表，boot-arg `touchscreen=2` 选 annibale 板
   参数（TLMM/SE 时钟/ldob12 供电/SMEM 扫 cmd_db），redwood 常数零改动。
   期间打掉两个 host 构建坑（strlcpy shim 63f0f01、varinit 探测缓存 b7ac03a）。
7. **QEMU 回归通过（自建内核开机进 SpringBoard）**。插曲记入 playbook 陷阱 9：
   DIRECT_PHONE_PLAT 版 loader 喂给 QEMU 会让内核 5.8s 卡死（GIC 对不上），
   排查 A/B 掉新旧内核后才定位——**两种 loader 谁用谁现编**。
8. **c.img 重打包**：8,022,016 B，payload bytesum=5630d796，内嵌自建内核 +
   DIRECT_PHONE_PLAT loader + rdfile 参数。装配线必须在 hackios-dev 容器里跑
   （宿主缺 llvm-objcopy，BootShim 重编需要）。
9. **震动驱动完成**（kernel 2006f81 + prebuilt 1dfe4b2）：新文件
   `redwood_haptic_hv.c`，自带 SPMI **v7** master（arbiter 布局与 redwood 的 v5
   完全不同：obsrvr/chnls/core+0x2000 通道表），`hv_haptic=1..4` 四级，参数照抄
   设备树（hv-haptics TI 内置马达，5714us/1300mV/brake ff 3f 1f）。容器增量编译
   ≈2min（全量 35min），产物 +17KB；QEMU 回归再次进 SpringBoard（不带旗标=驱动
   惰性，证明挂载/初始化安全）。c.img 重打包 8,028,160 B / bytesum=564237e9。
   真机验收=cmdline 加 `hv_haptic=3` 数秒后**手感 30ms 震动**，无需屏幕。
10. **Wi-Fi 移植调研完成**：`docs/plan/wcn7850-plan.md`。勘误红杉链路（PIL+GLINK/
    QMI，无 MHI）；annibale WCN7850 走 PCIe RC0@0x1c00000 + MHI，fork 内核两块
    全新增，估算 4–8 周真机窗口起步。硬前提：先 dump vendor 分区拿固件。
11. **GPU 移植调研完成**：`docs/plan/gpu-plan.md`。上游 Linux v7.3 已收 a8xx
    （288a9320，复用 a6xx GMU/HFI 框架）；SM8750 基址从设备树拆齐（3D 0x3d00000、
    GMU 0x3d37000、GPUCC 0x3d90000、SMMU 0x3da0000…），chipid 0x44050000 需自扩
    catalog。红杉全链路（上电阶梯→Mesa redwood-drm 桩→Mini IOSurface/FB→Metal
    半成品）盘点完毕，L1/L2/L3 三级均不动 iOS 用户态。头号外部未知：Mesa 的
    a8xx 是 GLES(freedreno) 还是只有 Vulkan(turnip)——下个离线日 GitLab 恢复后核实。

## 等设备回到视野后（按序）

0. **暂停门**：评审指出 stage-system.sh 往 userdata 尾部写 2.4G 前不校验块占用、
   且备份不含 userdata；用户指示当前一切调试限 RAM 启动、不做持久化。
   → 变体 C 的暂存步骤**先问用户**；空窗期可先走 A（USB 诊断，纯 RAM）与
   super 尾部空闲 extent 的只读勘察（loader `ufs=1` 日志 + tools/ufs-super.py）。

1. `tools/stage-system.sh` → flash `xnu-annibale-c.img` boot_a → `--set-active=a`
   → `reboot` → **看屏**（图形=里程碑；乱码=改 1440x3200 几何；黑+循环=取证回 b）。
2. 同场加 LK-splash 截图需求：屏摄几张（LK splash / iOS 画面）归档 evidence/。
3. loader USB 通道（QCOM_USB_DEVICE OUT 通知）继续排查——现在只是锦上添花
   （屏就是日志通道了）。

## 设备状态备忘

slot _a active（boot_a=auto.img 8,034,304 B 旧版），静默循环；`--set-active=b`
随时可回用户 Android（boot_b/userdata 头未动）。c.img 与本轮所有镜像在
hackios-xnu-kernel/ 根目录（gitignore）。
