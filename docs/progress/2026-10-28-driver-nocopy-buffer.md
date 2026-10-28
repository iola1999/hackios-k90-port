# 驱动 no-copy buffer 改动与回退（2026-10-28）

驱动在 `newBufferWithBytesNoCopy:length:options:deallocator:` 上原来无条件返回 nil，`backboardd` 里会出现 `[Metal] nil buffer from memory`，紧接着是 SIGABRT。这一页记录 2026-10-28 尝试改为复制一份的三版实现、各轮读数、以及回到返回 nil 的决定。**先看第一节的表：改动的代价大于收益，这条线已挂起。**

## 1. 结论：改动的代价大于收益

数字全部取自 `tools/round-stats.py`（整目录去重后的行数，`died on signal` 按信号与码分组）。改动前那一轮在表里，否则看不出改动是做成了还是做坏了。

| 轮次 | 驱动 | 帧 id | 最长空洞 | `11/11` | `9/0` | `nil buffer` | `pipeline` | `served as a copy` |
|---|---|---|---|---|---|---|---|---|
| `dasd`（改动前） | `f2627aa5` | **7,600** | 59.2 s | **0** | 49 | 68 | 2 | 0 |
| `driver1` | `bef13a3` | 3,626 | 80.4 s | 14 | 114 | 0 | 2 | 20 |
| `driver2` | `92d383b` | 49（`[!PERF]`） | 41.5 s | 19 | 115 | 0 | 0 | 19 |
| `driver3` | `759d45e` | 44（`[!PERF]`） | 140.7 s | 15 | 118 | 0 | 0 | 20 |
| `badaccess` | `5dd23f55` | 97（`[!PERF]`） | 51.3 s | 15 | 120 | 0 | 0 | 22 |
| `driver-revert` | `57281c79`（诊断行无条件编入） | **7,818**（可作性能基线） | 59.2 s | **0** | 54 | 70 | 2 | 0 |
| `airindex`（AIR 修好后） | `31f2d6b7` + AIR `d7b9ced5` | 3,550（可作性能基线） | 18.1 s | **0** | **0** | 21 | **0** | 0 |

- 收益只有一项：`Metal failed to build render pipeline` 从 2 条变 0（`driver2` 之后）。
- 代价三项：帧 id 从 7,600 掉到 3,626、49、44、97，后四轮全部被 `round-stats.py` 标成 `[!PERF]`；`signal 11 code 11` 从 **0** 变 14 到 19，**段错误是这一改动引入的**；`signal 9 code 0` 从 49 涨到 114 到 120。
- `badaccess` 轮驱动是 `759d45e` 加一行加载基址打印（`6b4ee59`），行为不变，所以计入改动后的那一组。

**`gestures` 轮 94 张截图整轮逐字节相同**：`shasum -a 256 run/shot-*.raw` 的 94 条只有一个哈希（`313e03d2…`），`round-stats.py` 的 `screens` 一节同样给 `order: home screen x94`。当时转述的「39 张相同」是某个窗口的数，不是整轮。

`airindex` 轮的 manifest 里 `pack.air_sources` 是空的：那一轮打包用的是加这个字段之前的 `package.py`（`4011a07` 在它之后）。所以那轮没有留下 `air_to_nir.c` 的摘要，`air_to_nir.c` 为 `35b6f62e` 这一点由 `air_sha256=d7b9ced5` 与产物里 `insertelement at a run-time index` 计数为 0 间接确认。下一轮起 `air_sources` 会有六条。**不要把「没记录」读成「没验证」。**

**`airindex` 那一行是主屏画出来的一轮**：AIR 库支持运行时下标的 `insertelement` 之后，`this render pipeline is refused` 0、`Metal failed to build render pipeline` 0、`signal 6 code 4` 0、`signal 9 code 0` 0，帧 3,550 且 id gaps 0，截图是主屏。**桌面停在锁屏之后的原因就是这一处着色器编译器能力缺口。**

**两个驱动版本对 `driver code at` 的处理不同**：`57281c79` 把那一行**无条件编入**，所以 `driver-revert` 轮的日志里有它；`31f2d6b7` 起由 `REDWOOD_DIAG` 控制，开关不设时日志里没有。看到某一轮有或没有这一行，先看 `pack.redwood_diag` 与驱动哈希，再下判断。

**`driver-revert` 那一行是驱动线关闭后的基线轮次**：驱动 `57281c79`（回退 + 一行加载基址打印），`round-stats.py` 标为 `usable as a performance baseline`，`11/11` 归零、帧 7,818 回到改动前量级（7,600）、`nil buffer` 70、`6/4` 1 条。后面看性能用这一轮。

**决定：退回返回 nil。** 相关提交：一进（`bef13a3`、`92d383b`、`759d45e`）一退（`90c3df0`「恢复无拷贝缓冲区返回 nil」），没有反向提交链。回退后打包重现的驱动哈希是 `f2627aa5`，与改动前一致。

早先几份读数（`11/11` 5 条、`9/0` 103 条等）是 375 秒附近快照的数，整目录去重后是上表的值。差别在统计口径。

## 2. 三版实现各错在哪

- `bef13a3`「复制后立刻调用 deallocator」：复制完成后立刻调用调用方传入的 `deallocator`，释放了调用方还在用的内存。`backboardd` 每 10 秒 `signal 11 code 11` 一次（06:55:57、06:56:07、06:56:18、06:56:27、06:56:38）。
- `92d383b`「把释放挪到 buffer 销毁时」：`bytes`／`length`／`deallocator` 存在 buffer 上，在 `-dealloc` 里调用。时机对了，但存的是调用方传入的 block 原指针，CA 传的常是内联栈 block，销毁时那块栈已作废。
- `759d45e`「deallocator 存堆副本」：存 `[deallocator copy]`，调用后 `release`。段错误仍在，`11/11` 15 条。

三版的 `11/11` 都在 14 到 19，所以 `deallocator` 的三种写法都没有解决段错误。

## 3. 挂起这条线时的四条现状

退回 `f2627aa5` 之后仍然存在、留待后续处理：

1. `nil buffer from memory` 约 68 条；
2. `Metal failed to build render pipeline` 2 条；
3. `backboardd` 一次 `signal 6 code 4`；
4. `backboardd` 每次重启带走一次会话。

## 4. 回退验证轮的判据

单一变量是驱动（`f2627aa5`，`redwoodmetal.m` 为 `75c50763589d`）：

1. 帧 id 回到数千量级（改动前 7,600）；
2. `signal 11 code 11` 归零；
3. `nil buffer from memory` 回到 60 到 70；
4. `signal 6 code 4` 回到 1 条。

## 5. 证据与命名

五个证据目录都保留：`kernel-12377-attr26-dasd`、`-driver1`、`-driver2`、`-driver3`、`-badaccess`。`driver1` 到 `badaccess` 这四轮的帧数与手柄读数不得引用，只有第一节表里的死因与字符串计数可用。证据目录被 `.gitignore` 覆盖，所以这份说明写在这里。

`driver1` 轮的 `served as a copy` 尺寸分布：1,277,952 一条、62,464 两条、32,768 十五条。

## 6. 诊断打印走 `REDWOOD_DIAG`

诊断行（`rwa metal: driver code at %p`，以及将来只在某次排查里要的行）放在 `getenv("REDWOOD_DIAG")` 之后：开关不设时一行都不打。这样开一个诊断不必换一份库，**基线描述的是行为**，`pack.redwood_diag` 记录这一轮有没有带诊断。`package.py` 把变量放进 backboardd 与 SpringBoard 的环境（job plist 与 launchd 缓存两份都要写，两份不一致打包会失败）。

驱动源改动是 `78a0173`，基线 `31f2d6b7`。开关不设时打包得到的驱动哈希与设了时相同，这就是这个开关的用处。

这一条实现上踩了两个「改了但没生效」的坑，与今晚前面几例同形：第一版只改了内存里的缓存对象、没写回 `xpc/launchd.plist`（job plist 有 `REDWOOD_DIAG`、打包后的缓存没有）；第二版缓存写回了，但校验用的 `job` 变量还是 `add_switch` 时读的那份。两处都当场被断言拦下。

**后面每一轮默认不带诊断行**：`REDWOOD_DIAG` 不设时驱动进程的环境里没有这个变量，日志里不会出现 `rwa metal: driver code at`。看到某轮没有这一行是正常状态，顶部的 `pack.redwood_diag` 是判据：`false` 或字段不存在表示那一轮没带诊断，`true` 才该有。要诊断时打包带 `REDWOOD_DIAG=1`。

## 7. `tl: p` 的读数

`driver1` 轮 `tl: p` 是 868 行原始、349 行唯一（`grep -o "tl: p.\{0,80\}" | sort -u | wc -l`），同一轮 `tl: s` 16,351 行原始。这一轮不是 0。`tl: p` 只在带 `touch_lat` 启动参数时打印，判断某轮是否为 0 要用同一条命令在该轮证据目录上复核。

## 8. buffer 生命周期与 deallocator 时机（task-15，只读源码，未改代码）

这一节回答一个问题：CA 交给我们托管的那块内存，有没有在 CA 还在用时被交还。结论分三条。deallocator 的调用时机对已经记录进 command buffer 的 work 是安全的，它比 Metal 的要求更晚。encoder 存裸指针到 work 记录它之间那段窗口里，我们这一侧没有任何引用，`setBytes:` 三处更进一步把唯一持有者交给 autorelease pool。观测侧有一条决定性数据：roundb 的全部日志里 `could not be mapped`、`Mesa would not allocate`、`the kernel would not allocate` 三行都是 0 条，`rwa buffer: copied` 1775 条、`left nil, over the` 8 条，所以 task-12 的第 1 条候选（`:2610` 映射失败仍返回非 nil）在 roundb 没有触发过。

行号基准：`userland/src/redwoodmetal.m` 在 `.userland.git` 的 `e0b7b62`（仅注释那次提交，行号与 roundb 装车那份驱动的源码一致），`redwoodmetal_commandbuffer.inc`、`redwoodmetal_work.inc`、`redwoodmetal_blit.inc` 同树同提交。

### 8.1 引用计数的完整链条（问题 1）

1. CA 调 `-newBufferWithBytesNoCopy:length:options:deallocator:`（`redwoodmetal.m:2400-2423`），返回 `[[RedwoodMetalBuffer alloc] initWithDevice:gpu:bytes:length:deallocator:]`，+1 归 CA。
2. 该 init（`:2624-2644`）先走分配 init（`:2543-2613`）拿到我们自己的 GPU 内存，`memcpy(_contents, bytes, length)`（`:2635`）拷一次，`_callerBytes = (void *)bytes`（`:2637`）只记指针不持有，`_callerDeallocator = [deallocator copy]`（`:2639`）持有 block 的堆副本。
3. CA 把 buffer 交给 encoder：`-setBuffer:offset:atIndex:` 执行 `_buffers[index] = buffer;`（`:4811`），不 retain；render 侧同形，`_vertexBuffers`／`_fragmentBuffers`（`:3558` 等）。`redwoodmetal_work.inc:1-3` 的头注释写明这是设计：「Encoders fill borrowed references; recording owns them until the command buffer releases this work item. A discarded, unrecorded item owns no resources.」
4. dispatch 把裸指针抄进 work：`work->buffers[i] = _buffers[i];`（`:4900`），随后 `[_commandBuffer recordWork:work]`（`:4915`）、`[work release]`（`:4916`）。draw 侧是 `:3676` 到 `:3790` 的同形序列。
5. `recordWork:`（`redwoodmetal_commandbuffer.inc:325-329`）执行 `[work retainResources]; [_work addObject:work];`。`retainResources`（`redwoodmetal_work.inc:6-32`）逐槽 `[buffers[i] retain]`（`:24`）、`[vertexBuffers[i] retain]`（`:21`）、`[textures[i] retain]`（`:27`）、`[samplers[i] retain]`（`:30`），并用 `_ownsResources` 保证只做一次（`:8-11`）。
6. 执行在 `-commit`：`for (RedwoodMetalWork *work in _work)`（`commandbuffer.inc:358`）同步跑完，`:333` 的注释写着「Metal's own rule, kept: the recorded dispatches run here and not when they were encoded」。
7. 释放：`_work` 数组只在 command buffer 的 `-dealloc` 里 release（`:272`），commit 之后不清空（该文件里 `_work` 只出现在 `:123`、`:231`、`:272`、`:328`、`:358`、`:488`、`:508`、`:563`，没有 removeAllObjects）。每个 work 的 `-dealloc`（`work.inc:34-58`）在 `_ownsResources` 为真时逐槽 release。
8. 最后 `RedwoodMetalBuffer -dealloc`（`redwoodmetal.m:2646-2676`）先把 `_callerDeallocator` 置 NULL 再调用一次 block（`:2652-2658`），传的是 `_callerBytes` 与 `_length`，之后才释放我们自己的内存（`:2659-2674`）。

链条读出来的结论：deallocator 在 command buffer 对象销毁时才跑，比 Metal 要求的「完成之前保住资源」更晚；已记录的 buffer 不存在提前交还。第 2 节里 `bef13a3`（拷完立刻调 deallocator）与 `92d383b`（存栈 block 原指针）两版的问题在当前源码里都不存在，当前是 `759d45e` 那一版的写法。

### 8.2 最后一个强引用可能在记录之前消失（问题 2）

有两处，都落在上面第 3 步到第 5 步之间。

- 窗口 A：`_buffers[index] = buffer`（`:4811`）到 `recordWork:`（`:4915`）之间我们这一侧零引用。Metal 的契约允许调用方在编码之后就释放自己的引用，因为它预期 command buffer 会持有；CA 若这么做，`_buffers[index]` 立即悬空，`work->buffers[i]` 抄的是悬空值，`retainResources` 的 `[buffers[i] retain]`（`work.inc:24`）对一块已被回收的内存发 retain。这一处是唯一会让 CA 的内存被提前交还的序列：悬空的那个对象如果是 no-copy buffer，它的 `-dealloc` 会执行 deallocator（`:2652-2658`）。成立条件是 CA 在 dispatch 之前释放，这一点没有设备证据。
- 窗口 B：`-setBytes:length:atIndex:`（`:4876-4883`）、`-setVertexBytes:`（`:3565-3572`）、`-setFragmentBytes:`（`:3574-3581`）三处都是 `id buffer = [[self device] newBufferWithBytes:bytes length:length options:0];` 之后 `[self setBuffer:[buffer autorelease] offset:0 atIndex:index];`。这个 buffer 的唯一持有者是 autorelease pool，pool drain 时它就 dealloc，而记录发生在之后的 dispatch 或 draw。成立条件只在 CA 一侧的 pool 作用域，例如 setBytes 与 dispatch 分属两次 runloop 迭代。这类 buffer 由 `newBufferWithBytes:` 创建、内存是我们自己的，所以它提前消失不会交还 CA 的内存，后果是 8.4 那条引用计数错乱。

两处都是「最后一个强引用可能在 command buffer 完成之前消失」的具体序列，都还不是 roundb 崩溃的证明。

### 8.3 `:5256` 为什么 retain，另外几处为什么不 retain（问题 3）

`redwoodmetal.m:5256-5263` 的注释写了理由，原文：「Retained, unlike the other back-pointers in this file, and for a measured reason: the records live in the compiler library WITH that buffer, so an application that released it while this encoder still pointed at it would have rwa_buffer_destroy free the records (and scrub them out of everyone else's) and leave this object holding a freed MTLBuffer to send -mesaBuffer to. Metal's own encoder outliving its argument buffer is an application's mistake; a crash in the driver is ours.」随后是 `[buffer retain]`（`:5263`）。

那一处的失效序列与 8.2 的窗口 A 同形：调用方提前释放，encoder 仍指向它，之后对它发 `-mesaBuffer`。差别是那一处已经修了，`_buffers`／`_textures`／`_samplers`／`vertexBuffers` 走的是 `work.inc:1-3` 声明的「记录时才持有」。两种做法在同一个文件里并存，注释各自说明了自己的理由，没有任何一处注释讨论「借用窗口本身能不能超过对象寿命」。

git 历史查不出更多：`_buffers[index] = buffer;`、`[buffer autorelease] offset:0 atIndex:index`、`Retained, unlike the other back-pointers` 三处最早都出现在 `89779df`（10-22 的开源发布提交），那次提交把此前的历史压平了；`retainResources` 在可查历史里最早出现在 `d9282a1`（按职责拆 `.inc` 那次）。所以「有意为之还是漏了」只能从注释读：`work.inc:1-3` 与 `:5256-5262` 说明借用设计与那一处的例外都是有意的，`setBytes:` 三处的 autorelease 没有任何注释覆盖，而它与借用设计的假设冲突（设计假设编码期间由调用方持有，这三处的调用方是我们自己，持有者交给了 pool）。

### 8.4 提前交还之后谁能解释观测到的地址形态（问题 4，定性推理，未证）

假设链，四步，每一步都没有证据：悬空的 `id` 被 `retainResources` retain，对一块已被回收的内存发 retain；那块内存此刻装着别的对象（CA 或 CoreFoundation 的），它的引用计数被我们多加一次；command buffer 销毁时 `[buffers[i] release]`（`work.inc:49`）把它多减一次，该对象可能在真正的使用者还持有指针时销毁；使用者随后从这个对象的字段里取值当 memmove 的 src，取到的是回收后重新写入的字节。

这条假设与观测的地址形态一致：11 个唯一故障地址分成共享缓存字符串常量字节（`cketTouc`、`le.siri.`、`le.media`）、小整数（`0x1`、`0x10000`）、高位非零低位稀疏的打包整数样，都是「槽位已被别的分配复用」会产生的内容；没有一个落在该轮 backboardd 自己的数据区间或共享缓存区间，也与「取到的是一个曾经有效的地址」不相容。与它竞争的解释是 8.5 那条，两者的预测不同：这条预测 src 是回收内存里的字节，那条预测 src 是 0。

### 8.5 与 task-12 第 1 条候选的比较（问题 5）

两条可以同时作为缺陷存在，roundb 的读数只支持其中一条。

- `:2610` 那条要 `IOConnectMapMemory64` 失败才触发，失败时必然打 `buffer %u is allocated but could not be mapped`。roundb 全部日志里这一行 0 条，`Mesa would not allocate`（`:2564`）与 `the kernel would not allocate`（`:2582`）也各 0 条，所以那条路径在 roundb 一次都没有走到。
- 后果也对不上。`:2610` 让 CA 拿到 `_contents` 为 NULL 而 `_length` 非 0 的 buffer，CA 之后动手的地址是 0，故障地址会是 0 或一个很小的值；观测到的 11 个地址没有一个是 0。
- 因此按现有读数，8.2 的窗口与「故障地址就是 src 实参本身、而 src 是垃圾值」更相容。`:2610` 仍是要修的缺陷（task-12 记着，修法是那个分支 `release` 后返回 nil，与 `:2566`、`:2584` 一致），但它不解释 roundb。

### 8.6 memmove 的调用方候选，即 round C 里 `lr` 的预期值清单（问题 6）

先给一条把候选收窄的实测。装车那份 `libredwoodmetal.dylib`（`9d66dd36`）的未定义符号里只有 `_memcpy`；`libredwoodair.dylib`（`d7b9ced5`）的未定义符号里有 `_memmove`、`_memcpy`、`___memcpy_chk`、`___memset_chk`、`_memset`、`_memset_pattern16`（`nm -u`）。

- 所以崩溃那次 `_platform_memmove` 的调用方不可能是我们的驱动，只能是 AIR 库或 iOS 侧。`tools/mesa/air/` 里 memmove 出现 0 次、memcpy 46 处，而这个目录只是 AIR 库的一小部分：`tools/mk-mesa.sh:144-145` 把 `tools/mesa/air` 拷成 `mesa-$VERSION/src/compiler/air`，`:205` 链的 `src/gallium/drivers/freedreno/libredwoodair.dylib` 里只有 `air_metal.c.o` 一个目标文件，其余全来自 `libgallium.a`、`libnir.a`、`libcompiler.a`、`libmesa_util.a`、`libfreedreno.a` 一长串静态库。


perf 在复核里把这处空白填了（[roundb memmove 归属复核](../analysis/2026-10-28-roundb-memmove-attribution.md) §6.3、§6.4）：镜像里 `_memmove` 有 **7 个调用点**，dylib 内 vmaddr 分别是 `0x1d6008`、`0x1d69f8`、`0x212a7c`、`0x260534`、`0x2605fc`、`0x3a7f8c`、`0x3db3ac`；

- 按链接进来的目录检索源码得到 9 处候选（`src/util` 3、`src/compiler` 除 air 外 4、`src/freedreno` 1、`src/gallium/auxiliary` 1），7 与 9 不相等的原因未查，所以那 9 处只是候选清单。故障时刻的 `lr` 是调用方那条 `bl` 的下一条指令，即 7 个调用点各加 4；
- 7 个预期值的低 12 位互不相同，而 dylib 的加载地址页对齐，所以给定一个运行时 `lr`，只有一个候选能让 `lr − 预期值` 页对齐，那一个就是调用点，差值就是 AIR 库的加载地址。这一步不需要内核另外打 AIR 库的基址。


内存进出边界的全部出口，按方向列。交出去（对方随后可能对它做块拷贝）：

- `-contents`（`redwoodmetal.m:2678`）返回 `_contents`，我们自己那块 GPU 内存的映射地址。
- `-constantDataAtIndex:`（`:5411-5426`）返回 `[_destination contents] + _offset + 8 * index`；`:5403-5409` 的注释自己写了「answering NULL would be a crash in the application's memcpy」，即调用方会对这个指针做块拷贝。`_destination` 是 retain 过的（`:5263`），这一处不受 8.2 的窗口影响。
- `-length`（`:2679`）与 `-allocatedSize`（`:2682`）都返回 `_length`，即请求长度，调用方按它决定拷多少。
- buffer 对象本身：`:2400-2423`（no-copy）与 `:2507-2521`（`newBufferWithLength:`、`newBufferWithBytes:`）。
- 交给 AIR 库的：`buffers[i] = [work->buffers[i] mesaBuffer]` 与 `table[i]`（`commandbuffer.inc:420-428`）进 `mesa.dispatch_buffers`／`mesa.dispatch`（`:446-451`）；`mesa.buffer_copy`／`mesa.texture_copy`／`mesa.texture_generate_mipmaps` 拿 `[work->buffers[i] mesaBuffer]` 与 `[work->textures[i] mesaTexture]`（`redwoodmetal_blit.inc:10-27`）；draw 走 `runDraw:`（`commandbuffer.inc:389`）。

接进来（我们只读一次）：

- `newBufferWithBytesNoCopy:` 的 `bytes`，`memcpy(_contents, bytes, length)`（`:2635`）之后不再碰，交还由 deallocator 负责（`:2652-2658`）。
- `newBufferWithBytes:` 的 `bytes`，`memcpy([buffer contents], bytes, length)`（`:2518`）。
- `setBytes:`／`setVertexBytes:`／`setFragmentBytes:` 的 `bytes`，转给上一条（`:4878`、`:3567`、`:3576`）。
- CA 的 IOSurface 由 `redwooddrawable.m` 经内核 `kRedwoodSurface` 变成 GPU buffer，该文件里没有 memcpy 或 memmove。
- blit 的源与目的（`redwoodmetal_blit.inc:95` 起），执行时只把 `mesaBuffer`／`mesaTexture` 交给 AIR 库；`:141-143` 的三处 memcpy 拷的是 origin 与 size 结构体，各 12 到 16 字节。

`lr` 落地后按这个顺序判：

1. 落在 `libredwoodair.dylib`：入口是上面那几个 `mesa.*` 调用之一，Mesa 在上传或拷贝 buffer 内容时调的 memmove。这一种我们能在自己一侧加校验，`commandbuffer.inc:424` 已经有一处 `buffers[i] == NULL && work->buffers[i] != nil` 的判断，可以扩展成对 `_contents` 与 `_length` 的合理性检查。
2. 落在共享缓存（QuartzCore、CoreAnimation、Foundation、CoreFoundation、backboardd 主二进制）：用 task-13 那套离线方法（imagesText 加 export trie）命名，不需要 dSYM。CA 侧最可能对 `-contents` 或 `-constantDataAtIndex:` 返回的指针做块拷贝。
3. 落在 `libredwoodmetal.dylib`：与上面的导入表实测冲突，我们只导入 `_memcpy`。出现这一种说明「memcpy 与 memmove 在 `libsystem_platform` 里是两个独立实现」这条离线结论要重查。

另记一条容易误读的地方：`redwoodmetal_blit.inc:35-38` 的注释写着「backboardd died fifteen times in one run on -generateMipmapsForTexture: before anything was drawn」，那是另一个失效模式（没人应答的 selector 导致 abort，信号 6），与 roundb 的 15 次 `signal 11 code 11` 数字相同、成因不同。不要按 15 这个数把两者对上。
