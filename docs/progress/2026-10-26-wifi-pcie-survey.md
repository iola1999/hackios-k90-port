# K90 Wi-Fi：PCIe 根复合体 0 勘察与上电（2026-10-26）

`bsd/dev/mhi_pcie.c` 的只读勘察（`pcie=N`）第一次在 K90 上运行。计划与步骤划分见 [WCN7850 计划](../plan/wcn7850-plan.md)第 4 节。原始日志保存在 Git 忽略的 `docs/progress/evidence/2026-10-25-codex-gpu-resume/`，下文用目录名指代各轮运行。

## 1. 结论

- 内核启动时 PCIe 根复合体 0 没有上电：两个电源域关闭，6 个时钟都停着；WCN7850 的使能脚 GPIO16 和 PERST（GPIO102）都是未驱动的输入，读数为 0。启动固件没有初始化 RC0，Wi-Fi 第 0 步需要从电源、时钟、PHY 到 PERST 完整上电。
- 前四轮的失败来自读引脚寄存器的基址错误，与 PCIe 无关。修正后勘察正常结束，同一轮桌面正常运行，没有 panic。
- 内核 `0fa0f40` 起，`pcie_power=1` 按主线 Linux 的做法给 RC0 和网卡上电，链路进入 L0（Gen1 x2），配置空间读出 `0x17cb:0x1107`；`fadb3a2` 起分配 BAR0 并读到网卡的 MHI 寄存器，状态为 RESET（第 4 节）。

## 2. 各轮结果

| 运行 | 内核 | 参数 | 结果 |
|---|---|---|---|
| `kernel-pcieguard-s23-auto-pcie1` | `474d6e9` | `pcie=1` | 启动约 8 s 后 USB 无应答，日志中没有勘察输出，设备回到 Android B 槽后自动恢复 loader |
| `kernel-pcie2-s23-auto-pcie2` | `32bbef4` | `pcie=2` | 启动约 8 s 后 USB 无应答，日志中没有勘察输出，USB 复位后直接回到 loader |
| `kernel-pcie3-s23-auto-pause` | `7e54fac` | `pcie=1 pcie_pause=15` | 映射和时钟控制器读取完成，宣布读取引脚后停止 |
| `kernel-pcie4-s23-auto-pins` | `76c1ad6` | `pcie=1 pcie_pause=8` | 宣布读取 GPIO16 后停止 |
| `kernel-pcie5-s23-auto-pins` | `82b475c` | `pcie=2 pcie_pause=5` | 勘察完成，运行 150 s 正常结束 |

- `474d6e9` 起，只有两个电源域都开、cfg_ahb／slv_axi／mstr_axi／aux 四个时钟都在运行时才读 RC0 的 parf、PHY、DBI 寄存器。读未上电或未供时钟的模块可能让 SoC 挂死，USB 无法恢复。
- `pcie_pause=N` 在每个读取阶段前先打印下一步，再等待 N 秒，主机每 4～5 s 拉一次日志，用最后一行定位停住的位置。
- 停止原因：勘察按原厂设备树的 `tlmm` reg 把引脚寄存器基址设为 `0xf000000`，K90 的引脚寄存器在 `0xf100000`（主线 `sm8750.dtsi`，`redwood_goodix.c` 的 `board_setup()` 也用这个地址）。`0xf000000 + 16 × 0x1000` 处的读取让 SoC 停止。`82b475c` 改用 `0xf100000`。

## 3. 读数（`kernel-pcie5-s23-auto-pins`）

- 电源域：`gcc_pcie_0_gdsc` 为 `0x0222f801`，`gcc_pcie_0_phy_gdsc` 为 `0x02222801`，bit 31 为 0，均关闭。
- 时钟：cfg_ahb、slv_axi、mstr_axi、aux、slv_q2a_axi、pipe 的 CBCR 均为 `0x88000000`，CLK_OFF 置位。
- 引脚（拉电阻按 `msm_gpio` 编码：1 下拉、2 保持、3 上拉；`e7246d0` 前的日志把 1 显示为上拉，3 显示为保持）：GPIO16、18、19、102 为普通 GPIO、输入、下拉，读数 0；GPIO103（CLKREQ）为普通 GPIO、上拉，读数 1；GPIO104（WAKE）为普通 GPIO、下拉，读数 1。

## 4. 上电与链路（`pcie_power=1`）

原厂内核在 SM8750 上通过 CESTA 和 PCIe 状态机管理 RC0 的时钟和电源，设备树的 RC0 节点没有时钟和电源属性。内核 `0fa0f40` 新增 `bsd/dev/mhi_pcie_power.c`，按主线 Linux 的做法直接上电：`pcie-qcom.c` 的 `cfg_1_9_0`（sm8750 回落到 `qcom,pcie-sm8550`）、`phy-qcom-qmp-pcie.c` 的 sm8750 gen3x2 PHY、`gcc-sm8750.c`、`pwrseq-qcom-wcn.c`；电源和 PHY 取值来自原厂设备树。逐步来源列在本地证据目录 `wifi-pcie-plan/powerup-steps.txt`。顺序：

1. 读 GPLL0 锁定、RSC 版本，在 cmd-db 中查 11 个 RPMh 资源并确认都标为 VRM。
2. PERST（GPIO102）与网卡使能（GPIO16）先输出低电平。
3. 经 apps DRV2 的第 3 个 active 命令槽（TCS2；TCS0 由触摸驱动使用，TCS1 由 adreno8 使用）投票：PHY 的 L1F 880 mV、L3G 1200 mV；网卡的 L3F 1800、L2F 1200、L6K 1800、S5F 932、S4D 976、S1D 976、S3G 1864、S7I 1316 mV；网卡晶振 `rfclka1`。每个电压先与设备树中调节器范围和网卡范围的交集比对，超出即不发送。
4. 两个电源域、aux 19.2 MHz 与 rchng 100 MHz、参考时钟和各分支时钟；核心与 PHY 复位；PARF；原厂 PHY 序列 126 项、pipe 时钟、PHY 启动。
5. 网卡使能拉高，CLKREQ 与 WAKE 切到对应功能；根端口头部，链路目标速率限为 Gen1；使能后 100 ms 释放 PERST，开始链路训练。

| 运行 | 内核 | 结果 |
|---|---|---|
| `kernel-pciepower-s23-auto-power1` | `0fa0f40` | 11 个资源都找到；电源投票、电源域、时钟、PHY 都成功；网卡使能后 sw-ctrl 两脚读到 1；释放 PERST 后 90 ms 内进入 L0。根端口报告 Gen1 x2。配置空间读出 `0x17cb:0x1107`（类 `0x028000`），BAR0 为 2 MiB 64 位内存 |
| `kernel-pciebar-s23-auto-bar0` | `91e559d` | BAR0 写 `0x40300000` 读回 `0x40200000`：BAR 只保留高于其大小的地址位 |
| `kernel-pciebar2-s23-auto-bar0` | `fadb3a2` | BAR0 分配到 `0x40400000`，根端口内存窗口与出站 iATU 区域 1 覆盖它，读到网卡的 MHI 寄存器 |

`kernel-pciebar2-s23-auto-bar0` 的 MHI 寄存器：MHIREGLEN `0x100`，MHIVER `0xdeadbeef`，MHICFG `0x00800080`，通道门铃偏移 `0x300`，事件门铃偏移 `0x700`，BHI 偏移 `0x100`，BHIe 偏移 `0x224`，MHISTATUS 为 0（RESET）。三轮桌面都正常运行，结束后回到 loader。

## 5. BHI 执行环境与 SID 读取（2026-10-27）

`pcie=5` 已完成一次 K90 真机读取。内核为 XNU `12377.121.6`，SHA-256 `41888cad8bbc3ba9fa05959a9cf0d987e3e7191b51cd6fded3ebbddcf510c908`；载荷 SHA-256 `a06d6154823e042894c9e1b156683824cbe269cf3a79b55a1b32bcd7dce6ee82`。配置为 `pcie=5 pcie_power=1 pcie_pause=2 cpus=1 bootcpu=7 small_cores_after=0 rootdev=md0 loader_return_after=120`，GPU、触摸、按键、电量、CPU 调频及其他可选外设诊断关闭。载荷使用 4 MiB 最小根盘，resident 系统盘为空。原始参数、输入与回读在本地 `hackios-xnu-kernel/out/ios26-resume/wifi-stage5-ready/`，设备命令和日志在相邻 `wifi-stage5-device/`。

Stage 5 源码此前已通过 8796／12377 构建；本轮先用独立 QEMU 载荷显式设置 `pcie=0 pcie_power=0`，验证静态 PID 1 等待和 20 秒限时返回，再执行真机读取。真机阶段输出完整，120 秒返回后完成软件复位，重新读到 fresh loader。QEMU 只验证最小根盘与返回路径。

| 项目 | 本轮实测 |
|---|---|
| 链路与端点 | Gen1 x2，端点 `0x17cb:0x1107`，revision `0x1` |
| BAR0 | `0x40400004`，2 MiB 64 位内存；根端口窗口 `0x40400000..0x405fffff`，command 低 16 位为 `0x0006` |
| MHI | `MHIREGLEN=0x100`、`MHIVER=0xdeadbeef`、`MHICFG=0x00800080`、`MHICTRL=0`、`MHISTATUS=0`（RESET）；BHI 偏移 `0x100`，BHIe 偏移 `0x224` |
| BHI | `EXECENV=0`（PBL），`STATUS=0`，`ERRCODE` 与 `ERRDBG1..3` 全部为 0 |
| BHIe | `TXVECSTATUS=0x8aa6c915`，高两位为 2，sequence 为 `0x0aa6c915` |
| PARF | `BDF_TO_SID_CFG=0x1`，bypass=1；RID `0x100` 的 CRC8 索引为 `0x15` |
| SID 表读取 | 从索引 `0x15` 读取 22 个不同表项，最后由 `0x91` 指回已读的 `0x6e`，诊断按重复索引停止；这些表项未出现 RID `0x100` |

MHI RESET 和 PBL 可以同时出现。日志中旧文案「nobody powered its bus up」不能解释本轮状态：同轮 GDSC、时钟和链路均已开启。本轮读取确认了 PBL 及当前 BHI 状态，固件下载尚未执行。

MiCode 快照 `f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea` 的 `drivers/bus/mhi/common.h` 把 BHIe 状态 2 定义为 `XFER_COMPL`。本轮没有提交 BHIe 地址、向量或门铃，初始非零状态的来源仍待确认；后续下载必须关联本轮提交和执行环境变化，不能仅以这个初始值验收。BHI 错误字段为 0 只覆盖本次读取时点。重复的串行输出与返回日志中的再次输出来自同轮采集，不能按多次独立硬件试验计数。

SID 诊断重查供电、时钟、链路、端点和 BAR 范围；BHI／BHIe 读取限制在 BAR0 已映射的首个 4 KiB。PARF 只读 `+0x2c00` 以及 RID `0x100` 的冲突链，未遍历其他表项。配置寄存器的 bypass 位为 1，表内环链没有证明当前 DMA 使用这些项；实际送入 apps SMMU 的 SID 尚未读取或验证。本轮 SID 转换未通过验收。

`pcie_power=1` 包含此前已经实测的电源、时钟、PHY、GPIO、BAR 和 iATU 写入，也启用端点 bus mastering。新增 stage 5 只读取状态，没有配置 SID、SMMU、固件 DMA 或 MHI 门铃。普通返回保留 PCIe 上电与 BAR 配置，所以本轮保存日志后完成了软件冷复位。

## 6. SID、apps SMMU 与固件下载前置

下一步先确认 PCIe 端点到内存的地址转换，再实施 BHI 下载。静态来源包括上述 MiCode MHI／ath12k 源码、本地主线 `sm8750.dtsi`／`pcie-qcom.c` 及厂商 `pci-msm.c`。本轮摘录、来源文件和 SHA-256 保存在 Git 忽略的 `hackios-xnu-kernel/out/ios26-resume/wifi-stage5-analysis/`，没有增加设备读取。

1. **确认 apps SMMU 可访问范围和占用。** 主线设备树把 RID `0`／`0x100` 映射到 SID `0x1400`／`0x1401`。本地厂商设备树 `msm-arm-smmu-sun-mi.dtsi` 定义 apps SMMU 为 `0x15000000+0x100000`，PCIe QTB 为 `0x016cd000+0x1000`，覆盖 SID `0x1400..0x17ff`，IOVA 宽度 32 位。该节点还带有 `qcom,opt-out-tbu-halting`。先核对 K90 当前供电、时钟与非安全访问权限，再设计有界读取：SMMU 标识／配置、覆盖目标 SID 的 SMR／S2CR 以及匹配 context 的配置和故障状态。已有 `redwood_wifi.c` 的 `wifi_smmu=1/2` 使用 WCN6750 的 SID `0x1c00`／mask 1，不能直接用于本机。不得重置共享 apps SMMU 或覆盖显示等已有 context；QTB 停止操作也需另查该属性的驱动处理。
2. **准备 RID→SID 表配置及读回。** `qcom_pcie_config_sid_1_9_0()` 与厂商 `msm_pcie_config_sid()` 都先关闭 BDF_TO_SID bypass，清零 256 项，再按 CRC8-MSB／多项式 `0x07` 写入 `RID[31:16] | relative_SID[15:8] | NEXT[7:0]`。SID base 为 `0x1400` 时，RID `0x100` 的无冲突表项是索引 `0x15`、值 `0x01000100`。这给出后续实现的格式，尚未执行本机写入。写入前必须确认端点没有活动 DMA、表归属及失败恢复，并在独立阶段读回配置和目标项；仅清除 bypass 会使当前未通过校验的表参与转换，不能单独作为修复。
3. **建立有限 DMA 映射与保留状态。** 先确认空闲 SMR／context、输出物理地址宽度、页表格式、TLB／缓存维护和实际 IOVA 范围。PCIe QTB 的 32 位 IOVA 限制需与原厂 geometry／fastmap 范围求交；K90 的高位物理 RAM 需要有效地址转换，不能截断后提交。现有 loader 的 GPU held 保护没有覆盖新 MHI 缓冲；首个下载门铃之前，应让停止、超时、panic 和正常返回都保留仍可能被设备访问的页与映射，直到确认停止或完成复位。
4. **固定固件输入，再按 BHI／BHIe 分阶段验证。** ath12k 为 WCN7850 设置 `sbl_size=512 KiB`、`seg_len=512 KiB`、`fbc_download=true`。先把同一 `amss.bin` 的前 `min(512 KiB, 文件长度)` 放入可 DMA 访问的缓冲，经 BHI 提交；确认提交后的状态和 PBL→SBL／READY 变化，再准备 BHIe 向量。该 ath12k 路径未设置 `tme_supported_image`，默认 BHIe 复制完整映像；厂商 MHI 的 TME 可选分支会跳过首个 SBL 段，选择其他控制器路径时需重新核对。固件目录为 `ath12k/WCN7850/hw2.0/`，后续还需 `m3.bin`、匹配 K90 板级标识的 `board-2.bin` 和 `regdb.bin`。先固定版本、长度、SHA-256、芯片硬件版本和 BDF；当前没有已核验的本机固件输入。

## 7. apps SMMU 只读访问条件（2026-10-27）

离线核对确认 apps SMMU 基址为 `0x15000000`、范围 `0x100000`，PCIe QTB 覆盖 SID `0x1400..0x17ff` 且设备树声明 IOVA 宽度为 32 位。SM8750 通用设备树与本地厂商设备树没有为 apps SMMU 节点列出 `clocks`、`clock-names` 或 `power-domains`；通用节点列出了全局与每 TBU/context fault 中断，厂商节点带有 `qcom,handoff-smrs=<0x800 0x2>`。这些静态字段没有给出当前启动期间 SMMU 可安全读取的寄存器条件。

`redwood_camera.c`、`redwood_sound.c` 和旧机型 `redwood_wifi.c` 都读取 `0x15000000` 的标识与 SMR／S2CR；前两者在各自驱动路径中调用，旧 Wi-Fi 驱动针对 SID `0x1c00`。这些调用没有证明 K90 的 `pcie=5` 启动阶段中 apps SMMU 已供电、时钟可用且非安全访问获准。PCIe 阶段 2 现有的 `show_power()` 只核对 RC0 电源域及其时钟，不能作为 apps SMMU 的访问门禁。

阶段 6 已加入 `mhi_pcie.c`，只映射 `0x15000000+0x100000` 的 apps SMMU 窗口，并读取全局页的 SCR0、IDR0 和 IDR1；进入前检查 PCIe 电源与链路状态以及已知端点身份。该实现不会扫描 SID、SMR、S2CR 或 context。XNU 12377.121.6（`DEVELOPMENT_ARM64_BCM2837`）主机构建通过，`mhi_pcie.o` 的 SHA-256 为 `e77dbb3bd4e2140308fbdb20ef4846d70d00a2ed3a0e7999f5a25896142a9d75`，内核 SHA-256 为 `fe37c30d2c900297d915802ccbbd0a9e5452c51cb08de03ca74d5a7146fa9198`。该载荷尚未在 K90 上运行。现有设备静态来源仍未说明 apps SMMU 在当前启动期间可安全读取的条件，因此不得据此宣称访问安全。

下一步先从 SM8750 电源控制、固件启动状态与访问控制来源确认 SMMU 可读条件，再审核阶段 6 的映射、门禁和寄存器偏移。只有阶段 6 在设备上成功读取并保存读数后，才评估 SID `0x1401` 的 SMR／S2CR 与匹配 context 的只读检查。不得写 apps SMMU、停止 PCIe QTB、改变 bypass 或提交 DMA。本轮没有在 K90 上执行阶段 6，访问条件与读数仍未实测。

每一阶段分别记录预期状态、实际读回、超时与资源释放条件。BHIe、MHI 上下文／事件环和 QRTR/QMI 分开验收，固件下载通过后再提高链路速率。本轮 BHI／PARF 读取结果仍不足以开始固件 DMA。
