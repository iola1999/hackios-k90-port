# A830 普通 HFI 与直接 ring 诊断

## 1. 运行范围

新增显式 `adreno8_direct_ring=1`，只接受完整 `adreno8=17 keep=1 return=0 adreno8_gmuclk=2 adreno8_secure_preflight=0`，`only`、`skip`、`empty_powerup` 均为 0；默认 `raw_nop=0` 验证 CP_INIT，`raw_nop=3` 只检查 SQE 启动前的配置并停止，`raw_nop=2` 在同一配置后要求 SQE 控制继承值为 0，再执行写 0 的控制访问对照。准入检查在阶段调用之前执行。默认 HWSCHED 路径保持既有行为，每次实验从 loader 新启动开始；同次启动只使用一种提交模式。

本轮只验证 CP_INIT 被消费、BR RPTR 前进和 idle。成功后也停止并保留内存、IOVA、时钟及 OOB，直到冷复位；`CP_READY` 保持关闭，后续 zap、scratch、context 和服务发布分别验收。当前 K90 固件能否运行该模式仍待真机确认。

## 2. 选择依据

固定 Linux 提交 `efbda69d92e6a4822c5f2d09910f547872a9498d` 的三处依据：

- [catalog](https://github.com/torvalds/linux/blob/efbda69d92e6a4822c5f2d09910f547872a9498d/drivers/gpu/drm/msm/adreno/a6xx_catalog.c#L3218) 明确包含 `0x44050001`、`ADRENO_8XX_GEN1`、gen80000 GMU／SQE／AQE、12 MiB GMEM 和 `a8xx_gpu_funcs`。
- [CP_INIT](https://github.com/torvalds/linux/blob/efbda69d92e6a4822c5f2d09910f547872a9498d/drivers/gpu/drm/msm/adreno/a8xx_gpu.c#L497) 通过普通 ring 提交，关键十字与当前命令一致。
- [首次调用](https://github.com/torvalds/linux/blob/efbda69d92e6a4822c5f2d09910f547872a9498d/drivers/gpu/drm/msm/adreno/a8xx_gpu.c#L793) 先于完整 powerup list 填充和 HWCG enable。

HWSCHED 的 AHB 超时配置及空 powerup 对照仍未取得 CP ACK，结果见[恢复记录](../progress/2026-10-25-gpu-resume-review.md)。普通 HFI 模式可检查独立的命令执行入口。A840 社区结果仅作方法参考，本轮验收只使用 K90 的实际运行结果。

## 3. 实现约束

- 复用现有 GMU 固件装载、SMMU、内存分配、寄存器访问和电源时钟检查。只增加固定模式分支和单 ring，不另建 allocator、提交框架或用户态接口。
- 普通 HFI 使用 168 字节表，三条队列位于缓冲偏移 `0x1000/0x2000/0x3000`，type 为 `0xa00|q`。HWSCHED 的 840 字节布局单独保留。队列发布的对齐、填充及屏障契约保持。
- 普通模式在阶段 8 完成 layout 后、阶段 9 前执行受限 NS TLB 失效对照：三个自有 context 均关闭、CM3 reset、GX off、全部可见 SMR 无有效项后，只发 NSNH 与 global sync；状态异常即停止。同步返回 0 已获真机确认，SQE 首次执行故障仍待定位。该操作的范围及单次 MMIO 阻塞边界见[恢复记录第 40 节](../progress/2026-10-25-gpu-resume-review.md#40-早期非安全-tlb-失效对照)。
- 普通模式跳过 HWSCHED VRB／trace 和相关特性；CM3 保持复位期间要求 GENERAL11 为 0，非零先停止。发送 CORE_FW_START、START 并完成时钟确认后才进入本模式 ready；MEM_ALLOC 和 CNTR_REGISTER 请求立即失败，安全移交调用数必须为零。
- GPU 使用 32 KiB READ／PRIV ring，独立 RW／PRIV shadow 页及清零的 powerup 页。首次 CP_INIT 前保留继承的 HWCG 状态，trusted range 为 0，OOB 后按主线顺序清零并读回两项 GBIF halt，再配置 SQE／AQE、RB_BASE／RB_CNTL 和 BR／BV RPTR 地址后启动 SQE。
- 普通 CB0 在路由为 fault、SCTLR 关闭期间写入并严格读回 `ACTLR=0x303`；活动上下文检查继续核对该值。该对照已确认写入生效，SQE 启动仍未取得下一条读取记录。
- 全部参数准入后、OOB 前，复用精确页表遍历核对 SQE／AQE 各 4 KiB 页的预期 PA、完整 READ／EXEC 属性和父表描述符；任一失败立即停止并保留资源。该检查仅读取页表元数据，真机两对象的 35 页已经通过，GPU 首次取指继续单独验收。
- `raw_nop=2` 完成输入发布和全部 ring 配置读回后，严格要求 SQE 控制继承值为 0，写回 0、执行屏障并严格读回 0，随后复用十秒健康检查；保持零 WPTR、零 CP_INIT。零值写入被忽略也可读回 0，结果只覆盖读值和观察窗口。原写 3 对照见恢复记录第 37 节；本轮来源与范围见第 42 节。`raw_nop=3` 保留原有不写 SQE 的配置对照；HWSCHED 的 `raw_nop=2` 保持原十字 NOP 含义。
- 发布十字 CP_INIT 后写 WPTR，按现有 AHB fence 检查写入结果。完成要求实际 BR RPTR 与 BR shadow 均为 10、GPU／GMU idle 且无新增 HFI／SMMU／CP 错误。BV RPTR 和 shadow 记录原值并检查合法范围；其必须前进至 10 的契约尚未确认。
- 两种提交模式保留独立 ready；失败永久关闭本模式，保留全部已暴露资源。各 ready 的消费者按运行模式选择，禁止跨模式接受。

## 4. 验证与失败处理

宿主测试编译实际生产 C，覆盖 4 KiB／16 KiB 页大小、两套队列 ABI、START 错误应答、意外资源请求、固件继承值、发布失败、RPTR／shadow 未前进、busy、HFI／SMMU 故障及超时，并用消融检查关键约束。既有 HWSCHED、context 和服务检查继续执行。单文件保持 1000 行以内，提交前独立审查新增状态、调用者和资源保留条件。

真机先核对 loader 身份和输入哈希，经 USB 将系统盘传入 RAM。日志分别记录 START、SQE 启动、WPTR、RPTR、shadow 和 idle；保留 USB 请求的开始时间与持续时间。任何失败后重新确认枚举和启动状态，复位触发时刻和来源保持待确认。CP_INIT 通过后再安排下一项实验。
