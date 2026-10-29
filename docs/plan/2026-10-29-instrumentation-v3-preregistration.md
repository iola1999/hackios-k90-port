# 插桩第三版预登记：三条打印（2026-10-29）

## 1. 这次要回答什么

三问各自独立，**分两轮跑**。三条改动都只加打印与计时，不改任何行为分支：守卫条件不动，`util_copy_rect` 的拷贝逻辑不动，`redwoodmetal.m` 的 `-dealloc` 顺序不动。

落点决定了不能同包：`tl: s` 与 `tl: v` 打在 `xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp`（`:838`、`:1017`），`tl: f` 打在 `RedwoodGPU.cpp:302` 的 `slowWait()`，两者都在内核里；`rwa dealloc:` 打在驱动库 `tools/userland-driver/redwoodmetal.m`。所以：

- **第一轮（先跑）**：只换驱动库（`9d66dd36…` → `d296b5a4…`、241,520 字节），内核 `cf1502f5…` 与 AIR `cbf1689c…`、作业 `freezef` 都不变，读数落在 fixguard6／7 那套健康配置上。回答问二。
- **第二轮**：只换内核（`tl: s` 与 `tl: f` 各加 pid／tid 两列，行数不变），AIR 与驱动库都不变。回答问题三。

AIR 库两轮都不重建：三条改动没有一处落在 AIR 源码里，`cbf1689c…` 保持不变，`rwa row:` 那条打印已经在库里。

| 问 | 打印 | 判据 |
| --- | --- | --- |
| 问一已结案 | 不加打印 | 内核边界不是量化点，量化在客户端节奏一侧 |
| deallocator 与 destroy 的先后，destroy 之后是否还有拷贝引用该 buffer | `-dealloc` 的三处 `rwa dealloc:` 行 | 有 `bad access` 的 `x0`／`x1` 落在已记录的被销毁 buffer 的 `[_contents, _contents + _length)` 内 |
| `tl: f` 的 pid／tid | 现有行加两列，门槛不动 | 行数不变、每行多 14 字节；按 pid 归并后能分进程 |

## 2. 落点与格式

| 落点 | 内容 | 输出形态 |
| --- | --- | --- |
| `redwoodmetal.m` 的 `-dealloc` 入口 | pid、`self`、`_mesa`、`_callerBytes`、`_length`、序号 | `rwa dealloc: begin <n> pid <pid> self <p> mesa <p> bytes <p> len <len>` |
| 同一函数里 deallocator 块之后、`mesa.buffer_destroy` 之前与之后各一行 | 序号与两个指针 | `rwa dealloc: freed <n> …`、`rwa dealloc: destroyed <n> …` |
| `tl: f` 现有打印 | 加 `pid` 与 `tid` 两列 | `tl: f <pid> <tid> <kind> <US> at <US>` |

`-dealloc` 只加打印，不动 `if (_callerDeallocator != NULL)` 与 `if (_mesa != NULL)` 两个分支的顺序。

## 3. 条数上界与环占用

环基线按 perf 的读数：13,531 行、1,055,418 字节、覆盖 92 秒。

| 打印 | 条数 | 字节 | 占环 |
| --- | --- | --- | --- |
| `tl: f` 加两列 | 行数不变（2,083，只有 ≥1 毫秒的等待才打） | 2,083 × 14 = 29,162 | 2.8% |
| `rwa dealloc:` | 每进程前 32 条，之后每 256 次一条 | 约 52 条 × 90 = 4,680 | 0.4% |

合计约 3.2%，覆盖 92 → 89 秒，仍是 20 秒快照间隔的 4 倍还多。

排插桩之前先问一遍「现有日志能不能算」。今晚已经两次靠现有日志省下一轮设备时间：fixguard7 的末帧减半与这一条量化点。

## 4. 预登记读数

**问一，整拍量化（已结案，用现有日志算出）**

`tl: v` 已带 `done`（GPU 完成该帧），`tl: s` 已带 `at`（提交时刻）。fixguard6 的 3,606 对帧上算 `s(id) − done(id−1)`：中位数 7,640 微秒，p10～p90 是 7,221～8,240，落在单拍（16.67 毫秒）±15% 内的只有 0.1%，落在 2～5 拍内的 0 条。间隔约半个拍子、分布宽约 1 毫秒，不在整拍格点上，所以内核边界不是量化点；若存在量化，位置在客户端节奏那一侧。

**问二，destroy 之后是否还有拷贝引用**

| 读数 | 结论 |
| --- | --- |
| 某条 `bad access` 的 `x0` 或 `x1` 落在同一进程已记录的 `[contents, contents+len)` 内 | 拷贝在 `buffer_destroy` 之后仍引用该 buffer，方向二成立，可进改动 |
| 全部 `bad access` 都不落在任何已销毁区间 | 方向二不足以解释这条故障，降级 |
| `rwa dealloc:` 的 `begin` 与 `destroyed` 之间出现 `freed`（顺序符合现有代码） | 只证明顺序，不证明引用；需与上面一条合看 |

**问三，`tl: f` 的 pid／tid**

| 读数 | 结论 |
| --- | --- |
| 行数仍是 2,083 量级、每行多两列 | 门槛未动，插桩密度表的 2.8% 生效 |
| 行数涨到 3,616 量级 | 说明门槛被意外绕过，先停下核对再打包下一轮 |

## 5. 静态核对（打包前）

- 构建树 `grep -c 'if (rsc->b.is_shared)'` 仍为 1。
- 两处新格式串在库里 `strings` 可见：`rwa dealloc: begin`、`tl: f %d %llu `；内核里 `tl: s %u %d %llu ` 与 `tl: f %d %llu `。
- 新库 sha256 与 `cbf1689c…` 不同，`air-build-record.json` 的 `holds` 追加这三条。
- image-diff 对上一轮只允许 `/lib/libredwoodair.dylib` 与 `/lib/libredwoodmetal.dylib` 两处差异（后者因为 `redwoodmetal.m` 加了打印）。

## 6. 未做与风险

`redwoodmetal.m` 的改法是加打印，deallocator 与 `buffer_destroy` 的顺序保持原样，所以本轮**不能**回答「顺序该不该改」；它只回答「现在这个顺序下，destroy 之后还有没有拷贝引用」。

`tl: s` 与 `tl: f` 都加字段后，`tools/frames.py` 与 `tools/latency.py` 里按位置读这两行的正则要同步改，否则会把 pid 当 kind。
