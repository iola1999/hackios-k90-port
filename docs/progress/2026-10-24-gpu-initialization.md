# 2026-10-24 A830 初始化记录

本文记录普通 HFI 阶段的历史实测。后续 HWSCHED 已更换第 14 阶段定义，当前状态、失败请求与暂停产物见[GPU 命令执行记录](2026-10-24-gpu-execution.md)；本文的「1–15 通过」仅适用于下列对应产物。

## 1. 当前范围与配置来源

本轮继续解决桌面绘制延迟。输入和 CPU 拓扑的已确认结果见[输入和绘制记录](2026-10-24-input-and-rendering.md)，Metal 路径选择见[图形加速对照](../analysis/2026-10-24-metal-route.md)。本轮按阶段运行 `adreno8=N`，各阶段结束后关闭驱动资源并返回驻留 loader；GPU 绘制尚未接入桌面。

本机 Android 启动日志加载四个 `gen80000_*` 文件，厂商 `qcom,adreno-gpu-gen8-0-0` 配置同样指定这组文件、GMEM 12 MiB 和 GMU revision `0x08000000`。先前以相似 chipid 选择 gen80200、18 MiB 和 `0x08020100` 的配置需要修正。参考源固定为 [OnePlusOSS SM8750 提交 d50b305](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno-gpulist.h)。该源码对应同一 SoC 的其他设备，本机设备树与启动日志仍分别核对。

当前实验固件来自 linux-firmware，版本和哈希见[固件说明](../../hackios-xnu-userland/firmware-gen8/README.md)。文件名与本机 Android 日志一致；二进制版本是否与手机厂商镜像一致尚未核对。

## 2. 已完成的硬件阶段

| 阶段 | 真机结果 | 验收边界 |
|---|---|---|
| 1：QFPROM／RPMh | 对齐 32 位读取完成，speed_bin=232；CMD DB 可读 | SKU 来自 socinfo feature_code/pcode，尚未读取；仅使用 DT 共有的 125 MHz／0x32 点 |
| 2：GPUCC | 寄存器可读 | 时钟配置仍按独立阶段验证 |
| 3：CX 上电 | GDSCR 从 `0x0222f801` 到 `0xfa22f800`，126 微秒后检测到上电；退出恢复原配置 | 覆盖这一轮供电和退出 |
| 4：CX／RSCC／GBIF | 已核对的窗口可读 | 移除来自 gen80200 的 slice 检查和未核对的 RSCC 槽位读取 |
| 5：时钟 | RCG 更新和分支启用后继续执行；GMU BCR 保持 0 | 修正 UPDATE bit0 和 parent selector 位移；BCR bit0 表示复位 |
| 6：GMU 寄存器 | CM3 reset=1，初始化结果=0，计数器可读 | 计数器偏移改为 dword `0x1f840/0x1f841` |
| 7：DTCM | 两个字写入、读回及原值恢复成功 | 写入前要求 CM3 处于复位 |
| 8：SMMU 识别 | 24 个 stream match、21 个 context，CB0=`0x3dc0000`、CB1=`0x3dc1000` | IDR2=`0x5511`；ATOSNS=1，硬件 ATOS 操作不可用 |
| 9：GMU 映射 | CB2／SID5、128 个 4 KiB 映射启用，关闭与 TLB 同步成功 | 固定 4 KiB granule，支持 XNU 16 KiB 分配页 |
| 10：固件 | gen80000 的 `0x15a50` 字节逐段读回一致 | 二进制来源见第 1 节 |
| 11：GMU 执行 | SCM 成功，清除 PTE AP bit6 后 INIT_RESULT=`0x100` | 保持继承 DDR 投票与 19.2 MHz 晶振 |
| 12：HFI 队列 | HFI_CTRL_STATUS=1，协议 2.7.1 | 队列轮询，无 HFI 中断处理 |
| 13：供电表 | 频率表与带宽表 ACK 成功 | ACK 验证消息应答，实际调频单独验收 |
| 14：核心固件 | IFPC disable 与 CORE_FW_START ACK 成功 | GX 仍关闭，完整 START 待实现 |
| 15：最低档 DCVS | 125 MHz／BW2 ACK 成功，USB 冷重启后恢复 | 保留资源至冷重启；尚未执行 GPU 命令 |

阶段 1–14 均已正常清理并返回 loader；阶段 15 保留资源，通过 USB 冷重启回到 loader。设备命令通道保持可用，尚未执行 GPU 渲染命令。

## 3. 地址映射、固件与 HFI 修复

固件零长度记录的第四个字段表示预分配字节数。加载前检查记录边界、完整区域覆盖和页级重叠；固件写入后逐段读回。固定 HFI 和日志区只保留实际消费者，移除未使用且与固件区域重叠的 dummy/debug 分配。

SMMU 使用固定 4 KiB granule，XNU 真机分配页为 16 KiB。页表按每个 4 KiB 地址调用 `kvtophys`，保持分配页之间物理不连续的语义；CBA2R 使用 GR1 的 `0x800 + 4 * context`。关闭前先阻止 stream 访问，再禁用 context 并同步 TLB。关闭失败保留内存，loader 返回路径停止重用该内存，等待 USB 冷重启。

HFI 表保留 17 个 header，其中 3 个队列启用，表长 210 dword。队列通过 uncached alias 访问，检查消息长度、完整 ACK 请求头、类型、序号和总超时，处理 debug/error 与 CM3 fault。`CORE_FW_START` 携带 handle=0；完整 `START` 等待 GPU MMU／OOB 前置条件。初始化阶段关闭 IFPC 并检查 ACK。

BCM 描述按 `unit:u32,width:u16,vcd:u8,reserved:u8` 解析；真机 SH0／MC0 的 unit 都为 4800000，width 分别为 64／16。BCM 命令 commit 位为 30、valid 位为 29，两路 vote 各 14 位。DDR 表采用本机 DT 的 12 档。HFI 的 ACV performance vote 位和主机 ICC enable 位按各自调用路径核对。

## 4. 第 9 阶段首次实测

真机分配 6 个固件保留区、日志和 HFI 区，软件页表遍历验证 128 个 4 KiB 映射。SMMU 写入 SCTLR=`0x1027` 后读回 `0x27`，可选 ASIDPNE 提示位未保留，严格回读检查因此停止。随后 S2CR 已设为 FAULT、context 禁用、TLB 同步完成，内核正常返回 loader。

ASIDPNE 是广播 TLB 失效提示；当前驱动使用本 context 的 TLBIASID。修复取消该可选提示，保留 M／TRE／AFE／CFRE 的精确回读。主机测试覆盖本机未保留 bit12 的行为及必要位写入失败，后续真机结果继续追加。

第二轮继续读取到 TCR2 写 `0x38011`、回读 `0x38071`。bits[6:5] 为 TBI0／TBI1，[MMU-500 寄存器参考](https://docs.amd.com/r/en-US/ug1087-zynq-ultrascale-registers/SMMU_CB4_TCR2-SMMU500-Register)定义为只读 1；当前 32-bit IOVA 不受影响。检查只忽略这两个位的回读差异，并读取全部 11 项配置后汇总结果。

第三轮 11 项回读通过，随后向 S2CR1（`0x3da0c04`）写入 translate／context1（`0x1`）触发 `ESR=0x96000010` 的同步 external abort。异常发生于 MMIO 写入，GMU 尚未启动；首次 DMA 及 shader 执行仍未发生。panic 后内核返回 loader，USB 可查询。随后核对本机 DT 得到 GMU `iommus` 的 SID=5、mask=0；先前使用的 `0x400` 是 TBU stream 范围长度。厂商分配函数为 GPU SID0/1 保留 context0/1，其他设备从 context2 分配，旧代码选择 context1 与此不同。正在按这两项来源修正并重测，具体异常原因仍需实测确认。完整异常来自返回前的实时日志，最终返回缓冲截断了后半段；原始文件与 manifest 保存到忽略提交的 `docs/progress/evidence/2026-10-24-gpu-initialization/`。

## 5. 构建与验证边界

`tools/test-adreno8-config.py` 检查实际时钟函数、CMD DB 布局、BCM 位域与 CX 失败恢复。`tools/test-adreno8-firmware.py` 使用真实 gen80000 固件检查记录、分配和写回失败；`tools/test-adreno8-smmu.py` 检查 4 KiB／16 KiB XNU 页、跨页表边界、非连续物理页、分配失败、寄存器回读及关闭失败；`tools/test-adreno8-hfi.py` 检查队列边界、回绕、ACK、错误和总超时。后三组通过 ASan／UBSan，内核构建通过。

首次第 9 阶段内核为 `out/handoff-mach-gpu-memory`，SHA-256 `96314af760bee420bdb555931c2d7454d006595c6cad3f3a7ed52d07526c725e`；小根盘为 `out/handoff-ui-gen80000.apfs`，SHA-256 `582b9fb28693ade94e0e374b3e55870ef986cea0a8660fc3e39d27b59f5c376e`。路径相对 kernel 子模块。主机测试和构建未覆盖实际固件响应、GX 上电或 shader 执行，继续按阶段验证。

SCM 初始化按厂商标准 SMC64 调用处理 availability、A6 中断续调和错误返回；本轮诊断请求 `0x9`，仅包含 ALWAYS 与 TSENSE，真机成功结果见第 7 节。厂商首次启动会投票最低 DDR 带宽 2,136,718 KB/s；本机 APSS RSC 的地址和 v3 寄存器布局与旧 Redwood helper 不同，也没有已确认的继承投票读取接口，因此暂时保持 host RPMh 投票不变。后续启动实验需记录此条件和当前 GMU 的 19.2 MHz 晶振频率。SCM 的保护与温度寄存器配置缺少对应撤销 API，CM3 复位与 SMMU 关闭只验收 GMU/DMA 停止。

## 6. SMMU 分配修正与 loader 重启

根据本机 DT 与[厂商分配实现](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/iommu/arm/arm-smmu/arm-smmu-qcom.c#L471-L489)，GMU 改用 context2、SID5 精确匹配。S2CR 按厂商设置 SHCFG=NSH、PRIVCFG=DEFAULT，TRANS=`0x302`、FAULT=`0x20300`。修正后的内核 `out/handoff-mach-gpu-memory4` SHA-256 为 `d5ad22daa1ad07f101d0d08ed97e410ac9a26973f03894cb0fe6a4284b40e878`，构建和对应主机测试通过。真机第 9 阶段已通过，S2CR 回读 `0x302`，128 个 4 KiB 映射验证完成，退出后的 context 关闭和 TLB 同步均成功。本轮同时修正 context、mask、SHCFG，并在冷重启后验证；各项对前次异常的独立影响尚未拆分。

随后第 10 阶段成功加载 gen80000 GMU 固件，逐段读回共 `0x15a50` 字节，内核正常返回 loader。首次 GMU 执行、HFI 应答和 GPU 绘制继续分别验收。

第 9 阶段异常后，loader 仍能响应；随后执行旧 loader 的 `fastboot reboot`，主机收到 OKAY，但后续命令超时，USB 枚举记录仍存在。针对该 USB 设备的 libusb reset 也超时，最终由用户进入 FASTBOOT 恢复。尚未定位旧路径具体阻塞于传输完成等待、UEFI stall、reset callback 还是最终复位调用。

已安装 `out/handoff-loader-v5.img` 到 `boot_a`，SHA-256 `89ed602ef4ecef1ae117b699cfa65d62f02a5d0cbd7be8b0f3cedb39238544a5`。annibale 的 USB reboot 改为直接调用 PSCI `SYSTEM_RESET=0x84000009`；本机 DT 指定 SMC，实际 UEFI 的 `ArmPsciResetSystemLib` 使用同一底层调用。该分支省去 UEFI reset callback 和 stall，PSCI 返回后保留 `reset-failed` 状态及 USB 命令循环。安装后已实测一次 USB reboot，约 17.09 秒后重新查询得到 `result: idle`，无需按键或插拔。该结果覆盖空闲 loader 的重启；内核异常后和长期重复恢复仍需分别验收。

## 7. GMU 首次执行的权限故障

第 11 阶段 SCM availability 返回 1、初始化请求返回成功。释放 CM3 后 100 毫秒内初始化结果仍为 0。首次失败路径只记录 GMU 寄存器，未主动读取 SMMU FSR；因此不能从该轮日志推断没有访存错误。

补充读回后，CM3 SYSRESET=0、BOOT_CONFIG=2、CM3_CFG=`0x4052`，AO counter 增加 4,219,003 tick。CB2 FSR=`0x8`、FAR=`0x4000`、FSYNR0=`0xd0063`，对应 privileged instruction read 的第 3 级权限故障。该结果确认 GMU 已访问外部固件页；下一轮保持时钟和固件不变，检查当前 SCTLR 和叶子权限，并对照厂商 `IOMMU_PRIV` 映射。

AArch64 翻译规则禁止 privileged 指令从允许 EL0 写入的页执行，[Arm 官方说明第 7 页](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Providing%20protection%20for%20complex%20software.pdf)记录了这一约束。厂商 GMU 映射指定 `IOMMU_PRIV`，本仓先前 PTE bit6 允许非特权写入。实验只清除 bit6，叶子属性从 `0xf43` 改为 `0xf03`，保持时钟、DDR、固件和其他页属性不变；第 11 阶段初始化结果变为 `0x100`，GMU 成功启动，随后复位、关闭 SMMU 并返回 loader。该对照确认了本轮固件启动失败与页权限的关系。当前尚未通过 HFI／GPU 命令执行验收。

## 8. HFI 队列

第 12 阶段 `HFI_CTRL_STATUS` 返回 1，DTCM HFI version=`0x20070001`，队列初始化通过。退出路径原有的 HFI33 空消息在一秒内未获 ACK；厂商 `hfi_prep_slumber_cmd` 要求 bw 和 freq 两个字段，并依赖已经建立的性能表与 GPU 状态。当前阶段清理改为直接复位 CM3、关闭 SMMU 和释放资源，删除提前发送的空消息。频率表、带宽表和 CORE_FW_START 的实际应答继续独立验证。

## 9. 频率表与核心固件应答

第 13 阶段的频率表消息 15 和带宽表消息 3 均收到成功 ACK；第 14 阶段的 IFPC disable 消息 11 和 CORE_FW_START 消息 14（handle=0）也均成功。GX power/clock status 仍为 `0x3`，GPU 执行尚未开始。两轮均完成 CM3 复位、SMMU 关闭、内存释放并返回 loader，后续 USB 查询正常。内核为 `out/handoff-mach-gpu-hfi`，SHA-256 `8afa9f16dca54a81c924e522052b47ad8363f0ce605d34088a9e72ee39483529`；小根盘沿用第 5 节记录。

当前未启用 HWSCHED feature，初始化顺序参照厂商保留的普通 HFI 路径：CORE_FW_START 后设置 DCVS，随后准备 GPU MMU、申请 OOB_GPU 并发送 START。本机 gen8_0_0 产品配置实际选择 hwsched，其顺序为启用 HWSCHED、CORE_FW_START、START／内存请求、DCVS、GPU MMU、OOB 和 GPU 初始化。普通模式在本机的完整命令提交能力仍待验证；本轮 ACK 结果仅覆盖已发送的四类消息。

下一阶段先核对 125 MHz 对应的带宽索引 2、GX 寄存器访问条件和退出流程。完整 START 可能请求分配内存或注册计数器，当前通用 ACK 等待函数尚未实现这些请求。GPU 页表、SQE／AQE、zap 认证和 CP 初始化需分别补齐，之后才开始离屏绘制及 fence 验收。

## 10. 最低档 DCVS 与运行期间 USB 复位

第 15 阶段改为发送 `{ack_type=1, freq=1, bw=2}`，只读取 GMUCX 状态。125 MHz 对应 DDR 索引 2，来自本机 DT 与厂商频率表；移除原步骤中的最高带宽选择、gen80200 slice aperture bit23 和未持有 OOB 的 GX counter 访问。内核 `out/handoff-mach-gpu-dcvs` 的 SHA-256 为 `3b6819b19aff6db22e3294892c3b7d670658b4dbdb989def5435c89d6a836cdc`，主机 HFI 测试和内核构建通过。

真机消息 30 收到成功 ACK，GX power/clock status=`0x3`，RPMh power state=`0xf`。这轮只验证最低档 DCVS 应答；GPU MMU、OOB、START 和 CP 仍未执行，尚无 GPU 渲染结果。

厂商通过 RSC sleep 撤销 GMU 的电源与带宽投票，其 helper 要求完整 GPU 首启成功，公开源码未确认 CORE_FW_START 后直接 sleep 的前置条件。本轮要求 `adreno8_keep=1 adreno8_return=0`，发送 DCVS 前设置 `dcvs_requested`，普通退出与 panic 返回均保留全部映射和内存，后续仅通过 USB PSCI 冷重启结束。ACK 超时或失败同样保留该限制。完整 RSC 退出通过验收后，再替换这一临时限制。

采样后在 `result: running` 状态发送 loader USB reboot，17.12 秒后重新连接并得到 `result: idle`，无需用户按键或插拔。该结果增加了 GMU/DCVS 内核运行期间的恢复验证；panic 后重复恢复仍未覆盖。原始日志、启动 payload 哈希和复位时间保存在本地忽略目录。

`tools/test-adreno8-quiesce.py` 直接编译生产退出函数，验证 DCVS 标记置位后两条退出路径都不读写 MMIO、不释放内存，panic 返回停在等待点；4 KiB／16 KiB、ASan／UBSan 均通过。分别删除两个检查的对照实验均失败。复杂度审查后将 HFI sender 改为文件内函数，删除 8 个无消费者的私有宏与过期注释；构建产物 `out/handoff-mach-gpu-dcvs-final` SHA-256 为 `73aae0755db1b35b6d9b0b0504a577bcdc397b43d368d71ebfe4fef2592bf75f`。该产物尚未真机执行，第 15 阶段实测对应本节前述版本。

冷重启后重新上传 2,492,227,584 字节系统盘，耗时 62.29 秒，再用已验证的 `handoff-mach-affinity`／`handoff-ui-clean.apfs` 和双核配置恢复 iOS。USB 截图确认主屏幕、壁纸和 Dock 已显示，内核保持 running；这轮没有重新验收手指操作延迟。GPU 加速尚未接入，桌面继续使用 softpipe。下一阶段采用厂商 HWSCHED，内存协议、GPU 页表、CP 和 zap 顺序见[命令执行启动调研](../analysis/2026-10-24-a830-command-startup.md)。
