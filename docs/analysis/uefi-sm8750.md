# SM8750 UEFI 现状调研（M2 风险项）

2026-10-23，web + gh 调研。结论：**UEFI 路径风险从"高"降到"中"**——SM8750（sun）
已有活跃的开源 EDK2 固件项目，且就在小米生态里。

## 关键发现

1. **Project-SunUEFI**（https://github.com/slwyts/Project-SunUEFI）
   小米平板 8 Pro（piano，骁龙 8 至尊版 = SM8750，与 annibale 同 SoC）的开源
   EDK2/UEFI，支持主线 Linux（WoA 规划中）。**活跃：最后推送 2026-10-22**，
   近期 commit 涉及 Goodix 触摸绑定、KDE/电源修复——已有真实日常使用痕迹。
   → 对我们最直接的候选基座：同 SoC、小米系（原厂 xbl/ABL 交互逻辑相似）、含触摸驱动。
2. **edk2-gunyah**（https://github.com/ChopinKernels/edk2-gunyah）："Run UEFI
   firmware in Qualcomm Gunyah"。K90 Pro Max 安卓侧就跑 Gunyah（EL2），该路线
   回答了"UEFI 在 Hypervisor 下怎么起"的问题，可参考其启动方式。
3. **edk2-msm 及 fork 网**（如 https://github.com/yuweiyuan8/edk2-msm，自述
   "Broken edk2 port …xD"）：8 Elite 世代支持仍在早期，但 fork 网活跃可借部件。
4. **Mu-Silicium 官方组织**（https://github.com/Project-Silicium/Mu-Silicium）：
   hackios 上游所用；目前 pkg 止步 ~SM8550，无 SM8750。
5. SM8750 **bootloader 解锁 exploit** 记录：
   https://wasddestroy.site/misc/qualcomm_unlock_exploit.html ——若小米限制解锁，
   `fastboot boot` 暂存路线（已实测可用）仍是不依赖解锁的兜底。
6. postmarketOS wiki 的 OnePlus 13/13s（dodge/pagani，同为 SM8750）条目已有
   UEFI/主线启动章节，可作次级参考。

## 对 hackios UEFI 路线的排序（更新版）

| 方案 | 工作量 | 最大不确定点 |
|---|---|---|
| a) 以 **Project-SunUEFI 为基座**，加 hackios 需要的 GOP 出图 + 我们的 loader 作 BOOTAA64.EFI | 中：piano→annibale 的 DTS/pinctrl 差异；显示面板不同（需点亮 1156x2510 DSI 或先用简单模式） | fastboot boot 起的 UEFI 能否拿到完整硬件（piano 方案可能假设解锁/abl 链路） |
| b) edk2-msm sun 分支从零 + Silicium 驱动移植 | 高 | 部件老化，8 Elite 时钟/显示拓扑差异大 |
| c) 纯 QEMU 演示，真机 UEFI 跟随社区进度 | 低 | 不达成"真机 iOS"只达成"iOS 开机" |

**当前决策：M1 用 QEMU 先达成开机；M2 立即开一个 SunUEFI 试验分支评估 a)。**

## 待办（M2 入口）

- [ ] clone Project-SunUEFI，读 piano 板级 diff，评估到 annibale 的面板/触摸差异
- [ ] 确认其镜像能否 `fastboot boot`（免刷写）直接起
- [ ] 研究 K90 原厂 `uefi_a`（备份里有）的分区加载链，看 SunUEFI 的装载前提
- [ ] Gunyah 环境下 GOP 显存地址获取（loader 的 fb_base 依赖它）
