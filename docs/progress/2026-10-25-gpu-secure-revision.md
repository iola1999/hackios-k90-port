# 2026-10-24 kind-5 安全分配修订轮（Codex 执行，待审阅；文件名沿用当时的 2026-10-25 写法，不移动）

上游输入：独立审阅结论与管理员修订指令（代码冻结解除后修订轮）。本轮范围限定为审阅意见对应的实现、测试、构建与文档修正；未接触真机，未推送远端，未变更 SCM function id（`0x42000c16` 经审阅复核：vendor `arm-smccc.h` 编码 SIP=2、STD=0、SMC64=1，实现保持）。内核提交 `ae841eb`（前序功能提交 `7786182`），父仓文档提交见本轮 gitlink。

## 1. 实现修订

- 物理地址检查失败统一保守保留：`adreno8_secure.c` 中数据页与页表页的 `kvtophys` 校验失败一律置保留标志，覆盖首次移交之前失败的情况。语义：首批 `MP_ASSIGN` 发出前失败的页面仍属 HLOS，代价是本次启动内安全路径关闭；首批之后失败则每页归属均按不确定处理，保留到冷重启。参数页自身的校验失败可回收重试，注释说明其从未移交、归属始终明确。代码内注释同时写明：恢复确认不得用 CPU 直接读取此前移交页面试探（读取被安全世界拥有的页会产生错误），冷重启对首次移交的恢复能力本身未经真机确认。
- 保留判定接入：`adreno8_memory_retained()` 并入 `adreno8_secure_lost()`，此前的未使用接口消除。
- 占用预检（主机可验证部分）：`adreno8_space_available()` 前置读取目标 context bank 的 `SCTLR`，非 0 即拒绝占用；S2CR 路由检查从仅 fault 类型扩展到任意类型（active 路由指向目标 context 此前漏检，属缺陷）。probe 观察读取范围从 context 0..2 扩到候选 context 3，纯读无写。
- 读副作用核对：预检仅读 SMR/S2CR/`SCTLR`，寄存器读取在 vendor `arm-smmu.c:239,688` 同样以普通读使用；主机测试断言三类拒绝路径写计数保持为 0。
- 真机侧与主机侧边界（写入代码注释）：`SCTLR==0` 只证明 HLOS 看到该 context 关闭，安全世界对同一 context bank 的保留对 HLOS 不可读，留给真机确认；secure space 的 TTBR、SCTLR 与 S2CR 路由由 `adreno8_space_on()` 在启用时写入，预检阶段不写任何寄存器。
- 依据与风险标注：SID 2 候选来自 vendor `sun-gpu.dtsi`（`gfx3d_secure` 在 kgsl SMMU 上 stream id `0x2`，与我们驱动的 GMU SID 5 同一 SMMU）；页表页 `{HLOS 读写, CP_PIXEL 只读}` 与移交失败即泄漏不回收策略对齐 vendor `qcom-io-pgtable-alloc.c:30-47,225`；vendor `kgsl_iommu.c:1575-1582` 为 secure 缓冲使用独立页表与独立 VA 段，本项目以单一 VA 分配器加普通页表占位映射替代，占位映射的风险（普通 SID 访问被安全世界拒绝属翻译行为，仅真机可观察；驱动不通过任一映射触碰该内存，主机测试覆盖驱动侧）写入 `adreno8_memory.c` 注释。任何路径都不得把 SID0 访问成功作为前提，现状无此依赖。

## 2. 主机测试修订（真实生产路径故障注入）

- `tools/test-adreno8-secure.py` 新增 `poison` 两模式：不可证明物理地址的页位于首批之前（无任何 SCM 调用）与位于批次边界之后（已有批次成功）两种时序，均断言统一保留、后续请求在发出 SCM 前拒绝。
- `tools/test-adreno8-memory.py` 从桩函数改为编译链接生产 `adreno8_secure.c`：kind-5 分配沿 `HFI 请求 → 内存 → secure.c → 脚本化 SCM` 完整链路执行，成功场景断言调用批次（1 次页表 + ceil(页数/32) 次数据）与 `QCOM_SCM_SVC_MP` 编码；`secure-fail` 模式注入最后一批数据失败，断言保留标志、`adreno8_memory_failed`、`adreno8_memory_retained()`、条目未完成，以及其后 kind-5 重放与普通 kind-4 请求均被拒绝且无新 SCM 调用。
- `tools/test-adreno8-smmu.py` 新增占用预检场景：context `SCTLR` 非 0、active S2CR 路由指向目标 context、fault S2CR 残留 CB 字段三种冲突均拒绝且写计数为 0；路由指向其他 context 的 active 流不冲突，启用成功。probe 观察新增 context 3 读取断言（各一次、写计数 0）。
- 全量 10 组主机检查两种页大小（4096/16384）全部成功；vendor 目录按本地 manifest 的 `tests.gpu_vendor_dir` 提供给审阅方（路径为本地私有，不入受控文档）。

## 3. 构建产物（受版本控制输入，无手工 Makefile 修补）

上一轮产物依赖手工修补的生成 Makefile，本轮以干净的受版本控制输入重建：容器 `kbuild` 内对 `/work/repo` 执行 `git fetch /src k90-port && git reset --hard FETCH_HEAD && git clean -xdf`（源码快照 = 内核提交 `ae841eb`），`XNU_URL=file:///work/xnu-tag-source bash xnu/apply.sh`（Apple 标签 `xnu-8796.121.2`，基线 `c54f35ca`，76 个补丁、131 个新增文件），`bash xnu-deps/setup.sh`，`bash xnu-build.sh -j8 BUILD_DSYM=0 KEXT_CREATE_SYMBOL_SET=/bin/true`。

构建后核验：`BUILD/obj/DEVELOPMENT_ARM64_BCM2837` 链接清单包含 `adreno8_secure.o`（由 `bsd/conf/files` 注册自动生成的规则编译，无需手工修补）；产物 `out/handoff-mach-secure` 大小 19,192,624 字节，SHA-256 `b9be06b844db7cc18199e5240337151525c6708c4e0d6c9263b863da8a490d74`，替代上一轮手工修补产物（旧 SHA-256 前缀 `8d1f463a`，其生成树含手工 Makefile 改动；该文件在干净重建中被同路径覆盖，本地已无存档，身份仅以哈希记录于 manifest 的 `secure_rebuild_2026_10_25.previous_hand_patched_sha256`）。产物以文件内容与 manifest 记录为准，消息中的哈希以两者复核后为准（交付消息曾出现一处抄写差异）。

## 4. 真机阶段 14 计划（修订后，待审阅放行）

- 前提：设备经 USB 传入 RAM 启动（系统盘边界沿用管理员约束）；boot-args `adreno8_keep=1 adreno8_return=0`；替换 payload 内核为本轮产物；启动健康检查按真机手册执行；记录与观察数据快照同格式的 kernel log 与截图。
- 动作：仅替换内核并启动，观察 HFI kind-5 应答与 START 流程，不新增寄存器写入、不执行 shmbridge 注册/ENABLE/DELETE（QTEE shmbridge 与 kind-5 的关系未知，桥状态未读取，状态明确前不尝试）。
- 成功判定（归属变更发生才算成功）：kind-5 安全应答 10 字且 `gmu_addr=0`、handle 一致；最终 START ACK。错误口径为同轮对比：实验启动与对照启动各自读取 GPU、HFI、SMMU 分项状态（启动步骤日志、GMU 状态寄存器、fault 状态、kind-5 应答序列），逐项对比实验与对照的差异；历史桌面的错误行总数只作背景，用作判定标准的做法已按审阅意见废止。桌面渲染仅作补充观察。
- 失败语义：任何非零或未知返回值、无应答、超时均按归属不确定处理，整批保留，日志出现「retained until cold reset」属预期保守路径，不算故障恢复动作。`WAITQ`（2/3）按失败保留，无续传。固定厂商源码副本 `vendor-qcom_scm-smc.c` L125-L169 实现了 WAITQ_SLEEP/WAKE 续传协议（a1 等待队列句柄、a2 调用上下文、a3 标志，另有 resume 与 wake-ack 调用，等待队列取回见 L104-L123），项目未实现该协议；返回值 2/3 之后请求终态未知，安全世界可能仍有未完成请求，保守保留是刻意实验限制，不能记成「请求已完成且失败」（2026-10-24 审查补记）。EBUSY 重试同样按失败上限保留处理，与厂商的重试写法对照见[审查记录](../analysis/2026-10-25-loader-review-findings.md) §3，两处写法有差异。
- 恢复边界：冷重启对此前移交内存的恢复能力对首次安全移交未经验证，不得声称一次试验调用即可解除未知前提；恢复确认以设备身份（`fastboot getvar` 与启动 cmdline）、启动健康与后续受控功能验证为准，安全内存重用需另行获得生命周期依据。禁止 CPU 直接读取此前移交页面试探。
- 主机验证与真机验证的分界：已主机验证的仅为寄存器配置与冲突检查、SCM 调用参数与失败处理、驱动侧不触碰移交页；真机待验证的是 secure 翻译行为（CB3 上 TTBR 走表、SID2 访问被安全世界允许、SID0 访问被拒绝的形式）、安全世界对 context 3 的保留状态、TZ 对移交失败的部分生效行为、冷重启恢复。后者不得写成已通过前提。

## 5. 状态与未验证项

- 推送状态：内核 `k90-port` 领先 origin 两个提交（`7786182`、`ae841eb`），父仓 `main` 领先文档提交，用户态与 origin 一致；本轮全部未推送，等待审阅结论。父仓 gitlink 随本轮文档提交更新到 `ae841eb`。
- 观察数据说明：`docs/progress/evidence/2026-10-24-gpu-baseline/` 两份快照为 softpipe 桌面观察数据（启动后约 35 秒与约 62 分钟窗口，稳态每 100 ms 窗口 42 次调用/6 次绘制），用作真机实验的错误行与窗口分布对照；不构成性能基线，内核身份未确认（所跑内核比 `handoff-mach-affinity` 记录产物小 512 字节）。
- 未验证清单：真机 `MP_ASSIGN` 实际应答；安全世界对 context 3 的保留；secure 翻译行为；冷重启恢复；QTEE shmbridge 与 kind-5 的关系；普通队列访问占位映射地址的真机表现（阶段 14 的 CP 普通队列不引用安全缓冲，无此访问）。
