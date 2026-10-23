# SM8750 UEFI 现状调研（M2 风险项）

2026-10-23，gh + web 调研（子代理全量扫描 + 复核）。结论：**风险从"高"降为"中低"** ——hackios 上游所用的 Mu-Silicium 主线已支持 SM8750，且姊妹机型（myron）的"自制 EFI 入口"已被社区打通。

## 1. 名称与前提校准

- **机型纠偏（2026-10-23）**：本机是 **REDMI K90 = `annibale`**；**myron 是 K90 Pro Max，另一款机器**（此前 KernelSU 机型伪装模块导致误判）。SoC 不受影响：`/sys/devices/soc0` = soc_id 618/"SUN"，dtb `model="Annibale based on SM8750"`（`msm-id 0x26a`=618），GPU `Adreno830v2`，社区树 platform `sun` —— **SM8750 坐实**（并非社区 repo 名所称 SM8850）。
- SM8750 Linux 代号 **sun**，高通参考平台 **Pakala**；SM8850 是 kaanapali（本代不涉及）。
- 真仓库地址：[edk2-porting/edk2-msm](https://github.com/edk2-porting/edk2-msm)、[Project-Silicium/Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium) （旧的 MangoTheCat/Mu-Silicium 已 404）。"kane" 是 Motorola 代号，与本机无关。

## 2. Mu-Silicium：8 Elite 已进 main（对我们最重要）

- [PakalaPkg](https://github.com/Project-Silicium/Mu-Silicium/tree/main/Silicon/Qualcomm/PakalaPkg) = SM8750 支持：OnePlus 13 (dodge) 显示/存储/USB/Linux boot ✅，13s (pagani) Active （[Status.md](https://github.com/Project-Silicium/Mu-Silicium/blob/main/Status.md)）。
- KaanapaliPkg（SM8850，OnePlus 15）也已 Active——8 Elite 世代架构经验已沉淀。
- **但小米 pkg 全是老机型**（polaris=SDM845 … onyx=8s Gen4），org 内无 "redwood"、无任何小米 8 Elite 设备 → annibale/myron 需自己出 pkg。
- 移植方法学现成：[Silicium Porting 指南](https://github.com/Project-Silicium/Guides/tree/main/Silicium/Porting/Snapdragon)；原厂 DXE 提取复用体系：[Project-Silicium/Device-Binaries](https://github.com/Project-Silicium/Device-Binaries) （含 dodge=SM8750 的 xbl DXE + 面板 XML；解包用 [xbltools](https://github.com/linux-msm/xbltools)）。
- ⚠️ 已知维护风险：XBL 协议地址随 HyperOS 固件版本漂移需逐版重扫（[PR #1937](https://github.com/Project-Silicium/Mu-Silicium/pull/1937) 先例）。

## 3. 姊妹机型入口已被打通：gbl-chainload-myron

[NullCode1337/gbl-chainload-myron](https://github.com/NullCode1337/gbl-chainload-myron) （[XDA 帖](https://xdaforums.com/t/mod-efisp-myron-gbl-chainloader-for-redmi-k90-pro-max-poco-f8-ultra-aosp-roms.4799356/)）：在 **K90 Pro Max（myron，姊妹机型，同 SM8750）**把自制 EFI payload 放 EFISP 分区，由 ABL 链入并在内存中 reload+patch 原厂 ABL（gbl_root_canoe 重实现），不动系统分区。→ 证明"同 SoC 同代小米机器能跑自制 UEFI/EFI"；hackios 的 `fastboot boot` 暂存路线（已实测 OK）是另一条免分区入口，两者可互为兜底。SM8850 侧同类：[oneplus15-boot-manager](https://github.com/travismills82/oneplus15-boot-manager)。

## 4. 社区 EDK2 阵营（同 SoC 旁证）

- [Project-SunUEFI](https://github.com/slwyts/Project-SunUEFI)：中文社区为小米平板 8 Pro （piano，SM8750）自研 EDK2，Debian 桌面/GPU/显示/相机可用（WoA 未开始），活跃（2026-10-22 有 commit）。其"UEFI 挂原厂 kernel 后由 ABL 按 header 加载"的合体 BOOT 与 HyperOS 交互经验可直接借鉴。
- [edk2-gunyah](https://github.com/ChopinKernels/edk2-gunyah)："Run UEFI firmware in Qualcomm Gunyah"——对 K90 的 Gunyah/EL2 环境直接相关。
- [edk2-porting/edk2-msm](https://github.com/edk2-porting/edk2-msm/tree/master/Silicon/Qualcomm) 对 SM8750 = **零支持**（止于 sm8550，org 内 sm8750 全 0 命中）→ 从零写，不推荐。
- 主线内核配套（驱动参考）：[sm8750-mainline](https://github.com/index986/sm8750-mainline)、pmOS [OnePlus 13/13s](https://wiki.postmarketos.org/wiki/Qualcomm_Snapdragon_8_Elite_Gen_5_(SM8850)) 页。
- **本机现成移植材料**：[MissMyTime/twrp_device_sm8850](https://github.com/MissMyTime/twrp_device_sm8850) 含 **annibale 设备树**（README 实为 SM8750/SM8850 混合树）：面板物理 1200×2608@480dpi、Wi-Fi kiwi_v2、Goodix goodix_core 触摸、f2fs+wrappedkey_v0 加密细节都有现成对照。

## 5. hackios UEFI 路线排序（定稿）

| 序 | 方案 | 工作量 | 最大不确定点 |
|---|---|---|---|
| ① | **Mu-Silicium 基座出 annibale pkg（参考姊妹 myron 化裁剪）**（Pakala 部件复用 + 本机 DXE 提取） | 1–3 月 | HyperOS XBL/ABL 协议地址漂移逐版重扫；面板 DSI 点亮 |
| ② | 原厂 uefi.elf 内存 patch + EFISP（gbl-chainload-myron 模式） | 数周 | 原厂 UEFI 的 BDS/GOP 完整度不可控 |
| ③ | 跟随/贡献 SunUEFI（EDK2，同 SoC 同 HyperOS 生态） | 不可控 | 目前只有平板；手机版未出 |
| ④ | fork edk2-msm 从零写 sun | 最大 | 无任何现成代码 |

**决策：M1 QEMU 先达成开机；M2 走 ①（与 hackios 上游 SILICIUM_UEFI 同栈），② 作快速验证入口（myron 已证明同系机器 EFI 可链入——甚至可以先在 ② 的环境里试跑 xnuloader 拿 GOP）。**

## 6. M2 待办

- [ ] clone Mu-Silicium，读 PakalaPkg + dodgePkg 结构，对照 docs/PORTING.md 列 annibale pkg 骨架
- [ ] 用 xbltools 拆备份里的原厂 `xbl`/`uefi_a`，提取 DXE/GOP 部件（对照 Device-Binaries 目录格式）
- [ ] 读 gbl-chainload-myron：确认其 EFI 入口能否不改分区、直接喂 hackios 的 loader.efi
- [ ] Gunyah/EL2 下 GOP 显存地址获取（loader 的 fb_base 依赖）
- [ ] 复核 HyperOS 当前版本（BP2A.250605.031.A3）对应的 XBL 协议地址表
