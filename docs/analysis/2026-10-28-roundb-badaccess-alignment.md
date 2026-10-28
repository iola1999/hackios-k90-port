# 2026-10-28 roundb bad access 与进程死亡时刻对齐

对 roundb（证据目录 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundb/`，payload `ef3c82e1b58ea6db`，驱动 `9d66dd36` 拷贝路径版，内核 `9a7a118a1545`，已收尾）做纯离线对齐：把日志里全部 bad access 行与 backboardd／SpringBoard 的死亡时刻放到同一条时间线上。计数按单份快照内的行序与邻接关系（每份快照内每条物理行只出现一次）；时刻按协议 §5 口径在单份快照内用相邻 `tl:` 锚点行插值；21 份快照另做了一次拼接（零内容缺口），只用于覆盖完整性证明与交叉核对。脚本与完整输出归档在 `docs/progress/evidence/k90auto/analysis-roundb-badaccess/`（Git 忽略）。

## 1. 结论

bad access 物理事件共 **15 条**，与 15 次 backboardd 段错误 **1:1 对应**：在全部 21 份快照的每一份额内，每条 bad access 行的下一行都是同代 backboardd 的 `died on signal 11 code 11` 行，15 个死亡 pid 各自对应唯一的（故障地址, pc）组合，跨快照零冲突（校验方法见 §2，不依赖拼接）。任务文本说的「212 条」是跨快照求和的原始行数（本文复核 Σ各快照 = 212，与交接文档一致），同一段错误行文本按整行去重是 11 条；一条物理事件平均出现在约 14 份快照里，212 是 15 的快照重复放大。

关于「真实故障总次数在 11 与 212 之间、日志里恢复不出来」的口径：该区间适用于不带顺序信息的两种数法（整行去重丢掉不同时刻的同文本事件，跨快照求和按环重叠重复计数）。带顺序信息的数法可以恢复精确值——单份快照内每次故障只出现一次（环是顺序写入的单份缓冲），快照内每条 bad access 行都紧邻其死亡行，15 个死亡 pid 互不相同且 died 行集合与 exited 行集合完全相等，所以故障打印次数 = 段错误次数 = 15。恢复不出来的前提是「只拿两个汇总数、不拿行序」；行序在每份快照里都在。内核侧不节流计数器（round D 候选）对此只剩交叉验证价值：给出不依赖环覆盖与拼接的独立计数。

覆盖范围包含收尾抓取：s020 之后 loader 在判 hung 时又存了一份完整日志（`run/hung-held.log`，12,507 行），其内容延伸到 stop 泊车为止——framewatch 无帧计数继续到 151 秒（tl 1387.6）、battery/memory/buttons 打印正常、末尾是 `--- the host asked for the end of the run: back to the loader ---` 与 adreno8 泊车行、`== END OF LOG ==`。这份收尾抓取里 bad access 13 条与 s020 完全同集合（gen 3～15），其后零条新的 bad access／died／exited 行。15 次覆盖整个已抓取窗口，轮次末尾（约 151 秒无帧期）没有第 16 代 backboardd 出现或死亡。

三个问题的答案：

1. 每一对死亡之前 bad access 恰好 1 条，紧贴死亡时刻（相邻行、同一插值区间，亚秒级分辨不出先后）。其中 13 次（gen 3～15）故障行上方 2 行是一条 32,768 字节的 `rwa buffer: copied` 打印，拷贝打印与故障之间只隔一条 `tl: w` 出入口打点，打点窗口宽 246～468 µs，故障发生在拷贝完成后的亚毫秒尺度内。
2. bad access 只在死亡时刻出现。15 代 backboardd 每代恰好 1 条，稳定存活时段（SpringBoard 各代的 10～80 秒存活期）零条。它是致命故障本身（异常递交时的打印，随后进程被杀），不是可恢复的刷屏噪声。
3. pc 与代次强相关：`0x2b0fb5ad4` 只在 gen 1（开机首个 backboardd，pid 38，故障地址 `0x1`）出现 1 次；`0x2b0fb59c0` 覆盖 gen 2～15 全部 14 次。离线分析已把两个 pc 定到共享缓存里 `libsystem_platform.dylib` 的 `_platform_memmove`：`0x2b0fb59c0` = +0x9c0（`ldnp q2, q3, [x1]`）、`0x2b0fb5ad4` = +0xad4（`ldr x6, [x1], #8`），两处都是第一次源访问的指令，故障地址即调用方传给 `memmove` 的 `src` 实参本身（归属结论来自 lead 的离线分析）。round C 的判据相应改为取 `lr`(x30) 与 `x0/x1/x2`，见 §7。故障地址在少数几个垃圾值上循环：`0x80000c00000000` ×3、`0x80000c00010000` ×2、`0x21f80001xxxx` ×3、ASCII 串片段 ×4（`cketTouc` 为 `PocketTouchesExpected` 的 &str[2] 起 8 字节，`le.siri.` ×2 为 `com.apple.siri.` 的 &str[7] 起 8 字节，`le.media` 同形态，来源见 §3 分类表）、`0x10000`、`0x1`、`0x82b00c2a010000` 各 1。ASCII 值与拷贝路径的因果关系是假设，核对状态见 §7。

## 2. 口径与方法

- **计数主口径：单份快照内的邻接校验**（不依赖拼接）。对 21 份快照逐份检查：每条 bad access 行的下一行是否 backboardd 的 died 行；同一死亡行上方是否出现两条 bad access；同一 pid 在不同快照里的（地址, pc）是否一致。结果：212 条 raw 行全部有紧邻的死亡行，无一例外、无一对多、跨快照零冲突；15 个 pid 各对应唯一组合。匹配串全貌与位置：bad access 行首 `redwood: backboardd bad access at <地址> pc <pc>`；died 行首 `redwood: proc backboardd pid <N> died on signal 11 code 11`；exited 行首 `redwood: backboardd pid <N> exited code -1 reason 2`（注意与 died 行差一个 `proc `，两者都在行首）。iOS 日志行的进程标识是行中 `<时间戳> backboardd[<pid>:` 形态，与内核行的方括号形式 `redwoodmetal[backboardd <pid>]:` 又各不同，三套串不能混用。
- 计数三口径并列：raw（跨快照求和）212；唯一行文本（`round-stats.py` 的整行去重口径）11；物理事件（邻接校验/拼接时间线）15。15 − 4 = 11：四组事件的整行文本互相重复（`0x80000c00000000` ×3、`0x80000c00010000` ×2、`0x2e697269732e656c` ×2）。**对齐与结论一律用物理事件口径 15**，整行去重会把不同时刻的同文本事件并掉，不适合计数。
- **时刻口径：单份快照内插值**。每条 bad access 与其死亡行的时刻，在该事件首次出现的快照内、用同一份快照里的相邻锚点行按行号线性插值（协议 §5 口径：按 `tl:` 基线逐点，墙钟不直接相减）；对间隔（bbd 死 → sb 死等）取两条行共同出现的单份快照（s009 含 gen 1～13 全部死亡行，s014／s020 含 gen 3～15 全部死亡行）在同一份内计算。全部 15 个事件的单快照插值与拼接时间线插值一致；bad access 行到其死亡行的 tl 差为 +0.0008～+0.0644 秒（打印顺序上故障行总在死亡行上方 1 行）。
- 拼接时间线（只用于覆盖完整性证明与交叉核对，不作为计数或时刻的依据）：每份快照 = 固定 256 KB 头 + 1 MB 环，均为时序。头在 s002～s020 逐字节一致（sha256 相同），头含 3,406 行。相邻快照按「已拼接序列的尾部在下一份快照里的唯一精确匹配」接续（匹配长度从 20,000 行逐级降到 30 行，要求唯一），s000→s001 为前缀增长直接续接。结果 18,459 行、零内容缺口，即 21 份快照的环覆盖首尾相接，中间没有被覆盖掉而丢失的时段；单份环可容纳约 148 秒日志（`round-stats.py` ring coverage 段），远大于 20 秒快照间隔，环写满不会在两份快照之间掉行。逐份窗口核对：按每份快照的行数与头行数推出其环窗口在拼接坐标里的区间，15 个物理事件落在窗口内的预测集合与 21 份快照的实际 bad access 行全部吻合（21/21，含 s010～s013 环起点越过 gen 1/2 后的 12 条平台段）；各快照行数序列 3,5,7,9,11,12,13,13,12,12,12,12,13,13,13,13,13,13,13,13,13（s000/s001 为 0），Σ=212。
- 时间：两个独立时钟域并列报告，互不相减。墙钟域取 iOS 日志行首 `2026-10-28 HH:MM:SS.ffffff+0800`（8,724 个锚点）；tl 域取 `tl: …at <µs>`／`tl: v …done <µs>`／`tl: c …read <µs>`／`framewatch: …at <µs>`（981 个锚点）。无时间戳的行在两个域里各自用同域最近锚点按行号线性插值；末段无墙钟锚点处只报下界（标 ≥）。
- 实测两个时钟域速率比 ≈1.003:1（20 对相邻快照的 mtime 差 vs 末条 tl 值差，单对比值 0.95～1.10，含抓取抖动）。本轮墙钟与 tl 秒差主要来自末尾：iOS 侧打印止于墙钟 10:21:45.114，内核侧打印（framewatch/battery/cpufreq/buttons）又持续约 131 秒到轮次末快照。
- 数据质量注记一条：头部区域有一行环写入交错损坏的行（`2026-10-28 10:17:21.291840+0800 iconservicesag0x80000000 0 at 987392861`，iOS 行前半与 `tl: w` 行尾拼接），已从 tl 锚点排除，未影响拼接（拼接按整行精确匹配）。

## 3. 对齐表

死亡对 = 每次 backboardd 段错误（15 次，全部 11/11）与其后的 SpringBoard 死亡。墙钟为插值（gen 15 为下界）；「寿命」= 该代 backboardd 自己第一条 iOS 日志行到死亡的墙钟差；「拷贝行」= bad access 行上方最近一条 `rwa buffer: copied` 的字节数@行距；sb→下代 bbd = 本次 SpringBoard 死亡到下一代 backboardd 死亡的墙钟秒差。

| gen | bbd pid | pc | 故障地址 | 地址类型 | tl 秒 | 墙钟 | 寿命 s | 拷贝行 | sb 死亡(信号) | bbd→sb 秒 | sb→下代bbd 秒 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 38 | 0x2b0fb5ad4 | 0x1 | 小整数 | 988.503 | 10:17:37.726 | 18.54 | 65536@-18 | 30 (9/0) | +0.28 | −0.05（bbd84 先死于 sb30 被杀） |
| 2 | 84 | 0x2b0fb59c0 | 0x21f800010003 | 损坏指针值 | 989.493 | 10:17:37.960 | 0.12 | 60 行内无 | 30 (9/0) | +0.05 | +10.73 |
| 3 | 99 | 0x2b0fb59c0 | 0x63756f5474656b63 | ASCII `cketTouc` | 999.550 | 10:17:48.739 | 0.72 | 32768@-2 | 103 (9/0) | +10.15 | +0.43 |
| 4 | 124 | 0x2b0fb59c0 | 0x80000c00000000 | 损坏指针值 | 1010.092 | 10:17:59.318 | 0.45 | 32768@-2 | 131 (9/0) | +10.10 | +0.48 |
| 5 | 140 | 0x2b0fb59c0 | 0x80000c00000000 | 损坏指针值 | 1020.711 | 10:18:09.900 | 0.49 | 32768@-2 | 142 (9/0) | +10.10 | +0.25 |
| 6 | 153 | 0x2b0fb59c0 | 0x21f800010493 | 损坏指针值 | 1031.056 | 10:18:20.255 | 0.27 | 32768@-2 | 161 (**6/6**) | +0.02 | +10.85 |
| 7 | 167 | 0x2b0fb59c0 | 0x80000c00000000 | 损坏指针值 | 1041.811 | 10:18:31.131 | 0.79 | 32768@-2 | 175 (9/0) | +9.95 | +0.28 |
| 8 | 187 | 0x2b0fb59c0 | 0x80000c00010000 | 损坏指针值 | 1052.107 | 10:18:41.358 | 0.29 | 32768@-2 | 189 (9/0) | +10.08 | +0.97 |
| 9 | 197 | 0x2b0fb59c0 | 0x80000c00010000 | 损坏指针值 | 1063.129 | 10:18:52.405 | 0.99 | 32768@-2 | 205 (9/0) | +9.94 | +0.31 |
| 10 | 212 | 0x2b0fb59c0 | 0x2e697269732e656c | ASCII `le.siri.` | 1073.407 | 10:19:02.654 | 0.32 | 32768@-2 | 214 (9/0) | +10.08 | +0.91 |
| 11 | 221 | 0x2b0fb59c0 | 0x10000 | 小整数 | 1084.314 | 10:19:13.645 | 0.93 | 32768@-2 | 228 (9/0) | +9.95 | +0.60 |
| 12 | 235 | 0x2b0fb59c0 | 0x21f80001083f | 损坏指针值 | 1094.936 | 10:19:24.191 | 0.62 | 32768@-2 | 241 (9/0) | +19.97 | +0.31 |
| 13 | 243 | 0x2b0fb59c0 | 0x616964656d2e656c | ASCII `le.media` | 1115.247 | 10:19:44.468 | 0.32 | 32768@-2 | 246 (9/0) | +40.00 | +0.41 |
| 14 | 257 | 0x2b0fb59c0 | 0x2e697269732e656c | ASCII `le.siri.` | 1155.624 | 10:20:24.880 | 0.43 | 32768@-2 | 260 (9/0) | +80.03 | +0.21 |
| 15 | 265 | 0x2b0fb59c0 | 0x82b00c2a010000 | 损坏指针值 | 1235.969 | ≥10:21:45.114 | 0.23 | 32768@-2 | 无（sb267 轮末存活） | — | — |

ASCII 类是小端还原出可打印字节的取值；「损坏指针值」指其余既非小整数、又无 ASCII 还原、也不符合本轮所见合法堆地址形态（`0x1xxxxxxxx`，如拷贝行里的 0x10451c000/0x102848000）的取值，11 个值里没有落在合法堆地址形态的。

15 个物理事件的整行文本去重后是 11 个取值，这是本轮日志能给出的最细地址粒度，逐个分类如下（事件数 = 该取值对应的物理故障次数；来源列为 lead 在宿主机按字节序列搜二进制所得，匹配串为行中任意位置的字节序列）：

| 取值 | 事件数 | gen | 类型 | 说明与来源 |
|---|---|---|---|---|
| 0x1 | 1 | 1 | 小整数 | pc 也是唯一的 0x2b0fb5ad4 |
| 0x21f800010003 | 1 | 2 | 损坏指针值 | 与下两个共享 0x21f800010 前缀、低 12 位变化（003/493/83f），形如结构化数据被当指针 |
| 0x63756f5474656b63 | 1 | 3 | ASCII `cketTouc` | `PocketTouchesExpected`／`pocketTouchesExpected` 的 `&str[2]` 起 8 字节；`ios26/rootfs/usr/libexec/backboardd` 命中三处：文件偏移 908993 在 `__TEXT/__objc_methname`（vaddr 0x1000ddec1）、938370 与 958004 在 `__TEXT/__cstring`（vaddr 0x1000e5182、0x1000e9e34） |
| 0x80000c00000000 | 3 | 4,5,7 | 损坏指针值 | 0x0080000c00000000 形态，与 0x80000c00010000、0x82b00c2a010000 同族（含常量字节 0c、低位大段为零） |
| 0x21f800010493 | 1 | 6 | 损坏指针值 | 同 0x21f8 前缀族 |
| 0x80000c00010000 | 2 | 8,9 | 损坏指针值 | 与 0x80000c00000000 仅差 bit16 |
| 0x2e697269732e656c | 2 | 10,14 | ASCII `le.siri.` | `com.apple.siri.` 的 `&str[7]` 起 8 字节；backboardd 主二进制零命中，仅 `SpringBoard` 内嵌 plist 字符串命中四处（偏移 40438、72051、72944、77769）。**零命中范围不含 dyld 共享缓存**：来源搜索没有覆盖缓存，缓存文件本地在 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/`（85 个文件、约 4.9 GB），backboardd 地址空间含共享缓存；如需补搜，按显式路径用 `strings`/`grep -F`，不对镜像本体做带上下文正则的 `grep -a` |
| 0x10000 | 1 | 11 | 小整数 | 65,536，与驱动 `NOCOPY_LIMIT` 同值；巧合记录，不作推断 |
| 0x21f80001083f | 1 | 12 | 损坏指针值 | 同 0x21f8 前缀族 |
| 0x616964656d2e656c | 1 | 13 | ASCII `le.media` | 形态与 `le.siri.` 相同（某个 `com.apple.media…` 串 &str[7] 起 8 字节）；具体来源二进制未核，lead 的来源搜索只覆盖上两个 ASCII 值 |
| 0x82b00c2a010000 | 1 | 15 | 损坏指针值 | 0x0082b00c2a010000，与 0x80000c 族形态相近 |

每条 bad access 的原始文本首次出现的快照：gen 1～3 为 s002，gen 4～5 为 s003，gen 6～7 为 s004，gen 8～9 为 s005，gen 10～11 为 s006，gen 12 为 s007，gen 13 为 s008，gen 14 为 s010，gen 15 为 s014；引用单条行时以这些快照为准（本表时刻即在各自首次出现快照内插值）。

gen 1～15 的死亡行原文样式（以 gen 3 为例，s002 起各快照均含）：

```
tl: w 32 0x80000001 0 at 999516708
redwoodmetal[backboardd 99]: rwa buffer: copied 0x10451c000 of 32768 bytes, buffer at 0x102848000
tl: w 32 0x80000000 0 at 999517102
redwood: backboardd bad access at 0x63756f5474656b63 pc 0x2b0fb59c0
redwood: proc backboardd pid 99 died on signal 11 code 11
redwood: backboardd pid 99 exited code -1 reason 2
```

`tl: w` 是帧缓冲用户客户端调用的出入口打点（`out/xnu12377/iokit/Kernel/MiniIOMobileFramebuffer.cpp:1325`），说明故障发生在一次 MobileFramebuffer 调用窗口内。

## 4. 死亡对的周期结构

稳态周期（gen 3～11）：SpringBoard 被杀（9/0）→ 下一代 backboardd 与 SpringBoard 几乎同时起（下代 backboardd 首条日志在 SpringBoard 死亡行前后 0.3 秒内）→ 新 backboardd 在 0.23～0.99 秒内段错误 → 新 SpringBoard 在无 backboardd 的状态下存活 9.94～10.15 秒后被 SIGKILL → 重复。周期约 10.6 秒。

后段拉长发生在「backboardd 段错误 → SpringBoard 被杀」这一段：19.97 秒（gen 12）、40.00 秒（gen 13）、80.03 秒（gen 14），逐代翻倍。SpringBoard 被杀后下一代 backboardd 的段错误间隔保持 0.21～0.41 秒不变。按翻倍规律，sb267 一代应在 160 秒后被杀，轮次在约 131 秒无帧时结束，没有等到。

三处偏离稳态的段：

- 开局（gen 1～2）：开机首个 backboardd（pid 38）存活 18.54 秒、画到帧 20（`tl: v 20 … done 988501507`）后段错误（pc `0x2b0fb5ad4`、地址 `0x1`，其上方 18 行有一条 65,536 字节拷贝打印）；重启的 pid 84 只活 0.12 秒、死前最后三行是渲染管线构建打印（`render pipelines: 2 built`、`pipeline seen: 0x101f65000 attachment 1125x2436`），60 行内没有拷贝打印；sb30 在 bbd84 死后 0.05 秒被杀。
- gen 6：sb161 死于 6/6（SIGABRT）而非 9/0，在 bbd153 死后 0.02 秒，abort 前的异常行原文（s004 起各快照）：`*** Terminating app due to uncaught exception 'NSInternalInconsistencyException', reason: 'Failed to create remote render context'`。这是 SpringBoard 因拿不到渲染上下文（backboardd 已死）而自行中止的直接记录。
- 另有两次 SpringBoard 死亡不在上表的对里：sb91（9/0，10:17:48.066，sb30 被杀后 10.06 秒）与 sb166（9/0，10:18:30.363，sb161 中止后 10.08 秒）。计入后 SpringBoard 死亡共 15 次：9/0 ×14、6/6 ×1，pid 依次为 30、91、103、131、142、161、166、175、189、205、214、228、241、246、260。

### 4.1 sb161：唯一自行中止的一代（6/6）

sb161 是 15 代 SpringBoard 里唯一死于自身 abort 的一代（died 行 6/6、exited reason 2；其余 14 代都是 9/0、reason 15）。它在全部 21 份快照与 `hung-held.log` 里没有任何 `SpringBoard[161:` 形态的 iOS 日志行（raw 计数 0），它在日志里的全部存在就是下面这个 console 中止块，五行都没有墙钟前缀（s004 idx 9795～9799，紧跟 bbd153 的 exited 行）：

```
*** Terminating app due to uncaught exception 'NSInternalInconsistencyException', reason: 'Failed to create remote render context'
*** First throw call stack:
(0x18f2502d4 0x18bd1d224 0x18cd816c0 0x195b1138c 0x194eccc54 0x194eccb24 0x194e13728 0x194eb8c70 0x194eb8a0c 0x195449c80 0x194eb8470 0x194ec85cc 0x1963ab330 0x195eb1068 0x2306649d8 0x23076d1e8 0x23076d134 0x1c9c7c1e4 0x1c9c655b0 0x22ffcdbe4 0x2306fb45c 0x2306a2d0c 0x2300cfa14 0x2300c50c0 0x194ea4420 0x194ea375c 0x194e9ee40 0x194e9e534 0x194ea0618 0x194e9d64c 0x194e08158 0x230035498 0x18bd75c1c)
libc++abi: terminating due to uncaught exception of type NSException
userabort: SpringBoard[161] aborts, shared cache slide 0xbc54000; called from: 0x19ad2efcc 0x18be1efd4 0x18be20b90 0x18bd1f868 0x18be2b1f8 0x18be2ce18 0x18be19360 0x18bd1d38c 0x18cd816c0 0x195b1138c 0x194eccc54 0x194eccb24 0x194e13728 0x194eb8c70 0x194eb8a0c 0x195449c80 0x194eb8470 0x194ec85cc 0x1963ab330 0x195eb1068 0x2306649d8 0x23076d1e8 0x23076d134 0x1c9c7c1e4
```

随后是 `redwood: proc SpringBoard pid 161 died on signal 6 code 6` 与 `redwood: SpringBoard pid 161 exited code -1 reason 2`（s004 idx 9800～9801）。时刻：中止块夹在 bbd153 的死亡三行（墙钟锚点 10:18:20.238253，died 行插值 10:18:20.255）与其下方 chronod 行 10:18:20.285826 之间，died 行墙钟插值 10:18:20.279、tl 插值 1031.135。

与前后两代的间隔（墙钟插值）：sb142 被杀（10:18:20.001，9/0）→ +0.254 秒 bbd153 段错误（10:18:20.255）→ +0.024 秒 sb161 中止（10:18:20.279）→ +10.084 秒 sb166 被杀（10:18:30.363，9/0）→ +0.768 秒 bbd167 段错误（10:18:31.131）。以 bbd153 死亡为锚，sb166 被杀在 +10.108 秒，与稳态的约 10 秒一致：10 秒计时锚在 backboardd 死亡上，sb161 的中止没有重置它。bbd167 的首条日志（10:18:30.343734，`starting /usr/libexec/backboardd...`）比 sb166 的死亡行早 19 毫秒，与稳态里「sb 被杀前后下一代 bbd 已在起」的形态相同。sb166 与 sb161 一样没有任何 iOS 日志行，从起到被杀约 10 秒全程无日志。

异常原因 `Failed to create remote render context` 指向渲染服务器连接建立失败；sb161 的中止发生在 bbd153 死后 24 毫秒，时间上与连接对端刚死一致（机制为推断，日志只给出时序）。中止块自带的 `shared cache slide 0xbc54000` 与两份共享缓存 VA 栈（first throw 与 called from）是后续离线命名调用方的原料。abort 行下方 2 行的 `framewatch: resumed at 1031169313 after 9 s` 是 §5 所述 resumed 误读的又一例。

## 5. 轮次末段状态

gen 15（bbd265）死于墙钟 ≥10:21:45.114（该行下方已无墙钟锚点，取下界；其上方 2 行是 bbd265 自己 10:21:45.113601 的 iOS 日志）。这是最后一次交换（`tl: s` 末条 tl 1235.9）之后的时刻，此后整轮再无帧。sb267 起来后没有任何 iOS 日志行；framewatch 的周期 dump 对它要了三次线程转储：tl 1238.4 时 8 个线程，dump 14/15 时都只剩 4 个线程（对照：sb260 的 dump 是 21 个线程）。内核侧打印持续到最后一份快照 s020（末行 `framewatch: still no frames, 130 s at 1366540835`），收尾抓取 `hung-held.log` 又把它延长了 21 秒：framewatch 计到 151 秒（tl 1387.6，与「末次交换 tl 1235.9 → tl 1387.6」的差一致），battery/memory/buttons 打印节奏正常，随后是 stop 标记行、adreno8 泊车行与 `== END OF LOG ==`；收尾走正常 stop→hung-held→复位路径（`reboot.json`: `left=hung-held, reset=true`）。即内核没有提前静默，日志终止于主机主动收尾；静默的是 iOS 用户态（backboardd 不再重启、sb267 无日志无帧，收尾抓取里也没有第 16 代 backboardd 的任何行）。

后段「bbd 死 → sb 被杀」间隔逐代翻倍（10→20→40→80 秒）与 sb267 未死于日志内自洽：按翻倍规律 sb267 应在 bbd265 死后约 160 秒被杀，落在 tl ≈1396，而日志止于 tl 1387.6，差约 8 秒没有等到。翻倍的机制（launchd 对反复崩溃任务的退避，或 SpringBoard 侧等待超时逐代加长）本轮日志判不了，留给 P5。

gen 15 死亡行后紧跟的 `framewatch: resumed at 1236048399 after 79 s`（s014 起各快照）再次确认交接文档对 framewatch 「resumed」的定性：新进程起来后帧计数从 0 重计造成的误读，其后到轮末再无任何帧。

## 6. 对交接文档与任务文本的更正

1. 拷贝阈值（已闭合）：交接文档 §2 写「≤16 KiB 拷贝并托管 deallocator」，perf 复核确认该数沿用了 `hackios-xnu-kernel/userland/src/redwoodmetal.m:2405` 注释里的错数，注释与常量差 4 倍；实际阈值是 `:2408` 的源码常量 `enum { NOCOPY_LIMIT = 0x10000 }` = 65,536 字节（本文直接读源码同值）。roundb 的 `rwa buffer: copied` 唯一行分布 32768→94、15360→5、62464→5、16384→4、65536→1，合计 109，全部不超过 65,536，最大一条正好等于阈值，与本文拼接时间线的物理口径 109 条一致；「超过阈值仍被拷贝」不成立。唯一 1 条 nil 是 1.3 MB 超限，按设计返回。计数口径注记：交接文档 §2 的 copied raw 1,775 条（32768 占 1,579）是加了 `hung-held.log` 的口径；`round-stats.py` 只读 `s*.log`，同轮为 1,675 条（32768 占 1,487），差 100 条。按 `round-stats.py` 报数用后者，引用交接文档数字时注明口径差异。
2. bad access 计数口径：「212 条」为跨快照求和；物理事件 15 条、唯一行文本 11 条。交接文档的 pc 分布（204/8）同为 raw 口径，物理口径为 `0x2b0fb59c0` ×14、`0x2b0fb5ad4` ×1。
3. SpringBoard 世代 pid 集合：交接文档 §2 记 14 代（含 267、无 91 与 166），与日志不符。本文按唯一行口径实读两种行、集合完全一致，均为 15 代死亡 `{30, 91, 103, 131, 142, 161, 166, 175, 189, 205, 214, 228, 241, 246, 260}`：died 行首 `redwood: proc SpringBoard pid <N> died on signal <S> code <C>`（14 代 9/0、pid 161 一代 6/6），exited 行首 `redwood: SpringBoard pid <N> exited code -1 reason <R>`（14 代 reason 15、pid 161 一代 reason 2）。两串都在行首、相差一个 `proc ` 前缀；iOS 日志行的进程标识是行中 `SpringBoard[<pid>:` 形态，与 `redwoodmetal[SpringBoard <pid>]:` 也不同，三套串不能混用。perf 按 exited 唯一行的实读结果与此一致。267 不在死亡集合里：它的出处是 framewatch 的 dump 请求行（`asked for SpringBoard pid 267`）与内核转储行（`tl: td pid 267 threads 8`／`printed 4`），都是行中匹配，说明它被拉起过且轮末存活。backboardd 侧 15 代 `{38, 84, 99, 124, 140, 153, 167, 187, 197, 212, 221, 235, 243, 257, 265}` 全部 11/11、exited 全部 reason 2，与交接文档一致。交接文档按时点快照不改写，本条即承载更正结论。
4. 死亡对的先后与间隔：交接文档 §2 写「backboardd 先死 11/11，0.2～0.7 秒后 SpringBoard 死 9/0，每对间隔约 10 秒，后段拉长到 20/40/80 秒」。实测稳态是 backboardd 段错误后约 10 秒（后段 20/40/80 秒）SpringBoard 才被杀；0.2～0.97 秒对应的是「SpringBoard 被杀 → 下一代 backboardd 段错误」的间隔。两个间隔的归属需要对调。
5. 任务文本的「17 对」：实测 backboardd 段错误 15 次、SpringBoard 死亡 15 次（含 1 次 6/6），按 backboardd 死亡计的对为 15 对。17 的来源在数据里找不到对应。

## 7. 对 P2（拷贝路径去留）的输入

- 时间耦合（实测事实）：15 次致命故障里 13 次发生在一条 32,768 字节 `rwa buffer: copied` 打印后 ≤0.5 ms（`tl: w` 打点窗口 246～468 µs 内），gen 1 的 65,536 字节拷贝在同帧窗口内上方 18 行。「32,768 与 ≤16 KiB 设计对不上」的疑问已闭合：perf 复核确认阈值是源码常量 65,536（§6 第 1 条），32,768 字节的拷贝符合设计。ASCII 类故障地址与拷贝路径的因果关系仍是**假设**：可能是拷贝路径引入的缺陷，也可能是同一次绘制里先后两步、或拷贝让 CA 走过了原先 nil 失败的点。P1 的 region 归属已由离线分析回答（pc 在系统库 `_platform_memmove`，见 §1 结论 3），display 的源码侧核对结论到齐之前不下定论。
- gen 2 例外：死前是管线构建打印（`render pipelines: 2 built`、`pipeline seen: 0x101f65000 attachment 1125x2436`），60 行内无拷贝行，说明 `0x2b0fb59c0` 这个故障点也可以在不邻接拷贝打印的路径上触发，或该次拷贝的打印被节流。`rwa buffer: copied` 是否节流影响「无拷贝行」的解读，判 P2 前建议 display 从源码确认这条打印有无 RW_AGAIN 类节流（协议 §5 只把 `tl: p` 与 `no-copy served as a copy` 明确记为节流打印）。
- 故障地址形态（形态学观察，非结论）：ASCII 片段 3 个取值（`cketTouc`、`le.siri.`、`le.media`）与小整数 2 个取值（`0x1`、`0x10000`）占 11 个取值中的 5 个，其余 6 个是两组结构化损坏值（0x21f800010 前缀族 ×3、含常量字节 0c 的 0x…0c…0000 族 ×3），没有一个符合本轮合法堆地址形态。pc 归属确定后，这些值的身份收窄为「调用方传给 `memmove` 的 `src` 实参」：调用方从某个字段读出的指针本身就是垃圾值，「读到被释放或被复用的内存里的指针再拿去拷贝」是与形态相容的候选解释，调用方是谁等 round C 的 `lr` 命名。
- round C 新判据（等带 `lr`(x30) 与 `x0/x1/x2` 打印的新内核）：`x1` 应等于同行打出的故障地址（`src` 实参的现场交叉验证）；`x2` 是长度，用来核对离线推出的指令区间（+0x9c0 要求 64 ≤ len < 16384，+0xad4 要求 len < 64）；`lr` 落在共享缓存里就能用离线方法（imagesText 加 export trie）直接命名调用方，不需要 dSYM。一条由两个给定事实推出的观察：13 次拷贝相邻的故障都在 +0x9c0，而相邻 rwa 拷贝是 32,768 字节、不在 [64, 16384) 区间内——若区间推导成立，故障的那次 `memmove` 调用与打出 `copied` 的那次 rwa 拷贝大概率不是同一次调用，等 round C 的 `x2` 现场确认。
- SpringBoard 侧无 bad access：本轮打印限定内 SpringBoard 零故障行，它的 15 次死亡全部是 SIGKILL/SIGABRT（后果侧），故障集中在 backboardd。
- 故障时刻在生命周期里的位置：gen 2～15 的 backboardd 从自己第一条 iOS 日志行到死亡只有 0.12～0.99 秒，故障发生在启动早期；gen 1（开机首个实例）活 18.54 秒、完成约 20 次交换后才故障。修复验证时「新 backboardd 能否活过第一秒」是最快的判据。
