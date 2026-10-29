# 上滑解锁卡死专查：判据与读法（2026-10-29）

## 1. 判据（数据到手前登记）

- 复现：解锁后 20 秒内没有新帧。帧号取自 `tl: s <id>` 的 id 序列，解锁动作以 `tl: p` 的触点上滑为界。
- 不复现：20 秒内出现新帧，或整轮没有上滑解锁动作。后者按「未执行」记，不算不复现。
- 判据只覆盖「上滑解锁后 20 秒」这段窗口，不覆盖更早的桌面阶段与之后的重启。

## 2. 三个问题与各自的证据来源

| 问题 | 读法 | 来源 |
| --- | --- | --- |
| 解锁把画面推进到哪一步停住 | 末帧 id 与末帧对应的阶段标记（解锁动画、第一个应用图标、home screen 首帧） | `run/probe-*.log` 的 `tl:` 行与截图序列 |
| 停在哪个线程 | 卡死时刻的线程栈与运行态；`tl: td pid … threads …` 之后的转储段 | `run/probe-*.log`、`probe-report.json` |
| 停住前最后一个渲染动作 | 末帧之前最后一条 `rwa draw:` 与 `tl: v`（显示驱动拷贝）的配对情况 | `run/probe-*.log` |

`probe-report.json` 若只给汇总，三个问题里前两个要靠 `probe-*.log` 的原始行补；汇总与原始行不一致时以原始行为准，并把差异写进记录。

## 3. 与已有轮次的关系

现有五轮（round C／D／F、fixguard6／fixguard7）的日志里没有线程级等待点，`SpringBoard` 只出现在库插入与 `framewatch` 启动行上。所以「停在哪个线程」这一问在这份专查之前没有基线，本轮读出什么都是首个数据点。

## 4. 未做与边界

本轮不做根因判断，只定位停止点。线程栈若指向内核态等待（锁、`thread_block`），下一轮再取内核侧的等待对象；若指向用户态轮询，则回到渲染服务器与 AIR 侧。

## 5. 93 行 bad access 的归类（2026-10-29 实测）

| 量 | 取值 | 行数 | 说明 |
| --- | --- | --- | --- |
| `x2 = 0x26`（38 字节） | `pc 0x2aff81ad4` | 53 | 该宽度全部配这个 pc，无一例外 |
| `x2 = 0xc0`（192 字节） | `pc 0x2aff819c0` | 40 | 同上 |
| `lr` | 全部满足 `mod 0x4000 == 0x180` | 93 | 同一调用点，差异只在进程的 ASLR 基址 |
| `region` | 全部 `0x293000000-0x2b8800000`，大小 `0x2580000` | 93 | pc 所在的映射，无 vnode |

减 slide 后（slide `0xac20000`，取自 `tl: td` 行）：`0x2aff819c0` → `0x2a53619c0`，`0x2aff81ad4` → `0x2a5361ad4`，两者都落在缓存里 `/usr/lib/system/libsystem_platform.dylib`（装载地址 `0x2a5361000`、`__TEXT` 长度 `0x8434`）内，偏移分别是 `0x9c0` 与 `0xad4`。

这张表支撑两条读法：

- **驱动侧只有一条路径**：93 行的返回地址关系只有一种，不存在第二个调用点。
- **memmove 内部按长度分岔**：两个 pc 只随 `x2` 变化，与调用者无关，所以 192 与 38 不是两次不同来源的故障，是同一处行拷贝的两种行宽。

以后凡这两种宽度同时出现，按此表直接归类，不必重新推导。

38 字节是 `ceil(width / blockwidth) * blocksize` 的一行，与 roundb 在 round E／F 记的 355、38 同类。本轮 38 字节占 53 行、192 占 40 行，与 E／F 的分布相反。

## 6. 三轮矩阵的判据

「崩」的判据必须同时满足：出现 `backboardd bad access`；pc 落在 `0x…9c0` 或 `0x…1ad4`；该行 lr 满足 `mod 0x4000 == 0x180`；`x2` 属于 `{0xc0, 0x26}`；backboardd 至少死一次。只出现别的 bad access 形态不算。

| 第一轮（无守卫 `d7b9ced5`） | 第二轮（守卫 `1be6ebf7`） | 结论 |
| --- | --- | --- |
| 崩 | 崩 | 守卫对这条路径无效，插桩也不是原因：有守卫、没插桩同样崩 |
| 崩 | 不崩 | 守卫在这条路径上有效，插桩改变了时序（第三轮带插桩崩、第二轮不带插桩不崩），需要用第三份库复查一次才能落结论 |
| 不崩 | 不崩 | 解锁作业不足以触发；先核第一轮是否真的没崩、`d7b9ced5` 那份库是否与 round F 一致 |
| 不崩 | 崩 | 结果与库的对应关系不稳定，按轮间方差处理，不加结论 |

## 7. 解锁不是触发条件

最后一条 `done` 在 469.779 秒，第一次按下在 486.288 秒；`bad access` 从 s003 快照起逐份增加（2→10），`died on signal` 从 2 涨到 142，都发生在解锁之前。解锁之后零新帧。

三轮矩阵仍然有效：它变的是作业文件与库，不涉及解锁动作，差别在作业执行前的静置与切换过程。

## 8. 第四轮

排在矩阵之前。同一作业文件、同一个库 `cbf1689c…`、不注入任何输入，判据同第 6 节。

- 仍崩：触发在静置期或应用切换，与输入无关，后续按静置时长做变量。
- 不崩：输入参与触发，转触摸驱动到合成器那条路径。

待补一条：device 正在比对 `rc.jobs.unlockprobe` 与 `rc.jobs.freezef` 的差异与两轮打包环境变量。若解锁之前存在实质差异（daemon 丢弃集合、启动顺序一类），第 6 节判据要加一条，让第四轮能区分「作业内容」与「有没有输入」两个变量。

## 9. 起轮方式这个变量

同一个库 `cbf1689c…`、同一系统盘 `d11083be…`、同一驱动、同一 cmdline（只差 `epoch`），fixguard6 与 fixguard7 健康，unlockprobe 从 30 秒起就崩。三者之间已知的差别不在载荷里，而在起轮前有没有完整复位。

| 轮次 | 起轮方式 | 结果 | 库 sha256 |
| --- | --- | --- | --- |
| fixguard6 | 安卓 → LK → 切 A 槽 → `reboot` | 健康，无 bad access | `cbf1689c…` |
| fixguard7 | 同上 | 健康，无 bad access | `cbf1689c…` |
| unlockprobe | 上一轮收尾的 loader 直接起（上一轮只做 PSCI 复位） | 崩，93 行 bad access | `cbf1689c…` |
| fixguard5 | 安卓 → LK → 切 A 槽 → `reboot`（完整路径） | 103 行 bad access | `1be6ebf7…` |
| round C／D／F | 待核 | C／D 崩、F 见对应轮次 | 各自 |

unlockprobe 的收尾日志留有 `psci: cpu 1 ends the system: the return to the boot loader is the boot processor's to make` 与 `adreno8: GPU probe requires host cold reset before reusing kernel memory` 两行，指向同一条线索：GPU 与显示侧在未冷复位的内核内存上继续运行。

fixguard5 走的是完整路径，证据是 device 会话记录里的时间戳链条：00:24:18 在安卓上 `adb shell 'getprop sys.boot_completed; getprop ro.boot.slot_suffix'`（`sys.boot_completed` 有值）后 `adb reboot bootloader`；00:24:36 `fastboot set_active a` 并在同一条命令里核 `current-slot`；00:25:00 `nohup python3 tools/k90auto/run-auto.py <fixguard5 目录> 240`。

四轮的 `reboot.json` 都是 `mode loader`、`reset true`、`off_seen true`，只描述进 loader 这一步，不能据此分路径；unlockprobe 那份多一个 `failed: {state: frozen, elapsed_seconds: 140.5}`，属于收尾。`hung-held-serial.log` 四轮都从 `== XNULOADER run (usb) ==` 开始，没有冷复位字段；`adreno8: … cold reset …` 每轮都有，不能当判别依据。

由此，冷复位只能解释 unlockprobe 那一例。fixguard5（`1be6ebf7…`、完整路径）与 fixguard6／7（`cbf1689c…`、完整路径）的矛盾仍然存在。

## 10. 排期与判据

矩阵要跑，另加一轮排在前面。

| 顺序 | 作业 | 库 | 起轮路径 | 结果的作用 |
| --- | --- | --- | --- | --- |
| 1 | `freezef` | `1be6ebf7…`（守卫，无插桩） | 完整路径 | 复现 fixguard5：崩则守卫版在这套配置下确实不稳；不崩则 fixguard5 属轮间方差 |
| 2 | `unlockprobe` | `9dbb857c…`（撤掉两份补丁） | 完整路径 | 矩阵第一列 |
| 3 | `unlockprobe` | `1be6ebf7…` | 完整路径 | 矩阵第二列，判「守卫有没有挡住这条」 |
| 4 | `unlockprobe` | `cbf1689c…` | 冷路径（loader 直接起） | 价值下降，只留「冷复位 + 无输入」这一格 |

「崩」的判据同第 6 节五条，不因排期变化放宽。

第 2 轮的库定在 `9dbb857c…`、14,000,384 字节：今晚把两份补丁都退出 mesa 树后由 `build-air.py` 重建。它与 `1be6ebf7…`（只加守卫补丁）出自同一棵构建树，二者只差守卫那一处插入，正是矩阵需要的单变量。

取舍要写明：`9dbb857c…` 不享受「与 round F 装车那份逐字节相同」这一性质。round F 装的是 `d7b9ced5…`、13,983,936 字节，带逐帧计时插桩，不能当无守卫基线；本轮用重建件换来单变量对照，代价是 round F 的帧数与帧间隔不能直接与本轮比。

第 2 轮开跑前由 device 报一次 `air-build-record.json` 与字节数，我按 sha256 与 14,000,384 字节复核后再起轮。第 1 轮（`freezef` 加 `1be6ebf7…`，复现 fixguard5）不受影响，先跑。
