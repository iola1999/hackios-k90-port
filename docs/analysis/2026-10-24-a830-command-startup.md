# A830 命令执行启动调研

本文记录 2026-10-24 的 GMU/HFI 验收边界，以及 SM8750 `gen8_0_0` 后续 GPU 初始化顺序。当前实验已通过阶段 1–14；随后阶段 15 的 125 MHz／BW2 DCVS 请求也获得 ACK，GX 状态仍为 `0x3`，运行期间通过 USB PSCI 重启并恢复 iOS 桌面，详见[最低档 DCVS 记录](../progress/2026-10-24-gpu-initialization.md#10-最低档-dcvs-与运行期间-usb-复位)。GPU 命令执行、绘制和加速仍待验证。后续优先采用厂商 HWSCHED 路径，阶段安排见 [GPU 计划](../plan/gpu-plan.md)。

## 1. 阶段 1–14 已确认的范围

本轮真机已通过 CX 上电、时钟与寄存器检查、DTCM 写入和恢复、GMU SMMU 映射、固件装载与读回、SCM GPU 寄存器初始化、CM3 启动、HFI 队列和初始化消息。GMU 外部取指曾因页权限失败；清除 GMU 叶子 PTE 的 bit 6 后，固件返回 `init_result=0x100`，HFI 版本读取为 `0x20070001`。

性能表、带宽表、关闭 IFPC 和 `CORE_FW_START(handle=0)` 均已获得 ACK。阶段 14 结束读取的 `GMU_PWR_CLK_STATUS=0x3`，GX 仍关闭；随后 CM3 复位、GMU translation context 关闭，映射内存释放，CX 配置恢复。原始日志保存在本地调试目录，本文只记录与后续判断有关的结果。

这些结果覆盖当前普通 HFI 初始化消息。GPU 地址空间、HWSCHED START 内存握手、SQE/AQE 执行、zap 认证、CP 命令和 fence 尚未验收。实验沿用继承的 DDR 投票和 19.2 MHz GMU 时钟；独立冷启动所需的时钟、投票和完整退出流程仍需核对。

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

当前文件来自 linux-firmware 固定提交，大小、SHA-256、许可和获取 URL 见[固件说明](../../hackios-xnu-userland/firmware-gen8/README.md)及[清单](../../hackios-xnu-userland/firmware-gen8/gen80000-manifest.json)。本机 Android 日志确认使用同一家族；公开文件与本机 Android 文件的二进制版本是否一致尚未核对。

| 文件 | 本轮解析结果 | 装载方式 |
|---|---|---|
| `gen80000_sqe.fw` | 111476 字节 | 跳过前 4 字节，映射剩余 111472 字节 |
| `gen80000_aqe.fw` | 25044 字节 | 跳过前 4 字节，映射剩余 25040 字节 |
| `gen80000_zap.mbn` | 12088 字节，ELF32，小端，3 个 program header | 提取 metadata，通过 PAS 装载可重定位段 |

[`adreno_get_firmware()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno.c#L73-L104) 将 SQE/AQE 分配为 `GPUREADONLY | UCODE`；[`_iommu_get_protection_flags()`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/kgsl_iommu.c#L104-L124) 据此生成只读、可执行映射。powerup list 使用 privileged、读写、不可执行映射。普通 ring 的[分配代码](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_ringbuffer.c#L123-L138)使用 privileged、只读、不可执行映射；HWSCHED 请求的缓冲区仍按各自 flags 处理。

下表列出 4 KiB stage-1 叶子页的候选属性，采用 NC、outer-shareable、AF、nG，且 MAIR index 0 为 Normal Non-cacheable。数值只含属性，不含物理地址；由[厂商 LPAE 权限转换](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/iommu/io-pgtable-arm-common.c#L238-L299)推导，GPU 上尚未验证。

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

- GPU SID/context 的实际可写范围、SQE/AQE 取指权限、APRIV 与 scratch 写回仍需真机验收；HWSCHED 同时可见于 GPU/GMU 的缓冲区需要分别映射和检查。
- `gen8_start()` 的寄存器表、pipe/aperture、powerup list 和特性配置尚未移植。LPAC、preemption、warmboot 等功能的裁减条件需按调用关系核对。
- K90 对当前公开 zap 文件的签名接受情况尚未验证；固件同族和 ELF 结构检查只覆盖选型及格式。
- host DDR 投票、GMU PLL 时钟及继承状态消除后是否仍可启动尚未验证。
- [RSC sleep](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_gmu.c#L355-L389)要求 `FIRST_BOOT_DONE`；厂商在 GPU 启动全部完成后才设置该标志。已检查的 gen8 驱动没有 RSC/PDC sequence RAM 初始化代码，初始化由哪个前置阶段完成尚不明确。CORE_FW_START ACK 后直接请求 RSC sleep 的条件仍未确认，DCVS/OOB 后的退出必须单独验收。
- CP 停止、GPU/GMU 无剩余访问、SMMU 关闭及 TLB 同步完成后才能释放映射内存。GPU 绘制、fence、异常恢复和持续运行分别通过后，再推进上层加速接入。
