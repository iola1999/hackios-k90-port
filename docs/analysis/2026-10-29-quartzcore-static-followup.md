# QuartzCore 静态补全：dsc 工具、Mach-O 提取与 26 的三个虚表（2026-10-29）

设备在 2026-10-29 仍未通过 USB 枚举，这一项全部离线完成。上一份文档 [iOS 26 共享缓存中 AppleCLCDDisplay 虚表与槽 0x138 的静态定位](2026-10-29-quartzcore-vtable-26.md) 留下三件事：`is_ready` 的 26 槽位、`EAGLServer` 与 `GLESContext` 的 26 虚表基址，以及一个能交给 IDA 的提取器。本文件记录这三项的结果、新工具的位置与用法、每一项的证据类型和置信度，以及没有做成或只做到一半的部分。第 8 节是随后追加的 `CA_HEARTBEAT_RATE` 只读检查。

槽位一律写成「vtable + 0x10 + offset」里的 offset，例如 0x150。上一份文档里的「第 44 号槽」把 vtable 头两个字也算进去了，两种写法相差 2 个槽，引用旧文档时注意换算。

## 1. 结论

| 项 | iOS 16.5 | iOS 26 | 结论类型 |
|---|---|---|---|
| AppleCLCDDisplay 虚表 | 0x1d5b44520 | 0x1ee97f868 | 实测（复核） |
| ignore_update_p 槽 | 0x138 → 0x1882e0c90 | 0x150 → 0x183efe30c | 实测（复核） |
| begin_update 槽 | 0x170 → 0x1882ddda4 | 0x198 → 0x183efb4d4 | 实测（复核） |
| finish_update 槽 | 0x178 → 0x1882c8568 | 0x1a0 → 0x183f5631c | 实测（复核） |
| is_ready 槽 | 0xb0 → 0x1882f0908 | 0xe0 → 0x183f4fdfc | 推断，证据强 |
| EAGLServer 虚表 | 0x1d5b45c58（62 槽） | 0x1ee982228（75 槽） | 推断，证据强 |
| GLESContext 虚表 | 0x1d5b3b540（138 槽） | 0x1ee982ab0（164 槽） | 推断，证据强 |
| 心跳默认周期 | 0x188553b60 = 1/60 秒 | 0x184242688 = 1/60 秒 | 实测 |

表里的「实测」指直接读缓存文件或 IDA 读同一份数据得到的值，可以被任意重算；「推断」指函数地址与槽位正确，但类归属靠构造函数和函数体匹配，没有运行期验证。`is_ready` 的 26 函数还把电源完成逻辑合并了进来，见第 5 节。

## 2. 工具

工具在 `hackios-xnu-kernel/tools/dsc/`，入口是 `dsc.py`，按职责拆成 `cache.py`（缓存与指针解码）、`macho.py`（Mach-O 解析、提取、导出表）、`disasm.py`（反汇编、引用扫描、虚拟调用扫描）、`vtables.py`（虚表候选与槽匹配）。五个文件合计约 1490 行，最大的 `macho.py` 486 行。

缓存目录由 `--cache` 指定；不给时先按当前目录解析 `hackios-xnu-kernel/ios26/23G90__iPhone18,3`，找不到再按工具位置解析 `../../ios26/23G90__iPhone18,3`。代码里没有本机绝对路径，仓库内的缓存目录名和默认值都不含用户目录。

| 子命令 | 作用 |
|---|---|
| `info` | 头字段、缓存类型、镜像数与映射数 |
| `images [--filter TEXT]` | 镜像地址、`textSegmentSize` 与路径 |
| `map ADDR ...` | 地址落在哪个子缓存、文件偏移、镜像、段与节 |
| `image NAME` | 一个镜像的段表与节表，含宿主子缓存 |
| `extract NAME -o PATH` | 抽成独立 Mach-O |
| `vtscan NAME [--section SECT ...]` | 在 `__const` 里找「16 字节零 + 连续指向本镜像 `__TEXT` 的指针」 |
| `slots ADDR [--count N] [--strings [N]]` | 解码虚表槽，可附上槽函数引用的字符串 |
| `vtmatch ADDR --other-cache DIR --other-vt ADDR` | 两个构建按槽内字符串匹配 |
| `vcalls NAME [--offset OFF ...]` | 虚拟调用点与槽偏移，认 arm64 的 `ldr+blr` 和 arm64e 的 `autda+add+blraa` |
| `refs NAME TARGET ... [--mode all/call/data]` | 直接 `bl` 与 adrp 数据引用 |
| `findstr NAME TEXT` | 字符串在镜像内的地址 |
| `exports NAME` | 导出 trie |
| `read ADDR LEN` / `disasm ADDR` | 十六进制与反汇编，反汇编会解析 adrp 页面并标注目标 |

`extract` 逐个复制镜像引用到的 linkedit 数据块，再改写对应 load command 的 `dataoff`。缓存里这些 `dataoff` 是宿主 `.dyldlinkedit` 文件内的绝对偏移，各数据块之间可能隔着几十兆别的镜像的数据；逐块搬运后 QuartzCore 的输出只有 0x4c4a6c 字节，整段 `__LINKEDIT` 有 178 MB。

提取的布局规则：

- 段按 load command 顺序放置，`__TEXT` 固定在文件偏移 0，其余段顺序排布，`fileoff` 与 `vmaddr` 对 0x4000 同余，所有 section 的 `offset` 重算。
- 符号表保留 14537 条 nlist，字符串表重建。缓存里的字符串表是 41 MB 的共享池，重建后只有 0x149cc 字节，`n_strx` 逐条改写。
- `datasize` 为 0 的 linkedit 命令把 `dataoff` 清 0。缓存里 `LC_DATA_IN_CODE` 留着旧偏移，`nm` 会报 `dataoff field of LC_DATA_IN_CODE command ... extends past the end of the file`。
- 头部和 load commands 在复制完所有段之后才写回文件开头。mach header 位于 `__TEXT` 数据的第一页，先写会被 `__TEXT` 的复制覆盖。

## 3. 提取产物

| 文件 | 大小 | 符号数 | 来源 |
|---|---|---|---|
| `/tmp/dsc26x/QuartzCore` | 0x4c4a6c | 14537 | 23G90 缓存 |
| `/tmp/dsc26x/QuartzCore165` | 0x40c971 | 12700 | 20F66 缓存 |
| `/tmp/dsc26x/libobjc` | 0x58b9e21 | 1105 | 23G90 缓存，测通用性 |

三个文件都用 `otool -l`、`otool -tV`、`xcrun llvm-objdump --macho --private-headers` 和 `nm` 打开过。QuartzCore 两个文件另外用 idalib 打开，`imagebase` 分别是 0x183ed3000 与 0x18827b000，与缓存里的镜像基址一致，段内地址不需要换算。IDA 对 26 的四个目标函数做了 define_func 与 Hex-Rays 反编译，结果见第 4、5 节。

提取文件只面向静态工具，不用于加载。缓存里的镜像没有 `LC_DYLD_CHAINED_FIXUPS` 与 `LC_DYLD_INFO`，数据段中的指针保持缓存编码（26 是 bit 63 选择形式的 chained 值，16.5 是低 36 位绝对地址），IDA 不还原这些指针。代码段不受影响。

`libobjc.A.dylib` 的输出有 93 MB，原因是它带一个 0x5528368 字节的 `__OBJC_RO` 共享段，工具按原样复制；这是该镜像的真实数据。

## 4. 三个已知槽的复核

从缓存文件读出的原始字与解码地址：

| 槽 | 原始字 | 解码地址 | 函数 |
|---|---|---|---|
| 0xe0 | 0x8016980403f4fdfc | 0x183f4fdfc | is_ready 候选 |
| 0x150 | 0x8014b59003efe30c | 0x183efe30c | ignore_update_p |
| 0x198 | 0x8017679803efb4d4 | 0x183efb4d4 | begin_update |
| 0x1a0 | 0x80177d9c03f5631c | 0x183f5631c | finish_update |

IDA 的 `get_bytes` 在抽取文件上读 0x1ee97f9c8、0x1ee97fa10、0x1ee97fa18 三个地址，返回的字节与上表逐个相同，说明提取器复制的数据与 load command 补丁没有改变虚表内容。

`otool -tV` 在 0x183efe30c 处的输出与上一份文档记录的 26 函数体一致，开头是 `ldrb w8, [x0, #0x293]`、`tbnz w8, #0x4, 0x183efe31c`。IDA 对 0x183efb4d4 与 0x183f5631c 做 define_func，得到的函数大小分别是 0xd6c 与 0x3a7c；这两个边界与另外两张 320 槽虚表的槽值吻合。

## 5. is_ready

16.5 的实现 0x1882f0908 在四张 246 槽虚表里都位于 offset 0xb0。函数体（省略栈帧建立与恢复）：

```text
0x1882f0918: add  x21, x0, #0x9f2
0x1882f091c: ldr  x8, [x21]
0x1882f0920: tbz  w8, #3, 0x1882f0968
0x1882f0924: mov  x19, x0
0x1882f0928: ldr  x0, [x0, #0x318]
0x1882f092c: mov  w1, #0
0x1882f0930: mov  w2, #-0x7ffffffd
0x1882f0934: bl   0x18dbb8484
0x1882f0938: cbnz w0, 0x1882f0968
0x1882f093c: ldr  x8, [x21]
0x1882f0940: and  x8, x8, #0xfffffffffffffff7
0x1882f0944: str  x8, [x21]
0x1882f0948: add  x20, x19, #0x1e0
0x1882f094c: mov  x0, x20
0x1882f0950: bl   0x188549ec0          ; pthread_mutex_lock
0x1882f0954: mov  x0, x19
0x1882f0958: mov  w1, #0
0x1882f095c: bl   0x18852956c
0x1882f0960: mov  x0, x20
0x1882f0964: bl   0x188549ed8          ; pthread_mutex_unlock
0x1882f0968: ldr  x8, [x21]
0x1882f096c: tst  x8, #4
0x1882f0970: cset w0, eq
```

Hex-Rays 对同一函数的反编译是：`if ((flags & 8) && !wait(*(this+0x318), 0, 0x80000003)) { flags &= ~8; lock(this+0x1e0); call(this, 0); unlock; } return (flags & 4) == 0;`。

调用关系这一路只拿到否定结果。`refs QuartzCore 0x1882f0908 --mode call` 扫了 865280 条指令，直接 `bl` 为 0 处。`vcalls QuartzCore --offset 0xb0` 找到 90 处间接调用，能对上函数归属的有三处：两处在四张 246 槽表的槽函数内（0x1882f2534 对另一个对象取槽 0xb0 后把返回值当浮点比率参与计算，0x188358800 在 GLES 相关的大函数里），一处在 EAGLServer 的缓冲区解码函数 0x1882f0724。三处都无法证明被调对象是 display，仅凭槽偏移不能把 display 的调用点从其它类里筛出来。

26 全镜像只有一条 `mov w2, #-0x7ffffffd`，在 0x183f4fe54，属于 0x183f4fdfc；16.5 全镜像同样只有一条，在 0x1882f0930，属于 is_ready。两个函数都是四张槽表共用同一实现：16.5 在四张表里都是 offset 0xb0，26 在四张 320 槽表里都是 offset 0xe0。

0x183f4fdfc 的关键指令：

```text
0x183f4fe24: ldr   x8, [x0, #0x300]
0x183f4fe28: add   x8, x8, #4
0x183f4fe2c: ldarb w8, [x8]              ; byte+4 非零则跳过
0x183f4fe34: ldr   x8, [x19, #0x300]
0x183f4fe38: add   x8, x8, #5
0x183f4fe3c: ldarb w8, [x8]
0x183f4fe40: cmp   w8, #1                 ; byte+5 必须为 1
0x183f4fe48: mov   w8, #0x6460
0x183f4fe4c: add   x0, x19, x8
0x183f4fe50: mov   w1, #0
0x183f4fe54: mov   w2, #-0x7ffffffd
0x183f4fe58: bl    0x183f383ec
0x183f4fea0: add   x3, x3, #0x2bf         ; "Display::complete_powering_on"
0x183f4feb8: ldr   x8, [x19, #0x300]
0x183f4febc: add   x8, x8, #4
0x183f4fec4: stlrb w9, [x8]               ; byte+4 = 1
0x183f4fed0: add   x0, x19, #0x240
0x183f4fed4: bl    0x184236930            ; pthread_mutex_lock
0x183f4fee0: bl    0x1841fd704            ; call(this, 0)
0x183f4fee8: bl    0x184236950            ; pthread_mutex_unlock
0x183f4feec: ldr   x8, [x19, #0x300]
0x183f4fef0: add   x8, x8, #4
0x183f4fef4: ldarb w8, [x8]               ; byte+4 非零返回 1
0x183f4fefc: mov   w0, #1
0x183f4ff04: ldr   x8, [x19, #0x300]
0x183f4ff08: add   x8, x8, #5
0x183f4ff0c: ldarb w8, [x8]               ; 否则返回 byte+5 != 0
0x183f4ff14: cset  w0, ne
```

两边的控制流一一对应：16.5 的 `flags & 8` 守卫对应 26 的 `byte+5 == 1` 守卫；等待调用的第一个参数分别是 `[this+0x318]` 与 `this+0x6460`，第二、三个参数都是 0 与 0x80000003；等待成功后两边都改写状态（16.5 清 bit 3，26 置 byte+4）、加锁、调用 `this->(0)`、解锁；返回值都来自同一组状态位（16.5 看 bit 2，26 看 byte+4 与 byte+5）。26 把 16.5 的 64 位标志位换成了状态对象里的两个原子字节，并加了 `Display::complete_powering_on` 日志，`is_ready` 的判定被合并进电源完成函数。

结论：26 的 `is_ready` 等价逻辑在 offset 0xe0，函数 0x183f4fdfc。这个判断的依据是唯一常量、逐指令对应的控制流和四张槽表一致的槽位，属于推断，证据强。运行期验证仍然需要：在真机上读 `CAWindowServerDisplay` 对象的 vtable，确认 0xe0 指向 0x183f4fdfc。镜像内部没有对 0xe0 的虚拟调用，`refs` 也没有直接调用者，所以静态这条路到这里为止。

## 6. EAGLServer

16.5 的虚表 0x1d5b45c58 有 62 槽，`inject.c` 用它挂两个钩子：slot 0x1a0 的 `renderer`（0x1882e2548）与 slot 0x178 的 `render_update`（0x18835770c）。26 的对应虚表是 0x1ee982228，75 槽。

判据一，构造函数形状。16.5 的工厂函数 0x1883d1544 与 26 的 0x1840a1124 结构相同：

- 开头都调用基类构造（16.5 `bl 0x1884f3a0c`，26 `bl 0x1841c6860`），随后把基类虚表写进返回的对象（16.5 写 0x1d5b35a98，即基类虚表 0x1d5b35a88 + 0x10；26 写 0x1ee98e018，即 0x1ee98e008 + 0x10）。
- 构造函数末尾都写两个虚表指针：`[this]` 写主虚表 + 0x10（0x1d5b45c68 / 0x1ee982238），`[this + 0x310]` 或 `[this + 0x5c0]` 写紧跟在主表后面的第二张虚表的 + 0x10。
- 第二张虚表的位置都等于「主表起始 + 0x10 + 槽数 × 8 + 0x10」：16.5 是 0x1d5b45e68，26 是 0x1ee9824a0。
- 两个工厂随后都读环境变量 `CA_ENABLE_OGL`（16.5 的字符串在 0x188576493，26 在 0x184260a40）。

判据二，`render_update` 的函数体。16.5 的 0x18835770c 与 26 的 0x183f4a8ac 开头逐条对应：保存 `x1`、`x2`，取 `[this]` 的虚表并把 `renderer` 取出来调用，然后 `ldr x0,[this,#0x60]`、调用渲染更新实现、按返回值把 flags 的最低两位置位。两处都引用字符串 `com.apple.GL.event.frameboundary.end`；26 里另有一张 70 槽表（0x1ee981ec0）的同槽函数 0x184099ef8 也引用它，用构造函数区分两张表。两边调用 `renderer` 的槽偏移分别是 0x1a0 与 0x1b0，说明 26 的 `renderer` 在 offset 0x1b0、`render_update` 在 offset 0x1d8。

判据三，`renderer` 的函数体。16.5 的 0x1882e2548 与 26 的 0x183f37dc0 都做同一件事：先看对象里的两个字段是否已经缓存，没有就创建渲染器对象、用类对象注册、把结果写回两个字段，并调用 `[this+0x60]` 上的方法登记。字段偏移从 0x318/0x320 变成 0x5c8/0x5d0，流程一致。26 的 0x1b0 槽有 15 处虚拟调用，说明这张表在实际代码里是活的。

基类也一一对应：16.5 的 0x1d5b35a88（57 槽）对应 26 的 0x1ee98e008（70 槽），两边的构造函数都把它作为第一层基类写入。EAGLServer 本身从 62 槽增到 75 槽，基类从 57 增到 70，增量一致。

结论：26 的 `EAGLServer` 虚表基址是 0x1ee982228。构造函数、唯一字符串和两个钩子函数的函数体三条证据独立，属于推断，证据强。

## 7. GLESContext

16.5 的虚表 0x1d5b3b540 有 138 槽，`inject.c` 用它挂 `function_supported`（slot 0x378）、`function_uniform`（0x388）与 `compile_shader`（0x060）。26 的对应虚表是 0x1ee982ab0，164 槽。

判据一，构造函数。16.5 的 0x188400a18 与 26 的 0x1840d1c28 逐项对应：

- 两边都先调用基类构造（16.5 `bl 0x18837dbd8`，26 `bl 0x1840d3334`），再把基类虚表写进返回的对象：16.5 写 0x1d5b3d138（基类虚表 0x1d5b3d128 + 0x10），26 写 0x1ee989190（0x1ee989180 + 0x10）。
- 都把构造参数存进一个固定字段：16.5 `[this+0xa8]`，26 `[this+0x258]`。
- 都写入常数 0x3c000000：16.5 `[this+0x800]`，26 `[this+0xaa0]`。
- 都把自身虚表 + 0x10 写进 `[this]`：16.5 是 0x1d5b3b550，26 是 0x1ee982ac0。
- 都把某个字节的最低位置 1（`orr #2`）：16.5 `[this+0x868]`，26 `[this+0xb08]`。
- 随后都用构造参数调用一个初始化函数：16.5 `0x1885c0f00`，26 `0x1842bb1a0`。

判据二，GL 错误字符串。16.5 虚表里引用 `GL_INVALID_ENUM`、`GL_INVALID_OPERATION` 等 9 条字符串的函数在 offset 0xa8（idx 21，0x1884a82c4）；26 虚表里引用同一组字符串的函数在 offset 0xf0（idx 30，0x18416374c）。26 的第 0 号槽还引用 `CA_MAX_TEXTURE_UNITS`、`GL_APPLE_fence` 等纹理相关字符串。

基类同样对应：16.5 的 0x1d5b3d128（54 槽）对应 26 的 0x1ee989180（69 槽）。

结论：26 的 `GLESContext` 虚表基址是 0x1ee982ab0。构造函数逐项对应，GL 字符串提供了独立旁证，属于推断，证据强。`inject.c` 用的三个槽偏移（0x378、0x388、0x060）没有逐个重定位，见第 9 节。

## 8. CA_HEARTBEAT_RATE 与刷新周期

上一份文档的 `vtmatch` 对 AppleCLCDDisplay 只匹配到 `CA_HEARTBEAT_RATE` 一处字符串。这一节查 26 侧对应的函数 0x183f380d8（虚表 0x1ee97f868 的 offset 0x318）、它的默认值和调用点。结论：返回值是显示刷新周期，单位秒，默认 1/60；`CA_HEARTBEAT_RATE` 按 Hz 解释并取倒数；显示驱动给出刷新属性时用属性值。没有找到 15 秒或 3 秒的默认值，也没有看到返回值被直接交给定时器 API。

### 位置与默认值

16.5 的同一函数在 0x1882d3930，位于虚表 0x1d5b44520 的 offset 0x2d8。两边函数结构对应，字段偏移不同。下表左侧是 26，右侧是 16.5。

| 项 | 26 | 16.5 |
|---|---|---|
| 函数 | 0x183f380d8 | 0x1882d3930 |
| 槽 offset | 0x318 | 0x2d8 |
| 结果缓存 | [this+0x7528] | [this+0xb18] |
| 显示刷新步长（秒） | [this+0x7510] | [this+0xaf8] |
| 最小刷新间隔 | [this+0x7508] | [this+0xaf0] |
| 标志字 | [this+0x280] | [this+0x220] |
| 模式字 | [this+0x290] | [this+0x230] |
| 默认常量 | 0x184242688 = 1/60 | 0x188553b60 = 1/60 |

函数的计算顺序（26）：

1. `[this+0x7528]` 非零直接返回；为零时算一次并写回缓存。
2. `getenv("CA_HEARTBEAT_RATE")`（0x18425ba05，stub 解析到 libsystem_c 的 `_getenv`）非空：`atof` 后算 `1.0 / x`。环境变量名与同镜像的格式串 `heartbeatRate: %g Hz`（0x18425c56c）一致，输入按 Hz 解释属于推断；取倒数是指令实测。内容无法解析成数字时 `atof` 返回 0，取倒数得到 +inf，这条路径不回退到默认值。
3. 否则 `[this+0x7510]` 非零时返回该值。属性初始化函数 0x184070768 从 IOMFB 属性 `displayRefreshStepMachTime` 读 32 位整数，调用 0x183f46e9c 用 mach 时间基换成秒，在 0x1840712e4 写进这个字段。
4. 否则 `[this+0x7508]` 非零时返回 `(double)值 × 2^-32`；`[this+0x280] & 0x10` 非零时乘 `2^-33`。同一函数在 0x1840712c0 把 IOMFB 属性 `displayMinRefreshInterval` 的整数写进该字段。按 Q32 定点秒解释能对上常见刷新率，这一步是推断。
5. 都没有时返回常量 1/60 秒。
6. 最后若 `[this+0x290] != -1`，返回值改为 `65536.0 / ((x >> 29) & 0x1ffffff)`；`[this+0x280] & 0x10` 非零且 x 为负时再乘 0.5。25 位字段按「Hz × 65536」解释时结果才是秒，字段编码本次没有确认。字段为 0 时这个除法得到 +inf。0x184070768 与构造 0x184073a5c 都没有直接的 0x290 偏移写入，写这个字段的位置本次没有定位。第 6 步不回写 0x7528，每次调用都重算。

属性名来自 0x184070768 引用的 CFString，cstring 地址分别是 `IOMFBDisplayRefresh`（0x18425b7e6）、`displayMinRefreshInterval`（0x18425b7fa）、`displayRefreshStepMachTime`（0x18425b814）。取值走 `CFDictionaryGetValue` 和 0x183f38340；后者先判 `CFBoolean`，再按 `kCFNumberIntType`（9）调 `CFNumberGetValue`。步长字段写入前经过 0x183f46e9c（tick→秒），它和 0x183f4688c（秒→tick，乘全局 0x1ecd99580 并加 0.5 取整）使用同一初始化例程填充的两个全局 0x1ecd99580 与 0x1ecd99590。

构造链把字段与虚表归到同一个类：工厂 0x184075600 以 0x7530 作为分配大小参数，调用构造函数 0x184073a5c，后者在 0x184074e5c 调用 0x184070768；工厂随后把签名后的 vptr 0x1ee97f878（0x1ee97f868 + 0x10）写进对象，并把 `[obj+0x7528]` 清零。本次用到的最大字段偏移是 0x7528，与 0x7530 的分配参数吻合。

### 调用点

`refs --mode call` 对 0x183f380d8 是 0 处，`vcalls --offset 0x318` 在 26 找到 28 处，分布在 19 个函数；16.5 的 offset 0x2d8 是 32 处。用法分三类：

- 换成 tick 后参与截止时间。0x183f33a44 的 0x183f33e00、0x183f33f94 与 0x183f4ad50 的 0x183f4e798、0x183f4e7dc 在调用 heartbeat 后紧跟 0x183f4688c。finish_update 的 0x183f56784 在条件成立时取 `heartbeat × 0.125` 调整时间戳；该函数在 0x183f568dc 另有一次 0x183f4688c 换算。
- 换成频率。0x183f4ad50 在 0x183f4b54c 取槽 0x330 的整数（另一条路径用 0x183f4b520 槽 0x90 的返回值），0x183f4b578 算 `1/(heartbeat × 计数)`，取整后存 `[this+0x628]`。
- 参与帧时间统计。函数 0x183f33a44 在 0x183f35654 用「经过时间 / heartbeat」取整减一，把结果限制在 0xf0 以内并累加直方图；0x18409aa38 把 heartbeat 换成 tick、乘槽 0x320 的计数、加基准 tick，再换回秒存入 `[obj+0x3e8]`，同时把基准 tick 和周期 tick 存进 `+0x3f0/+0x3f8`。把这三个量解释为基准时间、周期与下一次更新时间，属于推断。

28 处里没有一处把返回值直接传给 `CFRunLoopTimerCreate`、`CFRunLoopTimerSetNextFireDate`、`dispatch_source_set_timer`、`mach_wait_until` 或 `nanosleep`。19 个调用函数的外部调用里，和调度相关的是 0x183f33a44 的 `usleep`（0x183f33ba8）与 0x1841ce104 的 `CFRunLoopPerformBlock`/`CFRunLoopWakeUp`（0x1841ce45c/0x1841ce464）。`usleep` 睡到 0x183f36974 从对象取出的 tick 时间戳 x21；`CFRunLoopPerformBlock` 投递一个 block，`CFRunLoopWakeUp` 唤醒运行循环，两处都没有定时器参数，块的执行时机由 run loop 决定。这三处都没有把 heartbeat 用作周期。调用这个函数的定时器周期是否由它决定，未确认；能确认的是它作为刷新周期参与下一次更新时间和帧时间计算。

### 15 秒与 3 秒常量

做法两步：在所有段里按 IEEE754 位型搜 double/float（15.0、3.0、1/15、1/60、16384.0、0.125、0.25、0x3e800000），再对 `__TEXT` 全部 1033136 条指令扫 `fmov` 立即数。代码常量节的命中：

| 常量 | 地址 | 引用与用途 |
|---|---|---|
| 1/15 double | 0x184242f20 | 0x1840265b4，颜色解析函数 0x1840264a0 把十六进制颜色分量除以 15；函数引用 `rgb(`、`aqua`、`Incorrect number of color components (need %d)` |
| 3.0 double | 0x184243978 | 未找到代码引用 |
| 3.0 double | 0x1842439a0 | 0x184084be8，带 `init` 选择器的 ObjC 初始化函数 0x184084b90 把 3.0、10.0、±inf 写进对象字段 |
| 3.0 double | 0x1ee990ba2 | 未找到代码引用 |
| 15.0 float | 0x184244130、0x184244138 | 0x18402fed4，四分量浮点运算；同一函数 0x18402fef4 还有 `fmov s2,#15.0` |
| 16384.0 | 无 | 代码常量节没有 double 或 float 版本 |
| 0x3e800000（0.25f） | 多处 `__const` | 未逐个核对用途 |

内联 `fmov` 扫到 68 条（含数据表里的误命中）。落在 heartbeat 调用函数里的只有两处，都是 0x183f4ad50 里的 15.0：

- 0x183f4c014：算 `[display+0x2c8] + 15.0`，与当前时间 d8 比较；`now > last + 15` 时把 1 写进 `[this+0x138]`。display 由 `[x23+0x60]` 取出；`[display+0x2c8]` 在 0x183f4c008 由 d8 更新。
- 0x183f4c3b0：条件成立时把 `[display+0x2c8] + 15.0` 写进 `[this+0x80]`，否则写 +inf；0x183f4cb64、0x183f4cc20 等地址读取 `[this+0x80]` 并与当前时间比较。
- 两处的加法都没有 heartbeat 参与。`[this+0x80]` 的用法符合截止时间：条件成立时写入 last + 15，否则写 +inf，之后与当前时间比较；这个值没有传给定时器。内联 3.0 立即数和 3.0 常量引用都没有落在 heartbeat 调用函数里。

结论：按这些分支的取值来源，heartbeat 返回的是毫秒量级的刷新周期，与 15 秒、3.011 秒都不对应。0x183f4ad50 里的 15 秒是「最近时间 + 15」的截止时间比较，与 heartbeat 返回值没有数据依赖；它是否对应真机上每 15 秒一次的帧流空洞，未确认。要在真机上区分这两条线索，需要看空洞前后 `[display+0x290]`、`[display+0x2c8]` 与更新上下文 `+0x80` 的读数，静态分析到这里没有更多证据。

证据类型：槽位、函数体、默认常量、属性键、调用点计数、常量位型与引用点是实测；Hz 单位、Q32 解释、模式字段公式与「下一次更新时间」的语义是推断；定时器周期是否由 heartbeat 决定、15 秒截止时间与真机空洞的关系、写 0x290 的位置未确认。

## 9. 未完成与否定证据

idalib 仍然打不开主缓存文件。`idb_open` 对 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/dyld_shared_cache_arm64e` 返回 `Failed to open database: <路径>`。抽取出来的独立 Mach-O 可以正常打开，这条路线不再需要动主缓存。

26 的虚表方法顺序相对 16.5 发生了大范围变化，不能按槽序号做算术映射：

- 16.5 的 powering-on 虚函数 0x1885224d4 在 offset 0x108（idx 33），26 中带同一条 `powering on display and entering flipbook` 字符串的对应函数 0x18405f9cc 在 offset 0x8d8（idx 283）。
- EAGLServer 的 `renderer` 从 0x1a0 移到 0x1b0，`render_update` 从 0x178 移到 0x1d8，两者在表内的相对顺序反了过来。
- 之前用 (指令数, 调用数) 形状做 difflib 对齐，相似度只有 0.124，246 个槽只对齐 35 个，连三个已知锚点都对不上，这个方法已放弃。

`is_ready` 的槽位没有运行期证据，也没有镜像内的调用者。16.5 的 0xb0 有 90 处虚拟调用点，但无法做类型判定；26 的 0xe0 在 `vcalls` 里是 0 处。唯一的确认办法是真机读对象虚表。

`vtmatch` 按槽内字符串匹配对 AppleCLCDDisplay 只找到 1 对（`CA_HEARTBEAT_RATE`），对 EAGLServer 也只找到 1 对。字符串匹配只适合有日志的类，不能作为通用手段。

`inject.c` 在 GLESContext 上的三个钩子槽没有重定位。16.5 的 `function_supported`（0x1884a9308）靠 `cmp w9,#0x59` 加字节跳转表分派，26 里没有相同形状的函数，可能改成了别的表结构；`compile_shader` 的 16.5 槽函数 0x1883fc808 只有 `mov w0,#0; ret`，与注释描述的「编译着色器」不符，这一点在上一轮就没有解释。两者都需要单独核对。

EAGLServer 的 `renderer`／`render_update` 槽位已经给出（0x1b0／0x1d8），其余槽位没有逐个比对。两个基类（0x1ee98e008、0x1ee989180）只做到基址与槽数，没有逐槽核对。

## 10. 复现命令

```text
# 头字段与镜像
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py info
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py images --filter QuartzCore

# 地址落在哪个子缓存与节
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py map 0x1ee97f868 0x183efe30c

# 虚表扫描与槽解码（26）
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py vtscan QuartzCore
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py slots 0x1ee97f868 --count 320

# 16.5 侧
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py --cache hackios-xnu-kernel/ios165/20F66__iPhone10,3_6 \
    slots 0x1d5b44520 --count 246 --strings
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py --cache hackios-xnu-kernel/ios165/20F66__iPhone10,3_6 \
    vcalls QuartzCore --offset 0x2d8

# 抽成独立 Mach-O
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py extract QuartzCore -o /tmp/dsc26x/QuartzCore
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py --cache hackios-xnu-kernel/ios165/20F66__iPhone10,3_6 \
    extract QuartzCore -o /tmp/dsc26x/QuartzCore165

# 引用、虚拟调用与字符串
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py vcalls QuartzCore --offset 0xe0 --offset 0x1b0 --offset 0x318
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py refs QuartzCore 0x183f4fdfc 0x183f380d8 --mode call
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py findstr QuartzCore "complete_powering_on"

# heartbeat 默认常量与颜色解析的 1/15
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py read 0x184242688 8
python3 -I hackios-xnu-kernel/tools/dsc/dsc.py read 0x184242f20 8
```

## 11. 相关文档

上一轮的缓存格式、指针解码与 AppleCLCDDisplay 虚表定位见 [iOS 26 共享缓存中 AppleCLCDDisplay 虚表与槽 0x138 的静态定位](2026-10-29-quartzcore-vtable-26.md)。注入点与槽的原始用途见 [`inject.c`](../../hackios-xnu-userland/userland/src/inject.c)。真机操作与恢复流程见[设备测试手册](../plan/device-test-playbook.md)与[引导目标切换 SOP](../plan/device-boot-target-sop.md)。