# Loader 与返回路径审查记录（2026-10-24 审查轮）

本文档是 2026-10-24 审查轮的记录（文件名沿用当时的 2026-10-25 写法，不移动），本次文档任务未修改代码、未构建、未刷写，原始日志未改；其他 agent 正在并行修改内核，行号一律固定于 `hackios-xnu-kernel` 仓库提交 `ec53bac`。两条验收错误与厂商源码事实均由主 agent 直接读取关键源码确认，本文件的修改等待复核，不代替验收。

## 1. 此前验收结论复核未通过两条

### 1.1 「hung 后 `oem log` 仍读实时环形缓冲」不成立

调用链：loader 在另一核心观察内核运行（[loader.c](../../hackios-xnu-kernel/xnuloader/loader.c) L2405 起 `run_on_other_cpu`）。心跳静默满 50 秒判定挂死时，L2488-L2494 调用 `log_of_hung_kernel`（L1135-L1156）把实时环形缓冲整理成有序快照、写入 `loader_ctx[CTX_LOG_PA]/[CTX_LOG_LEN]`，并置 `status = OTHER_CPU_HUNG`；观察循环退出后 L2517 无条件 `running_live = NULL;`，随后才 `return status`。caller（L3573-L3579）打印「THE KERNEL HUNG…」、`set_result("hung")`、`write_logs`（L3578）、`return 1`，其间没有任何代码恢复 `running_live`。

快照的保存与覆盖：`write_logs`（L355 起，L360 调用 `compose_logs`）把挂死判定时刻的内核快照与 loader 日志拼进暂存缓冲 `out_buf`，`out_buf` 即 `get_staged` 发送的内容（L315-L323 注释与定义）。因此判定 hung 之后直接执行 `get_staged` 可以取到该快照；再次执行 `oem log` 因 `running_live` 为空走 `compose_logs(NULL, 0)`（分支 L4035-L4041，函数 L327-L347）：清空 `out_buf`、只复制 loader 自身的 `log_buf`，内核日志参数为 NULL 时不追加，快照被覆盖为仅 loader 日志。hung 之后没有实时环形缓冲的再采集，取不到挂死判定点之后的新输出。run003 停止后两轮立即补采成功发生在 `result` 仍为 running 时（`oem stop` 置 `running_live->stop`，L3872-L3877），属 running 状态行为，不能推广到 hung 之后。playbook §5 与预检门禁记录 §10 已按上述状态语义修正。

### 1.2 「loader 到 `loader_return_after` 时限自动回收控制台」不成立

`loader_return_after` 在 loader 侧解析为 `kernel_budget`（[loader.c](../../hackios-xnu-kernel/xnuloader/loader.c) L3154-L3166），唯一用途是喂看门狗上界：`seconds_since(started) < budget + 60` 时继续 `wdt_pet`（L2477-L2480）。loader 到点不打印、不回收控制台。真正的「--- loader_return_after expired ---」打印与返回来自内核侧 thread_call 定时器（[loader_return.c](../../hackios-xnu-kernel/xnu/files/osfmk/arm64/loader_return.c) L467-L503，banner 在 L469）：依次执行 `redwood_var_save_on_return`、adreno/wifi/adsp 停止，再经 `loader_return` → `psci_smp_stop_others` → `adreno8_quiesce`；quiesce 一类停止环节可能无限等待，各环节都返回后才执行 `loader_jump`，任一环节停住则返回停在该环节；loader 观察循环收到 `other_cpu_done` 后退出。该定时器与停止轮询都注册在 `STARTUP(EARLY_BOOT, STARTUP_RANK_LAST)`（L505、L540），运行需要内核线程已启动并可调度。早期挂死（未执行到注册或线程停滞）时 banner 与返回都没有保证。喂狗窗口与挂死判定是两个独立条件：50 秒心跳静默即判 HUNG（L2492-L2494），该判定不含 budget 条件。L2525-L2529 注释说明虚拟看门狗的设计意图（任何挂死最终以复位结束、不需要人工），该注释不构成任何挂死最终必然复位的真机保证；`WDT_BITE_MS` 在 L3568 重设。「无 banner」必须写成抓取不完整与停止回调未执行两种情况无法区分；补采分类中的 banner 是 host-stop banner（「the host asked for the end of the run: back to the loader」，L513-L540，打印在 L519），旧文写作「启动 banner」。playbook §4 L52 的表述（依赖对应初始化与回调，早期挂起仍可能无法返回）与源码一致，保留。

## 2. loader 生命周期缺陷（必须修复；待安排实现，主 agent 审阅）

busy 判定在 [loader.c](../../hackios-xnu-kernel/xnuloader/loader.c) L3862-L3864：`busy = running_live != NULL || firmware_fault`。`firmware_fault` 仅在 UEFI 异常处理器置位（L2612-L2616，L2614），HUNG 路径没有设置它，而 `running_live` 已在 L2517 清空。于是 `result: hung` 状态下 busy 为空，L3866-L3871 的命令检查放行 `download:`、`oem run`、`oem ramdisk`、`oem selftest` 等命令，UFS 控制器又已由 `hc_take_back` 收回（L3571）：挂死内核仍可能在自己的核心上运行或持有 GPU、内存资源，此时上传或运行新镜像会与之冲突。手册 §6 已要求先重启，代码没有拦截。最小修复方向：把 held/unknown 的内核生命周期状态与实时日志指针分离，busy 由生命周期状态驱动；只保留 `running_live` 不够，还要处理停止语义与命令检查的互斥。设备移交实验的放行决定必须评估该缺口；修复落地前的恢复入口是 PSCI_SYSTEM_RESET（playbook §6）。

## 3. 厂商 SCM 续传协议与重试语义（实现未改）

固定厂商源码副本 `vendor-qcom_scm-smc.c`（本地固定厂商源码目录，Git 忽略）L125-L169 实现了 WAITQ 续传协议：L136 判定 `IS_WAITQ_SLEEP_OR_WAKE`，L137-L139 取 a1 等待队列句柄、a2 调用上下文、a3 标志，SLEEP 分支 L152-L155 `wait_for_completion` 后 `fill_wq_resume_args` 续传，WAKE 分支 L157-L158 `fill_wq_wake_ack_args` 加标志处理，队列上下文取回在 L104-L123。此前审查者「厂商对 2/3 无特殊处理」的说法与上述原文不符。项目把返回值 2/3 按失败保留、无续传，可作为刻意实验限制继续，必须注明该协议未实现、保留后安全世界可能仍有未完成请求，不能记成「请求已完成且失败」。EBUSY 重试：厂商 L30 定义 `QCOM_SCM_EBUSY_MAX_RETRY` 为 20，L196-L200 用 `retry_count++ > QCOM_SCM_EBUSY_MAX_RETRY` 控制（另有 NORETRY 分支），调用次数上界 22；项目 [adreno8_secure.c](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_secure.c) L14、L107 的循环上界 20，总尝试不超过 20 次。项目更保守，两处写法有差异，文档不得声称完全一致。

## 4. 文档状态与措辞修正（已完成，等待复核）

- [交接文档](../plan/2026-10-24-gpu-handoff.md) §6：旧文「设备留在已验证可启动的 iOS 16.5 配置，当前为软件绘制」改为 run003 最后观测（PSCI 复位后 xnuloader idle、slot a 未变），链接预检门禁记录 §12；softpipe 快照注明采集于 2026-10-24 软件绘制桌面时段，属历史观测，当前设备状态需重新读取；「本轮已经暂停」改为 run003 完成与审查进行中的当前状态并链接最新记录。
- [真机手册](../plan/device-test-playbook.md) §5：三档分类改用 host-stop banner 名称，「banner 未见」写明两种成因无法区分；适用状态 running 写明，hung 后写明快照只保留在 HUNG 分支预先组装的暂存内容中、直接 `get_staged` 可取、再次 `oem log` 覆盖为仅 loader 日志；§6 的 hung 条目注明代码当前不拦截上传与运行命令；reboot 措辞统一为 PSCI_SYSTEM_RESET 加重新枚举与 `result` 判据（`loader.c` L4042-L4047，不经 UEFI reset 回调），不承诺安全内存归属清除。
- [预检门禁记录](../progress/2026-10-25-gpu-secure-preflight.md) §9：OTHER_CPU_HUNG 路径行号由 L3571-L3577 修正为 L3573-L3579；§10 三档分类与 hung 后快照语义同步修正。
- [交接文档](../plan/2026-10-24-gpu-handoff.md) §4 与[修订记录](../progress/2026-10-25-gpu-secure-revision.md)：WAITQ 与重试措辞按 §3 修正。
- 「冷重启/冷复位」在受控文档中一律指实际 PSCI_SYSTEM_RESET 调用及重新枚举结果；安全内存归属是否清除未经真机验证，不作保证。

## 5. 待修复与待复核项简表

| # | 位置 | 问题与影响 | 状态 | 验收 |
|---|------|-----------|------|------|
| 1 | [loader.c](../../hackios-xnu-kernel/xnuloader/loader.c) L3862-L3871、L3573-L3579、L2517 | hung 后命令检查放行上传与运行命令（§2） | 第六轮主机有限验收通过（§7，固定 hash `71082b55…`）；`313033ad`/`782b630b` 正式构建与产物有限验收已完成（内核链记录 §3），真机运行未确认（L1 轮 B），未部署、未 mode1 | hung 状态下 `download:`、`oem run`、`oem ramdisk` 被拒绝，并有对应检查 |
| 2 | [adreno8_gmu.c](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_gmu.c) L77-L89 | `dsb sy`、`dc civac` 内联汇编缺 memory clobber，周边内存访问可被编译器重排 | 待修复 | 补 clobber 后主机检查与构建通过 |
| 3 | [adreno8_memory.c](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_memory.c) 旧 secure_execute 分支 | 仍为 CB0 建有效 PTE 且主机测试开启，生产无调用者 | 待修复（建议删除死路径） | 删除后主机测试全部成功 |
| 4 | [adreno8_secure.c](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_secure.c) L209-L219 | 表页只检查起始物理地址，整 PAGE_SIZE 移交、clean 仅 4 KiB | 待修复（统一整页契约防御校验） | 新增页粒度与整页覆盖的主机测试通过；文档不声称 XNU 原生页实际不连续 |
| 5 | [test-adreno8-hwsched.py](../../hackios-xnu-kernel/tools/test-adreno8-hwsched.py) L127 与 [test-adreno8-memory.py](../../hackios-xnu-kernel/tools/test-adreno8-memory.py) | hwsched 测试用 mock allocator，memory 测试不链 hfi，缺真实全链 0 回复测试 | 待修复（补测试） | 真实分配加 HFI 发送、0 回复场景进入一次性终止状态且无第二次 SCM |
| 6 | [adreno8_smmu.c](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_smmu.c) 路由视图判据与 [test-adreno8-smmu.py](../../hackios-xnu-kernel/tools/test-adreno8-smmu.py) | 新 M/hits 判据不强制自有 GMU 控制路由在场，全 SMR=0 也可通过 | 待修复（判据与测试） | SCM 调用前验证 GMU_MATCH 预期条目的 SMR、TYPE、CB 读回一致且对应 CB `is_on`，缺失时直接拒绝该次 SCM 调用 |
| 7 | [mkpayload.py](../../hackios-xnu-kernel/xnuloader/mkpayload.py) | 校验完成后重新读取输入文件；name 静默截断、NUL、专用字段旁路 | 固定 `ec53bac` 的临时复现已由独立 agent 报告，主 agent 未逐项复核；修复进行中 | 复现成立后修复，并用截断、NUL、旁路用例覆盖 |
| 8 | [frames.py](../../hackios-xnu-kernel/tools/frames.py) L95 | 过滤 ≥100 ms 卡顿，输出阈值标签与实测帧时不符（18/34.5 对 16.7/33） | 有限范围源码审阅通过；5 项测试由实现 agent 执行成功；未独立复跑、未真机验收，未提交 | 修复交付并通过复核 |
| 9 | 一次性构建溯源流程（见预检门禁记录 §10、§11 构建部分） | dirty 只输出不断言、fetch 浮动 HEAD、失败轮固定日志被 rm 覆盖 | 待修复（下一次构建做最小流程修正） | dirty 非空即停止；记录明确提交号；失败轮日志保留 |
| 10 | SCM WAITQ 文档口径（[adreno8_secure.c](../../hackios-xnu-kernel/xnu/files/bsd/dev/adreno8_secure.c) 失败语义、交接文档 §4） | 协议未实现、可能有未完成请求需注明（§3） | 文档已改，实现未改，待复核 | 主 agent 复核通过 |
| 11 | 重试语义文档口径（`adreno8_secure.c` L14/L107 对厂商 L196-L200） | 与厂商写法有差异，文档不得声称完全一致（§3） | 文档已改，待复核 | 主 agent 复核通过 |

## 6. 状态汇总

本次文档任务未修改代码、未构建、未刷写，原始日志未改；其他 agent 并行修改内核的工作不在本文件验收范围。§1 到 §4 的文档修订等待复核。§5 第 1 项第六轮主机有限验收通过（§7，固定 hash `71082b55…`），`313033ad`/`782b630b` 正式构建与产物有限验收已完成（内核链记录 §3），真机运行未确认（L1 轮 B），未部署、未 mode1；第 2 到 6、9 项待修复，第 7 项修复进行中（临时复现已报告、未逐项复核），第 8 项有限范围源码审阅通过、5 项测试由实现 agent 执行成功、未独立复跑、未真机验收、未提交，第 10、11 项文档已改、等待复核。移交实验放行与 §2 缺口一并决定。

## 7. loader 生命周期保护候选轮次（第二轮未通过；第六轮主机有限验收通过、未部署，2026-10-24）

来源与核对：候选轮 diff 归档在 Git 忽略的归档目录。[loader.c](../../hackios-xnu-kernel/xnuloader/loader.c) 的 diff 基址是 `hackios-xnu-kernel` 提交 `ec53bac` 的 blob `2369d64c62ce48219627ca57c2631512640b164a`，即针对 §2 缺口的续修。本文作者复算：diff 对 `ec53bac` 的 `xnuloader/loader.c` 干净应用，结果文件 sha256 为 `5a03a09b1db95ce058339bf54632b5ea81da94306f1699fada93fa5a9a673a15`，与候选附带的 SHA256SUMS 记录一致；新增主机测试 `tools/test-loader-lifecycle.py`（718 行）sha256 为 `3df16e8c5c18eb0f04842478b7c24a36f2849cee2d4d2bb3692d4a0295789a7a`，同样一致。独立审查已完成，结论为未通过（[第二轮审查报告](local/astra-loader-rev1-review-5a03a09b.md)，归档目录不随仓库分发）。修订者随后获第三轮授权，后续结果见本节末第六轮段落。本节全部行为是候选代码行为：真机尚未部署，当前设备按 §2 与手册现行指令操作；修复并通过独立验收、实际部署后，手册操作指令再同步修改。

独立审查确认的两项阻塞（最终报告结论，本文作者在候选文件中确认了同样的代码行为）：其一，`active_watch` 例外范围过宽。`run_on_other_cpu` 在 CPU_ON 返回后无条件置 1，非 0 的失败或未知答复同样置位，观察循环前的 `flush_log()` 在例外生效期间执行（annibale 平台 `log_other_cpu = 1`），held=1 时真实发生分区查找与块写，审查者的最小桥接反例实测 `find_calls=1`、`written_blocks=1`；固件异常入口不清 `active_watch`，annibale 分支置 `firmware_fault` 后进入命令轮询死循环，调用方的清例外永不执行，另一分支 `flush_log` 也继承该例外。其二，USB 超时只完成等待有界化，buffer 与 endpoint 所有权未处理：超时不取消在途传输，`usb_rx` 可对同一 OUT buffer 重新排队接收，`usb_tx` 可先改写 IN buffer 再发送，旧请求是否仍持有这些 buffer 未确认；`abort_xfer` 在 `efi.h` 有定义、本版未调用。以下段落中「意图」描述候选代码的设计目标，实际是否达成以上述两项为准。

生命周期状态与持有条件：候选新增 `kernel_resources_held`，与实时日志指针 `running_live` 分离。CPU_ON 发起时持有即置位，调用返回后仅当答复属于显式拒绝白名单（`PSCI_E_NOT_SUPPORTED`、`PSCI_E_INVALID_PARAMS`、`PSCI_E_DENIED`、`PSCI_E_INVALID_ADDRESS`）才清除；`ALREADY_ON`、`ON_PENDING`、`INTERNAL_FAILURE`、`NOT_PRESENT`、`DISABLED`、未知负值与正值都保留持有。

释放条件：唯一释放点在 `lc_after_return`。内核返回后，对本轮交给 XNU 的每个核心发 `PSCI_AFFINITY_INFO`（内核跑在另一核心时含 `cpu_mpidr[0]`，loader 自身核心不查询），全部答 off 才清除持有，随后才执行 `hc_take_back` 与中断恢复；有核心未答 off 则保留持有，并打印「core %x: the firmware answers %d to the question whether it is off: restart before running another」。

返回状态：正常返回分支改为 `set_result(kernel_resources_held ? "returned-held" : "returned", klog_len, 0)`，`getvar:result` 原样返回该字符串（`ec53bac` L3886-L3887 的 `fb_reply("OKAY", last_result)` 路径）。挂死判定仍记 `hung`，候选未改该值，hung 状态下持有同样未清除。

命令门控：live、固件异常或持有状态下，`oem ramdisk`、`download:`、`oem run`、`oem selftest`、`oem hang`、`oem recording`、`oem sound`、`oem clearscreen`、`oem memmap`、`oem probe`、`oem logwrite` 一律拒绝；held 且非 live 时回复 `FAIL a kernel may still hold memory or devices: reboot to start over`。returned-held 之后上传新镜像与重跑被拒绝，出路是复位。日志取回的设计意图：held 时 `write_logs` 跳过分区查询与块写（不调 `find_log_partition`），暂存内容由 `get_staged`（线上命令名 `upload`）取回，读暂存缓冲本身不触块设备；写 `boot_a` 的 `oem logwrite` 在拒绝清单内。独立审查的两项结论限制该段：例外范围问题说明 held 全程无分区查询与块写这一意图未成立（阻塞项其一）；USB 超时后传输所有权未确认，`get_staged` 在命令层允许读取，实际传输恢复未验收（阻塞项其二涉及 IN/OUT 两个方向），不能写成取回暂存文本不受影响。

`oem stop` 三态：live 写 `stop = 1` 并回复 `OKAY`；held 且无 live 内核不写 stop，回复 `FAIL no kernel to notify: memory and devices may still be held (reboot to start over)`；idle（未启动任何内核）不写 stop，回复 `OKAY`，与现有行为一致。

观察循环与 USB 服务边界：watch 轮内超时判定成立即结束该轮，charger、block、USB 服务在判定后不再运行；watch 循环内的协作服务是唯一列出的例外，以超时判定所在轮结束为界。USB 事件等待的 3 秒上限从仅 live 扩展到 live 或 held，完成了等待有界化；超时不取消在途传输，接收方向可对同一 OUT buffer 重排、发送方向可先改写 IN buffer 再发送，旧请求是否仍持有这些 buffer 未确认，候选注释称丢失传输按既有方式自然恢复超过当前代码与测试范围，该声明未通过审查（阻塞项其二），不能写成 USB 超时已安全恢复。held 路径推迟恢复 daif 与 group1，到释放点才恢复；`reboot` 在 held 时跳过 `hc_take_back` 与 `flush_log`，直接调用 `reset_system`。

主机测试：`tools/test-loader-lifecycle.py` 把 loader 的 LC、LC-WRITE、LC-WATCH、LC-RETURN、LC-USB 标记块原样提取编译，PSCI 常量用测试独立书写的规范数值交叉断言；实现者自记录运行含生产逻辑检查、7 条变异检查与调用点顺序检查，均报告通过。独立审查者复跑：原 host 测试 exit 0、7 条变异重新执行均真实失败，另以最小桥接反例实证阻塞项其一（`find_calls=1`、`written_blocks=1`）。host 验证范围不含 `exception_handler`、`usb_rx`/`usb_tx`、真实 `fb_command` 与复位命令分支，完整 UEFI 构建与真机行为未在本轮进行。结果级别：独立审查已完成（host 范围，未通过）；中断恢复与 note/IRQ-mask 内联部分只有调用点与顺序检查，真机行为待部署后观察。

第六轮有限验收（通过，当前结论）：修订者经第三到第五轮处理后提交第六轮，固定输入 loader.c sha256 `71082b55956fb54ea83fd2677026004faf9556e2ad63daed16733bba0017fe8a`、测试 driver `f7be85d40a60c237b183ca3080be12a02302ad851f07d1ba3a092aff4975f8d0`、harness `8af09586c56d9ba329b844a3ab8f9ddc695464f03be1610ba0dfe78ca5dd622e`（交付清单见归档文件 [loader-lifecycle-rev5-SHA256SUMS](local/loader-lifecycle-rev5-SHA256SUMS)）。独立审查核对三项哈希相符并确认三个 USB 缺口关闭：短事件先按类型与尺寸过滤再读字段；lost 标志置位后迟到事件不再解析、不执行命令；queued 请求仅在 buffer 与长度同提交记录一致时接续复用。独立复跑：固定 host exit 0、19 个变异均被检出、lost/short/queued 独立反例全部符合预期、移除旧保护的三个变异按预期失败，命令与退出码见 [loader-round6-commands.json](local/loader-round6-commands.json)。审查报告见 [第六轮验收报告](local/astra-loader-round6-review-71082b55.md)；上述路径在 `docs/analysis/local/` 归档目录（Git 忽略，仅本机保留，不随仓库分发）；必要结论已写入本文，归档件不作为唯一依据。保留的准入边界：单 endpoint 单未完成请求、每请求一个终态通知是软件层明确假设，真实固件通知终止语义、DMA 终止、IRQ 屏蔽下 USB 可达性、同步 `handle_event` 返回均待真机验证；不确定通知保留缓冲并停用 endpoint，不依赖 `abort_xfer` 语义，恢复依赖外部复位。本轮只验证固定 host 输入；其后 `313033ad` 正式 run 已含本变体，`782b630b` 完成 build-id 增量双变体正式构建与产物有限验收（内核链记录 §3），真机运行未确认（2026-10-24 L1 轮 B），未部署，mode1 设备操作另行审核。本节此前各段为第二轮（rev1）历史记录。版本链：`795c1a6` 已提交第六轮固定输入（`loader.c` sha256 `71082b55…`，本文件复算一致）；build-id 增量（`782b630` 起，HEAD `c0716bf` 的 `loader.c` 为 `af54316e…`）不在第六轮固定输入内，主 agent 确认该增量已单独通过独立验收；2026-10-24 L1 轮 B 单次 RAM 启动未确认新 loader 进入运行，mode1 真机未做；两版本链分别记录见[内核链进度记录](../progress/2026-10-24-kernel-chain-progress.md) §4。
