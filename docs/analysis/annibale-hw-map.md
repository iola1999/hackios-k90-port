# annibale（REDMI K90 / SM8750 "sun"）硬件资源图谱

数据源：我方 FD 内嵌的合并设备树
`hackios-xnu-kernel/Mu-Silicium/Platforms/Xiaomi/annibalePkg/FdtBlob/sm8750-xiaomi-annibale.dtb`
（vendor_boot base DT ⊕ 自家 dtbo，956KB）。`dtc -I dtb -O dts` 提取后逐项核对，
2026-10-23。GPIO 控制器 phandle 0x27 = tlmm。

## 1. 中断控制器 / timer / PSCI（内核 bring-up 三件套）

| 项 | 值 |
|---|---|
| GICv3 | `interrupt-controller@16000000`：dist 0x16000000+0x10000，redist 0x16080000+0x200000，stride 0x40000，ITS @0x16040000 —— **与 loader platform_annibale 完全一致** |
| memtimer | `timer@16800000`（系统计数器组） |
| PSCI | `arm,psci-1.0`，**method = "smc"**；CPU idle 状态簇齐全 |
| memory 节点 | reg = 0（占位）——内核内存以 loader 从 EDK2 memory map 注入为准 |

## 2. UART 控制台

- `serial0` 别名 → `/soc/qcom,qupv3_1_geni_se@ac0000/qcom,qup_uart@a9c000`，
  chosen `stdout-path = "serial0:115200n8"` → **控制台基址 0xa9c000，115200 8n1**。
- loader `platform_annibale.uart` 由 0 改为 0xa9c000（本轮修复）。
- 副产物 `hsuart0` = qupv3_2@8c0000/qup_uart@898000（备用）。
- 桌面 wch 串口线（921600）与本设备无关（desk-01 JSON 干扰源），别再碰。
- Android 自家 bootargs 见 chosen（无 console=，纯靠 stdout-path；我们自己的
  cmdline 要显式给）。

## 3. 触摸（Goodix，SPI）

- 节点 `goodix@0`（compatible `"xiaomi,touch-spi"`，goodix 调优参数群 + qts TVM）。
- 总线：`spi@a8c000`（QUP_1 SE 系；别名 spi0 = `spi@a88000`），
  `spi-max-frequency = 15MHz`（0xe4e1c0）。
- `goodix,irq-gpio = <&tlmm 162 0x2008>`（**GPIO_162**），
  `goodix,reset-gpio = <&tlmm 161 0>`（**GPIO_161**）。
- Trusted-touch TVM：io base **0xa88000**、spi-irq 0x28c、gpio-list 含
  (27,40..43)+(27,161,162)——iOS 侧先裸 SPI，TVM 路可完全绕开。
- 电源：`vdd-supply`/`avdd-supply` 是 regulator phandle（名 vdd/avdd），
  上电时序内核侧要自己补。

## 4. 显示

- 面板时序/DSC/初始化命令已由 `tools/dts2panelxml.py` 提取进 annibalePkg RAW；
  DisplayDxe 按 `<PanelName>`/DDIC ID 匹配，K90 DDIC 自报 ID 仍未取得（待日志）。
- GOP fb：我方 FD `MemoryMapLib` 的 `Display_Reserved` = **0xFC800000+0x2B00000**
  → loader `platform_annibale.fb_base`（kernel 仓 872da86）。
- 设备自家 DT 里显示相关保留区只有 `non_secure_display_region`
  （shared-dma-pool/reusable，size 0xFC00000=252MB，**无固定地址**，内核 CMA 性质）
  ——与 FD 的固定 carveout 是两回事，Linux 消费前者，我们 EDK2 用后者。

## 5. 震动

- `qcom,hv-haptics@f000`，compatible `"qcom,hv-haptics"`，**PMI010x PMIC 内**
  （SPMI 从设备 reg 块 f000/f100/f200），irq `"fifo-empty"`；
  LRA 周期 5714us、vmax 1300mV、驱动/制动波形齐。
- SPMI PMIC arbiter：`qcom,spmi@c42d000`（qcom,spmi-pmic-arb，
  reg 窗 c42d000/c400000/c500000/c440000/c4c0000）。

## 6. Wi-Fi / BT

- **WCN7850（kiwi）**：`qcom,cnss-kiwi@b0000000`（reg-names smmu_iova_ipa），
  supported-ids **0x1107**，PCIe RC0（`qcom,wlan-rc-num = 0`）；
  `wlan-en-gpio=<&tlmm 16>`，`qcom,sw-ctrl-gpio=<&tlmm 18>`，
  `qcom,wlan-sw-ctrl-gpio=<&tlmm 19>`，bt-en 走 ssi2gpio 次级控制器；
  `wlan_mem = cnss_wlan_region`（shared-dma-pool）。
- 中期 iOS Wi-Fi 路：fork 的 Wi-Fi 栈（M1 已在 QEMU 用软驱）→ kiwi PCIe 驱动
  是全新工作，先记资源不排期。

## 7. 蜂窝调制解调器

- DT 内 modem 痕迹为 `spu_secure_shared_memory_region@9b2c0000` 等共享区
  （qcom,mhi/PCIe modem 节点在 modemiio/独立 include 里，base DT 提取稿未见全）。
- 排期最远，资源暂不展开。

## 8. 存储

- `ufshc@1d84000`（UFS HC），PHY `ufs-phy-qmp-v4-sun` @0x1d80000（2 lane/方向）
  ——**redwood 与 SM8750 的 UFS HC 基址相同（0x1d84000）**，loader 里
  hc_* 寄存器逻辑对 annibale 不应当炸（skip_ufs_arbitration 仍保留，语义是
  "内核不从 UFS 起，无需交接"）。
- 路线 D（rootfs-strategy.md）近期不需要内核 UFS 驱动。

## 9. SMMU / GPIO

- apps SMMU = **qsmmu-v500 @ 0x15000000+0x100000**（3 级表，handoff-smrs 0x800/2），
  GPU SVA 独立。
- TLMM：`pinctrl@f000000`（qcom,sun-tlmm，reg 0xf000000+**0x202000**，
  irq 208）。

## 10. 其它

- I2C/SPI 全族在 `qcom,qupv3_1_geni_se@ac0000`（QUP_1：uart a9c000、spi a88000/
  a8c000…）与 `qcom,qupv3_2_geni_se@8c0000`（QUP_2：898000 hsuart、88x000 系）
  两个簇；loader `io_base=0x00400000 + 0x3FC00000` 的 IO 窗已覆盖之。
- LPAE 地址：DDR 高段在 32 位以上，chosen bootargs 里 `disable_dma32=on` 佐证。
- 原始提取稿：/tmp/hw_check.dts（43867 行，源自仓内 DTB，可复现）。
