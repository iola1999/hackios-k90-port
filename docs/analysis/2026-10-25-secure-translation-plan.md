# 安全翻译方案：一次移交诊断之后的最小实施路径（2026-10-24，文件名沿用 2026-10-25 写法）

本文是安全移交与安全翻译的架构研究汇总，只读来源，改动代码、设备与构建都不在本轮。目标是给出一轮移交诊断实验之后的完整 START 最小实施路径；mode0/1/2 语义保持，完整 kind-5 回复继续关闭。协议顺序的既有结论见[交接计划](../plan/2026-10-24-gpu-handoff.md)§4，厂商文件与小米官方内核的对比见[MiCode 调研记录](2026-10-25-micode-annibale-reference.md)，loader 生命周期问题的唯一审查记录是[审查记录](2026-10-25-loader-review-findings.md)，本文只写翻译架构与实施分级。

来源分三档并逐条标注：①「本文作者已核对」：pinned 厂商副本（graphics-kernel @`d50b305`，固定 URL 见[GPU 实测记录](../progress/2026-10-24-gpu-execution.md)）与 MiCode 主仓 @`f66f8c8` 的直读行号，本轮全部重读确认；②「Astra 报告」：两份独立审查报告与一份源码差异文件保存在 Git 忽略的归档目录，版本、读取范围与生产文件哈希由报告开头自述，核对由 Astra 完成、主 agent 抽查裁决，其中 XNU 行号按报告自述的最终核对提交 `5c5616e`；③「主 agent 裁决」。运行时 goal 与本文冲突时以主 agent 裁决为准。

## 1. 主 agent 裁决（本文约束）

- 架构方向：HLOS 自建独立 secure stage-1 域，物理页访问归属经 SCM 移交；CB3 只作条件候选；secure 不调用 user/LPAC aperture；mode0/1/2 保持，完整 kind-5 回复关闭。
- 实验顺序：loader held 全路径与共享硬件副作用验收 → 固定构建 → 新版 mode1 诊断与恢复验收 → 另审 mode2；secure attach 的设备操作后置。
- mode2 复位后旧物理页归属未知，新 loader 自身分配也可能复用同一批页，仅禁止下轮上传无法声称隔离；host stop 与五秒 HFI 预算取消不了已在执行的 SMC；移交须逐批记录表页、数据、区域、权限、参数页 PA 与结果，顶层 attempts 计数不含 A6 续传迭代。
- 准入门槛原则：不设「证明所有 SID2 消费者停止、所有 TZ 保留已知」这类公开接口无法取得的门槛；采用可核实前提加明确未知风险裁决。mode2 不改翻译、不回复新地址，与 START 等待 kind-5 并存，前提收敛在自有未发布页、无旧映射别名、全生命周期保留；attach 独立准入，优先选 START 之前的检查点，且检查点称呼不含全局静默承诺。

## 2. 厂商调用链（本文作者已核对）

kind 与回复。kind 枚举在 `adreno_hfi.h` L150-L246，kind 5 即 `HFI_MEMKIND_CSW_PRIV_SECURE`（特权 secure 抢占记录）。厂商实现在 [adreno_gen8_hwsched_hfi.c](https://github.com/OnePlusOSS/android_kernel_modules_and_devicetree_oneplus_sm8750/blob/d50b305f7da9e14715a25120a4ac7b1a4b8b97c3/vendor/qcom/opensource/graphics-kernel/adreno_gen8_hwsched_hfi.c)：

- `get_mem_alloc_entry` 把 `HFI_MEMFLAG_GFX_SECURE` 转成 `KGSL_MEMFLAGS_SECURE`（L1491-L1492），默认 kind 走 `kgsl_allocate_global`（L1534-L1535）。
- `process_mem_alloc` 回填 `gpu_addr`、`gmu_addr`、`host_mem_handle`（L1571-L1592）。
- `mem_alloc_reply` 写回复 cmdq（L1594-L1617）。
- `send_start_msg`（L1664 起）表明 host 在等待 START 最终 ACK 期间持续处理 MEM_ALLOC。

数据页归属。`kgsl_sharedmem.c` 的 `kgsl_allocate_global`（L1945）在 secure 标志下转入 `kgsl_allocate_secure_global`（L1951-L1952）→ L1908 → `kgsl_alloc_secure_pages`（L1669）→ `kgsl_lock_sgt`（L1717）→ `hyp_assign_table`（L596-L624 内 L604）→ secure_buffer 批量 `qcom_scm_assign_mem_regions` → MP_ASSIGN（pinned 副本 `vendor-secure_buffer.c` L486-L599、L386-L389）。是否存在 `gh_rm_needs_hyp_assign` 运行时分支由 Astra 报告核对。

secure 域在 probe 期建立，早于 kind-5。`kgsl_iommu.c` 的 `iommu_probe_secure_context`（L2630-L2704）：取 DT 子节点 `gfx3d_secure`（L2643）→ `VMID_CP_PIXEL`（L2639，`vendor-include_soc_qcom_secure_buffer.h` L23 = `0xA`）→ `qcom_iommu_set_secure_vmid`（L2667）→ `iommu_attach_device`（CB 在此分配）→ `qcom_iommu_get_context_bank_nr` 回读 cb_num（L2690，实现 `vendor-arm-smmu.c` L2795-L2806，锁内返回软件对象 `cfg.cbndx`）→ 创建 securepagetable（L2699）。probe 顺序 user 先、secure 后（L2822-L2838）。kind-5 阶段厂商只做数据页分配与 secure 域映射，CB 配置在此之前已就位。

映射与错误传播。secure VA 从 securepagetable 分配并映射到 `secure_context.domain`（`kgsl_iommu.c` L793-L808、L640-L644）。`kgsl_iommu_map_secure_global` 返回 void，`secure_map` 错误未上传（L807 无返回检查），厂商顺序只能确认「尝试映射后回复」。XNU 实现须在回复前显式确认映射成功与完整长度，该缺口 Astra 报告同样指出。

表页归属。`vendor-qcom-io-pgtable-alloc.c`：`io_pgtable_hyp_assign_page`（L30-L47）对每张表页调用 `qcom_scm_assign_mem`，目标权限 {HLOS RW, secure VMID R}；`qcom_io_pgtable_alloc_page`（L205-L229）禁止 atomic 与 secure 组合（`BUG_ON`），共享失败即漏页不回收。`vendor-qcom-io-pgtable-arm.c` 的 `qcom_arm_lpae_map_pages`（L521 起）在写入末尾 `wmb()` 发布（L555）。`vendor-secure_buffer.c` 有对已处理批次的回滚尝试（L396-L448）与「归属不明页不再由 HLOS 访问」约束（L483-L484），此两段 Astra 报告核对，本文作者未逐段复读。

CB 寄存器顺序。`vendor-arm-smmu.c` `arm_smmu_write_context_bank`（L1176-L1255）：先写 SCTLR=0，再 CBA2R（16-bit VMID）→ CBAR（8-bit VMID 写入处）→ TCR2/TCR（源码注释要求 TCR 先于 TTBR，影响 ASID 高位行为）→ TTBR0/TTBR1（AArch64 用 64 位写）→ MAIR → SCTLR。

- ACTLR 由 qcom impl 的 init 回调在 domain 初始化中先行写入：MiCode [arm-smmu-qcom.c](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/drivers/iommu/arm/arm-smmu/arm-smmu-qcom.c) `qsmmuv500_init_cb`（L2643-L2660）写 ACTLR 后 `iommu_flush_iotlb_all`。
- 固定设备树的 ACTLR 表仅一条 `<0x000 0x3ff 0x32B>`（`msm-arm-smmu-sun.dtsi` L60-L62，注释「All CBs of GFX: +15 deep PF」），该值有固定来源但本方案未授权当前 XNU 写入。
- SID2 的 ACTLR 命中条件与安全世界要求值未知。

aperture。kgsl 侧 aperture 仅两处：user CB（`kgsl_iommu.c` L2609）与 LPAC CB（L2615），经 `kgsl_set_smmu_aperture`（L1443-L1460）调用 `qcom_scm_kgsl_set_smmu_aperture`（L1451，L1453 重试一次），服务于普通 GPU/LPAC 的 per-process 页表切换；secure attach 路径没有该调用，与主 agent 裁决一致。本轮未找到 secure attach 专用的独立 aperture 命令。

## 3. CB 与 SID 相容性（本文作者已核对）

`gfx3d_secure` 静态声明：pinned 副本 `sun-gpu.dtsi` L156-L159，compatible `"qcom,smmu-kgsl-cb"`，`iommus = <&kgsl_smmu 0x2 0x000>`（GPU SMMU 上 SID2/mask0），DMA disabled；DTS 声明 SID，未声明 CB 编号。

- 分配规则：MiCode `arm-smmu-qcom.c` 的 `qcom_adreno_smmu_is_gpu_device`（L395-L413）以 fwspec SID∈{0,1} 识别 GPU，`qcom_adreno_smmu_alloc_context_bank`（L471-L489）对 GPU 限定位图 [0,2)，其余设备从 CB2 起按 attach 顺序动态分配，SID2 secure 与 GMU 都走后者。
- 结论：GPU 的 CB0/CB1 保留与 CB3 候选在静态与分配规则两层都无冲突；CB3 的成立条件是 GMU 已占 CB2、CB3 无其他已知占用、且安全世界无隐藏保留（第三项 HLOS 无查询接口）。
- SMR 匹配槽、SID、CB 是三个独立编号空间，debug 用例 `iommus <&kgsl_smmu 0x7 0x0>` 给 SID7/mask0，推不出 CB7。
- K90 实际加载的 DT/驱动/固件组合与本机静态声明的一致性、以及 Android 侧 secure attach 实际分到的 CB，属真机或已存日志采集项，本轮未采集。

## 4. XNU 差距清单（Astra 报告行号，HEAD `5c5616e`；标注者为报告）

1. secure stage-1 域缺失：需要独立 domain 与页表分配器，表页共享路径对应厂商 `io_pgtable_hyp_assign_page`，同时承接 atomic/secure 禁组合与失败漏页策略。
2. CB 写入差异：现有通用 space_on 用两次 32 位 TTBR store 且无 ACTLR 写入；厂商为 64 位 TTBR 写、TCR 先行、ACTLR 在 init 回调写入。secure 启用前须单独审阅该差异，直接复用现有 GMU 路径并宣称与厂商 attach 等价缺少依据（Astra 报告）。
3. 逐批物理清单缺失：表/数据角色、批次序号、区域范围、权限、进入与返回状态、参数页 PA（Astra 恢复报告 §3.5）。
4. WAITQ 未实现：返回值 2/3 时续传所需 x2/x3 未保存，pending 即结束该 boot 的移交入口。
5. 注释错误待修：`adreno8_smmu.c` L389-L398 写「MP_ASSIGN 经 GMU stream5」，实际 CPU 经 SMC 发起；GMU 路由对照验证的是已配置路由与寄存器视图一致性，确认不了 SCM 可用性与 secure 归属（Astra 报告）。
6. loader held 生命周期：修复与主机失败矩阵未完成，见审查记录。

## 5. 分阶段最小方案

每步给出前提、成功条件、失败保留；顺序为主 agent 裁决，未过一步不进下一步。

P0 loader held 全路径验收（代码修复进行中）。前提：修复覆盖 CPU_ON 之前直到可证返回，含 IRQ 恢复、UFS 接管、充电轮询等共享硬件动作审查。成功条件：主机失败矩阵（HUNG、CPU_ON 成功未到达、ON_PENDING/ALREADY_ON、returned 后非 OFF、PSCI 返回、晚到 core/done、日志缓冲满、重复命令）全部按 held 语义通过，正常完成且 OFF 的对照可恢复正常操作，删除 held 保护的负例失败。失败处理：继续修，不进入设备步骤。

P1 固定构建 + 新版 mode1。前提：P0 通过；固定最终提交、内核/loader/payload/固件哈希与整串参数。成功条件：kind-5 时刻自有 GMU 路由对照在场、secure 预检给出通过或明确拒绝、零 MP_ASSIGN、零回复、零 CB3 写；停止后日志与 held 语义、一次 PSCI 后重新枚举分别记录。失败处理：诊断不达标即停，产物固定重跑一轮。残留未知：TZ 运行时保留、固件配套关系照旧，mode1 通过支持不了 secure 可用性。

P2 mode2 一次移交实验。前提：恢复负责人对 Astra 恢复报告 §3-§4 的准入逐条签署；残余风险单独批准（单条 SMC 永不返回、WAITQ pending、TZ/hypervisor 影响其他核心的 PSCI 或 USB、复位后旧 PA 归属未知、可能需要人工恢复）。成功条件：预检与区域计划完整；所有计划批 status=0/answer=0；逐批清单可回放；terminal 日志；零 kind-5 回复、零 START ACK、CB3 保持关闭、无 CB0 安全页映射；资源保留；复位结果单独列明。成功命名为「移交调用完成」，恢复成功另行记录。失败处理：任一批失败、WAITQ、interrupted 上限、PSCI 返回、意外 MEM_ALLOC/START ACK 都停止，不做逆向归属、不读旧页、不第二次移交。

P3 secure attach 诊断（后置）。前提：P2 归档并复核；优先选 START 之前、尚无新任务授权的检查点；保留既有 GMU 路由，只改候选 SID2/CB3 资源，不全局 reset SMMU、不重配 CB0/1/2。内容：共享空表页、无数据叶子、无 kind-5 回复；确切 MMIO 顺序、ACTLR 值与回读掩码先经审查确定，未确认前不写寄存器。成功条件：CB 配置回读达到审查定义的必要条件、路由视图与自有状态一致、观察窗口内无新 fault。失败处理：停止后续配置与回复，保留资源与最后日志，不盲目换 CB 重试。空表激活成功只验收配置动作与观察窗口，若空表可能吸收未知 SID2 请求，实验前需说明继承请求仍未排除。

P4 完整 kind-5 服务实验。前提：P3 通过且映射审查完成。顺序：预构建全部表与 PTE 并保持路由阻断 → 表页共享与数据移交全部成功 → 启用翻译 → 显式验收 → 回复一个已观察到的 kind 5/flags `0x1007` 形状；回复前确认映射成功、完整长度与发布完成（补厂商 void 缺口）。成功条件：START 最终 ACK；随后停在启动验收，scratch、shader、用户态各自另行验收。失败处理：任何一次共享、移交、CB 写入、同步、回复结果不确定，立即停止后续发布，保留相关页与元数据。

## 6. WAITQ 与恢复风险（单次诊断范围）

- 返回值 2/3：请求协议未完成、可能持有 wq/context；项目只保存 x1，未保存 x2/x3，不重发原请求、不补猜测的 RESUME/ACK，结束该 boot 的移交入口。厂商续传协议在 `vendor-qcom_scm-smc.c` L125-L169，本项目未实现。
- host stop 与定时返回依赖内核调度；单核陷入 SMC 时两者都可能无法执行，五秒 HFI 轮询预算中断不了同步资源处理中的 SMC。banner 与 park 日志分别确认回调进入与资源保留等待，两者都取消不了 TZ 请求。
- PSCI SYSTEM_RESET 若返回，复位未按成功路径完成；原命令先回 OKAY，主机 OKAY 确认不了复位。重新枚举只验收恢复可达：旧 PA 归属、WAITQ 请求取消、桥状态、CPU/GPU 访问安全均未确认。新 loader 的分配、清零与下轮上传可能复用旧物理页，本轮保留记录无法跨复位约束它；跨启动复用需要另行给出归属依据或隔离方案。
- 复位后首次动作须预先决定：默认只允许状态读取与日志保存；CPU 探测旧页、重跑实验都要单独授权。

## 7. 未决问题（主 agent / 用户裁决）

1. 先做孤立移交取得 ABI 与恢复数据，还是等 bridge/attach 前提明确后再实验；前者结论适用范围更小。
2. 是否接受复位后旧 PA 归属未知、PSCI 可能失效与人工恢复等残余风险；若不接受，mode2 继续关闭。
3. 复位后恢复验收止于 loader 可达加日志保存；若要求下轮内存复用，需另列安全归属依据或跨启动隔离方案。
4. CB3 板级适用性来源：解析本机已存 DTB/DTBO 静态声明，以及经授权取得 Android secure attach 成功后 `cbndx`/fwspec 观测（Astra 补充报告方案），本轮未采集；Android 结果只作平台适用性参考，XNU 逐次检查已知冲突。
5. P3 的确切 MMIO 顺序、ACTLR 值与回读掩码，由主报告审查确定后进入实现。
