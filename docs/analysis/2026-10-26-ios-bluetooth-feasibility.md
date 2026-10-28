# iOS 蓝牙接入可行性（静态分析，2026-10-26）

本文记录 iOS 16.5（20F66）`BlueTool`、`bluetoothd` 的静态分析，以及 WCN7850 蓝牙在 Linux 上的启动要求，用于判断 K90 的高通蓝牙控制器能否交给 iOS 使用。分析对象为 `hackios-xnu-kernel/ios165/rootfs` 中的 `usr/sbin/BlueTool`、`usr/sbin/bluetoothd`（字符串与 IDA 反编译）和分区备份 `annibale-backup/20261022-2355/bluetooth_a.img.gz`，没有真机运行。标注「推断」的内容没有直接证据。

系统目标已改为 iOS 26、iPhone 17 身份（[路线图](../plan/2026-10-26-roadmap.md)第 3 节）。iPhone 17 使用的蓝牙芯片和传输方式与 iPhone X 不同，下文 iOS 侧的结论需要在 iOS 26 上重新核对。

## 1. iOS 16.5 启动蓝牙控制器的流程

- `bluetoothd` 开机启动，异常退出后由 launchd 重启。它通过 XPC 请求 `BlueTool`（Mach 服务 `com.apple.BlueTool`，以 `BlueTool -R` 运行）执行 `boot`、`init` 或 `deepsleep` 脚本，`BlueTool` 返回 `result`、`firmware` 和 `manufacturer`。
- 两个进程从 IORegistry 中名为 `marconi-bt`（其次 `bluetooth`）的设备树节点读取 `transport-encoding`：0 USB、1 H4、2 H4DS、3 H4BC、4 H5、6 APPLEBT（IOKit `AppleBTHci`）、7 PCIe。环境变量 `BT_HCI_TRANSPORT` 可以覆盖。
- UART 传输不经 tty 设备。`BlueTool` 打开 `PF_SYSTEM` 控制套接字 `com.apple.uart.bluetooth`，用套接字选项 `TIOCGETA`／`TIOCSETA` 设置 8N1 和 RTS／CTS 流控，默认 115200，`-S` 时取设备树 `transport-speed`。
- `bluetoothd` 默认打开 `com.apple.uart.sk.bluetooth`，并要求通过 Skywalk 通道收发（套接字选项 `0x800C7414`、`0x40107412` 后 `os_channel_create`），失败即打开失败。只有 `BT_HCI_TRANSPORT` 指定设备名时才用普通 `read()`／`write()`。
- 芯片选择：平台取 MobileGestalt `ProductHash`（或启动参数 `wifibt-external=`），芯片取 HCI Read_Local_Version 的厂商号与 LMP 子版本（厂商 15、子版本 0x6103 为 `BCM4355C0`，厂商 76 为 Apple），模组厂商取 MobileGestalt `WifiVendor`。三者在 `BlueTool` 内置表中查到条目后，执行对应脚本并下载内置的 `.hcd` 固件。
- iPhone X 推断为 Broadcom BCM4355C0（UART）。启动脚本使用 Broadcom 厂商命令：0xFC18 改波特率、0xFC2E／0xFC4C 下载固件、0xFC01 写地址、0xFC27 设置睡眠模式。

## 2. 初始化之后的命令

- 协议栈初始化使用标准 HCI 命令：Reset、Read Local Version、Supported Commands、BD_ADDR、各类 Features、事件掩码、SSP、LE Host Support、缓冲区大小、LE States 等。Reset 失败和不支持 Host Flow Control 都会被忽略。
- 厂商命令按芯片编号启用：1～1999 为 Broadcom 表（共 219 条，涉及睡眠、SCO 路由、宽带语音、LE 多广播、共存等），2000～3999 为 Apple 表，0（`THIRD_PARTY_DONGLE`）不启用厂商命令。不支持的命令记录「not implemented for current chipset!」。
- 直接失败的情况：`BlueTool` 查表无结果时，`bluetoothd` 记录「Unknown platform/chipset/manufacturer combination, restarting」并以 `_exit(1)` 退出，随后被反复重启；`BlueTool` 无应答或 `local-mac-address` 全为 0 时同样退出。

## 3. WCN7850 蓝牙在 Linux 上的启动

- 传输为 UART（`qcom,wcn7850-bt`），MHI 只承载 WLAN。SM8750 MTP 的上游补丁与社区移植都使用 uart14，BT_EN 为 pm8550ve_f GPIO3，与本机设备树一致，对应 SE14（`0x898000`）。
- 上电：6 路电源（vddio、vddaon、vdddig、vddrfa0p8／1p2／1p9），BT_EN 拉低 50 ms 再拉高 50 ms，sw-ctrl 为 GPIO18。
- 固件下载使用高通厂商命令：0xFC00 子命令 0x19（读版本）、0x1E（分段下载补丁与 NVM，每段 243 字节）、0x23（读板号），0xFC48 改波特率，最后发 HCI Reset。
- 备份分区中有 `image/hmtbtfw20.tlv`（`BTFW.HAMILTON.2.0.1-00450-PATCHZ-1.131051.2`）、`hmtnv20.bin` 和约 60 个板级变体 `hmtnv20.bXX`，与 Linux `btqca` 的命名一致。
- 交给 iOS 之前，内核需要完成：电源、时钟与引脚；SE14 GENI UART（RTS／CTS，3 Mbaud 以上）；上述固件下载；带内睡眠字节（0xFD／0xFE／0xFC）的处理和高通调试事件的过滤（推断这些字节会打乱 iOS 的 H4 解析）。

## 4. 结论与最小实验

高通控制器完成上述初始化后提供标准 HCI，`bluetoothd` 的协议栈初始化可以使用。阻塞点在 iOS 侧：

1. `BlueTool` 只启动内置表中的芯片。高通控制器推断报告厂商号 29，查不到条目，`bluetoothd` 会反复重启。可选做法是内核在 `BlueTool` 会话期间按表中芯片回答 Read_Local_Version，并对其厂商命令直接返回成功、丢弃固件；或改动 MobileGestalt `ReleaseType` 使 `/etc/bluetool` 下的覆盖脚本生效（副作用未知）。
2. `ProductHash`、`WifiVendor` 在本系统上能否解析未核对。
3. `com.apple.uart.sk.bluetooth` 需要 Skywalk 通道；内核已编译 `bsd/skywalk`，可以实现对应的提供方，另一条路是在用户态配置中设置 `BT_HCI_TRANSPORT`。
4. 冒充 Broadcom 芯片后 `bluetoothd` 会在运行中发送 Broadcom 厂商命令；芯片编号为 0 时不发送，最终取到哪个编号未核对。
5. 语音（SCO 路由）与共存相关的厂商命令有风险；蓝牙音频还依赖尚未实现的 ADSP 音频链路。

不需要蓝牙硬件的最小实验：在设备树加入带非零 `local-mac-address`、`transport-encoding=1`、`transport-speed=3000000` 的 `bluetooth` 节点，内核注册上述两个控制套接字（允许 mobile 用户连接），支持 `TIOCGETA`／`TIOCSETA`，记录收到的全部字节，读取 `BlueTool` 与 `bluetoothd` 的日志；第二轮由内核按表中芯片回答 Reset 和 Read_Local_Version、确认全部 0xFCxx 命令，记录 `bluetoothd` 随后发送的内容。`bluetooth`、`BTServer` 当前在 `userland/mkjobs.py` 的 `DENY` 列表中，实验前需要放开。

未确认：`BlueTool` 是否在发送 Read_Local_Version 前打开 UART；MobileGestalt 如何计算 `ProductHash`。

参考：Linux [btqca.c](https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btqca.c)、[hci_qca.c](https://github.com/torvalds/linux/blob/master/drivers/bluetooth/hci_qca.c)。
