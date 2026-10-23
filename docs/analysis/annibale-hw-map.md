# annibale（REDMI K90 / SM8750 "sun"）真机设备树硬件资源图谱

数据源：**合并设备树**（vendor_boot base DT ⊕ 我方备份 dtbo，fdtoverlay 合并，956,243 B）。`/tmp` 下素材：`/tmp/vb/merged.dtb`（与仓内 `hackios-xnu-kernel/Mu-Silicium/Platforms/Xiaomi/annibalePkg/FdtBlob/sm8750-xiaomi-annibale.dtb` 同一份，87416d2 固化）；base 为 `/tmp/vb/v3.dtb`（qcom,sun），dtbo 片段在 `/tmp/vb/ov*.dtbo`。重建/反编译：

```bash
dtc -I dtb -O dts -o /tmp/annibale-merged.dts /tmp/vb/merged.dtb   # dtc 1.8.1，5553 节点
```

根节点：`model = "Qualcomm Technologies, Inc. Sun SoC"`，`compatible = "qcom,sun"`，`qcom,msm-id = <0x26a 0x10000>`（SM8750 v1），`qcom,board-id = <0 0>`；根 `memory` 节点 `reg = <0 0 0 0>` 是占位，实际内存由 loader 从 EDK2 memory map 注入（bootargs 带 `disable_dma32=on`，DDR 高段在 32 位以上）。

**中断号读法**：本文 `interrupts = <A B C>` 为 DT 原始 cell。A=0 为 SPI，GIC INTID = B+32；A=1 为 PPI，INTID = B+16。`interrupts-extended` 指向 PDC（phandle 0x26）时为 PDC 索引，唤醒时再翻译成 SPI。GPIO 中断的 `interrupt-parent` 为 tlmm（phandle 0x27）。XNU 侧 GIC 配置表要用 INTID，换算务必保留。

---

## 1. 中断控制器 / 系统定时器

| 项 | 节点路径 | compatible | reg/基址 | 中断 | 时钟/电源 | 状态 |
|---|---|---|---|---|---|---|
| GICv3 分发器+RD | `/soc/interrupt-controller@16000000`（label `intc`，全局 interrupt-parent） | `arm,gic-v3` | dist `0x16000000+0x10000`；redist `0x16080000+0x200000`，stride `0x40000` | 维护中断 `<1 9 4>` = PPI9 / INTID 25 | — | okay |
| GIC ITS（MSI） | `/soc/interrupt-controller@16000000/msi-controller@0x16040000`（`gic_its`） | `arm,gic-v3-its` | `0x16040000+0x20000` | — | — | okay |
| PDC（唤醒源） | `/soc/interrupt-controller@b220000`（`pdc`） | `qcom,sun-pdc`,`qcom,pdc` | `0xb220000+0x10000`，另窗 `0x164400f0+0x64` | 级联到 GIC | — | okay |
| PCIe PDC | `/soc/pdc@b360000`（`pcie_pdc`） | `qcom,sun-pdc` 系 | `0xb360000+0x10000` | — | — | okay |
| ARM arch timer | `/soc/timer`（`arch_timer`） | `arm,armv8-timer` | 无 reg（系统寄存器） | `<1 13>`,`<1 14>`,`<1 11>`,`<1 10>` 按绑序 phys/virt/hyp/sec → INTID 29/30/27/26 | `clock-frequency=307.2MHz`（0x124f800） | okay |
| memtimer | `/soc/timer@16800000`（`memtimer`） | `arm,armv7-timer-mem` | `0x16800000+0x1000` | 帧中断子节点 | 307.2MHz | okay |
| Gunyah qtimer | `/soc/qcom,gh-qtimer@1680b000` | gunyah host 侧 | `0x1680b000` | — | — | okay |
| IPCC（跨核邮箱路由） | `/soc/qcom,ipcc@406000`（`ipcc_mproc`） | `qcom,ipcc` | `0x406000+0x1000` | `<0 0xe5 4>` = SPI 229→INTID 261 | — | okay |
| PSCI | `/psci` | `arm,psci-1.0`（method smc） | — | — | — | okay |

> 与 loader `platform_annibale` 的 GIC 表完全一致（dist/redist/ITS 三段），维护中断 PPI9 也已对齐。

## 2. UART 控制台（kernel 早期日志重点）

`chosen/stdout-path = "serial0:115200n8"`；`/aliases/serial0 → /soc/qcom,qupv3_1_geni_se@ac0000/qcom,qup_uart@a9c000`。

| 项 | 值 |
|---|---|
| 节点 | `/soc/qcom,qupv3_1_geni_se@ac0000/qcom,qup_uart@a9c000`（label `qupv3_se7_2uart`，QUP_1 **SE7**） |
| compatible | `qcom,geni-debug-uart` |
| reg | `0x00a9c000 + 0x4000`（reg-names `se_phys`） |
| 中断 | `<0 0x243 4>` = SPI 579 → **INTID 611** |
| 时钟 | `clocks = <&gcc 0x66>`（GCC 里 SE7 的 QUP 时钟） |
| pinctrl 组 | `qupv3_se7_2uart_tx_active`（**GPIO62**，function `qup1_se7_l2`，2mA，bias-disable）/ `qupv3_se7_2uart_rx_active`（**GPIO63**，`qup1_se7_l3`）/ `qupv3_se7_2uart_sleep`（GPIO62+63 拉成 gpio + bias-pull-down） |
| 状态 | okay |

- 波特率 **115200 8n1**；Android bootargs 里没有 `console=`，全靠 stdout-path——我方 cmdline 要显式给 `console=ttyMSM0,115200n8`。
- loader `platform_annibale.uart` 已改为 `0xa9c000`（本轮修复，见 annibale-uefi-build.md）。
- 备用：`/aliases/hsuart0 → /soc/qcom,qupv3_2_geni_se@8c0000/qcom,qup_uart@898000`（SE14，`qcom,msm-geni-serial-hs` 高速 4 线 UART，TX/RX=GPIO26/27，CTS/RTS=GPIO24/25，组 `qupv3_se14_default_*`，okay，BT/GNSS 候选，见 §6）。
- 桌面 wch 串口线（921600）与本设备无关（desk-01 JSON 干扰源），别再碰。

## 3. 触摸：Goodix（SPI 总线，非 I2C）

| 项 | 值 |
|---|---|
| 节点 | `/soc/qcom,qupv3_1_geni_se@ac0000/spi@a88000/goodix@0` |
| compatible | `xiaomi,touch-spi`（小米 Goodix QTS 驱动风格节点；`goodix,config-name="goodix_cfg_group_annibale"`、`goodix,firmware-name="goodix_firmware_annibale"`） |
| 总线 | **SPI**：`spi@a88000`（label `qupv3_se2_spi`，QUP_1 SE2，别名 `spi0`，reg `0xa88000+0x4000`，控制器中断 `<0 0x163 4>`=SPI 355→INTID 387），CS0，`spi-max-frequency = 15MHz`（0xe4e1c0） |
| SPI 引脚 | MOSI GPIO41（`qup1_se2_l1`）/ MISO GPIO40（`l0`）/ CLK GPIO42（`l2`）/ CS GPIO43（`l3`），组名 `mi_ts_spi_{mosi,miso,clk,cs}_active` |
| IRQ GPIO | `goodix,irq-gpio = <&tlmm 162 0x2008>`（**GPIO_162**，下降沿+bias-pull-down；`interrupts=<162 0x2008>`，`goodix,irq-flags=2`，组 `ts_int_active/suspend`） |
| 复位 GPIO | `goodix,reset-gpio = <&tlmm 161 0>`（**GPIO_161**），组 `ts_reset_active/suspend`；pinctrl-names `pmx_ts_active/pmx_ts_suspend` |
| 电源 | `vdd-supply = <&rpmh_regulator_ldob12>`（iovdd，RPMh L12B）；`avdd-supply = <&touch_avdd_vreg>`（固定调节器"avdd"）；上电时序内核侧要自己补 |
| 坐标 | panel-max-x `0x1c390`=115600、panel-max-y `0x3d478`=251000（÷100 → 1156×2510，与 P11 面板一致，见 §4） |
| Trusted-touch(TVM) | `qts,en`；`qts,trusted-touch-io-bases=<0xa88000>`、`qts,trusted-touch-spi-irq=0x28c`、gpio-list (tlmm 27,40–43)+(161,162)——iOS 侧先裸 SPI，TVM 路整体绕开 |
| 其它 | `panel = <&dsi_p11_* … &dsi_nt37801_amoled_video>` 关联面板配置；`mi_tp,*` 游戏/边缘抑制参数群 |
| 状态 | okay |

I2C 系触摸（goodix/parade/novatek/synaptics/atmel 的 i2c 节点）合并树里**没有**——本板触摸只走上面这条 SPI。（旧注记修正：触摸所在 SPI 是 `spi@a88000`（别名 spi0），不是 a8c000；a8c000 是 I2C SE3 挂 fsa4480。）

## 4. 显示：DSI / NT37801 + P11 面板

显示拓扑：MDP `ae00000` + DISPCC `af00000` + 双 DSI（ctrl+phy 各 2），主显示节点 `/soc/qcom,dsi-display-primary`（`sde_dsi`，compatible `qcom,dsi-display`，label "primary"，`qcom,dsi-ctrl = <&mdss_dsi0 &mdss_dsi1>`，`qcom,dsi-phy = <&mdss_dsi_phy0 &mdss_dsi_phy1>`）。

| 项 | 节点路径 | compatible | reg/基址 | GPIO | 电源/时钟 | 状态 |
|---|---|---|---|---|---|---|
| MDP | `/soc/qcom,mdss_mdp@ae00000`（`mdss_mdp`） | `qcom,sde_kms` 系 | `0xae00000+0x100000` | — | dispcc | okay |
| DSI ctrl0 / phy0 | `/soc/qcom,mdss_dsi_ctrl0@ae94000` / `qcom,mdss_dsi_phy0@ae95500` | `qcom,dsi-ctrl-6g` / `qcom,dsi-phy-5nm` | `0xae94000+0x94` / `0xae95500+0x2b4` | — | dispcc + 面板电 | okay |
| DSI ctrl1 / phy1 | `/soc/qcom,mdss_dsi_ctrl1@ae96000` / `qcom,mdss_dsi_phy1@ae97500` | 同上 | `0xae96000+0x94` / `0xae97500+0x2b4` | — | 同上 | okay |
| TE | —（`sde_dsi` 属性 `qcom,platform-te-gpio`） | — | — | **GPIO86**，组 `sde_te_active`（function `mdp_vsync`） | — | — |
| 复位 | —（面板配置属性 `qcom,platform-reset-gpio`） | — | — | **GPIO98** `<&tlmm 98 0>`，组 `sde_dsi_active`；复位序列 `<1 10ms 0 10ms 1 10ms>` | — | — |
| 面板电 | `/soc/dsi_panel_pwr_supply_p11` 等 | — | — | — | `vdd=L11B(ldob11) 1.0–1.1V`、`vci=L13B(ldob13) 2.9V`、`vddio=L2G(ldog2) 1.8V`、`tvdd=L4B(ldob4) 1.8V`、`avdd 4.6–6.0V/600mA`、`vddd=display_panel_vddd`（fixed） | okay |
| 显示 SMMU 域 | `sde_iommu_region 0xc0000000+0x3fc00000` | — | CB `<&apps_smmu 0x800>`（unsec）/`0x801`（sec） | — | — | okay |

**面板配置节点**（都在 `/soc/qcom,mdss_mdp@ae00000/` 下，运行时小米驱动按 `mi,panel-id` 选择；UEFI 侧已固化其中一款）：

| 配置节点 | 类型 | 分辨率 | 帧率 | DSC | 备注 |
|---|---|---|---|---|---|
| `qcom,mdss_dsi_nt37801_wqhd_plus_vid`（`dsi_nt37801_amoled_video`，**`qcom,dsi-default-panel` 指向它**） | video mode, burst，4+4 lane，双 DSI（ctrl0+ctrl1） | 1440×3200（0x5a0×0xc80）；hfp 0x64/hbp 0x14/hpw 0x14，vfp 0x2c/vbp 0x14/vpw 0x02 | 120Hz（timing@0）/60Hz（timing@2） | slice 720×40（0x2d0/0x28），pentile SPR | "nt37801 amoled video mode dsi csot panel with DSC"，Novatek NT37801 DDIC，CSOT 面板，bpp 24，bl_ctrl_dcs（0x51，上限 0x7ff） |
| `qcom,mdss_dsi_p11_42_0d_0a_p10_dsc_cmd`（`dsi_p11_42_0d_0a_p10_dsc_cmd`，**Mu-Silicium 面板 XML 用的是它**） | cmd mode，DSC | **1156×2510**（0x484×0x9ce）；hfp/hbp 0x40/hpw 0x20，vfp/vbp 0x40/vpw 0x20 | 120Hz | slice 578×10（0x242×0x0a） | "xiaomi p11 42 0d 0a cmd mode dsc dsi panel"；bitclk `0x47d2d740`；on-command 5802 字节；`mi,panel-id=<0x503131 0x50420d0a>`（"P11\r…\n"），esd-err GPIO87，亮度上限 0x3fff |
| 同族变体 | cmd/video、cphy、ddicspr 等 | — | — | — | `..._p11_42_0d_0a_dsc_cmd`、`..._p11_42_02_0b_dsc_cmd`、`nt37801_fhd_plus_cmd`、`qsync_wqhd_plus_vid_cphy` 等 10 余个 |

`tools/dts2panelxml.py` 已用字段：`qcom,mdss-dsi-panel-width/height`、`h-/v-front-porch`、`h-/v-back-porch`、`h-/v-pulse-width`、`panel-framerate`、`panel-clockrate`、`panic-lanes`、`mdss-dsc-slice-width/height`、`dsc-version`（默认 0x11）、`on-command`（6 字节头命令流 → UEFI XML `<type> data [delay]`）。这些属性分布在节点的 `qcom,mdss-dsi-display-timings/timing@N` 子块内（工具按 label 抓整块所以能命中）。用法：`python3 tools/dts2panelxml.py <merged.dts> dsi_p11_42_0d_0a_p10_dsc_cmd <out.xml> <PanelName>`。DisplayDxe 按 `<PanelName>`/DDIC ID 匹配，K90 DDIC 自报 ID 仍未取得（待日志）。

**GOP framebuffer**：`/reserved-memory/splash_region`（label `splash_memory`，别名 `cont_splash_region`）`reg = <0 0xfc800000 0 0x2b00000>`（43MB，非 reusable）——与我方 FD `MemoryMapLib` 的 `Display_Reserved`（0xFC800000+0x2B00000）**同址同大小**，loader `platform_annibale.fb_base` 已接（kernel 仓 872da86）。另一显示区 `non_secure_display_region` 是 `shared-dma-pool`+reusable、size 0xfc00000（252MB）、无固定地址（限 4G 内、对齐 4M），Linux CMA 性质，与 EDK2 carveout 是两回事。**待验证（独立评估 F07）**：同址同大小仅支持"该内存区可定位"；LK 本次启动实际选择的模式/stride/像素格式、接管后面板是否继续扫描、软件写入能否上屏，均无记录——且上表同时存在 1440×3200 默认面板节点与 1156×2510 XML 面板节点，loader 在 GOP 缺失时写死的 `0xFC800000`/1440×3200/stride 5760 是否与实际扫描一致，需真机静态色块+阶段标记验证后才能升格为"显示可用"。

## 5. 震动：qpnp 压电/LRA 马达

| 项 | 值 |
|---|---|
| 节点 | `/soc/qcom,spmi@c42d000/qcom,pmih010x@7/qcom,hv-haptics@f000`（label `pmih010x_haptics`） |
| compatible | `qcom,hv-haptics`（PMIH010X 高压 haptics，SPMI 从设备号 7，寄存器基 `0xf000/0xf100/0xf200`） |
| 中断 | SPMI 设备中断 `<0x07 0xf0 0x01 0x01>`（"fifo-empty"）——经 PMIC arb `c42d000` 级联 |
| 关键参数 | LRA 周期 5734–5714–5684µs（默认 5714）；`qcom,vmax-mv=1300`；`qcom,imax-ma=1250`；LRA 自动阻抗检测频段 0xa0–0xb9（默认 0xaa）；go-ip 制动 dq 波形 + primitive_0..7/wf-vmax 3600mV 波形表齐 |
| 状态 | okay |

第二路：`/soc/spf_core_platform/lpass-cdc/wsa2-macro@6AA0000/wsa2_swr_master/swr_haptics@f0170220`，compatible `qcom,pmih010x-swr-haptics`（经 soundwire 的数字音频驱动马达通路，reg `<0x03 0xf0170220>`，`swr-slave-supply` okay）。`sun_snd` 声卡把 `swr-haptics` 注册为 codec。

## 6. Wi-Fi / BT：Qualcomm Kiwi（WCN785x 家族，Wi-Fi 7）

| 项 | 节点路径 | compatible | reg/基址 | 中断 | 电源/GPIO | 状态 |
|---|---|---|---|---|---|---|
| WLAN 主控 | `/soc/qcom,cnss-kiwi@b0000000`（`wlan_kiwi`） | `qcom,cnss-kiwi` | `0xb0000000+0x10000`（reg-names `smmu_iova_ipa`，PCI 窗口固定 IOVA） | 见 PCIe 行 | `wlan-en-gpio=<&tlmm 16>`、`qcom,sw-ctrl-gpio=<&tlmm 18>`、`qcom,wlan-sw-ctrl-gpio=<&tlmm 19>`；`vdd-wlan*= smpd1/ldof2/ldof3/smpg3/smpi7/ldok6`（RPMh）；`qcom,qmp=<&aoss_qmp>` | okay |
| PCI 端点 | `/soc/pcie@1c00000/pcie0_rp/cnss_pci0` | （`qcom,pci-msm` 树内节点） | `reg = <0 0 0 0 0>`（bus 0 dev 0 func 0） | MSI | `memory-region=<cnss_wlan_mem, cnss_pci0_iommu_region_partition>`；iommu-group 几何 `0x98000000+0x18010000` fastmap | okay |
| PCIe RC0 | `/soc/pcie@1c00000`（`pcie0`） | `qcom,pci-msm`（QCOM legacy 驱动，非 generic ecam host） | parf `0x1c00000+0x3000`，phy `0x1c06000`，elbi `0x40000000`，conf_apb `0x40100000`，pcie_sm `0x1d07000+0x1000`，atu `0x40080000`，config 窗 io `0x40200000+0x100000`/mem `0x40300000+0x3d00000`（bootargs `pcie_sm_regs=0x1D07000,…` 与之一致） | 主中断 `<0 0x8c 4>`=INTID 172，edge `<0 0x95…0x98>`=INTID 181–184；唤醒走 `pcie_pdc` | perst=GPIO102、clkreq=GPIO103、wake=GPIO104（组 `pcie0_perst_default` 等）；gdsc 电源走 gcc | okay（bootargs 带 `pcie_ports=compat`） |
| BT | `/soc/bt_kiwi`（label `bluetooth`） | `qcom,kiwi` | 无 reg | — | `qcom,bt-reset-gpio`/enable = **pm8550ve_f PMIC GPIO3**（phandle 0x6c5 = `/qcom,pm8550ve@5/pinctrl@8800`）；`qcom,bt-sw-ctrl-gpio=<&tlmm 18>`；`qcom,wl-reset-gpio=<&tlmm 16>` 共享；`qcom,bt-fmd-clk-gpio=pm8550ve_f pin6`；bt_rf_clk1 时钟 | okay |

- **芯片识别**：`supported-ids = <0x1107>`（Qualcomm PCI device id，WCN785x 系），代号 **kiwi** ——FastConnect 7800 级 Wi-Fi 7 + BT combo；`qcom,wlan-rc-num = 0`（走 PCIe RC0）。
- pinctrl 组：`cnss_wlan_en_active/sleep`（GPIO16）、`cnss_wlan_sw_ctrl(_wl_cx)`（GPIO18 function `wcn_sw_ctrl`）、`bt_en`（pm8550ve_f）。
- MSI 映射：`msi-map = <0x1400 &gic_its 0x1400 1>` → **GIC ITS**，StreamID 0x1400；`iommu-map = <0x1400 &apps_smmu 0x1400 0xff>`（pcie_qtb 域 0x1400，IOVA 32bit）。PCIe 视口 IOVA 窗 `0x98000000+0x80000000`（iommu-geometry），tlucc/dbic/ibar 窗见 bootargs。
- RAM dump 预留 `qcom,wlan-ramdump-dynamic = 7.5MB`；`/reserved-memory/cnss_wlan_region` （shared-dma-pool、reusable、32MB、4G 内、对齐 4M）挂给 `cnss_pci0`。
- BT HCI：DT 未给显式 uart 属性；树中存在 SE14 高速 UART（`hsuart0`，§2）与 `qcom,qrtr-mhi`/ `qcom,qrtr-gunyah`（PCIe MHI 通道）两套通路，WCN785x 实际 BT HCI 走 PCIe MHI 或 SE14 UART，接驱动时以真机日志定夺。声卡节点带 `qcom,wcn-bt` 标志（音频也走 WCN）。
- 小米自加监控：`/soc/xiaomi_wifi_gpio`（compatible `xiaomi,xiaomi-wifi`，GPIO79 `wifi_ctrl_irq` 去抖 30ms，okay）。
- 中期 iOS Wi-Fi 路：fork 的 Wi-Fi 栈（M1 已在 QEMU 用软驱）→ kiwi PCIe 驱动是全新工作，先记资源不排期。

## 7. 蜂窝调制解调器 / 远程处理器（PAS）

合并 DT 里 remoteproc 节点齐全（此前"痕迹未见全"的注记作废）：

| 处理器 | 节点 | compatible | reg/基址 | 邮箱/中断 | 内存区 | 状态 |
|---|---|---|---|---|---|---|
| **Modem(MPSS)** | `/soc/remoteproc-mss@04080000`（`modem_pas`） | `qcom,sun-modem-pas` | `0x04080000+0x10000` | `qcom,smp2p-modem`：`mboxes=<&ipcc_mproc 2 2>`，中断 `<&ipcc 0x2 0x2>`；`qcom,remote-pid=1`；entries master/slave-kernel、ipa、smem-mailbox | `memory-region = mpss_mem(0x8ba00000+0xf600000, 246MB) + q6_mpss_dtb_mem(0x9b000000+0x80000) + system_cma + dsm_partition_1/2` | okay |
| ADSP | `/soc/remoteproc-adsp@03000000`（`adsp_pas`） | `qcom,sun-adsp-pas` | `0x03000000+0x10000` | smp2p/glink | `adspslpi_mem 0x9ee00000+0x4580000` + q6_adsp_dtb | okay |
| CDSP(NPU) | `/soc/remoteproc-cdsp@32300000`（`cdsp_pas`） | `qcom,sun-cdsp-pas` | `0x32300000+0x10000` | smp2p-cdsp | `cdsp_mem 0x9d200000+0x1900000` + secure/eva heap | okay |
| SPSS | `/soc/remoteproc-spss@1880000`（`spss_pas`） | `qcom,sun-spss-pas` | `0x188101c` 起 6 个 4B 寄存器窗（sp2soc_irq 等） | `<0 0x160 1>`=SPI 352→INTID 384 | `sp_mem` | okay |
| SOCCP | `/soc/remoteproc-soccp@a3380000`（`soccp_pas`） | `qcom,sun-soccp-pas` | `0xa3380000+0x10000` | — | `soccp_mem 0x9ec00000+0x180000` + soccp_sdi | okay |

SMMU 关系：外设（含 modem 侧 IPA/PCIe）StreamID 全部汇入 **apps_smmu**（§9）；modem 自身的 `spu_modem_shared_mem 0x9b2c0000+0x40000` 与 TZ/SPU 共享。IPA fw 区 `ipa_fw_mem 0x9b080000`。全部 okay——kernel bring-up 若先不起 modem，可整体绕开 PAS 驱动；注意 DT **没有** `qcom,support-shutdown` 属性，即无 SSR 关机交接语义，排期最远，资源暂不展开。

## 8. I2C / SPI 总线总表（QUP GENI 序列引擎）

三个 QUP 包装器（compatible `qcom,geni-se-qup`，包装器自身 `iommus=<&apps_smmu 0xa3>`，时钟均出自 GCC）：

| 簇 | 包装器基址 | SE 编号/地址 | 在用 SE（status ok） |
|---|---|---|---|
| `qupv3_1` | `/soc/qcom,qupv3_1_geni_se@ac0000`（`0xac0000+0x2000`） | SE0–SE7 @ `0xa80000–0xa9c000` 步进 0x4000 | I2C：SE0 `0xa80000`、SE3 `0xa8c000`、SE5 `0xa94000`、SE6 `0xa98000`；SPI：**SE2 `0xa88000`（触摸）**；UART：**SE7 `0xa9c000`（控制台）** |
| `qupv3_2` | `/soc/qcom,qupv3_2_geni_se@8c0000`（`0x8c0000+0x2000`） | SE8–SE15 @ `0x880000–0x89c000` | I2C：SE8 `0x880000`、SE9 `0x884000`；SPI：SE15 `0x89c000`（红外）；UART：SE14 `0x898000`（hsuart0） |
| `qupv3_0_i2c_hub` | `/soc/qcom,qupv3_i2c_geni_se@9c0000`（`0x9c0000+0x2000`） | hub SE0–9 @ `0x980000–0x99c000` | I2C：hub_i2c0 `0x980000`（音频功放） |

在用总线挂的设备（按 SE 归位；其余 SE 全部 disabled）：

| 总线 | 片上设备（地址） | 备注 |
|---|---|---|
| i2c@a80000 (SE0) | `nq@0x28`（`qcom,sn-nci`） | NFC（NCI） |
| spi@a88000 (SE2，别名 spi0) | **`goodix@0` 触摸（§3）** | 15MHz CS0 |
| i2c@a8c000 (SE3) | `fsa4480@0x42` | USB Mux/Type-C 开关（wcd939x@0xe 禁用） |
| i2c@a94000 (SE5) | `sc8585_master@0x6e`、`bq27z561_standlone@0x55` | 充电泵 + 电量计 |
| i2c@a98000 (SE6) | `hl7603@0x77` | 无线充电 RX（小米 SC96281/NU1652 FOD 数据节点在 /soc 下） |
| uart@a9c000 (SE7) | 控制台（§2） | 别名 serial0 |
| i2c@880000 (SE8) | `qcom,cam-sensor2@0x7a`、eeprom@0x50 | 摄像头（CCI 伴生） |
| i2c@884000 (SE9) | `qcom,cam-sensor1@0x10`、eeprom@0x51 | 摄像头 |
| uart@898000 (SE14) | 高速 UART（§2/§6） | 别名 hsuart0 |
| spi@89c000 (SE15) | `ir-spi@0` | 红外发射 |
| i2c@980000 (hub0) | `tfa98xx_1@0x36`、`tfa98xx_2@0x34`（Ti 功放）、`sipa_i2c_R@0x6c`、`sipa_i2c_L@0x6e`（Sia91xx） | 音频功放两条线 |

触摸、振动、传感器复用总线时的空闲余量：QUP_1 的 SE1（0xa84000）/SE4（0xa90000）与 hub 簇 SE1–9。

## 9. SMMU

| 项 | 节点路径 | compatible | reg/基址 | 中断 | 状态 |
|---|---|---|---|---|---|
| **apps_smmu** | `/soc/apps-smmu@15000000`（label `apps_smmu`） | `qcom,qsmmu-v500` | `0x15000000+0x100000`；`qcom,use-3-lvl-tables`；`qcom,handoff-smrs=<0x800 0x02>`（UEFI 阶段已接手的 SID 0x800/0x802，即显示路径）；`dma-coherent` | 首 cell `<0 0x41 4>`=INTID 97（全局 fault），其余 0x61–0x1f6 各 cell 为 per-TBU/context fault | okay |
| GPU SMMU | `/soc/qcom,kgsmmu@3da0000`（`kgsl_smmu`） | `qcom,qsmmu-v500`,`qcom,adreno-smmu` | `0x3da0000+0x40000`；CB `/soc/qcom,gpu-smmu-cb`（`kgsl_smmu_cb`）`0x3da1000+0x1000` | fault cb | okay |
| 显示 CB | `/soc/qcom,smmu_sde_unsec_cb` / `qcom,smmu_sde_sec_cb` | — | 无 reg（apps_smmu 的 context bank，`qcom,iommu-cb=<&apps_smmu 0x800/0x801>`） | — | okay |

apps_smmu 下游 **QTB（TBU）StreamID 域**（`qcom,qsmmuv500-tbu`/`qcom,qtb500`）：

| QTB | reg | SID 域 | IOVA 宽 |
|---|---|---|---|
| anoc_1_qtb | `0x16f2000+0x1000` | `0x0000+0x400` | 36b |
| anoc_2_qtb | `0x171b000+0x1000` | `0x0400+0x400` | 36b |
| mdp_hf_qtb | `0x17d0000+0x1000` | `0x0800+0x400` | 32b |
| nsp_qtb | `0x7d3000+0x1000` | `0x0c00+0x400` | 32b |
| lpass_qtb | `0x7b3000+0x1000` | `0x1000+0x400` | 32b |
| pcie_qtb | `0x16cd000+0x1000` | `0x1400+0x400` | 32b |
| sf_qtb | `0x17d1000+0x1000` | `0x1800+0x400` | 32b |
| cam_hf_qtb | `0x17d2000+0x1000` | `0x1c00+0x400` | 36b |
| gpu_qtb | `0x3de8000+0x1000`（挂在 kgsl_smmu） | `0x0000+0x400` | 49b |

QUP 包装器自身 `iommus=<&apps_smmu 0xa3>`（SE DMA 也过 SMMU，fastmap 32bit 窗）——iOS 侧若直接驱动 QUP/触摸，记得把 SID 0xa3 恒等映射或 bypass。

## 10. reserved-memory 全表（按基址排序）

iOS 侧关键：**splash_region 0xFC800000+0x2B00000（GOP framebuffer / 连续 splash，bootloader logo 残留）**；`non_secure_display_region`（动态 CMA 252MB，4G 下）；`cnss_wlan_region` （动态 32MB，Wi-Fi DMA）。

| 基址 | 大小 | 节点名（label） | 用途 |
|---|---|---|---|
| — | 0x0 | demura_region_0/1（demura_memory_0/1） | 面板 demura 数据（运行时填） |
| 0x80000000 | 0x1200000 | gunyah_hyp_region（gunyah_hyp_mem） | Gunyah hypervisor 本体 |
| 0x81200000 | 0x200000 | cpucp_pdp_region | CPUCP PDP |
| 0x81a00000 | 0x40000 | xbl_dtlog_region | XBL 日志 |
| 0x81c00000 | 0x60000 | aop_image_region | AOP FW |
| 0x81c60000 | 0x20000 | aop_cmd_db_region（`qcom,cmd-db`） | AOP cmd-db（RPMh 依赖） |
| 0x81c80000 | 0x74000 | aop_tme_uefi_merged_region | AOP/TME/UEFI 合并区 |
| 0x81cf4000 | 0x800 | dump_display_region | 显示 dump |
| 0x81d00000 | 0x200000 | smem_region（`qcom,smem`） | SMEM（smp2p/remoteproc 依赖） |
| 0x81f00000 | 0x100000 | pdp_ns_shared_region | PDP 共享 |
| 0x82000000 | 0x380000 | cpucp_scandump_region | CPUCP scandump |
| 0x82380000 | 0x20000 | adsp_mhi_region | ADSP MHI |
| 0x823a0000 | 0x40000 | soccp_sdi_region | SOCCP SDI |
| 0x823e0000 | 0x80000 | pmic_minii_dump_region | PMIC dump |
| 0x824a0000 | 0x100000 | pvm_fw_region | protected VM FW |
| 0x82600000 | 0x100000 | global_sync_region | 全局同步 |
| 0x82700000 | 0x100000 | tz_stat_region | TZ 状态 |
| 0x82800000 | 0x2000000 | qdss_apps_region（reusable dma-pool） | QDSS trace |
| 0x84a00000 | 0x4900000 | dsm_partition_1_region | DSM（modem 日志分区1） |
| 0x89300000 | 0xa80000 | dsm_partition_2_region | DSM 分区2 |
| **0x8ba00000** | **0xf600000** | mpss_region（mpss_mem） | **Modem 镜像 246MB** |
| 0x9b000000 | 0x80000 | q6_mpss_dtb_region | modem DTB |
| 0x9b080000 | 0x10000 | ipa_fw_region | IPA FW |
| 0x9b090000 | 0xa000 | ipa_gsi_region | IPA GSI |
| 0x9b09a000 | 0x2000 | gpu_microcode_region | GPU 微码 |
| 0x9b09c000 | 0x4000 | lost_reg_mem | 占位 |
| 0x9b0a0000 | 0x1e0000 | spss_region_region（spss_region_mem） | SPSS |
| 0x9b280000 | 0x40000 | spu_secure_shared_memory_region（spu_tz_shared_mem） | SPU↔TZ |
| 0x9b2c0000 | 0x40000 | spu_secure_shared_memory_region（spu_modem_shared_mem） | SPU↔Modem |
| 0x9b300000 | 0x800000 | camera_region | 相机 |
| 0x9bb00000 | 0x800000 | camera_2_region | 相机2 |
| 0x9c300000 | 0x800000 | video_region | 视频 |
| 0x9cb00000 | 0x700000 | cvp_region | CVP |
| 0x9d200000 | 0x1900000 | cdsp_region | CDSP 镜像 25MB |
| 0x9eb00000 | 0x80000 | q6_cdsp_dtb_region | CDSP DTB |
| 0x9eb80000 | 0x80000 | lost_reg_mem2 | 占位 |
| 0x9ec00000 | 0x180000 | soccp_region | SOCCP |
| 0x9ed80000 | 0x80000 | q6_adsp_dtb_region | ADSP DTB |
| 0x9ee00000 | 0x4580000 | adspslpi_region | ADSP 镜像 69.5MB |
| 0xa3500000 | 0x400000 | ramoops-region（`ramoops`） | pstore（kernel 崩溃日志可直接接） |
| 0xb8000000 | 0x200000 | xbl_ramdump_region | XBL ramdump |
| 0xd4e23000 | 0x2dd000 | hwfence-shmem | HW fence |
| 0xd8000000 | 0x600000 | tz_merged_region | TZ |
| 0xf3800000 | 0x5000000 | trust_ui_vm_region（reusable shared-dma-pool） | TrustUI VM |
| 0xf8800000 | 0x3800000 | oem_vm_region | OEM VM |
| 0xfc000000 | 0x400000 | shm@fc000000（oem_vm_shm，gunyah-label 3） | VM 共享内存 |
| **0xfc800000** | **0x2b00000** | **splash_region（splash_memory，"cont_splash_region"）** | **GOP framebuffer / 连续 splash** |
| 0xff800000 | 0x800000 | llcc_lpi_region | LLCC LPI |
| 动态 | 0x2000000 | cnss_wlan_region（shared-dma-pool，reusable，<4G，对齐 4M） | Wi-Fi DMA |
| 动态 | 0xfc00000 | non_secure_display_region（shared-dma-pool，reusable，<4G，对齐 4M） | 显示 CMA |
| 动态 | — | linux,cma（system_cma）、qseecom/qseecom_ta、sp_region、vm_comm_mem、adsp_heap、va_md_mem、qmc_dma、secure_cdsp_heap 等 | 各类 dma-pool |

注：`cnss_pci0_iommu_region_partition` 把 IOVA 0x98000000–0xb0000000 与 0xb0000000+0x50000000 从可用域划走给 PCIe 视口（`qcom,iommu-geometry`/`qcom,range`），与物理区同名易混，是 **IOVA**。

## 11. 其它 kernel bring-up 资源

| 项 | 节点 | compatible | 基址 | 中断 | 状态 |
|---|---|---|---|---|---|
| SPMI 主 arbiter | `/soc/qcom,spmi@c42d000`（`spmi_bus`） | `qcom,spmi-pmic-arb` | cnfg `0xc42d000+0x4000`，core `0xc400000+0x3000`，chnls `0xc500000+0x400000`，obsrvr `0xc440000+0x80000`，intr `0xc4c0000+0x10000` | `interrupts-extended=<&pdc 1 4>`（PDC 索引 1） | okay；下挂 17 个 PMIC：pmk8550@0、pm8550@1、pm8550ve@3/5/6/8、pm8550vs@9/j、pmih010x@7（haptics）、pmd802x@4、pmr735d@a、pm8010@c/d 等 |
| SPMI 副 arbiter | `/soc/qcom,spmi@c432000`（`spmi1_bus`） | 同上 | c432000 系 | — | **disabled** |
| SPMI debug | `/soc/qcom,spmi-debug@c540000` | `qcom,spmi-pmic-arb-debug` | `0xc540000` 系 | — | okay |
| TLMM GPIO | `/soc/pinctrl@f000000`（`tlmm`，全部 GPIO 中断父） | `qcom,sun-tlmm` | `0xf000000+0x202000` | 自身 `<0 0xd0 4>`=INTID 240；`wakeup-parent=<&pdc>` | okay |
| GCC 总时钟 | `/soc/clock-controller@100000`（`gcc`） | `qcom,sun-gcc`,`syscon` | `0x100000+0x1f4200`；电源 `vdd_cx`/`vdd_mx`（RPMh） | — | okay |
| TCSRCC | `/soc/clock-controller@f204008`（`tcsrcc`） | `qcom,sun-tcsrcc` | `0xf204008+0x3004` | — | okay |
| DISPCC | `/clock-controller@af00000`（`dispcc`） | `qcom,sun-dispcc` | `0xaf00000` | — | okay |
| RPMh 电源 | 根层 `/rpmh-regulator-*` 系节点 | `qcom,rpmh-regulator` | 经 cmd-db（`aop_cmd_db_mem`）与 AOP 通信，无 MMIO 直控 | — | okay；本图谱引用：L11B/L13B/L4B（显示）、L2G（vddio）、L12B（触摸 iovdd）、SMPD1/G3/D4+LDOF2/3+LDO6K+SMPI7（Wi-Fi）等 |
| PMIC GPIO | `/soc/qcom,spmi@c42d000/qcom,pmk8550@0/pinctrl@b800`、`…/qcom,pm8550ve@5/pinctrl@8800` 等 | `qcom,pmic-gpio` | SPMI 窗口 b800/8800 | SPMI 中断 | okay（BT reset/enable 用 pm8550ve_f pin3） |
| UFS | `/soc/ufshc@1d84000`（alias ufshc1）+ UFS PHY @`0x1d80000`（qmp-v4-sun 系） | `qcom,ufs` 系 | HC `0x1d84000`（**与 redwood 同基址**） | — | okay；loader 里 hc_* 逻辑对 annibale 不应当炸（skip_ufs_arbitration 语义="内核不从 UFS 起，无需交接"）；路线 D 近期不需要内核 UFS 驱动 |
| SDHCI | `/soc/sdhci@8804000`（alias mmc1） | `qcom,sdhci-msm` | `0x8804000` | — | okay（SD 卡，非启动路径） |
| HWSPINLOCK | `/soc/tcsr_mutex`（`tcsr_mutex`） | `qcom,tcsr-mutex` | 0x1fc0000 系 | — | okay |

## 12. 相机：CAMSS（titan 家族，主摄 OV50E 定制）

完整拆解与移植路线在 `docs/plan/camera-plan.md`；本表只收编硬件事实（源 `/tmp/hw_check.dts`，行号见 camera-plan §2.2）。

| 块 | 基址/大小 | 备注 |
|---|---|---|
| camcc | `0xade0000+0x20000` | `qcom,sun-camcc`,`syscon`；GDSC：titan_top +0x134c、tfe0/1/2 +0x1004/0x1084/0x10ec、ipe0 +0x17c、ofe +0xc8 |
| cambistmclkcc / camcc_crmc | `0x1760000` / `0xadcd600` | bist/mclk 时钟与 CRMC syscon |
| CSIPHY0–5 | `0xada9000` 起步进 `0x2000`（各 8K） | csiphy **v2.3.0**，C/D-PHY 通用 |
| CSID0/1/2 | reg `0xad27000`/`0xad2a000`/`0xad2d000`（0x2b00） | `qcom,csid980`；节点名与 reg 差 0x1000，**以 reg 为准** |
| CSID-lite0/1 | `0xad6d000` / `0xad72000`（0xa00） | `qcom,csid-lite980` |
| IFE0/1/2 | `0xac86000`/`0xac96000`/`0xaca6000`（各 64K） | 时钟名 tfe_0..2；UBWC static cfg |
| IFE-lite0/1 | `0xad6d000+0x2800` / `0xad72000+0x2800` | 与 csid-lite 同窗打包 |
| CAM-CPAS | `0xac13000` | cam_cpas_top/camnoc_nrt/camnoc_rt/rpmh/cesta——**titan 访问前必须先起 CPAS/CAMNOC（redwood无此步）** |
| CCI0/1/2 | `0xac7b000` / `0xac7c000` / `0xac7d000` | 主摄走 CCI0 master1 |
| CAM SMMU | `qcom,cam_smmu` 多 context（ife/icp/jpeg/cdm/secure） | redwood单 context 经验不通用 |
| TPG13–15 | `0xad8b000`+（第二窗 `0xac04000`） | cam=3 等价演示路径依托 |
| RT-CDM | `cam-cdm-intf` + rt-cdm2_2×5（pid 0x18..0x1c） | IFE980 编程走 RT-CDM，非纯直写 |

sensor 挂线：wide 主摄=CCI0 m1/CSIPHY3/MCLK1(GPIO90)/RESET GPIO6，轨 VIO1.8/VDIG1.15/ VANA2.8(`camera_wide_avdd_ldo`，GPIO127 开关)/VAF3.1/BOB2 2.7；tele=CCI1 m0/CSIPHY1；ultra=QUP SE8 I2C `0x880000`（0x7a）/CSIPHY2；front=SE9 `0x884000`（0x10）/CSIPHY4。供电轨都是 RPMH LDO（走 SPMI，非redwood PM8008i 手撸 I2C）。主摄=光影猎人800 （OV50E 小米定制，50MP/1/1.55"/OIS）；chip ID/上电序列在 vendor sensormodule bin，待真机 `adb pull /vendor/lib64/camera`。

## 附：与既有文档/代码的衔接核对

1. `docs/analysis/annibale-uefi-build.md`：merged DTB 生成方式（v3.dtb + 自家 dtbo，fdtoverlay，956,243B）与本文数据源一致；面板 XML 节点 label `dsi_p11_42_0d_0a_p10_dsc_cmd` 的全部被消费字段已在 §4 表中给出。
2. `docs/analysis/uefi-sm8750.md` 提到的 "kiwi Wi-Fi、Goodix goodix_core 触摸" 与 §6/§3 一致（DT 主 compatible 分别是 `qcom,cnss-kiwi` / `xiaomi,touch-spi`）。
3. loader `platform_annibale`：GIC 三窗、uart 0xa9c000、fb_base 0xfc800000 均与 DT 实证吻合；`io_base=0x00400000 + 0x3FC00000` 的 IO 窗覆盖 TLMM/GCC/QUP/SPMI/GIC 全部 MMIO。
4. 本次勘误（相对旧稿）：触摸 SPI 是 `spi@a88000`（非 a8c000）；DT 里**确有**固定显示保留区 `splash_region@fc800000`；modem/ADSP/CDSP/SPSS/SOCCP remoteproc 节点齐全（§7）；haptics 所在 PMIC 是 **PMIH010X**（非 PMI010x）。
