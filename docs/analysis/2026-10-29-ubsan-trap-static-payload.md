# static-cbf1689c 早期 UBSAN panic（2026-10-29）

## 1. 三问的判据（登记）

- **检查类别与函数**：`ubsan_minimal.c:81` 在哪个函数里、由哪条宏编出的 BRK 触发；函数归属以「caller 地址落在哪个符号区间」为判据，落不到具体业务函数就写明落不到，不用相邻符号猜。
- **先后关系**：以两条消息在内核输出里的相对位置为判据。`handshake structure not initialized` 若由 panic 输出阶段打印，则为 panic 的后果；若由启动流程打印，则为 panic 之前的事件。
- **载荷差异**：以两份 `manifest.json` 的字段逐项比对为判据，内核可见输入（内核镜像哈希、cmdline、extra boot-args、memsize、identity）全部相同则载荷内容不是变量。

## 2. 实测：`ubsan_minimal.c:81` 是哪条路径

第 81 行在 `ubsan_handle_brk_trap()` 的 `if (!ubsan_minimal_enabled)` 分支里：`panic("UBSAN trap taken in early startup code")`，只在 DEVELOPMENT 构建编入。触发链是 `osfmk/arm64/sleh.c:1324` 收到 BRK 后调用 `ubsan_handle_brk_trap(tstate, comment)`，而此时 `ubsan_minimal_enabled` 仍是 false，即 `ubsan_minimal_init()` 尚未运行。

检查类别：`osfmk/kern/trap_telemetry.h:204` 只定义了一条 soft trap `UBSAN_SOFT_TRAP_SIGNED_OF = 0xFF00`，`ubsan_minimal.c` 的 `ubsan_traps[]` 表也只有 `signed-overflow` 一条。所以类别是**有符号整数溢出**（推断：panic 串没有打印 trap 号，按表里唯一一项判定）。

## 3. 实测：caller 地址反查

内核装载区间 `fffffff007004000..fffffff008764000`，`caller 0xfffffff007caa1d4` 对 `out/xnu12377/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837` 的 89,065 个符号取最近项，命中 `_ubsan_handle_brk_trap.cold.2`，偏移 `+0x0`。

也就是说 caller 记的是 UBSAN 运行库里的 panic 调用点，不是触发溢出的那段代码。**这份日志不能定位到具体函数**；要定位需要 backtrace 或把 `ubsan_handle_brk_trap` 的 `state` 一起打出来。

## 4. 实测：`handshake structure not initialized` 是后果

该串的唯一出处是 `osfmk/kdp/output_stages/out_shmem.c:658`，在 `panic_spin_shmcon()` 里：`hwsd_info == NULL` 时打印并直接返回。它是 panic 输出阶段找不到共享内存调试握手结构时的消息。

所以顺序是：**UBSAN trap → panic → 输出阶段发现没有 handshake 结构**。handshake 不是触发原因。日志里同一段还出现 `Please go to https://panic.apple.com`，那属于握手结构存在时的分支之外的常规输出。

## 5. 实测：与 fixguard6 载荷的逐项差异

| 项 | static-cbf1689c | fixguard6 | 是否内核可见 |
| --- | --- | --- | --- |
| 内核 sha256 | `cf1502f5…` | `cf1502f5…` | 相同 |
| cmdline | 与 fixguard6 只差 `epoch`（1793208658 对 1793206160） | 同 | 相同 |
| extra boot-args | `gpu_log=1 metal=1 cpufreq=1 fb_threads=2 touch_lat=1` | 同 | 相同 |
| memsize／identity | 相同 | 相同 | 相同 |
| 作业 | `rc.jobs.unlockprobe-static`（`d08fef07…`） | `rc.jobs.freezef`（`e6ece111…`） | 用户态任务表 |
| root／ramdisk | `f95bc399…`（新拼） | `c2f96350…` | 用户态内容 |
| 打包工作区 | `dirty_worktree: true`，含 `M tools/k90auto/run-auto.py` 与四个未跟踪脚本 | 干净 | 跑步器与打包脚本 |

内核可见的输入没有一项不同。**载荷内容无法解释早期 UBSAN**；能解释的是起轮路径：这次是冷路径（loader 直接起，上一轮只做 PSCI 复位），日志同段有 `core 10100: the firmware answers 0 to the request to start it`，即只起了 core 0，次级核没起来。

## 6. 候选与判别

| 候选 | 支持 | 推翻它的读数 |
| --- | --- | --- |
| 冷路径起轮后固件拒绝启动次级核，早期启动代码在有符号运算上溢出 | 两条日志都在 `oem run` 后 1.05 秒返回；同段有固件拒绝启动 core 的打印；同一内核走完整路径正常 | 完整路径重跑同一载荷仍 panic |
| 打包工作区带未提交改动（`run-auto.py` 106 行新增）改变起轮动作 | 该改动含收尾与冻结判定，影响起轮前状态 | 用干净工作区重打同一载荷仍 panic |

判别方法：先用干净工作区重打同一份载荷、走完整路径跑一次。不 panic 则第一条成立第二条第不得证；仍 panic 则载荷内容或内核本身有问题，回到第 5 节逐项排查。

## 7. 下一步需要的材料

定位溢出所在函数需要以下任一：内核 panic 时的 backtrace（KDB 或 spindump）、`ubsan_handle_brk_trap` 的 `state` 与 `trap` 号打进 panic 串、或对该内核做一次带 `-fno-sanitize-recover` 与符号的离线反查（在 `sleh.c` 的 BRK 处理处打印 `trap` 号）。

## 8. `core 10100: the firmware answers 0` 不是失败

这一行此前被读成「固件拒绝启动次级核」。内核侧同一件事的代码在 `osfmk/arm64/psci_smp.c:184-191`：

```c
status = psci_call(PSCI_CPU_ON, phys_id, entry, 0);
if (status != 0) {
    os_atomic_store(&psci_smp_cpu_stage[cpu], 0, release);
    printf("psci: cpu %d (MPIDR 0x%x) was not started: the firmware answers %lld (%s)\n",
        cpu, phys_id, status, psci_error(status));
    return KERN_FAILURE;
}
```

`PSCI_CPU_ON` 返回 0 表示成功。失败分支只在 `status != 0` 时进入，并且会打出 `was not started`。日志里那一行只说「对启动它的请求，固件答 0」，也就是**启动成功**，`10100` 是请求的 MPIDR（同一行上文列出的核顺序 `10100 10000 500 400 300 200 100` 都是 MPIDR）。

所以「次级核没起来 → 计数器为 0 → 减出负数 → UBSAN 命中」这条链条不成立：次级核起来了，这一行是正常输出。早期 panic 与它无因果。

## 9. `ubsan_minimal_init()` 之前触发意味着什么

`ubsan_minimal.c` 里 `ubsan_minimal_enabled` 初值为 false，只有 `ubsan_minimal_init()` 把它置 true。该函数带 `__startup_func`，排在 `__BOOTDATA.__init` 的启动函数表里。在它之前跑的代码如果带 UBSAN 检查并真的溢出，`ubsan_handle_brk_trap()` 走 `if (!ubsan_minimal_enabled)` 分支，DEVELOPMENT 构建直接 panic。

检查类别是有符号整数溢出：`trap_telemetry.h:204` 只定义了一条 soft trap `UBSAN_SOFT_TRAP_SIGNED_OF = 0xFF00`，`ubsan_traps[]` 表也只有 `signed-overflow` 一项。

panic 串里的 `caller 0xfffffff007caa1d4` 反查是 `_ubsan_handle_brk_trap.cold.2`，即运行库自己的 panic 调用点，**不是**触发溢出的函数。要定位到具体函数，需要 backtrace 或把 `state` 与 trap 号打进 panic 串。

## 10. 两次正常与三次 panic 的对照表

判据先写：下表填满后，若某一列在三次 panic 里同值、在两次正常里同值且两值不同，该列才是候选；只在一侧出现的列不算。

| 列 | 数据来源 | static-r1 | static-r2 | dealloc | static-r3（正常） | perf-sustain（正常） |
| --- | --- | --- | --- | --- | --- | --- |
| 复位路径 | `reboot.json` 与 device 会话记录 | 完整 | 完整 | 完整 | 完整 | 完整 |
| 起轮前 loader 停留 | `reboot.json` 的 `seconds` | 无关联 | 无关联 | 无关联 | 无关联 | 无关联 |
| 上次收尾状态 | 上一轮的 `teardown`／`hung-held` | 无关联 | 无关联 | 无关联 | 无关联 | 无关联 |
| 起轮前温度 | `hottest` 或取温日志 | 待补 | 待补 | 待补 | 待补 | 待补 |
| 内核 | `kernel.json` | `cf1502f5…` | `cf1502f5…` | `cf1502f5…` | 待补 | 待补 |
| 驱动库 | `manifest.json` | `d296b5a4…` | `d296b5a4…` | `d296b5a4…` | 待补 | 待补 |
| 作业 | `jobs_source` | `freezef` | `freezef` | `freezef` | 待补 | 待补 |
| 结果 | `returned` 时刻 | 1.05 秒 | 1.05 秒 | 1.05 秒 | 240 秒跑满 | 80.5 秒冻结 |

已能读出的一点：三次 panic 的内核、驱动库、作业三项完全相同，两次正常的配置待 device 补齐。若两次正常的内核也是 `cf1502f5…`、驱动库也是 `d296b5a4…`，那么差异只在起轮条件一侧（复位路径、loader 停留、上次收尾状态、温度）。

## 11. 复位路径排除，候选改为「引导层抽签」

device 给了六次引导的完整记录：**六次全部走完整路径**（安卓 → LK → 切 A 槽 → `reboot`），其中三次 panic、三次正常。先前「从 loader 直接起轮」的读法作废，那一列不再是候选。

按第 10 节的判据，剩下三列（复位路径、loader 停留、上次收尾状态）里复位路径在六次中同值，另两列与结果无关联。也就是说**已知的配置与控制量解释不了这三次 panic**，六次里三次失败、三次正常，分布与任何已记录的变量对不上。

这是当前状态：不是「某个已知条件触发」，而是同配置下的不稳定复现。要往前走只有两条：让 panic 自报位置（内核 `3b856b57…` 已带 trap 号与 pc），或按失败率估出还要多少次引导才能拿到一次带定位信息的 panic。

## 12. dealloc 轮的区间比对与字符串片段

dealloc-r2 的 613 组 `begin／freed／destroyed` 三行完整，43 行 bad access、8 条唯一。区间比对做了两遍：

| 区间集合 | 命中 |
| --- | --- |
| `[mesa, mesa+len)` | 0 |
| `[callerBytes, callerBytes+len)` | 0 |
| 两者并集 | 0 |

所以「destroy 之后还有拷贝引用该 buffer」这条在两个区间上都不被支持。

8 条唯一的 `x0`／`x1` 里六条是 ASCII 片段，按小端读出来分别是：

| 值 | 读出 | 判断 |
| --- | --- | --- |
| `0x63616f72502e656c` | `le.Proac` | `…le.Proactor…`，libdispatch 的 proactor 事件循环名 |
| `0x63756f5474656b63` | `cketTouc` | `…cketTouch…`，某个以 Touch 结尾的名字 |
| `0x4e5a5f203a6e6f69` | `ion: _ZN` | 一段把 C++ 修饰名打进去的文本 |
| `0x6573616220646472` | `rdd base` | 某个短语的后半 |
| `0x80000c000c0000` | 非 ASCII | 两个 12 位字段拼在一起的结构值 |
| `0x1` | 非 ASCII | 小整数 |

能认出的三个都是**字符串内容**，不是指针：libdispatch 的 `Proactor`、`…cketTouch…`、含 `_ZN` 的修饰名。这与第 4 节的读法一致——拷贝源指向的是一块被当作指针使用、实际装着文本的内存。要指出这几段字符串的分配方，需要分配器侧的归属信息，这份日志里没有。

## 13. 宽度分布与 fixguard8 相反

| 轮次 | 原始行 | 唯一 | `x2=0x26`（38 字节） | `x2=0xc0`（192 字节） |
| --- | --- | --- | --- | --- |
| dealloc-r2 | 43 | 8 | 1 | 7 |
| fixguard8 | 19 | — | 5 | 14 |
| unlockprobe | 93 | — | 53 | 40 |

dealloc-r2 里 38 字节那一档只占 1/8，unlockprobe 里占 57%。同一调用点、同一实现，两个宽度的比例在不同轮次之间大幅变化，这一项记进对照表，不当候选、也不当常量。

## 14. 用创建记录代替销毁记录：x0 落在活缓冲，x1 一条也不落

`rwa buffer: copied %p of %lu bytes, buffer at %p` 在缓冲创建时打出，给的是 `_contents` 与长度，即一块活着的区间。

| 轮次 | 创建行 | bad 行 | 唯一 | `x0` 落创建区间 | `x1` 落创建区间 | `x1` 落 `region` |
| --- | --- | --- | --- | --- | --- | --- |
| dealloc-r2 | 386 | 43 | 8 | 7/8 | 0 | 0 |
| fixguard8 | 153 | 19 | 5 | 3/5 | 0 | 0 |

`x0` 落在创建区间时都精确等于某块 32,768 字节缓冲的起点，也就是这条拷贝的**写入目标确实是 AIR 的缓冲**。故障在**读侧**：`x1` 既不落任何已创建缓冲，也不落在 `region` 那段共享缓存映射里。

按先写的判据：落在创建区间说明在读一个仍有效的缓冲，方向转「谁把这个缓冲的内容换掉了」；都不落则转「拷贝源的指针字段本身被复用」。实测是后者，下一步要看谁写了那个字段。

这一条同时排除一种可能：野读不在代码段（`x1` 不落 `region`），所以不是「把 pc 当指针」，读源在堆上。

## 15. 三族配对：地址被反复复用，销毁记录缺地址无法配对

按 pid 与缓冲把创建、行拷贝、销毁三族串起来的结果：

| 轮次 | 创建 | 行拷贝 | 销毁 | bad access |
| --- | --- | --- | --- | --- |
| dealloc-r2 | 386 | 217 | 613 | 43 |
| fixguard8 | 153 | 0 | 0 | 19 |

命中的三个地址各自的次数（dealloc-r2）：

| 地址 | 创建次数 | 行拷贝提到 | bad access |
| --- | --- | --- | --- |
| `0x101c48000` | 199 | 125 | 22 |
| `0x102048000` | 113 | 88 | 11 |
| `0x102448000` | 2 | 4 | 2 |

**同一个地址被创建了 199 次**：分配器把同一块 32,768 字节的槽反复给出。所以「地址落在创建区间内」不能说明那个区间对应哪一次缓冲的一生，更不能说明它还活着。上一轮 7/8 与 3/5 的命中率是**按地址区间**算的上界，不是「活缓冲」命中率。

**销毁记录无法与创建记录配对**：`rwa dealloc: begin <n> pid <pid> self <p> mesa <p> bytes <p> len <n>` 没有带 `_contents` 地址。创建与行拷贝都带地址，销毁只带 `mesa`、`bytes`、`len`，三者都不是那块 `_contents`。所以「这块缓冲在这次故障之前有没有被销毁」用现有三族打印答不出来。

补一个字段就能答：`rwa dealloc: begin` 那一行加上 `contents <p>`。这只是加字段，不新增行，也不动顺序。

`x1` 侧的结论不受影响：读源在任何创建区间里都不出现（0 命中），也不在 `region` 内，所以读源既不是活缓冲也不是代码段。

## 16. 判读规则：说「落在区间内」必须注明是哪种集合

地址会被分配器反复复用：dealloc-r2 里 `0x101c48000` 被创建 **199 次**，`0x102048000` 113 次。同一地址的创建记录叠在一起，区间命中不等于任何一次缓冲的存活。

所以任何「某指针落在某区间内」的结论，都要同时写明用的是哪一种集合：

| 集合 | 含义 | 分辨力上限 |
| --- | --- | --- |
| 创建记录 | 该地址曾被某次创建占用过 | 只说明「曾经」，不说明当前是否存活 |
| 剔除已销毁的活区间 | 创建减去销毁 | 需要销毁记录带 `_contents` 地址，当前打印做不到 |
| 单次生命周期 | 一次创建到对应销毁 | 需要创建与销毁能按地址配对 |

2026-10-29 有一个结论因为没区分这三者而偏了方向：`x0` 在创建记录里命中 7/8，被读成「写入目标是活缓冲」，实际只能读成「写入目标曾经作为缓冲创建过」。

## 17. 两轮的命中率不能并列

fixguard8 那轮 `rwa row:` 0 行、`rwa dealloc:` 0 行，只有 153 行创建记录。说明那轮的库没有执行到行拷贝与销毁的打印点（不同库、不同路径），所以：

- fixguard8 的 3/5 只在创建记录上算得出来，没有活区间口径可比。
- dealloc-r2 的 7/8 有行拷贝与销毁打印，两轮的集合不同，命中率不能并列比较。

下一版插桩清单里加一项：`rwa dealloc: begin` 加 `contents <p>`。只加字段、不新增行、不动顺序，排在验收轮跑通之后再安排。

## 18. 断言 panic：`ml_get_cpu_number_local()` 的 MPIDR 映射断言

原文两句：

```
machine_routines.c:1339 Assertion failed: cpu_id <= (unsigned int)ml_get_max_cpu_number()
Synchronous exception taken while SP1 selected at pc 0x0000000000000000
```

**守的是哪个函数**：`osfmk/arm64/machine_routines.c` 的 `ml_get_cpu_number_local()`：

```c
MRS(mpidr_el1_value, "MPIDR_EL1");
cpu_id = ml_get_cpu_number((uint32_t)mpidr_el1_value);
assert(cpu_id <= (unsigned int)ml_get_max_cpu_number());
return cpu_id;
```

`cpu_id` 来自 `ml_get_cpu_number(MPIDR_EL1)`，即用当前核的 MPIDR 在核枚举表里查编号；`ml_get_max_cpu_number()` 是核数上界减一。断言要求「查出来的编号不超过上界」，失败说明**这台核的 MPIDR 没在表里，或者上界还是初始值**。

**四个偏移（用 `handoff-mach-attr26-panicloc` 的符号表，52,370 个符号）**：

| 落点 | 地址 | 符号 |
| --- | --- | --- |
| 断言调用方 | `0xfffffff007aa49b0` | `_panic_with_options` +0x0 |
| FAULT pc | `0xfffffff00738c5b4` | `_vm_fault_internal` +0x74 |
| FAULT lr | `0xfffffff00738c4a8` | `_vm_fault$XNU_INTERNAL` +0x14 |
| 同步异常 lr | `0xfffffff0072ecdb4` | `___doprnt` +0xdc |

断言由 `panic_with_options` 打出，符合预期。同步异常那两条落在缺页处理与格式化输出里：`vm_fault_internal+0x74` 是缺页路径，`___doprnt+0xdc` 是 panic 串格式化，而 `pc 0x0` 说明异常发生在一次空指针调用上——panic 打印过程中又撞了一次缺页或空调用。

**未确认的一项**：`ml_max_cpu_count`（或等价上界）在这份移植里的赋值点还没读到。容器树里 `osfmk/` 下检索 `ml_max_cpu_count` 没有命中，赋值可能来自移植侧的设备树解析或 PSCI probe，需要对着 `xnu/files/` 那一侧再读一遍。这一项决定「次级核先跑、上界后发布」这条竞争是否成立，读清之前不当结论。

**与 UBSAN 那条的关系**：两条签名不同（一个是 MPIDR 映射断言、一个是早期有符号溢出），共同点都落在早期启动。能否归到同一根因取决于上一条未确认的赋值顺序：若上界在次级核启动之后才发布，那么次级核进 `ml_get_cpu_number_local()` 会撞断言，而同一时段里别的计数器为 0 再减出负数就撞 UBSAN，两条就是同一竞争的两副面孔；若上界在次级核启动之前就已就位，那么两条要分开解释。

**能证实或推翻的读数**：在断言前打印 `cpu_id` 与 `ml_get_max_cpu_number()` 的实际值（一行），以及在 `ml_max_cpu_count` 赋值处打印一次。前者给出「表里查到了几号、上界当时是多少」，后者给出「上界在什么时候就位」。

## 19. 读到赋值点了：次级核在核数上界发布之前就被启动

移植侧的核枚举在 `xnu/files/iokit/Kernel/GenericARMPE.cpp`（8796 原树没有这段，见该文件头部注释：它按 boot-arg `cpus=N` 与设备树 `/cpus` 建 `GenericARMCPU`）。顺序是：

```c
for (每一个 /cpus 子节点) {
    GenericARMCPU * cpu = new GenericARMCPU;
    if (cpu->init() && cpu->attach(nub)) {
        if (cpu->start(nub)) {      /* 启动这颗核 */
            cpus[number] = cpu;
            count++;
            continue;
        }
        ...
    }
    ...
}
if (cpus[master_cpu] != NULL) {
    ml_set_max_cpus(count);          /* 上界在这里才发布 */
    ...small_cores_after...
    cpus[master_cpu]->run();
}
```

**`cpu->start(nub)` 在循环里，`ml_set_max_cpus(count)` 在循环之后。** 次级核在核数上界发布之前就被放出去了。

`ml_set_max_cpus()` 在 8796 的 `osfmk/arm/machine_routines_common.c:1271`，内部按 `max_cpus_initialized` 做状态机（`MAX_CPUS_WAIT` 时唤醒等待者）。断言读的 `ml_get_max_cpu_number()` 在这之前返回未发布的值，次级核此时调 `ml_get_cpu_number_local()` 就会撞 `cpu_id <= ml_get_max_cpu_number()`。

这条解释了抽签：次级核与主核的时序决定它是在发布之前还是之后进那条路径，所以六次里三次中就落在这里。

**第 4 问**：那行 `core 10100 … answers 0` 之后，内核没有等次级核进入成功再继续——`cpu->start(nub)` 返回即继续下一个核，发布在循环之后。

**与 UBSAN 那条的关系**：竞争的存在已经证实（不是推断），但两条签名是否同根还差一步——需要看 UBSAN 命中的那条有符号运算是否同样发生在次级核的启动路径上。判据：若在断言前打印 `cpu_id` 与 `ml_get_max_cpu_number()` 的实测值，同时 UBSAN 那轮（内核 `3b856b57…`）拿到 pc 落在 `psci_smp.c`／`machine_routines.c` 一类启动路径上，则两条同根；若 pc 落在别处，两条分开解释。

**修法方向**（形状待定）：把 `ml_set_max_cpus()` 提到 `cpu->start()` 之前，或让次级核的启动路径在发布之前用表长而不是上界。两者都是内核行为改动，要重编并连跑若干轮验证发生率。
