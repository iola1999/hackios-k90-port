# WCN7850（annibale / REDMI K90）Wi-Fi 移植路径规划

本页记录 redwood WCN6750 与 annibale WCN7850 的驱动差异及移植步骤。2026-10-27 已完成 RC0 上电、PCIe Gen1 x2 链路、WCN7850 BAR0 和 stage 5 状态读取：BHI 处于 PBL，BHI 错误字段为 0；PARF bypass=1，RID `0x100` 的读取链出现环且未找到该 RID，SID 转换和 apps SMMU 映射尚未验收，详见 [PCIe 实测记录](../progress/2026-10-26-wifi-pcie-survey.md#5-bhi-执行环境与-sid-读取2026-10-27)。后续先落实 SID／SMMU 与 DMA 资源保留，再实施固件下载；下文早期工期估计尚未按当前进度重估。

---

## 1. redwood（POCO X5 Pro / SM7375 / WCN6750）现状盘点

### 1.1 链路形态

WCN6750 **不是 PCIe 设备**：射频 + WPSS（SoC 内 Hexagon DSP，`qcom,wpss@8a00000`，PAS=6）。应用侧只做「PIL 起 DSP → 跟固件对话」，全程无 PCIe/MHI：

```
PIL/TrustZone 加载 wpss 固件 → SMP2P/IPCC 门铃 → GLINK(IPCRTR) 通道
  → QRTR 枚举 WLFW 服务 → QMI 握手(发 regdb+BD, init done, mission)
  → 固件回报 radio 寄存器 0x61e00000/2MB → 建 SMMU context 喂 ring
  → WMI/CE 跑数据面 → en0
```

中断默认**不用**（每毫秒轮询 ring），`wifi_irq=1` 走「radio 的 MSI 经其 SMMU context 到 GIC」（lx_bus 侧）。

### 1.2 文件职责（bsd/dev/，均为裸寄存器 + boot-arg 风格，无 IOKit 框架）

| 文件 | 行数 | 职责 |
|---|---|---|
| `redwood_wifi.c` | 4393 | 总编排。`wifi_step=1..16` 分步引导（1–5 纯只读勘察 SMEM/AOP/RPMh/引脚/固件；6–11 PIL 加载+起 DSP；12–13 GLINK；14 QRTR；15 WLFW/ath11k；16 读 radio 寄存器）。`wifi=1` = 生产路径（ath11k + en0 + 自动连 `fw/network`）。还管 SMMU（`wifi_smmu=2` 给 radio 建页表窗 `0xa0000000+256MB`）与停机时序（先 SMP2P 请求停再 TrustZone 关，否则下次起不来） |
| `redwood_qmi.c` | 957 | 通用 QMI：表驱动 TLV 编解码、IPCRTR 上的请求/ indication 事务。接口仿 Linux qmi 以便 ath11k qmi.c 直接编译。同一文件也编到 host（tools/qmi-test） |
| `redwood_wlfw.c` | 545 | **一次性替身**：手拼 WLFW QMI 报文摸真机行为。报文/表在构建时由 `tools/mk-wlfw.sh` 从 ath11k 源码抽出，不入库。实测（WLAN.MSL.1.0.1-01277）：regdb 4 片、bd_m20gl.elf 10 片、init done 283ms、冷校准 6.7s 后 ready，radio 寄存器 0x61e00000 |
| `redwood_lx.c` + `tools/mk-ath11k.sh` | — | **真 ath11k 进 XNU**：下载 Linux 7.0.14 ath11k（免改）+ FreeBSD 15.1 LinuxKPI（打 `wifi/lx/patches/*.patch`，源文件不用，功能由我方 `wifi/lx/src` 在 `redwood_lx.h` 的少数原语上重写：锁/睡眠/work/firmware/radio 总线），编成单个 ath11k.o 由 xnu-build.sh 链接。未编文件自动成 stubs（out/stubs.txt）。ath11k 对 WCN6750 用 **ahb 总线**（非 pci） |
| `redwood_net.c` | 377 | en0：用 KPI 造以太网接口（仿 if_fake/feth），**芯片无关**；不认识的接口 ioctl 转给 apple80211 层 |
| `redwood_apple80211.c` | 739 | 内核里答 SIOCG/SIOCSA80211（wifid/Settings 的 Apple80211 请求，无 user client 走 ioctl 回退）；用 class 6/subclass 1 kern_event 按 IO80211.framework 语义上报。布局部分从 iOS 16.5 的 IO80211.framework 反读 |
| `files/iokit/Kernel/RedwoodWLAN.cpp` | — | 假注册表对象（IO80211Controller + IONetworkInterface，仅属性），让 SC/configd 给 en0 建网络服务、wifid 认接口 |
| `redwood_sta.h` 边界 | — | station 语义（power/信道/scan/join/事件），apple80211 只认这个边界 |

### 1.3 关键 boot-arg

- 生产：`wifi=1`（含 `wifi_irq`/`wifi_ba`(block-ack，不通约丢 4/5 吞吐)/`wifi_wide`(40/80MHz)）；`wifi_station=1`/`wifi_join=1`/`wifi_scan=1`、`wifi_mac=`、`wifi_file=0`、`wifi_loud=1`
- 勘察：`wifi_step=N` + `wifi_new/pause/fine/wait/watch/listen/ask/cal/mission/radio_read/keep/dirty/again/return`
- 驱动替换：`wifi_lx=1`（ath11k 替身 QMI）/ `wifi_lx=2`（真跑，需 `wifi_smmu=2`）
- SMMU：`wifi_smmu=1` 只读勘察 / `=2` 建 context（会写 SMMU）

### 1.4 MMIO 基址类别（redwood常数，全出自其 DT/Linux）

SMEM `0x80900000+2MB`（WPSS 条目 13）与其锁 `0x1f43000`、IPCC `0x408000`、AOP rsc `0x18200000`、AP RPMh sequencer `0x18220000`、cmd-db `0x80860000`、WPSS PIL 内存 `0x9ae00000+25MB`、radio 寄存器 `0x61e00000+2MB`（固件回报）、SMMU 展示窗 `0xa0000000+256MB`、SoC 外设基址 `0x400000`。

### 1.5 固件来源

手机 `/vendor/firmware_mnt/image/{wpss.mdt,wpss.b02..b07}` → 放 userland `fw-wifi/` → `userland/build.sh` 打进小镜像 `fw/` → 内核 `redwood_image_file("fw", …)` 从 RAM disk 内存直读（redwood_image.c）。regdb + `bd_m20gl.elf` 不落 MMIO，而是**经 QMI WLFW 分片上载给固件**。`fw/network` 存自动连接 SSID。

---

## 2. annibale 差异清单（DT 实证，/tmp/hw_check.dts + hw-map §6）

### 2.1 芯片与连接

- **WCN785x（代号 kiwi，FastConnect 7800，Wi-Fi 7）**，PCI device id `0x1107`（DT `supported-ids`），厂商 0x17cb。
- 挂 **PCIe RC0 = `/soc/pcie@1c00000`**（`qcom,wlan-rc-num=0`；**不是 pcie2**——DT 里可见的 host 就是 RC0）。qcom,pci-msm 布局：parf `0x1c00000+0x3000`、phy `0x1c06000`、elbi `0x40000000`、conf_apb `0x40100000`、pcie_sm `0x1d07000+0x1000`、atu `0x40080000`、config 窗 io `0x40200000+1MB`/mem `0x40300000+0x3d00000`（bootargs `pcie_sm_regs=0x1D07000,…` 一致）。
- 端点：`/soc/pcie@1c00000/pcie0_rp/cnss_pci0`；管控节点 `qcom,cnss-kiwi@b0000000`（reg 为 `smmu_iova_ipa` 固定 IOVA 窗）。
- 引脚：PERST=GPIO102、CLKREQ=103、WAKE=104（`pcie0_*` 组）；wlan-en=GPIO16、sw-ctrl=GPIO18、wlan-sw-ctrl=GPIO19；唤醒经 pcie_pdc `0xb360000`；主中断 INTID 172（edge）+ 181–184。

### 2.2 供电 / 时钟 / 电源域

- 电源轨（RPMh，`rsc@16500000/drv@2`，注意基址与redwood 0x18200000 不同）：`vdd-wlan-io/io12/dig/aon/rfa1/rfa2/ant-share` → hw-map 已映射为 smpd1/ldof2/ldof3/smpg3/smpi7/ldok6 等 LDO/SMP。
- 域与时钟：`gcc_pcie_0_gdsc`（GCC `0x16b004`）、`gcc_pcie_0_phy_gdsc`（`0x16c000`）、pcie_crm `crm@1d01000`（v2）、bi_tcxo + pcie_0_pipe_clk + sleep_clk。
- CX/MX：`rpmh-regulator-mxlvl`（`vdd-mxa-level`）在 drv@2；上电时序 = gcc gdsc + CRM + RPMh 轨 + wlan-en/sw-ctrl GPIO，顺序在 Linux pci-msm/cnss 源码里可抄。

### 2.3 BT

`/soc/bt_kiwi`（`qcom,kiwi`）：reset/enable = **pm8550ve_f PMIC GPIO3**（SPMI `@5/pinctrl@8800`），bt-sw-ctrl=GPIO18 与 WLAN 共享。DT 未写死 HCI 载体：候选 **PCIe MHI**（树上有 `qcom,qrtr-mhi`）或 **SE14 高速 UART `0x898000`**（hsuart0，GPIO26/27+24/25）——真机日志定夺。音频卡带 `qcom,wcn-bt`（BT 音频也过 WCN）。

### 2.4 IOMMU

原厂设备树与主线 `sm8750.dtsi` 将根端口 RID `0` 映射到 SID `0x1400`，端点 RID `0x100` 映射到 SID `0x1401`。当前端点为 bus 1／device 0／function 0，DMA 域应按端点 SID 核对。

- RID→SID 转换：需检查 PCIe PARF 的 RID→SID 转换配置。2026-10-27 实测 PARF bypass=1，哈希索引 `0x15` 的链经过 22 个表项后回到 `0x6e`，RID `0x100` 未出现；本轮没有验证实际输出 SID，当前驱动尚未配置这一转换。
- IOVA 窗：PCIe 视口 IOVA 窗为 `0x98000000+0x80000000`（geometry），cnss_pci0 fastmap 为 `0x98000000+0x18010000`；页表与 DMA 缓冲分配仍需核对 cnss_wlan_mem 等保留区。
- 本地厂商设备树定义 PCIe QTB `0x016cd000+0x1000` 覆盖 SID `0x1400..0x17ff`，IOVA 宽度为 32 位，并带有 `qcom,opt-out-tbu-halting`。
- IOVA 选择需满足该宽度并避开已有映射，SMMU 页表还需支持分配到的高位物理 RAM；现有 redwood 的 SID `0x1c00`／mask 1 和 context 选择不能直接套用。
- 具体来源、待读取字段与写入前提见[下一步](../progress/2026-10-26-wifi-pcie-survey.md#6-sidapps-smmu-与固件下载前置)。

### 2.5 与redwood的结构性差异总结

| 维度 | redwood WCN6750 | annibale WCN7850 |
|---|---|---|
| 总线 | 片内 ahb（PIL 起 WPSS DSP） | **PCIe RC0 端点** |
| 固件加载 | TrustZone PIL（mdt/b0x） | **MHI SBL/EDL 下载**。固件勘误（2026-10-23 二查，见 docs/analysis/2026-10-23-feature-scan.md §3）：**linux-firmware 有 WCN7850 包**——`ath12k/WCN7850/hw2.0/{amss.bin,m3.bin,board-2.bin}`（在 ath12k/ 下不在 qcom/ 下，首查目录找错了）；本地 ath12k/MHI 源码使用同一 `amss.bin` 的前 `min(512 KiB, 文件长度)` 做 BHI 初始下载，再通过 BHIe 下载完整映像；K90 的硬件版本及板级 BDF 待核对 |
| 控制面传输 | SMEM/SMP2P/IPCC/GLINK→QRTR | **MHI 通道**（QRTR-over-MHI、QMI 直接跑 MHI buf ring） |
| QMI/WLFW | 已打通 | 报文族相近（ath11k qmi → ath12k qmi 表不同），`redwood_qmi.c` 编解码器**可复用**，只换传输 |
| 驱动 | ath11k(ahb) via LinuxKPI | **ath12k** `drivers/net/wireless/ath/ath12k/wifi7/`（mainline 已有 `hal_wcn7850.c`，MHI 总线） |
| 中断 | 轮询为主 | MHI 控制中断 + MSI |
| iOS 挂接 | redwood_net/apple80211/RedwoodWLAN | **全部芯片无关，直接复用** |

---

## 3. 修正 porting-plan.md「外设驱动盘点」

原文：`Wi-Fi redwood_wifi.c/wlfw（QWC NVM 加载 MHI）→ WCN7850 kiwi PCIe RC0，月级`。

- **“MHI”误**：redwood链路 = PIL + GLINK/QRTR/QMI，全程无 MHI；MHI 是 annibale 侧才出现的新东西。
- **“QWC NVM”无对应物**：实为 QMI WLFW 上载 regdb + BD 板文件。
- **“kiwi PCIe RC0”对**（wlan-rc-num=0，基址 0x1c00000）。
- **“月级”维持，且此前偏乐观**：redwood路线里没有 PCIe host 和 MHI，而 fork 内核今天一行 PCIe 都没有；修正为 **4–8 周真机窗口起步、保守 1.5–3 个月到可用联网**。建议把该行改写为：
> Wi-Fi：redwood = WPSS-PIL+GLINK/QMI+ath11k(ahb)（无 MHI）；annibale WCN7850 = PCIe RC0+MHI+ath12k，需新增 PCIe host 与 MHI host 两块，月级（详见 wcn7850-plan.md）。

---

## 4. 最小可行路线排序

原则：沿用redwood「分步 boot-arg + 先读后写」打法；每步独立可验证；先证明总线，再证明固件，最后才是 802.11。

| 步 | 内容 | 新增/改动 | 难度 | 盲写比例 |
|---|---|---|---|---|
| 0 | **（2026-10-26 完成，内核 `fadb3a2`，见 [PCIe 勘察与上电记录](../progress/2026-10-26-wifi-pcie-survey.md)）PCIe link-up + 读 config space**（认出 0x17cb:0x1107）。gcc 双 gdsc + CRM + phy/elbi 上电、perst/clkreq GPIO、RC0 init、conf_apb 配置读。boot-arg `wifi_step=` 风格分步 `pcie=1..N` | 新 `redwood_pcie.c`（或 annibale_ 前缀） | 1–2 周 | 70% 可盲写（寄存器 Linux pci-msm/DT 全有）；**link-up 必须真机**（LK/UEFI 是否已占 RC0 要实测） |
| 1 | **MHI host 最小子集**：stage 5 已确认 PBL；先核对 apps SMMU 可访问范围与目标 SID 匹配、实现 RID→SID 配置读回和有限 DMA 映射，再补 MHI 缓冲的停止／超时／返回保留。完成这些前置后执行 BHI/BAR0 握手、SBL 加载、state change、MHI reset/EDL、开 QMI+QRTR 通道 | 新 `redwood_mhi.c`（对照 Linux drivers/bus/mhi） | 1–2 周 | 大部分可盲写；失败态（SBL 不响应、需要 EDL 强制下载）必须真机 |
| 2 | **固件下载 + WLFW 握手**：SBL→下载 FW（主体固件已可从 linux-firmware `ath12k/WCN7850/hw2.0/` 离线取得；同一 `amss.bin` 分 BHI／BHIe 两阶段下载，板级 BDF 变体待真机核对）；QMI WLFW：`redwood_wlfw` 逻辑平移，`mk-wlfw.sh` 改抽 **ath12k** 的 qmi 表；传输层 = `redwood_qmi.c` 换挂 QRTR-over-MHI（新 `redwood_mhi_qrtr.c`） | 改 wlfw + 新 mhi_qrtr + mk- 脚本改向 | ~1 周 | 握手报文可盲写；FW 文件与行为要真机 |
| 3 | **数据面**：Plan A = 手写「最小 WMI 集」（scan/join/收发，仿 wlfw 替身思路），HAL ring 直对 BAR0（REO/TCL/TxDMA + RX ring）；Plan B = `mk-ath12k.sh` 把 wifi7 ath12k + LinuxKPI 全量搬进来（仿 mk-ath11k.sh，mhi/pci bus）。**先 Plan A 出联网，Plan B 做完整化** | 新 `redwood_wmi.c`/ring 代码，或新 mk- 脚本 + lx 补丁 | 2–6 周 | 结构可盲写；ring/中断/DMA 时序**基本靠真机磨**——「月级」就出在这步 |
| 4 | **en0 挂接**：redwood_net/apple80211/RedwoodWLAN 换 link 指到新 radio | 小改 | 天级 | 全盲写 |
| 5 | （后置）BT：MHI HCI 或 SE14 UART 二选一（真机定）；BT 音频 | — | 周级 | — |

到「2.4G 扫网+连接」总量：真机窗口累计 4–8 周。离线可先行完成：步 0–2 的代码 + 步 3 的结构骨架（约 2–3 周纯写码）。

---

## 5. 风险与放弃准则（「这轮不做 Wi-Fi」的触发条件）

1. **PCIe 起不来**：连续 3 个真机窗口 link-up 失败（PERST/时钟/上电序排查完仍无 LTSSM detect）→ 放弃本轮。嫌疑点：LK/UEFI 是否已初始化 RC0 并被安全态锁住；pcie_sm 序列与 bootargs 常量对不上。
2. ~~固件不可得是硬前提~~ **已消解（2026-10-23）**：ath12k 主固件在 linux-firmware 拿得到；仅当板级 BDF 全部对不上且 vendor 分区加密读不出时才触发放弃。
3. **MHI 下载成功但固件不 boot**（SBL 无 state change / QMI 服务不出）≥2 周 → 降级：本轮只做「能枚举到设备 + 读卡 ID」存档。
4. **SMMU/IOVA 冲突**：端点 SID `0x1401` 的路由或 context 配置失败或与 DisplayDxe/保留区撞窗 → DMA 不可用 → 放弃数据面，保留结论。
5. **数据面 timebox**：步 3 开工 2 周无第一笔 TX 完成 → 砍到「QMI 握手通」为止。
6. 板级校准/BDF 缺失可能只有 2.4G 保守速率——可接受，不算失败。
7. 兜底现状本来就成立：锁屏里程碑无 Wi-Fi 可交付（第一/第二里程碑不依赖它），放弃的代价是演示没有无线联网，不阻塞主线。

## 6. TODO（留给真机/联网轮）

- [x] ~~linux-firmware 无 WCN7850 包~~ 勘误：在 `ath12k/WCN7850/hw2.0/`（GitLab 镜像实查）。真机侧只剩：硬件版本与 board-2.bin 板级变体验证，以及固定固件版本、长度和 SHA-256；原厂固件可从 `/vendor/firmware_mnt/image` 提取
- [x] LK/UEFI 阶段 RC0 状态：内核启动时两个电源域关闭、时钟停止，网卡使能脚与 PERST 未驱动（[PCIe 勘察记录](../progress/2026-10-26-wifi-pcie-survey.md)）；pcie_sm 未读
- [ ] BT HCI 真实载体：MHI vs SE14 UART
- [ ] ath12k WCN7850 的 BAR/ring 布局笔记（读 wifi7/hal_wcn7850.c 出一份寄存器清单）

- [x] stage 5 真机读取：PBL、BHI 错误字段全 0；BHIe 初始 TXVECSTATUS 为 `0x8aa6c915`，本轮没有发起传输，该读数只记录初始状态；PARF bypass=1，目标 RID 链有环，结束后已软件复位
- [ ] 核对 apps SMMU／PCIe QTB 访问前提、目标 SID 的 SMR／S2CR 与 context，占用明确后实现 RID→SID 配置和读回
- [ ] 首个固件下载门铃前实现 MHI DMA 缓冲／映射的停止、失败与复位保留；禁止 loader 在未确认停止前覆盖这些资源
