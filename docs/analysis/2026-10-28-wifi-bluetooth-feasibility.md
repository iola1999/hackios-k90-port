# Wi-Fi 与蓝牙：可行性结论与最小验证路径（2026-10-28）

本文回答两件事：WCN7850 的 Wi-Fi 与蓝牙在 K90 上「做不做得成」，以及每一项按依赖关系的第一步是什么、哪一步必须上真机。已有基础见 [WCN7850 计划](../plan/wcn7850-plan.md)、[PCIe 勘察与上电记录](../progress/2026-10-26-wifi-pcie-survey.md)、[iOS 蓝牙接入可行性](2026-10-26-ios-bluetooth-feasibility.md)。本轮只做静态分析与离线取证，没有真机操作，也没有写驱动。

两项的可行性不同：Wi-Fi 的路径已经通到「只差工作量」，唯一的未知是 apps SMMU 对端点流量的态度；蓝牙的硬件侧同样明确，卡点在 iOS 26 仍然是 Broadcom 专用芯片表。文末列出本轮的依据、未确认项，以及要动的文件。

## 1. 结论

| 项目 | 判断 | 唯一的硬门槛 | 第一步 | 需不需要真机 | 到「可用」的距离 |
|---|---|---|---|---|---|
| Wi-Fi | 可行。PCIe 链路、BAR0、MHI 寄存器已实测；固件全部在机内备份里 | apps SMMU 对端点流量是放行还是必须建 context，只有读一次寄存器能定 | 离线固定固件输入（解出 amss/board/regdb、组装 board-2.bin、算 SHA-256），**不需要设备** | 离线部分不需要；SMMU 判读要一轮 | 真机窗口 4～8 周，离线可先做 2～3 周 |
| 蓝牙 | 硬件可行，iOS 26 侧仍是 Broadcom 专用表，没有给高通开门 | iOS 的 `BlueTool` 认不认这颗芯片，只能靠内核代理身份来绕 | 内核注册 `com.apple.uart.bluetooth` 并记录 `BlueTool` 的报文，零硬件依赖 | 要一轮，但没有硬件风险 | 硬件通 2～3 周，iOS 接受再 1～2 周；音频另算 |

两条共同点：第一步都不在驱动里。Wi-Fi 的第一步是整理固件，蓝牙的第一步是一段只记录不回包的 socket 代码。真机在这两件事里只负责读一个状态（SMMU）和取一份报文序列（BlueTool），硬件可以先不动。

## 2. Wi-Fi：五件事

### 2.1 需要哪些内核接口

按依赖顺序，前四项是数据通路的必经环节，最后一项是与 iOS 的接口。

- **PCIe RC0 上电与链路**：已有。`bsd/dev/mhi_pcie_power.c`（524 行）按主线 Linux 的做法完成 GDSC、CRM、RPMh 投票、PHY 序列、PERST 与 iATU，实测进 L0、Gen1 x2、读出 `0x17cb:0x1107`、BAR0 分配到 `0x40400000`。这一层不需要新工作，只在提速或复位恢复时再看。
- **MHI host**：新工作，建议新文件 `annibale_mhi.c`（或 `redwood_mhi.c`）分片写。最小子集是 BHI/BHIe（SBL 段下载、向量提交、按 `TXVECSTATUS` 的 sequence 判完成）、`MHICTRL` 的 RESET/ENABLE、`MHISTATUS` 状态机、EE 状态、MHI 通道与事件环。Linux 参照 `drivers/bus/mhi/host/*`，寄存器偏移以本机读到的 `MHIREGLEN`/`MHICFG` 为准（`0x100`/`0x00800080`，通道门铃 `0x300`、事件门铃 `0x700`、BHI `0x100`、BHIe `0x224`）。
- **apps SMMU 与 DMA**：新工作。要回答的两件事是「端点事务带什么 SID」和「该 SID 在 SMMU 里是放行（bypass）还是要查页表」。放行的话第一阶段可以用物理地址直接做 BHI 下载；要查页表就得先建 context 与页表，并在 loader 的 held 保护里覆盖这些缓冲。
- **QRTR over MHI 与 QMI**：`redwood_qmi.c`（957 行）的表驱动编解码可以复用，换传输层；`redwood_wlfw.c`（545 行）的握手逻辑可以平移，报文表要按 ath12k 重抽（`tools/mk-wlfw.sh` 改指向）。
- **数据面**：Plan A 是手写最小 WMI 集（scan/join/收发，直接对 CE/REO/TCL ring），Plan B 是用 `mk-ath12k.sh` 把 ath12k 加 LinuxKPI 全量搬进来（照 `mk-ath11k.sh` 的做法）。
- **与 iOS 的接口**：已有且芯片无关。`bsd/dev/redwood_net.c`（377 行）造 en0，`bsd/dev/redwood_apple80211.c`（739 行）答 Apple80211 请求，`files/iokit/Kernel/RedwoodWLAN.cpp`（137 行）注册 `IO80211Controller` 与 `IONetworkInterface` 两个只带属性的对象。Wi-Fi 换上真射频时这三处只需要把 link 指过去。

中断不在第一阶段依赖里。BHIe 完成后 `TXVECSTATUS` 的 sequence 会变，MHI 的状态机在 `MHISTATUS` 里可见，两者都能轮询；redwood 的 ring 本来就是轮询（`wifi_irq=1` 才走 MSI）。MSI/ITS 只在数据面吞吐不足时才需要考虑，那时再单独评估。

### 2.2 固件从哪里来

全部在机内备份里，不需要从外网取主固件。Wi-Fi 固件在 modem 分区（挂载点是 `/vendor/firmware_mnt`）的 `image/kiwi/`，本轮解出并确认的清单：

| 文件 | 大小（字节） | 用途 |
|---|---|---|
| `amss.bin` | 7,458,880 | 主固件（hw1.0 命名） |
| `amss20.bin` | 6,426,688 | 主固件，`20` 后缀对应 hw2.0，与 linux-firmware 的 `WCN7850/hw2.0` 同类 |
| `regdb.bin` / `regdb_xiaomi.bin` | 24,278 / 24,278 | 监管域数据 |
| `phy_ucode.elf` / `phy_ucode20.elf` | 299,660 / 299,660 | PHY 微码 |
| `bdwlan.e01`…`e41`、`e52`、`bdwlan.elf` | 各 88,860 | 板级数据，共 63 个变体 |
| `bd_p11.elf`、`bd_p11bob.elf`、`bd_p11gl.elf` | 约 88,800 | 板级数据的另一种形态 |
| `Data.msc` / `Data20.msc` | 1,158,272 / 1,273,881 | 未定性的容器 |
| `ncm865` 风格的分区外来源 | — | linux-firmware `ath12k/WCN7850/hw2.0/{amss.bin,board-2.bin,m3.bin}` 与 `ncm865/{amss.bin,m3.bin}` |

三点判断：

- **主固件取机内的 `amss20.bin`。**linux-firmware 当前的 `WCN7850/hw2.0/amss.bin` 是 6,090,816 字节，与机内两份都不同尺寸，属于更新或不同分支的版本；机内那份与本机硬件和校准配套，风险最低。两者的版本号与 SHA-256 待固定后写进清单。
- **`m3.bin` 可能要单独准备。**ath12k 对 WCN7850 用 host 侧的 M3 loader（`fw.m3_loader = ath12k_m3_fw_loader_driver`），WLFW QMI 会把 M3 内存的物理地址交给固件（`ath12k_qmi_m3_load()` → `req.addr = m3_mem->paddr`），所以这条流程要一份 M3 映像；机内分区没有独立的 `m3.bin`。linux-firmware 的 `WCN7850/hw2.0/m3.bin` 有现成的。机内 `amss.bin` 是否已经包含 M3、能否切出来，本轮没有验证。
- **板级数据要转换一次**。ath12k 只认 `board-2.bin`（带 `QCA-ATH12K-BOARD` 魔数和 IE 结构），机内是 63 个 `bdwlan.eXX` 平文件。转换是机械工作：写一个脚本把候选的 `bdwlan.eXX` 包成 IE；具体选哪一个是 boot 时 WLFW QMI 回报的 `qmi-chip-id`/`qmi-board-id` 决定，也就是说要先跑通固件下载，才能确定哪一份是对的，此前的转换只是把 63 份都备好。

结论：固件可得性不再是风险项。剩下的是固定版本、组装 `board-2.bin`、补 `m3.bin` 三件机械活。

### 2.3 iOS 侧哪个服务在等它

等的是一个带 IO80211 形状的 en0，与射频无关。三处消费者：

- **wifid**（`/usr/sbin/wifid`，iOS 26 上 2,918,432 字节，`com.apple.wifid.plist` 在）。它按 `IO80211InterfaceRole = "Infrastructure"` 找到设备，再按 `IOInterfaceName` 绑接口；绑定失败就走 Apple80211 的 ioctl 路径。负载里 wifid 已默认启动（`userland/build.sh` 的 `WIFID=1`），iOS 26 的启动日志里它一直在跑。
- **configd/SystemConfiguration**：把 `IONetworkInterface` 且父对象是 `IO80211Controller` 的口认成 Wi-Fi 口，为它建网络服务。没有服务就不能成为路由口，wifid 加入网络后会停在「failed to become routable interface」。
- **Settings/控制中心**：经 wifid 与 MobileWiFi。

iOS 26 与 16.5 在这条链上的差别本轮查过，没有实质变化：`IO80211.framework`、`MobileWiFi.framework`、`WiFiKit.framework` 都在；`wifid` 里 `IO80211SkywalkInterface` 的引用次数两版都是 1；`Falling back to IOCTL path` 这条格式串在 iOS 26 的 dyld 共享缓存里仍然存在（子缓存 `.60`）。也就是说 16.5 上「只带属性的两个注册表对象 + ioctl 回退」这套做法在 26 上仍然成立，但没在 26 上跑过。

### 2.4 第一步能验证的最小动作

三件，前两件不占真机：

1. **固定固件输入（离线，今天就能做）**：从分区备份解出 `image/kiwi/` 的候选文件，算出 SHA-256，写一个 `board-2.bin` 组装脚本，把 `amss20.bin`、`regdb.bin`（或 `regdb_xiaomi.bin`）、63 份板级数据整理成一个目录加一份清单。产出物进 `fw-wifi/` 之类的构建输入目录，不进仓库。
2. **iOS 侧的形状验证（QEMU，不占真机）**：给 `redwood_net` 加一个「无线但不出帧」的桩链路，用 boot-arg 开关（例如 `net_wireless=1`），让 QEMU 里的 en0 带 `wireless` 标记进 iOS 26，观察 wifid 是否走到 ioctl 回退、Settings 是否出现 Wi-Fi 开关、configd 是否给 en0 建了服务。这一步完全不碰 PCIe 与射频，却能提前暴露 iOS 26 对 `IO80211Controller` 属性的要求。代码量在几十行，因为 `struct redwood_net_link` 已经有 `wireless` 字段，virtio 链路只是没置位。
3. **apps SMMU 判读（需要真机，一次只读）**：阶段 6 已经在 `mhi_pcie.c` 里写好（映射 `0x15000000` 的全局页，只读 `SCR0`/`IDR0`/`IDR1`），尚未上机。建议在它上面加读 `GBPA`（全局 bypass 允许），因为它直接回答「没有匹配 SMR 的流会不会 fault」，也就是第一阶段能不能用物理地址做 BHI 下载。加一个寄存器读是这一阶段最小的增量，不碰 SMR/S2CR/context，也不碰 QTB。

这三件做完，Wi-Fi 的第一个未知（SMMU 的态度）就有答案，而 MHI 代码可以在等真机的窗口里离线写完。

### 2.5 代价量级

| 环节 | 需要真机 | 量级 |
|---|---|---|
| 固件输入固定与 `board-2.bin` 组装 | 否 | 1～2 天 |
| iOS 侧形状验证（QEMU 桩链路） | 否 | 1～2 天 |
| 阶段 6 加 `GBPA` 与全局故障状态，上机读一次（代码已提交 `caa71dc`） | 是 | 1 轮（约 3 分钟运行） |
| MHI host 最小子集 | 分阶段 | 2～3 周 |
| SID/SMMU 与 DMA 保留 | 是 | 1 周 |
| WLFW/QMI over QRTR-MHI | 是 | 1 周 |
| 数据面（Plan A 最小 WMI） | 是 | 2～6 周 |
| en0 挂接与 iOS 26 认口 | QEMU 先行 | 天级 |

真机窗口累计 4～8 周，与 [WCN7850 计划](../plan/wcn7850-plan.md) 第 4 节的估计一致。放弃条件沿用该文件第 5 节，本轮补一条：若阶段 6 读出 apps SMMU 对端点流量不放行、并且现有 context 已满或与显示等服务冲突、无法安全取得一个 context，则数据面暂停，先把「MHI 通、QMI 通」作为这一段的结果存档。

## 3. 蓝牙：五件事

### 3.1 需要哪些内核接口

- **电源与时钟**：6 路电源、`BT_EN`（pm8550ve_f 的 PMIC GPIO3）、`sw-ctrl`（GPIO18，与 WLAN 共享）、使能后的 50 ms 时序。投票路径已有先例：`mhi_pcie_power.c` 走 apps DRV2 的第 3 个 active 命令槽。BT 的开关脚在 PMIC 上，不在 TLMM 上，这一处是新代码。
- **SE14 GENI UART**：新增。可复用的部分不少：`redwood_goodix.c` 已经用 FIFO 轮询方式驱动 QUP 的一个 SE（时钟、复位、引脚组、`GENI_*` 寄存器序列），`annibale_battery.c` 有 QUP 引脚组的处理方式。UART 与 SPI 的差别在协议寄存器（`GENI_SER_M/CLK_CFG`、`UART_TX/RX`、中断状态）、波特率分频、以及 4 线流控（GPIO24/25 的 qup 功能与 RTS/CTS 使能）。目标速率 3 Mbaud 以上。
- **与 iOS 的传输接口**：两步。第一步只需要一个 `kern_control`，名字 `com.apple.uart.bluetooth`，实现 `TIOCGETA`/`TIOCSETA`（8N1 与流控）和读写；XNU 自带 `bsd/kern/kern_control.c`，但它在 arm64 内核配置里是否编入本轮没有核实（本机没有内核源码树）。第二步要 `com.apple.uart.sk.bluetooth` 的 Skywalk 通道，前人分析记录里说内核已编 `bsd/skywalk`，本轮同样没有复核；如果不想做 Skywalk 提供方，可以给 bluetoothd 设 `BT_HCI_TRANSPORT`，让它改用普通 socket 读写。
- **芯片侧 HCI**：固件下载用高通厂商命令（`0xFC00` 子命令 `0x19` 读版本、`0x1E` 分段写、`0x23` 读板号，`0xFC48` 改波特率），随后 `Reset`；这些在 `btqca.c` 里都有可直接对照的实现。带内睡眠字节（`0xFD`/`0xFE`/`0xFC`）与高通调试事件要过滤，否则会打乱 iOS 的 H4 解析。
- **身份层**（很可能必须）：按 `BlueTool` 表里的 Broadcom 身份回答 `Read_Local_Version`，并把 `0xFCxx` 命令一律答成功、丢弃载荷。理由是 3.3 节。

### 3.2 固件从哪里来

全部在机内 bluetooth 分区的 `image/` 下，命名规则已由 Linux 源码确认：

- `hmtbtfw20.tlv`（275,208 字节）、`hmtbtfw20.ver`（44 字节）、`hmtnv20.bin`（9,592 字节），另有 60 个板级变体 `hmtnv20.bXXX`（约 9.7 KB 一份）、`hmtbtfw20.mbn` 与 `brh*`/`gng*` 两个别的模组系列。
- `btqca.c` 对 `QCA_WCN7850` 依次取 `qca/hmtbtfw%02x.tlv`（`rom_ver` 为 `0x20`）与按板号拼出的 NVM 名 `hmtnv20.bXX`，与分区里的文件名完全对得上。板号通过 `0xFC00` 子命令 `0x23` 读回后再选文件。
- 分区的 `brh*`（Brimhall 一族）与 `gng*`（Ganges 一族）不属于本机，别混用。

结论：蓝牙固件完全在机内，命名与下载顺序都有公开源码可对照，这一侧没有未知。

### 3.3 iOS 侧哪个服务在等它（含 iOS 26 的重新核对）

等它的是 `bluetoothd` 与它拉起的 `BlueTool`。核对结果：iOS 26 的芯片表仍然只有 Broadcom，16.5 的阻塞在 26 上以另一种形式存在。

已确认的事实：

- `com.apple.BlueTool.plist` 还在，`MachServices` 为 `com.apple.BlueTool`，程序 `/usr/sbin/BlueTool -R`，`UserName` 为 `mobile`；`bluetoothd`、`bluetoothuserd`、`bluetoothuiservice` 的 plist 都在，`bluetoothd` 本体在 dyld 共享缓存里。
- 传输层多了 Apple 自己的 PCIe 路：`/usr/lib/AppleConvergedTransport.dylib` 的一套导出（`AppleConvergedTransportCreate/SendImage/Read/Write`）、`com.apple.BlueTool.pcie`、`ACIPCInterfaceTransport` 与 `IOSkywalkNexusUUID`、`apple_pcie` 传输、boot-arg `bt-transport-override`。这条路走的是 `IOServiceNameMatching("AppleOLYHAL")`，从设备树的 `HWIdentifiers`（键 `C` 与 `s`）拼出 `BCM%llu%s` 形式的芯片串（`276347` 映射到 `4377`），不经过 HCI 询问芯片。
- 老路仍然保留：`com.apple.uart.bluetooth` 控制套接字、`marconi-bt` 与 `bluetooth` 设备树节点、`transport-encoding`、`transport-speed`、`AppleBTHci`（`applebt_hci_*` 的 `IOConnectCallMethod` 序列）、Skywalk 读写通道、`MGCopyAnswer` 的 `ProductHash` 与 `WifiVendor`。
- 芯片表仍然只有 Broadcom：厂商命令处理器只有 `bluetool_command_broadcom`（`bluetool_command_hci`/`device`/`autobaud`/`power` 是通用命令），表里最新的名字是 `BCM4387C0/C2`、`BCM4388B0/C0/C2`，另有 `BCM4355C0/C1`、`BCM4377B2/B3`、`BCM4378B1/B3`、`BCM43430B1`。没有 Qualcomm 条目。
- 平台身份是 `ProductHash` 的 20 字节转成的 40 个十六进制字符；`getPlatform()` 扫 `kern.bootargs`，认三个固定覆盖值 `wifibt-external=0x442514e4`、`=0x443314e4`、`=0x443414e4`。脚本查找顺序是 HWModel 覆盖脚本、platform 覆盖脚本、`firmwareList` 内置脚本，都没有就报 `Error - no firmware for this platform`。
- 覆盖脚本的目录在日志里会被打印（`we are going to look for override script in %s`），但 iOS 26 的系统镜像里既没有 `/etc/bluetool` 也没有 `/usr/share/firmware/bluetooth`，脚本全部来自 `BlueTool` 内置数组（这也是它 5,255,248 字节的原因）。要加覆盖脚本就得往系统镜像里加目录，属于兜底手段。

由此得到结论与设计取向：

- 高通芯片报告的厂商号（推断 29）在表里没有条目，`BlueTool` 找不到固件与脚本，`bluetoothd` 会被反复重启。这一条 16.5 与 26 相同。
- 26 相比 16.5 多了两个可用点：芯片串可以来自设备树 `HWIdentifiers`，平台可以由 `wifibt-external=` 强制。身份因此有两处可以声明，HCI 的回答之外还有设备树这条。
- 反过来，硬件侧不需要冒充任何东西：内核把真实的 WCN7850 初始化好（UART、供电、固件下载、Reset 之后它就是一颗标准 HCI 控制器），再把「给 iOS 看的那一面」按表里的 Broadcom 身份回答，把 `0xFCxx` 命令吸收掉。真正作业的是高通固件，iOS 看到的是它认识的芯片。

还有一处未确认：26 的 `bluetoothd` 在找不到组合时的行为文本在共享缓存里没有搜到（16.5 的 `Unknown platform/chipset/manufacturer combination, restarting` 这一轮没在 26 的缓存里命中），所以「26 上一定反复重启」目前是按 16.5 的行为推断，未直接证实。这一条正好由 3.4 的第一轮实验一并回答。

### 3.4 第一步能验证的最小动作

这一步的目的只有一个：问出 iOS 26 要哪个传输、要哪个芯片串三元组。这两个答案决定后面所有设计——用 H4 还是冒充 AppleBTHci、身份在哪一层伪造、固件下载放在内核还是交给 `BlueTool` 的脚本。它比先写 UART 驱动重要，所以排在硬件之前。

26 里 PCIe 传输那一面的字符串是 `apple_pcie`、`com.apple.BlueTool.pcie`、`AppleConvergedTransport`、`ACIPCInterfaceTransport`，取芯片串走 `HWIdentifiers` 那条链。这套命名与 UART 那条路是两套东西，26 上究竟用哪一套由 `BlueTool` 自己按三元组决定，所以第一轮要把传输编号一起采下来。

先是两轮不碰蓝牙硬件的实验，都不改设备树，也不用给 BT 供电，因此没有挂死风险。第一轮即使一个字节都不回，也能拿到传输与三元组这两个答案。

1. **注册控制套接字并记录**：内核注册 `com.apple.uart.bluetooth` 的 `kern_control`（构建机已确认它编进了 arm64 配置），`TIOCGETA`/`TIOCSETA` 正常应答，读到的字节全部打进日志、不回包；代码已提交（内核仓 `baa499c`，之后 `a48a496` 让连接与断开行带上累计计数、`01bc649` 去掉 16.5 线没有的 `ctl_enable`、`fc9c340` 每十秒打一行累计值、`1133be5` 打真实秒数、`eb7287b` 去掉 `ctl_bind` 回调，boot-arg `bt_probe=1`）。两棵树的差别：16.5 线 `xnu-8796.121.2` 的 `<sys/kern_control.h>` 直接给出 `ctl_bind` 等字段；设备真机用的 26 线 `xnu12377` 把这类字段放在 `<sys/kern_control_private.h>` 的 `KERNEL_PRIVATE` 段，公开结构里没有 `ctl_bind`，所以探针不注册 bind 回调（BlueTool 走 socket → `CTLIOCGINFO` → connect，`ctl_connect` 不需要它）。`eb7287b` 用 26 线 `BUILD/obj` 下的编译命令实测：本文件 0 warning 0 error，目标文件的 13 个未定义符号在同树已链接内核里全部能找到，套接字按 `BlueTool` 反汇编里读出的样子注册：`socket(PF_SYSTEM, SOCK_STREAM, SYSPROTO_CONTROL)`，用 `CTLIOCGINFO` 按名字取 ID 后 `connect`，`sc_unit` 为 0；boot-arg 把传输强制到 H4（`bt-transport-override`），payload 里放开 `bluetoothd` 与 `BlueTool`（`userland/mkjobs.py` 的 `DENY` 里有 `bluetooth` 与 `BTServer`）。这一轮的行数与时机要先跟 device 说清：探针在 BlueTool 与 bluetoothd 启动的头几秒出日志，而串口环在忙的时候只装得下约 15 秒（日志量约 65 KB/s，环 1 MB，快照 20 秒一次），所以探针另外每十秒打一行累计值，前十次 10 秒间隔、之后每分钟一行；即使一个客户端都没连、即使首发被挤掉，后面快照里仍能看到「探针起没起、有没有人连、发了多少字节」。一轮总量在 4 KB 以内（启动 1 行、每个客户端会话 6～10 行、累计行若干），连接与断开行也带累计计数。跑一轮，要采四个答案：`BlueTool` 实际选的传输编号、它要的三元组（platform/chipset/manufacturer）、覆盖脚本目录的实际路径、以及 26 的 `bluetoothd` 在组合未知时是退出重启还是继续。前两个决定后续设计，后两个决定要不要改系统镜像。
2. **第二轮再回包**：内核按表里的 Broadcom 身份回答 `Reset` 与 `Read_Local_Version`，对其余命令答成功，看 `bluetoothd` 是否活下来、随后的 HCI 序列长什么样。

第三轮才碰硬件：SE14 上电、读 `0xFC00`/`0x19` 的芯片版本与 `0x23` 的板号，与分区里 `hmtbtfw20.ver` 对照，确认载体选对了。

### 3.5 代价量级

| 环节 | 需要真机 | 量级 |
|---|---|---|
| 控制套接字 + 记录一轮 | 是（无硬件风险） | 1～2 天代码 + 1 轮 |
| 身份代理（Broadcom 身份、吸收 `0xFCxx`） | 是 | 1 周，含试错 |
| SE14 UART + BT 供电与开关脚 | 是 | 1 周 |
| 固件下载与 `Reset`、读版本 | 是 | 3～5 天 |
| `bluetoothd` 传输（Skywalk 通道或 `BT_HCI_TRANSPORT`） | 是 | 1～2 周 |
| 蓝牙音频 | — | 另算，依赖 ADSP，暂缓 |

硬件通 2～3 周，iOS 侧接受再 1～2 周。第一步的两轮不需要硬件，也不占真机，值得先做。

## 4. 依赖顺序与真机需求

| 步骤 | 项目 | 需要真机 | 前置 | 判据 |
|---|---|---|---|---|
| W0 | 固定 Wi-Fi 固件输入、组装 `board-2.bin` | 否 | 分区备份 | 目录 + SHA-256 清单；`board-2.bin` 能被自己的解析脚本读回 |
| W1 | QEMU 里让 en0 带 Wi-Fi 形状 | 否 | 与 W0 无依赖，可并行 | wifid 进 ioctl 回退；Settings 出现 Wi-Fi；configd 建服务 |
| W2 | 阶段 6 加 `GBPA` 与 GFSR 并上机只读（`caa71dc`） | 是 | 现有 `pcie_power=1` 路径 | 打出 SCR0／GBPA／GFSR／GFSYNR0／GFSYNR1 且非 `0xffffffff`；SMMU 对本端点放行与否有结论 |
| W3 | RID→SID 或 S2CR 处理 + 首个 BHI 下载 | 是 | W2 放行结论 | BHI 提交后 `MHI_EXECENV` 从 PBL 变化 |
| W4 | WLFW QMI over QRTR-MHI | 是 | W3 | QMI 服务枚举出 WLFW，`init done` |
| W5 | 数据面最小 WMI 与 en0 | 是 | W4 | 扫到 AP 并关联 |
| B0 | 控制套接字记录一轮 | 是 | 无 | 日志里有 `BlueTool` 的完整请求序列 |
| B1 | 身份代理 | 是 | B0 | `bluetoothd` 不再退出 |
| B2 | SE14 UART + 供电 + 读版本 | 是 | 无，可与 B0、B1 并行 | `0xFC00`/`0x19` 与 `hmtbtfw20.ver` 对得上 |
| B3 | 固件下载 + `Reset` | 是 | B2 | `Read_Local_Version` 返回厂商号 29 |
| B4 | `bluetoothd` 传输打通 | 是 | B1、B3 | 协议栈初始化命令走完 |

两项都需要真机，但各自第一个要真机的动作（W2、B0）前面都有不需要设备的活。Wi-Fi 的离线段更长，蓝牙的第一步更容易排进真机窗口。

## 5. 本轮依据与未确认项

### 5.1 依据

- 分区备份：`annibale-backup/20261022-2355` 的 `modem_a` 与 `bluetooth_a`，用 7-Zip 读 FAT 目录树，只取文件名与尺寸，没有解出固件内容到仓库。
- Linux 源码（本轮通过 curl 取主线文件，未入库）：`drivers/bluetooth/btqca.c`（WCN7850 的固件命名与下载分支）、`drivers/bluetooth/hci_qca.c`（速率、时序、流控）、`drivers/net/wireless/ath/ath12k/wifi7/hw.c`（`wcn7850 hw2.0` 的固件目录与 M3 loader）、`hw.h`/`core.c`/`qmi.c`/`mhi.c`（`amss.bin`/`m3.bin`/`board-2.bin` 命名、board 名构造、`sbl_size`/`seg_len` 512 KiB、M3 的物理地址上交）。
- iOS 26 用户态：`usr/sbin/BlueTool` 的字符串与 IDA 反编译（`getPlatform`、`HWIdentifiers` 芯片串、`firmwareList`、覆盖脚本顺序）、`usr/sbin/wifid` 与 16.5 的字符串对比、`System/Library/LaunchDaemons` 下相关 plist、dyld 共享缓存里 `Falling back to IOCTL path` 的命中。
- 构建机核对（device 在 `kbuild` 里读 `bsd/conf/files`、构建目录与链接后的核）：`kern_control` 编入 arm64 配置（`optional networking`，`DEVELOPMENT` 带 `networking`），`bsd/skywalk` 只有 `skywalk_stubs.c`、真实实现要 `option skywalk` 而配置里没有。蓝牙只能走控制套接字。
- 现有内核代码：`mhi_pcie.c`（阶段 1～6）、`mhi_pcie_power.c`、`redwood_net.c`、`redwood_apple80211.c`、`RedwoodWLAN.cpp`、`redwood_goodix.c`（GENI SE 的轮询式驱动）、`redwood_virtio_net.c`。

### 5.2 未确认

- apps SMMU 的当前状态与 `GBPA`（未读）；端点事务实际带的 SID。
- 机内 `amss.bin`/`amss20.bin` 是否已包含 M3；`Data20.msc` 的用途；63 份 `bdwlan.*` 里哪一份对应本机板号。
- iOS 26 `BlueTool` 的 `firmwareList` 里是否有任何条目能与 UART 上的 Broadcom 身份配对；三个 `wifibt-external=` 值分别对应哪个平台。B0 一轮会打印出来。
- iOS 26 `bluetoothd` 在组合未知时的行为（按 16.5 推断，未在本版证实）。
- 蓝牙 HCI 载体仍是推断为 SE14 UART：依据是 Linux 主线对 WCN7850 用 `hci_qca` 走串口、固件命名与机内分区完全吻合、设备树把 SE14 作为 `hsuart0` 暴露。设备树没有写死载体，MHI 承载 HCI 的可能没有排除，B2 会给出答案。

## 6. 要动的文件

本文的结论先落地了两件不需要设备的事：固件解出与 `board-2.bin` 组装写成了 `tools/mk-fw-wifi.py`（内核仓库 `3ca5057`），iOS 侧的 Wi-Fi 形状验证写成了 `net_wireless=1` 的桩链路（内核仓库 `ad80074`）。其余改动还没开始，下面按依赖排在前面的动作列出会碰到的文件。

| 动作 | 文件 | 性质 | 备注 |
|---|---|---|---|
| W0 固件整理与板级数据转换 | `tools/mk-fw-wifi.py`（已提交 `3ca5057`）：`list`、`extract` 出清单与 SHA-256，`board2` 按 ath12k 的 API 2 格式包 `board-2.bin` 并读回校验 | 已做 | 板级数据选哪份要等 QMI 回报 board-id |
| W1 桩链路 | `xnu/files/bsd/dev/redwood_net.c`（已提交 `ad80074`）：boot-arg `net_wireless=1`，wireless 置真的空链路，`net_wireless_up=1` 才拉起 | 已做，未编译 | 本工作区没有内核源码树，要等构建机；QEMU 用 `net_wireless=1` 验 |
| W2 SMMU 判读 | `xnu/files/bsd/dev/mhi_pcie.c` 阶段 6 加读 `GBPA` 与 `GFSR`／`GFSYNR0`／`GFSYNR1`（已提交 `caa71dc`） | 已做，未编译 | 只读，仍是 `pcie=6`；要等构建机 |
| W3 起 MHI | 新增 `xnu/files/bsd/dev/annibale_mhi.c`（按 BHI/通道/状态机分文件或 `.inc` 分片）与 `bsd/sys/` 下对应头文件 | 新增 | 单文件控制在 1200 行内 |
| W4 起 QMI | 新增 `redwood_mhi_qrtr.c`，`redwood_qmi.c` 与 `redwood_wlfw.c` 换传输 | 改 + 新增 | 编解码复用 |
| B0 控制套接字 | `xnu/files/bsd/dev/redwood_bt_probe.c`（已提交 `baa499c`；`redwood_input.c` 加一次调用，`bsd/conf/files` 的补丁加一行） | 已做，未编译 | boot-arg `bt_probe=1`，注册两个名字，只记录不回包 |
| B0 放开守护进程 | `hackios-xnu-userland/userland/mkjobs.py` 的 `DENY`（16.5 路径）与 `tools/k90auto/package.py` 的任务清单（26 路径） | 小改 | 两个 payload 都要放 `bluetoothd` 与 `BlueTool` |
| B2 起 UART | 新增 `annibale_bt_uart.c`，复用 `redwood_goodix.c` 的 QUP SE 初始化 | 新增 | 供电与 `BT_EN`（PMIC GPIO3）另算 |