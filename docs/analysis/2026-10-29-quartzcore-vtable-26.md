# iOS 26 共享缓存中 AppleCLCDDisplay 虚表与槽 0x138 的静态定位（2026-10-29）

设备在 2026-10-29 从 USB 掉线，这一项全部在离线状态下完成：解析本机 `23G90__iPhone18,3` 的 split dyld 共享缓存，给 `userland/src/inject.c` 里取自 iOS 16.5 的虚表常量找 iOS 26 的对应值。下文记录方法、每一步的实测读数、用 16.5 做的自检，以及可直接替换的常量与一条启动期断言。所有结论来自缓存文件与静态反汇编，没有真机验证。

## 1. 结论

26 的 `CA::WindowServer::AppleCLCDDisplay` 虚表基址是 `0x1ee97f868`，位于 `dyld_shared_cache_arm64e.33.dylddata` 的 QuartzCore `__AUTH_CONST.__const`（实测）。虚表长 `0xa10` 字节，含 320 个函数指针；头两个字（offset-to-top 与 typeinfo）都是 0（实测）。

26 上 `vtable + 0x10 + 0x138 = 0x1ee97f9b0` 存的是 `0x184072d88`，函数体只有三条指令：`mov w8,#0x7377; ldrb w0,[x0,x8]; ret`，读 `this+0x7377` 的字节（实测）。这个槽与 `ignore_update_p` 无关，把钩子装在这里会改掉一个取字节的虚函数。

26 的 `ignore_update_p` 等价函数是 `0x183efe30c`，位于槽 `0x150`，即 `vtable + 0x10 + 0x150 = 0x1ee97f9c8`（地址与函数体为实测，槽位对应为推断，依据见第 5、6 节）。

同一组另外三个已知槽的 26 取值：`begin_update` 在 `0x198`（`0x183efb4d4`），`finish_update` 在 `0x1a0`（`0x183f5631c`），`is_ready` 只有候选 `0xe0`（`0x183f4fdfc`），未确认，见第 8 节。

| 项 | iOS 16.5 | iOS 26 |
|---|---|---|
| 虚表基址 | `0x1d5b44520` | `0x1ee97f868` |
| 槽 0xb0（is_ready） | `0x1882f0908` | 候选 `0x183f4fdfc`（槽 0xe0） |
| 槽 0x138（ignore_update_p） | `0x1882e0c90` | `0x183efe30c`（槽 0x150） |
| 槽 0x170（begin_update） | `0x1882ddda4` | `0x183efb4d4`（槽 0x198） |
| 槽 0x178（finish_update） | `0x1882c8568` | `0x183f5631c`（槽 0x1a0） |
| 函数指针数量 | 246 | 320 |

## 2. 输入与工具

26 的缓存目录是 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/`，共 85 个 `dyld_shared_cache_arm64e*` 文件（主文件加 `.01` 到 `.83`、`.atlas`），合计 4.9 GB。16.5 的缓存目录是 `hackios-xnu-kernel/ios165/20F66__iPhone10,3_6/`，43 个 `dyld_shared_cache_arm64*` 文件，架构是 arm64（实测）。

解析与反汇编用 Python 3.13 加 capstone 5.0.7，脚本放在仓库外的临时目录 `/tmp/dsc26/`，没有入库。`/usr/bin/dyld_info` 存在，但把主缓存文件当输入时报 `file not found`，没有起作用（实测）。idalib 的 `idb_open` 打开主缓存文件直接失败（实测），IDA 这条路需要先把 QuartzCore 抽成独立 Mach-O 才能用。

## 3. 缓存格式与指针解码

主缓存头按 `dyld_cache_header` 解析：magic 在 0x00，legacy mapping 表偏移与条数在 0x10／0x14（两个 u32），uuid 在 0x58，cacheType 在 0x68，images 表偏移与条数在 0x88／0x90（两个 u64），共享区起点与大小在 0xe0／0xe8（实测，两份缓存同构）。

实测头字段：26 的 magic 是 `dyld_v1  arm64e`，uuid `46e741b70e753f19a3080464f4140b00`，共享区 `0x180000000` 起、长 `0x142cf8000`；16.5 的 magic 是 `dyld_v1   arm64`，uuid `e5420db330d033aa8b7e05b5038bb46d`，共享区 `0x180000000` 起、长 `0xa9eec000`。

images 表每条 32 字节，布局是 `uuid[16]` + `address`（u64）+ `textSegmentSize`（u32）+ `pathOffset`（u32）。按这个布局读出 26 有 4315 条、16.5 有 2710 条，QuartzCore 的 path 都能正确落在 `/System/Library/Frameworks/QuartzCore.framework/QuartzCore`（实测）。

每个子缓存文件自带一份 `dyld_cache_header` 和一张 32 字节的 mapping 表（`address`、`size`、`fileOffset`、`maxprot`、`initprot`）。把所有文件的表合并后，26 得到 106 个 mapping，16.5 得到 51 个（实测）。地址到文件偏移的换算就靠这张表，子缓存名（`.27`、`.33.dylddata` 等）只作记录。

指针编码在两个版本里不同，实测规律如下。16.5 的 `__DATA_CONST` 里，低 36 位是绝对地址，第 36 到 43 位带有非零标记（观察到的值有 `0x20`、`0x80`），解码时必须把这几位掩掉；例如 `0x201882e0c90` 解出 `0x1882e0c90`。26 的 `__AUTH_CONST` 与 `__DATA_CONST` 里，bit 63 为 1 表示带认证的 rebase，目标等于共享区起点加低 32 位；bit 63 为 0 时目标等于共享区起点加低 36 位。

26 的解码规则用 `__objc_classlist` 交叉验证过：`0x001000006cd924e0` 解出 `0x1ecd924e0`，落在 QuartzCore `__DATA_DIRTY.__objc_data`（`0x1ecd923a0` 起）；`0x001000006daf8518` 解出 `0x1edaf8518`，落在 `__AUTH.__objc_data`（`0x1edaf81d0` 起）。两条都对得上（实测）。

## 4. 用 16.5 做的自检

先按 [`inject.c`](../../hackios-xnu-userland/userland/src/inject.c) 里的四个已知函数指针验证整条链路。QuartzCore 在 16.5 里加载在 `0x18827b000`，`__TEXT` 段 `0x18827b000` 起、长 `0x34d000`；`__DATA_CONST` 在 `0x1d5b31860`，长 `0x5ca18`（实测）。

`0x1d5b44520` 落在 `__DATA_CONST.__const`（`__const` 起点 `0x1d5b34530`，长 `0x243c8`），对应文件是 `dyld_shared_cache_arm64.27.dylddata` 的 `0x230520`（实测）。按「vtable + 0x10 + offset」读四个槽，得到的值与 `inject.c` 里的期望值逐个相同（实测）。

| 槽 | 16.5 读出（原始字） | 解码地址 | `inject.c` 期望 |
|---|---|---|---|
| 0xb0 | `0x00000201882f0908` | `0x1882f0908` | `0x1882f0908` |
| 0x138 | `0x00000201882e0c90` | `0x1882e0c90` | `0x1882e0c90` |
| 0x170 | `0x00000201882ddda4` | `0x1882ddda4` | `0x1882ddda4` |
| 0x178 | `0x00000201882c8568` | `0x1882c8568` | `0x1882c8568` |

四个值全部对上，说明地址换算、文件映射、chained 指针解码和「vtable + 0x10 + offset」这条约定都是对的。这一步是方法正确性的第一道验证。

16.5 的虚表边界也量了：从 `0x1d5b44520` 起，前 16 字节是全零的头两个字，随后是 246 个指向 `__TEXT` 的指针，到 `0x1d5b44ce0` 处出现一个指向 `0x1d5b591f8` 的数据指针，虚表到此结束（实测）。

## 5. 26 上定位虚表

### 扫描思路

在 QuartzCore 的常量段里找「16 字节零前缀 + 连续指向本镜像 `__TEXT` 的已解码指针」。26 的候选段是 `__AUTH_CONST.__const`（`0x1ee97d9b0`，长 `0x15cb0`）与 `__DATA_CONST.__const`（`0x1e61f1860`，长 `0xf2d0`）（实测）。

扫描结果：16.5 的 `__DATA_CONST.__const` 有 293 个候选，26 的 `__AUTH_CONST.__const` 有 308 个候选，26 的 `__DATA_CONST.__const` 只有 17 个（实测）。数量本身说明不了问题，需要按四个一组的虚表结构筛选。

### 四个一组的虚表

16.5 有四个依次排列的 246 槽虚表：`0x1d5b35c60`、`0x1d5b37820`、`0x1d5b43d00`、`0x1d5b44520`，其中最后一个是 `AppleCLCDDisplay`（实测）。两两相同的槽数在 226 到 243 之间（共 246），说明它们共享大部分实现。

26 的 `__AUTH_CONST.__const` 开头有四个依次排列的 320 槽虚表：`0x1ee97d9b8`、`0x1ee97e408`、`0x1ee97ee58`、`0x1ee97f868`，每个 `0xa10` 字节；两两相同的槽数在 298 到 314 之间（共 320）（实测）。两边都是一组四个、排列顺序相同。

### 构造函数比对

决定性的证据在构造函数。16.5 里给 `AppleCLCDDisplay` 装虚表指针的工厂函数在 `0x1883a634c`，指令序列是：分配 `0xb20` 字节、调用构造 `0x1883a3eb0` 且第 3、4 个参数为 0、把 `vtable + 0x10` 写入 `[x0]`、再把 `[x0 + 0xb18]` 清零（实测）。

26 里结构相同的工厂函数在 `0x184075600`：分配 `0x7530` 字节、调用构造 `0x184073a5c` 且第 3、4 个参数为 0、把 `vtable + 0x10` 写入 `[x0]`、再把 `[x0 + 0x7528]` 清零（实测）。它写入的是 `0x1ee97f868 + 0x10`。

其余两个成员也能一一对上：16.5 的 `0x1883a643c`（构造参数 0、1，随后调用一次）对应 26 的 `0x184075780`（构造参数 0、1，随后调用一次）；16.5 的 `0x1883a6528`（构造参数 2、2，先写基类虚表再写自身）对应 26 的 `0x184075914`（同样先写 `0x1ee97e408` 再写 `0x1ee97ee58`）（实测）。

### 字符串特征

`AppleCLCDDisplay` 有一处只有它实现的虚函数，会读环境或默认值 `CA_HEARTBEAT_RATE`。16.5 的四个成员里只有 `0x1d5b44520` 的第 93 号槽（偏移 `0x2d8`）引用这个字符串，函数在 `0x1882d3930`；26 的四个成员里只有 `0x1ee97f868` 的第 101 号槽（偏移 `0x318`）引用它，函数在 `0x183f380d8`（实测）。

两个函数体也一致：都从对象尾部那个被构造函数清零的字段读一个 double（16.5 是 `[x0 + 0xb18]`，26 是 `[x0 + 0x7528]`），再决定取默认值还是倒数（实测）。

### 判定

三条独立证据指向同一个结论：`0x1ee97f868` 是 26 的 `AppleCLCDDisplay` 虚表。构造函数形状、四个虚表的排列顺序、`CA_HEARTBEAT_RATE` 的唯一槽位，三者互相独立（推断，证据强度高）。

## 6. 四个已知槽在 26 上的位置

16.5 的四个函数在 26 里都能靠特征常量或函数体形状找到，并且在 26 的四个虚表里都落在同一个下标（实测），与 16.5 的行为一致。

`ignore_update_p` 的对照最直接。16.5 的实现是 21 条指令，先读 `this+0x233` 的第 4 位决定是否早退，再读 update 对象 `+0xf0` 的 `0xa` 位，最后把结果写进 `this+0x9f2` 的标志字并返回取反后的布尔值。

26 的实现在 `0x183efe30c`，把这个结构原样保留：读 `this+0x293` 的第 4 位早退，读 update 对象 `+0x130` 的 `0xa` 位，写入 `this+0x7368` 的字节，再用两次 `ldarb` 读 `[this+0x300]+4` 与 `+5` 做选择，最后 `eor w8,w8,#1` 后 `and w0,w8,#1` 返回。

```text
16.5  0x1882e0c90: ldrb w8,[x0,#0x233]     |  26  0x183efe30c: ldrb  w8,[x0,#0x293]
      0x1882e0c94: tbnz w8,#4,+0x4c        |       0x183efe310: tbnz  w8,#4,+0x3c
      0x1882e0c98: mov  w0,#0               |       0x183efe314: mov   w8,#0
      0x1882e0c9c: ret                     |       0x183efe318: b     +0x54
      0x1882e0ca0: ldr  w8,[x1,#0xf0]      |       0x183efe31c: ldr   x8,[x1,#0x130]
      0x1882e0ca4: mov  w9,#0xa            |       0x183efe320: mov   w9,#0xa
      0x1882e0ca8: ands w8,w8,w9           |       0x183efe324: ands  x9,x8,w9
      0x1882e0cac: cset w9,ne              |       0x183efe328: cset  w8,ne
      0x1882e0cb0: add  x10,x0,#0x9f2      |       0x183efe32c: mov   w10,#0x7368
      ...                                  |       0x183efe330: ldrb  w11,[x0,x10]
      0x1882e0ce0: eor  w0,w8,#1           |       0x183efe368: eor   w8,w8,#1
      0x1882e0ce4: ret                     |       0x183efe36c: and   w0,w8,#1
```

`begin_update` 的对照用常量 `0x3f80000000000000`：16.5 的 `0x1882ddda4` 在 `0x1882ddea4` 处有这条立即数，26 的 `0x183efb4d4` 在 `0x183efb5c0` 处有同一条（实测）。`finish_update` 的对照用开场形状：16.5 的 `0x1882c8568` 以 `stp d15,d14,[sp,#-0xa0]!` 打头、随后 `sub sp,sp,#0x720`；26 的 `0x183f5631c` 用同一个开场、`sub sp,sp,#0x7a0`（实测）。

`is_ready` 的对照只做到候选。16.5 的 `0x1882f0908` 末尾是 `tst x8,#4; cset w0,eq`，并调用一次带 `mov w2,#-0x7ffffffd` 的辅助函数；26 全文只有一个 `mov w2,#-0x7ffffffd`，在 `0x183f4fe54`，属于 `0x183f4fdfc`（虚表下标 30，偏移 `0xe0`）（实测）。但这个函数还引用字符串 `Display::complete_powering_on`，16.5 里没有这条字符串，函数体也比 16.5 的 `is_ready` 长。它可能是 `is_ready` 被内联进 `complete_powering_on`，也可能这个虚函数的位置换了含义，所以只记为候选（推断，证据不足）。

四个槽在 26 四个虚表里的一致性：`0x183efe30c`、`0x183efb4d4`、`0x183f5631c`、`0x183f4fdfc` 在 `0x1ee97d9b8`、`0x1ee97e408`、`0x1ee97ee58`、`0x1ee97f868` 四张虚表里都落在下标 44、53、54、30（实测），与 16.5 里四个成员共享同一下标的行为吻合。

### 槽 0x138 的实际内容

`0x1ee97f868 + 0x10 + 0x138 = 0x1ee97f9b0`，原始字 `0x80156cac04072d88`，解码为 `0x184072d88`（实测）。反汇编：

```text
0x184072d88: mov  w8,#0x7377
0x184072d8c: ldrb w0,[x0,x8]
0x184072d90: ret
```

它读的是 `this+0x7377` 的一个字节，和 `ignore_update_p` 的两次参数、标志位读改写都没有关系。26 上继续用槽 0x138 会在一个取字节的虚函数上装钩子，`inject.c` 里的 `expected` 比对会失败并打印 `left alone`，这与运行期日志一致。

## 7. 与运行期读数的对照

运行期在 `0x1d5b44520 + 0x148` 读到 `0x9907980677eb9604`，本机 26 缓存同一地址（`dyld_shared_cache_arm64e.27` 文件偏移 `0x1b90668`）的 8 字节是 `0x9907980697059604`（实测）。

两组值的高 32 位 `0x99079806` 与低 16 位 `0x9604` 相同，只有中间两个字节不同（`0x9705` 对 `0x77eb`）。按地址算，`0x1d5b44520` 在 26 缓存里属于 `ImagePlaygroundInternal.framework` 的 `__TEXT`（`0x1d5431000` 起），这一段是只读代码段。

从 6 个字节相同可以推断，运行期这份缓存的装载地址与静态地址一致，slide 为 0；2 个字节的差异说明设备上跑的缓存构建与本机 23G90 转储不完全一致，或者该页在运行期被改写过。两种情况都要求把启动期断言写进 `inject.c`，不能假定静态地址一定命中。

## 8. 对 `inject.c` 的改写建议

常量替换按下表进行，左侧是现有宏，右侧是 26 的取值。`EAGLServer` 与 `GLESContext` 的六处常量不在这一项范围内，仍需按同样方法单独定位。

| 宏与槽 | 16.5 | 26 |
|---|---|---|
| `VT_APPLE_CLCD_DISPLAY` | `0x1d5b44520` | `0x1ee97f868` |
| `is_ready` 槽 | `0xb0` | 候选 `0xe0`，先不上钩 |
| `ignore_update_p` 槽 | `0x138` | `0x150` |
| `begin_update` 槽 | `0x170` | `0x198` |
| `finish_update` 槽 | `0x178` | `0x1a0` |

对应的期望函数指针（26，静态地址）：`ignore_update_p` = `0x183efe30c`，`begin_update` = `0x183efb4d4`，`finish_update` = `0x183f5631c`。

启动期断言用差值形式，不依赖 slide 的具体数值。同一个缓存里的虚表地址与函数地址共享同一个 slide，所以「槽值减静态函数地址」应当等于「运行期虚表地址减静态虚表地址」。

```c
#define VT_APPLE_CLCD_DISPLAY_26  0x1ee97f868UL
#define SLOT_PTR(vt, off)  ((volatile uintptr_t *)((uintptr_t)(vt) + 0x10 + (off)))

/* 同一个缓存内的两个地址共享同一个 slide，只比较差值。 */
static int
slot_matches(uintptr_t vt_runtime, size_t off, uintptr_t fn_static)
{
	uintptr_t slot = *SLOT_PTR(vt_runtime, off);
	return slot - fn_static == vt_runtime - VT_APPLE_CLCD_DISPLAY_26;
}

static int
window_server_vtable_ok(void)
{
	uintptr_t vt = VT_APPLE_CLCD_DISPLAY_26;

	/* 头两个字：offset-to-top 与 typeinfo，26 上都是 0。 */
	if (((volatile uintptr_t *)vt)[0] != 0 || ((volatile uintptr_t *)vt)[1] != 0)
		return 0;
	return slot_matches(vt, 0x150, 0x183efe30cUL)	/* ignore_update_p */
	    && slot_matches(vt, 0x198, 0x183efb4d4UL)	/* begin_update */
	    && slot_matches(vt, 0x1a0, 0x183f5631cUL);	/* finish_update */
}
```

断言失败时按现有 `replace_virtual` 的约定整组跳过并打印原因，不要逐个槽试探。`is_ready` 的候选值不稳定，等真机确认后再加。

另外两条改写注意。第一，这四个槽在 26 的四个虚表里指向同一批函数，改一张虚表只影响从这张虚表发出的调用；运行期对象如果属于另外三个类，钩子不会被调用，所以需要先确认 `CAWindowServer` 实际创建的类。第二，磁盘上这些槽存的是 chained 编码（例如 `0x8014b59003efe30c`），运行期读到的是解码后的地址，断言比对的必须是解码后的值。

## 9. 未完成与替代路径

`is_ready` 的 26 位置没有确认。16.5 的识别特征（末尾 `tst #4; cset w0,eq`）在 26 的 320 个槽里一个都没有，候选 `0xe0` 的依据只有一处唯一的 `0x80000003` 常量，而该函数还带 `complete_powering_on` 的日志字符串。要确认它有两条路：等设备回来在真机上读对象虚表并单步；或者把 QuartzCore 抽成独立 Mach-O 后用 IDA 看交叉引用。

`EAGLServer`（16.5 `0x1d5b45c58`，62 槽）与 `GLESContext`（16.5 `0x1d5b3b540`）的 26 地址没有做。方法可以照搬：先按 16.5 的构造函数形状与槽位特征在 26 的候选虚表里找对应的一组，再用唯一字符串或常量特征确认。

IDA 交叉验证没有做成。idalib 打开主缓存文件直接失败，本机也没有 `ipsw`、`jtool2`、`dsc_extractor` 这类能把镜像抽成独立 Mach-O 的工具，`/usr/bin/dyld_info` 对主缓存文件报 `file not found`。可行的替代是写一个最小的提取器：按 images 表的地址与 `LC_SEGMENT_64` 把 QuartzCore 的段拷出来，再把 `__LINKEDIT` 按 `fileoff` 对齐写回去，产出一个能直接喂给 `llvm-objdump` 或 IDA 的文件。

2026-10-29 的后续工作见 [QuartzCore 静态补全](2026-10-29-quartzcore-static-followup.md)：提取器已落地并能被 otool、llvm-objdump 与 IDA 打开，三个已知槽已复核，`is_ready`、`EAGLServer`、`GLESContext` 的 26 位置有新结论和对应的否定证据。

## 10. 复现要点

全部结论可以从缓存文件重算，关键是三步：读主头 0x88／0x90 拿 images 表；合并每个子缓存头 0x10／0x14 指向的 32 字节 mapping 表做地址换算；按第 3 节的规则解码指针。

虚表扫描的判据是「16 字节零 + 连续指向本镜像 `__TEXT` 的已解码指针」，`min_slots` 取 3 以上。26 上 `__AUTH_CONST.__const` 的四个 320 槽虚表、16.5 上 `__DATA_CONST.__const` 的四个 246 槽虚表都能一次扫出来。

确认某个虚表属于哪个类，用构造函数；类名在这份缓存里用不上：没有本地符号（`localSymbolsOffset` 与 `localSymbolsSize` 都是 0，实测），导出表只有 C 符号（QuartzCore 26 导出 1351 个，16.5 导出 1206 个，实测），C++ 类名与 RTTI 字符串在整份缓存里搜不到（`AppleCLCDDisplay` 在缓存文件里 0 次命中，实测）。

以上脚本都放在 `/tmp/dsc26/`（`dsclib.py`、`vtscan2.py`、`insnindex.py`、`strmatch.py`、`imgmap.py`），本机临时文件，不入库；需要长期保留时应整理进 `hackios-xnu-kernel/tools/`。