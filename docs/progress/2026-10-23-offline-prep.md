# 2026-10-23 离线准备轮（设备 blackout，用户不在手机前）

背景：slot_a 变体 B（PLAT 修复后）在真机上静默循环，USB 无反应，用户不便操作——按指示转向"准备好直到开机+图形+触摸/震动/联网资源"的离线工作。

## 完成

1. **rootfs 路线 D 落地（变体 C，transport 全链路就绪）**
   - loader `rdfile=<分区>:<字节>[:<偏移>|tail]` XNUP 条目：起内核前用 EDK2 BlockIo（读实测可用）把 system.apfs 从分区批量预读进常驻窗（phys_base+RESIDENT_RD_OFFSET），先 memset 清零再填（QEMU 稀疏文件的洞=零，这边手工补），1MB 弹跳缓冲，进度打印。复用 QEMU rdres 的全部下游（md0=root/md1=ramdisk 语义在 loader.c DT writer 处实证一致）。kernel 72bbea4。
   - mkpayload `--rdfile`；`tools/stage-system.sh`（Android 侧 dd 到 userdata 尾，不动 f2fs 头部；每轮试前重跑防 f2fs 写花）。
   - `xnu-annibale-c.img` 8,237,056 B 编译就绪（boot_a 100,663,296 B 富余）。
   - 备选：super 尾部空闲 extent 更稳（f2fs 碰不到），偏移等 `ufs=1` 日志 + tools/ufs-super.py 解析后固化。
2. **图形直通定案（本轮最大发现）**：内核显示只认 BootArgs.video（QEMU ramfb 实证；chosen 无 framebuffer 属性）。GOP==NULL 时 loader 现把 LK splash 区 0xFC800000 当 fb 交给内核（kernel a6bdbab）→ **真机图形锁屏不需要 MDSS 驱动**。启动方式必须 `--set-active=a + reboot`（LK 点屏），`fastboot boot` 黑屏。splash_region@0xfc800000 与 DT/Display_Reserved 三方同址已在 hw-map 复核。
3. **sub agent 交付验收**（各 1 个，符合 ≤3 约束）：
   - rootfs-strategy.md 终版（含对我早期草稿 4 处勘误：gzip 只 -3.5%、boot_a 实测 96MiB、rd=md0 只是设备名、B1 FLASHBOOT 二线定位）。数字已抽查复核。
   - annibale-hw-map.md 5553 节点重写版；**两处勘误被我在权威 DT 上证实**：触摸 SPI=spi@a88000(SE2)（a8c000 是 I2C SE3×fsa4480）；DT 确有 splash_region 0xfc800000+0x2b00000（我此前"无显示 carveout"结论错误）。
4. **外设驱动盘点**进 porting-plan M3：fork 真机驱动 = bsd/dev/redwood_*.c 裸寄存器全家桶（goodix 触摸/haptic/wifi/ufshc/adreno 3800 行含面板），annibale 适配 = 逐驱动换 gcc/pinctrl/PMIC 常数；触摸天级、震动天级、Wi-Fi 月级、相机未映射最后做。

## 下午追加（同一离线轮的后半段）

5. **内核自建流水线跑通**（详见 docs/analysis/kernel-build-linux.md）：Docker `kbuild` 容器（--platform linux/amd64）theos+clang-11 工具链全量构建 ~35min，增量构建只重编改动文件。首产物已替换 `prebuilt/mach.development.bcm2837` （kernel 8a86129；旧版 9239d4ad… 仍在 git 历史可 A/B）。
6. **触摸 annibale 参数化完成**（kernel cc9ff58，文档见 porting-plan 盘点）：`redwood_goodix.c` 常数改运行时表，boot-arg `touchscreen=2` 选 annibale 板参数（TLMM/SE 时钟/ldob12 供电/SMEM 扫 cmd_db），redwood 常数零改动。期间打掉两个 host 构建坑（strlcpy shim 63f0f01、varinit 探测缓存 b7ac03a）。
7. **QEMU 回归通过（自建内核开机进 SpringBoard）**。插曲记入 playbook 陷阱 9：DIRECT_PHONE_PLAT 版 loader 喂给 QEMU 会让内核 5.8s 卡死（GIC 对不上），排查 A/B 掉新旧内核后才定位——**两种 loader 谁用谁现编**。
8. **c.img 重打包**：8,022,016 B，payload bytesum=5630d796，内嵌自建内核 + DIRECT_PHONE_PLAT loader + rdfile 参数。装配线必须在 hackios-dev 容器里跑（宿主缺 llvm-objcopy，BootShim 重编需要）。
9. **震动驱动完成**（kernel 2006f81 + prebuilt 1dfe4b2）：新文件 `redwood_haptic_hv.c`，自带 SPMI **v7** master（arbiter 布局与 redwood 的 v5 完全不同：obsrvr/chnls/core+0x2000 通道表），`hv_haptic=1..4` 四级，参数照抄设备树（hv-haptics TI 内置马达，5714us/1300mV/brake ff 3f 1f）。容器增量编译 ≈2min（全量 35min），产物 +17KB；QEMU 回归再次进 SpringBoard（不带旗标=驱动惰性，证明挂载/初始化安全）。c.img 重打包 8,028,160 B / bytesum=564237e9。真机验收=cmdline 加 `hv_haptic=3` 数秒后**手感 30ms 震动**，无需屏幕。
10. **Wi-Fi 移植调研完成**：`docs/plan/wcn7850-plan.md`。勘误redwood链路（PIL+GLINK/ QMI，无 MHI）；annibale WCN7850 走 PCIe RC0@0x1c00000 + MHI，fork 内核两块全新增，估算 4–8 周真机窗口起步。硬前提：先 dump vendor 分区拿固件。
11. **GPU 移植调研完成**：`docs/plan/gpu-plan.md`。上游 Linux v7.3 已收 a8xx （288a9320，复用 a6xx GMU/HFI 框架）；SM8750 基址从设备树拆齐（3D 0x3d00000、GMU 0x3d37000、GPUCC 0x3d90000、SMMU 0x3da0000…），chipid 0x44050000 需自扩 catalog。redwood全链路（上电阶梯→Mesa redwood-drm 桩→Mini IOSurface/FB→Metal 半成品）盘点完毕，L1/L2/L3 三级均不动 iOS 用户态。外部未知经两轮实查收敛（web 恢复后 GitLab API；子 agent 复核修正了我一轮的过度结论——大写串 grep 假阴性）：**turnip 的 A8XX 生产可用级；gallium GL 并非零——fd6 已 CHIP 模板化、有 `CHIP >= A8XX` 运行时分支与专修提交，只缺 CI 背书**。L2 选型：先 fork rebase 26/27 直译实测（离线可做、与 L1a 并行），不通再退 turnip+GL 桥。0x44050000 上游 catalog 认得（fuse 勘误补丁进 25.3）；gen80200 固件三件套（gmu/sqe/aqe）linux-firmware 直接可拿，L1a 不用等真机 dump。附："Introduce A8x"（288a9320）核验在 v6.19 内、v6.18 不含；"gen8 弃 ir3"系误传，shader 后端仍是 ir3，差异由 CHIP 模板+devinfo 吸收。
12. **相机移植调研完成**：`docs/plan/camera-plan.md`。redwood链路是完整方案（内核 cam=1..5 + mediaserverd 注入 + 软 ISP，非半成品）；annibale CAMSS 基址/供电/ I2C 从 /tmp/hw_check.dts 拆齐补录（hw-map 待同步）；L1a TPG→CSID-lite→IFE-lite 通路 ~3 周、盲写 70–80%。硬前提=真机拉 /vendor/lib64/camera 的 sensormodule bin（当前 annibale-backup 无 vendor dump）。
13. **gen80200 GPU 固件三件套入库**（userland 仓 `firmware-gen8/`，SHA256 钉死）——GPU L1a 开工零真机依赖。至此"开机→图形→触摸→震动→联网→GPU→相机"七项的离线可准备资源全部落档：前三项代码就绪，后四项规划+基址表+固件就绪。
14. **功能全景扫描 + 上游同步**：新增 `docs/analysis/2026-10-23-feature-scan.md`（红杉全家底×K90 对照表）。扩容决定：按键（音量上=TLMM GPIO6 实证）/电池（内核直读 FG）/手电三项进本期批次；音频不做。上游 oosexgang 两仓 main 零新提交；replydev 三个未合并 PR（构建失败传播/QEMU --foreground/老 prebuilt 修复）经用户裁决**不提前摘取**，已摘又回退。勘误：WCN7850 Wi-Fi 固件其实在 linux-firmware `ath12k/WCN7850/hw2.0/`（首查只翻了 qcom/ 目录），Wi-Fi 硬前提消解，全链路可离线盲写。
15. **Agent team 开工 + Mesa rebase 完成（task-5）**：协作切换为 team 模式（drivers=三个小驱动、adreno=GPU L1a、mesa=rebase 试验，Lead 只做编译/回归/提交闸门）。mesa 队友结论（详见 `docs/analysis/mesa-rebase-2026-10.md`）：fork 补丁栈在 **26.2.5** 上 4 存活/1 可退役（ir3-shift-split，上游成因已消失）/3 需改写并固化进 `tools/mesa/rebase-26/0003` 适配层；darwin 原生 ninja 全绿出 libOSMesa.8.dylib（1300 个 gl* 导出），软管线冒烟通过。最大成本：**上游 25.1 删了 OSMesa**（027ccd963b），iOS 无 EGL 栈，短期靠反向恢复。a8xx 真实 devinfo 26.1.0 起（26.0.x 假 FD830 否决），2ee0a5e6/779cdb8e 两修复 cherry-pick 到 26.2.5 零冲突。`mk-mesa.sh` 已加 `REBASE=26` 基线开关（默认仍 25.0.7）。
16. **三个小驱动入库（task-1/2/3，kernel 059a59e + prebuilt 3c4c534）**：redwood_buttons_hv.c（音量上=PMI GPIO slave1 低有效带上拉——DT 证据推翻任务书早先的 TLMM GPIO6 说法；电源/音量下=PMK8550 PON 纯读）、redwood_battery_hv.c（SDAM 电量 VALID 才发布 + 全总线 TYPE/SUBTYPE 普查红利）、redwood_torch_hv.c（flash 模块 TYPE/SUBTYPE+fault 双检才写、每写必回读，low_on/off 原语留给相机 L1b）。**顺带修掉一个真机必翻车的 bug**：redwood_haptic_hv.c ppid 硬编码 0x0f0，DT 全路径裁决 TI 块在 slave 7 → 0x7f0（旧镜像手感自检必然无感，drivers 队友指认）。共享总线锁 redwood_spmi_hv_lock 三驱动共用。QEMU 回归绿（三驱动无旗标全惰性），c.img 重打包 8,036,352 B / bytesum=566a1d37，playbook 一把过批次更新为 `touchscreen=2 hv_haptic=3 buttons=1 battery=1 torch_secs=3`。
17. **AIR 前端迁移 26.x 完成（task-6，userland ced0ed5）**：7 文件 +132/−122 全在 tools/mesa/air/，ninja 全树绿、softpipe 冒烟三连过（fragpos 回读正确/texopcheck 27/27/argbufruncheck 20/20）；清单外新漂移 pipe_surface 值结构化是最大一块（报告 §8）。GPU L2 的地基自此在 26.2.5 上成立。**上游关系改章**（用户拍板）：不再跟进 hackios 上游，贡献攒通用修复反向送 PR、不收则自家开源；内核层机制改造（task-8 patch series 工具等）按我方工程判断放开做。
18. **PCIe 勘察驱动入库（task-7，kernel f2175a8 + prebuilt 4f5ab24）**：redwood_pcie.c 606 行，`pcie=1..3` 三步只读阶梯（GDSC/TLMM 六脚/LTSSM/链路位 → link up 才做 iATU 借窗 BAR sizing 全存全恢 → MHI 状态机读数），boot-arg 特意用 pcie= 避开老 redwood_wifi.c 的 wifi=（碰撞经裁决：老驱动不动）。QEMU 回归绿，c.img 重打包 8,042,496 B / bytesum=5678cb64，playbook 一把过批次加 pcie=3。**命名三层制获批**（task-10 排队）：板级四件套→annibale_*、IP 级→无前缀（adreno8.c/mhi_pcie.c）、ABI 面（/dev/redwood-*、kern.redwood.*）冻结待真机后改名波。

## 等设备回到视野后（按序）

0. **暂停门**：评审指出 stage-system.sh 往 userdata 尾部写 2.4G 前不校验块占用、且备份不含 userdata；用户指示当前一切调试限 RAM 启动、不做持久化。→ 变体 C 的暂存步骤**先问用户**；空窗期可先走 A（USB 诊断，纯 RAM）与 super 尾部空闲 extent 的只读勘察（loader `ufs=1` 日志 + tools/ufs-super.py）。

1. `tools/stage-system.sh` → flash `xnu-annibale-c.img` boot_a → `--set-active=a` → `reboot` → **看屏**（图形=里程碑；乱码=改 1440x3200 几何；黑+循环=取证回 b）。
2. 同场加 LK-splash 截图需求：屏摄几张（LK splash / iOS 画面）归档 evidence/。
3. loader USB 通道（QCOM_USB_DEVICE OUT 通知）继续排查——现在只是锦上添花（屏就是日志通道了）。

## 设备状态备忘

slot _a active（boot_a=auto.img 8,034,304 B 旧版），静默循环；`--set-active=b` 随时可回用户 Android（boot_b/userdata 头未动）。c.img 与本轮所有镜像在 hackios-xnu-kernel/ 根目录（gitignore）。
19. **mesa iOS 交叉构建可复现（task-9，userland b9baeac + 父仓 983f7ba）**：在重建后的 hackios-dev:latest 容器内 `VERSION=26.2.5 SHA256=794b… REBASE=26 AIR=1 tools/mk-mesa.sh` 端到端 rc=0，产出 libOSMesa.8.dylib（18 659 056 B，1300 个 gl* 导出）、libredwoodair.dylib（13 063 080 B，31 个 rwa_*）、air_run，导出符号面与 host darwin 构建逐名一致。mk-mesa.sh 六处 26.x 修正（vdpau/xa 版本开关、REBASE=26 容忍旧补丁环失败、ld64/xnu-clang++ 自建符号链接、install_name_tool 走 $THEOS、nm→llvm-nm、gl.xml 路径回退）。Dockerfile 固化：iOS 工具链钉版本（theos 304e0799 + ld64/install_name_tool/SDKSettings.plist 三个 sha256 构建期校验，漂移即失败）、amd64 multiarch 层（ports 无 amd64 索引与 zlib1g Multi-Arch:same 互锁的绕法进注释）、apt 依赖补齐（meson 故意不进 apt，走 mk-mesa venv 钉 1.12.1）。溯源结论（报告 §9）：老 prebuilt dylib 历史上从未入库、系 ad hoc 手搓不可复现，从今天起 out/ 产物就是 userland/build.sh 的可复现对接面。kernel 树 common/ugit 视图对齐 b9baeac（修复 .gitignore skip-worktree 丢失导致的 pull 卡死；README/.gitignore/LICENSE 按 setup.sh 设计保留 kernel 版）。
