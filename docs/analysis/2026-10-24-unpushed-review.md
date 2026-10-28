# 未推送提交与待提交变更审查记录（2026-10-24）

本文记录 2026-10-24 对父仓库和 `hackios-xnu-kernel` 未推送提交及父仓库待提交变更的审查结果，按类别分节，每条给出位置、问题、触发场景、置信度和建议。审查只在主机侧进行：未操作真机，未提交，未修改被审代码，未做完整内核构建。文中代码路径相对 `hackios-xnu-kernel/`，行号对应该仓库提交 `c0716bf`；文档行号对应 2026-10-24 20:10 的父仓库工作树。

## 1. 审查范围与方法

- 父仓库 `main` 领先 `origin/main` 15 个提交（`de4a0c5`..`a05b96b`，2026-10-24 05:01–11:49），只改文档和 gitlink。工作树另有 5 个文档修改、gitlink 改指 `c0716bf`、4 个未跟踪文档和未跟踪的 `logs/` 目录。
- `hackios-xnu-kernel` 的 `k90-port` 领先 `origin/k90-port` 33 个提交（`7786182`..`c0716bf`，2026-10-24 05:01–20:09），涉及 28 个文件，新增 5939 行、删除 485 行；工作区无未提交改动。`hackios-xnu-userland` 与 origin 一致，不在范围内。
- 方法：逐个提交阅读 diff 与提交说明；运行主机测试；在临时副本中做变异实验；MP_ASSIGN 参数对照本地固定版本厂商源码副本（目录见本地 manifest 的 `tests.gpu_vendor_dir`）；USB 事件语义来自反编译仓库内 annibale 固件 `UsbDeviceDxe.efi` 与 `UsbfnDwc3Dxe.efi`；`uefi/mu-silicium.patch` 在临时副本中对 Mu 根 `5b83e7d` 做 `git apply --check`；通过 GitHub 公开 API 只读查询上游提交。
- 主机测试：`test-adreno8-config/firmware/gpu/handoff/hfi/hwsched/logcheck/memory/quiesce/secure/smmu/zap`、`test-annibale-input`、`test-frames`、`test-loader-buildid`、`test-loader-lifecycle`、`test-mkpayload`、`test-xnu-payload-terminal` 共 18 个全部成功。`test-adreno8-gpu.py` 需要 `--vendor-dir`，使用本地 manifest 记录的目录运行；`test-video-scroll.py` 需要视频输入且不在本次改动范围，未运行。
- 严重度：高表示推送或上机前需要处理，否则可能导致设备失联、安全门禁误判或推送后仓库引用不完整；中表示影响正确性、可维护性或测试判别力；低表示注释、口径或冗余问题。置信度：「已验证」指经代码阅读、主机复现或变异实验确认；「推测」指依赖未核实的前提。

## 2. 结论汇总

本轮没有找到「页已移交或归属不明，但内核随后释放、复用或写入」的路径，MP_ASSIGN 的调用号、参数布局和返回判据与厂商实现一致。需要优先处理的问题集中在四处：严格预检判据在代码中已放宽，已提交文档仍写未放宽；新 loader 的 USB 所有权模型会在拔插线或主机重新枚举后让 loader 永久收不到命令，返回路径还有一处核心关闭状态的竞态，目前不适合部署；父仓库 HEAD 引用的内核提交尚未推送；文档日期整体晚一天，并有失效链接和总账过长等问题。

高、中严重度条目如下，低严重度条目见各节。

| 编号 | 类别 | 严重度 | 摘要 | 处理时机 |
|---|---|---|---|---|
| C1 | 推送流程 | 高 | 父仓库 HEAD 的 gitlink `3ce4102` 不在 kernel 远端 | 推送前 |
| G1 | GPU 驱动与文档 | 高 | 预检判据已改为只判 M 位，已提交文档写「未放宽」 | 推送前修文档，mode 2 放行前签署 |
| L1 | loader | 高 | USB 状态变化后 OUT 端点永久停用，loader 收不到任何命令 | loader 部署前 |
| L2 | loader | 中 | 内核正常返回后单次 AFFINITY_INFO 查询有竞态，可能误判 held | loader 部署前 |
| L3 | loader | 中 | `loader.c` 净增 475 行，违反 1000 行约定 | 合并前 |
| L4 | loader 工具 | 中 | `--forbid-cmd` 帮助写前缀语义，实现按键名匹配 | 下次编写审批命令前 |
| G2 | GPU 测试 | 中 | 删除参数页、表页或数据页的 cache 清理，测试全部仍然成功 | mode 2 放行前 |
| U1 | UEFI | 中 | 「payload 区域在内存图中保留」对 annibale 不成立 | 下次 UEFI 维护 |
| U2 | UEFI | 中 | 在当前 Mu 树上运行 `uefi/export.sh` 会删除 overlay | 再次运行该脚本前 |
| U3 | UEFI 测试 | 中 | payload 解析测试有 4 个变异无法检出 | 下次修改 XnuLoader 前 |
| U4 | UEFI 测试 | 中 | 测试写死生产文件 sha256，任何改动都会在断言前退出 | 同上 |
| S1 | 帧统计测试 | 中 | 每秒帧数输出没有断言，N 与 N-1 的差错测不出 | 下次修改 frames.py 前 |
| P1 | 仓库卫生 | 中 | `logs/` 未被忽略，含本机用户目录绝对路径 | 下次 `git add` 前 |
| D1 | 文档 | 中 | 文件名与正文中的「2026-10-25」实际发生在 2026-10-24 | 推送前确认处理方式 |
| D2 | 文档 | 中 | `docs/plan/2026-10-24-gpu-handoff.md:66` 链接失效 | 提交前 |
| D3 | 文档 | 中 | 总账第 8 行单条 4434 字 | 提交前 |
| D4 | 文档 | 中 | `ec53bac` 之后的内核提交没有进度记录 | 提交 gitlink 前 |

## 3. GPU 驱动（adreno8）

- **G1 高｜严格预检判据已放宽，已提交文档仍写「未放宽」**。位置：`xnu/files/bsd/dev/adreno8_smmu.c:475`（提交 `ec53bac`）；[预检门禁记录](../progress/2026-10-25-gpu-secure-preflight.md) 第 78、86、103 行；[总账](../plan/2026-10-23-tracking.md) 第 8 行。问题：`ec53bac` 把 CB3 `SCTLR` 判据从「非零即拒」改为只判 bit 0（M 位），另加路由视图命中数和 GMU 自有路由读回两项条件。父仓库已提交的 §12（`a05b96b`，早于 `ec53bac`）写的是「判据『非零即拒』保持不变、未放宽」，只有未跟踪的 [MiCode 调研记录](2026-10-25-micode-annibale-reference.md) 第 70 行提到判据已改。触发场景：按 run003 读数（CB3 `SCTLR`=`0x96cc51a`，bit 0 为 0；路由视图 hits 0；match 1 为 `0x80000005`/`0x302`，与 GMU 路由期望值一致），当前代码的预检会通过，`adreno8_secure_preflight=2` 时会实际发出 MP_ASSIGN；按文档操作的人会认为同样的设备状态仍会被拒绝。置信度：已验证（代码与 run003 日志数值对照）。建议：推送前在预检门禁记录与总账写明判据变更、生效提交，以及「run003 状态下预检会通过」；mode 2 放行时由负责人对新判据单独签署。
- **G2 中｜测试无法发现 cache 清理被删除或挪位**。位置：`tools/test-adreno8-secure.py:105` 的 `assert(clean_at_call[call] >= 1)` 使用全局累计计数，任何一次表页或参数页清理都能让它成立。触发场景：以下变异在 secure、memory、handoff 三组测试中全部成功：删除 `adreno8_secure.c:137` 的参数页清理；把该清理挪到 `sources`/`extended` 写入之前；删除 `adreno8_secure.c:300` 的表页清理；删除 `adreno8_memory.c:151` 的数据页清理。只有同时删除 137 和 300 两处，secure 测试才失败。生产代码当前的顺序正确，问题只在测试。置信度：已验证（第一项变异复现过，并确认测试编译的是改动后的副本）。建议：mock 记录每次清理的地址和长度，假 SCM 入口断言「上次 SCM 之后有一次清理覆盖参数页前 672 字节」，并断言数据页和表页在各自批次之前清理过。
- **G3 低｜启动探测读取 CB3 时没有范围检查**。位置：`adreno8_smmu.c:75`。`adreno8_smmu_layout` 只证明到 CB2 落在映射范围内，`adreno8_get` 不做越界检查。触发场景：IDR1 给出 `(pages + 4) * page > 0x40000` 的布局（例如 64 KiB 寄存器页）时，step 8 会读到映射块之外。当前设备 page 为 0x1000、pages 为 32，CB3 位于 0x23000，不受影响。预检入口 `adreno8_smmu.c:574` 起已有同样的检查。置信度：已验证（代码阅读）。
- **G4 低｜mode 0 的注释与行为不符**。位置：`adreno8.c:36-40`、`adreno8_memory.c:176-178`。注释写「0 关闭，1 只做预检」，实际 `adreno8_memory.c:212` 先调用 `adreno8_secure_preflight` 再按模式分支，mode 0 与 mode 1 执行同一组 MMIO 读（CB3 `SCTLR`、全部 SMR、有效项的 S2CR、GMU 槽位），只差一行日志。handoff 测试和预检门禁记录 §1 都按这一行为编写，属于有意设计，需要改的是注释。置信度：已验证。
- **G5 低｜预检注释与实际读取范围不符**。位置：`adreno8_smmu.c:557-562`。注释写「run before every secure page-table or data MP_ASSIGN」，实际每个 kind-5 请求只在首批之前运行一次；注释写「only touches … registers the boot probe already reads」，实际启动探测只读 SMR/S2CR 0..15，预检读取全部已探测的匹配项，设备上为 24 项。这些读取都在范围内。置信度：已验证。
- **G6 低｜`adreno8_secure.c` 及相关文件中不准确的注释**。置信度均为已验证。
  - `adreno8_secure.c:14` 写「vendor QCOM_SCM_EBUSY_MAX_RETRY」，读起来与厂商等价。厂商 `vendor-qcom_scm-smc.c` L196-L200 最多调用 22 次、睡眠 21 次；本驱动调用 20 次、睡眠 20 次，最后一次 EBUSY 之后多睡 30 ms。测试注释「vendor's 30 ms spacing」「vendor retry bound」有同样的问题。[审查记录](2026-10-25-loader-review-findings.md) 第 11 项已要求文档不得声称两者一致，代码注释还没有同步。
  - `adreno8_secure.c:12` 只写了厂商的 `BATCH_MAX_SECTIONS`。厂商 `vendor-secure_buffer.c` L27、L277-L278 另有 `BATCH_MAX_SIZE=SZ_2M` 上限，本驱动只按 32 项分批，合并后的单批可能超过 2 MiB。当前 kind-5 大小 0x138000 小于 2 MiB，实际没有差别；厂商设该上限的原因未核实。
  - `adreno8_secure.c:90-93` 写「freed and retried on the next call」，实际参数页失败后经 `adreno8_secure_xfer_abort` 进入终止态，不会重试。
  - `adreno8_secure.c:214-223` 讨论「首个 MP_ASSIGN 之前」的情况，这一分支不可达：`assign_data` 总在表批之后运行，`assign_plan` 在置 ATTEMPTED 之前已检查过全部数据页。
  - `adreno8_secure.c:397` 写「have an unprocessed tail」，第 405 行的条件允许 `secure_tables == table_count`。
  - `adreno8_secure_private.h:29-30` 写「or the driver could not stage the batch」，没有调用方对应这种情况。
  - `adreno8_memory.c:29-30` 把保留归因于 `adreno8_secure_lost`，实际 lost 置位时 `adreno8_memory_count` 一定非零；删掉 `|| adreno8_secure_lost()` 的变异在所有测试下都成功。
- **G7 低｜`adreno8_secure_xfer` 入参拒绝分支不进入终止态**。位置：`adreno8_secure.c:402-410`。该分支直接返回 false，`adreno8_xfer_state` 保持 NOT_STARTED，与头文件「Every later call returns false without issuing SCM calls」的契约不一致。当前唯一调用方 `adreno8_memory_alloc_xfer` 已保证这些条件，分支不可达；即使到达，调用方也会置 `adreno8_memory_failed`，后续分配仍会被拦住。置信度：已验证。建议：删除该守卫（见 G8），或在分支内调用 `adreno8_secure_xfer_abort`。
- **G8 低｜可删减的复杂度**。依据是变异实验中删除后所有测试仍然成功，或代码中没有读取方。
  - `adreno8_assign.lost` 与 `adreno8_secure_lost()` 没有影响运行行为的读取方：`adreno8_secure.c:99` 的检查在终止态下不可达（第 391 行先返回），`adreno8_memory_retained` 中的这一项与 `adreno8_memory_count` 重复。
  - `SECURE_XFER_ATTEMPTED` 没有读取方能区分它，所有读取都只判断 `!= NOT_STARTED`。
  - `entry->terminal`（`adreno8_memory.c:18,165,392`）等价于「`alloc_secure` 返回非空」；有顶部门控后，secure 条目的 `from_hfi`/`request` 记录没有读取方。
  - `adreno8_space_available` 的 `strict` 参数（`adreno8_smmu.c:440-505`）：strict 分支在自身块内返回，与普通路径只共享 3 行边界检查，`adreno8_secure_preflight` 又把这 3 行重复了一遍，可拆成独立函数。
  - `adreno8_secure_xfer` 入参守卫（402-410 行）及其专门测试、`adreno8_secure_xfer_abort` 的状态守卫（369-371 行）在唯一调用方下不可达。
  - `secure_tables` 游标服务于增量移交，一次性实验不会续传。
  - 日志打印与参数页内容一致这一点，`adreno8_logcheck.py`（245 行）及其自测（129 行）与 `test-adreno8-secure.py` 的 `check_regions`/`check_table_call`/`check_data_call` 各验证一遍，而打印取自刚复制进参数页的同一个 `regions[]`。
  - `adreno8_memory_retained` 中的 `adreno8_secure_space.is_on` 在任何路径下都不会为真。
  - `adreno8_memory.c:170-195` 有 26 行设计背景和真机未知项说明，更适合放进文档。

## 4. loader（xnuloader）

- **L1 高｜USB 状态变化后 OUT 端点永久停用，loader 收不到任何命令**。位置：`xnuloader/loader.c:4059-4069`（`usb_lost_on_unconfirmed`）、`4195-4198`（`usb_rx`）、`4574-4596`（`usb_command_loop`）。触发场景：空闲命令循环中 `usb_rx` 一直挂着一个 OUT 接收；此时出现任一 DeviceStateChange（拔插线、主机总线复位、主机挂起后恢复），代码把 `usb_out_lost` 置 1 且之后不再清除；此后 `usb_rx` 只调用 `usb_wait(0xff)` 并返回 -1，空闲状态下 `usb_wait` 没有时间上限；`reboot`、`oem stop`、`oem log`、`upload` 都无法送达，只能长按按键复位。内核运行中同样适用。旧代码在拔插后会重新挂上接收。反编译仓库内固件的结果：`UsbDeviceHandleEvent` 每次进入 CONFIGURED（包括挂起恢复和复位后重新配置）都上报 Connected，进入 DETACHED 时上报 Disconnected；复位和断开会对活动端点发 DWC3 End Transfer，最多等 500 ms，完成后投递带原 buffer 的 Aborted 完成通知，映射为 Cancelled；End Transfer 超时则不投递；挂起恢复不取消传输。置信度：代码路径已验证（读代码并用提取的生产代码块在主机复现：拔线后 `lost=1`，重插后 `connected=1 lost=1`，下一条命令 `sends=0`）；固件行为来自反编译、未上机；主机触发挂起或复位的频率为推测。另外 `usb_rx` 第 4196 行注释「bounded and watchdog-feeding」在空闲状态下不成立，annibale 上 `wdt_arm` 也不启用看门狗（`loader.c:2768-2770`）。建议：匹配原 buffer 的 Cancelled 通知释放所有权并允许重新提交；没有先收到 Cancelled 的 Connected 继续等待原请求，既不重新提交也不标记停用；该规则需要上机验证。新 loader 部署后，[真机手册](../plan/device-test-playbook.md) §5 中「恢复 USB」一类操作需要按新行为改写。
- **L2 中｜内核正常返回后可能误判为 held**。位置：`loader.c:3195-3210`（`lc_after_return`）；返回桩 `loader.c:1128-1141` 先写 `other_cpu_done`、`dsb sy`、`sev`，然后才发 CPU_OFF。触发场景：loader 看到 done 后立即进入 `lc_after_return`，对内核所在核心只查一次 AFFINITY_INFO；此时 PSCI 可能仍在处理 CPU_OFF 并回答 ON。TF-A 在断电流程完成后才把状态设为 OFF，Linux 的 `cpu_psci_cpu_kill` 因为同样的竞态轮询 100 ms。后果：正常返回被判为 `returned-held`，上传和运行命令全部被拒，跳过 `hc_take_back`，不收集录屏和录音，中断保持屏蔽，只能重启 loader 并重新上传约 2.4 GB 系统盘（约 62 秒）。旧代码从 `i=1` 开始查询，从未查过内核所在核心，没有历史实测数据。置信度：竞态由代码确认；真机发生概率为推测。建议：对每个核心有界轮询（100 ms 到 1 s）后再下结论。
- **L3 中｜违反 AGENTS.md §2 行数约定**。`loader.c` 从 4275 行增至 4750 行，净增 475 行（新增 628 行，其中约 208 行为注释）。文件头第 12-15 行只说明了为什么不重构整个文件，没有说明新增部分为什么不能拆。LC、LC-USB、LC-FB、LC-BID、LC-RETURN 各块本身可以独立编译，可以按 `platform_private.h` 的方式拆成单独文件、在同一编译单元中 `#include`，测试也能直接编译这些文件，不再需要用正则提取标记块。置信度：已验证。
- **L4 中｜`--forbid-cmd` 的帮助文字写前缀语义，实现按键名匹配**。位置：`xnuloader/mkpayload.py:20,52`（帮助与说明）、`:101`（实现 `t == bad or t.startswith(bad + '=')`）。触发场景：按帮助文字理解写 `--forbid-cmd adreno8`，期望拦住全部 `adreno8_*` 参数，实际 `adreno8_keep=1` 能通过，退出码为 0。置信度：已验证（实测）。建议：统一帮助文字与实现，审批命令中逐个列出完整键名。
- **L5 低｜3 秒超时会永久停用 IN 端点**。位置：`loader.c:4180-4182`。触发场景：live、held 或固件异常状态下，主机在 `upload`（`get_staged`）途中停顿超过 3 秒，本次会话之后所有应答都无法发送；命令仍会执行，`reboot` 仍然有效，但主机看不到回复。置信度：已验证（代码路径）。
- **L6 低｜held 时 `reboot()` 仍走 UEFI 复位**。位置：`loader.c:856-866`。注释写「reset without touching storage」，代码调用 `ST->rt->reset_system`，会经过 UEFI 复位回调；annibale 的 USB `reboot` 分支（`loader.c:4498-4509`）正是为了避开这些回调才直接用 PSCI。影响一次性模式结束时（`loader.c:4748`）和非 annibale 平台的异常分支。置信度：代码已验证；回调是否访问存储为推测。
- **L7 低｜同核运行路径在 held 判定前恢复中断**。位置：`loader_return_stub`（`loader.c:1001` 附近）在 `lc_after_return` 之前执行 `msr daif` 恢复中断，判为 held 时中断已经打开，与另一核心路径「held 时保持屏蔽」的规则不一致。置信度：已验证。
- **L8 低｜提交说明和注释与代码不符**。置信度：已验证。
  - `795c1a6` 说明「日志与块写入在无活跃看守时才访问日志分区」，与 `loader.c:497` 相反：held 或固件异常时，只有看守进行中才允许访问日志分区。
  - `795c1a6` 说明「watch 轮询 kernel_live 魔数」，`lc_watch_round` 不读魔数，魔数只在启动前查找一次。
  - `795c1a6` 说明「异常处理…走复位路径」，annibale USB 模式下的异常分支（`loader.c:2797-2805`）不复位，置 `firmware-fault` 后等待主机发 reboot。
  - `xnuloader/build.sh:17,26` 提到「build manifest」和「a test build must set it」，脚本并不生成清单；`common/build.sh` 调用 loader 构建时不传 `BUILD_ID`，默认产物报告 `unknown`。
- **L9 低｜`tools/stage-system.sh` 没有覆盖新增的 held 状态**。位置：`tools/stage-system.sh:33` 用子串匹配 `running`、`hung`、`no-such-core`，能覆盖 `hung-held` 和 `no-such-core-held`，覆盖不到 `returned-held`、`checkpoint-held`、`early-exception-held`、`selftest-ok-held` 和 `firmware-fault`。这些状态下主机侧检查通过，要到 loader 拒绝 `oem ramdisk` 时才报出笼统的错误。置信度：已验证。
- **L10 低｜测试覆盖与判别力**。置信度：已验证。
  - `tools/test-loader-lifecycle-harness.py:135-136` 自行定义了 USB 枚举，设备状态取值与 `xnuloader/efi.h:219` 相反（harness 中 Disconnected=0、Connected=1，`efi.h` 中 Connected=0、Disconnected=1），union 也少了 `raw[8]`；测试内部自洽所以能通过，`efi.h` 写错时测不出来。
  - `usb_idle_change_stops_nothing`（harness 第 599 行附近）只覆盖没有挂起请求的情况，真实空闲循环中 OUT 一直挂着；没有场景驱动 `usb_command_loop`，L1 测不到。
  - `lc_after_return` 的测试把 AFFINITY_INFO 当作瞬时完成，L2 测不到。
  - wiring 检查匹配注释原文和已删除的标识符，任何注释改动都会让测试失败，其中历史名称的检查在运行时没有作用。
  - 变异 `mut_already_on_const` 改的是生产逻辑没有用到的常量；`PSCI_E_NOT_SUPPORTED`（`loader.c:385`）与 `PSCI_NOT_SUPPORTED`（`loader.c:1053`）重复定义。
  - `mkpayload.py` 的 NUL 校验从命令行调用不到（argv 不能携带 NUL），只有进程内注入 argv 的测试能覆盖；`--require kernel` 不带 `=` 时直接抛出 Python traceback，异常发生在写输出之前，不会留下输出文件。
- **L11 低｜不可达的防御代码，注释夹带评审历史**。置信度：已验证。
  - `usb_notification` 中 `sub == NULL` 分支（`loader.c:4101-4104`）不可达。
  - `write_logs` 与 `run_on_other_cpu` 中的 `firmware_fault` 条件（`loader.c:497`、`2693`）在 annibale 上不可达：annibale 的异常分支不返回，非 annibale 分支不置 `firmware_fault`。
  - 按仓库内固件，transfer 事件大小固定为 24 字节、状态事件为 4 字节，「事件过短则全部停用」的分支在这版固件上不会触发。这一点也消除了「固件不按预期填写 size 导致首条命令就停用」的顾虑，前提是真机运行的正是仓库内的固件二进制。
  - 注释中出现「rev1 review section 3」「rev3 review」「ruling 2026-10-25」（`loader.c:368,455,2649` 等）这类评审过程记录，按注释规范应放在提交说明或文档中，注释只保留当前有效的约束。

## 5. UEFI 覆盖层与帧统计工具

- **U1 中｜「payload 区域在内存图中保留」对 annibale 不成立**。位置：`uefi/files/Silicon/Silicium/SiliciumPkg/Library/BootManagerLib/XnuLoader.h:5-6`、`XnuLoader.c:64`；`xnuloader/loader.c:47` 的 `PAYLOAD_MAX_SIZE` 注释有同样的假设。问题：Mu 树 `Platforms/Xiaomi/annibalePkg/Library/MemoryMapLib/MemoryMapLib.c` 没有 `0xF0000000` 条目（redwood overlay 中有，类型为 Reserv）；真机 loader 打印的内存图（[loader 调试数据](data/2026-10-23-loader-debug.txt) 第 85 行）中 `e3720000 - fc800000` 为 type 7，即空闲内存，覆盖整个 payload 区域。因此「区域可读」在 annibale 上成立，「区域被保留、BDS 之前不会被改写」不成立。触发场景：4 GiB 以下的分配增长到该区间，或有固定地址分配落入其中时，payload 会在 XnuLoader 读取前被改写；XnuLoader 只校验 magic 和长度，没有完整性校验。置信度：区域未保留已验证；实际被覆盖为推测，目前实测未出现。修正需要落在 annibalePkg，而 overlay 中目前没有 annibalePkg 的维护来源。
- **U2 中｜在当前 Mu 树上运行 `uefi/export.sh` 会删除 overlay**。位置：`uefi/export.sh:7-14`。当前 Mu 的 HEAD 是本地提交 `87416d2`，BootManager.c 的改动已提交在其中，树中没有 `redwoodPkg`、`redwood.toml`、`Binaries/redwood`。运行该脚本会：把 BASE 写成上游不存在的 `87416d2`；把 patch 改写为只含未提交差异，丢失 BootManager.c 的改动并混入 XnuLoader.c/h；执行 `rm -rf files` 后在复制 `redwoodPkg` 时失败退出，overlay 已被删除。置信度：已验证（阅读脚本并核对 Mu 树状态，未实际执行）。建议：脚本开头加入拒绝条件，或在 README 中写明暂停使用。
- **U3 中｜`tools/test-xnu-payload-terminal.py` 的场景缺少判别力**。位置：第 252-266 行。触发场景：对生产源码做以下变异，测试全部通过：删除 magic 判断；删除 MAX 上限；游标前进改为不按 16 字节对齐；游标固定前进 24 字节。原因是 missing_magic 场景的 Size 为 0，size_too_big 场景后面全是 0，所有条目长度都是 16 的倍数，loader.efi 前面从来没有需要跳过的条目。对照变异（删除越界检查、删除 Size==0 检查、`>` 改为 `>=`）能被检出。置信度：已验证。建议：坏 magic 和超长场景后面放一个合法的 loader.efi；增加「17 字节条目加 loader.efi」场景，并断言 loader.efi 的偏移。
- **U4 中｜测试写死生产文件 sha256**。位置：`tools/test-xnu-payload-terminal.py:37-43,319-328`。改动 XnuLoader.c、XnuLoader.h 或 BootManagerLib.inf 的任意一个字节（包括注释），测试都会在断言之前退出，修改代码的人必须先改哈希常量才能用该测试检查改动；同一份内容因此有 overlay、Mu 文件、patch、哈希常量四处副本。默认被测根是 Git 忽略的本地 Mu 克隆，新克隆上会直接报 cannot read。置信度：已验证（追加一个字节后退出码为 1）。建议：改为比较 overlay 与被测根中的同名文件是否逐字节一致，inf 只保留第 346-348 行已有的内容检查。
- **U5 低｜BootShim 在没有 payload 时不清除旧 magic**。位置：`uefi/mu-silicium.patch:10-28`（`_NoPayload`），对应 `XnuLoader.c:7-10`。触发场景：DDR 内容跨复位保留时（[UEFI 构建记录](annibale-uefi-build.md) 第 83 行记录 Qcom warm reset 保留 DDR，loader 的 `fastboot stage` 也会写 `PAYLOAD_BASE`，见 `loader.c:4374`），启动一个不带 payload 的镜像会启动上一轮留下的 loader.efi，与注释「missing payload 进入停机」不符。置信度：推测（取决于 DDR 是否保留）。shim 不在本次提交的改动范围内。
- **U6 低｜payload 大小上限的边界不一致**。位置：`XnuLoader.c:66` 的 `Size > MAX` 允许 Size 等于 MAX，此时结束位置为 base+8+MAX，超出 64 MiB 区域 8 字节。同一区域的上限有三种：`mkxnuimg.py:62` 为 `MAX-0x1000`，loader 的 download 为 `MAX-0x100000`（`PANIC_LOG_BASE` 位于末尾 1 MiB），这里为 MAX。只有畸形 payload 会触发，annibale 上多出的 8 字节仍是可读 RAM；测试的主机缓冲开到 `MAX+4096`，看不出这个差距。置信度：已验证。
- **U7 低｜`uefi/BASE` 与验证所用的树不一致**。BASE 记录 `e51cd877`；Mu 根 `5b83e7d` 记录的上游提交是 `42fe5637`，比 BASE 新 6 个提交。两者之间 BootShim 和 BootManagerLib 没有变化，patch 同样能应用，但 SiliciumPkg、QcomPkg、Mu_Basecore 有差异，`apply.sh` 检出的树与验证时的树不同。置信度：已验证（上游提交经 GitHub API 查询）。建议：BASE 改为 `42fe5637`，或在文档中注明差异。
- **U8 低｜patch 中 `PlatformBootManagerUnableToBoot` 存在不可达代码**。位置：`uefi/mu-silicium.patch:486-505`。`XnuLoaderMain` 改为 noreturn 后，其后的 `DeviceBootManagerUnableToBoot`、`DisplayBootGraphic`、`Stall`、`ResetSystem`、`CpuDeadLoop` 都执行不到，删除不影响行为。置信度：已验证。
- **U9 低｜`XnuLoader.c:60-64` 的长度来源注释不准确**。注释称 `Header->Size` 是唯一的长度来源并改用减法，实际 `Entry->Size` 也是长度来源，第 71 行仍用指针加法（有上限检查，结果安全）。置信度：已验证。
- **U10 低｜`test-xnu-payload-terminal.py` 中的冗余**。第 297 行的 `head` 赋值后未使用；第 355 行 `line not in ("",)` 恒为真；wfi/wfe 在第 288 行和第 340 行各检查一次；第 350 行的 `mkdtemp` 不清理，`$TMPDIR` 下已有多个 `xnu-terminal-*` 残留；第 122-168 行的 forbidden 桩和第 339-341 行的字符串清单对应已删除的实现，只要 `BS_STUB` 不含这些成员，重新加回的调用会直接编译失败。置信度：已验证。
- **S1 中｜每秒帧数输出没有断言**。位置：`tools/frames.py:143,174,181`。把分子改成 `(len+1)/whole`（N 与 N-1 的差别）或把分母换成 100 ms 以下间隔之和，三处输出都能通过 `tools/test-frames.py`；目前只有次级速率 `34.9` 有断言。置信度：已验证。建议：slow_frame 用例断言 `45.5 a second`（4 个间隔 / 88 ms），long_stalls 用例断言 `7.3 a second`（5 个间隔 / 686 ms），同手势与全体统计各加一处。
- **S2 低｜阈值边界没有样本**。没有恰好 18.0 ms 或 34.5 ms 的间隔，`>` 改为 `>=` 能通过测试；判定阈值在 (16, 20) 或 [20, 40) 内任意改动、只要标签不变，测试都能通过，docstring 第 6 行「printed thresholds are the ones the code counts at」只验证到这个范围。置信度：已验证。
- **S3 低｜`frames.py` 中的冗余**。第 137 行 `over2` 为本次提交引入且未使用；第 125 行 `b['done'] >= a['done']` 恒为真（第 112 行已按 done 排序）；第 44-45 行的空列表分支不可达；第 109 行 `draws` 未使用（存量）；主统计的格式串在第 142-145、173-177、180-184 行复制了三份，已出现 `:3.0f` 与 `:.0f` 混用。置信度：已验证。
- **S4 低｜慢帧归因包含 100 ms 以上的停顿，需作者确认**。位置：`frames.py:136,150-159`。测试中 20/50/100/500 ms 四个间隔的 idle 均值为 160.0，主要由停顿决定。提交说明写明这是有意统一的口径，需要作者确认该 idle 读数是否符合预期。
- **S5 低｜「N times」统计的是段数**。位置：`frames.py:129-141`。只统计至少有一个间隔的段：同一手势做 3 次、其中一次只有 1 帧时输出「2 times」，`test_short_windows` 固定了这一行为，读者容易理解为手势次数。置信度：已验证。

## 6. 文档与总账

- **D1 中｜文件名与正文中的「2026-10-25」实际发生在 2026-10-24**。涉及 [预检门禁记录](../progress/2026-10-25-gpu-secure-preflight.md)、[安全分配修订记录](../progress/2026-10-25-gpu-secure-revision.md)、[审查记录](2026-10-25-loader-review-findings.md)、[MiCode 调研记录](2026-10-25-micode-annibale-reference.md)、[安全翻译方案](2026-10-25-secure-translation-plan.md) 五个文件名及其标题，以及总账、交接计划、真机手册、[GPU 加速目标](../plan/gpu-acceleration-goal.md) 中的「10-25」时间标注。依据：两个仓库的全部提交时间都在 2026-10-24（+0800）；run003 记录的 epoch `1792813370` 换算为 2026-10-24 11:42:50 CST；本地 `evidence/2026-10-25-gpu-preflight/` 目录的修改时间为 2026-10-24 11:45。置信度：已验证。建议：由负责人决定改名还是在文档中注明；改名需要同步修改所有页内与跨文档链接、本地 evidence 目录名和 manifest 中的引用。
- **D2 中｜失效链接**。位置：[交接计划](../plan/2026-10-24-gpu-handoff.md) 第 66 行（未提交修改）的 `[审查记录](2026-10-25-loader-review-findings.md)` 解析为 `docs/plan/` 下不存在的文件，应为 `../analysis/2026-10-25-loader-review-findings.md`。置信度：已验证（脚本检查全部变更文档的相对链接，只有这一处失效）。
- **D3 中｜总账单条过长**。位置：[总账](../plan/2026-10-23-tracking.md) 第 8 行，单条 4434 字；推送前的 `origin/main` 版本中没有超过 800 字的行。AGENTS.md §5 要求总账「保持简练（一项一行），细节写进各条目链接的专门文档」。建议：压缩为当前状态加链接，过程细节留在预检门禁记录中。
- **D4 中｜`ec53bac` 之后的内核提交没有进度记录**。`6983430`（收窄移交实验）、`90c4a25`、`06f9088`、`6a734f5`、`6259bd1`、`8064f7e`、`fd6d9ae`、`6012234`（MP_ASSIGN 逐批日志）、`313033a`（PAGE_SIZE 断言）、`795c1a6`（loader 生命周期）、`782b630`（build-id）、`2a78897`（mkpayload）、`08f73e7`（frames）、`c0716bf`（UEFI 同步）在 `docs/progress/` 中都没有对应记录。目前只有未提交的总账新增行按哈希提到 loader 第六轮和 parser `8907055`，审查记录 §5、§7 覆盖了部分内容。工作树中的 gitlink 已指向 `c0716bf`，而预检门禁记录与交接计划仍以 `bd8eca5`/`3ce4102` 作为当前内核。建议：提交 gitlink 前补一份进度记录，写明改动、测试与未验证项。
- **D5 低｜loader 验收对应的版本与 HEAD 不同**。总账和真机手册写第六轮验收固定 loader `71082b55…`，这是 `795c1a6` 的 `loader.c`；HEAD（`782b630` 加入 build-id 之后）的 `loader.c` sha256 为 `af54316e…`。build-id 改动有自己的测试，但没有经过第六轮的独立验收。建议：文档写明验收版本与当前 HEAD 的差异。
- **D6 低｜真机手册中的 loader 行号与 HEAD 不符**。[真机手册](../plan/device-test-playbook.md) 第 91 行注明行号固定于 `ec53bac`；第 97 行的 `L3864` 和第 104 行的 `L4042-L4047` 没有注明提交，HEAD 中 `reboot` 分支位于 `loader.c:4498-4509`。gitlink 前移后读者会对照错误的位置。建议：改用函数名或分支名定位，或逐处注明提交。
- **D7 低｜链接到 Git 忽略的归档目录**。总账第 11 行、审查记录 §7 等链接 `docs/analysis/local/` 下的文件，这些文件不随仓库分发，其他人点开会失效。原文已注明「归档目录，不随仓库分发」，结论也已写进仓库内文档，影响有限。
- **D8 低｜目标文档与交接计划的系统盘边界需要确认**。[GPU 加速目标](../plan/gpu-acceleration-goal.md) §3 允许在满足条件时「按需扩大 userdata 中供本项目使用的写入空间、无需再次询问」；[交接计划](../plan/2026-10-24-gpu-handoff.md) §6 写「新的 userdata 授权不得直接沿用该方法……真机阶段全部留在 RAM」。两者不完全冲突，但哪一条优先需要负责人确认。
- **D9 低｜写作规范**。按全局写作约定：总账第 11 行使用表情符号「🔵」；预检门禁记录第 49 行、目标文档第 62 行使用「兜底」，需写明实际操作；预检门禁记录第 104 行「负证据」；交接计划第 64 行「非性能基线」；真机手册第 91 行和预检门禁记录第 16-19、56 行使用破折号。

## 7. 隐私与仓库卫生

- **P1 中｜`logs/` 未被忽略且含本机绝对路径**。父仓库根目录的 `logs/`（约 22 MB，含 `rebuild-loader-782b630b-*` 与 `review-*-fullbuild` 两个子目录）未跟踪，也不在 `.gitignore` 中（`.gitignore` 只覆盖 `hackios-xnu-kernel/logs/`）。其中 `run.sh` 和 `build.log` 共有 15 处本机用户目录绝对路径。执行 `git add -A` 或 `git add .` 会把它提交进去，违反 AGENTS.md §3。置信度：已验证。建议：在 `.gitignore` 中加入 `/logs/`，或把内容移到 `docs/analysis/local/` 等已忽略目录。
- **P2 检查结果**：对两个仓库未推送提交的 diff 与提交说明、父仓库未提交 diff、4 个未跟踪文档，扫描了本机用户目录与挂载路径、私有网段地址、MAC 地址、邮箱、令牌、密钥、认证头、会话标识，没有命中。出现的 URL 都是公开上游（MiCode、OnePlusOSS、UniXNU、googlesource）。提交作者邮箱属于 AGENTS.md §3 允许保留的 Git 署名。vendor 目录路径按原文约定没有写进受控文档。

## 8. 提交与推送流程

- **C1 高｜父仓库 HEAD 引用的内核提交不在远端**。父仓库 HEAD 的 gitlink 为 `3ce4102`，工作树为 `c0716bf`，两者都不在 `origin/k90-port` 上（远端停在 `57066c7`）。先推父仓库会让远端父仓库引用一个不存在的子模块提交，新克隆执行 `git submodule update` 会失败。置信度：已验证。建议：先推 `hackios-xnu-kernel`，再推父仓库；或使用 `git push --recurse-submodules=check`。
- **C2 低｜提交主题行过长**。内核 13 个提交把完整说明写在主题行中，没有正文，最长为 `c0716bf` 的 766 字；父仓库 `a05b96b`（153 字）、`ef75799`（121 字）也偏长。影响 `git log --oneline` 和托管平台的列表显示。这些提交尚未推送，可在推送前整理，改写历史需要负责人授权。
- **C3 低｜`6a734f5` 的提交说明有事实错误**。该说明称「MP_ASSIGN 经由 GMU 自身的 stream 5 路由到达固件」，实际 SCM 调用是 CPU 发出的 SMC；`6259bd1` 已修正代码注释，提交说明仍在未推送范围内。置信度：已验证。
- **C4 低｜中间提交可能无法完整构建**。`313033a` 的说明称原 `_Static_assert(... <= PAGE_SIZE)` 在完整内核构建中编译失败，该断言由 `90c4a25` 引入，因此 `90c4a25` 到 `8907055` 之间的提交在完整构建下可能不可编译，影响 bisect。置信度：推测（依据提交说明推断，未复现）。
- **C5 低｜`xnu/patches/04-bsd%conf%files.patch` 后续 hunk 的新起始行号没有同步**。第 1 个 hunk 改为 `+109,54` 后，后面三个 hunk 的新起始行号没有加 1。`git apply` 不校验新起始行号，在临时仓库中验证过可以正常应用，没有实际影响。

## 9. 已核对无问题的项

- MP_ASSIGN ABI 对照本地厂商源码副本逐项核对：函数号 `0x42000c16`、arginfo `0x1117`；x2..x4 依次为区域 PA、字节数、源 VM 列表 PA，x5 指向 4 个 LE64 扩展参数（4、目标 PA、目标字节数、0）；区域记录 16 字节、权限记录 24 字节；源 VM 为 u32 值 3；数据页权限 {0xA: RW}，表页权限 {3: RW, 0xA: R}；成功判据为 status 0 且 x1 为 0；EBUSY 为 -12；A6 续传使用 x0=1 与 x6 session；状态 2/3（WAITQ）按失败处理并保留页。
- cache 与屏障：参数页写完后逐 64 字节 `dc civac`（带 memory clobber），再 `dsb sy`，然后 SMC；672 字节覆盖全部记录；数据页在任何 MP_ASSIGN 之前清零并清理，之后不再写入；表页按原生页大小清理。
- 批次：每个区域只入批一次；EBUSY 原样重发同一批，不重新 staging；非 EBUSY 失败立即停止；失败后参数页不再改写也不释放；没有 uint64 回绕。
- 16 KiB 页物理检查覆盖 VA 原生对齐、PA 原生对齐、逐个 4 KiB 子页、末字节和 36 位范围，表页另回读比对映射器记录的 PA；删除逐子页循环或把范围边界改差一位的变异都会被测试检出。
- 失败路径：数据页在任何 SMC 之前已计入 `adreno8_memory_count`，表页计入 `adreno8_secure_space.table_count`；`adreno8_block_stop` 与 quiesce 受 `adreno8_memory_retained` 门控；数据页和安全表页没有任何 `kmem_free` 路径，唯一的释放是 SMC 之前的参数页；publish/acquire 拒绝 secure 条目。
- 终止态冻结：`adreno8_hwsched_alloc`、`adreno8_memory_alloc`、`adreno8_memory_alloc_xfer` 三层门控都存在，删除前两层中任意一层的变异会被测试检出；START 失败后步骤循环退出，后续分配不可达。
- 预检只读：相关代码没有寄存器写调用；读 CB3 前先做边界检查；拒绝条件与 `ec53bac` 的说明一致。
- GPU 测试通过 `#include` 编译生产 `.c` 文件；`6611c5c`、`5ac02a2`、`3ce4102`、`6012234`、`199640b`、`d7176d4` 等「生产代码未动」的说法属实。
- loader 跨核共享：`kernel_resources_held`、`active_watch`、`firmware_fault`、`running_live` 与 USB 标志只在 loader 核心读写；跨核共享的 `other_cpu_done`、`other_cpu_stage`、`loader_ctx` 仍按原方式用 `flush_dcache` 读取；`active_watch` 只在 CPU_ON 返回 0 时打开，循环结束和异常入口都会关闭；held 在发 SMC 之前置位。
- annibale 上 `wdt_arm` 直接返回，看门狗上界改动不影响该平台；redwood 上 budget+60 的语义不变。
- `build.sh` 在 macOS bash 3.2 下的数组、`=~`、`${BUILD_ID+x}` 用法正常，宏只接受 40 位小写十六进制，不存在注入；带与不带 `BUILD_ID` 的构建产物分别包含该值和 `unknown`。
- `mkpayload.py` 的条目名规则（长度 1..15、禁止 NUL、禁止重名、旗标名单）与 loader `parse_payload` 的 `str_eq`、遇空名终止、后者覆盖前者的语义一致，`common/build.sh` 使用的 `loader.efi=` 条目仍能通过。
- `c0716bf` 的可核实声明成立：overlay 的 XnuLoader.c/h 与 Mu 文件逐字节一致（sha256 `1a271e3f…`/`3fdb210e…`）；新旧 patch 对 `5b83e7d` 归档 `--check` 均通过，应用后 inf 的 sha256 为 `241bb728…`；三个 hunk 头声明的行数与实际一致（CR 计入行内容）。XnuLoader.c 的解析代码没有越界读或整数溢出，删除的旧逻辑中，诊断输出已由 loader 自行打印，旧 FlushLog 在没有 logdump 分区时写 boot_a 第 0 块，删除是正确的。
- `frames.py` 的最近秩百分位、每秒帧数（N-1 个间隔除以首末帧跨度）、18.0/34.5 ms 严格大于口径、100 ms 分界都正确；floor、round、线性插值三种错误百分位写法都会被测试检出。
- 所有新增和改动的代码文件中，除 `loader.c`（L3）外都在 1000 行以内；最大的是 `tools/test-loader-lifecycle-harness.py`（799 行）和 `adreno8_smmu.c`（731 行）。

## 10. 未验证的前提

- 真机运行的 UEFI DXE 与仓库内 `Mu-Silicium/Binaries/annibale` 下的二进制一致（L1、L11 的固件行为依赖此前提）。
- USB 在中断屏蔽下的可达性、DWC3 End Transfer 是否总能完成、主机侧挂起或总线复位的实际频率。
- Gunyah 与 TZ 上 AFFINITY_INFO 从 ON 变为 OFF 的实际时延（L2）。
- `reset_system` 的 UEFI 复位回调是否访问存储（L6）。
- 厂商 `vendor-qcom_scm.c:1301` 的 `gh_rm_needs_scm_assign`：在 Gunyah 下 HLOS 到 CP_PIXEL 的移交是否走 SCM，本地没有该函数源码。
- shmbridge 启用时厂商把扩展参数缓冲放在 `qtee_shmbridge_allocate_shm` 分配的内存中；本驱动使用普通内核页，TZ 是否接受未知。
- 移交成功后数据页仍映射在 `kernel_map` 中，panic 或 core dump 路径是否会读取这些页。
- PSCI SYSTEM_RESET 是否清除此前移交内存的归属。
- arm64 实际代码生成与 LTO 下 memory clobber 的效果；主机 mock 运行在普通内存上，无法证明这一点。
- HEAD 的完整内核构建未在本轮重做。

## 11. 建议处理顺序

1. 推送前：按 C1 的顺序推送；处理 P1，避免 `logs/` 被误提交；修正 G1 涉及的文档并在总账标注；修复 D2 链接；决定 D1 的日期处理方式；需要时整理 C2、C3 的提交说明。
2. 提交 gitlink `c0716bf` 前：补 D4 的进度记录，同步 D5、D6，压缩 D3 的总账条目。
3. 新 loader 部署前：修复 L1、L2，补上对应的 `usb_command_loop` 和 AFFINITY_INFO 延迟场景测试（L10），再考虑 L5、L6、L7；同步修改真机手册中的 USB 恢复步骤。
4. mode 2 放行前：负责人签署 G1 的新判据；按 G2 补充测试断言；在 §10 的未验证前提中明确哪些作为已裁决的残余风险。
5. 其余条目可在后续维护中分批处理。中严重度的 L3、L4、U1–U4、S1 优先，其中 L3 的拆分最好在 L1、L2 修复时一并完成，避免同一段代码改两次；低严重度的 G3–G8、L8–L11、U5–U10、S2–S5、D7–D9、C4、C5 随相关文件的下一次修改处理。

## 12. 认领与复核交付

| ID | 姓名 | 职责 | 状态与交付 |
|---|---|---|---|
| USB-RETURN | Astra 独立复核 | 作者 L1/L5/L10 的固件身份、USB 终态与重连方案；L2/L6/L7 的返回预算与复位副作用 | 研究完成，实施规格已交主 agent；新 FD 内 UsbDeviceDxe/UsbfnDwc3Dxe 已逐字节匹配分析对象。裁决：Connected 保留 owned；匹配 Cancelled 可回收但不派发旧数据；timeout 与结构错误分别处理；取消 API 返回不作为释放依据，嵌套等待不能称总计 500 ms。单在途及终态唯一前提保留。L2 采用共享总预算方案，L6/L7 覆盖复位入口与延后恢复 DAIF；生产修改待授权，新 loader 与候选 C 暂停部署。作者 L1 是问题编号，与项目 L1 启动试验分别记录；无设备、构建或生产修改。 |
| PAYLOAD-MEM | Astra 架构研究 | U1/U5/U6/U7 与长度、内存前提；annibale payload 保留、BootShim 旧 magic、维护来源 | 研究完成，[实施规格](</tmp/astra-payload-memory-contract-review.md>)已交主 agent。U1为部署前置，C暂停；固定DTB的trust_ui从0xf3800000起，与旧64MiB窗口尾8MiB静态重叠，B/C小payload未触及该区，未认定本次实际写入。建议56MiB保留、55MiB完整容器上限及panic移至0xf3700000，FD/shim/loader/packer同步；待裁决源长度方案及平台宏。Binaries/annibale实际指向dodge，运行期安全保留仍未知；U7新鲜BASE复现后置且未完成。无生产修改、构建或设备操作。 |
| DOCS-P1 | 文档处理 | P1 与 G1 文档面、D1–D9、C1–C4 记录协调 | 已完成（10-24 二轮按最新事实修正）：P1 核 `logs/` 未跟踪、未移动；撤回此前新增的 `/logs/` 行；既有 `logs` 行（工作区未提交，归属不明）经 `git check-ignore` 验证实际生效，标已覆盖待提交，无需重加，本轮 `.gitignore` 净改动为零。G1 预检门禁记录新增 §13（`ec53bac` 判据改判 bit 0 加两条件；run003 读数代入属静态核对，当前机状态需实读；mode 2 暂停待签署），总账同步。D2 交接计划链接已修。D3 总账第 8 行压缩为状态加链接，细节留门禁记录。D4 新建[内核链进度记录](../progress/2026-10-24-kernel-chain-progress.md)：`ec53bac`..`c0716bf` 逐提交改动、18 组主机验证、构建边界（内核正式完整构建@`313033ad`、loader 双变体正式构建@`782b630b`、新 FD `17221a52…` 自固定 dirty 快照构建，三类各绑固定提交并通过有限验收，其后文档/overlay 维护提交未触发内核重建）、设备与恢复（含 2026-10-24 L1 轮 B：`fastboot boot` 被接受、30 次枚举均为 LK、新 loader 运行未确认、用户报告黑屏阶段未定位、一次授权 LK `reboot` 后驻留旧 loader 的 idle 应答恢复）、勘误、授权状态（L1 轮 B 后无新设备授权），四份验收与观察报告归档于 ignored 的 `docs/analysis/local/`。D5 loader 版本链分列（`71082b55…`@`795c1a6` 第六轮固定输入复算一致；`af54316e…`@`782b630` 起 build-id 增量，主 agent 确认已单独通过独立验收；两者真机运行均未确认，mode1 未做），见审查记录 §7 与内核链记录 §4。D6 手册行号改函数/分支名+固定提交（`ec53bac`/`c0716bf`）。D7 归档链接注明仅本机保留、不作唯一依据。D8 goal §3 与交接 §6 并列两层：长期存储授权有效；goal 只保留通用条款「当前实验不自动放行，主机 RAM 加载仍须审核镜像内部持久副作用，超出授权需另确认」，L1 轮与 FD 回落路径等过程史留在内核链记录 §5 与交接 §6。D9 进行中、「兜底」「负证据」「非性能基线」与破折号已修。D1 不移动历史文件与 ignored 目录，标题与正文日期改实际 2026-10-24 并注文件名沿用旧命名，跨链路径未动。C1 推送顺序（子仓先行或 `--recurse-submodules=check`）记录于总账与内核链记录，本轮未推送。C2/C3 不改历史，勘误记录于内核链记录 §6，reword 待用户授权。只改文档，未提交，本轮无设备操作，本节原发现文字未改。 |
| GPU-G2–G6 | Qwen 独占实施 | G2 测试判别力（mock 记录每笔清理 addr/len/顺序与快照内容，断言参数页 672 B、数据页与表页各批次前覆盖，四变异必须失败，区分主机逻辑与目标硬件）；G3 启动 CB3 范围检查补生产测试；G4/G5 按实际代码注释 mode 与读取范围；G6 仅纠正文案与 32 项分批对厂商 2 MiB 上限的差异说明，不改批策略与批次数；G7/G8 删减只记录待决，不删安全门 | 已完成并通过 Astra 独立有限验收。G2：mock 记录每笔清理 addr/len/顺序与快照，断言参数页 672 B 按调用窗口与内容比对、表页与数据页各自批次前覆盖，覆盖被检批次的写入、清理、SCM 顺序与内容；EBUSY 同批重试复用已清理参数页，测试未逐次调用 check_envelope，不写每次重试 SMC 均重新清理；四变异 m1 删参数页清理、m2 清理提前到写入前、m3 删表页清理、m4 删数据页清理全部失败（m2 由内容比对捕获）。G3：启动 CB 循环补映射范围内检查并有生产场景（额外 m5 删守卫失败）。G4/G5 注释按实际代码：preflight 在所有 mode 的分支前运行、0 与未知值共用 closed-path 日志、读取范围写 24 对 SMR/S2CR 与启动探测前 16 的差异。G6 修正 7 处：EBUSY 计数 20/20 对厂商 ≤22/21 并列陈述、32 项分批与厂商 2 MiB 上限差异注明且未改批策略与批次数、参数页失败为终止态、214-223 只描述可达情形、397 游标允许等于计数、private.h 去掉无调用方的 stage 子句、memory.c 保留归属改为计数条件。G7/G8 记入 evidence 内 notes-g7-g8-pending.md 待决，未删代码。host 18 组 17 组成功；test-loader-buildid 失败源自 67044 在改的 loader.c（usb_device_event_data 在其 harness 缺声明），与本轮文件无关。独立验收见 [独立验收报告](../progress/evidence/gpu-review-fix-2026-10-24T12:44:28Z/independent-review-g2-g6.md)（ignored 归档件，原样复制）：secure/memory/smmu/handoff 四组 4096/16384 双页大小均成功；m1–m5 仅在 4096 构建下变异失败，未声称 16384 变异也重放；独立 pages16/page4096/mapped_size 0x13000 布局在双页大小确认 CB2 读取且 0x13000 及以上未读；第二数据批缺失或提前清理的定向变异未执行；目标硬件 cache 可见效果未验证。diff、前后 hash、测试与变异日志在 [evidence 目录](../progress/evidence/gpu-review-fix-2026-10-24T12:44:28Z/manifest.md)；无完整构建、无设备、无提交；9 文件按验收结论冻结待整体来源核对；G2 属 mode 2 前置。 ||
| LOADER-L1/L2/L5/L6/L7+L4/L9/L10+U1 | Qwen loader 独占实施 | 按 [USB/返回实施规格](</tmp/astra-usb-return-implementation-spec.md>) 接手实现：L1/L5 USB 终态状态机（回收与派发分离、双端点统一消费、IN 超时不派发、CompleteError 保守隔离）、L2 共享 100 ms 预算轮询、L6 held/fault 先 PSCI 且不 UEFI fallback、L7 DAIF 恢复时机；L4 mkpayload 帮助语义、L9 stage-system 提前拒、L10 测试枚举改由生产 efi.h 注入加规范值断言；L3 只交拆分方案待确认后实施；U1 loader 子项按[实施表](</tmp/astra-payload-contract-implementation-sheet.md>)：平台 R=0x03800000/C=0x03700000、parse 总界与逐条界、download 实际字节数与头声明上限区分且短下载/取消后旧 magic 不可消费、panic=0xF3700000/0x80000、choose_window 排除完整 [B,E)，shim 别名算术不在 loader 重复 | 已完成主机侧实施与测试：L1/L5 USB 终态按规格 §3 落地（每端点所有权与缓冲/长度记录、Connected 只更新链路状态、Disconnected 结束当前等待并保留所有权与缓冲、usb_notification 为唯一终态入口、隔离标志跨 Connected 与迟到事件、外部重连为恢复边界），L2 按 §5 用一条共享 100 ms 预算轮询（关核答复缓存一次、开与正在启动在预算内重试、负值或文档外取值立即 held、计数器无频率时零查询 held、预算只限制下一次发起、轮询期间无 Stall/WFI），L6 按 §7 在 held/fault 的三处复位入口先 PSCI SYSTEM_RESET 且失败后屏蔽中断停机，L7 按 §6 把 DAIF 恢复推迟到返回路径喂看门狗之前、快照读自 loader_ctx、held 在内存图清理前置位；L4/L9/L10 与 U1 loader 子项按各自规格落地。测试证据：tools/test-loader-lifecycle.py 生产场景通过，29 项变异（其中 1 项靠场景超时捕获）与 2 项反例全部被捕获，wiring 断言通过；test-loader-buildid、test-payload-contract、test-mkpayload、test-stage-system、test-xnu-payload-terminal 全部通过；冻结副本在 /tmp/lc-delivery-final/，loader.c sha256 e3dc7024。真机未知：目标 asm 与新对象需另行核对，run_kernel 主体未做主机提取，同核、SELFTEST 与跨核提前返回的中断顺序靠 wiring 断言覆盖。L3 只交拆分方案，等确认后实施；U1 与 USB 修复分补丁记录；无设备、无完整构建、无提交。 |
| PAYLOAD-TOOLS | 工具独占实施（U2/U3/U4/U10；阶段2 U1 FD/map、U6 长度源码子项） | `uefi/export.sh` 预检（U2）；`tools/test-xnu-payload-terminal.py` 判别力、测试入口与冗余（U3/U4/U10）；新增 `tools/test-uefi-export.py` 夹具测试；阶段2 annibale MemoryMapLib 条目与 `uefi/annibale/` 维护副本、XnuLoader 容器边界、契约测试与 FDT fixture（U1 FD/map、U6 长度源码子项）；patch 与 BootShim 归 ebde，本行未动 | 已完成（主机侧），按 Astra 验收口径合并记账，验收报告 [FDT token 小修有限复验](local/astra-payload-fdt-fix-review.md)。U2/U3/U4/U10 有限通过：U2 export 预检在任何写入前拒绝 staged 输入、路径类型错误、HEAD≠BASE 与缺路径，旧脚本危害在一次性夹具复现，拒绝时 BASE/patch/overlay 逐字节不变，导出为临时目录验证后多文件依次替换（无原子性声明）；U3 终端测试主机编译生产 XnuLoader.c/h，删 magic、删上限、去 16 对齐、固定步进四种解析变异与两条终态变异按指定失败点检出；U4 overlay 与被测根逐字节一致门禁、独立线格式常量 `b"XNUP"`/`0x50554E58` 断言、裸字节正例与仅改头 magic 反例；U10 测试入口冗余已清。U1 FD/map 与 U6 长度源码子项通过：annibale MemoryMapLib 新增 `XNU_Payload 0xF0000000+0x03800000`（Reserv、WRITE_BACK_XN，排序与重叠检查按 MemoryInitPei 读取路径），kernel 维护副本 BASE `87416d23` 为本机受控基础树、README 记录原条目哈希 `7516ffe8…` 与应用前比对，无 DSC/FDF 改动；XnuLoader 解析上界 `Header->Size > XNU_PAYLOAD_MAX_SIZE - sizeof (XNU_PAYLOAD_HEADER)`，`XNU_PAYLOAD_MAX_SIZE` 语义为含 8 字节头的容器 `0x03700000`，Mu 与 overlay 逐字节一致；契约测试以独立常量断言窗口 `0xF0000000`–`0xF3800000` 与 39 个非自身条目，固定 DTB（`b30f254e…`）144 组非零 64 位 reg 对照窗口、trust_ui reg 与原始字节相等，六项变异反例按预期失败；FDT token 缺口关闭：按 Devicetree E-PAPR 修正 4=NOP、9=END，遍历上界 `off_dt_struct + size_dt_struct` 且要求到达 FDT_END，中途插入合法 NOP 等价与 END 置零、截短拒绝用例旧实现失败新实现成功，Astra 冻结增量 tree 复验成功。边界：walker 为固定文件测试辅助函数，不是完整 FDT 验证器（未验证树平衡、完整 string table 边界与完整 property header 安全，节点名称搜索未限定结构区），不声称等效 `fdt_check_full`，不接受任意不可信 DT；「END 须为末个 token」仅是固定 fixture 的前提；最终静态保留冲突复核按已交清单使用合格工具、reserved-memory 父 cell 布局与 memreserve 表，144 组扫描不升级为完整证明；DT 缺席 SKIP 只算部分测试；walker 不再自行重写。冻结三处均自校验通过：阶段1 `docs/analysis/local/payload-tools-u23410-20261024/`（`98b1a9a7…`）、阶段2 `docs/analysis/local/payload-tools-phase2-20261024/`（`9513446e…`）、FDT 增量 `docs/analysis/local/payload-tools-phase2-fdt-fix-20261024/`（`b7745178…`），生产与测试冻结，不再扩范围。未验收：shim/loader/packer 整体契约、新 FD 实际 SEC/HOB 与运行期内存图，部署继续暂停；提交与构建等 loader/shim 跨组件整体验收后统一处理；无设备、无构建、无提交，Mu dirty 未动，本节原发现文字未改。 |
| PAYLOAD-SHIM-P | Qwen 独占实施（shim/packer 组） | U1/U5/U6 的 shim 与 packer 子项：BootShim 运行期地址算术前检（源地址 S、FD 目的 D、容器 P=S+FD_SIZE、长度 L=align16(8+N)、加法溢出、FD 拷贝源目重叠、代码段与 payload 源自保护），无 payload 镜像显式 16 零字节，packer 按 PAYLOAD_CAP 拒绝超出完整容器上限 C 的输入 | 已完成（主机侧）。`Mu-Silicium/BootShim/BootShim.S` 新增通用严格分支，仅同时定义 `PAYLOAD_BASE` 与 `PAYLOAD_CAP` 宏时启用，旧 176 B legacy 分支原样保留；四个编译期自检（CAP 缺 BASE、CAP 对齐与下界、窗口越过 4 GiB、FD 与窗口重叠）拒绝错误宏组合，严格分支 368 B、`_Payload` 等于表尾且 16 对齐，第一条存储只出现在 FD 拷贝循环内，无 payload 分支只用 `str xzr` 清 8 字节头。`mkxnuimg.py` 以 `PAYLOAD_CAP` 环境变量启用严格校验：N≤C−8、8+N 与文件长度一致、align16(8+N)≤C、条目遍历与终止符检查，未设置时产物与旧版逐字节一致，严格模式拒绝预构建回退。`uefi/mu-silicium.patch` 仅替换 BootShim 段（整文件 sha256 `ab55cd99…`→`e1dbe738…`），其余段含 CRLF 逐字节保留，测试断言重建应用结果与工作树一致。新增 `tools/test-bootshim-contract.py` 36 项全部成功：改动前 BootShim.S 由改动前 patch 重建并与哈希 `3898ce4b…` 比对；legacy 与 plain 编译产物同基线逐字节一致；反汇编静态核对 8 项（检查全部位于拷贝/清零块之前、溢出分支位于容器探测之前、`_Dead` 自环不返回、四种错误编译配置按预期报错）；packer 9 组含最大边界（16 对齐容量）与 13 个畸形容器；qemu-aarch64 + GDB stub 真实执行 15 布局（含 annibale 真实地址 0xF0000000/0xA7100000 三组），内存终态与独立地址算术模型逐字节比对：完整拷贝、清零只写 8 字节、各重叠类进 `_Dead` 且零写入。边界：N=24 最小接受、N=C−8 接受、N=C−7 拒绝、L==C 接受、L>C 拒绝、N=0xFFFFFFFF 拒绝、头声明与文件长度不一致拒绝、S==D 跳过 FD 拷贝仍处理 payload、P==B、P==D、代码段落入窗口均拒绝；P 加法溢出有静态分支位置与模型两层核对，qemu 侧仅模型（越过物理范围的取指不可达）。限制：固件运行期源地址范围可读属离线打包前提，主机无法验证；字节码覆盖为列出的 15 个布局，本机没有 Unicorn，未引入手写解释器；FD-only 或冻结 packer 流程要产出新 shim 需在 BootShim 目录以 `-DPAYLOAD_BASE -DPAYLOAD_CAP` 手工编译，现行 `prebuilt/uefi/BootShim.bin` 仍是旧 176 B legacy；annibale 接入已完成（主 agent 授权，接入时两文件工作树干净、改动后 common/ 下仅这两个文件被改）：`common/devices/annibale.conf` 加 `PAYLOAD_CAP=0x03700000`，`common/build.sh` 第 76 行 mkxnuimg env 原样转发（loader 的 build.sh 未动），其他设备 conf 无 CAP 默认；新增 `tools/test-payload-cap-wiring.py` 4 项全部成功（CAP 从 conf 经 build.sh 抽取的真实调用行进入 mkxnuimg 环境并落到 make 宏 `-DPAYLOAD_CAP=0x3700000`；redwood 空 CAP 环境、无 CAP 宏、旧镜像形状逐字节不变；CAP 置位且 Mu 产物缺失时报错拒用旧 prebuilt shim），夹具为 stub make/mkbootimg，未跑实际 common build；接入 2 文件+测试独立冻结于 `/tmp/qwen-shim/freeze-payload-cap-wiring-20261024/`。严格产物与反汇编在本机 `/tmp/qwen-shim/deliver/`（临时目录）。Astra 终审后按两条 must-fix 修复并另立 r2 冻结（原 r1 快照 `/tmp/qwen-shim/freeze-payload-shim-p-20261024/` 自含复跑 36 项成功、四件哈希未动，保留不覆盖）。must-fix ①（Astra §3，mkxnuimg 副作用顺序）：严格路径改为 cap 形状、`FD_SIZE>0 且 %16`、`FD_BASE/FD_SIZE` 非负、`FD_BASE+FD_SIZE≤0xFFFFFFFF`、prebuilt 拒收、FD 实际长度==`FD_SIZE`、容器 `validate_container` 全部先于首次 unlink/make/写输出；新增 `cli_tests` 隔离完整 CLI 组（临时夹具 + mock make，含 BootShim.elf/bin 与输出镜像 sentinel），12 例非法输入（非法 cap/对齐、零与非法 FD_SIZE、负 FD_BASE、FD 末端越过 4 GiB、FD 长度不符、无 Mu prebuilt、非 XNUP、N 越界、头长与文件长度不符、字符串条目缺 NUL）断言 make 调用 0 次且 sentinel 逐字节不变，合法输入恰好一次 make。must-fix ②（Astra §4，宏取值范围）：strict 分支新增编译期 `#error` 拒绝 `FD_SIZE≤0`（零 Q 会在 copy16 存一个 16B 块后把循环预算回绕到 2^64−16）、`FD_BASE/PAYLOAD_BASE` 负值、FD 末端越过低 4 GiB，负面编译从 4 例增至 8 例；这些改动只在预处理阶段，annibale 严格机器码逐字节不变 （`.text` 仍 `0a5cbe63…`，368 B，测试第 12 项固定该哈希），legacy/plain 产物仍同基线逐字节一致。patch 的 BootShim 段随 BootShim.S 同 hunk 重生成（整文件 sha256 `e1dbe738…`→`67569759…`），CRLF 的 Silicon 段逐字节保留，patch gate 断言应用结果==工作树。契约测试从 36 项增至 39 项全部成功（快照目录内跑 + 独立复制 setup 重跑均 39 项 exit=0）。CAP 继承裁决（主 agent，方案二）：`common/lib.sh` 的 `load_device` 在 source 目标 conf 前仅 `unset PAYLOAD_CAP`，strict 由设备配置选择，直接调 mkxnuimg 仍可用 env 显式指定，不清其他变量、不改 legacy 三 conf 与 template；`tools/test-payload-cap-wiring.py` 从 4 项增至 9 项全部成功（继承 CAP→redwood 清空、同 shell annibale→redwood 清空、redwood→annibale 取 0x03700000、profile CAP 覆盖继承值、仅 CAP 被清其余保留），接入 r1 冻结 `freeze-payload-cap-wiring-20261024/` 与依赖反例 `freeze-payload-cap-wiring-deps-20261024/` 保留。r2 冻结：四件 `/tmp/qwen-shim/freeze-payload-shim-p-r2-20261024/`（BootShim.S `18e247cf…`、mkxnuimg.py `243c87c5…`、patch `67569759…`、test `ab77bda3…`，含 change.diff/baseline/artifacts 与自校验 SHA256SUMS，自含复跑 39 项 exit=0），接入 r2 `/tmp/qwen-shim/freeze-payload-cap-wiring-r2-20261024/`（lib.sh `98a3dfb1…` + 全部 legacy/template conf 依赖 + 9 项测试）。r2 增量均未做设备、端到端镜像、整构建与提交；Mu 子模块仅动 `BootShim/BootShim.S`。r3 增量（Astra r2 复核第 3 节，packer 零副作用残余三类）：mkxnuimg 严格预检补齐与 BootShim 编译 guard 同表达式、同端点的三项，`PAYLOAD_BASE` 非负（独立文案）、`PAYLOAD_BASE+PAYLOAD_CAP≤0xFFFFFFFF`（同 guard 文案）、FD 目标 `[FD_BASE, FD_BASE+FD_SIZE)` 与 payload 窗口 `[B, B+C)` 半开区间相交拒绝（端点相接接受），全部先于首次 unlink/make/写输出。CLI 反例新增 Astra 复现值三例（B=-1、B=0xF0000000 且 C=0x20000000、B=0xA7100000 且 C=0x3700000 且 FD_BASE=0xA7100000）断言 make 调用 0 次且 sentinel 逐字节不变（拒绝组 15 例），接受组新增 FD 末端恰等于 B 的端点相接正例，编译反例新增与 CLI 同宏三例至 11 例。BootShim.S/patch/lib.sh/conf 零改动（哈希逐项同 r2 冻结），annibale 机器码仍 `0a5cbe63…`；定向 21 项与 CAP wiring 9 项全部成功，15 QEMU 本轮未重跑（机器码未变）。CAP 接入按 Astra r2 第 4 节有限通过，packer 三类配置已前置拒绝。r3 冻结 `/tmp/qwen-shim/freeze-pack-guard-parity-r3-20261024/`（INDEX 含 guard 与预检全量对照），r2/r1 各目录保留不覆盖。Astra r3 独立快验通过（2026-10-24 消息）：shim/packer/CAP 源码与 host 模拟有限通过，无新增必要修复，生产文件与 tests 冻结不再扩实现、不提交；实际新 FD 镜像、最终封装镜像与 loader 及真机运行期契约尚待验收，设备继续暂停。工作小结、Astra 复核结论与 7b 构建输入哈希清单归档于 `docs/progress/2026-10-24-payload-shim-cap-r3.md`（归档以清单自哈希标识各本地临时冻结目录，不依赖绝对路径）。 |
| FRAMES-S1/S2 | frames 工具测试独占实施 | S1 主每秒帧数三处输出的测试断言（分段行、同手势汇总行、全体统计行）；S2 恰好 18.0/34.5 ms 的严格 > 边界样本与内置变异反例；只改 `tools/test-frames.py`，`tools/frames.py` 生产终版不改（重放期间临时修改并恢复） | 已完成（主机侧），Astra 独立有限验收通过。S1：三处主每秒帧数逐行断言，预期由测试内 fixture 独立推导——长停顿 5 区间÷首末帧跨度 686000 µs=7.3、慢帧 4÷88000=45.5、短窗口 1÷500000=2.0（两帧段只计 1 个区间）、同手势汇总与全体 5÷118000=42.4、边界 4÷105002=38.1；长停顿分段行上主 7.3 与次级 34.9（3÷86000）分行固定，分子、分母变异互不掩盖。S2：新增 18000/18001/34500/34501 µs 四个区间，严格 > 下超 18.0 ms 计 75%、超 34.5 ms 计 25%（分段行与全体统计行分别断言），> 改 >= 变 100%/50%；归因断言 idle 21.5 ms 独立推导，>= 或阈值改 −500 µs（打印标签仍是 18.0/34.5）时归因集变为 idle 18.8 ms。变异反例：测试内置 8 项（分段/汇总/全体分子 +1、分段分母换 100 ms 以下区间之和、over_share >=、归因集合 >=、两处阈值 −500 µs 标签不变），并以同样 8 项在生产文件上重放整套测试，8 项全部失败且首个失败行即对应预期断言，每次重放后 `tools/frames.py` 恢复并核对与 `cd1a23b8…beee` 逐字节一致；share 断言初版跨全部输出，仅改分段一处的变异会被未变异的全体统计行满足，已改逐行断言。测试 7 项全部成功，干净运行日志、重放日志、diff、恢复基线与重放脚本归档于 [evidence 目录](local/frames-s1s2-evidence-20261024/)（Git 忽略的本机归档，SHA256SUMS 自校验通过）；过程记录：外部重放对共享工作树的 `tools/frames.py` 曾为变异测试临时修改并逐项恢复，最终生产字节与基线 `cd1a23b8…beee` 逐字节一致；测试内置反例始终在源码副本上运行，后续所有变异改在独立临时副本执行，不改共享工作树；本轮仅 `tools/test-frames.py` 改动（314 行，sha256 `96660c2c…56eb4`），他人文件与 GPU/loader 文件未动；无设备、无构建、无提交。独立复核（结果来源 Astra，报告归档 [astra-frames-s1s2-review.md](local/astra-frames-s1s2-review.md)，sha256 `563aba11…49da`，原件与归档逐字节一致）：固定两 hash（`tools/frames.py` `cd1a23b8…beee`、`tools/test-frames.py` `96660c2c…56eb4`），7 项测试成功，N 替 N−1、分母错误、阈值 34.499 ms 三项独立反例全部按预期失败，结论为有限通过；S3（`frames.py` 冗余）与 S4（100 ms 以上停顿的归因口径，待作者确认）超出本行范围，未做。生产与测试均不提交，本行冻结，等统一提交。 |

表格内 `/tmp/…` 链接（PAYLOAD-MEM、LOADER-L1/L2/L5/L6/L7+L4/L9/L10+U1 行）指向主机临时文件。提醒各认领组：暂不要新增此类链接；三份原件已归档到 Git 忽略的 `docs/analysis/local/`（sha256 与原件一致），待所有人编辑完成后按[认领状态表](../progress/2026-10-24-claim-status-table.md) §6 的待替换清单改为仓库相对链接，替换前不动他人活跃行。
