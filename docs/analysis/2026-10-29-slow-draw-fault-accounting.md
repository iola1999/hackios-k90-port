# 慢 draw 缺页计数口径核对与替代判据（2026-10-29）

这份文档核对 2026-10-29 慢 draw 读数里 `flt 196` 的口径，回答四个问题：这个数计不计 IOKit device pager 建立的缺页、能不能按线程取缺页数、24 条读数上的回归能否复现、判据怎么改写。读数取自 `docs/progress/evidence/k90auto/kernel-12377-attr26-diag3x-statefault/run/` 下的 `s001.log` 到 `s007.log` 与 `hung-held.log`，内核源码取 `hackios-xnu-kernel/out/xnu12377/`，驱动源码取 `hackios-xnu-kernel/xnu/files/iokit/Kernel/`。每条结论标注「实测」或「推断」。

## 1. 四个问题的答案

### 1.1 device pager 的缺页计不计入，算 minor 还是 major

答案：计入 `task->faults`，在 getrusage 口径里算 minor。196 是进程级缺页数，覆盖该进程所有线程和所有映射，不指向绘制线程。

（实测）`vm_fault_internal()` 在通过 `map->never_faults`、抢占级、`th_vm_faults_disabled` 三个早期返回之后，先执行 `counter_inc(&vm_statistics_faults)` 与 `counter_inc(&current_task()->faults)`（`osfmk/vm/vm_fault.c:4974-4975`）。`vm_fault_wire_fast()` 另有一条同样的任务计数（同文件 7886-7890）。

（实测）`getrusage(RUSAGE_SELF)` 的 `ru_minflt` 与 `ru_majflt` 由 `calcru()` 每次现算：`ru_minflt = faults - pageins`，`ru_majflt = pageins`（`bsd/kern/kern_resource.c:1781-1783`）。两项相加恒等于 `TASK_EVENTS_INFO.faults`（`osfmk/kern/task.c:5727`，64 位计数先截到 `INT32_MAX`）。补丁里的 `flt = ru_minflt + ru_majflt` 就是这个和的窗口增量。

（实测，按 osfmk/vm、osfmk/kern、bsd/kern、bsd/vm、iokit/Kernel 逐文件扫描）`pageins` 的增加点有两类：聚类读入页的 `VM_PAGE_COUNT_AS_PAGEIN`（`osfmk/vm/vm_page_internal.h:1138-1151`，调用点是 `vm_fault.c` 的 2314、2525、2630、2651、4065、5856 行）和 UPL 聚类页入（`osfmk/vm/vm_pageout.c:7139-7142`）。两条都要求页由 pager 的簇读或 UPL 预读带进来。

（实测，按源码走查）本项目的 GPU BO 映射没有经过 device pager。`RedwoodGPUMemory.inc:312-313` 用 `IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task, kIODirectionInOut | kIOMemoryKernelUserShared | ..., size, PAGE_SIZE)` 分配；`RedwoodGPU.cpp:608-624` 的 `clientMemoryForType` 直接返回这块描述符；`IOUserClient::mapClientMemory64` 调 `createMappingInTask`（`iokit/Kernel/IOUserClient.cpp:2084`）。

（实测，按源码走查）描述符的 `_task` 是 `kernel_task`（`iokit/Kernel/IOBufferMemoryDescriptor.cpp:445-450` 传 `inTask ?: kernel_task`，`iokit/Kernel/IOMemoryDescriptor.cpp:2220` 赋值），`memoryReferenceCreate` 走 `_task` 分支，用 `mach_make_memory_entry_internal(kernel_map, ...)` 建命名条目（`iokit/Kernel/IOMemoryDescriptor.cpp:590-716`），映射由 `memoryReferenceMapNew` 完成。device pager 只在 `_task == 0`（physical 或 UPL 描述符）时创建（同文件 784-828）。

（实测，按源码走查）走 device pager 的那条路结论相同：`populateDevicePager()` 在映射时把整段物理页填进 pager 对象（`iokit/Kernel/IOMemoryDescriptor.cpp:5553-5619`，调用点 5390-5391），之后用户态首次触碰同样是 cache hit，`pageins` 不增加。

（实测，按源码走查）命名条目的对象就是内核缓冲区所在的 vm_object（`osfmk/vm/vm_memory_entry.c:783-953`），映射进来的页是常驻页。用户态首次触碰走 cache hit 加 `vm_fault_enter`，`pageins` 不增加，按 `calcru` 的定义落进 `ru_minflt`。

（实测）计数点不看 map 参数，所以进程里其它线程的缺页、其它映射的缺页、系统调用里对用户缓冲的 copyin／copyout 缺页都算进同一个 196。`TASK_EVENTS_INFO.faults` 是任务计数，不区分线程。

（推断）页面若在窗口内被压缩或换出，再次触碰会产生解压或 pager 读入，这部分会计入 `pageins`。补丁把 minor 与 major 加成一个数打印，这 24 行里两者的比例无从还原。

196 的准确含义：在那个 state 段的墙钟窗口里，进程（日志里 `redwood lib loaded pid 38 name backboardd`）所有线程合计进入 196 次 `vm_fault`。它描述的是整进程的缺页次数；绘制线程自己的缺页次数未知。

### 1.2 有没有按线程取缺页数的接口

答案：没有。用户态拿不到单线程缺页数，XNU 也没有在线程上维护这个计数。

（实测）`thread_info` 的 flavor 表里没有任何缺页字段：`THREAD_BASIC_INFO` 只有 user_time、system_time、cpu_usage、policy、run_state、flags、suspend_count、sleep_time（`osfmk/mach/thread_info.h:89-101`）；`THREAD_IDENTIFIER_INFO` 是 thread_id、thread_handle、dispatch_qaddr（108-114）；`THREAD_EXTENDED_INFO` 多出优先级和线程名（149-163）；`THREAD_DEBUG_INFO_INTERNAL` 只有 `page_creation_count`（169-182）；`THREAD_SCHED_TIMESHARE/RR/FIFO_INFO` 是调度参数（225-227）。

（实测）`THREAD_DEBUG_INFO_INTERNAL` 只在 `DEVELOPMENT || DEBUG` 下返回，内容是 `thread->t_page_creation_count`（`osfmk/kern/thread.c:2202-2219`）。这个变量是页创建节流的计数（`osfmk/vm/vm_fault.c:864` 加一，840、861 在节流时重置或清零），不是缺页计数。

（实测）`struct thread` 里没有缺页或 pagein 字段（`osfmk/kern/thread.h`，整份头文件里只有 851-856 的节流字段和 913-930 的微栈采样元数据）。

（实测）`task_info(TASK_VM_INFO)` 的字段表（`osfmk/mach/task_info.h:363-429`）里没有 faults、pageins 或任何缺页字段。带这两个计数的只有 `TASK_EVENTS_INFO`（同文件 197-208），它按任务统计（`osfmk/kern/task.c:5727-5728`）。

（实测）stackshot 里名字像线程计数的 `tds_faults`、`tds_pageins` 也是任务计数：`osfmk/kern/kern_stackshot.c:4259-4260` 直接从 `task->faults` 和 `task->pageins` 读出，填进任务快照。

（实测）补丁里的 `cpu` 来自 `THREAD_BASIC_INFO`（`fd6-draw-seg-slow.patch` 的 `fd_draw_thread_cpu_us`），这是真正的按线程量；`flt` 不是。

替代计量有五条，按代价从低到高：

1. 用 `task_info(TASK_EVENTS_INFO)` 取 `faults` 与 `pageins` 两个增量，至少能把 minor 与 major 分开，口径仍是进程级。
2. 收窄窗口：取一段没有 draw 的空转期做对照，用窗口增量减去背景增量，得到这段时间里 draw 带来的那一部分。
3. 用按线程 CPU 时间做上界：本线程若处理了 N 次缺页，`cpu` 增量至少要覆盖 N 次异常入口加 pmap 工作。`cpu` 远低于这个下界时，缺页不在本线程。
4. 改内核：在 `vm_fault_internal()` 里给 `current_thread()` 加计数，再用新的 `thread_info` flavor 或 sysctl 读出。本项目自己构建内核，这条路可行，判据不要依赖它。
5. 微栈采样：`thread->t_vm_fault_info` 已经在为 VM 缺页采样记录地址、类型和来源（`osfmk/kern/thread.h:913-930`），代价是采样而非计数，需要 kperf／telemetry 工具链。

### 1.3 回归能否复现

答案：正相关复现，斜率、截距和分组都不支持「缺页造成长尾」的因果读法。

（实测，复算）24 条 `state` 读数上做 wall 对 flt 的最小二乘：wall = 85522.584 + 1695.587 × flt（µs），R² = 0.6319，n = 24；Pearson r = 0.7949，Spearman ρ = 0.8510。

（实测）按 flt 分组不单调。flt=34 的 63869 µs 低过 flt=19 的 59025 µs 以外的多数读数；flt=47 的 120972 µs 低过 flt=26 的 136164 µs；flt=398 的 543327 µs 低过 flt=196 的 824045 µs。

（实测）CPU 时间与墙钟无关：Pearson r(wall, cpu) = -0.0321，wall 对 cpu 单变量的 R² = 0.0010，r(flt, cpu) = 0.0627。把 cpu 放进二元回归，R² 从 0.6319 升到 0.6386，flt 的系数仍是 1706.602。

（实测）最小二乘受单个点影响大：去掉 flt=196 那一条，斜率 1330.433、R² 0.7339；去掉 flt=398 那一条，斜率 3035.780、R² 0.7869；留一法斜率范围 1330.433～3035.780。

（推断）斜率 1695.6 µs/次对一次 minor fault 太高。824045 那行的 `cpu` 是 128 µs，若 196 次缺页都由本线程处理，每次可分摊的 CPU 只有 0.65 µs。这组数与「本线程处理了这 196 次缺页」很难同时成立；缺页计数更可能来自别的线程或别的映射。

（推断）flt 与 wall 同向变化有一个更简单的共因：两者都随窗口内的工作量增大。窗口里做的绘制和分配越多，墙钟越长，进程里所有线程的缺页也越多；这条共因能解释正相关，也能解释为什么每缺页的隐含成本在 1365.1～6083.2 µs 之间大幅摆动。

### 1.4 判据怎么改写

原来的「flt 接近 0」不可判定：flt 是进程级计数，含所有线程和所有映射，预落页再有效也压不到 0。替代判据改成五条只依赖可取量的判据：预落页的开关对照、预落页行的单页成本、同轮非慢 draw 的基线、首次映射本身的耗时、flt 的排除用法。每条在 §3 给出通过条件与它排除的假设。

## 2. 数据表与计算过程

### 2.1 这一轮的身份

下表左列取自 `kernel-12377-attr26-diag3x-statefault/manifest.json`，是这一轮的实测身份：

| 项 | 值 |
| --- | --- |
| 内核 sha256 | `f055cc0a928e6b3a69f1043a419105362a71ea46ac1789e05387dea1db54c2c3`（20,226,616 字节） |
| 系统镜像 sha256 | `d11083be02820507f5639e0a29c6f35256a48d1d4f3cf4cd265eb4b8e346efe4`（4,925,816,832 字节） |
| payload sha256 | `3d7c8f4b2fc184b24c250c1def77a331eb578a5f3b88fe32779062ad5295f16b`（25,478,216 字节） |
| AIR sha256 | `04f25e4cbd320fbd53fa24151250ca43c90daf07660877688cd773e98ae0cf3d` |
| 驱动 sha256 | `868677669a794310ce1159ac37721eca9e5f726221a714e4f9ea3bd6afd71d44` |

（实测）`hackios-xnu-kernel/out/handoff-12377-attr26-diag3x-statefault.bin` 重算的 sha256 是 `3d7c8f4b2fc184b24c250c1def77a331eb578a5f3b88fe32779062ad5295f16b`，与 manifest 一致；manifest 里 `pack/expected_air_sha256` 与 `pack/air_sha256` 相同，AIR 身份校验通过。

（实测）`docs/analysis/2026-10-29-slow-draw-reading-criteria.md` §1 登记的另一组身份是 AIR `57fdb85c38bcf6892de3394ffa184963d881a99a091dae828c85dba5cb22e8eb`（14,051,376 字节）与驱动 `529d19bf36271609afc020e20bdc080b36b9a28af62c49ec9c9323dd0a11f40e`。这两个文件在 `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/` 下按哈希核对一致，该 AIR 里同时含 `fd bo prefault slow` 与 `fd draw state segs` 两个格式串。

这两组身份不同。§1.3 所用的 24 条读数属于 AIR `04f25e4c` 那一轮，不是判据文档登记的预落页那一轮；预落页那一轮还没有跑。

### 2.2 日志快照与去重

8 份文件是同一控制台流的累积拷贝，`fd draw seg slow` 行去重后共 24 条：

| 文件 | 本轮 `fd draw seg slow` 条数 | 与其他文件的关系 |
| --- | --- | --- |
| `s001.log` | 2 | 与 `s002` 相同 |
| `s002.log` | 2 | 与 `s001` 相同 |
| `s003.log` | 11 | 含 `s001` 全部 |
| `s004.log` | 11 | 与 `s003` 相同 |
| `s005.log` | 24 | 含 `s003` 全部 |
| `s006.log` | 24 | 与 `s005` 相同 |
| `s007.log` | 24 | 与 `s005` 相同 |
| `hung-held.log` | 24 | 与 `s005` 相同 |

（实测）24 条全部是 `state` 段；`emit`、`streamout`、`allclean` 三个分段一条都没有，说明这三段在整场 8000 次以上的 draw 里没有一次超过 50,000 µs 的打印阈值。

（实测）同一批文件里 `fd draw state segs` 0 条、`fd bo prefault slow` 0 条、`redwood: stall` 0 条。`fd draw calls` 与 `fd draw vbos calls` 两个计数都打到 8000，说明探针本身在跑。

（实测）`reboot.json` 记录这一轮以 frozen 结束：`elapsed_seconds` 70.0591356670484，`snapshot` `s007.log`，`last_frame_id` 913，`no_new_frame_seconds` 19.98，`max_frame_gap_seconds` 16.901。

（推断）`fd draw state segs` 为 0 指向这一轮的 AIR 里没有这个探针。`fd6-state-segs.patch` 的 `say_state()` 与 `fd_draw_seg_say("state", ...)` 在同一点前后调用，阈值同为 50,000 µs；`say_state()` 的 `total` 只算到最后一个 `mark()`，理论上可以因未埋点的缺口很大而不打印，但 24 条 state 行无一配对，这个解释站不住。2.1 的 AIR 哈希差异与这条一致。

### 2.3 24 条读数

全部照抄原始行，单位 µs，按 `flt` 升序排列。`wall/flt` 是派生量，按 3 位小数列出。

| flt | wall | cpu | wall/flt |
| --- | --- | --- | --- |
| 14 | 72151 | 51 | 5153.643 |
| 16 | 72689 | 128 | 4543.063 |
| 17 | 50142 | 95 | 2949.529 |
| 17 | 103414 | 53 | 6083.176 |
| 19 | 59025 | 59 | 3106.579 |
| 20 | 81545 | 79 | 4077.250 |
| 20 | 89930 | 94 | 4496.500 |
| 23 | 98635 | 38 | 4288.478 |
| 23 | 116495 | 118 | 5065.000 |
| 25 | 132157 | 61 | 5286.280 |
| 26 | 112068 | 55 | 4310.308 |
| 26 | 127581 | 61 | 4906.962 |
| 26 | 136164 | 146 | 5237.077 |
| 33 | 136914 | 143 | 4148.909 |
| 33 | 163669 | 42 | 4959.667 |
| 34 | 63869 | 553 | 1878.500 |
| 35 | 151057 | 75 | 4315.914 |
| 46 | 172767 | 109 | 3755.804 |
| 47 | 120972 | 80 | 2573.872 |
| 78 | 458553 | 50 | 5878.885 |
| 119 | 274281 | 98 | 2304.882 |
| 184 | 392083 | 116 | 2130.886 |
| 196 | 824045 | 128 | 4204.311 |
| 398 | 543327 | 125 | 1365.143 |

### 2.4 回归计算

最小二乘按 wall = a + b × flt 拟合，`b = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)²`，`a = ȳ − b·x̄`，`R² = 1 − SS_res / SS_tot`。n = 24。

| 量 | 值 |
| --- | --- |
| 斜率 b | 1695.587 µs / 次 |
| 截距 a | 85522.584 µs |
| R² | 0.6319 |
| Pearson r(wall, flt) | 0.7949 |
| Spearman ρ(wall, flt) | 0.8510 |
| Pearson r(wall, cpu) | -0.0321 |
| R²(wall ~ cpu) | 0.0010 |
| Pearson r(flt, cpu) | 0.0627 |
| 二元回归 wall ~ 101040.2 + 1706.602 × flt − 152.002 × cpu | R² 0.6386 |
| 留一法斜率范围 | 1330.433 ～ 3035.780 |
| 去掉 flt=196 后的拟合 | a 88168.0，b 1330.433，R² 0.7339 |
| 去掉 flt=398 后的拟合 | 斜率 3035.780，R² 0.7869 |

（实测）残差最大的几行：824045 行的预测值 417857.7、残差 +406187.3；458553 行预测 217778.4、残差 +240774.6；543327 行预测 760366.3、残差 −217039.3；63869 行预测 143172.5、残差 −79303.5。24 行里有 6 行的墙钟低于截距 85522.584。

（实测）按 flt 分组的组均值：14→72151，16→72689，17→76778，19→59025，20→85737.5，23→107565，25→132157，26→125271，33→150291.5，34→63869，35→151057，46→172767，47→120972，78→458553，119→274281，184→392083，196→824045，398→543327。按 flt 升序看这串均值，中间多次下降，组均值不单调。

（实测）每缺页的隐含成本（wall/flt）最低 1365.143 µs（flt=398），最高 6083.176 µs（flt=17），中位数 4288.478～4310.308 µs（24 个值的中位区间）。

### 2.5 对回归的解释

（推断）斜率的物理含义要求每一次缺页平均对应 1.7 ms 的墙钟，而且截距要求 flt=0 时 state 段仍有 85.5 ms。两次读数在同一个函数里前后相邻，中间只执行 `draw_emit` 之前的状态生成，85.5 ms 的常数项说明这段墙钟里有一块与缺页无关的固定开销，回归把它压进了截距。

（推断）如果缺页是主因，flt 相同的两行墙钟应当接近。实测里 flt=17 的两行是 50142 与 103414，相差一倍；flt=26 的三行是 112068、127581、136164，跨度 24%。同一缺页数下墙钟的离散来自别处。

（推断）如果本线程因缺页睡眠，`cpu` 会包含每次缺页的内核工作；实测 `cpu` 与 wall 的相关系数是 -0.0321，接近零且符号为负。这条数据与「绘制线程自己在处理缺页」不相容，与「进程里别的线程在缺页」相容。

## 3. 下一轮判据建议

下一轮要回答的问题是：state 段的毫秒级长尾是否来自首次触碰 BO 页的缺页工作。五条判据都只用下一轮能取到的量，任何一条的通过条件都在数据到手前登记。

### 3.1 判据一：预落页开关的对照

量：同一次启动内用运行时开关交替开关预落页，比较 `fd draw seg slow: state` 的条数分布，以及 `fd draw state segs` 的分段分布。

通过条件：关闭预落页时至少出现 1 条 state 墙钟超过 100,000 µs 的 draw，打开后同等工作量下为 0；打开期间 `fd bo prefault` 覆盖的 BO 页数不少于这些 draw 涉及的 BO 页数。

排除什么：打开预落页后 state 长尾仍在，且分段显示时间落在 `cs_begin` 或 `emit_3d_state`，首触缺页不在成因链上。

阈值来源：本轮 24 条里有 16 条超过 100,000 µs（实测计数），这个界能把本轮的长尾与 50,000～100,000 µs 的一段分开。

需要的埋点：预落页开关。跨启动比较会混入场景、帧率和其它进程的差异，同一次启动内的开关对照才是单变量。

### 3.2 判据二：预落页行的单页成本

量：每条 `fd bo prefault slow: %p %u bytes %llu us` 给出一个 BO 的字节数与微秒数；页数 = bytes ÷ 页大小，单页成本 = us × 页大小 ÷ bytes。页大小取补丁里 `sysconf(_SC_PAGESIZE)` 的返回值，下一版把页数或页大小打进这一行。

通过条件：该 draw 涉及的 BO 的「页数 × 单页成本」之和达到 state 墙钟的同一量级（不低于它的十分之一），缺页在数量上仍可能解释长尾。

排除什么：这个和低于墙钟的十分之一时，首触页的工作量不足以构成这段墙钟，缺页解释不了。举例：若单页成本在 50 µs、涉及 400 页，合计 20,000 µs，对 824,045 µs 的墙钟只占 2.4%。

依据：本轮 24 条读数隐含的每次缺页成本在 1365.143～6083.176 µs；真实单页成本若落在几十微秒，flt 与墙钟的相关只能来自共因。

需要的埋点：现在只在单 BO 耗时 ≥ 5000 µs 时打印，静默既可能是「很快」也可能是「没跑到」。下一版对每个首次映射输出一行，或每轮输出一行汇总（BO 数、页数、总 us、最大单页成本）。

### 3.3 判据三：同轮非慢 draw 的基线

量：所有 draw 的 state 墙钟分布。现有探针只在超过 50,000 µs 时打印，没有基线。建议把每 1000 次 draw 的那行计数扩展成一段统计：这 1000 次的最大值、中位数、超过 50,000 µs 的条数。

通过条件：慢 draw 占全部 draw 的比例低于 1%，且慢 draw 的最小墙钟达到基线 p99 的 10 倍以上。

排除什么：全体 draw 都慢时，这条指向常态路径的性能问题，不再有「离群长尾」可解释；分布连续、没有断档时，「慢 draw」是阈值造出来的一组，不是一个独立机制。

依据：本轮 `fd draw calls` 计数到 8000，24 条慢 draw，占比不超过 0.3%（实测）。1% 与 10 倍是本次登记的判据阈值，数据到手前写死。

### 3.4 判据四：首次映射本身的耗时

量：`IOConnectMapMemory64` 的墙钟，按 BO 计量，在 `redwood_drm_map` 调用两侧打点。

（推断）预落页在映射返回之后才跑（`fd-bo-prefault.patch` 的 `__fd_bo_map` 先建立 `bo->map`，再调 `fd_bo_prefault`），映射本身的耗时不在预落页行里。这条路径要建命名条目、抽取整段 vm_map 条目、把条目映射进用户任务（`osfmk/vm/vm_memory_entry.c:783-953`、`iokit/Kernel/IOMemoryDescriptor.cpp:6114-6154`），耗时随 BO 大小增加，落在 state 段里同样可能。

通过条件：慢 draw 存在时没有任何一条 BO 映射超过 50,000 µs（与其它探针同一阈值）。

排除什么：映射本身超过阈值时，先查 `IOConnectMapMemory64` 这条路，预落页和缺页都不是目标。

### 3.5 判据五：flt 的使用边界

量：`task_info(TASK_EVENTS_INFO)` 的 `faults` 与 `pageins` 两个增量，或 getrusage 里 `ru_minflt`、`ru_majflt` 分开记录。补丁下一版应把两个值分开打印，不再相加。

通过条件（只作排除）：窗口内 `faults` 增量为 0，而 state 墙钟仍超过 100,000 µs，缺页被排除。

不成立的用法：`faults` 增量大不能证明本线程缺页；进程里任何线程、任何映射的缺页都进同一个计数。要把 flt 用于确认，必须先按线程隔离（停住其它线程，或在 `vm_fault_internal` 里按线程计数），并证明该线程的 `cpu` 增量足以覆盖这些缺页处理。

### 3.6 对事前登记文档的处理

原 `2026-10-29-slow-draw-reading-criteria.md` §3.1 的「flt 接近 0 且长尾消失」这一条删除，替换为判据一与判据二。进程级计数在正常运行下不会接近 0，这条条件无法判定真假。

原 §3.2 的分段判据在这一轮无法评估：本轮 AIR 的哈希与登记值不同，24 条 state 行也没有配对的 segs 行，§2.2 的判断是这个探针不在本轮构建里。下一轮用登记过的那份 AIR 才有效。

原 §3.4 的采样有效性同样无法评估：本轮 0 条 `redwood: stall` 行，驱动哈希与登记值不同。

这三条不影响 §1 的结论，它们只说明旧判据里的三项观察都还没有在对应的构建上取到。