# A830 HWSCHED 实测与暂停交接

## 1. 当前结论

2026-10-24，用户允许升级至 iOS 17 或更新版本，并要求评估剩余工作；缺口较大则整理后暂停。本轮暂停新增驱动实现和真机实验。硬件加速尚未运行：普通 GMU/HFI 初始化通过，HWSCHED START 已处理 7 项普通内存申请，随后因缺少安全内存分配实现而停止。GPU 命令执行、离屏渲染、用户态提交与桌面加速均未验收。后续安排与系统版本选择见[恢复工作计划](../plan/2026-10-24-gpu-handoff.md)。

此前[GPU 初始化记录](2026-10-24-gpu-initialization.md)的第 14 阶段为普通 `CORE_FW_START`；当前源码第 14 阶段已替换为完整 HWSCHED START。旧记录的「1–15 通过」只适用于旧产物及其阶段定义。当前 HWSCHED 产物的第 14 阶段失败，后续步骤没有执行。

## 2. 本轮真机结果

两轮均使用 `gen80000` 小根盘，先重新启动 loader，再经 USB 上传系统盘。第 1–13 阶段通过；SQE/AQE、powerup list 与 scratch 分配完成；HWSCHED、KPROF、AQE 和核心固件配置获得 ACK。START 中按固件请求建立共享映射并回复，结果如下。

| kind | handle | flags | 请求字节数 | 结果 |
|---|---|---|---|---|
| 2 | `0x2` | `0x33f` | `0x1000` | 分配并回复 |
| 14 | `0xe` | `0x33f` | `0x1000` | 分配并回复 |
| 15 | `0xf` | `0x339` | `0x1000` | 分配并回复 |
| 16 | `0x10` | `0x178` | `0x8000` | 分配并回复 |
| 1 | `0x1a` | `0x37b` | `0x8000` | 分配并回复 |
| 3 | `0x3` | `0x17f` | `0x18` | 按页分配并回复原请求长度 |
| 4 | `0x4` | `0x37f` | `0x138000` | 分配并回复 |
| 5 | `0x5` | `0x1007` | `0x138000` | 缺少安全内存分配实现，拒绝并停止 |

第二轮在 `CORE_FW_START` 后显式发送 `PREEMPTION=0`，收到成功 ACK，但固件仍要求相同的 kind 5 资源。这个对照仅确认该固件的安全资源请求不能通过当前关闭抢占的配置取消。失败采样中 GMU SMMU 未报告 fault；GPU 普通地址空间尚未启用，GPU 访问权限仍待实测。

kind 5 对应厂商 `CSW_PRIV_SECURE`。flags `0x1007` 要求 GPU 可访问、privileged、可写及 secure，GMU 地址应为 0。普通分配器无法满足其归属与映射要求。当前协议解析允许该组合进入回调，并要求回调返回 `secure=true`；实际分配器继续拒绝，尚未执行 secure SCM。

两轮失败后都通过 loader v5 的 USB PSCI reboot 恢复为 `idle`，耗时均约 17.13 秒，无需按键或插拔。第二轮重新上传 2,492,227,584 字节系统盘耗时 62.29 秒。该结果覆盖本轮 HWSCHED 资源保留状态下的恢复。

## 3. 源码已完成与尚未执行的部分

下列路径相对 `hackios-xnu-kernel/`。代码位于共享工作树，尚未提交；其他输入、CPU、loader 等修改有独立历史，提交前分别检查归属。

| 文件 | 已实现内容 | 验证范围 |
|---|---|---|
| `xnu/files/bsd/dev/adreno8_hfi.c`、`adreno8_hwsched.c` | START 异步内存请求、版本和长度校验、ACK 匹配、计数器不可用回复、RAW 命令入口 | 7 项普通分配经真机验证；secure 回调契约仅主机测试 |
| `adreno8_memory.c`、`adreno8_smmu.c` | GPU/GMU 共享物理页、逐页权限、动态页表发布、TLB 同步、请求重放与失败保留 | 主机测试；真机覆盖 GMU 动态映射及 START 请求回复，GPU CB0 未启用 |
| `adreno8_gpu.c`、`adreno8_gpu_private.h` | gen8.0.0 寄存器表、OOB、SQE/AQE、powerup list、CP 初始化、secure exit 和 scratch 写回 | 主机测试和内核构建；真机未到达执行阶段 |
| `adreno8_zap.c` | 真实 MBN 边界、重定位与 PAS 13 调用顺序 | 主机测试和内核构建；签名认证未实测 |
| `adreno8_cx.c` | SCM wrapper 可传入 x5 参数，保留 A6 中断续调 | 新签名构建通过；MP_ASSIGN、QTEE bridge 和 WAITQ 尚未实现 |
| `adreno8.c` | 第 14–20 阶段编排、`adreno8_reset_required` 与持有内存检查 | 主机测试；第 14 阶段失败后资源保留及 USB 重启实测通过 |

当前阶段顺序为 14 HWSCHED START → 15 最低档 DCVS → 16 GPU MMU → 17 OOB/GPU 配置/CP → 18 zap → 19 secure exit → 20 scratch → 21 诊断。每阶段失败立即停止。第 14 阶段要求 `adreno8_keep=1 adreno8_return=0`；资源保留后只通过 USB 冷重启结束实验。`loader_return_after` 无法取消该保护。

## 4. 安全资源的下一步

厂商 [`kgsl_sharedmem.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/kgsl_sharedmem.c#L596-L622)将数据页由 HLOS 移交给 CP_PIXEL；页表分配器保留 HLOS 读写权限，并赋予 CP_PIXEL 读取权限。两类资源需要分别处理，数据页移交后停止 CPU 访问。XNU 实机分配页为 16 KiB，SMMU 叶子仍为 4 KiB；归属转换应以完整分配页为单位。

厂商 [`kgsl_iommu.c`](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/kgsl_iommu.c#L2630-L2680)的 secure domain 使用 SID2。CB3 是 GMU 已占 CB2 后的候选，启用前仍需检查全部 stream match 与 context 的占用。独立地址空间、页表共享、数据页移交、失败保留与重放语义均未实现。

[`qcom_scm.c`](https://github.com/OnePlusOSS/android_kernel_oneplus_sm8750/blob/6028f47faddaa27700f8dd3a1d83906ea8f27170/drivers/firmware/qcom_scm.c#L1242-L1268)给出 MP_ASSIGN 的 7 参数格式；调用号为 `0x42000c16`，arginfo 为 `0x1117`，x5 指向扩展参数区。数据归属使用 VMID 3 → VMID 10、权限 RW=6；页表目标包含 HLOS RW=6 和 CP_PIXEL R=4。源码中的布局与调用约定已经核对，真机尚未调用。

本机 DT 包含 `qtee_shmbridge`；厂商 SCM wrapper 在 bridge 已启用后从已注册区域获取扩展参数内存。loader 当前的 bridge 状态尚未确认；注册、返回 handle 和 WAITQ 返回 2/3 的处理仍需明确。当前 wrapper 只提供调用参数与 x0/x1 返回，尚不提供 bridge 注册所需的 x2 handle。后续先解决这些前提，再实现安全资源分配；普通内存无法满足 secure 请求。

## 5. 产物与复现

以下路径相对 kernel 子模块；原始日志、截图、当前源码副本与 manifest 保存在 Git 忽略的 `docs/progress/evidence/2026-10-24-gpu-execution/`。

| 产物 | SHA-256 | 使用情况 |
|---|---|---|
| `out/handoff-mach-gpu-hwsched1` | `ba549d8053c35463f341f01ccfc81cfd2a1ef6a2de2a2a3d5e7bef7286549294` | 首次 START 真机实验 |
| `out/handoff-mach-gpu-hwsched2` | `b1cc27396efce121e9e86792e0fcea010fa3872f7ffbf7124d94869e3bea47dc` | 显式关闭抢占的真机实验 |
| `out/handoff-mach-gpu-pause` | `3afe914b78ae9b55b8bcb462deffd8f338a35ea85c6974f3fd377479d49467cd` | 当前源码构建，包含 secure 回调契约和 x5 参数，未真机执行 |
| `out/handoff-ui-gen80000.apfs` | `582b9fb28693ade94e0e374b3e55870ef986cea0a8660fc3e39d27b59f5c376e` | 两轮 GPU 实验小根盘 |

两轮实验参数均为 `debug=0x10e cpus=1 bootcpu=7 epoch=<运行时秒数> adreno8=14 adreno8_pause=0 adreno8_watch=0 adreno8_keep=1 adreno8_return=0 adreno8_speed=1 loader_return_after=25`。实际参数和 payload 哈希留在本地 manifest。恢复工作先核对产物、源码状态与设备身份，再按[真机手册](../plan/device-test-playbook.md)执行。

## 6. 检查结果与设备状态

暂停前运行了 `tools/test-adreno8-{config,firmware,smmu,hfi,hwsched,memory,gpu,zap,quiesce}.py` 共 9 组检查，全部成功。GPU 测试需要 `--vendor-dir <固定版本 graphics-kernel 源码目录>`；首次批量调用遗漏该参数，补齐后 GPU、zap 和 quiesce 均成功。映射、固件、GPU、zap 与退出测试覆盖 4 KiB／16 KiB 分配页；相关脚本启用 ASan／UBSan。内核最终构建成功，本轮文件的空白检查与构建 patch 解析成功。主机模型未覆盖实际安全固件、GPU 取指与渲染。

复杂度审查保留一个 HFI 发送循环和一个共享分配记录表，secure owner 尚未增加。`reset_required` 记录已发送的固件状态修改；`memory_retained()` 还覆盖发送前的分配失败，两项保护的触发范围不同。拆除任一保护会允许 loader 重用仍需保留的内存。完整关闭与资源释放通过真机验收前，保留冷重启限制。

设备已恢复 `handoff-mach-affinity`／`handoff-ui-clean.apfs` 的 iOS 16.5 双核配置。USB 返回 `running`，截图确认主屏幕、壁纸和 Dock，电量显示 91%；截图中的两个小组件仍为空白。桌面仍使用 softpipe，本轮没有重新测量触摸延迟或验收充电标志。Android B 槽与 userdata 未在本轮写入。暂停后不再运行 GPU 实验或构建。
