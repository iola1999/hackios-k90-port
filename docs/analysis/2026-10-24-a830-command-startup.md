# A830 命令执行启动调研

2026-10-26 已完成 CP 初始化、zap 认证、scratch 写回、标准 context 的 SOP／EOP 和真实 GPU 桌面绘制。此前 RAW131 附近复位及直接 ring 停滞，后续通过固件等待位置追踪到 LPAC SID 1 缺少 SMMU 路由；修订后相关阶段通过。第 7～9 节保留 2026-10-25 的排查及后续修正，最新判断见第 9 节末段，桌面正确性和性能方法见[验证案例](2026-10-26-gpu-validation-lessons.md)。

第 1～5 节保留 2026-10-24 调研和当时产物的阶段定义，当前第 14 阶段为完整 START，参数以[真机调试手册](../plan/device-test-playbook.md)和本轮产物清单为准。本机运行设备树已确认 `gen8_0_1`／`Adreno830v2`；与 `gen8_0_0` 共用的寄存器表和固件仍可参考，revision 与最低工作点按本机结果修订。通用判断方法见[排查与协作手册](../plan/debugging-and-collaboration.md)。

## 1. 阶段 1–14 已确认的范围

2026-10-24 的普通 HFI 轮已通过 CX 上电、时钟与寄存器检查、DTCM 写入和恢复、GMU SMMU 映射、固件装载与读回、SCM GPU 寄存器初始化、CM3 启动、HFI 队列和初始化消息。GMU 外部取指曾因页权限失败；清除 GMU 叶子 PTE 的 bit 6 后，固件返回 `init_result=0x100`，HFI 版本读取为 `0x20070001`。

性能表、带宽表、关闭 IFPC 和 `CORE_FW_START(handle=0)` 均已获得 ACK。阶段 14 结束读取的 `GMU_PWR_CLK_STATUS=0x3`，GX 仍关闭；随后 CM3 复位、GMU translation context 关闭，映射内存释放，CX 配置恢复。原始日志保存在本地调试目录，本文只记录与后续判断有关的结果。

这些结果覆盖该轮普通 HFI 初始化消息；GPU 地址空间与 HWSCHED START 的后续验收见第 7 节，SQE/AQE 执行、zap 认证、CP 命令和 fence 在 2026-10-26 的进展见第 9 节末段。实验沿用继承的 DDR 投票和 19.2 MHz GMU 时钟；独立冷启动所需的时钟、投票和完整退出流程仍需核对。

## 2. 后续优先采用 HWSCHED

厂商 [`adreno_gpu_core_gen8_0_0`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno-gpulist.h#L2932-L2973) 明确选择 `adreno_gen8_hwsched_gpudev`，并配置 AQE、LPAC、12 MiB GMEM 和 `gen80000_*` 固件。该路径已有配套的 AQE 基址设置、GMU 内存申请协议和 CP 原始命令提交。当前普通 HFI 初始化通过后，按这条调用链继续实现，可以逐项对照本芯片的厂商配置。

厂商的[首次启动](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched.c#L824-L867)、[HFI 启动](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched_hfi.c#L2209-L2357)和 [GPU 启动](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched.c#L570-L634)按以下顺序执行：

1. 读取 SQE、AQE，分配 powerup register list，准备 GMU 内存并启动 GMU。
2. 发送性能表、带宽表及特性配置；在 `CORE_FW_START` 之前启用 HWSCHED。厂商还配置 KPROF 等特性，最小实现需要逐项核对裁减条件。
3. `CORE_FW_START` 成功后配置 preemption、LPAC、AQE 等特性，再发送 `START`。主机处理 `F2H_MSG_MEM_ALLOC` 和 `F2H_MSG_GMU_CNTR_REGISTER`，直至收到本次 START 的最终 ACK；分配结果按请求 flags 提供 GPU 地址、GMU 地址或两者。[START 处理代码](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched_hfi.c#L1449-L1735)包含这段循环。
4. 启动 GPU MMU，申请 `oob_gpu`，执行 `gen8_start()`，清除旧故障状态并配置中断，再写入 SQE/AQE 基址。OOB 在 GPU 启动函数退出时释放。
5. 通过 `ISSUE_CMD_RAW` 提交 CP 初始化并等空闲，加载并认证 zap，再提交 `CP_SET_SECURE_MODE(0)`。LPAC 启用后另行初始化其 CP。

厂商还保留[传统 ring 启动路径](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_gmu.c#L2556-L2625)，其顺序为 GPU MMU → OOB → START → GPU 配置 → ring。该入口未被 `gen8_0_0` catalog 选择，AQE 固件在当前普通模式下的执行兼容性尚未验证。后续按 HWSCHED 的 START 顺序和内存申请协议实现。

## 3. 固件和 GPU 页权限

本节解析的公开文件来自 linux-firmware 固定提交，大小、SHA-256、许可和获取 URL 见[固件说明](../../hackios-xnu-userland/firmware-gen8/README.md)及[清单](../../hackios-xnu-userland/firmware-gen8/gen80000-manifest.json)。2026-10-25 已比较 Android 实际文件：GMU、SQE、AQE 的长度和 SHA-256 均与实验输入一致；zap 不同，后续认证优先核对本机文件。下表及第 4 节的 MBN 解析只覆盖当时公开的 zap 文件。

| 文件 | 本轮解析结果 | 装载方式 |
|---|---|---|
| `gen80000_sqe.fw` | 111476 字节 | 跳过前 4 字节，映射剩余 111472 字节 |
| `gen80000_aqe.fw` | 25044 字节 | 跳过前 4 字节，映射剩余 25040 字节 |
| `gen80000_zap.mbn` | 12088 字节，ELF32，小端，3 个 program header | 提取 metadata，通过 PAS 装载可重定位段 |

[`adreno_get_firmware()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno.c#L73-L104) 将 SQE/AQE 分配为 `GPUREADONLY | UCODE`；[`_iommu_get_protection_flags()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/kgsl_iommu.c#L104-L124) 据此生成只读、可执行映射。powerup list 使用 privileged、读写、不可执行映射。普通 ring 的[分配代码](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_ringbuffer.c#L123-L138)使用 privileged、只读、不可执行映射；HWSCHED 请求的缓冲区仍按各自 flags 处理。

下表保留 2026-10-24 调研的 4 KiB stage-1 叶子页候选属性，采用 NC、outer-shareable、AF、nG，且 MAIR index 0 为 Normal Non-cacheable。数值只含属性，不含物理地址，由[厂商 LPAE 权限转换](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/iommu/io-pgtable-arm-common.c#L238-L299)推导。后续实际配置以生产实现和第 9 节的设备验收为准。

| 用途 | 权限 | PTE 属性 |
|---|---|---|
| SQE/AQE | privileged 和 unprivileged 均可读、可执行，禁止写入 | `0xec3` |
| privileged ring | privileged 只读、不可执行 | `0xe83 | (3ULL << 53)` |
| powerup list、privileged scratch | privileged 读写、不可执行 | `0xe03 | (3ULL << 53)` |

GPU 映射需独立确认 SID/context 路由及访问权限，GMU context 的通过范围限于 GMU。CPU 写入命令或固件后发布数据，读取 GPU 写回结果前执行对应的 acquire/cache 操作；同时保留 CPU 与设备使用同一物理页的关系，逐页检查非连续分配。

gen8 的 SQE 基址寄存器为 `0x816/0x817`，AQE0 为 `0x818/0x819`，AQE1 为 `0x81a/0x81b`，均为 dword offset。厂商对 AQE0 配置 AQE 固件地址，AQE1 仅在 LPAC 启用后设置，见[微码基址设置](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched.c#L541-L568)。

## 4. CP 初始化先于 zap 认证

[`gen8_cp_init_cmds()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8.c#L607-L650) 生成 10 dword，先关闭 concurrent binning，再设置 CP 上下文、错误检测、操作模式和 powerup list 地址：

```text
TYPE7(CP_THREAD_CONTROL, 1), BIT(27)
TYPE7(CP_ME_INIT, 7), 0x14b, 3, 0x20000000, 2,
pwrup_iova_lo, pwrup_iova_hi, BIT(31)
```

powerup list 包含锁和计数头、静态寄存器对，以及带 pipe ID 的动态三元组。[`gen8_start()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8.c#L1301-L1540) 设置非上下文寄存器、保护范围、APRIV、SECVID 和时钟门控后，再[读取寄存器生成列表](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8.c#L1031-L1181)；CP 初始化必须引用有效的 GPU 地址。HWSCHED 的[原始命令提交](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched_hfi.c#L2359-L2449)先检查 ACK，再等待 `GPU_CX_BUSY_STATUS.bit23=0`，超时为 200 ms。

[`gen8_hwsched_cp_init()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched_hfi.c#L2432-L2452) 在 CP 初始化成功后加载 zap，随后发送 `CP_SET_SECURE_MODE(0)`。本机 DT 中 zap 预留区为 `0x9b09a000`、大小 `0x2000`，与[厂商预留区](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/kernel_platform/qcom/opensource/devicetree/qcom/sun.dtsi#L3862-L3865)和 [`zap-shader` 引用](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-devicetree/gpu/sun-gpu.dtsi#L89-L91)一致。当前 MBN 的解析结果和认证顺序如下：

1. metadata 由文件开头 `0x94` 字节和文件 `0x2000` 处的 hash 段 `0xf38` 字节拼接，总长 `0xfcc`。hash 位于第三个 program header，按段类型识别。[MDT/MBN metadata 解析](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/soc/qcom/mdt_loader.c#L163-L237)说明该格式。
2. 唯一 `PT_LOAD` 位于文件 `0x1000`，`p_paddr=0x1000`，`p_filesz=p_memsz=0x3b4`，带 relocatable 标志。按最低加载地址重定位到预留区起点，页对齐后的装载范围为 `0x1000`。
3. PAS ID 为 13。先 `INIT_IMAGE(metadata_pa)`，再 `MEM_SETUP(0x9b09a000, 0x1000)`，复制加载段，最后 `AUTH_AND_RESET(13)`。调用关系见 [MDT 装载](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/soc/qcom/mdt_loader.c#L252-L480)和 [GPU zap 装载](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/kgsl_util.c#L103-L170)。
4. metadata 必须物理连续、至少 4 KiB 对齐并以非缓存方式访问；每次 PAS 调用同时检查 SMC transport 返回和服务返回值。该要求来自 [`qcom_scm_pas_init_image()`](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/firmware/qcom_scm.c#L676-L737)。认证失败后保留失败状态，后续 secure-mode 命令停止执行。

## 5. 分阶段验收与可复用代码

| 下一步 | 独立完成条件 |
|---|---|
| 主机解析和映射准备 | SQE/AQE 长度、MBN 段边界与重定位通过；GPU 页表满足各资源权限，映射不重叠 |
| GX 诊断 | 使用已确认的低频点，检查 OOB ACK、GX 电源和时钟状态；先明确 DCVS/OOB 后的退出条件，再扩大寄存器访问 |
| HWSCHED START | 每条内存申请的大小、对齐、flags 和回复均可检查，计数器注册完成，最终 ACK 匹配本次请求 |
| GPU 配置和 CP 初始化 | powerup list 完整，SQE/AQE 基址读回正确，CP 初始化 ACK 和空闲条件均通过，GPU SMMU 无新增故障 |
| zap 和最小命令 | PAS 认证成功，退出 secure mode 完成；`CP_MEM_WRITE` 写入专属 scratch，CPU 读回预期值并确认任务完成 |

现有 [`redwood_adreno.c`](../../hackios-xnu-kernel/xnu/files/bsd/dev/redwood_adreno.c) 的 `odd_parity()`、`ring_command()`、`ring_send()`、`ring_run()` 和 `step_core_commands()`可提供 PM4 构造、发布、完成轮询和 scratch 验收方法。A660 寄存器表、八参数 `CP_ME_INIT`、固定 zap 地址及分离 MDT 解析需要按 gen8 替换；旧 `step_zap_load()` 将部分 PAS 失败按已加载处理，该分支不能用于新实现。

[NativeAdreno 的 CP 构造](https://github.com/UniXNU/NativeAdreno/blob/b686b9054f57d393c80195b82568a09f8ca106a2/NativeAdrenoCpInit.cpp#L6-L62)使用相同的 10 dword payload；其 SQE 寄存器 `0x830` 和 A740 powerup 寄存器表需要替换。[启动代码](https://github.com/UniXNU/NativeAdreno/blob/b686b9054f57d393c80195b82568a09f8ca106a2/NativeAdrenoGpu.cpp#L4-L66)在观察到真实 fence 后设置 ready，失败后调用 quiesce；这些验收和生命周期约束可继续采用。其 A740 硬件结果与 K90 分开记录，接口及上层路径见 [UniXNU 对照](2026-10-24-metal-route.md)。

## 6. 尚未确认的条件

- 当前配置已通过 context 启用、LPAC 路由、CP 初始化、zap 认证及命令写回，后续桌面由 A830 绘制；不同固件、安全资源布局与启动模式仍需各自验收。HWSCHED 同时可见于 GPU/GMU 的缓冲区继续分别映射和检查。
- LPAC 在当前固件的启动同步中参与等待，裁减前必须核对固件和厂商特性配置；显式关闭 preemption 后固件仍请求安全资源，当前实现继续处理这些请求。warmboot 等其他裁减条件仍需实测。
- GPU 运行后 CB0 的 TCR EPD1 被清零，写入方未确认；`4d93f52` 只在 GPU context、TTBR1 为零且 IOVA 使用 TTBR0 的范围内容忍该差异，扩大地址范围或复用到其他 context 前需重新核对。
- host DDR 投票、GMU PLL 时钟及继承状态消除后是否仍可启动尚未验证。
- [RSC sleep](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_gmu.c#L355-L389)要求 `FIRST_BOOT_DONE`；厂商在 GPU 启动全部完成后才设置该标志。已检查的 gen8 驱动没有 RSC/PDC sequence RAM 初始化代码，初始化由哪个前置阶段完成尚不明确。CORE_FW_START ACK 后直接请求 RSC sleep 的条件仍未确认，DCVS/OOB 后的退出必须单独验收。
- CP 停止、GPU/GMU 无剩余访问、SMMU 关闭及 TLB 同步完成后才能释放映射内存。现有桌面运行保留异常后资源至全系统复位的约束，持续运行与完整异常退出继续分别验收。

## 7. 安全资源与 START 的真机验证

接手审查发现原 3a 只核对首个叶子描述符。提交 `537f970` 改为从 TTBR 根检查完整路径和全部缓冲；首轮真机遍历 312 个叶子映射，4 批 MP_ASSIGN 的 transport 与 answer 均为 0，CB3 控制及页表寄存器也已读回。软件遍历确认主机建立的映射内容，设备真实访问仍需后续命令验证。

该轮停在 FSR 读值 `0x400`。固定 MiCode 与厂商定义确认 `[10:9]` 为翻译格式字段，`0x400` 对应 AArch64；有效故障掩码为 `FSR_ALL=0xc00001fe`。提交 `3a4d388` 使用该掩码后，真机完成 TLB 同步，SCTLR 读回 `0x27`，有效故障位为零。mode 3 继续保持 stream 2 为 fault，不回复 MEM_ALLOC。测试同时接受格式字段并逐个检查有效故障位，保留真正故障的停止条件。

提交 `744092c` 的 mode 4 在同次启动中继续把 stream 2 切到 context 3，路由读回 `0x303`，应答 kind 5 后还处理 kind 7、24，最终取得 HWSCHED START ACK。mode 3 与 mode 4 分别检查了配置启用和路由／握手；START 的 ACK 尚未覆盖安全数据的真实 GPU 访问。

安全资源状态需区分已经移交、可以继续服务及失败后停止。READY 允许后续普通分配和原安全请求的精确重放，新安全 handle 继续拒绝；HFI／START 失败后停止服务并保留资源至全系统复位。安全页移交后继续限制 CPU 访问，恢复了主机命令应答也仍需遵守该约束。实现见[内存请求处理](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_memory.c)和[翻译检查](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_translation.c)。

同一内核的阶段 15 获得 125 MHz／带宽索引 2 的请求 ACK；阶段 16 完成 363 个映射的软件检查、GPU context 0 启用与 stream 0 路由读回 `0x300`。该频率来自早期参考配置，本机最低点的修订见下一节。

## 8. CPU 映射越界与 RAW 自动复位

阶段 17 首轮的 CPU data abort 已用实际二进制定位到 `adreno8_wr`，调用点为 `adreno8_gpu_cp_init+0x290`，目标偏移 `0x2b840`。生产声明只映射 `0x10000` 字节；固定厂商设备树给出的窗口为 `0x03d00000 + 0x40000`。提交 `7faa7c1` 修正映射，并在寄存器索引乘以 4 之前检查边界。旧主机测试自行提供 `0x40000`，因此漏掉生产声明中的错误；修订后直接读取生产配置，再与固定设备树比较。

修正后，同一内核的阶段 16 通过，阶段 17 改为整机自动复位。逐次日志确认 GPU 配置、1560 字节 powerup 表及 SQE/AQE 基址均已写入并读回。后续实验逐项检查了下列差异，完整产物哈希保留在[运行记录](../progress/2026-10-25-gpu-resume-review.md)及本地清单。

| 修订或对照 | 确认的范围 | 复位结果与限制 |
|---|---|---|
| `9134960` 安全 IOVA 改从 `0xf0000000` 分配 | 与 GPU trusted base 一致，普通分配仍从 `0x10000000` 开始；重测仍有 START ACK | 阶段 17 仍复位，安全范围修正未消除故障 |
| `a473130` MMIO 屏障 | 写入前、读取后的屏障按厂商顺序补齐，直接访问与诊断分支均有主机检查 | 阶段 17 仍复位，该轮只取到启动日志 |
| `ae92c8a` CB0 aperture | 厂商普通初始化在默认 TTBR0 后调用 `qcom_scm_kgsl_set_smmu_aperture`；本轮 SMC 返回 0、answer 0，ACTLR 为 `0x3` | RAW131 索引发布后复位，尚无 CP ACK |
| `57bbcff` 最小 NOP | 真机运行 2 个 PM4 字的 NOP；10 个字的等长模式仅完成主机检查 | 仍在索引发布后复位；厂商冷启动首条 RAW 固定为 CP_INIT，pre-init NOP 的有效性未确认 |
| `d6e7015` GMU revision | 本机运行设备树为 `gen8_0_1`，chip ID `0x44050001`；GENERAL_10 改为 `0x08000100` 并先于 CM3 解除复位 | 原 125 MHz 输入下仍复位 |
| `189ba55` 最低工作点 | 本机各频率档组最低为 160 MHz、level `0x32`、DDR 索引 2；单独修订该工作点 | 仍在 RAW131 索引发布后复位，随后约 26.1 秒重新枚举为 loader `idle` |

CB0 aperture 轮及后续 CP_INIT 轮的最后非空快照包含以下标记：

```text
adreno8: HWSCHED START acknowledged; GPU execution initialization is pending
adreno8: step 17: RAW131 payload ready: 11 dwords; producer publication follows
adreno8: step 17: RAW131 producer published at 344; doorbell follows
```

日志未记录到 `RAW131 doorbell write returned`。索引发布后设置了 1000 毫秒诊断暂停，GMU 可能已在这段时间读取队列；当前记录只限定复位区间，触发指令和原因尚未确定。保持相同复位现象也不足以证明每轮原因完全相同。NOP1 发布的是 3 个 HFI 字、索引 336，随后回退 B 槽 Android；运行脚本在这次 USB 断开后没有发送复位命令。

Android 诊断读到 PMIC 的 PS_HOLD、WARM_RESET 与 HARD_RESET 缓存记录，pstore 为空，hypervisor 的 S2 Fault Counter 为 0，TZ 内容加密。缓存包含多次启动，现有输出尚无法定位 XNU 的复位原因。Android 与实验的 GMU、SQE、AQE 哈希一致，zap 哈希不同；阶段 17 尚未加载 zap，因此文件差异留给后续认证阶段核对。

用户报告「进安卓系统了」后，LK 查询确认 A 槽 `slot-successful: no`、`slot-unbootable: yes`、`slot-retry-count: 0`，B 槽为 successful。经 ADB 返回 LK、重新选择 A 槽后恢复 v7 `idle`。该次回退来自实验槽重试耗尽，恢复已有 loader 无需重写启动镜像；具体操作见[手册第 2、6 节](../plan/device-test-playbook.md#2-操作前检查)。

## 9. 测试、构建与服务生命周期

本轮从固定 XNU 标签在独立目录重新应用全部补丁，再与容器的实际编译树按文件集合和内容比较；第一轮检查 5127 个文件，只更新 10 个差异文件后复用缓存。后续新增文件也纳入全量比较。源码输入一致、构建退出成功、payload 输入正确和设备实际运行分别核对；可复用的方法见[手册第 3 节](../plan/debugging-and-collaboration.md#3-沿实际使用的数据追踪源码与产物)。

截至 2026-10-25，标准 context、A830 缓冲映射、接口分派与服务发布已实现并完成主机检查，服务内核也已构建成功，当时等待 CP 初始化后的真机验收。实现与检查范围见[运行记录第 20 节](../progress/2026-10-25-gpu-resume-review.md#20-a830-用户态接口准备)，2026-10-26 的后续结果见本节末段。

提交 `9771edf`、`4f3cc11` 修订现有服务的失败清理：映射提交、TLB 同步或解除映射失败后保留 IOVA 与 descriptor，后续停止提交；绘制完成标记依赖实际 fence。生命周期检查覆盖 4 KiB／16 KiB 和失败分支，变异检查、ASan／UBSan 均通过。该结果覆盖主机模型；后续桌面运行验证了正常设备访问，失败注入的设备行为仍需分别检查。映射和资源释放的实现见[RedwoodGPUMemory.inc](../../hackios-xnu-kernel/xnu/files/iokit/Kernel/RedwoodGPUMemory.inc)与[legacy 服务](../../hackios-xnu-kernel/xnu/files/bsd/dev/redwood_gpu_service.inc)。

### 后续实验的选择依据

RAW 附近持续复位后，实验保留前面的配置，暂不发布命令，十秒内状态持续可读，随后软件恢复成功。该对照减少了对「仅由此前配置引起延迟复位」的怀疑，后续优先调查发布后才开始的处理。fault stall 配置虽已读回，复位仍未留下故障报告；这一诊断尚未排除其他故障路径。原始结果见[运行记录第 11、12 节](../progress/2026-10-25-gpu-resume-review.md#11-实际最低频率与-fault-stall-诊断)，通用选择方法见[手册第 2 节](../plan/debugging-and-collaboration.md#2-用能区分原因的实验推进)。

默认 GPU 页表提前配置后，START 与后续校验通过，RAW 复位仍存在；总线时钟使能实验又读到操作前已启用的继承状态。这两轮分别确认了时序修订后的行为与本机原有配置，仍未确定复位原因。源码缺少一项设置后先读实际状态，可以判断试验是否真正改变条件，见[运行记录第 14、15 节](../progress/2026-10-25-gpu-resume-review.md#14-默认-cb0-提前配置对照)。

用户补充 idalib 可用后，调查针对实际加载的驱动模块核对布局和启动准备，发现 HFI 队列布局及 GMU 虚拟寄存器、trace 的准备缺项。修订后配置和 START 通过，RAW 复位仍存在；实现差异与原故障原因继续分别判断。HFI 布局变化还使队列跨页，修复同时处理了 CPU 映射前提，范围限定在该缓冲；该轮结果只覆盖布局与映射一起修改的组合。具体核对见[运行记录第 17 节](../progress/2026-10-25-gpu-resume-review.md#17-实际驱动二进制与-hfi-布局)和[第 19 节](../progress/2026-10-25-gpu-resume-review.md#19-gmu-虚拟寄存器与-trace)。

电源调查先读取 RSC 状态，再通过协议读取本方 CX、MX 继承票值；两项请求完成、资源回收和软件恢复均通过。这类读取需要写共享命令与 IRQ 寄存器，诊断因此排除触摸路径的并发使用，并只撤销本轮新增状态。返回值只描述 DRV2 请求，其他 DRV 的需求继续由硬件聚合；电压和 PLL 写入仍待后续验证，见[运行记录第 18 节](../progress/2026-10-25-gpu-resume-review.md#18-arc-继承票值读取)。共享资源的判断方法见[手册第 5 节](../plan/debugging-and-collaboration.md#5-用状态和资源归属理解设备行为)。

### LPAC 路由与后续验收（2026-10-26）

直接 ring 停滞时，GFSR 为零，WPTR 已发布，RPTR 不动。BR、BV 的 SQE PC 分别停在 `0xe3`、`0x4a`；对照实际 `gen80000_sqe.fw` 反汇编，两者在等待 `THREAD_SYNC` 清零。各单元分别清除自己的位，LPAC 对应位始终未清。设备树与寄存器配置确认 LPAC 使用 SID 1，当前路由只覆盖 SID 0 与 GMU SID 5。BR、BV 已经执行微码，只能确认它们各自的进度；GFSR 零读数也未排除 LPAC 的独立路由遗漏，其未报告故障的原因仍未确认。

`a10067e` 为 SID 1 增加指向 GPU context 0 的路由。直接 ring 随后记录 `CP_INIT consumed and idle`，HWSCHED 轮取得 CP 初始化 ACK 并空闲，之后完成 zap、退出 secure、scratch 写回及标准 context 两条 IB 的 SOP／EOP。直接 ring 诊断仍打印阶段 17 `FAILED`，因为该分支在取得诊断结果后主动停止；检查应读取具体完成条件，再解释总状态。

阶段 23 还修正了诊断条件、平台识别及限定范围内的 TCR 读回检查；阶段 22 则为 EOP 与空闲之后稍晚可见的队列读指针增加有界等待（`3d9c53f`）。这些问题各有独立检查，LPAC 修复单独支持 CP 启动原因，完整桌面成功覆盖上述组合配置。CoreAnimation 经 freedreno 使用 A830 绘制后，继续处理显示缓存和帧时间；相关方法及边界见[桌面验证案例](2026-10-26-gpu-validation-lessons.md)。

## 10. 增量阅读范围

前次整理到 `01575e5`、`kernel-arc-read-both-s2`，payload 的 epoch 对应北京时间 2026-10-25 18:13:02，包含 fault stall、配置后暂不发布 RAW 的对照、页表时序、继承状态、实际驱动分析、HFI／VRB 修订及服务准备。本次继续读取 Claude Code 接手后的完整时间线，纳入 LPAC 路由、阶段 14～23 通过、真实 GPU 桌面及后续正确性、性能、外设验证；最新截止位置见[桌面验证案例第 6 节](2026-10-26-gpu-validation-lessons.md#6-阅读范围与后续入口)。

原始运行材料继续保留在 Git 忽略的 `docs/progress/evidence/2026-10-25-codex-gpu-resume/`，本次阅读快照与索引位于 `docs/analysis/local/claude-review-20261026/`。CP 启动已有后续成功结果，新增调查按当前失败阶段选择检查；独立时钟、电源初始化与完整停止条件继续保留。来源会话仍在执行，设备现状由实现会话重新读取；本轮只读取材料和整理文档。
