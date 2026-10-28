# Loader 修复与下一次启动试验接续任务

## 1. 目标与当前状态

继续完成 REDMI K90（annibale，SM8750）的 loader 修复和下一次启动准备。代码位于 `hackios-xnu-kernel/`。完成 loader 必要修复及验证，复用已验收的新 FD 和 BootShim，生成输入、版本和哈希明确的启动候选。首次真机验证仅检查 loader 启动、USB 身份、完整 build-id 和空闲状态，不加载内核、不运行 GPU。

先核对工作树、现有日志和运行中测试，保留全部未提交修改。后续实现以当前实际文件为起点；旧冻结包保留作对照。本文按最近一次实现者报告更新，A/B 新版尚未完成独立验收。

| 分组 | 最近报告的状态 | 接续动作 |
|---|---|---|
| A：payload | pkg-A 已冻结；loader 哈希前缀 `bd4ec216`，清单自身哈希前缀 `2644641f`。实现者报告 payload 9 项变异、ASan、lifecycle 29 项变异和相关测试成功 | 取得完整清单，先复验短下载完整前缀、终止条目和夹具修复 |
| B：USB | 修改已落盘，新增 19 项顺序场景。最后一轮生产场景、35/35 变异、2/2 反例均按预期完成，但末尾 `wiring_verify_checks_present` 失败，整套尚未通过，B 未冻结；payload/buildid/mkpayload/stage/语法五套成功 | 核对两处长度检查的实际职责后修正 wiring 断言，单独验证该检查，更新包内依赖清单并冻结 B |
| C：held／异常 | 尚未修改 | 完成提前退出屏蔽中断、watchdog 顺序和首次异常复位路径 |
| FD／BootShim | 正式构建、产物机制检查和固定输入审计已有限通过 | 核实文件哈希后复用 |
| GPU G2–G6、工具 U2/U3/U4/U10、帧统计 S1/S2 | 已有限通过，改动未统一提交 | 保持冻结，不重复无关测试 |

实现者最后报告 B 测试进程已结束，无遗留运行任务，已停止新增修改且 C 未开始。此前中断原因由实现者解释为 bash 等待超时或工具调用中止，测试日志继续推进；接续时可核原始记录，不再操作旧 PID。

B 的失败点位于 `tools/test-loader-lifecycle.py:232`：`wiring_verify_checks_present` 要求 LC-USB 块中 `bytes_completed > sub_len` 恰出现一次，新增 Cancelled 长度检查后实际出现两次。实现者建议改为两次；接续前先确认两处均处于正确路径，不能仅调整计数取得成功。单独运行 wiring 检查后，重算该测试文件哈希，修正 B 包 DEPS 的过期值，再生成冻结清单。已经完成的场景和变异结果应复用，是否重跑由实际修改范围决定。

B 包 `logs/life-full.log` 保存生产场景、35 项变异、2 项反例及末尾 wiring 失败；同目录 `payload.log`、`buildid.log`、`mkpayload.log`、`stage.log`、`syntax.log` 成功。B 包无 SHA256SUMS，尚不可作为完整冻结交付。

## 2. 冻结版本与审查资料

旧 loader SHA256 为 `e3dc70244e4dfdfc13518cbb7b224d70ed6f69737f93f79cd4e672ead1beb582`，独立验收未通过。旧自含包清单自身 SHA256 为 `e21adb86bac0fe58e4e86c6bbbac662610cb224559c8f2920bbee7f3e9b926b3`。A/B 前缀只用于定位，不作为正式构建身份。

最新实现者提供的完整哈希如下，接续时复算确认；A/B 新版仍待独立验收。

| 对象 | SHA256 |
|---|---|
| pkg-A 的 SHA256SUMS | `2644641f3cdeabe80214fb16ee5975834da9e2cdbea2794d3c577b9335d3f6e3` |
| A 期 loader.c | `bd4ec216e5e5203a46958506265edc805133b05cf88e92d29b79767f1bd3c97c` |
| B 期 loader.c | `e5d7414bb5c8df204bb5d6114e23d9ebdb1971f130e419a28c93a5ad52535eff` |
| B 期 lifecycle harness | `36e92e382406465ebb75cf2b84627bac02a2377e74a331f595a2a095ad9e92d5` |
| B 期 lifecycle harness2 | `047cd2f9ea64d9b66111cea65fb786ff1cdea9443d2bd17eab29de078d6edd61` |
| A 后 payload-contract 测试 | `df2b7f5a5a3623b0b888b0b3e7c02caf675877136f861ce46e7c1c2e5f488a1c` |

B 期 `test-loader-lifecycle.py` 仅报告前缀 `a2a9b6109ec0d33e`，完整值需重新计算；B 包 DEPS 中的 `775745f165d5a5591765b80b2472036d55e407f858a0954d7609981d5e12d5d6` 属修改 tag 前的旧值，不得用于新版身份确认。

本机临时目录中的交付按以下名称查找；路径由接续会话实际解析并核对，不提交个人绝对路径。

| 本地件名称 | 用途 |
|---|---|
| `lc-delivery-pkg` | 旧版自含包，原 11 文件及补取依赖，来源时点有记录 |
| `lc-delivery-pkg-a` | A 组新版冻结包，完整清单哈希见上表，待独立复验 |
| `lc-delivery-pkg-B` | B 组未冻结包，注意名称中的大写 B；已有日志，DEPS 需更新，无 SHA256SUMS |
| `lc-delivery-final` | 旧 11 文件原始冻结 |
| `astra-loader-e3dc7024-review.md` | USB／返回路径独立失败报告 |
| `astra-loader-payload-preliminary.md` | payload 真实函数反例和剩余范围 |
| `astra-loader-payload-urtp58zi/independent-repros.c` | 短下载与四种终止缺陷的真实函数反例 |
| `astra-lc-final-z755hznp/independent.log` | USB 四项动态反例 |

仓库内资料：[原始审查与认领状态](../analysis/2026-10-24-unpushed-review.md)、[USB／返回路径规格](../analysis/local/astra-usb-return-implementation-spec.md)、[payload 契约规格](../analysis/local/astra-payload-contract-implementation-sheet.md)、[跨组件验收清单](../analysis/local/astra-payload-final-integration-checklist.md)、[单次 idle 准入清单](../analysis/local/astra-next-idle-admission-checklist.md)。`analysis/local/` 为仅本机保留的忽略目录；缺件须明确报告，不能以缺少的材料作为已验依据。

## 3. A 组验收要求：payload 下载与解析

1. 短下载、取消或失败后，收到的数据不得继续作为有效 payload 消费。
2. 旧版已确认反例：请求下载 88 字节，仅收到完整合法的 72 字节 XNUP 前缀，命令回复 `FAIL short download`，后续 `parse_payload` 仍成功。新版必须拒绝。
3. 成功 USB 下载的实际字节数必须精确等于 `8 + Header.Size`。启动时由 BootShim 提供的 payload 与 USB 下载分别表达长度来源。
4. 解析器必须要求完整、全零的 24 字节终止条目，终止条目后没有多余容器内容。缺终止、仅 1 字节终止、终止内非零、终止后多 1 字节均须拒绝。
5. 修复测试中实际仅 104 字节数组被按 512 字节读取的问题，并用运行时分配和初始化替代约 55 MiB 的 C 静态初始化文本，保留最大长度测试。
6. 核对 `run_kernel` 的真实调用路径会执行上述门禁。Mach-O header/load-command 的 entry 长度深层检查另列未覆盖项，本轮不扩展重写。

## 4. B 组验收要求：USB 连接与传输

1. idle 连接等待收到 `Connected` 后应能返回命令循环并继续接收。旧版 `usb_wait(0xff, 0)` 会持续等待。
2. 固件仍持有 OUT 缓冲区期间不得重复提交；`Connected` 本身不释放旧传输所有权。
3. timeout 或断开后的迟到 `CompleteOK` 只能按有效终态回收，不能交付旧数据或派发旧命令。
4. `Cancelled` 必须先完成事件结构、缓冲区和长度检查；超出已提交长度的通知不得释放所有权。取消函数返回值不能作为 DMA 已停止的依据。
5. 测试覆盖真实命令循环中的连接、断开、重连、取消、超时和迟到通知顺序，不能仅依赖 helper 或字符串顺序断言。
6. 保留单在途传输与固件通知的实际限制，不引入固件未提供的 generation 保证。

实现者报告 B 组 35 项变异中两项依靠 180 秒上界捕获：原等待预算删除变异和新增连接等待出口删除变异。接续时先收集已有运行结果，避免重复整套长测试；有修改再按受影响范围验证，明确超时捕获和断言失败的区别。

## 5. C 组任务：held、异常和中断恢复

1. 所有相关提前 held 路径先屏蔽中断，再执行后续操作，包括非 annibale 的 CPU_ON 未知结果和 NOT_STARTED 超时路径。
2. watchdog 调用不得早于需要执行的统一中断屏蔽。
3. 首次异常必须正确设置 fault 并进入已规定的 PSCI 路径；相关异常路径不得先执行日志 flush 或 UEFI reset。
4. PSCI 返回后记录失败并停止，不回退到未批准的固件复位路径。普通非 held 平台行为保持原范围。
5. L2 共享 100 ms 核心关闭查询预算已有限通过，保持实现。该预算限制后续查询发起，无法抢占未返回的 SMC。
6. 对同核、SELFTEST、跨核及提前退出检查实际控制流，正式产物中另核目标汇编。主机 asm 替身和文本断言不能完成目标执行验收。

## 6. payload 统一契约

```text
基址 B                 = 0xF0000000
保留窗口 R             = 0x03800000   // 56 MiB
完整容器上限 C         = 0x03700000   // 55 MiB，包含8字节头
Header.Size 最大值     = 0x036FFFF8
复制长度               = align16(8 + Header.Size)，不得超过 C
容器末端               <= 0xF3700000
保留窗口末端           = 0xF3800000
panic 地址             = 0xF3700000
panic 大小             = 0x00080000
```

固定 DTB 的 trust_ui 保留区为 `[0xF3800000, 0xF8800000)`。旧 64 MiB payload 窗口与其重叠。此前 B 的小 payload 正常复制范围未进入该区，没有确认发生覆盖。自动窗口选择必须排除完整 R；系统盘 ramdisk 的独立预算保持原语义。强制地址分配依赖 Reserved HOB 和固件分配接口，软件未独立校验全部强制窗口。

BootShim 保留运行时源目标重叠和加法溢出检查，所有危险重叠在复制或清头之前拒绝。无 payload 的严格封装尾部为 16 字节零；shim 清目标 8 字节头。真实源可读范围仍依赖已验封装输入。DT 静态检查覆盖按父 cells 解码的 49 组固定地址，14 个无固定 reg 节点及 TZ 动态占用仍未知。

## 7. 可复用的正式产物

| 产物 | 字节数 | SHA256 |
|---|---:|---|
| 新 FD | 3145728 | `85415cc488c2485c8c4329bb23bd06bdcb08c267e5182d6539391e45fb852e3b` |
| 新 BootShim | 368 | `0a5cbe63026c7e372120a9ed55f4380e94e2842babc741f87f44f44130ffaa87` |
| FD 内嵌 BDS | 343552 | `24fbaa69d5467becc5d62dcb3442332fae07ed24d1044bcc058f5bc7e4b81b88` |

[构建与验收归档](../progress/evidence/early-fd-shim-snapshot-20261024T145846Z/EARLY-APPROVAL.md)记录产物路径。先核实际文件哈希再复用，不默认重新构建。旧 176 字节 BootShim 和旧候选 C 不用于验证新契约。

已独立确认 BDS 从 `0xF0000004` 读取 Header.Size、上限为 `0x036FFFF8`，失败或返回后进入 DAIF 屏蔽与自循环；SEC 实际生成资源 HOB 和 Reserved allocation HOB。原始 pre/post 清单独立解析得到 139592→144507 项，55 项变化为 52 个 Git index、两个授权 shim 产物和根目录元数据，新增 4915 项均在 Build/Conf，删除 0 项。既有源输入无变化。index 字段变化原因未经核对，父目录挂载在构建时的完整内容缺少同期记录，相关限定保留。

## 8. 修复后的完成步骤

1. 验收 A，收集 B 当前测试结果，完成并验收 B/C。每个结论绑定明确文件哈希，变异在独立临时副本执行。
2. 处理 loader 文件组织要求：新文件和本次净增长越线文件控制在 1000 行以内，确有不可拆原因按项目约定说明；不得通过合并代码行缩短文件。此前提出同一编译单元内按职责拆分的方案，保留正常代码格式，不新增无必要的共享上下文框架。
3. 固定源码提交和完整输入，构建 loader。BUILD_ID 使用对应完整提交号，正式候选拒绝 unknown。
4. 核对正式 loader 中的 USB／返回路径、payload 常量及 build-id 回复分支。
5. 与已验 FD、BootShim 封装新候选；XNUP 仅含 `loader.efi` 与 `usb=1\0`，不附带内核或 cmdline。外部 DTB 选择单列，空 DTB 的实际启动适用性尚未验证。
6. 独立解包核对全部组件、终止与对齐、boot header、SHA1 id、实际大小和 SHA256。
7. 更新[唯一进度总账](2026-10-23-tracking.md)和[审查认领表](../analysis/2026-10-24-unpushed-review.md)，保留未覆盖的硬件条件。

## 9. 设备边界

目前没有新设备试验授权。首次试验仅做一次 RAM 启动、身份查询和限定恢复，不自动重试、不切槽、不刷写、不加载内核或 GPU。开始前阅读[设备操作手册](device-test-playbook.md)并重新确认实际设备状态。

现有设备脚本包含自动重试、未绑定 serial 或自动后续操作，不能直接用于本次单次授权。命令必须有主动终止的主机 deadline；先枚举确认目标，再绑定 serial；协议正文出现 FAILED 即使进程退出码为 0 也按失败处理。超时只停止主机等待，设备侧操作是否结束需另确认。

主机 RAM 下载仍可能触发固件内部副作用。已关闭指定 BDS 日志写盘路径，更早的 BDS/NV 操作和二进制驱动副作用仍有未确认范围。下一次启动前须确认剩余风险与物理恢复条件，无人值守条件尚未成立。
