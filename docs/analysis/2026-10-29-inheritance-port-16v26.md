# inheritance port 失败的真实来源：16.5 launchd 与 26 内核的线上格式错配（2026-10-29）

## 1. 结论

fixguard／fixguard2／fixguard3／fixguard4 的载荷把系统盘指到了 2,492,227,584 字节的 `userland/system.apfs`（16.5 用户态），在 26 内核上跑 16.5 launchd。`could not set up inheritance port` 是这次错配的产物。按 fixguard 那轮 EXC_GUARD 的 payload 反推（第 6 节），16.5 的 `mach_ports_register` 在线上发的是一个 OOL 端口数组；26 内核对同一 msgh_id 的服务端按三个 inline 端口描述符解析（第 5 节），两边对不上。

按工程含义排三条：

- **守卫补丁的验证与这条失败无关。** `ool_port_array_enforced=0` 挡掉的是 16.5 客户端被 26 的 `IPC_SEC_POLICY_RESTRICT_OOL_PORT_ARRAYS` 杀掉这件事；26 用户态在这条路径上不发 OOL 端口数组，所以关或不关都不影响 26 配置。
- **26 配置不缺这条路径。** round C／D／E／F 用 26 用户态在同一内核上过了 launchd 这一步（实测）；源码与 ABI 表指向两侧描述符布局一致（推断，见第 5 节）。
- **处置是不投入。** 16.5 用户态不是本项目的目标配置；这条失败只在有人漏写 `SYSTEM`／`SYSTEM_WINDOW` 时出现。建议按低优先级登记，不阻塞主线。

## 2. 载荷错配的实测依据

`tools/k90auto/make-payload.py:49` 的 `SYSTEM` 默认值是 `hackios-xnu-kernel/userland/system.apfs`，`SYSTEM_WINDOW` 缺省为空，超过 `0xffffffff` 的镜像必须有窗口才允许打包。26 镜像需要显式传这两个变量。

| 镜像 | 大小 | sha256 前缀 | 用户态 | 用它的轮次 |
| --- | --- | --- | --- | --- |
| `userland/system.apfs` | 2,492,227,584 | `1b33770d…` | arm64／2023 构建 | bbmetal11-panic、bbmetal12、fixguard、fixguard2、fixguard3、fixguard4 |
| `userland/system26.apfs` | 4,925,816,832 | `d11083be…` | arm64e／iOS 26 | roundb、C、D、E、F 等 30 余轮 |

日志侧对得上：round C 与 round F 的 launchd 是 `libxpc_executables-3102.160.5~128`（2026-07-30），fixguard3 的是 `libxpc_executables-2462.120.4~11`（2023-04-17）。两行原文分别在 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundc/run/hung-held.log`、`…-roundf/run/hung-held.log`、`…-fixguard3/run/hung-held.log:2196`。

两份 launchd 都在本地：`hackios-xnu-kernel/ios165/rootfs/sbin/launchd`（525,088 字节，版本串 `libxpc_executables-2462.120.4~11`，与 fixguard3 日志第 2196 行逐字一致）是实际跑的那一份；`hackios-xnu-kernel/ios26/rootfs/sbin/launchd`（620,432 字节，版本串 `libxpc_executables-3102.160.5~128`）是 26 的那一份。两者的 `start()` 是同一段代码的两次编译，下面的反汇编两份都做了，地址给的是 16.5 那份。

这条失败在真机轮次之前已经出现过一次，出处是 [iOS 26 移植计划](../plan/2026-10-26-ios26-port.md)第 5 节：2026-10-26 在 QEMU 里挂 16.5 根文件系统启动 16.5 launchd，同样报 `could not set up inheritance port` 后退出，当时的处置是「iOS 16.5 用户态在 12377 内核上只作冒烟测试，不继续处理」。QEMU 那条路径没有本轮的 cmdline、没有 AIR、没有 loader 槽位，失败形态一致，说明它与设备侧这些变量无关。

## 3. 失败点落在哪一个调用（实测）

三行原文见 `…-fixguard3/run/hung-held.log:2198-2206`。`namespace 7` 是 `OS_REASON_LIBXPC`（`hackios-xnu-kernel/out/xnu12377/bsd/sys/reason.h:151`），说明 os_reason 由 libxpc 一侧构造，串本身来自 launchd 自己的代码。

「could not set up inheritance port」在两份 launchd 里各出现一次：16.5 那份在 file offset `0x5492b`（VA `0x10005492b`），26 那份在 `0x6255b`（VA `0x10006255b`）；两份的唯一 xref 都在 `start()` 里（16.5 调用点 `0x100012ffc`，26 是 `0x1000186b4`）。`start()` 这一段有三个出口，只有第三个会带上这条串：

| 调用 | 16.5 地址 | 26 地址 | 失败时的表现 | 本轮日志 |
| --- | --- | --- | --- | --- |
| `task_set_special_port(mach_task_self, 4, 0)` | `0x100012e90` | `0x10001852c` | 打 `Could not neuter bootstrap port: 0x%x` 后 `exit(1)` | 没有出现 |
| `mach_port_construct(mach_task_self, options, 0x70507, &name)` | `0x100012eb8` → `sub_100012980` | `0x100018558` → `sub_100017FE8` | 打 `Bug in libxpc: mach_port_construct() failed` 后 `__break(1)` | 没有出现 |
| `mach_ports_register(mach_task_self, {name}, 1)` | `0x100012ed0` | `0x10001856c` | 打 `could not set up inheritance port` 后 abort | 命中 |

所以失败的是 `mach_ports_register` 这一次调用返回了非 0；前两个调用都成功了。这个判定在 16.5 与 26 两份二进制上一致，与日志里的 launchd 版本无关。

## 4. 被登记的端口是什么（实测）

16.5 的 `sub_100012980` 构造的 `mach_port_options_t`：flags `0x433`、`mpl_qlimit` `0x80`、`service_port_info64` 指向一份 `mach_service_port_info_data_t`，其中名字为 `com.apple.xpc.launchd.domain.system`、`mspi_domain_type` 为 `7`；`mach_port_construct` 的 context 是 `0x70507`。

flags 按 `osfmk/mach/port.h:509` 起的定义拆开：`0x433` = `MPO_SERVICE_PORT`（`0x400`）｜`MPO_STRICT`（`0x20`）｜`MPO_INSERT_SEND_RIGHT`（`0x10`）｜`MPO_QLIMIT`（`0x02`）｜`MPO_CONTEXT_AS_GUARD`（`0x01`）。这段代码里叫 inheritance port 的就是它：launchd 给后续作业准备的可继承服务端口。

26 那份的同一处 flags 是 `0x24B3`，多出 `MPO_ENFORCE_REPLY_PORT_SEMANTICS`（`0x2000`，与 `MPO_SERVICE_PORT` 合起来即 `MPO_STRICT_SERVICE_PORT`，`osfmk/mach/port.h:521`）与 `MPO_IMMOVABLE_RECEIVE`（`0x80`），名字与 context 相同。

## 5. 内核侧这条路径要求什么（源码）

**服务端只接受三个 inline 端口描述符。** `osfmk/mach/task.defs:136-146` 用 `#if LIBSYSCALL_INTERFACE` 把这条 routine 分成两个形态：用户侧是 `mach_ports_register(target_task; init_port_set : mach_port_array_t = ^array[] of mach_port_t)`，内核侧是 `_kernelrpc_mach_ports_register3(target_task; port1; port2; port3)`。内核实际编译的是后者。

生成的检查在 `BUILD/obj/DEVELOPMENT_ARM64_BCM2837/osfmk/DEVELOPMENT/mach/task_server.c:502-522`：要求 `msgh_bits & MACH_MSGH_BITS_COMPLEX`、`msgh_body.msgh_descriptor_count == 3`、`Head.msgh_size == sizeof(__Request)`，三个描述符各要求 `type == MACH_MSG_PORT_DESCRIPTOR` 且 `disposition == 17`（`MACH_MSG_TYPE_MOVE_SEND`）。任何一项不符合直接返回 `MIG_BAD_ARGUMENTS`，函数体不进。

**服务端拿到端口后还有一道检查。** `osfmk/kern/ipc_tt.c:2184` 起的 `_kernelrpc_mach_ports_register3` 对每个端口调 `ipc_can_stash_naked_send`（`:2203`），该函数是 `!ip_is_currently_immovable_send(port)`（`osfmk/ipc/ipc_policy.c:1084`），失败返回 `KERN_INVALID_RIGHT`。第 4 节那个端口的 label 类型是 `IOT_SERVICE_PORT`，策略表里它的 `pol_movable_send` 为 `true`（`osfmk/ipc/ipc_policy.c:1629-1638`），这一道能过。

**26 用户态一侧按源码与 ABI 表看与 26 服务端一致（推断）。** `libsyscall/mach/task.c:59-77` 的 `mach_ports_register()` 把名字数组截到 3 个后转调 `_kernelrpc_mach_ports_register3`。26 的 `libsystem_kernel` 里有这条 RPC 的桩：`docs/progress/evidence/ios26-abi/mig-26.tsv:190` 记 `3403 __kernelrpc_mach_ports_register3 0x232f34d18`，紧邻的 3404 是 `__kernelrpc_mach_ports_lookup3`。

按这两处推出「26 用户态发的是三个内联描述符」，属于推断：我没有把 26 那个桩反汇编到描述符字段的逐字节写入，只反汇编到它调用 `mach_msg` 前后一段，也没能解出三个描述符的 `disposition` 与 `type`。stub 地址取自那份 ABI 表。

## 6. fixguard 那轮 EXC_GUARD 的解码（实测）

`…-fixguard/run/hung-held.log:2196` 原文为 `EXC_GUARD AST: type=0x1 flavor=0x43 target=0x800407 code=0x2000004300800407 subcode=0x300000000000011`。

| 字段 | 值 | 含义 |
| --- | --- | --- |
| `flavor` | `0x43` = 67 | `kGUARD_EXC_DESCRIPTOR_VIOLATION`（`osfmk/mach/port.h:637`） |
| `subcode` 高字节 | `0x03` | `MPG_FLAGS_INVALID_OPTIONS_OOL_RIGHT`（`osfmk/mach/port.h:781`），打包方式见 `osfmk/mach/port.h:690` 的 `MPG_PAYLOAD(flag, a) = (flag << 56) \| a` |
| `subcode` 低 32 位 | `0x11` = 17 | `ip_type(dest_port)`，取自 `osfmk/ipc/ipc_types.h` 的 `IKOT_TASK_CONTROL` |
| `code` 低 32 位 | `0x00800407` | 发送方空间里目的端口的名字（`target` 同值） |

`flag` 为 `0x03` 把命中的分支定到 `osfmk/ipc/ipc_policy.c:896` 的 `!ip_is_port_array_allowed(dest_port)`，判据是 `ip_type(dest_port) != IOT_CONNECTION_PORT_WITH_PORT_ARRAY`（`osfmk/ipc/ipc_port.h:342`）。`0x01`（`OOL_DISP`，`osfmk/ipc/ipc_kmsg.c:2428`）与 `0x02`（`OOL_ARRAYS`，`osfmk/ipc/ipc_policy.c:909`）两个分支都不是。

由此得到的实测结论：被杀的消息是 launchd 发给自己 task 控制端口的、**带 `MACH_MSG_OOL_PORTS_DESCRIPTOR` 的消息**。`ipc_kmsg.c:2754-2758` 对每个 OOL 端口描述符给 `send_dsc_port_arrays_count` 加一，`:893-895` 只要这个计数非 0 且目的端口类型不是 `IOT_CONNECTION_PORT_WITH_PORT_ARRAY` 就触发检查。

## 7. 关掉守卫之后为什么走到 mach_ports_register（推断，有两条实测支撑）

`ool_port_array_enforced` 只作用于一个回调：`ipc_sec_is_policy_enforced` 要求 `maybe_should_apply_cb` 返回真，而 `ipc_sec_policy_should_apply_ool_port_array()` 直接返回该 tunable（`osfmk/ipc/ipc_policy.c:1849-1853`，tunable 定义在 `:99`）。置 0 之后第 6 节那两个位置都不再拦，消息继续走 `ipc_kmsg_copyin_body`（`osfmk/ipc/ipc_kmsg.c:2847`），OOL 端口数组被照原样搬成内核描述符。

推断部分：要传给服务的这条消息，最终要由第 5 节第一段的 MIG 检查判定，而它的线上形态与三个内联描述符不符，于是返回非 0。**实测支撑**有两条：fixguard3 日志里 guard 零出现（`:2197-2206` 之间没有 `EXC_GUARD`），同时 `mach_ports_register` 明确返回非 0。**推断部分**是失败码具体为 `MIG_BAD_ARGUMENTS`，日志没有打出返回值。

这条推断的前提是「带 OOL 端口数组的那条消息就是 inheritance port 的登记消息」。支撑是调用序列：`start()` 在这段里发给自己的 task 控制端口的 Mach 消息只有 `task_set_special_port`、`mach_port_construct`、`mach_ports_register` 三个，前两个的 defs 里没有端口数组（`osfmk/mach/task.defs:228-234`、`osfmk/mach/mach_port.defs:568-578`）。

另一个读法是：fixguard 的 guard 发生在登记成功之后某条更晚的消息上，则 fixguard3 里 `mach_ports_register` 的失败需要另一条独立原因。按「一种原因解释两轮」的标准，前一个读法只留一个待定项（失败码具体值），这个读法要多一个待定项（`mach_ports_register` 为什么失败）。三份日志都不能直接分辨这两个读法；能分辨的做法是在 `_kernelrpc_mach_ports_register3` 或 `ipc_kobject_server` 加一处临时打印（返回值、`msgh_id`、`msgh_descriptor_count`），这需要改内核并重建，本轮按只读约束不做。

## 8. 为什么轮次 C／D 过得去

差别在系统盘，与 cmdline、与 AIR 版本无关。C／D／E／F 用 `system26.apfs`，launchd 是 `libxpc_executables-3102.160.5~128`；按第 5 节的 26 `libsyscall` 实现，它的 `mach_ports_register` 与 26 内核服务端同为三个内联描述符，这一步能过。fixguard 系列用 `system.apfs`，launchd 是 `libxpc_executables-2462.120.4~11`，按第 6 节的 guard payload，线上形态是 OOL 端口数组。

能区分「载荷构成」与「boot-arg 改变消息处理」两个解释的实测只有一次：**同一份载荷只把 `SYSTEM`／`SYSTEM_WINDOW` 换成 `system26.apfs` 那两个值，cmdline 保留 `ool_port_array_enforced=0`。** 若 launchd 打过 boot-args 后继续往下走，则差别在载荷构成；若仍死在 inheritance port，则差别在 boot-arg。按第 5、7 节，预期是前者。

## 9. 守卫补丁的验证与本条失败无关

fixguard3 与 fixguard 的唯一差别是 cmdline 多了 `ool_port_array_enforced=0`。这个差别让 guard 不再触发（fixguard3 日志零 `EXC_GUARD`，实测），但两轮都停在 launchd 打完 boot-args 之后的同一处，因为两轮的载荷都是 16.5 用户态。

因此这条 boot-arg 的「有效」只在 16.5 用户态上成立，不能拿它当 26 配置需要它的证据。26 配置里这条策略是否该保留、该不该带这个参数，要用 26 载荷单独判定；本轮没有做过带／不带该参数的 26 载荷对照，属未查项。

## 10. 实测与推断分界

| 条目 | 性质 | 出处 |
| --- | --- | --- |
| 两套 system 镜像的大小与 sha | 实测 | `userland/` 下两个文件；与 lead 的交叉表一致 |
| 16.5 用户态在 12377 内核上同样死在这一步 | 实测（2026-10-26，QEMU） | [iOS 26 移植计划](../plan/2026-10-26-ios26-port.md)第 5 节 |
| fixguard3 用 16.5 launchd、C／F 用 26 launchd | 实测 | 三个轮次的 `hung-held.log` 版本串 |
| 串出自 launchd、唯一 xref 在 `start()` | 实测 | 16.5 与 26 两份二进制各自反汇编，见第 3 节 |
| 失败调用是 `mach_ports_register` | 实测（日志与反汇编互证） | 第 3 节两个出口都没触发，第三个触发了 |
| inheritance port 是服务端口，名字、flags、domain type | 实测 | 第 4 节 |
| fixguard 被杀的消息带 OOL 端口数组、目的端口是 task 控制端口 | 实测 | 第 6 节 payload 解码 |
| 26 服务端要求三个内联描述符、disposition 17 | 源码 | `task_server.c:502-522` |
| 26 的 `libsystem_kernel` 里存在 id 3403 的 `__kernelrpc_mach_ports_register3` 桩 | 实测（ABI 表） | `docs/progress/evidence/ios26-abi/mig-26.tsv:190` |
| 26 用户态发的是三个内联描述符 | 推断 | 上表那一行加 `libsyscall/mach/task.c:59-77`；桩内描述符字段未逐字节核对 |
| fixguard3 的失败码是 `MIG_BAD_ARGUMENTS` | 推断 | 日志没有打印返回值 |
| 换回 `system26.apfs` 后这条失败消失 | 推断（有 C／D／E／F 的实测支持） | 第 8 节的对照实验未做 |

## 11. 这次查了什么、没查什么

查了：共享缓存 78 个文件流式搜索 `inheritance port`（零命中，未对缓存用 grep）；`ios165/rootfs/sbin/launchd` 与 `ios26/rootfs/sbin/launchd` 两份二进制的 `start()` 与 construct 辅助函数的反汇编；26 内核树里 `task.defs`、`task_server.c`、`ipc_tt.c`、`ipc_kmsg.c`、`ipc_policy.c`、`ipc_port.h`、`port.h`、`ipc_types.h` 的相关路径；三个轮次日志的版本串与失败行；两套 system 镜像的大小与 sha；`docs/plan/2026-10-26-ios26-port.md` 里 QEMU 那条同样形态的记录。

没查：26 的 `libsystem_kernel` 的 id 3403 桩只反汇编到调用 `mach_msg` 前后一段，没有解出三个端口描述符的 disposition 与 type 字段逐字节写入，也没有反汇编 16.5 的对应桩；这两项的结论分别由 `mig-26.tsv` 的符号名与 fixguard 那轮的 guard payload 支撑；16.5 的 `libsystem_kernel` 客户端没有独立反汇编（16.5 的 OOL 形态由第 6 节的 guard payload 反推）；没有跑任何设备命令，没有改代码、产物或 cmdline；没有做第 8 节那个对照实验。

## 12. 给 lead 的决策请求

| 选项 | 具体动作 | 代价 | 验证方法 | 建议 |
| --- | --- | --- | --- | --- |
| A 不投入，只登记 | 不改内核、不改参数；把「漏写 `SYSTEM`／`SYSTEM_WINDOW` 会换掉整套用户态」写成 payload 前置检查，打包时发现系统盘小于 4 GB 或 `SYSTEM_WINDOW` 为空即报错退出 | 一次改 `tools/k90auto/make-payload.py` 的前置断言，约 5 行；无内核风险 | 用现在这两份 manifest 回放：16.5 那份应当被拒，26 那份应当通过 | 推荐 |
| B 靠启动参数兜住 16.5 | 继续在 16.5 载荷上带 `ool_port_array_enforced=0` | 0 行代码；但这条参数关掉的是 26 内核上的一条 IPC 加固策略，对 26 载荷的影响面未测 | 带与不带该参数各跑一次 26 载荷，比较 launchd 之后的日志行数与是否出现 `EXC_GUARD` | 不推荐，只在 A 之外作为临时手段 |
| C 内核算改到兼容 16.5 客户端 | 改 `osfmk/mach/task.defs:141-145` 的服务端形态并在 `ipc_kobject_server` 前后加 OOL 端口数组展开（把 1 个 OOL 数组拆成最多 3 个内联描述符），再让 `task_server.c` 重新生成 | 触碰内核 IPC 描述符投递路径与 MIG 生成物，改动跨 defs、kobject、kmsg 三处，缺陷面大；16.5 用户态不是目标配置 | 只能在 A 的对照实验证明「载荷无关」之后才有意义；验证需要 16.5 载荷重回桌面 | 不推荐 |