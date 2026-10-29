# fixguard6 插桩与预登记读数（2026-10-29）

## 1. 这一轮要回答什么

fixguard5 的三项判据全不通过，bad access 仍是同一形态（`pc …9c0`、`x2 0xc0`、src 含字符串字节）。守卫补丁第一次在 26 用户态下真实执行，结果没有消掉这条路径，于是要么拦截生效但不够，要么拦截根本没被走到。本轮插桩只为区分这两种读法，并顺带抓一次故障行拷贝的实参。

判据在数据到手前登记，见第 4 节。插桩不动守卫条件与返回值。

## 2. 插桩落点与输出形态

两处改动，一个补丁文件 `hackios-xnu-kernel/tools/mesa/fixguard6-shadow-counters.patch`，`patch -p1` 应用在 `out/ios26-resume/mesa-arm64e/mesa-26.2.5/`。

| 文件 | 改动 | 输出 |
| --- | --- | --- |
| `src/gallium/drivers/freedreno/freedreno_resource.c` | `fd_try_shadow_resource` 入口加三个计数；守卫拒绝处加一次计数并在首次拒绝打一行；`SWAP(rsc->bo, …)` 之后加交换计数并在首次交换打一行；`atexit` 注册一行收尾 | `rwa shadow: <why> calls=… is_shared=… refused=… swapped=…` |
| `src/util/format/u_format.c` | `util_copy_rect` 在算出 `width` 之后、行循环之前，仅当 `width == 0xc0`（192 字节，fixguard5 的 `x2`）打前 8 行 | `rwa row: <n> src=… dst=… len=… shadow calls=… is_shared=… refused=… swapped=…` |

四个计数是全局量（`fd_shadow_calls`、`fd_shadow_shared`、`fd_shadow_refused`、`fd_shadow_swapped`），只有这样才能在 `u_format.c` 的打印里带出来。守卫条件仍然写成 `if (rsc->b.is_shared)` 且只出现一次，`grep -c 'if (rsc->b.is_shared)'` 的结果是 1。

## 3. 打印量上界

单进程上界 11 行：收尾 1 行、首次拒绝 1 行、首次交换 1 行、行拷贝 8 行。fixguard5 里 backboardd 有 14 个世代（`11/11` ×14），按每世代一个新进程算，全轮上界 154 行。

日志环容量约 7,347 行，fixguard5 一轮产出 12,444 行唯一内容并回绕过一次。154 行约占环的 2%，不会把环冲掉。行拷贝的 8 行上限按进程计（`static` 计数器）。

## 4. 预登记读数与判定规则

先是「守卫有没有被执行到」，三种读法互斥：

| 读数 | 读法 | 下一步 |
| --- | --- | --- |
| `calls = 0`（连收尾行都没有） | `fd_try_shadow_resource` 在该进程里没被调用 | 守卫与这条 UAF 无关，转查 AIR 侧的 buffer 生命周期 |
| `calls > 0`、`is_shared = 0` | 进入过，但没有一个 `is_shared` 资源进入 | 导入资源没走这条路径，守卫对这条 UAF 无效 |
| `is_shared > 0`、`refused = is_shared` | 每个 `is_shared` 都被拒 | 拦截生效；若 bad access 仍在，说明 UAF 不在 shadow 交换处 |

`refused` 小于 `is_shared` 只可能来自计数竞争，不改判据，按最接近的整数比。

再看「故障那次 memmove 的 src 是谁」：

- `rwa row:` 有行且 `len=192`：与 bad access 的 `x2=0xc0` 对应。看第一行出现时的 `swapped`。`swapped = 0` 且 `refused > 0` 表示这次行拷贝发生在任何交换之前，故障与交换无关；`swapped > 0` 表示交换已经在同一进程里发生过，但本轮没有打出交换的资源与 bo，判断要留到下一轮。
- `rwa row:` 一行都没有而 bad access 仍在：故障那次的行宽不是 192（fixguard5 的 355 与 38 两种），下一轮把门槛改成「前 8 次任意 width」。
- `rwa row:` 有行但同进程没有 bad access：打印的那 8 行不是故障行，只在 `src` 与 bad access 行的 `x1` 相同时才算命中。

比较纪律：计数只在同一段被环保留的窗口内比较，不能拿 fixguard5 的 103 当全程量。

## 5. 重建与静态核对

宿主侧重建走 `tools/k90auto/build-air.py`（复制 AIR 三个源文件、校验两侧源文件一致、`ninja` 单一目标、adhoc 签名、写记录）。库的合格性在打包时静态检查，不等跑完去日志里找。

| 核对项 | 结果 |
| --- | --- |
| 构建树 `grep -c 'if (rsc->b.is_shared)'` | 1 |
| 计数引用数（`freedreno_resource.c`／`u_format.c`） | 7／4 |
| 新库 | `out/ios26-resume/bbmetal-device/libredwoodair.dylib`，14,000,624 字节 |
| 新库 sha256 | `cbf1689cc025e583a44bed7e9bda29f56020f111ae711659a82c06066843af5a` |
| 与守卫版 `1be6ebf7…` 是否相同 | 不同 |
| `air-build-record.json` | 已更新，`holds` 11 项全 true，含 `rwa shadow:` 与 `rwa row:` |
| 库内格式串 | `rwa shadow: %s calls=%llu is_shared=%llu refused=%llu swapped=%llu`、`rwa row: %u src=%p dst=%p len=%u shadow calls=%llu …` |

## 6. 未做与风险

本轮没有打印交换时的资源与 bo 指针：`fd_try_shadow_resource` 的交换处只打一次 `first-swap` 汇总行。要判「故障那次行拷贝读的是不是交换走的 bo」，需要下一轮在交换处记录 `rsc`、旧 bo 与大小，并在 `util_copy_rect` 里比对 `src` 是否落在这些区间。

也没有处理进程在 SIGSEGV 上不执行 `atexit` 的情况：收尾行只在正常退出时出现，所以首次拒绝与首次交换各自单独打一行。若某世代进程崩得早，该世代的计数只剩这两行。

`u_format.c` 是 Mesa 通用代码，`width == 0xc0` 的条件对所有使用者生效（不止 AIR）。判定只看 8 行上限与 `len` 值，不再细分调用者。
## 7. fixguard6 读数与预登记表的缺口

读数：`rwa shadow:` 0 行、`rwa row:` 0 行、bad access 0 原始／0 唯一、帧 3,616（id 1..3,616 无断裂、最后交换 245.8 秒、`usable as a performance baseline`）、43 张截图全是 home screen、deaths 27 条全是 widget 扩展（`9/1001` ×16、`5/5` ×9）加 `launchd.ios` 与 `MSUEarlyBootTask` 各 1、`rwa draw:` 653 行。

第 4 节第一行的判据本轮落不下去，缺口在插桩的设计上：`calls` 与 `is_shared` 的分母只出现在 atexit 收尾行、首次拒绝行、首次交换行。backboardd 与 SpringBoard 本轮都没有退出，`atexit` 不触发；退出的是 widget 扩展，死在 `9/1001` 与 `5/5`，也不执行 `atexit`。所以零行不能读成 `calls = 0`。

可用的读法只剩一条，标推断：245 秒里有 3,616 帧、`rwa draw:` 653 行，期间一次 shadow 交换都没有打印。非导入资源的首次交换是常规路径，长时间健康运行里一次都没有，更像 `fd_try_shadow_resource` 在保留窗口内没被调用过。这一条不是实测，下一次插桩用首调行才能定。

`rwa row:` 0 行有一个确定含义：保留窗口内没有 192 字节的行拷贝，与 bad access 0 一致，但它不指向归因。

## 8. 与 fixguard5 的相反结果

唯一差异是 AIR 库（`1be6ebf7…` → `cbf1689c…`，image-diff 只差 `/lib/libredwoodair.dylib`），结果却从 42 张全黑、103 次 bad access、14 个 backboardd 世代翻成 home screen、0 次、一次没死。三个候选：

| 候选 | 支持点 | 反对点 |
| --- | --- | --- |
| 插桩改变了时序 | 库尺寸与代码布局都变了（14,000,400 → 14,000,624 字节） | 不打印时插桩只多四个计数、一次 `bool` 读取与一次 `atexit` 注册；本轮零打印行，说明这些路径里没有一条执行到打印 |
| 轮间方差 | 本轮帧数 3,616 对 79，工作负载明显不同；deaths 全在 widget 扩展且退出码与 GPU 无关 | 单轮无法给出发生率 |
| 守卫在 fixguard6 才生效 | 两轮都带守卫 | fixguard5 也带守卫，103 次照样发生 |

判别实验：同一载荷（不改库、不改包）再跑一次。第二次仍健康，说明 fixguard5 那条崩溃不是稳定性质，先做可复现性再谈守卫有效性；第二次复现 103 次，说明轮间方差占主导，单轮结果不能当判据。

## 9. 下一轮的最小改动

1. `fd_try_shadow_resource` 首次调用就打一行（`first-call calls=1 …`），补上分母；收尾行改成每 N 次调用打一次（N 取 1024），进程不退出也能读到计数。
2. `util_copy_rect` 的门槛从 `width == 0xc0` 改成「前 8 次任意 width」，仍带四个计数与 src／dst／len。
3. 守卫条件与返回值不变，AIR 侧其它改动不做。

这三条等 lead 通知再动，改动先挂工作区。

## 10. `tl: f` 的条数口径

`tl: f` 由 `RedwoodGPU.cpp:302` 的 `slowWait()` 打印，门槛是 `ns >= NSEC_PER_MSEC`：只打等待 1 毫秒及以上的行。它有两个调用点，`:696`（`cpu-prep`）与 `:712`（`fence`），所以一帧最多两行，等待不足 1 毫秒的一行都不打。

因此 fixguard6 的 2,083 行是「≥1 毫秒的等待数」，不是帧数（3,616 帧）。两数之差不是别的过滤条件。

代价核算随之分两种口径：只给现有行加 pid／tid，2,083 × 14 字节占环 2.8%；要让每帧都有一行 `tl: f`，得把打印移到门槛之外，那是新增 3,616 行、按每行 31 字节计占 10.6%。perf 的 4.9% 对应的是后一种（每帧一条），不是前一种。
