# MiCode K90 官方内核源码调研记录（2026-10-24，文件名沿用 2026-10-25 写法）

本轮调研读取小米官方（MiCode）K90 内核源码，并与项目已 pin 的 OnePlusOSS SM8750 厂商源码比较。本文档把结论分三档：主 agent 亲读确认、子 agent 比较报告待核验、待查；未采信调研初版中越界的断言。本地副本保存在 Git 忽略的调研归档目录，目录内 `ARCHIVE-MANIFEST.txt` 记录主仓 HEAD 与各归档文件的 sha256，可复核本文引用的快照。本任务只读，未改代码、未触碰设备。

## 1. 固定来源

- 主仓 [MiCode/Xiaomi_Kernel_OpenSource](https://github.com/MiCode/Xiaomi_Kernel_OpenSource) 分支 `annibale-w-oss`，HEAD `f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea`，commit「Kernel: Xiaomi kernel changes for REDMI K90 / POCO F8 Pro Android W」，日期 2026-03-13，Linux 6.6.57。主 agent 已用 gh 确认该 HEAD。
- 设备树仓 [MiCode/kernel_devicetree](https://github.com/MiCode/kernel_devicetree) 分支 `annibale-w-oss`，HEAD `32fd4ddcedd46baa579643b3894c37c0fccccb91`。commit message 含「Patch based on QualComm release TAG: LA.VENDOR.15.4.0.r1-15000-r1.0.r1_00044.1」，此处仅记原文，对应 QTI tag 未独立校验。
- 显示驱动仓 [MiCode/vendor_opensource_display-drivers](https://github.com/MiCode/vendor_opensource_display-drivers/tree/4a586833e811c8ec53e6924116505b5724a90c2d) 分支 `annibale-w-oss`，HEAD `4a586833e811c8ec53e6924116505b5724a90c2d`，434 个文件，纯 SDE，无 adreno 文件。
- 比较基准：项目 pin 的 [OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/tree/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3)（`d50b305f7da9e14715a25120a4ac7b1a4b8b97c3`）。固定厂商目录的 `vendor-revision.json` 只记录该仓与该 SHA（commit message 列出各组件的 QCOM release TAG），没有文件级来源记录；各厂商文件的实际上游未逐一校验，列入 §5。
- 本次只取浅克隆，未追溯上游基线提交。

## 2. 主 agent 亲读确认

- 构建继承：主仓 [build.config.msm.annibale](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/build.config.msm.annibale) source `msm-kernel/build.config.msm.sun`（SM8750 平台代号 sun）；[annibale.bzl](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/annibale.bzl) 加载 `xiaomi_sm8750_common.bzl` 与 `sun.bzl`。
- 设备树仓 [qcom/msm-arm-smmu-sun.dtsi](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/qcom/msm-arm-smmu-sun.dtsi) 的 GPU SMMU：节点 `kgsl_smmu@3da0000`，reg `0x3da0000` 长度 `0x40000`，带 `qcom,use-3-lvl-tables` 三层页表；电源域 `GPU_CC_CX_SMMU_GDSC`，时钟 `gpu_cc_hlos1_vote_gpu_smmu`，带宽路径 `MASTER_GPU_TCU`→`SLAVE_EBI1`；节点注释写明 GDSC 开启且 CPU 进入 cpuidle 时必须保持 DDR 带宽投票，否则 DDR 可能掉电。`qcom,actlr` 为 `<0x000 0x3ff 0x32B>`，注释「All CBs of GFX: +15 deep PF」。
- `gpu_qtb@3de8000`：reg `0x3de8000` 长度 `0x1000`，`qcom,stream-id-range = <0x0 0x400>`，`qcom,iova-width = <49>`。
- `iommus` 语义：`kgsl_smmu` 的 `#iommu-cells = <2>`；主仓 [arm-smmu.c](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/drivers/iommu/arm/arm-smmu/arm-smmu.c#L2646-L2658) 的 `arm_smmu_of_xlate` 把 `args[0]` 装入 `ARM_SMMU_SMR_ID`、`args[1]` 装入 `ARM_SMMU_SMR_MASK` 后调用 `iommu_fwspec_add_ids`。
  - debug usecase `usecase5_kgsl` 的 `iommus = <&kgsl_smmu 0x7 0x0>` 因此是 stream ID 0x7、mask 0 的精确匹配，与 CB7 无关，不能据此推断生产 GPU 的 CB 路由。
  - `usecase4_apps_secure` 的 `qcom,iommu-vmid = <0xa>`（注释 VMID_CP_PIXEL）同样只是 apps SMMU 的 debug 用例，不能推广为 GPU 当前的 VMID 绑定。
- 页归属移交链（已亲读部分）：pinned 厂商副本 `kgsl_sharedmem.c` L596-L624 `kgsl_lock_sgt` 对 sg_table 调用 `hyp_assign_table`（L604）。`hyp_assign_table` 的导出与内部实现、HFI 与移交关系、其余调用方向与调用点见 §3。

## 3. 子 agent 比较报告（待核验）

以下比较已完成文件级对比，运行影响未分析；尤其 `arm-smmu.c` 的 55 行差异未逐 hunk 评估。sha 为 sha256 前 16 位，pinned 侧对 MiCode 主仓 @`f66f8c8`。

| pinned 侧 ↔ MiCode 侧 | pinned sha | MiCode sha | diff ±行 | 差异要点 |
|---|---|---|---|---|
| qcom_scm.c ↔ drivers/firmware/qcom_scm.c | ff2ede28e6e00369 | 619418ae82a4547d | 44 | pinned 独有 `qcom_scm_update_rollback_version`（BOOT 0x1E）；READ_ONCE/smp_load_acquire 版本差异 |
| qcom_scm-smc.c ↔ drivers/firmware/qcom_scm-smc.c | d4b460234a47f42a | c7e2a7e1f83ac3c4 | 5 | MiCode 独有 Xiaomi `tzdbg_log_wq` |
| qtee_shmbridge.c ↔ drivers/firmware/qtee_shmbridge.c | 4f0f262dc7aa465a | 4f0f262dc7aa465a | 0 | 同哈希 |
| secure_buffer.c ↔ drivers/soc/qcom/secure_buffer.c | 3b5b4097a710de9c | 3b5b4097a710de9c | 0 | 同哈希 |
| arm-smmu-qcom.c ↔ drivers/iommu/arm/arm-smmu/arm-smmu-qcom.c | ee346a39182516b4 | bc10cda59c6fb298 | 2 | compat 表两行 |
| arm-smmu.c ↔ drivers/iommu/arm/arm-smmu/arm-smmu.c | 5960e88c96d3d64d | 0a90ed32693e6c65 | 55 | pinned 侧含 OnePlus pm-runtime autosuspend、EPROBE_DEFER 私有补丁；对 ctx reset 行为的影响未逐 hunk 评估 |
| io-pgtable-arm.c ↔ drivers/iommu/io-pgtable-arm.c | cbbc0e807c17cf18 | cbbc0e807c17cf18 | 0 | 同哈希 |
| secure_buffer.h ↔ include/soc/qcom/secure_buffer.h | bad28e36313d4d9a | bad28e36313d4d9a | 0 | 同哈希 |
| qtee_shmbridge.h ↔ include/linux/qtee_shmbridge.h | 58f3eff89b3f83a8 | 58f3eff89b3f83a8 | 0 | 同哈希 |
| msm-arm-smmu-sun.dtsi ↔ [qcom/msm-arm-smmu-sun.dtsi](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/qcom/msm-arm-smmu-sun.dtsi) | 87de085148f59146 | 87de085148f59146 | 0 | 字节一致，按交叉核对处理，不计新增 |
| qcom-io-pgtable-alloc.c ↔ drivers/iommu/qcom-io-pgtable-alloc.c | 5fd93ff98228ba5e | 5fd93ff98228ba5e | 0 | 字节一致（Astra 报告核对后本文作者两侧复算一致） |
| qcom-io-pgtable-arm.c ↔ drivers/iommu/qcom-io-pgtable-arm.c | 10357b84bc903214 | 10357b84bc903214 | 0 | 字节一致（Astra 报告核对后本文作者两侧复算一致） |

补充说明：

- 报告称 `qcom_scm_assign_mem`（MiCode 侧 [qcom_scm.c L1234](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/drivers/firmware/qcom_scm.c#L1234)）、`qcom_scm_assign_mem_regions`（L1327）、`gh_scm_assign_mem` 声明（qcom_scm.h L294）两侧同在；本文档撰写时已按固定 SHA 的本地副本核对上述行号，接口行为差异与契约差异未评估。
- 移交链补充（本文档撰写时在 pinned 厂商副本核对，主 agent 未亲读该部分）：`hyp_assign_table` 由 secure_buffer.c L586 导出，内部经 `_hyp_assign_table` 逐项移交；HFI 文件无直接 SCM 调用，厂商驱动的页移交经这条链进入 secure_buffer。同文件 `kgsl_unlock_sgt`（L634）调用 `hyp_assign_table` 归还归属；`kgsl_sharedmem.c` L1586、L1717 是 secure 分配路径调用 `kgsl_lock_sgt`；`adreno.c` L3852-L3893 在 secure 恢复路径（`KGSL_MEMDESC_HYPASSIGNED_HLOS` 条件）调用 `kgsl_lock_sgt`。
- 候选 CB 分配函数 `qcom_adreno_smmu_alloc_context_bank`（[arm-smmu-qcom.c L471](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/drivers/iommu/arm/arm-smmu/arm-smmu-qcom.c#L471) 起）对 GPU 设备取 start=0、count=2，注释写明 CB0/CB1 留给 GPU 切换页表，非 GPU 设备从 CB2 起。该函数由子 agent 核实，主 agent 尚未复读，行为结论以复核为准。
- MiCode 新增内容（pin 集合之外的文件，均已读）：
  - [qcom/annibale-sm8750.dtsi](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/qcom/annibale-sm8750.dtsi) 的 mitee OEM VM（`oem_vm_mem@f8800000` 0x3800000、`oem_vm_shm@fc000000` 0x400000、gunyah-label=3、binding-core=<4 5 6>）与 gh-secure-vm-loader 的 memory-region 引用；
  - [qcom/annibale-sm8750-overlay.dts](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/qcom/annibale-sm8750-overlay.dts) 的 qcom,msm-id 四组（618/639/0x100026a/0x100027f）与 `xiaomi,miboard-id = <0xB 0>`；
  - [reserved_memory_control/sun_standard_node_info.txt](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/reserved_memory_control/sun_standard_node_info.txt) 的 sun 保留区名与大小清单（hwfence-shmem 0x2dd000、gpu_microcode_region 0x2000、tz_merged_region 0x600000、trust_ui_vm_region 0x5000000 等）。
- 主仓结构：`arch/arm64/boot/dts/vendor` 是符号链接（mode 120000，指向设备树仓）；`modules.list.msm.annibale` 无 GPU ko；sun.bzl 模块清单含 gpucc-sun.ko、arm_smmu.ko、secure_buffer.ko，无 msm_drm/kgsl。
- pinned graphics 副本溯源补充（Astra 报告核对，限定来源）：`kgsl_iommu.c`、`kgsl_sharedmem.c`、`adreno_gen8_hwsched_hfi.c`、`sun-gpu.dtsi` 四个文件对本地保存的 OnePlus 完整 tree JSON（sha `d50b305`、`truncated=false`）逐路径 git blob SHA1 匹配成功。该检查覆盖本地文件与该 tree 的对应关系；tree 的网络侧来源未重新验证，K90 固件与该 graphics 版本是否配套未证明，仓级 pin 之外文件的独立来源确认仍列入 §5。

## 4. 检索范围与措辞边界

- 检索范围 = MiCode org 仓名清单（80 个，无 graphics/gpu 相关名）加上述三仓的 `annibale-w-oss` 分支。本次检索在该范围内未找到 gen8 gmu/hfi/hwsched 与 kgsl 核心；主仓 `drivers/gpu/drm/msm/adreno` 仅 a2xx–a6xx（mainline 6.6，无 a7xx）；[sun.dtsi L2617](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/qcom/sun.dtsi#L2617) 只有空 stub `msm_gpu: qcom,kgsl-3d0@3d00000 { };`。真机 GPU 固件与 gen8 驱动的来源与配套未验证。
- QTI googlesource msm-modules/graphics 镜像存在同名 `adreno_gen8_hwsched.c`、`adreno_gen8_hwsched_hfi.c`（示例 [15.0.0 标签副本](https://android.1.googlesource.com/kernel/msm-modules/graphics/+/refs/tags/android-wear-15.0.0_r0.12/adreno_gen8_hwsched.c)），与 K90 固件 gen80000 的版本配套未验证。
- 10 对文件中 6 对字节一致，其余 4 对（44、5、2、55 行）已比较、运行影响未分析；pin 集对 K90 的适用性与契约差异未知。
- carveout：[sun.dtsi L3895](https://github.com/MiCode/kernel_devicetree/blob/32fd4ddcedd46baa579643b3894c37c0fccccb91/qcom/sun.dtsi#L3895) `gpu_microcode_region@9b09a000`（no-map，0x2000）与 L3981 `hwfence-shmem`（no-map，0xd4e23000、0x2dd000）两个 label 在 sun.dtsi 与 annibale dtsi 内没有引用节点，MiCode 主仓 drivers/ 全文检索没有消费者（GPU 驱动不在主仓）。节点名只给出候选，「HWSCHED 硬件栅栏预留」属待验证推断，用途要从 graphics 侧消费者源码验证。保留内存清单不能授权 XNU 使用这些区域；真机 GPU ko 清单与实际内存布局未读取。TZ 运行时状态与复位后的归属恢复本轮不做任何承诺。

## 5. 待查清单

1. pinned 各文件的文件级来源：`vendor-revision.json` 只有仓级 SHA 与 commit message 的组件 tag，逐文件实际上游未校验。
2. 4 个未读 dtsi：`qcom/sm8750-xiaomi-common.dtsi`、`qcom/sm8750-ir-sensor-common.dtsi`、`qcom/annibale-charger-common.dtsi`、`qcom/annibale-nfc-pinctrl.dtsi`（仅定位，未读内容）。
3. graphics 镜像 tag 与 K90 固件 gen80000 的配套关系。
4. 真机 GPU ko 清单与实际内存布局。
5. carveout 消费者源码。
6. `arm-smmu.c` 55 行 OEM 差异对 ctx reset 行为的影响（未逐 hunk 评估）。

## 6. 对 HackiOS 的价值与限制

- kind 5 与安全归属：已比较结果中 secure_buffer.c、qtee_shmbridge.c 及对应头文件两侧字节相同，可供移交实现核对；两家 `qcom_scm.c` 存在 44 行差异、`qcom_scm-smc.c` 存在 5 行差异，对移交行为的影响待评估（见 §3）。`kgsl_lock_sgt`→`hyp_assign_table`→secure_buffer 链展示了厂商驱动按页移交的形态，可对照我们的页粒度移交契约。
- 恢复与性能：GPU SMMU 的 GDSC、vote 时钟、带宽路径与「GDSC 开启时 CPU idle 需保持 DDR vote」约束是官方内核设备树的静态声明，可用于核对 SMMU 配置与电源依赖；ACTLR、gpu_qtb、iova-width 49 同属配置声明。实际寄存器读回与断电恢复顺序仍需真机验证。
- 外设与安全世界：annibale dtsi 的 mitee OEM VM、trust_ui_vm 区与 gunyah-label 是该平台设备树声明的 VM 与保留区配置，运行时是否实际使用需另行查证；本轮未做设备操作，TZ 运行时状态未验证。
- 限制：本次调研属参考资料类，没有提供可直接执行的新路径，也不改变任何在审项的验收状态。当前阻塞是安全移交、地址翻译与恢复路径未验收；CB3 `0x96cc51a` 非零拒绝、路由视图 hits 0 是 run003 历史产物的行为，最新内核提交 `ec53bac` 已将严格预检判据改为 SCTLR.M 位与路由视图，尚未上机。

## 7. 与现有文档的关系

[loader 审查记录](2026-10-25-loader-review-findings.md)保持独立，本文档不向其中并入 MiCode 内容，两份文档各自行号与来源固定于各自引用的提交。本文比较表中的 sha 是调研当次快照，复核按调研归档清单执行。
