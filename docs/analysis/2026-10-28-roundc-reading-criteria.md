# round C 判读口径（2026-10-28）

round C 只换内核，新增两类打印。本文给出这两类行怎么读、崩溃报告收集读什么、停机段怎么在不依赖 `framewatch` 的前提下判定、以及用户 2026-10-28 追加的性能验收口径落到哪几个可执行的数上。格式串原文已由 display 在 [内核改动记录](../progress/2026-10-28-kernel-badaccess-region.md) §1 给出并已在最终镜像里 `strings` 到，本文按那份原文写死匹配串。round D 的驱动提交入口三计数一并写在第 10 节，标明它的前置条件。

## 1. 本轮身份与口径边界

| 项 | 值 |
|---|---|
| 内核 | `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492`、20,210,232 字节、源码提交 `5c9f563`（`sleh: bad access 再打 lr 与 x0/x1/x2`），取代 task-1 那版 `81f544688809a2e8`、源码提交 `690e36a` |
| 内核 dSYM | 本轮 `BUILD_DSYM=0`，dSYM 目录停在旧内容、与该镜像不同源，不得用于任何 pc 符号化 |
| 驱动 | `9d66dd367d09af4d…`（复用 roundb 的 apfs 产物）。`nm -u` 只有 `_memcpy`，没有 `_memmove`、没有 `_bcopy` |
| AIR 库 | `d7b9ced5a115c08c…`（复用 roundb 的 apfs 产物）。`nm -u` 有 `_memmove`，镜像里 7 个 `_memmove` 调用点，见 3.7。**这一份带逐帧计时插桩**，见 9.4 |
| lsprobe | 复用 roundb 的 apfs 产物，本轮不改 |
| 作业脚本 | `tools/k90auto/jobs/rc.jobs.freeze`，sha256 `a4af9a9f1384fbac`，与 roundb 同一份 |
| 唯一变量 | 内核（bad access 行加 region 后备文件名与起止，并在行尾加 lr／x0／x1／x2；线程 dump 加 exec 基址行） |

五条边界，读任何数之前先过：

- roundb 那两个 pc 的归属已经离线定到共享缓存里的 `libsystem_platform.dylib` 的 `_platform_memmove`，逐条复核见[归属复核](2026-10-28-roundb-memmove-attribution.md)。round C 的 region 后备文件名与 exec 基址两处打印因此是交叉验证，也是把这个推导变成每轮都有的直接读数，3.2 与 3.3 已按缓存这一组候选改写。
- 本轮是诊断轮。`python3 tools/round-stats.py <证据目录>` 的 `frames` 段按帧号 id 的断裂数盖印章，roundb 是 13 处断裂、99 帧，盖 `NOT A PERFORMANCE BASELINE`；round C 断裂 0、3611 个帧号，盖的是 `usable as a performance baseline`。那个印章只判帧号连续性，判不了一轮能不能出性能数，实测与理由见 9.3。
- `summary.py --verify` 的 `coverage:` 行与 `thermal:` 行、`round-stats.py` 的 `ring coverage`／`swap holes`／`fence timeouts` 三段全部原样贴，不做二次加工。`coverage` 跨度不足轮次时长一半时，只报「该跨度内的局部值」并写明跨度。
- 轮次目录在 device 宣布收尾之前不读。中途读了必须标 `partial, through s0NN`；roundb 上有人因此把 36／94／99 读成 0／0／45。
- **以行数为单位的窗口口径受插桩状态影响，两个插桩状态下的比例不可直接比。** roundb 与本轮装车的 AIR 库（`d7b9ced5`）带逐帧计时插桩（9.4），插桩会往日志流里加行，所以「随后 N 行内」这个窗口在插桩开着时对应的时间跨度比关着时短。实例：[归属复核](2026-10-28-roundb-memmove-attribution.md) §8 那个「1775 条 `copied` 里 209 条（11.8%）在随后 4 行内出现 bad access」，它的 4 行窗口是在插桩开着的条件下量的，插桩关掉之后同一个 4 行覆盖更长的时间，比例会变大，两个数不可直接比。凡是「N 行内」的口径都要与插桩状态一起报；要跨插桩状态比，把窗口从行数换成时间（用同一行里的 `tl:` 时间戳之差）。这条与「验收轮必须关掉插桩」是同一件事的两面：插桩既影响绝对耗时，也影响以行数为单位的窗口口径。

计数口径全文统一：默认报「唯一行」，即跨快照按整行去重之后的条数；需要与量级对照时同时给 raw（跨快照求和）并在同一句里写明两个数各自是什么。`round-stats.py` 只读 `s*.log`，`summary.py` 的 `merged_log()` 还读 `returned.log`／`hung-held.log`／`running.log`，两者的文件集合不同，报数时写清用的是哪一个工具。

## 2. 两类新行的字段表与匹配串

原文格式串（源码提交 `5c9f563`，`osfmk/arm64/sleh.c:2124` 与 `osfmk/kern/redwood_threads.c:52`，display 在最终镜像里 `strings` 核过，lead 也核过）：

```
redwood: %s bad access at %#llx pc %#llx region %s %#llx-%#llx lr %#llx x0 %#llx x1 %#llx x2 %#llx
tl: td %d exec %#llx %s
```

按空白拆分的字段位置（`$1` 起）。`$1` 到 `$11` 与上一版逐字一致，四个新字段全部追加在行尾：

| 行 | 字段 | 含义 |
|---|---|---|
| bad access | `$2` | 进程名，仍只有 `backboardd` 与 `SpringBoard` 会打 |
| bad access | `$6` | 故障地址 |
| bad access | `$8` | pc |
| bad access | `$10` | pc 所在 region 的后备文件名（basename），取不到时是 `-` |
| bad access | `$11` | 该 region 起止，形如 `0x2b0f80000-0x2b0fbb000` |
| bad access | `$12` | 字面量 `lr` |
| bad access | `$13` | lr，调用方的返回地址，保存状态原始值，内核不剥 PAC |
| bad access | `$14` | 字面量 `x0` |
| bad access | `$15` | x0，`memmove`／`memcpy` 的 dst 实参 |
| bad access | `$16` | 字面量 `x1` |
| bad access | `$17` | x1，src 实参 |
| bad access | `$18` | 字面量 `x2` |
| bad access | `$19` | x2，len 实参 |
| exec | `$3` | pid |
| exec | `$4` | 字面量 `exec`，用来与同前缀的 `tl: td <pid> slide …`、`tl: td <pid> tid …` 区分 |
| exec | `$5` | 基址，为 0 表示这个 task 没有「有 vnode 后备且权限含 execute」的 region |
| exec | `$6` | 该 region 的后备文件名（basename），取不到时是 `-` |

匹配串按行首行尾锚定写，三个版本各一条：

```python
BADACCESS     = r'^redwood: (\S+) bad access at (\S+) pc (\S+) region (\S+) (\S+) lr (\S+) x0 (\S+) x1 (\S+) x2 (\S+)$'
BADACCESS_MID = r'^redwood: (\S+) bad access at (\S+) pc (\S+) region (\S+) (\S+)$'
BADACCESS_OLD = r'^redwood: (\S+) bad access at (\S+) pc (\S+)$'
EXEC          = r'^tl: td (\d+) exec (\S+) (\S+)$'
```

按字段数分流，`NF` 是 19 的行属于本轮内核 `cf1502f5…`，11 属于 `81f54468…` 那一版，9 属于 roundb 的 `9a7a118a…`。按字段数分流之前先看 `NF`：`NF` 是 9 或 11 的行来自旧内核，它缺的字段不构成任何结论（协议 §5：新增的日志行在它被编进去之前，缺席不构成结论）。

`NF` 大于 19 时说明 region 的 basename 里带了空格，此时按字面量定位而不是按位置取：在拆出的 token 序列里找满足 `t[i]=='lr'` 且 `t[i+2]=='x0'`、`t[i+4]=='x1'`、`t[i+6]=='x2'` 的那个 `i`，`t[i-1]` 是起止，`t[9]` 到 `t[i-2]` 用单个空格拼回是名字，`t[i+1]`／`t[i+3]`／`t[i+5]`／`t[i+7]` 依次是 lr／x0／x1／x2。这一行还要原样贴出来报给 lead。

四个新值有一条共同的排除项：取值前判了 `is_saved_state64(state)`（`sleh.c:2116`），32 位保存状态下四个值都是 0。本轮两个进程都是 arm64e，走不到那个分支；四个值同时为 0 时先按这条排除，不要读成「调用方是地址 0、dst／src／len 都是 0」。

### 2.1 三条自我否证判据

这四列的价值在于它们能推翻本文自己的离线结论，所以每条都写成「不成立时怎么办」，三条同时成立才算归属在设备侧得到交叉验证。推导过程见[归属复核](2026-10-28-roundb-memmove-attribution.md) §4 到 §6。

| 判据 | 成立条件 | 不成立时 |
|---|---|---|
| `$17` 等于同一行的 `$6` | 两处故障指令都是第一次源访问（`libsystem_platform` 的 `+0x9c0` 是 `ldnp q2, q3, [x1]`、`+0xad4` 是 `ldr x6, [x1], #8`，都从 x1 读、x1 未被改过），所以 src 实参就是故障地址 | `$8` 的归属要重判，先核 slide 与 `imagesText` 查表那两步 |
| `$19` 与同行 `$8` 的偏移对应 | `+0x9c0` 要求 `64 ≤ len < 16384`，`+0xad4` 要求 `len < 64`（分派在 `+0x940` 的 `cmp x2,#0x40` 与 `+0x954` 的 `cmp x2,#4, lsl #12`） | 偏移与长度两条读数至少有一条错，把两个数都贴出来报 lead，不要各取一半拼结论 |
| `$13` 不落在 `libredwoodmetal.dylib` | `nm -u` 实测 roundb 装车那份驱动（`9d66dd36`）的未定义符号里只有 `_memcpy`，没有 `_memmove`、没有 `_bcopy`，它调不到 memmove | 「`_platform_memcpy` 与 `_platform_memmove` 是两个独立实现」这条要重查。归属复核 §6.1 已查出子任务对 `+0x6af4` 的定性是错的（那是一个 4 参、先 `memchr` 再 `memmove` 的 `strlcpy` 形状，且它有 2 条 `bl` 进 memmove），所以这个分支值得当真 |

一处与 display 那份记录对不上的地方，判据按实测写：`%#llx` 打 0 得到的是 `0`，`#` 标志只在值非零时加前缀。宿主机实测（`cc` 编 `printf("%#llx-%#llx", 0, 0)`）输出 `0-0`，`printf("%#llx", 0)` 输出 `0`。所以「pc 当时不在任何 map entry 里」实际会打成 `0-0`，[内核改动记录](../progress/2026-10-28-kernel-badaccess-region.md) §1 表格里写的 `0x0-0x0` 与它不符。判据因此写成与两种形式都相容的判法：把起止按 `-` 拆成两半，各自 `int(x, 16)`（`int('0', 16)` 与 `int('0x0', 16)` 都是 0），两半都为 0 才算这一类。已把这一条报给 display 与 lead 核对。

exec 行的位置：紧跟同一次 dump 的 `tl: td <pid> slide %#x` 行之后。一次 dump 的行序是 `tl: td pid <N> threads <M>`、`slide`、`exec`、逐线程行、`tl: td pid <N> printed <K>`。

同一 pid 的多次 dump 打出的 exec 行文本完全相同（基址与文件名都不变），跨快照去重之后合并成一条。所以 **exec 行按唯一行计数得到的是「被 dump 过的 pid 代次数」**，dump 次数从这个数恢复不出来。roundb 的 `tl: td pid <N> threads <M>` 唯一行 16 条、`slide` 唯一行 10 条，读法分别是「16 个不同的 (pid, 线程数) 组合」与「10 个不同的 (pid, slide) 组合」，两个数都读不成 dump 次数。

覆盖率影响：bad access 每条比旧版多约 60 字节，每次 dump 多一条 exec 行，打印范围仍是 `backboardd`／`SpringBoard`。roundb 的规模是 raw 212 条、唯一行 11 条、平均行长 140 字节，多出 212 × 60 ≈ 12.7 KB，对 1.31 MB 的环可以忽略，`ring coverage` 的两条判据沿用。

## 3. bad access 的 pc 归属

### 3.1 三种「取不到名字」分开计数

三种情形是三种结果，分别计数，不合并成一种「拿不到名字」：

| 类 | 判法 | 含义 | 怎么记 |
|---|---|---|---|
| A 名字直接给出 | `$10` 不是 `-` | region 有 vnode 且 namecache 里有名字 | 按名归属，见 3.2 |
| B 有 region 无名字 | `$10` 是 `-` 且起止两半不全为 0 | region 存在，无 vnode 后备，或 namecache 里没有它的名字 | 走 3.3 的反推；反推不成立写「判不了」 |
| C pc 不在任何 region | 起止两半都为 0 | pc 当时不落在任何 map entry 里 | 单独一类，记「pc 不可信」，不记「镜像未知」 |

B 与 C 的处置相反：B 是「镜像待定」，C 是「这个 pc 本身不能用」。把 C 并进 B 会把一个已经跳出映射的 pc 读成某个镜像里的偏移。

### 3.2 主路径：region 名直接给出

A 类直接读 `$10`。归属与 P2 的对应关系（由 lead 判处置）：

| `$10` | 归属 | 对拷贝路径的含义 |
|---|---|---|
| `libredwoodmetal.dylib` | 我们的驱动 | 拷贝路径实现自身引入段错误，修 |
| `libredwoodair.dylib` | 我们的 AIR 库 | 同上，落点在 `tools/mesa/air/` |
| `dyld_shared_cache_arm64e` 或它带 `.NN` 后缀的形式 | 共享缓存里的某个 iOS 系统库，具体是哪一个要按 3.3 第 4 步算 | 故障在系统库里，要查的是把非法值传进去的调用方 |
| `backboardd`／`SpringBoard` | 主二进制 | 已剥符号，只有偏移，见 3.4 |
| 其余任何 basename | 表外的系统库或私有库 | 先把这一行原样贴出来再判归属 |

第三行是 round C 最可能出的一类，理由在[归属复核](2026-10-28-roundb-memmove-attribution.md)：roundb 那两个 pc 离线定到了 `libsystem_platform.dylib` 的 `_platform_memmove`，而缓存里的镜像是 dyld 按 subcache 文件 `mmap` 进来的，所以 vm_map entry 的后备 vnode 是 subcache 文件本身，`$10` 打出来会是 `dyld_shared_cache_arm64e.77` 这一类名字，**不会是 `libsystem_platform.dylib`**。缓存的 4315 个镜像共享 85 个 subcache 文件，看到 subcache 名只说明 pc 在缓存里，具体镜像要靠 3.3 第 4 步。

`$10` 是 basename，不含目录。出现表外的名字时先把这一行原样贴出来，再判归属，不要按名字相似去猜镜像。

判据：

- 通过：A 类至少一条，且 `$10` 落在上表五行之一。此时 P2 的决定点已经拿到，把该行原文、唯一行条数、raw 条数一起报。`$10` 是 subcache 名时，通过的条件还要加上 3.3 第 4 步算出的镜像名与镜像内偏移。
- 不通过：A 类为 0 而 B 类不为 0。此时按 3.3 反推，反推成立仍可用，不成立写「判不了」。
- 无法判定：A、B 都为 0，只有 C 类；或者本轮 bad access 唯一行为 0。唯一行为 0 时必须附 `ring coverage` 的单份可容纳时长与并集跨度，并写明是单份口径还是并集口径（两者差 2.2 倍），否则不构成「本轮没有 bad access」。

### 3.3 备选路径：只有起止

前提要先立住：这条打印在用户态数据异常的路径上（`osfmk/arm64/sleh.c`，pc 取 `get_saved_state_pc(state)`），pc 是当时正在执行的指令地址，所以它所在的 region 必然带 execute 权限。候选分两组：我们自己那三个镜像的 `__TEXT`（`__DATA_CONST`、`__DATA`、`__LINKEDIT` 都不在候选里），以及共享缓存的 `__TEXT` 镜像区（缓存里 4315 个镜像的 `__TEXT`，roundb 的答案就在这一组）。

反推用的数是 **`__TEXT` 的 vmsize**。文件字节数与它差一到两个量级，拿文件大小去比 region 大小会得出错误结论：`libredwoodmetal.dylib` 文件 241,488 字节而 `__TEXT` 只有 131,072 字节，`libredwoodair.dylib` 文件 13,983,936 字节而 `__TEXT` 是 12,632,064 字节。task-5 与 [内核改动记录](../progress/2026-10-28-kernel-badaccess-region.md) §2 都写的是文件字节数，本文按段表实测值改正，已报 lead。

三个候选的段表，按本轮实际装车的产物实测（`otool -l`）：

| 镜像 | 文件字节 | `__TEXT` vmsize | `__DATA_CONST` | `__DATA` | `__LINKEDIT` | 运行时路径 | 本地副本 |
|---|---|---|---|---|---|---|---|
| `libredwoodmetal.dylib` | 241,488 | `0x20000` = 131,072 | `0x4000` | `0x8000` | `0x14000` | `/redwood/lib/libredwoodmetal.dylib` | `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root/lib/libredwoodmetal.dylib`，sha256 `9d66dd367d09af4d…` |
| `libredwoodair.dylib` | 13,983,936 | `0xc0c000` = 12,632,064 | `0x9c000` | `0x38000` | `0xac000` | `/redwood/lib/libredwoodair.dylib` | `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root/lib/libredwoodair.dylib`，sha256 `d7b9ced5a115c08c…` |
| `backboardd` | 1,366,064 | `0x100000` = 1,048,576 | `0x10000` | `0x20000` | `0x20000` | `/usr/libexec/backboardd` | `hackios-xnu-kernel/ios26/rootfs/usr/libexec/backboardd`，sha256 `050bc2ea69fd76a8…` |

三个 `__TEXT` vmsize 互不相同，size 精确匹配一次就能定归属。用之前先核产物：本地副本的 sha256 要与本轮 apfs 里解出的文件一致（协议 §5：manifest 记应该跑什么、apfs 记实际跑了什么），不一致就用 apfs 里那份重算段表。

四步，按顺序：

1. **精确匹配 size。** `size = hi − lo`。`size` 等于 `0x20000`／`0xc0c000`／`0x100000` 之一时，归属就是对应镜像，记「按 region 大小判定」。
2. **偏移上限排除。** `size` 与三个值都不相符时（vm_map entry 被切过，region 是某个 `__TEXT` 的一段），改用 `off = pc − lo` 与 `off + size ≤ vmsize` 逐个候选过一遍。`off ≥ 0x20000` 排除 `libredwoodmetal.dylib`，`off ≥ 0x100000` 再排除 `backboardd`。只剩一个候选时记「按偏移上限判定，region 被切分」。
3. **exec 基址交叉核。** 同一 pid 的 `tl: td <pid> exec <基址> <名>` 给出主二进制的 `__TEXT` 基址。`0 ≤ pc − 基址 < 0x100000` 时 pc 在 `backboardd` 主二进制里，与第 1、2 步的结果必须一致；不一致就把两个读数都贴出来报 lead，不要挑一个。`pc − 基址` 落在 `[0x100000, 0x150000)` 时 pc 在 `backboardd` 的数据段里，与「pc 正在执行」矛盾，说明这个 pc 不可信，按 C 类读。
4. **共享缓存查表。** 前三步都不成立而 `pc − slide` 落在缓存的 `__TEXT` 镜像区里时，pc 属于缓存里的某个系统库。算法与三个边界数见[归属复核](2026-10-28-roundb-memmove-attribution.md) §3 与 §4：`slide` 取同一 pid 的 `tl: td <pid> slide %#x` 直接读数，`u = pc − slide`，在 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/dyld_shared_cache_arm64e` 头部 `+0x88` 的 `imagesText` 数组（4315 项、每项 32 字节、`loadAddress` 在 `+16`、`textSegmentSize` 在 `+24`、`pathOffset` 在 `+28`）里找 `loadAddress ≤ u < loadAddress + textSegmentSize` 的那一项，镜像名就是它的 `pathOffset` 指向的路径，镜像内偏移是 `u − loadAddress`。该数组的 `max(loadAddress + textSegmentSize)` 是 `0x2adb74640`，`u` 超过它就落在缓存的 `__TEXT` 镜像区之外，此时写「判不了」并把 `u` 与这个上界一起报。

四步都不成立时写「判不了」，并附四样东西：region 起止、算出来的 `size` 与 `off`、三个候选的 `__TEXT` vmsize、`pc − slide` 与 `0x2adb74640` 的关系。写「判不了」本身就是一条结论：它把「需要再补一个打印」与「归属已定」区分开，下一轮据此决定补什么，不再重复走同一条路。

`SpringBoard` 不在候选表里，因为 roundb 的 212 条 raw bad access 的进程名全部是 `backboardd`。本轮若出现 `$2` 为 `SpringBoard` 的行，先按 A 类读名字；落到 B 类时补一行 `SpringBoard` 的段表再反推，不要拿 `backboardd` 的段表套。`SpringBoard` 的主二进制只有 133,344 字节、`__TEXT` 只有 `0x4000`，其中 `__text` 段是 4 字节的一条 `b` 指令跳到 `_SBSystemAppMain` 的 stub，所以它的 pc 绝大多数落在共享缓存里，走第 4 节那条路。

### 3.4 归属定了之后取函数名

`BUILD_DSYM=0` 影响的是内核镜像的符号化。bad access 的 pc 是用户态 pc，符号化走镜像自己的符号表，与内核 dSYM 无关，本轮可用。

命令形式（宿主机，已实测）：

```sh
# 我们的两个 dylib，__TEXT 的 vmaddr 是 0，-l 直接填 region 起点
atos -o <本地副本> -arch arm64e -l <region 起点> <pc>
```

实测两条：`atos -o …/libredwoodmetal.dylib -arch arm64e -l 0x2b0000000 0x2b000dcf4` 给出 `+[RedwoodMetalArgumentEncoder load] (in libredwoodmetal.dylib) + 0`；`atos -o …/libredwoodair.dylib -arch arm64e -l 0x2b0000000 0x2b0092994` 给出 `ddebug_screen_create (in libredwoodair.dylib) + 0`。

三个候选的符号可用性不同，取不到名字时按这张表写原因：

| 镜像 | 本地已定义符号 | 能不能给函数名 |
|---|---|---|
| `libredwoodair.dylib` | 13,908 | 能 |
| `libredwoodmetal.dylib` | 1,027 | 能 |
| `backboardd` | 1（只有 `__mh_execute_header`） | 不能，只有偏移；要继续就得反汇编该偏移，靠 `__stubs` 的间接符号表认调用目标 |
| 共享缓存里的系统库 | 本地没有可用路径 | 不能，见第 4 节 |

命中 `backboardd` 时，报「偏移 `0x…`，主二进制已剥符号，函数名待反汇编」，不报一个猜出来的名字。

### 3.5 条数口径

bad access 有三个口径，各自量不同的东西，报数时三个并列并写明用的是哪一个：

| 口径 | roundb 的值 | 量的是什么 | 怎么数 |
|---|---|---|---|
| raw 跨快照求和 | 212（`s[0-9]*.log`），加 `hung-held.log` 是 225 | 打印条数，含快照重叠造成的重复 | 每份快照各数一遍再相加 |
| 唯一行 | 11 | 不同的 (进程名, 故障地址, pc) 组合数 | 跨快照按整行去重 |
| 物理事件 | 15 | 故障发生了几次 | 单份快照的有序流里，每条 bad access 之后 5 行内第一条 `redwood: proc backboardd pid N died on signal 11 code 11` 的 pid，跨轮去重 |

这条打印在故障路径上不节流，每次故障打一条，而同一组合的两次故障文本完全相同，所以唯一行会合并、raw 会重复，两者都读不成事件数。事件数走第三个口径：故障之后紧跟同代的死亡行，按死亡行的 pid 去重。roundb 这样数出 15 起，与该轮 `redwood: backboardd pid N exited code -1 reason 2` 的 15 个 pid **完全相同**，两个独立来源给出同一个 15 代集合，口径因此立住。推导与逐条核对见[归属复核](2026-10-28-roundb-memmove-attribution.md) §7。

对齐与结论一律用 15 起这个口径。邻接法成立的前提是相邻关系只在单份快照内部有意义，跨快照拼接会破坏它，所以数事件要逐份快照数完再按 pid 去重。本轮若出现「bad access 之后 5 行内没有死亡行」的条目，把这些条目单独列出来报，事件数写「至少 N 起」并说明缺口。

判据写成三个口径加取值分布：报 11 个组合各自的 `$6`、`$8`、`$10`、`$11` 与每个组合在 raw 里的条数，再报 15 起事件各自的 pid 与故障地址。

### 3.6 拷贝路径的阈值实测：65536 字节，`copied` 的尺寸字段是调用方请求的长度

P2 要判拷贝路径的去留，阈值与尺寸分布是它的输入，两处都与既有记录对不上，这里按源码与 roundb 的日志核一遍。

阈值是 **65536 字节**。`hackios-xnu-kernel/userland/src/redwoodmetal.m:2408` 的 `enum { NOCOPY_LIMIT = 0x10000 }`，`newBufferWithBytesNoCopy:` 在 `length > NOCOPY_LIMIT` 时返回 nil 并打 `rwa buffer: %lu bytes left nil, over the %u this path copies`（`:2413`）。它上面那段注释（`:2405`）写的是「16 KiB is 109 of the 128 requests a round logs」，与常量差 4 倍；[交接文档](../plan/2026-10-28-team-handoff-model-switch.md) §2 的「大于 16 KiB 阈值」沿用的是注释那个数。日志自己把实际阈值打出来了，roundb 的那一条是 `rwa buffer: 1359872 bytes left nil, over the 65536 this path copies`，所以以 65536 为准。1.3 MB 那个 nil 的结论两种阈值下都成立。

`rwa buffer: copied %p of %lu bytes, buffer at %p`（`:2641`）里的尺寸字段是 `length`，即调用方请求的长度，而 `memcpy(_contents, bytes, length)`（`:2638`）拷的就是这个长度，所以它同时是请求长度与拷贝长度；分配长度走 `initWithDevice:gpu:length:` 拿到的 `_length`，同一个值。

roundb 的分布，两个口径都给（唯一行按 `s*.log` 跨快照去重，raw 分两种文件集合）：

| 尺寸（字节） | 唯一行 | raw（`s*.log`） | raw（加 `hung-held.log`） |
|---|---|---|---|
| 32768 | 94 | 1,487 | 1,579 |
| 15360 | 5 | | |
| 62464 | 5 | | |
| 16384 | 4 | | |
| 65536 | 1 | | |
| 合计 | 109 | 1,675 | 1,775 |

32768 的占比在两种文件集合下都是 89%，[交接文档](../plan/2026-10-28-team-handoff-model-switch.md) §2 记的「1,775 条原始行、32768 占 89%（1,579 条）」是加 `hung-held.log` 那个口径，与 `round-stats.py` 只读 `s*.log` 的 1,675／1,487 差 100 条，占比一致。

**全部取值都 ≤ 65536，最大的一条正好等于阈值。** 所以「超过阈值仍被拷贝」这一条不成立，32768 那些拷贝是按设计走的，P2 的结论不因它改变。要改的是注释里那个 16 KiB 与各处沿用的说法。

两条 nil 打印来自两个不同的产生方，分开计数：`rwa buffer: <N> bytes left nil, over the 65536 this path copies` 是我们驱动自己打的（roundb 唯一行 2 条、raw 8 条），`nil buffer from memory: [b:… o:… l:…], w:… h:… bpr:… bpi:…` 是 CoreAnimation 侧的 os_log（带墙钟时间戳前缀，roundb raw 8 条）。交接文档里的「`nil buffer from memory` 25 条」指的是后者，与前者不是一份计数。已按协议 §5 核过这两条路径在 roundb 实际装车的驱动里存在：`strings` `9d66dd36` 那份 `libredwoodmetal.dylib` 命中 `rwa buffer: %lu bytes left nil, over the %u this path copies` 与 `rwa buffer: copied %p of %lu bytes, buffer at %p` 两条格式串。

### 3.7 `lr` 的归属：调用方是谁

`$13` 是调用方的返回地址。pc 的候选集合与 `lr` 的候选集合是两件事，分开读：pc 是当时正在执行的指令地址，它所在的 region 必须可执行，候选是 3.3 那两组 `__TEXT`；`lr` 是调用方的指令地址，候选多一类，而且那一类是我们自己的库：`libredwoodair.dylib`（`d7b9ced5`）导入 `_memmove`，镜像里有 7 个 `_memmove` 调用点，驱动那份（`9d66dd36`）不导入 `_memmove`。

内核打的是保存状态的原始内容，**没有剥 PAC**：在内核里剥一个用户态返回值要选 key，选错会得到一个看起来正常、实际错掉的地址，而原始值的高位形态自己会说明有没有签名。所以归属按三步走，走完第三步还不成立就停下。

1. 先用原值试三类区间：

   | 区间 | 判法 | 归属 |
   |---|---|---|
   | 共享缓存 | `lr − slide` 落在 `0x180000000..0x2c2cf4000`（`slide` 取同 pid 的 `tl: td <pid> slide %#x`；等价地，运行时区间是这两端各加 slide） | 缓存里的系统库，按 3.3 第 4 步查 `imagesText` 得镜像名与镜像内偏移 |
   | `libredwoodair.dylib` | `lr` 减去下表 7 个预期值之一得到页对齐的差，见下面那一步 | 我们的 AIR 库，那个预期值就是调用点，差值就是加载地址 |
   | `libredwoodmetal.dylib` | 前两类都不成立时才考虑，`__TEXT` vmsize `0x20000` | 与导入表冲突，按 2.1 第三条处理，不要直接采信 |

2. 三类都不落且 bit 47 以上有非零位时，把原值清零到 bit 47 以下再走一次第 1 步，**两次的值都报**。带签名的返回值清零后落进区间是正常结果，此时归属按清零后的值写，同时保留原值，因为原值的高位形态是「这个 lr 被签过名」这一事实的唯一记录。
3. 清零后仍不落在任何区间：停下，不猜。把 `lr` 原值、清零后的值、同 pid 的 `slide` 与 `exec` 基址四项一起贴出来报 lead。

AIR 库那一步不需要内核另外打它的基址。memmove 函数体内没有跳出体外的分支（[归属复核](2026-10-28-roundb-memmove-attribution.md) §5 扫全 `__TEXT` 的结果），所以故障时刻的 `lr` 就是调用方那条 `bl` 的下一条指令地址。7 个调用点各加 4，低 12 位互不相同，而 dylib 的加载地址页对齐，于是给定一个运行时 `lr`，7 个候选里只有一个能让 `lr − 预期值` 页对齐，那一个就是调用点，差值就是加载地址：

| 调用点（dylib 内 vmaddr） | 预期 `lr` | 低 12 位 |
|---|---|---|
| `0x1d6008` | `0x1d600c` | `0x00c` |
| `0x1d69f8` | `0x1d69fc` | `0x9fc` |
| `0x212a7c` | `0x212a80` | `0xa80` |
| `0x260534` | `0x260538` | `0x538` |
| `0x2605fc` | `0x260600` | `0x600` |
| `0x3a7f8c` | `0x3a7f90` | `0xf90` |
| `0x3db3ac` | `0x3db3b0` | `0x3b0` |

这 7 个调用点在源码里对应哪一处，本轮判不了：dylib 已剥局部符号，镜像里的 7 个与 Mesa 源码里 9 处 `memmove` 调用点对不上数，差的成分未逐个验证（[归属复核](2026-10-28-roundb-memmove-attribution.md) §6.3 列了 9 处的 file:line 与三类可能的差因）。所以 `lr` 落到 AIR 时，结论写到「调用点是这 7 个里的第几个、加载地址是多少」，源码位置留到能用未剥符号的目标文件比对时再补。

`$15`／`$17`／`$19` 三列的用法在 2.1 的三条自我否证判据里，那里写了不成立时怎么办。补一条正向用法：`$19` 与 `$17`、`$15` 一起给出这次 `memmove` 的三个实参，`$17` 是非法值而 `$15`、`$19` 正常时，问题在 src 的来源；`$19` 也异常时，问题在调用方那一侧的参数构造，两种形态要分开报。

## 4. 线程 dump 里的 pc

dump 里逐线程行的 pc 分三类，符号化路径不同，不要混用：

| pc 形态 | 归属 | 用什么命名 |
|---|---|---|
| 减去该 pid 的 `slide` 之后落进共享缓存的 `__TEXT` 镜像区 | 缓存里的系统库 | 按 3.3 第 4 步查 `imagesText` 得镜像名与镜像内偏移，再用 capstone 反汇编那个偏移；落在 `libsystem_kernel` 的 stub 区时另有一条捷径，即协议 §5 的系统调用号方法（stub 是 `mov x16,#imm` 加一条 `svc #0x80`，取立即数查 `osfmk/mach/syscall_sw.h` 与 `syscalls.master`） |
| 减去该 pid 的 `exec` 基址之后落进主二进制 `__TEXT` | 该进程的主二进制 | 主二进制加偏移；`backboardd` 与 `SpringBoard` 都已剥符号，只有偏移 |
| 两者都不落 | 私有 dylib 或不可信 | 需要该地址所在 region 的名字，本轮的 region 名只随 bad access 行打，dump 里没有，写「判不了」 |

`slide` 用本轮 `tl: td <pid> slide %#x` 的直接读数，每个 pid 一条。交接文档 §3 里那个 `0xb05000` 已确认是错的，roundb 的正确值是 `0xbc54000`（全轮 `slide 0x…` 只有这一个值、出现 239 次，`0xb05000` 零命中），核对过程见[归属复核](2026-10-28-roundb-memmove-attribution.md) §2：`libsystem_kernel.dylib` 的 `loadAddress` 是 `0x232f09000`，它 `+0xccc` 是 `mov x16, #-0x2f`（即 `movn x16,#46`，−47）、`+0xcd0` 是 `svc #0x80`、`+0xcd4` 是 `ret`，与 `osfmk/mach/syscall_sw.h:128` 的 `kernel_trap(mach_msg2_trap, -47, 8)` 对上。`slide` 是 `0xffffffff` 时表示该 task 从未设置过共享缓存 slide，此时缓存内的 pc 不可读，按第三类记。

共享缓存的范围可以从本地这份缓存直接算出来，位置是 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/`，85 个文件、4.87 GiB、UUID `46E741B7-0E75-3F19-A308-0464F4140B00`。三个边界数量的是不同的东西，用法见 3.3 第 4 步：

| 数 | 值 | 来源 |
|---|---|---|
| 声明的共享区 | `0x180000000..0x2c2cf8000` | 主缓存头部 `+0xe0` 的 `sharedRegionStart` 与 `+0xe8` 的 `sharedRegionSize` |
| 实际映射末端 | `0x2c2cf4000` | 85 个文件全部 mapping 项的 `max(address + size)`，比声明的末端少一页 |
| `__TEXT` 镜像区上界 | `0x2adb74640` | `imagesText` 4315 项的 `max(loadAddress + textSegmentSize)`，取自 `/usr/lib/updaters/libPS190Updater.dylib` |

`maxSlide` 是 `0x20000000`（头部 `+0xf0`），每轮的 slide 都在它范围内，但值每轮都变，所以判「落不落进缓存」要先减本轮的 slide 再比这三个数。交接文档 §3 那句「超出共享缓存上界」把第三个数当成了缓存上界，还用了错的 slide，两处都不成立，作废。

命名一个缓存内的 pc 要走 3.3 第 4 步的 `imagesText` 查表加反汇编，`atos` 与 idalib 这两条现成路径对这份缓存都不可用：`atos` 报 `cannot load symbols for the file dyld_shared_cache_arm64e for architecture arm64e`，宿主机没有 `dyld_shared_cache_util` 或 `ipsw`；`idb_open` 对主缓存文件与对 subcache `.77` 都返回 `Failed to open database`（两次都传了 `run_auto_analysis: false`、`build_caches: false`、`init_hexrays: false`），该目录下 `.symbols` 文件是 0 个，IDA 的共享缓存装载器通常需要它，这是最可能的原因，未验证。可用的组合是自己解缓存头部与 `imagesText`、按 subcache 的 mapping 表算文件偏移、再用 capstone 反汇编，[归属复核](2026-10-28-roundb-memmove-attribution.md) §1 给了四个结构的字段偏移，§4 给了走通的实例。

一个已经能离线算出的实例，用它示范第三类怎么写：冻结线里 tid 306 的 pc `0x105f00cd8`。假设 exec 基址是页对齐的 `0x105f00000`，偏移是 `0xcd8`；`SpringBoard` 的 `__TEXT` 只用到 `0x1000005d4`（`__text` 0x100000568 起 4 字节、`__auth_stubs` 0x10000056c 起 16 字节、`__unwind_info` 0x10000057c 起 88 字节），`0xcd8` 落在段内空白区，没有任何 section 覆盖它。所以「tid 306 的 pc 在 SpringBoard 私有 `__TEXT`」这个归属即使基址对上了也命不中代码，读法是「保存的 pc 不指向一条有效指令」。这与 `osfmk/kern/redwood_threads.c` 头注释写的取值条件一致：线程字段不持线程锁读，运行态线程的 `upcb` 可能不是当下的值。本轮拿到 exec 行之后先核这一条，再决定要不要给这个 pc 找名字。

## 5. 故障地址分类

`$6` 按形式分四类，各自单独计数。分类只看取值形式：本轮新打印给的是 **pc 所在** region 的起止，故障地址所在 region 的起止这一轮没有，所以故障地址的镜像归属拿不到。

| 类 | 判法 | 读法 |
|---|---|---|
| ASCII | 把 64 位值按小端拆成 8 个字节，全部落在 `0x20`~`0x7e` | 崩溃点把一段字符串的 8 个字节当指针解引用了。roundb 的两例：`0x2e697269732e656c` → `le.siri.`、`0x63756f5474656b63` → `cketTouc`。这一类要单独报，并把还原出来的字节原样贴出 |
| 小整数 | 值小于 `0x10000` | 空指针附近的偏移解引用，例如 roundb 的 `0x1`。这一类指向结构体字段偏移被当成指针 |
| 高位有值 | 值大于本轮已知的用户态映射上界，例如 roundb 的 `0x21f800010493` | 指针被改写或带了高位标记。要判它属于哪里，需要故障地址所在 region 的起止，本轮没有 |
| 其余 | 上面三条都不满足 | 落在正常地址范围，需要与当轮的映射对照才能定性 |

ASCII 类还可以再窄一步：把 8 个字节按小端与大端两种顺序都还原一次，只有一种能得到可读片段时按那一种记，两种都能时把两个串都贴出来，不挑一个。

判据：四类各自报唯一行条数与取值样本。

### 5.1 roundb 那两个 ASCII 故障地址：来源已追到

lead 在宿主机上直接搜了 roundb 那两个含 ASCII 的故障地址，结论可复算，抄在这里作为 ASCII 类的第一个实例。

`0x63756f5474656b63` 按小端还原是 `cketTouc`，是 `PocketTouchesExpected`／`pocketTouchesExpected` 从第 3 个字节起的 8 个字节（`&str[2]`）。它在 `hackios-xnu-kernel/ios26/rootfs/usr/libexec/backboardd` 里命中三处。表里的文件偏移按下面的安全写法取，是 `cketTouc` 这 8 个字节自己的位置，不含前导上下文；vaddr 由 `otool -l` 的 section 表算出（`addr + (文件偏移 − offset)`）：

| 文件偏移 | 所在 section | vaddr | 上下文 |
|---|---|---|---|
| 909023 | `__TEXT/__objc_methname`（file 842532..929329，addr `0x1000cdb24`、size `0x1530d`） | `0x1000ddedf` | `playState:forSpeed:error:`、`point`、`pointScale` |
| 938400 | `__TEXT/__cstring`（file 929329..959505，addr `0x1000e2e31`、size `0x75e0`） | `0x1000e51a0` | `ScreenOn`、`DisplayState`、`FaceTouchesExpected` |
| 958034 | `__TEXT/__cstring` | `0x1000e9e52` | `_content == ((void *)0)`、`on`、`faceExpected`、`wakeO` |

`0x2e697269732e656c` 按小端还原是 `le.siri.`，是 `com.apple.siri.` 从第 8 个字节起的 8 个字节（`&str[7]`）。它在 `backboardd` 里零命中，在 `ios26/rootfs/System/Library/CoreServices/SpringBoard.app/SpringBoard` 里命中 22 处，全部落在内嵌 plist 的 `<string>` 里；`com.apple.siri.` 同样命中 22 处，偏移各比 `le.siri.` 小 7，与 `&str[7]` 对得上。前四处是 40455 `com.apple.siri.TypeToSiriWidget`、72068 `com.apple.siri.orchestration.capabilities`、72961 `com.apple.siri.activation.service`、77782 `com.apple.siri.VoiceShortcuts.xpc`。

我们两个库零命中：`out/ios26-resume/bbmetal-device/libredwoodmetal.dylib`（`9d66dd36`）与 `libredwoodair.dylib`（`d7b9ced5`）里 `le.siri.`、`cketTouc`、`PocketTouches` 三个串的命中数都是 0，这两个文件就是 roundb 实际装车的版本，已按 sha256 核过。

搜索口径分三步，「零命中」要附它才成立：

1. 取偏移用固定串匹配：`grep -a -b -o -F '<串>' <文件>`。`-F` 走字符串匹配，不建自动机。
2. 取上下文有两条路：拿到偏移之后 `dd if=<文件> bs=1 skip=<偏移-40> count=120 2>/dev/null | strings`，或者先 `strings -t d -a <文件> | grep -F '<串>'`。`strings` 按 NUL 与不可打印字节切分，产生的都是短行，从根上避开长行缓冲。
3. 定位 section 用 `otool -l <文件>` 的输出交给 python 解析，把命中偏移落到 `sectname`／`segname`／`addr`／`size`／`offset`，§3.3 的段表核产物用的是同一步。

**带上下文窗口的正则写法禁用**：`grep -a -b -o -E '.{0,30}<串>.{0,30}'` 在 14 MB 的 `libredwoodair.dylib` 上耗时 6.31 秒、1,307 亿条指令、283 亿个 cycle，换成 `grep -a -b -o -F '<串>'` 是 0.08 秒，CPU 差 79 倍；两侧 `.{0,30}` 的有界重复让正则引擎在每个字节偏移上都做一次多路回溯。峰值内存两次分别是 2.9 MB 与 2.4 MB，所以这个写法的问题在 CPU。它给出的偏移还带 30 字节前导上下文（backboardd 三处是 908993／938370／958004，对应 vaddr `0x1000ddec1`／`0x1000e5182`／`0x1000e9e34`，各比上表小 30），两种偏移混在一份文档里会读成两个不同位置。

另一条内存口径，搜大文件之前先看：BSD grep 的内存开销约等于最长无换行段的 3 倍，`-a` 让它把二进制当文本，遇到长无换行段就整段缓冲。实测 64 MiB 全无换行的文件峰值 RSS 71 MB，同样 64 MiB 切成 64 字节一行只有 1.9 MB，1 MiB 单行 2.9 MB、2 MiB 单行 6.1 MB。**在多 GB 的二进制上用 `grep -a` 会按最长无换行段吃内存**，`userland/system26.apfs` 4.9 GB、`out/` 下那些 `root.apfs`、dyld 共享缓存都属于这一类，这是唯一能把 grep 的内存推到 GB 量级的用法；要在这些文件里搜字符串，先 `strings` 再 `grep -F`。

**共享缓存已搜，命中数如下。** 缓存位置是 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/`，85 个文件、4.87 GiB。用 python 流式 `bytes.find` 扫全部 85 个文件（块 8 MiB、块间保留 `len(pattern) − 1` 字节重叠，内存有界，不用 `grep -a` 扫多 GB 文件）：`le.siri.` 1958 次、`le.media` 567 次、`cketTouc` 23 次、`PocketTouches` 8 次。所以 `le.siri.` 那一条的来源候选包含缓存里的镜像，SpringBoard 主二进制的内嵌 plist 只是其中一个（22 处）；`backboardd` 的地址空间里有共享缓存，两个来源都在它的地址空间里，光凭故障地址分不出是哪一个。要分开就需要故障时刻的 region 归属，本轮的新打印给的是 pc 所在 region 而不是故障地址所在 region，所以这一项本轮判不了。缓存里的命中数与「多少个不同串、多少个镜像」是两件事，后者要先从命中位置抽完整字符串再按镜像归属，[归属复核](2026-10-28-roundb-memmove-attribution.md) §9 标了判不了。

读法上的三条限制：

- 这条线索不解决 P1 的归属问题。故障地址是被解引用的**值**，值来自数据；pc 仍可能落在我们的库里，只是它读的指针来自 iOS 侧的字符串数据。归属要靠 round C 的 region 后备文件名，判据在 §3.2 与 §3.3。
- 两个值取自字符串的不同偏移（`&str[2]` 与 `&str[7]`），落在同一个固定结构体偏移上的解释因此被削弱，更符合「按某个解析位置从一个装着字符串的缓冲里取出 8 字节当指针」。
- 它与拷贝路径的关系是一个具体假设：`9d66dd36` 让不超过 65536 字节的 buffer 返回真拷贝（见 §3.6），CA 于是走过原先 nil 失败的点；如果拷进来的内容在后续被当成结构或对象图走，就会出现字符串字节被当指针。这条假设已交 display 对源码，本文不写成结论。

## 6. 崩溃报告收集

round C 的作业脚本与 roundb 同一份（`rc.jobs.freeze`，sha256 `a4af9a9f1384fbac`），不新增崩溃报告收集作业：jobs 集合一变就是第二个变量，而这一轮的唯一变量是内核；加上下面第二条读数说明的，加了也拿不到内容。本节的读数来自脚本里已有的那两行 `lsprobe`，收集通道的修复排 round D。

数据源是 `lsprobe` 的 `probe_crashes()`（`hackios-xnu-kernel/userland/src/lsprobe.m:509`），它扫两个目录：`/private/var/mobile/Library/Logs/CrashReporter` 与 `/private/var/root/Library/Logs/CrashReporter`，前者标 `mobile`、后者标 `root`，并对第一层子目录下探一层。`rc.jobs.freeze` 里跑 `lsprobe 60 &` 与 `lsprobe 300 &`，**报告内容只在 `t=300` 那一次打**（`lsprobe.m:584`：`total == 0 || seconds < 300` 直接返回），`t=60` 只有计数。所以本轮若崩得早、`t=300` 那次没跑到，就一份内容都没有，这一项记「内容没采到，采集计划的限制」。

三种读数，分开写，不合并：

| 读数 | 匹配串 | 含义 |
|---|---|---|
| 目录空 | `lsprobe t=<T> crash_files=0 crashes=root=-` | `mobile` 目录打开成功且没有条目，`root=-` 是 `root` 那个目录打不开。ReportCrash 没有往 `mobile` 的 CrashReporter 目录写东西 |
| 通道不通 | `crash_files=1 crashes=mobile/DiagnosticLogs root=-`（名字后面没有 `(字节数)`），配 `crashfile=DiagnosticLogs bytes=0 head=` | `DiagnosticLogs` 这个子目录存在（`stat` 成功且是目录），而 `opendir` 失败（`lsprobe.m:543` 返回 NULL），于是它被当成一个条目计数（`lsprobe.m:569`）。本轮回答不了「ReportCrash 写了什么」 |
| 通道可用 | `crashes=mobile/DiagnosticLogs/<进程名>-<日期>.ips(<字节数>)`，配 `crashfile=<名> bytes=<n> head=<前 900 字节>` | 报告列出来了，`head=` 给内容 |

第二类在已归档的轮次里实测出现过：`kernel-12377-attr-crashlog`、`kernel-12377-attr-speed3`、`kernel-12377-attr26-persona`／`persona3`／`persona4` 的部分时刻。round C 的 apfs 复用 roundb 产物、`lsprobe` 本轮不改，所以预期仍落在第二类。

判据：

- 通过：出现第三类，且 `head=` 里读得到 `Exception Type`／`Termination Reason` 一类字段，其中的进程名与 `redwood: proc <名> pid <N> died on signal` 的进程名对得上。
- 不通过（记「通道不通，无结论」）：出现第二类。此时崩溃报告这一项写「收集通道不通」，这个读数只说明 `lsprobe` 列不出那个目录，ReportCrash 有没有工作、有没有写出报告都还没有读数。要修的是 `lsprobe`：给失败的 `opendir` 打 `errno`，下探层数从 1 加到 2，并把 `crashfile=` 的内容读取从 `t=300` 的门槛里放出来。改动落在 `hackios-xnu-kernel/userland/src/lsprobe.m`，需要容器构建修好（task-7）之后才能进 apfs，本轮不做。
- 第一类要配一条独立读数才能读成「没有崩溃」：`redwood: proc … died on signal` 的唯一行条数为 0，且附 `ring coverage` 的单份可容纳时长。只有目录空而死亡行不为 0 时，结论是「死了但没写报告」。

与死亡行的对齐按唯一行做，两类行分开报：

| 行 | 格式 | 字段读法 |
|---|---|---|
| `redwood: proc %s pid %d died on signal %d code %d` | `bsd/kern/kern_exit.c:1760` | `$3` 进程名（`p_comm`，16 字节截断，原样贴不展开）、`$5` pid、`$8` 信号、`$10` `osr_code` |
| `redwood: %s pid %d exited code %d reason %u` | `bsd/kern/kern_exit.c:1769`，只对 `backboardd` 与 `SpringBoard` 打 | `$2` 进程名、`$4` pid、`$6` 退出码（信号致死时是 `-1`）、`$7` 是 `osr_namespace`；退出原因码 `osr_code` 在 `died on signal` 行的 `$10` |

`reason` 的取值查 `bsd/sys/reason.h:144` 起：`2` 是 `OS_REASON_SIGNAL`，`9` 是 `OS_REASON_EXEC`，`10` 是 `OS_REASON_SPRINGBOARD`，`13` 是 `OS_REASON_COREANIMATION`，`15` 是 `OS_REASON_RUNNINGBOARD`（旧名 `OS_REASON_ASSERTIOND`），`21` 是 `OS_REASON_METAL`。roundb 按唯一行实读：`backboardd` 15 代全是 `exited code -1 reason 2`（信号致死），`SpringBoard` 15 代里 14 代是 `reason 15`（RunningBoard 杀的）、1 代（pid 161）是 `reason 2`。这一列直接分开「自己死了」与「被谁杀了」，比只读 `9/0` 那一对信号给出的信息多，本轮起每轮都报。

世代数会随读哪一类行变化，报的时候把行类型一起写出来。roundb 的 `exited code` 行给出 `SpringBoard` 15 代、pid 集合 `{30, 91, 103, 131, 142, 161, 166, 175, 189, 205, 214, 228, 241, 246, 260}`，而[交接文档](../plan/2026-10-28-team-handoff-model-switch.md) §2 记的是 14 代、集合里有 267 而没有 91 与 166。差异来源待 task-2 的对齐结论，本文按实测值写；两代以上对不上时不要把两个集合合并成一个报。

对齐口径：以 pid 为键，把每个 pid 的 `died on signal` 时刻、`exited code` 时刻、以及该 pid 名下 bad access 组合的时刻排在一张表上。时刻一律用 `tl:` 基线逐点对齐，墙钟不能直接相减。bad access 行不带时间戳（它走 `printf`，`redwood_tl` 才带时间戳），所以它与死亡行的先后关系只能用同一份快照里相邻的 `tl:` 行夹逼，报的时候写明这是夹逼得到的区间并把区间宽度一起给出。

## 7. 停机段判据

`framewatch` 的 `resumed at … after N s` 本轮继续不作判据。误读的机制在 `framewatch.m:255`：`last` 只在 `frames > last` 时更新，而 `kern.redwood.frames` 在新的 `backboardd` 起来后从 0 重新计数，所以一个计数很低的代次结束后，下一代只要涨过那个低位 `last`，就被判成「恢复」。roundb 全轮只有 99 次交换交接、13 处帧号断裂，`last` 长期停在很小的值上，16 条 `resumed` 就是这么来的。

停机段一律用两个不依赖 `framewatch` 的读数：

- **交换空档。** `tl: s <id> <进程名> at <µs>`（`iokit/Kernel/MiniIOMobileFramebuffer.cpp:838`）带绝对微秒时间戳，按时间戳排序后取相邻差，大于 1.5 秒记一个空档。`round-stats.py` 的 `swap holes` 段就是这个算法，直接引它的输出，不另算一套。
- **帧号断裂。** `tl: v <id>` 的 id 只在增长，id 跳变一次是一个重起的指纹。`round-stats.py` 的 `frames` 段给断裂数，并按「断裂数大于 3 或帧数少于 500」直接标 `NOT A PERFORMANCE BASELINE`。

两个读数要一起用，因为它们分的是两种停机：

| 形态 | 交换空档 | 帧号断裂 |
|---|---|---|
| 停机但进程没换 | 有 | 无 |
| 停机且进程换了 | 有 | 有，断裂数等于重起次数 |

`tl: s` 的行里只有进程名没有 pid，所以「进程换没换」要靠帧号断裂、`exited code` 行的 pid 序列、或 exec 行的 pid 集合来判，不能从 `tl: s` 本身读。

判据：

- 通过（本轮拿到了停机段数据）：`swap holes` 给出的空档数与 `frames` 段给出的断裂数都非零或都为零，且 `ring coverage` 的并集覆盖了每个空档的时刻（逐点对齐，不用墙钟相减）。
- 不通过：并集覆盖不到某个空档的时刻。此时该空档只记「采集之外」，不记形态。
- 无法判定：`coverage` 跨度不足轮次时长一半。此时只报该跨度内的局部值并写明跨度。

## 8. 冻结形态与重启循环形态

round C 要回答的是这两种形态统一还是分开。判据表，全部用唯一行：

| 判据 | 冻结形态（`freeze` 轮） | 重启循环形态（roundb） |
|---|---|---|
| `backboardd` 的 `exited code` 行的不同 pid 数 | 0 | 15 |
| `SpringBoard` 的 `exited code` 行的不同 pid 数 | 0 | 15 |
| 帧号断裂数 | 0 | 13 |
| 截图分档（`round-stats.py` 的 `screens`） | 有内容，2 个唯一哈希 | `order: black x94`，5 个唯一哈希 |
| 交换空档形态 | 15 秒周期的 3 秒空洞，末尾一个 3.9 秒空洞后提交永久停止 | 约 10 秒 ×9，之后 16.4／20.3／40.3／80.3 秒 |
| `reason` 列 | 两个进程都没有 `exited code` 行 | `backboardd` 15 代全是 2（信号致死），`SpringBoard` 14 代是 15（RunningBoard 杀的）加 1 代是 2 |
| `redwood: proc … died on signal` 唯一行 | 26 条 | 178 条 |

`died on signal` 那一行不作形态判据：它对所有进程都打（`bsd/kern/kern_exit.c:1760` 没有进程名过滤），冻结轮里也有 26 条，条数差异来自整轮的进程活动量，不来自这两个桌面进程。分开两种形态的是 `exited code` 行，它只对 `backboardd` 与 `SpringBoard` 打（`kern_exit.c:1769`），冻结轮里两个进程都没有这一行。

两条形态判定，互相独立：

- 重启循环：`backboardd` 的 `exited code` 行里出现两个以上不同 pid，或帧号断裂数大于 0。两条满足任一即成立，同时成立时把两个数都报出来。
- 冻结：两个进程都没有 `exited code` 行、帧号断裂数为 0，而交换空档不为 0。

本轮的读法：两条都成立时写「两种形态在同一轮里都出现」，并按时间顺序给出各自覆盖的时段，不合并成一个结论。两条都不成立时（pid 只有 1 个、断裂 0、空档 0）写「本轮没有停机段」，并附 `coverage` 跨度证明确实观测到了那一段。

`framewatch` 的 `dump asked for`／`periodic dump` 行只用来确认 dump 有没有被请求，`tl: td pid <N> printed <K>` 用来确认 dump 有没有真的写出来。请求了而 `printed` 行缺席，说明 `kern.redwood.thread_dump` 那一步没走到，此时 exec 行也一定缺席，第 4 节的归属整段不可用。

## 9. 性能验收口径的可执行判据

用户 2026-10-28 追加的口径（[用户需求](../plan/2026-10-28-user-requirements.md) §6）是「不受热限制时 ≥60 fps」加「从冷机开始维持满频的时长」。此前以整轮平均帧率与「超过 35 ms 的帧不超过 9 个」为验收的条目一律作废。`fps`／`fps_mv`／`static` 三列都不能跨轮次比，能排序的只有 `gestures.py` 的手势口径。

### 9.1 不受热限制时 ≥60 fps

这台机器的驱动刷新率是 60 Hz：`perf-draw-v3` 的帧间隔 p50 是 16.66 ms，空闲时面板分频到 30 与 20 Hz，间隔精确落在 33.3 与 50.0 ms（[差距分析](2026-10-28-ios26-perf-gap.md) §2.18）。帧间隔的下界就是 16.67 ms，所以在 60 Hz 上「平均 ≥60 fps」与「一次都没掉槽」是同一件事：`gestures.py` 的窗口帧率算法是 `1000 × 间隔数 ÷ 间隔之和`，107 个间隔里有一个从 16.67 变成 33.3，结果就是 59.4。

由此得到一条 lead 已批准、**待用户确认之后才作为验收判定**的改写：**验收阈值写成「满频段内、有输入期间、每次下拉的掉槽帧数（间隔 ≥25 ms）为 0」，帧率数字保留两位小数一起报。** 论证是 60.0 这条线在 60 Hz 面板上连一个完美轮次都会因取整落到 59.98，而 iOS 16.5 的六轮基线本身是每次下拉 55.9~60.6、中位 56.4~59.8，按数字判会把参照物一起判不通过；25 ms 这个阈值落在 16.67 与 33.3 之间，任何一次掉槽都会被它抓到，所以「掉槽帧数为 0」在物理上等价于满足 60 Hz 刷新。改写成立的前提是刷新率确实是 60 Hz；若之后把面板模式提到 120 Hz，这条要重新写。

三个数并列报，缺一个都不构成结论：

| 数 | 来源 | 判据 |
|---|---|---|
| 掉槽帧数 | `gestures.py --each` 给出的每次下拉的间隔列表，数 ≥25 ms 的个数 | 通过：满频段内每次下拉都是 0。不通过：任一次下拉出现 ≥1 个 |
| 窗口帧率 | `gestures.py` 的逐次下拉行 | 报两位小数；判据落在掉槽帧数那一行 |
| 间隔分档 | 同上，按 16.67 ms 的整数倍分档：14~20 ms 是 1 槽、30~37 ms 是 2 槽、47~53 ms 是 3 槽 | 通过：全部落在 1 槽。2 槽与 3 槽要再分开两种原因，见下 |

分档按 16.67 ms 的整数倍分，是因为面板分频本身会产生 33.3 与 50.0 ms 的间隔（[运行协议](../plan/k90auto-run-protocol.md) §5 那条判读规则，实测在[差距分析](2026-10-28-ios26-perf-gap.md) §2.18：`perf-draw-v3` 的空闲帧间隔 p50 16.66 ms，`perf-draw-v6` 在 `glslow=3000` 强制每帧绘制耗时之后降到 30 与 20 Hz，间隔精确落在 33.3 与 50.0 ms）。2 槽与 3 槽的间隔要按这一条分开两种原因再判：间隔落在整数倍上是刷新率分频，落在整数倍之间才是绘制超时。验收时把这两种分开报，分频那一类不判不通过。

60 Hz 这个前提每轮都能核，不需要新增打印：驱动侧 `kFBRefreshHz` 是 60（`iokit/Kernel/MiniIOMobileFramebuffer.cpp:74`），只有 boot-arg `fb_hz=N` 能改它（`:145` 的 `TUNABLE`）。所以判法是两条并读，`summary.py` 的 `args` 列里没有 `fb_hz`，且本轮 `tl: v` 间隔的 p50 落在 16.6~16.7 ms。两条都对上，9.1 的改写在这一轮成立；`args` 里出现 `fb_hz` 而值不是 60，这一节整段要按那个值重写（分档倍数、掉槽阈值 25 ms、以及「≥60 fps」这个说法本身）。round C 之后若 `tl:` 侧能直接读到刷新率，把实测值补进这一节，替代上面这个间接判法。

`gestures.py` 现有的 `>18 N%` 档把 18~25 ms 的抖动与 33.3 ms 的掉槽混在一起，所以数掉槽帧要从 `--each` 的间隔列表自己数。给 `gestures.py` 加一个 `>25` 档、以及把 `CC_TARGET_FPS` 从 55 调到 60，都等用户确认了上面那条改写再动，本轮不改。

「有输入期间」的口径：`tl: p` 有指针事件的时段。`tools/k90auto/input_fps.py` 已经实现这一条（前后 0.25 秒内有指针事件、间隔落在 14~20 ms），38 轮里 36 轮落在 59.6~62.3。**`input_fps.py` 的数只回答「出帧的时候是不是贴着 60 Hz」**：它只把 14~20 ms 的间隔计入分子与分母，掉槽帧被排除在外，「有没有掉帧」要靠上面那三个数。引它的数时把这句话一起写出来。

「不受热限制时」的口径按 [差距分析](2026-10-28-ios26-perf-gap.md) §2.13 的四段取样：满频段、过渡段、截频段、重起前后各 10 秒。只有满频段内的窗口进验收，另外三段单列。切分点取 `cpufreq:` 频点分布的变化点，不取固定秒数。

样本量的下限：`gestures.py` 的 `coverage:` 行给出的识别数必须等于注入数，识别数少于注入数时结论只能是「样本不足」，既不判通过也不判不通过。`rc.jobs.perf`（sha256 `93f9f521267e3520`）是十四段 30 秒拖动、手势总时长 422 秒，性能轮只用它。

### 9.2 从冷机开始维持满频的时长

`summary.py` 新增一列 `ff_s` 与 `--verify` 的一行 `thermal:`，定义与口径：

- 数据源是 `cpufreq: domain 1 in <N> s: <直方图>; <C> changes, <U> us each; <L> times at the limit; hottest <T> C`。只取 domain 1，只取 `in N s:` 这一类；`hot ticks N of M` 是另一份直方图，与它在同一轮里交织出现，混进来会把两个分布当成一个。
- 满频档取本轮所有窗口里出现过的最高 MHz，不写死 3072。判的是「上限掉下来了」，上限属于本轮。
- `ff_s` 是从本轮第一个窗口起、连续满足「满频档份额大于 0」的窗口秒数之和。原点是第一个 cpufreq 窗口，粒度是一个窗口（30 秒）；开机时刻与轮次起点都在这个原点之前，两者到原点的差本轮没有读数。
- `thermal:` 行同时给出：第一个窗口的 `hottest`（判「冷机」是否成立）、掉档那个窗口的 `changes` 与 `hottest`、以及本轮 `hottest` 峰值。

满频档的去向有三种，分开判：上限全程没掉、掉档时接近本轮 `hottest` 峰值是热限制、掉档时远低于峰值是负载没了。四轮实测：

| 轮次 | `thermal:` 行 | 读法 |
|---|---|---|
| `attr-biomed` | `3072 MHz held for 150 s (5 of 13 windows), hottest 72.5 C in the first window, dropped at window 6 of 13 (19 changes, hottest 71.3 C of a 75.2 C peak)` | 热限制，与 [差距分析](2026-10-28-ios26-perf-gap.md) §2.12 手算的 708.9 秒起 3072 MHz 消失一致 |
| `attr26-freeze` | `3072 MHz held for 300 s (10 of 13 windows), hottest 74.4 C in the first window, dropped at window 11 of 13 (576 changes, hottest 77.9 C of a 78.7 C peak)` | 热限制，调频器仍在动 |
| `attr26-roundb` | `3072 MHz held for 150 s (5 of 13 windows), hottest 74.0 C in the first window, dropped at window 6 of 13 (4 changes, hottest 47.3 C of a 74.0 C peak)` | 负载没了：黑屏重启循环，没有东西要画 |
| `attr-speed3` | `3072 MHz held for 360 s (12 of 12 windows), hottest 71.7 C in the first window, still there in the last of 12 windows (peak 75.2 C)` | 上限全程没掉：`held` 等于窗口总数，行尾是 `still there in the last of N windows` 而不是 `dropped at window`，`changes_at_drop` 与 `hot_at_drop` 两项不存在 |

四条局限，报 `ff_s` 时一起写：

- 「冷机」不由 `ff_s` 本身证明。轮次是连续排的，设备可能带着上一轮的热起来。判冷机看第一个窗口的 `hottest`，`attr26-roundb` 的第一个窗口就已经是 74.0 °C，这一轮的 `ff_s` 不能读成「冷机维持了 150 秒」。
- `ff_s` 的上限是窗口覆盖的秒数，而窗口覆盖不满整轮。`attr-speed3` 的 `coverage:` 跨度是 419 秒、12 个窗口共 360 秒，`ff_s` 报 360，差的 59 秒落在第一个窗口之前与最后一个窗口之后。所以 `ff_s` 等于窗口总秒数时读作「窗口覆盖到的那段里上限没掉过」，读不成「整轮上限没掉过」。
- 窗口数按 `summary.py` 的 `merged_log()` 顺序计，不按 `round-stats.py` 的唯一行计。两个完全相同的直方图文本在唯一行口径下会合并成一条，在顺序口径下是两条；本轮 13 个窗口两种口径一致，不一致时以顺序口径为准并写明差异来源。
- 窗口文本里没有 `tl:` 时间戳，所以 `ff_s` 不能与帧时间轴直接对齐。要对齐就用相邻 `tl:` 行夹逼，并写明是夹逼区间。

### 9.3 round C 为什么不出这两个数

round C 是诊断轮，唯一变量是内核。它跑的作业脚本是 `rc.jobs.freeze`（含 90 秒等待加一次 250 ms 滑动），性能轮用的 `rc.jobs.perf` 本轮不跑；roundb 的形态是 99 帧、13 处帧号断裂、94 张截图全在黑屏档。所以本轮的 `ff_s` 与 `thermal:` 行照常报（每一轮都有这两个读数），而 9.1 的三个数不出：没有可测的下拉动画，`gestures.py` 会报样本不足。

本轮实测，两处与预期不同：

- `gestures.py` 的样本不足这一条成立，原文是 `swipe-left 1x: no animation to measure, each window held one frame -- a desktop with one page turns nothing, the swipe springs back`，覆盖 97 s、1 次 touch down、0 次控制中心下拉。97 s 占 418 s 跨度的 23%，不足一半，按协议 §5 它本身也只能当局部值。
- **`round-stats.py` 的 `frames` 段给的是 `usable as a performance baseline`**，因为本轮 3611 个帧号、1..3611、断裂 0，而那个印章只判帧号连续性。§1 那句「同一形态再来一次就沿用 `NOT A PERFORMANCE BASELINE`」的条件没有满足，本轮形态是冻结。所以这个印章读不成「本轮可当性能样本」：本轮有 8 个超过 1 s 的空档（首个 15.4 s），`gestures.py` 没有判定，`fps`／`fps_mv`／`static` 三列按用户 2026-10-28 的口径本来就不能跨轮次比。判断一轮能不能出性能数要看 9.1 那三个数有没有，不看这个印章。

### 9.4 装车的 AIR 库带着逐帧计时插桩，验收轮必须关掉

roundb 装车的 `libredwoodair.dylib`（`d7b9ced5a115c08c…`、13,983,936 字节）带逐帧计时插桩，round C 复用同一份产物，所以 round C 也带着。两级证据，第二级比第一级硬：

- 构建记录：`hackios-xnu-kernel/out/ios26-resume/mesa-arm64e/air-build-record.json` 的 `library_sha256` 是 `d7b9ced5a115c08ca17c23e7322a9505c2c6352b3c9660a0d51beece91102e5f`、`library_bytes` 13,983,936、`library` 指向 `out/ios26-resume/bbmetal-device/libredwoodair.dylib`，与 roundb 装车那份同一个 sha256；它的 `holds` 块里 `"perf draw: timing on": true`。
- 运行时：roundb 的日志里有 `perf draw: timing on, frames over 6000 us are printed, 128 frames per summary`，raw 866 条、唯一 1 条；`perf driver <N> us: <M> draws` 汇总行 raw 44 条；`perf driver worst:` raw 88 条、唯一 6 条。

插桩的量级从 26 线已提交的 `hackios-xnu-kernel/tools/mesa/draw-perf.patch`（700 行）读出来：时钟是 `mach_absolute_time() / 1000`，与内核 `tl:` 行用的同一个钟；每次 draw 记 8 个时间点（client 侧 `wait` 一个，driver 侧 `entry`、`track`、`prog`、`emit0`、`emit1`、`draw`、`exit` 七个）；每 128 帧一条汇总（`FD_PERF_WINDOW`）；每帧留最慢的 2 次 draw（`FD_PERF_WORST`）；慢帧阈值 `FD_PERF_SLOW_US 6000`。开销是每次 draw 8 次取钟加每帧簿记，外加每 128 帧一次打印。

**「存在」与「生效」要分两个方向核，两边都要写。** `holds` 记的是「库里有这个格式串」，读不成「它打过」：同一份记录里 `"perf flush totals"` 是 true，而 roundb 的日志里 `perf flush totals:` 是 0 条，`perf client ` 也是 0 条，这两部分编进去了而没触发。反方向同样要核：日志里出现一条打印就证明它生效，而格式串在库里存在不证明任何一轮打过它。所以报插桩状态时给两个数，一个是构建记录里的 `holds` 项，另一个是本轮日志里该族的 raw 与唯一行条数。

对验收口径的影响，三条：

- 用户的验收口径是还原安卓真机性能，出一份验收数的那一轮必须关掉插桩，否则那份数里含着每次 draw 8 次取钟与每 128 帧一次打印的成本。roundb 与 round C 都不出验收数（9.3），所以本轮不受影响，但下一个性能轮之前要先确认 AIR 库的构建关掉了 `perf draw`。
- 16.5 那条参照线不得携带插桩，规则在 `hackios-xnu-userland/tools/mesa/NOTE.md`：`tools/mesa/*.patch` 会被 16.5 的 `mk-mesa.sh` 用通配符自动收下，而所有性能对比都以 16.5 为参照。26 线有意携带、16.5 线不得携带，这是两条不同的规则，不要互相引用。
- 跨轮次比帧率时，插桩状态是必须一起报的一项。三列 fps／fps_mv／static 本来就不能跨轮次比（用户 2026-10-28 的口径），插桩开关又给跨轮比较加了一个变量。

那 44 条按阶段的汇总行是已有而没人用过的数据源，它给的是每帧成本的去向而不是帧间隔。样例一条：`perf driver 6956 us: 2 draws in 6955 us, tracking 0 prog 6950 emit 4 draw 0 us, max 6146 us, program calls 2 cache lookups 2`，即 2 次 draw 共 6955 µs 里 6950 µs 在 `prog`（program 准备与查找），`emit` 4 µs、`draw` 0 µs。读它归 task-16，本节只记它存在与它的口径。

## 10. round D 的三计数判读口径

前置条件：容器构建修好（task-7）、驱动侧重建、`tools/k90auto/library-baseline.json` 的两个哈希更新。在那之前这三个字段不存在于任何产物里，日志里读不到它们不构成结论（协议 §5：新增的日志行在它被编进去之前，缺席不构成结论）。

三个计数是 `rwa commit entry`（CA 进驱动提交入口）、`rwa kernel entry`（驱动进内核）、`tl: s`（内核侧交换交接），按 task-5 的描述合在同一行、每秒一条。读法：

- **计数值可用，行数只用来核覆盖。** 每秒一条是定时打印，计数值本身是累计量，不受 `RW_AGAIN` 一类节流影响。行数与「有提交的秒数」对得上才说明这一段没被环挤掉；对不上就只报行数覆盖到的那一段。这一族的量很小，420 秒约 420 行、约 40 KB。判它有没有被环挤掉要引 13.6 那一对实测值（环的字节上限与这一轮自己的日志速率），引一个固定的秒数会在别的轮次上失效。
- **判据是三者的比值。** `commit ≈ kernel ≈ tl: s` 是一次提交对应一次入内核对应一次上屏。`commit > kernel` 说明提交在驱动里被合并或被拒。`kernel > tl: s` 说明进了内核而没有交接上屏，落在排队或失败上。三个都不增长说明没有人发起提交，与 15 秒周期的 3 秒空洞同族。
- **窗口内的计数要有基率对照。** 判据写成空洞内与空洞外同长窗口的每秒计数之比，或空洞内出现空洞外没有的取值。只报「空洞内命中 N 条」不成立：`commit has run for` 那一类告警的基率约 3 条/秒，任何 3 秒窗口都会命中。
- **报累计量之前先除以次数。** 三个计数都是累计值时，先算每次提交的量，再算它占墙上时间的比例，与 [差距分析](2026-10-28-ios26-perf-gap.md) §2.20 处理外部 buffer 等待的方式相同。
- **口径按每秒一行分开写。** 一行里同时有三个计数时，报「唯一行条数」与「三个计数各自的末值减首值」，两者是不同的量：前者是覆盖，后者是事件数。

判据：

- 通过：三个计数的末值减首值都非零，且比值的形态能与本轮的停机段对上（有空档的时段三个计数都不增长）。
- 不通过：三个计数里有一个全程不增长，而另外两个增长。这说明那一段代码在这一轮的产物里没有被走到，先按「打点位置不可达」查，确认那一段在本轮产物里走得到之后，再谈事件有没有发生；`perf-draw-v4` 的 `sync`／`pass` 全为 0 是同一类。
- 无法判定：唯一行条数远小于有提交的秒数，说明环把这一段挤掉了，只报覆盖到的那一段。

## 11. 工具改动

`summary.py` 与 `gestures.py` 由 perf 维护，device 只运行。round C 之前那一批改了 `summary.py` 三处，`gestures.py` 未改；round C 收尾复跑时又查出两个缺陷，两个工具都改了，见 11.2。

### 11.1 round C 之前那一批：`summary.py` 三处

- 新增 `full_frequency()` 与 `thermal()`，`--verify` 末尾多打一行 `thermal:`，`--markdown` 与非 markdown 的行表格多一列 `ff_s`（在 `lowest_share` 之后、`shots` 之前）。定义与局限见 9.2。没有 domain 1 窗口时 `ff_s` 打 `-`，`thermal:` 打 `no cpufreq domain 1 window, the clock ceiling is unknown`。
- 新增 `log_files()`，`merged_log()` 与 `verify()` 都改成用它。改的原因是一处口径不一致：`merged_log()` 读 `s*.log` 加 `returned.log`／`hung-held.log`／`running.log`，而 `verify()` 的期望集合只从 `s*.log` 取，于是收尾时多拉的那一份里独有的行会被判成「合并结果里有、任何快照里都没有」。按协议 §4，`--verify` 返回非 0 时这一轮不计成功，所以这是一个会把好轮次判掉的缺陷。`hung-held-serial.log` 是串口控制台，与环不是同一个来源，两个口径都不读它。

  改动前后对全部 67 个已归档轮次逐轮跑了一遍 `verify()`，把两类坏行（计数不符与「任何文件里都没有」）加总比较，8 轮的判定从「不计成功」翻成通过：

  | 轮次 | 改动前坏行数 | 改动后 | 多出来的那一份 |
  |---|---|---|---|
  | `kernel-12377-attr-biomed` | 492 | 0 | `hung-held.log` |
  | `kernel-12377-attr-crashlog` | 496 | 0 | `hung-held.log` |
  | `kernel-12377-attr-linkd` | 490 | 0 | `hung-held.log` |
  | `kernel-12377-attr26-dasd` | 20 | 0 | `hung-held.log` |
  | `kernel-12377-attr26-persona` | 504 | 0 | `hung-held.log` |
  | `kernel-12377-attr26-persona2` | 23 | 0 | `hung-held.log` |
  | `kernel-12377-attr26-persona4` | 34 | 0 | `hung-held.log` |
  | `kernel-12377-attr26-probe-age` | 33 | 0 | `hung-held.log` |

  **已写进文档的结论没有一条因此需要更正。** 理由是 `merged_log()` 的行为一点没变（它本来就读那几份），所以帧数、帧率、行数、覆盖率这些数字一个都没动；变的只有 `--verify` 的通过与否。上面 8 轮在 `docs/` 里的引用都是引它们的内容（4099 计数、`nil buffer` 计数、persona 与扩展宿主分析），没有一处引它们的 `--verify` 判定，[差距分析](2026-10-28-ios26-perf-gap.md) §2.23 那句「八轮全部通过」说的是 `bbmetal17`～`25`，与这 8 轮没有交集。剩下 59 轮改动前后都是 0。

  仍有 1 轮报坏行，与本次修复无关：`kernel-12377-attr-speed3` 改动前后都是 2 条，形态是 `frame: merged 2x, snapshots 1x: tl: v 1 ready 1925021689 …` 与 `tl: v 2 …`，即合并结果里帧号 1 与 2 各出现两次而任何单份文件里只有一次。这两行的文本连时间戳都完全相同，所以是合并把同一段追加了两次，落在 `overlap()` 的锚定上（§1.1 记的那个函数），与文件集合无关。这一轮的其他数字不受影响（`windows 51/51`、`frames 6915/6915`、`coverage` 跨度 419 秒），但按协议 §4 它仍不计成功。修它要动 `overlap()`，那处刚按 §1.1 修过一轮，本轮不动，单独立一条。
- `tools/k90auto/test-tools.py` 的失败集合改动前后逐项相同（`failures=3, errors=8`，13 个用例），失败都在 `run-queue`／收尾那批夹具上，与 `summary.py` 无关。

`gestures.py` 在那一批里不改，两个原因：`CC_TARGET_FPS` 从 55 调到 60 是对用户明写的验收口径的等价改写，lead 已批准但要先向用户说明并确认（见 9.1）；`>25` 档与阈值一起改才有意义，分开改会让两轮之间的输出不可比。这两个阈值到 11.2 那批改动时仍未动。

### 11.2 round C 收尾复跑查出的两个缺陷

round C 收尾之后把两个工具在两轮上复跑，查出两处，都已修，`test-tools.py` 改动前后都是 3 failures／8 errors／13 用例，失败集合逐项相同，那 11 个都在 `run-queue` 与收尾那批夹具上，是既有 backlog。

**一、`crashes` 这一列数的是崩溃报告守护进程的名字，历史值全部偏小且与真实退出数反相关。** 原来的实现是 `len(re.findall(r'ReportCrash|Terminated due to|EXC_BAD_ACCESS|EXC_CRASH', text))`，`ReportCrash` 是守护进程名，每轮日志里都会出现，round C 那 7 次全部来自名字：LaunchDaemons 的目录列表一行、dyld 的 unnest 一行、`MiniAppleKeyStore` 的 selector 未实现一行、`lsprobe` 一行贡献 2 次。另外三个串在 roundb 与 round C 都是 0 次，崩溃报告内容从来没进过这些日志。

| 轮次 | 旧 `crashes` | 内核 `exited code` 唯一行 | 按进程分 |
|---|---|---|---|
| roundb | 6 | **30** | `backboardd` 15、`SpringBoard` 15 |
| round C | 7 | **0** | — |

30 次真实退出的那轮报 6，零退出的那轮报 7。改成数内核报的进程退出行，正则 `redwood: \S+ pid \d+ exited code -?\d+ reason \d+`，与 §3.5 和[归属复核](2026-10-28-roundb-memmove-attribution.md) §7 用的是同一个口径。`merged_log()` 已按重叠对接去重，roundb 上 `findall` 与 `set` 都是 30，不需要再套一层。改完 roundb 是 30、round C 是 0。`tools/k90auto/README.md:31` 那句「崩溃记录数」在新定义下才是它字面的意思，README 不在 perf 的 write scope，未改。

历史行的处理待 lead 裁：总账与差距分析里引过 `crashes` 的行值都变了，perf 没有改任何总账或历史文档。倾向标注旧值是当时工具的真实输出，而不是回填新值。

**二、两个工具传错目录层级时静默返回全零并退出码 0。** `summary.py` 要轮次目录（内部自己拼 `run`），`gestures.py` 要 `RUN_DIR/run`，`README.md:23-24` 分别记着两种写法。传错层级时两个工具都在空 glob 上继续跑：`gestures.py <轮次目录>` 打 `coverage: 0 s of frames, largest gap 0.0 s, 0 touch downs recognised`，`summary.py --verify <轮次目录>/run` 打 `windows 0 merged / 0 in snapshots; frames 0 merged / 0 in snapshots` 与 `coverage: no tl: line, the span is unknown`，两者退出码都是 0。perf 自己踩了这一处，拿轮次目录跑 `gestures.py` 得到 0 s 覆盖，与 device 回报的 97 s 对不上才发现是层级问题。

改法两处：`summary.py` 加 `round_dir()`、`gestures.py` 加 `run_dir()`，把两个层级都解析到同一个目录；解析之后仍找不到任何 `s[0-9]*.log` 时往 stderr 打一行并退出码 1。另外把 `gestures.py` 的 glob 从 `s*.log` 收紧成 `s[0-9]*.log`，与 `summary.py:79` 一致（`system-upload.log` 与快照并列放着，两轮都是 4751 字节、0 条 `tl:` 行，所以这个收紧今天不改变任何读数，属潜在问题）。

改完的验证：两个工具在两个层级上输出逐字相同，伪造路径退出码 1 并给出明确原因；roundb 与 round C 的 `--verify` 输出与改前逐字相同（13/13 与 99/99、16/16 与 3609/3609），退出码都是 0。

## 12. 待回填与待别人确认的项

已定的：

| 项 | 结论 |
|---|---|
| 验收阈值 55 → 60 与「掉槽帧数为 0」这条改写 | lead 批准，标成待用户确认之后才作为验收判定；`gestures.py` 的 `CC_TARGET_FPS` 与 `>25` 档在此之前不动 |
| round C 加崩溃报告收集 | 取消，task-4 revision 3。jobs 保持 `a4af9a9f1384fbac` 以维持「唯一变量是内核」，且第二类读数说明加了也拿不到内容 |
| `%#llx` 打 0 得到 `0` | display 确认，起止就是 `printf("%#llx-%#llx", start, end)`，未命中时 start/end 保持初值 0，实际打成 `0-0`。display 改产出文档、`kernel.json` 的 `new_prints` 段与 `sleh.c` 的注释（注释-only，镜像字节不变，`81f544688809a2e8…` 与 20,210,232 字节仍成立）。本文的判据按 `-` 拆两半各自 `int(x, 16)`，对两种形式都成立，不依赖前缀 |
| 反推用 `__TEXT` vmsize | display 接受，改记录文档 §2 并指向本文 §3.3 |
| 故障地址里两段 ASCII 字节的来源 | lead 的离线路径追到 backboardd 与 SpringBoard 里的串，本文复核后抄进 §5.1；共享缓存也已扫（`le.siri.` 1958 次、`cketTouc` 23 次），两个来源都在 `backboardd` 的地址空间里，光凭故障地址分不出是哪一个，本轮判不了 |
| 搜二进制字符串的命令 | lead 实测带上下文窗口的正则写法 CPU 差 79 倍，§5.1 改成 `-F` 固定串加 `dd`／`strings` 取上下文，原写法标成禁用；文件偏移按不含前导上下文的值写，vaddr 跟着重算 |
| 拷贝路径阈值 | 实测 65536（`redwoodmetal.m:2408` 的 `NOCOPY_LIMIT = 0x10000`），`redwoodmetal.m:2405` 注释里的 16 KiB 与交接文档 §2 沿用的说法都要改；roundb 的 `copied` 尺寸全部 ≤ 65536，「超过阈值仍被拷贝」不成立，P2 的结论不因它改变。见 §3.6。lead 已把交接文档 §2／§4 改成 65536 并注明来源，那处按事实错误更正处理，快照不改写的规则对它不适用 |
| roundb 的 bad access pc 归属 | 复核成立，在共享缓存的 `libsystem_platform.dylib` 的 `_platform_memmove` 里，镜像内 `+0x9c0` 与 `+0xad4`，不在我们的两个 dylib。slide 是 `0xbc54000`，交接文档 §3 的 `0xb05000` 与「超出共享缓存上界」都作废，两个 pc 的距离是 `0x114` 而非 `0x10c`。逐条复核见[归属复核](2026-10-28-roundb-memmove-attribution.md) |
| bad access 的事件数口径 | 邻接法可精确恢复，roundb 是 15 起，与该轮 `exited code` 的 15 代 backboardd pid 集合完全相同。§3.5 已改成三个口径并列，对齐与结论一律用 15 |
| `userland/obj/` 与本文引的产物 | display 核过：本次容器构建的写入只有 `obj/` 与 `hackios-xnu-kernel/userland/root/`，`out/ios26-resume/bbmetal-device/root/` 不由 `build.sh` 写，§3.3／§3.4 引的两个 sha256 不受影响 |
| exec 行的 `$6` 与 slide 的直接读法 | round C 实测：`tl: td 30 exec 0x100fb4000 SpringBoard`（首现 `s002.log:8919`）、`tl: td 38 exec 0x100c78000 backboardd`（`s002.log:8981`），两处 `$6` 正是主二进制，slide 行紧邻在前，双 pid 单值 `0x105a4000`。pc 减 exec 基址直接得主二进制内偏移，roundb 那种反推不再需要。`tl: td` 族自 `s002.log` 起每份快照都有，s002 是 78 条、s017 起 567 条封顶 |
| §8 的形态判据 | round C 按它归冻结形态，判据每一项都有读数支撑，见 13.1。这是 §8 在冻结形态上第一次跑通，此前只有 roundb 那个循环形态的样本 |
| §9.4 的插桩核对项 | round C 实测 `perf draw: timing on…` raw 100、唯一 1 条，装车 AIR 确为 `d7b9ced5`，本轮帧数据同样在插桩开着时采集。这条核对项同时验证了 AIR 身份 |
| bad access 的不节流计数器 | lead 撤销 task-9 第 1 项。邻接法已能精确恢复事件数（roundb 15 起）并与 `exited code` 的 15 代独立吻合，这个计数器只剩交叉验证价值，不值得为它单独重建内核 |
| round C 的实际读数 | 全轮 bad access 零条（raw 0、唯一行 0、物理事件 0，21 份 `s*.log` 与 `hung-held.log` 都零命中），形态归冻结，唯一变量是内核 `9a7a118a` 到 `cf1502f5`。四条收尾命令的原文见 13.4 |
| `summary.py --verify` 在 round C 上的首次实战 | perf 与 desktop 各自复跑，退出码 0、坏行 0，输出与 device 回报逐字相同：windows 16 merged / 16 in snapshots、frames 3609 merged / 3609 in snapshots。11.1 那处 `log_files()` 修复通过 |

待回填的：

| 项 | 需要谁 | 什么时候 |
|---|---|---|
| `$10` 是不是 `dyld_shared_cache_arm64e.NN` 这一类 subcache 名 | device 贴原文；3.2 第三行预测缓存内的 pc 会打出 subcache 文件名而不是 dylib 名，这一条是那个预测的直接检验。**round C 未获验证**：全轮 bad access 零条，没有 region 名读数 | 下一个有故障的轮次 |
| `region` 名取不到（B 类）在真机上的出现频率 | device 回报。**round C 未获验证**，同样因为零故障 | 下一个有故障的轮次 |
| §2 的四个新字段、§2.1 的三条自我否证判据、§3.7 的 `lr` 三步归属与页对齐反解 | 需要一个有 bad access 的轮次。round C 零故障，这四处都只有离线推导，状态见 13.2。「零故障」与「打印失败」分开写：本轮打印路径没有触发，格式串在镜像里、`strings` 也核过 | 下一个有故障的轮次 |
| roundb 的 `SpringBoard` 世代 pid 集合与交接文档差 3 个 | task-2 已完成，`backboardd` 一侧本文独立复核后与 15 起事件的 pid 集合完全相同；`SpringBoard` 一侧仍差 3 个，等 device 补 | device 补 `SpringBoard` 一侧之后 |
| `backboardd` 主二进制已剥符号，命中它时只有偏移 | lead 已定用 idalib 对着 `ios26/rootfs` 那份二进制分析 | 命中时 |
| 谁把非法的 `src` 传给 `memmove` | 归属复核 §6 已把候选缩到 AIR 库那 7 个 `_memmove` 调用点，判法是 §3.7 的页对齐反解；CA 侧是第二类候选。**round C 零故障，`lr` 没有读数**，这一步推到下一个有故障的轮次 | 下一个有故障的轮次 |
| 共享缓存起止的设备侧直接读数 | display，round D 候选。lead 已把 task-9 第 2 项保留但降级：离线一侧已经能从本地缓存算出三个边界数（见 §4），这条的价值在于设备侧不必依赖本地那份缓存与当轮 slide | round D 之前 |
| `crashes` 列的历史值要不要回溯标注 | lead 裁。roundb 6→30、round C 7→0，见 11.2；perf 没有改任何总账或历史文档 | lead 裁定之后 |
| `lsprobe` 的 `opendir` errno 与下探层数 | 归属由 lead 裁（不在 display 的 task-7 write scope 内），依赖 task-7 先修好容器构建 | round D 之前 |
| `kernel-12377-attr-speed3` 的 2 条坏行（`overlap()` 把同一段追加两次） | perf，单独立一条 | 下一次动 `summary.py` 时 |
| [差距分析](2026-10-28-ios26-perf-gap.md) §4.1 那张判据模板表仍写着「不低于 55」「每次不低于 55」，属用户已作废的那一套 | perf 改，lead 已裁归属；与 `gestures.py` 的阈值调整放在同一次改动里，避免两处判据不一致的时间窗拉长 | 用户确认阈值之后 |

引用与计数都要经过完整检索再落笔，这一节自己就有四个实例。

- 凭上下文印象写了一个不存在的锚点行。本文早先请 desktop 在总账「桌面只画出一半、诊断已排（10-28，当前焦点）」之后插入，docs/ 全库零命中，那一行是我按印象写的。
- 三个不同位置的成分被合成一行并配了一个错的行号。同一次请 desktop 改「总账第 16 行的性能验收判据（≥55／35 ms）」，desktop 三重检索（当前版、git 全历史 `-S`、三个规划文档）确认没有这一行。三个成分的实际位置：「超过 35 ms 的帧不超过 9 个」出自[总账](../plan/2026-10-23-tracking.md)第 98 行「性能验收口径（10-28）」，那一行引它是为了声明作废；「不低于 55」出自[差距分析](2026-10-28-ios26-perf-gap.md) §4.1 判据模板表的第 697 与 699 行；`CC_TARGET_FPS = 55` 出自 `tools/k90auto/gestures.py:26`，pass/fail 判据在 `:125`。
- 命中数被 `head` 截断之后当成全部命中。§5.1 里 `le.siri.` 在 SpringBoard 的命中数早先记成 4 处，来源是 `grep … | head -4` 的输出；用安全写法完整跑一遍是 22 处，`com.apple.siri.` 也是 22 处、偏移各小 7，这三条一起才把「全部落在内嵌 plist 的 `<string>` 里」这个定性立住。协议 §5 那条「以 0 作否定的结论必须写明统计覆盖范围」管的是零命中，截断输出作肯定结论是它的反面，同样要写明范围。
- 核实引用用的那条检索自己把宿主机打到 186 GB。命令是 `grep -rn '35 ms 的帧\|不超过 9 个' docs/ 2>/dev/null | head -5`，第二段没有 `--include`，递归扫了 `docs/` 下全部文件，包括 `docs/progress/evidence/` 里被 Git 忽略的轮次快照，那底下有单个 408 MB 的 git pack（内部几乎无换行）与 100 MB 一级的二进制。BSD grep 按行读入，遇到无换行长区间就一直扩行缓冲；`head -5` 没凑满 5 行一直在等，SIGPIPE 不会提前终止 grep。那次检索的目的正是核实上面两条不存在的引用，核实本身的代价高于它防住的错误。

由此三条规则，本文与后续每轮的报告都按它执行：引用一律给出文件加章节或行号，落笔前用检索确认它存在；报命中数或零命中时命令里不带 `head`／`tail` 一类截断，带了就写明截断到第几条；对 `docs/` 的递归检索必须带 `--include`，或显式排除 `docs/progress/evidence/` 与 `.git`，更省事的做法是用 `rg`（它默认吃 `.gitignore`，那些多 GB 二进制根本不进扫描范围，且内存有界）。`| head -N` 不能当内存保护，要限量用 `rg -m N` 或先缩小路径范围。

## 13. round C 的检验结果：哪些用上、哪些没用上

round C 已跑完，本文的判据第一次过了一轮实战。本轮读数来自 lead 2026-10-28 的通报；`summary.py --verify`、`gestures.py`、`reboot.json` 与 `round-stats.py` 三段的原文由 device 交给 desktop，本文向 desktop 索取，拿到后原样贴进 §12。

本轮的形态与 roundb 相反。roundb 是同 apfs、同 jobs 下的 15 代 `signal 11 code 11` 加黑屏循环；round C 归**冻结**形态，全轮 bad access 零条（raw 0、唯一行 0、物理事件 0，21 份 `s*.log` 与 `hung-held.log` 都零命中）。唯一变量是内核，`9a7a118a` 到 `cf1502f5`。

### 13.1 用上的三条，判据成立

| 判据 | 本轮读数 |
|---|---|
| §8 的形态判据 | 归冻结形态，判据每一项都有读数支撑：双进程 `exited code` 0 条、帧号 1..3611 零断裂、3611 次交换、空档 8 个（首个 15.4 s，其后 15 s 周期约 3 s）、末次交换后提交永久停止、framewatch `still no frames` 计到 297 s、101 张截图全 home screen、`bad_shots=0`、bbd pid 38 与 SB pid 30 全轮存活。§8 此前只有 roundb 那个循环形态的样本，这是它在冻结形态上第一次跑通 |
| §4 的 exec 行与 slide 直接读法 | `tl: td 30 exec 0x100fb4000 SpringBoard`、`tl: td 38 exec 0x100c78000 backboardd`，两处 `$6` 正是主二进制；slide 双 pid 单值 `0x105a4000`。用 `tl: td %d slide %#x` 直接读、pc 减 exec 基址得主二进制内偏移，这条本轮生效，roundb 那种反推不再需要 |
| §9.4 的插桩前提 | `perf draw: timing on…` raw 100、唯一 1 条，装车 AIR 确为 `d7b9ced5`。这一条同时验证了 AIR 身份，本轮帧数据同样在插桩开着时采集 |

### 13.2 没用上的四处，设计完成而未经设备验证

本轮零故障，bad access 行的 `lr`／`x0`／`x1`／`x2` 四个字段没有任何读数。以下四处因此**只有离线推导，没有设备侧验证**，引用时按这个状态读，不要当成跑通过的判据：

| 位置 | 内容 | 状态 |
|---|---|---|
| §2 字段表 | `$12` 到 `$19` 八个字段（四个字面量加四个值）、`NF` 是 19 的分流、`NF>19` 按字面量定位的恢复规则、`is_saved_state64` 那条四值同时为 0 的排除 | 设计完成，未经设备验证 |
| §2.1 | 三条自我否证判据（`$17` 等于 `$6`、`$19` 与 `$8` 的偏移对应、`$13` 不落在 `libredwoodmetal.dylib`） | 设计完成，未经设备验证 |
| §3.7 | `lr` 的三步归属（三类区间、bit 47 以上清零再试、停下不猜） | 设计完成，未经设备验证 |
| §3.7 的页对齐反解表 | 7 个 `_memmove` 调用点的预期 `lr` 与「只有一个候选能让差值页对齐」这一步，推导见[归属复核](2026-10-28-roundb-memmove-attribution.md) §6.4 | 设计完成，未经设备验证 |

§3.2 那条预测同样未获验证：「缓存内镜像的 `$10` 会打成 `dyld_shared_cache_arm64e.NN` 而不是 dylib 名」的依据是 dyld 按 subcache 文件 mmap，本轮零故障所以没有 region 名读数。它与 `region` 名取不到（B 类）的出现频率一起留在 §12 的待回填里，等有故障的轮次再验。

### 13.3 零命中怎么写才算成立：本轮的样板

§3.5 的三个口径本轮都是 0。按协议 §5，以 0 作否定的结论必须写明统计覆盖范围，本轮的覆盖数是：ring coverage 单份约 166 s、并集跨度 398 s、`coverage:` 行 418 s。418 s 大于轮次时长的一半，所以「本轮没有 bad access」按并集口径成立。

这个实例给出零命中结论的三段写法，后续每轮照用：

- 三个口径各自的 0（raw 0、唯一行 0、物理事件 0），并写明检索覆盖哪些文件（本轮是 21 份 `s*.log` 加 `hung-held.log`）。
- 覆盖数：单份 ring 覆盖、并集跨度、`coverage:` 行三个值都写，因为并集跨度与轮次时长的比决定这个 0 能不能当全轮结论。
- 覆盖不足一半时的降级写法：只报「该跨度内的局部值」并写明跨度，不下全轮结论。

「零故障」与「打印失败」是两回事，两种情形在 §12 里分开写。本轮四个新字段没有读数属于前者：打印路径没有触发，格式串在镜像里、`strings` 也核过。后者会是格式串没编进去或打印被节流，判法不同。

### 13.4 四条收尾命令的原文

device 收尾回报、desktop 原样转贴，perf 在宿主机对 `summary.py --verify` 与 `gestures.py` 各自复跑过，输出逐字相同。按协议 §5 原样贴，不做二次加工。

`python3 tools/k90auto/summary.py --verify docs/progress/evidence/k90auto/kernel-12377-attr26-roundc`，退出码 0，坏行 0：

```
kernel-12377-attr26-roundc: windows 16 merged / 16 in snapshots; frames 3609 merged / 3609 in snapshots
  coverage: tl: 12841497838 to 13259580616 us, span 418 s, largest gap between tl: lines 10.0 s, 3606 frames
  registration: 4 stuck judgement(s) on extensionkitservice, iconservicesagent, pkd -- the desktop's upstream degraded, so the rates describe only the part before
  thermal: 3072 MHz held for 390 s (13 of 13 windows, domain 1), hottest 72.1 C in the first window, still there in the last of 13 windows (peak 78.3 C)
```

`python3 tools/k90auto/gestures.py docs/progress/evidence/k90auto/kernel-12377-attr26-roundc/run`，退出码 0，`--each` 输出相同：

```
kernel-12377-attr26-roundc
  coverage: 97 s of frames, largest gap 15.4 s, 1 touch downs recognised, 0 of them Control Center pulls
  swipe-left   1x: no animation to measure, each window held one frame -- a desktop with one page turns nothing, the swipe springs back
```

覆盖 97 s 对跨度 418 s 是 23%，不足一半，按协议 §5 这个读数只能当局部值。它也没有判定：1 次 touch down、0 次控制中心下拉，`swipe-left` 那行的原因是桌面只有一页、滑动回弹，窗口里只有一帧。本轮没有手势口径的排序结果。

`reboot.json` 全文：

```json
{"off_seen": true, "mode": "android", "seconds": 21.218128541950136, "left": "hung-held", "reset": true, "failed": null, "samples": 21, "loader_build_id": "unknown", "window": "0x300000000", "payload_sha256": "ebdca4adfc9fb5f441a12489a7c5a0123e733b6f32582d8b606b389249a5b402", "system_sha256": "d11083be02820507f5639e0a29c6f35256a48d1d4f3cf4cd265eb4b8e346efe4", "status": null, "product": null}
```

`python3 tools/round-stats.py` 的三段，另附 device 报的 `frames` 与 `screens` 两段：

```
fence timeouts: 0 line(s) saying a command did not finish in time
ring coverage: 31849 lines over 398 s, 79 bytes per line / a 1024 KiB ring holds about 13268 lines, about 166 s of this round's logging / absence of a line proves nothing when that figure is below the snapshot interval (~20 s)
swap holes: 3611 swap handoffs, 8 hole(s) over 1 s: 1-6 s x7, 12-18 s x1（12844.4 s 起 15.4 s；随后 15 s 周期 3 s 上下；末次 12939.2 s 起 2.4 s）
frames: usable as a performance baseline（3611 个 id、1..3611、断裂 0）
screens: order: home screen x101；last shot is home screen at 419.0 s；bad_shots=0
```

`summary.py` 的行：

```
run=kernel-12377-attr26-roundc commit=5c9f563 args=cpus=2 gpu_log=1 cpufreq=1 fb_threads=2 seconds=420 panic=0 fps=45.6 fps_mv=59.9 static=24% driver_us=1928 gl_p50=0.0 gl_p90=0.0 under18=100% mid=0% long=0% long_count=4 hottest=78.3 lowest_share=23% ff_s=390 shots=101 bad_shots=0 crashes=7
```

`crashes=7` 是 11.2 那个缺陷的旧值，改成数内核报的进程退出行之后本轮是 0，与「双进程 `exited code` 0 条」一致。这一行其余各列不受那次改动影响。`long=0%` 与 `long_count=4` 并行不矛盾：`long` 是最长档帧数占全部帧数的百分比按 `{:.0f}%` 格式化，4 / 3606 是 0.11%，四舍五入到 0%。

### 13.5 帧数有三个值，各数各的

引用本轮帧数时写清是哪一个，三个值都不构成矛盾：

| 值 | 谁给的 | 数的是什么 |
|---|---|---|
| 3611 | `round-stats.py` 的 `swap holes` 与 `frames` 段；`gestures.py` 读的 `tl: v` 唯一行也是 3611 | 交换次数，以及帧号 1..3611 的 id 集合 |
| 3609 | `summary.py --verify` 的 `frames 3609 merged / 3609 in snapshots` | `FRAME_LINE` 这个正则在合并文本里的匹配数，merged 与 snapshots 两侧相等正是 verify 要判的那件事 |
| 3606 | `summary.py --verify` 的 `coverage:` 行 | 落在覆盖跨度内、带 `shown` 时间戳的帧 |

差的 2 与 3 来自三个正则各自的要求不同，本文没有逐条定位那几行差在哪，所以只报三个值与各自数的是什么。

### 13.6 环的覆盖：四个数各量各的，跨度不等于覆盖

日志环的容量是字节，折合多少秒取决于那一轮自己的日志速率，所以判据里不能写死一个秒数。下面四个值都在流传，它们量的东西不同，四个都对：

| 值 | 出处 | 量的是什么 |
|---|---|---|
| 166 s | `round-stats.py` 的 `ring coverage` 段 | 1 MiB 能装这一轮多少秒的日志。算法在 `:443-453`：`RING_BYTES / 每行平均字节 = 1048576 / 79.1 = 13263 行`，再除以并集的行速率 `31850 行 / 398.1 s = 80.0 行/s` |
| 395.2 s | display 从 round C 的 s020 实测 | s020 里 `tl: v … shown` 与 `tl: a` 两类时间戳的极差 |
| 398.1 s | `round-stats.py` 的 `span`；本文从 s020 单份用同一取法也量到 398.1 s | 任意 `tl:` 行里第一个 9 位以上数字的极差，正则是 `:443` 的 `^tl: .*?(\d{9,})` |
| 418.1 s | `summary.py --verify` 的 `coverage:` 行 | `merged_log()` 的跨度，输入是 `s[0-9]*.log` 加 `hung-held.log` |

395.2 与 398.1 的差在取哪个字段：`tl: v` 一行里有 `ready`、`shown`、`done` 三个时间戳，display 取 `shown`，`round-stats.py:443` 的正则取行里第一个 9 位以上数字，在 `tl: v` 行上那是 `ready`。418.1 比 398.1 多 20 s 在输入集合：`hung-held.log` 是收尾时多拉的一份，`merged_log()` 收它，`round-stats.py` 的 `read_lines()` 只收 `s[0-9]*.log`。

**跨度覆盖整轮推不出内容装着整轮。** round C 的 s020 单份跨度是 398.1 s，与 21 份并集相同，但它只有 16,453 行唯一行（并集 31,850 行）、11,331 个 `tl:` 时间戳（并集 21,906 个），并且有一个 51.4 s 的内部空洞（起于 12844.6 s）；并集的最大内部空洞是 10.0 s，那 51.4 s 由早先几份快照补回来。原因是 loader 日志的结构是固定的头加滚动的环：s000 的头三行是 `== XNULOADER run (usb) ==` 起、`tl:` 行 0 条，头把跨度的起点拉到开机，环把终点拉到本轮末尾，中间被挤掉的那段只在别的快照里。`merged_log()` 的重叠拼接就是为这件事存在的。以 0 作否定的结论要报字节数、跨度与最大内部空洞三个值，报跨度一个值会高估覆盖。

两轮的实测值，都按 `round-stats.py` 自己的算法：

| 轮次 | 并集唯一行 | 平均行长 | 单份快照字节 | 唯一行产生速率 | 1 MiB 折合 | 1,311,925 B 折合 | s020 跨度 | s020 最大内部空洞 |
|---|---|---|---|---|---|---|---|---|
| round C | 31,850 | 79.1 B | 1,311,925 | 6.18 KB/s | 166 s | 207 s | 398.1 s | 51.4 s |
| roundb | 13,534 | 140.7 B | 1,311,925 | 6.94 KB/s | 148 s | 185 s | 268.0 s | 80.2 s |

`round-stats.py:153` 的 `RING_BYTES = 1024 * 1024` 比实测的单份快照小 25%，所以它给出的折合秒数偏小；上表两个值都列出来，引用时写清用的是哪一个容量。原先判据里「环能装约 20 秒」这个说法在这两轮上都不成立（148 s 与 166 s），它来自 `tl:` 打印密度高得多的轮次。roundb 的平均行长是 round C 的 1.8 倍，因为它每条 bad access 带一段 region dump，同一容量折合的秒数因此更短，这条也说明折合秒数不能跨轮次沿用。
