# 2026-10-24 内核链 ec53bac..c0716bf 进度补记

内核子模块从 `ec53bac` 到 `c0716bf`（工作树 HEAD）的提交此前在 `docs/progress/` 没有对应记录，本文件按[未推送审查](../analysis/2026-10-24-unpushed-review.md) D4 补记改动、主机验证、构建、设备与恢复状态和勘误。逐提交的完整说明在内核仓库 git log 中，本文件只做摘要；本补记轮只改文档，未修改代码、未构建、未操作设备。

## 1. 源码改动（按提交）

- 安全移交链：
  - `6983430` 收窄实验支持面（kind-5 只保留关闭/只读预检/一次移交三种模式，删除无生产调用的包装）。
  - `90c4a25` 移交日志区分逻辑批次与 SCM 实际尝试，`xfer_abort` 只关闭未开始状态，参数页布局加编译期断言。
  - `06f9088` 移交前整页物理验证覆盖原生页与 4 KiB 子页缝隙。
  - `6a734f5` 严格预检新增 GMU 自身路由核对（提交说明的通路表述有误，见 §6）。
  - `6259bd1` 修正该语义：MP_ASSIGN 的 SCM 由 CPU 经 SMC 发出，路由读回只核对 MMIO 视图。
  - `2792866` 缓存维护与屏障汇编声明 memory 副作用。
  - `d7176d4` 新增真实 HFI 泵内的安全移交联测。
  - `199640b` 严格预检测试补 GMU 自身路由种子。
  - `5e7f588` 整页验证改逐 4K 子页遍历、范围判断改减法防回绕。
  - `f48935d` 表数量核对数组容量并声明调用方契约。
  - `5c5616e` 评审用例补齐。
  - `8064f7e` 首次 MP_ASSIGN 前记录逐批计划。
  - `fd6d9ae` 计划日志改为实际 staging 逐批输出（删除 1024 项静态缓存与截断）。
  - `6012234` 新增公共日志解析模块 `adreno8_logcheck.py` 并逐项核对日志与 SCM 快照（生产代码未动）。
  - `8907055` 解析器改单趟状态机并收 17 例反例。
  - `313033a` 布局断言改用编译期最小页 4096（`PAGE_SIZE` 在导出头中可为运行期值，原断言在完整内核构建中编译失败）。
- loader：
  - `795c1a6` 内核生命周期保护与 USB 缓冲所有权（held 语义统一并门控 `hc_take_back` 与 `reboot`；事件先按类型校验尺寸，短事件停用全部在途请求，停用端点忽略迟到通知，queued 接收按原 buffer/len 接管；新增标记块原样编译的主机测试与 harness，19 个变异全部被捕获）。
  - `782b630` `getvar build-id` 报告构建时显式输入的 40 位十六进制源码 commit，未设置时报告 `unknown`，附 `test-loader-buildid.py`。
- 工具：`2a78897` `mkpayload.py` 输入校验与审批范围收口（单次读取、条目名规则、`--forbid-entry`、失败在写输出前退出）；`08f73e7` `frames.py` 分段统计改整段口径并新增 `test-frames.py`。
- UEFI：`c0716bf` overlay 与 Mu 生产文件同步、`mu-silicium.patch` 收敛、终端解析测试移入 kernel `tools/`。

## 2. 主机验证

- 审查轮 18 个主机测试全部成功，范围与两个未运行测试的排除理由见[未推送审查](../analysis/2026-10-24-unpushed-review.md) §1。
- loader `795c1a6` 的第六轮主机有限验收通过（固定输入、19 项变异、独立反例，见[审查记录](../analysis/2026-10-25-loader-review-findings.md) §7）。
- parser `8907055` 独立复验通过（17 例自测、15 例独立反例，secure、handoff 原脚本全模式退出 0，主机范围）。
- `782b630` build-id 增量有自己的专项测试（应答值、`build.sh` argv 捕获、变异检出）。

## 3. 构建

- 正式产物三类各自绑定固定提交，均已在 2026-10-24 通过独立有限验收：
  - 内核在 `313033ad` 完成正式完整构建与对象、最终 mach 独立核对（正式内核 `handoff-mach-full-313033a` sha256 `788d9046…`，19,248,680 字节；反汇编确认 store→cache helper→DSB→SMC 顺序），见[正式构建验收](../analysis/local/astra-formal-build-313033ad-acceptance.md)。
  - loader 在 `782b630b` 完成 generic/phone 双变体正式构建与产物有限验收（phone EFI sha256 `10ba70a9…`，build-id 应答分支经链接产物反汇编关联核对），见 [loader 产物验收](../analysis/local/astra-loader-782b630b-artifact-acceptance.md)。
  - 新 FD sha256 `17221a52…` 自固定 dirty 快照构建并通过有限验收（关闭 XnuLoaderMain 的 payload 失败/返回日志持久写路径；不覆盖其他 BDS 变量、启动选项与驱动内部副作用），见 [FD 产物验收](../analysis/local/astra-fd-17221a52-artifact-acceptance.md)。
- 内核正式构建固定在 `313033ad`：其后的 loader build-id、工具与文档/overlay 维护提交未触发内核重建，`c0716bf` 的完整内核构建未重做（[未推送审查](../analysis/2026-10-24-unpushed-review.md) §10）。`90c4a25` 起在完整构建下可能不可编译的推断为推测，`313033ad` 的正式构建直接证实该断言此前在完整构建中失败、修复后成功。
- loader `build.sh` 自 `782b630` 起接受 `LOADER_BUILD_ID`，`common/build.sh` 默认不传，产物报告 `unknown`；`782b630b` 正式构建显式传入自身完整提交。
- 归档报告在 `docs/analysis/local/`（仅本机保留，不随仓库分发），必要结论已写入本文，归档件不作为唯一依据。

## 4. loader 版本链

- `795c1a6` 的 `loader.c` sha256 `71082b55956fb54ea83fd2677026004faf9556e2ad63daed16733bba0017fe8a`：第六轮主机有限验收的固定输入（本文件复算一致）；同一内容作为 `313033ad` 正式 run 的 loader 变体一并构建、验收。
- `782b630` 起（含 `c0716bf`）的 `loader.c` sha256 `af54316ef3c9e4864ce6aecc4828ba2a5fcddd8ff030de1aea706a4577a1ddaa`：build-id 增量，不在第六轮固定输入内；`782b630b` 已完成双变体正式构建与产物有限验收（主 agent 确认该增量已单独通过独立验收）。
- 真机 boot_a 仍为 v5 loader（`89ed602e…`，[真机手册](../plan/device-test-playbook.md) §5）：L1 轮 B 试验后复位观测 `version=0.5`、build-id 为空，与新 loader 进入运行不一致，上述两个新 loader 版本都未在真机确认运行。

## 5. 设备与失败恢复

- 提交链本身不含设备改动；2026-10-24 当天发生了独立设备轮（L1 轮）：
  - B 候选（发送前 sha256 `35769541…`，1,267,712 字节）`fastboot boot` 被接受（Sending/Booting 均 OKAY），随后 30 次枚举均为 LK（`product=annibale`），未观察到 xnuloader 枚举，新 loader 进入运行未确认。
  - 用户报告黑屏，日志缺 BootShim/SEC/DXE/早期 loader 标记，黑屏阶段无法定位，未认定 `empty.dtb` 为原因。
  - 定向 xnuloader 查询在设备未枚举时阻塞，约 304 秒后被人工取消（tool timeout 只把前台命令转后台，进程靠显式取消停止），属超出本轮 90 秒观察预算的 host 等待偏离，后续设备命令须放受管进程并设 deadline 主动终止。
  - 经单独授权执行一次 LK `reboot`，18 秒后出现 xnuloader（`version=0.5`、build-id 空、`result`=idle），应答与试验前驻留旧 loader 逐项一致，未对运行字节做 hash 校验。只读复核见 [L1-B 观察复核](../analysis/local/astra-l1-B-observation-review.md)。
  - 同轮独立复核确认所用 FD（`109c477b…`）含可达的日志持久写路径：payload 无效、LoadImage 失败或 StartImage 返回都进入日志采集尾部，FlushLog 优先写 logdump、失败回落 boot_a 起始 LBA，写入前无主机授权或 slot 检查；本轮无 BDS 阶段日志与前后分区内容对照，是否执行、写入量均未知（[FD 持久写风险复核](../analysis/local/astra-v5-fd-persistent-write-risk-review.md)）。
  - 新 FD 只关闭该 XnuLoaderMain 尾部路径，其余变量与驱动副作用未排除。
- 最后观测（2026-10-24 L1 轮 B 收尾）：驻留旧 loader 的 idle 应答恢复（身份应答逐项一致，未校验运行字节）；候选 A/B 保持原样，试验停止。更早的 run003 收尾观测见[预检门禁记录](../progress/2026-10-25-gpu-secure-preflight.md) §12。
- 失败恢复口径：run002 的 hung 恢复与停止后两轮日志补采程序在[真机手册](../plan/device-test-playbook.md) §5；run003 已按该程序确证 park 打印。预检判据变更与 mode 2 暂停状态见预检门禁记录 §13。

## 6. 勘误与提交说明记录

- `6a734f5` 提交说明写「MP_ASSIGN 经由 GMU 自身的 stream 5 路由到达固件」，实际 SCM 调用是 CPU 发出的 SMC；代码注释已由 `6259bd1` 修正，提交说明保持原样，reword 需用户另行授权。
- 内核 13 个提交把完整说明写在主题行（最长 `c0716bf` 766 字），历史整理与 reword 同样待授权，本轮未改写任何历史。
- 构建与验收记录的勘误（命令记录名称、manifest 三项描述、FD BUILD-PLAN 身份替代限制等）在各验收报告的非阻塞修正节记录，原始日志未改。
- L1 轮记录勘误总结（getvar 失败仍回 rc=0 的判定、重新枚举时刻更正、恢复结论边界、host 控制流程偏离、授权措辞与持久写风险勘误）见 `docs/progress/evidence/l1-boot-B-20261024T110858Z/13-errata-summary.md`（Git 忽略目录，仅本机保留），00–12 原始日志未改。

## 7. 授权边界

- 本链未提交文档之外的改动、未推送；推送顺序固定为先 `hackios-xnu-kernel` 后父仓库，或 `git push --recurse-submodules=check`（总账与[未推送审查](../analysis/2026-10-24-unpushed-review.md) C1）。
- L1 轮 B 之后无新的设备授权：无重试、无换候选、无刷写授权，不提出默认持久写路径；mode 2 继续暂停；mode1 需按正式构建验收报告 §5 的最小清单另行获得设备操作授权。
