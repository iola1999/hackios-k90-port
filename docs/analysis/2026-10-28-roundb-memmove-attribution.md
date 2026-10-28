# roundb 的 bad access pc 归属复核（2026-10-28）

一个离线子任务把 roundb 的 212 条 bad access 的故障 pc 定到 iOS 系统库 `libsystem_platform.dylib` 的 `_platform_memmove`，并据此要求改写 P1 的结论。本文逐条独立复核它的 8 个点。复核走的是与子任务不同的推导路径：缓存头部与 `imagesText` 数组自己解、subcache 的 mapping 表自己解、指令用 capstone 自己反汇编、分支拓扑自己扫全 `__TEXT`、日志侧的计数与相邻关系自己在单份快照的有序流里数。

结论先给：**归属成立，roundb 的故障 pc 不在我们的两个 dylib 里。** 8 个点里 7 个复核成立，第 6 点按 display 的 `nm -u` 证据重做后拆成两半：对驱动成立，对 AIR 库不成立，调用方是谁待一个有 bad access 的轮次的 `lr` 读数定（round C 全轮零故障，没有读数），另有 2 项子数据判不了。交接文档 §3 有三处事实错误，其中 slide 那一处是整条错误推理的根，已收进交接文档 §11 的更正清单。

## 1. 复核用到的工具与一处工具失败

`mcp__idalib__*` 这一组工具在本会话可用，但两个输入都打不开：`idb_open` 对 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/dyld_shared_cache_arm64e.77` 与对主缓存文件 `dyld_shared_cache_arm64e` 都返回 `Failed to open database`，两次都按 lead 的约束传了 `run_auto_analysis: false`、`build_caches: false`、`init_hexrays: false`，`idb_list` 之后是空会话列表，目录可写、没有 `.i64`／`.idb` 残留。该目录下 `.symbols` 文件是 **0 个**，另有一个 `dyld_shared_cache_arm64e.atlas`（2,790,670 字节，与主缓存同日 Sep 2 17:50）。IDA 的共享缓存装载器通常需要 `.symbols`，`.atlas` 是不是也要，两处都未验证，这是最可能的原因。将来若真要用 idalib 开这份缓存，先试两件事再决定投入：产出 `.symbols`，以及查清装载器要不要 `.atlas`。lead 已裁定本次不追，理由是下面这条替代路径够硬：第 4 到 6 点是用 capstone 5.0.7 加自解的缓存结构完成的，反汇编结果在本文里逐条给出原文，可复算，而第 4 点的函数边界用了三条独立证据（`udf #0` 填充给边界、`bl #+0x930` 给入口、入口的重叠检查给 memmove 的语义），比解 export trie 拿一个导出名更硬。真正需要 idalib 的场景只剩一个：`lr` 落在缓存里要给调用方命名，而那一步用 §4 的 `imagesText` 查表加 capstone 也能做。

复算用的四个入口：

```python
# 缓存头部（主文件 dyld_shared_cache_arm64e）
mappingOffset  = u32 @ 0x10   # 0x228
imagesTextOffset = u64 @ 0x88 # 0x21df8
imagesTextCount  = u64 @ 0x90 # 4315
sharedRegionStart = u64 @ 0xe0  # 0x180000000
sharedRegionSize  = u64 @ 0xe8  # 0x142cf8000
maxSlide          = u64 @ 0xf0  # 0x20000000
uuid                = 16B @ 0x58 # 46E741B7-0E75-3F19-A308-0464F4140B00

# imagesText 项，32 字节一项
uuid[16] | loadAddress u64 @+16 | textSegmentSize u32 @+24 | pathOffset u32 @+28

# 每个 subcache 文件自己的头部：mappingOffset @0x10、mappingCount @0x14
# mapping 项，32 字节一项： address u64 | size u64 | fileOffset u64 | maxProt u32 | initProt u32
```

搜索纪律按全队规则执行：共享缓存的字符串扫描用 python 流式 `bytes.find`，8 MiB 一块、块间保留 `len(pattern) − 1` 字节的重叠，85 个文件共 4.87 GiB，全程内存有界；没有对缓存用 `grep -a`，也没有用带 `.{0,N}` 上下文窗口的正则。

## 2. slide 是 `0xbc54000`

**复核成立。** lead 已核过日志侧（roundb 全轮 `slide 0x…` 只有 `0xbc54000` 一个值、出现 239 次，`0xb05000` 零命中），本文补镜像侧那一半。

`imagesText` 里 `/usr/lib/system/libsystem_kernel.dylib` 的 `loadAddress` 是 `0x232f09000`、`textSegmentSize` 是 `0x3bb20`，它在 subcache `dyld_shared_cache_arm64e.46` 的文件偏移 `0x6661000`。反汇编该镜像 `+0xcc0` 起的四个桩：

```
libsystem_kernel+0xcc0  mov x16, #-0x2e     ; -46 = pid_for_task
libsystem_kernel+0xcc4  svc #0x80
libsystem_kernel+0xcc8  ret
libsystem_kernel+0xccc  mov x16, #-0x2f     ; -47 = mach_msg2_trap
libsystem_kernel+0xcd0  svc #0x80
libsystem_kernel+0xcd4  ret
libsystem_kernel+0xcd8  mov x16, #-0x30     ; -48 = macx_swapon
```

`+0xccc` 的 `mov x16, #-0x2f` 就是子任务说的 `movn x16,#46`（`movn` 写入 `~46 = −47`，capstone 渲染成立即数形式），`+0xcd4` 是那个桩的 `ret`。`hackios-xnu-kernel/out/xnu12377/osfmk/mach/syscall_sw.h:128` 写的是 `kernel_trap(mach_msg2_trap, -47, 8)`，trap 号对上。所以 roundb 日志里那个 pc `0x23eb5dcd4` 减 slide `0xbc54000` 得 `0x232f09cd4`，正是 `mach_msg2_trap` 桩的 `ret`，slide 值成立。

## 3. 缓存的三个边界数，以及交接文档错在哪

**复核成立。** 三个数各自量的是不同的东西：

| 数 | 值 | 来源 | 量的是什么 |
|---|---|---|---|
| `imagesText` 上界 | `0x2adb74640` | 4315 项里 `max(loadAddress + textSegmentSize)`，取自最后一项 `/usr/lib/updaters/libPS190Updater.dylib` base `0x2adb5b000` + size `0x19640` | 缓存里所有镜像 `__TEXT` 段的最高地址 |
| 实际映射上界 | `0x2c2cf4000` | 85 个文件全部 mapping 项的 `max(address + size)` | 缓存实际占用的地址范围末端 |
| 声明的共享区末端 | `0x2c2cf8000` | `sharedRegionStart 0x180000000 + sharedRegionSize 0x142cf8000` | 内核预留的共享区末端，比实际映射多一页 |

`maxSlide` 是 `0x20000000`，roundb 的 `0xbc54000` 在它范围内。

交接文档 §3 那句「`0x2b0fb59c0 − 0xb05000 = 0x2b04b09c0` 超出共享缓存上界 `0x2adb74640`」有两处错：

- slide 用了 `0xb05000`，正确值是 `0xbc54000`。
- 拿 `0x2adb74640` 当「共享缓存上界」，而它是 `__TEXT` 镜像区的上界；缓存的映射上界是 `0x2c2cf4000`。即使沿用错误的 slide，`0x2b04b09c0` 也落在 `0x180000000..0x2c2cf8000` 里，只是落在 `__TEXT` 镜像区之外。

用正确的 slide 重算，两个 pc 都落进 `__TEXT` 镜像区：

| pc | 减 `0xbc54000` | 在 `__TEXT` 镜像区内 | 在共享区内 |
|---|---|---|---|
| `0x2b0fb59c0` | `0x2a53619c0` | 是 | 是 |
| `0x2b0fb5ad4` | `0x2a5361ad4` | 是 | 是 |

减错误的 `0xb05000` 得 `0x2b04b09c0` 与 `0x2b04b0ad4`，两者都在共享区内、都在 `__TEXT` 镜像区外。**「超出共享缓存上界」这个结论在两种 slide 下都不成立**，它是把镜像区上界当成缓存上界读出来的。

## 4. 归属：`libsystem_platform.dylib` 的 `+0x9c0` 与 `+0xad4`

**复核成立**，四个数各自独立解出：

| 量 | 子任务给的值 | 本文独立解出的值 | 来源 |
|---|---|---|---|
| `__TEXT` base | `0x2a5361000` | `0x2a5361000` | `imagesText` 第 3544 项 |
| `textSegmentSize` | `0x8434` | `0x8434` | 同上 |
| subcache 与文件偏移 | `.77` 的 `0x28e1000` | `.77`，mapping[0] `address 0x2a2a80000`、`size 0x6f0c000`、`fileOffset 0`，`0x2a5361000 − 0x2a2a80000 = 0x28e1000` | `.77` 头部 mapping 表 |
| 镜像内偏移 | `+0x9c0`、`+0xad4` | `0x2a53619c0 − 0x2a5361000 = 0x9c0`、`0x2a5361ad4 − 0x2a5361000 = 0xad4` | 减法 |

从 `.77` 的 `0x28e1000` 读出 `0x8434` 字节，capstone 反汇编，两条故障指令与子任务说的逐字一致：

```
+0x09c0  220c40ac  ldnp q2, q3, [x1]      ; 从 x1 读 32 字节
+0x0ad4  268440f8  ldr  x6, [x1], #8      ; 从 x1 读 8 字节并后移
```

函数身份与边界用三条独立于导出表的证据确定，所以本文没有去解 export trie：

- **边界由对齐填充给出。** `+0x928` 与 `+0x92c` 是 `udf #0`（全 0 填充），`+0xbf8` 与 `+0xbfc` 同样是 `udf #0`。函数体因此是 `+0x930..+0xbf7`。
- **入口由调用点给出。** `+0x90c` 是 `bl #0x2a5361930`，全 `__TEXT` 里从函数体外部指向 `+0x930` 的 `bl` 共 20 条（`+0x8e8`、`+0x90c`、`+0x12a0`、`+0x12bc`、`+0x1304`、`+0x137c`、`+0x1390`、`+0x1d90`、`+0x1da0`、`+0x1db0`、`+0x20ac`、`+0x20bc`、`+0x20cc`、`+0x27f8`、`+0x2840`、`+0x2854`、`+0x300c`、`+0x4d68`、`+0x6b40`、`+0x6b60`）。
- **语义是 memmove 而不是 memcpy。** 入口三条指令是重叠检查：

```
+0x0930  sub  x3, x0, x1     ; x3 = dst - src
+0x0934  cmp  x3, x2         ; 与 len 比
+0x0938  b.lo #+0xb00        ; (dst-src) < len 无符号成立 → 走 +0xb00 的倒序拷贝
```

  `+0xb00` 之后那一块先把 `x4 = dst + len`、`x1 = src + len`，再从末端往回拷（`ldp q2,q3,[x1,#-0x20]`、`stnp q2,q3,[x4,#-0x20]`），是倒序实现。`memcpy` 不需要重叠检查，所以这个函数是 `memmove`。紧邻的下一个函数 `+0xc00` 开头是 `mov x2,x1; eor v0.16b,v0.16b,v0.16b; eor x1,x1,x1; mov x3,x0`，把 `x1` 清零后按长度填充，形状是 `bzero`，与子任务说的「下一个导出 `_platform_bzero`／`_bzero` 在 `+0xc00`」一致。

`_platform_memmove` 这个导出名本身本文没有独立解出（没解 export trie），它的依据是上面的语义与边界，加上子任务从 `.83.dyldlinkedit` 文件偏移 `0xabc73c8` 的 trie 解出的 `+0x930`。名字这一项标**成立（间接）**。

## 5. 长度分派：两个 pc 各自只在一段长度区间里到达

**复核成立。** 入口之后的分派链：

```
+0x093c  mov  x3, x0
+0x0940  cmp  x2, #0x40              ; len 与 64 比
+0x0944  b.lo #+0xadc                ; len < 64 → 小拷贝循环
+0x0948  sub  x4, x1, x0
+0x094c  cmp  x4, x2
+0x0950  b.lo #+0xa14                ; 源与目标相距不足 len 的另一类重叠 → 走 +0xa14 那块
+0x0954  cmp  x2, #4, lsl #12        ; len 与 16384 比
+0x0958  b.lo #+0x9b8                ; 64 ≤ len < 16384 → 走 +0x9b8
+0x095c  add  x3, x3, #0x20          ; len ≥ 16384 从这里继续
+0x0960  and  x3, x3, #~0x1f
+0x0964  ldnp q2, q3, [x1]           ; len ≥ 16384 的第一次源读取
```

两条路径各自的第一次源读取：

| pc | 到达条件 | 前驱 |
|---|---|---|
| `+0x9c0` `ldnp q2,q3,[x1]` | `64 ≤ len < 16384`，且 `dst − src ≥ len` | `+0x958` 的 `b.lo` 跳到 `+0x9b8`，`+0x9b8`／`+0x9bc` 把 `x3` 向下对齐到 32 之后顺序执行到 `+0x9c0`，`x1` 未改动 |
| `+0xad4` `ldr x6,[x1],#8` | `len < 64` | `+0x944` 的 `b.lo` 跳到 `+0xadc`，`+0xadc` 是 `subs x2,x2,#8` 接 `+0xae0` 的 `b.hs #+0xad4`，第一次迭代进 `+0xad4`，`x1` 未改动 |

分支拓扑扫全 `__TEXT` 的结果支持「只有这两条路」：从函数体外部指进 `+0x930..+0xbf8` 的分支共 20 条，**全部指向入口 `+0x930`**，没有一条跳进函数体中间；函数体内没有跳出体外的分支；指向 `+0xad4` 的分支只有 `+0xae0` 的循环回边一条，指向 `+0x9c0` 的分支为 0 条。所以任何调用方都必经 `+0x940` 与 `+0x954` 这两次长度比较，绕不过去。

由此子任务的关键推论成立：**两处都从 `x1` 读、都发生在该路径的第一次源访问，所以故障地址就是调用方传给 `memmove` 的 `src` 实参本身，`src + k` 的形式排除。** 长度也被约束住：14 起事件的 pc 是 `+0x9c0`（`64 ≤ len < 16384`），1 起是 `+0xad4`（`len < 64`），见第 7 节。

## 6. 排除我们自己那次拷贝：对驱动成立，对 AIR 库不成立

这一节按 display 的 task-15 证据重做过一遍。子任务原来那句「出错的 memmove 不是我们调的」要拆成两半：**对 `libredwoodmetal.dylib` 成立，对 `libredwoodair.dylib` 不成立**，调用方是谁在 round C 的 `lr` 落地之前是未知。

### 6.1 子任务给的两条理由与镜像不符

- 子任务说「`_platform_memcpy` 是另一个导出（`+0x6af4`）」。`+0x6af4` 那个函数是 4 参的，形状如下：

```
+0x6af4  cbz  x3, #+0x6b58 附近     ; 第 4 个参数为 0 就直接返回
+0x6af8  pacibsp
+0x6b0c  mov  x21, x3
+0x6b10  mov  x20, x1
+0x6b14  mov  x19, x0
+0x6b18  mov  x0, x1               ; 把 (x1,x2,x3) 挪到 (x0,x1,x2)
+0x6b1c  mov  x1, x2
+0x6b20  mov  x2, x3
+0x6b24  bl   #+0x2920             ; 三参查找，形状是 memchr(s, c, n)
+0x6b28  cbz  x0, #+0x6b54
+0x6b2c  sub  x8, x0, x20          ; 找到的位置 − 起始
+0x6b30  add  x21, x8, #1          ; 长度 = 差值 + 1
+0x6b34  mov  x0, x19              ; dst
+0x6b38  mov  x1, x20              ; src
+0x6b3c  mov  x2, x21              ; len
+0x6b40  bl   #+0x930              ; memmove
```

  先按长度找终止字节、再把「找到的位置 − 起始 + 1」当长度调 `memmove`，这是 `strlcpy` 一类的形状，`memcpy(dst, src, n)` 是三参且不需要先查找。
- 子任务说「扫了 `+0x6af4..+0x930` 全部分支确认没有跳进 memmove 区间」。这个区间里有 2 条 `bl` 进 memmove：`+0x6b40` 与 `+0x6b60`。

### 6.2 驱动这一半：排除成立

`nm -u -arch arm64e` 对 roundb 实际装车的那份 `libredwoodmetal.dylib`（sha256 前 8 位 `9d66dd36`，241,488 字节；`out/ios26-resume/bbmetal-device/` 与 `…/root/lib/` 两个路径下同一份，sha256 相同）的未定义符号里只有 `_memcpy`，**没有 `_memmove`，也没有 `_bcopy`**。驱动根本不导入 `memmove`，它调不到那两个 pc。

长度区间也不相交，这一条独立于导入表：驱动的拷贝长度是 32768 与 65536，都 `≥ 16384`，进 memmove 会走 `+0x95c` 到 `+0x964`；两个故障 pc 是 `+0x9c0`（要求 `64 ≤ len < 16384`）与 `+0xad4`（要求 `len < 64`）。15 起事件里 14 起的 pc 是 `+0x9c0`、一起是 `+0xad4`，全部落在 `len < 16384` 一侧。

`hackios-xnu-kernel/userland/src/redwoodmetal.m:2637` 调的是 `memcpy`，紧随其后的 `:2641` 那条打印每轮都出来，说明那次拷贝执行完了。这条只证明驱动那次 `memcpy` 自己没崩，承担排除的是上面两条。`redwoodmetal.m:2641` 打的长度就是 `memcpy` 用的那个 `length`，所以「日志长度等于实参长度」这个前提在本轮成立。

### 6.3 AIR 库这一半：排除不成立

同一份 `nm -u` 对 `libredwoodair.dylib`（`d7b9ced5`，13,983,936 字节）的未定义符号里有 **`_memmove`**，另有 `_memcpy`、`___memcpy_chk`、`___memset_chk`、`_memset`、`_memset_pattern16`（display 的清单少了 `___memset_chk` 一项，其余一致）。

调用点数从镜像里直接数出来，不依赖源码检索：`objdump -d --macho` 会把每条经 stub 的调用注解成 `; symbol stub for: <名>`，把全部注解行收下来再按符号计数，得 6667 个调用点、181 个不同的被导入符号，其中：

| 符号 | 调用点数 | stub 地址 |
|---|---|---|
| `_memmove` | **7** | `0x4316f0` |
| `_memcpy` | 394 | `0x4316e0` |
| `___memcpy_chk` | 27 | `0x431280` |
| `_memset` | 21 | `0x431700` |
| `_memset_pattern16` | 15 | `0x431710` |
| `___memset_chk` | 1 | `0x431290` |
| `_bcopy` | 0 | — |

7 个 `_memmove` 调用点的地址（dylib 自己的 vmaddr，`__text` 起于 `0x4000`）：`0x1d6008`、`0x1d69f8`、`0x212a7c`、`0x260534`、`0x2605fc`、`0x3a7f8c`、`0x3db3ac`。

子任务那句「`userland/src/` 与 `tools/mesa/air/` 里 `memmove`／`bcopy` 出现 0 次」在它自己那个范围内是对的，但那个范围覆盖不到 AIR 库的主体。库的构成看 `hackios-xnu-kernel/tools/mk-mesa.sh`：`:144-145` 把 `tools/mesa/air` 拷成 `mesa-$VERSION/src/compiler/air`，`:205` 链 `src/gallium/drivers/freedreno/libredwoodair.dylib`。该目标的 ninja 链接语句里只有 1 个目标文件（`air_metal.c.o`）加一长串静态库：`libgallium.a`、`libnir.a`、`libcompiler.a`、`libmesa_util.a`、`libmesa_util_simd.a`、`libblake3.a`、`libmesa_util_c11.a`、`libgalliumvl_stub.a`、`libws_null.a`、`libfreedrenowinsys.a`、`libair.a`、`libsoftpipe.a`、`libfreedreno.a`、`libfreedreno_common.a` 等。所以源码检索的正确范围是这些静态库对应的目录，不是 `src/compiler/air` 一个目录。

按链接进来的目录逐个检索 `memmove`／`bcopy` 调用点（`--include` 限定 `.c`／`.cpp`／`.cc`／`.h`）：

| 目录 | 调用点 | 文件数 |
|---|---|---|
| `src/compiler/air` | 0 | 0 |
| `src/gallium/drivers/freedreno` | 0 | 0 |
| `src/gallium/drivers/softpipe` | 0 | 0 |
| `src/gallium/winsys/freedreno` | 0 | 0 |
| `src/c11` | 0 | 0 |
| `src/util` | 3 | 3 |
| `src/compiler`（`air` 之外） | 4 | 4 |
| `src/freedreno` | 1 | 1 |
| `src/gallium/auxiliary` | 1 | 1 |

9 处源码调用点：`src/util/log.c:541`、`src/util/parson.c:1930`、`src/util/u_printf.c:226`、`src/compiler/spirv/vtn_bindgen2.c:75`、`src/compiler/glsl/gl_nir_link_uniform_blocks.c:429`、`src/compiler/nir/nir_opt_load_store_vectorize.c:530`、`src/compiler/glsl_types.c:547`、`src/freedreno/ir3/ir3_parser_support.c:237`、`src/gallium/auxiliary/draw/draw_gs.c:352`。

镜像里 7 个调用点对源码里 9 处，两个数不相等，差值的原因未查，可能的成分有三类：某些源文件所在的目标文件没被链进来或被 dead-strip（`vtn_bindgen2.c` 属 SPIR-V、`draw_gs.c` 属几何着色器路径，都不一定进这个 target）；编译器为结构体赋值一类操作生成的 `memmove` 调用在源码里没有对应写法；`bcopy` 在头文件里展开成 `memmove` 会让源码侧多算。这三个都未逐个验证，所以这 9 处只作为候选清单，读不成「7 个调用点就是这 9 处里的 7 处」。

### 6.4 round C 的 `lr` 怎么把这 7 个调用点分开

新格式串在行尾打了 `lr`（`$13`），它就是调用方的返回地址。memmove 函数体内没有跳出体外的分支（第 5 节的扫描结果），所以故障时刻的 `lr` 是调用方那条 `bl` 的下一条指令地址，即上表 7 个调用点各加 4：

| 调用点 | 预期 `lr`（dylib 内 vmaddr） | 低 12 位 |
|---|---|---|
| `0x1d6008` | `0x1d600c` | `0x00c` |
| `0x1d69f8` | `0x1d69fc` | `0x9fc` |
| `0x212a7c` | `0x212a80` | `0xa80` |
| `0x260534` | `0x260538` | `0x538` |
| `0x2605fc` | `0x260600` | `0x600` |
| `0x3a7f8c` | `0x3a7f90` | `0xf90` |
| `0x3db3ac` | `0x3db3b0` | `0x3b0` |

7 个低 12 位互不相同，而 dylib 的加载地址是页对齐的，所以给定一个运行时 `lr`，7 个候选里只有一个能让 `lr − 预期值` 页对齐，那一个就是调用点，差值就是 `libredwoodair.dylib` 的加载地址。这一步不需要内核另外打 AIR 库的基址。

`lr` 落在 `libredwoodair.dylib` 之外时按读数规则文档 §3.7 的三步走；落在 `libredwoodmetal.dylib` 与 6.2 的导入表冲突，出现就说明「`_platform_memcpy` 与 `_platform_memmove` 是两个独立实现」这条要重查，而 6.1 已经查出子任务对 `+0x6af4` 的定性是错的，所以这个分支值得当真。


## 7. 故障地址分类与事件口径

**全部复核成立**，五个数逐个对上：

| 量 | 子任务 | 本文 | 口径 |
|---|---|---|---|
| raw 跨快照求和 | 212 | 212 | `s[0-9]*.log`，每份快照各数一遍再相加 |
| raw 加 `hung-held.log` | 225 | 225（`hung-held.log` 多 13 条） | 同上再加收尾那一份 |
| 唯一行 | 11 | 11 | 跨快照按整行去重 |
| 不同 (故障地址, pc) 组合 | — | 11 | 与唯一行同数，说明去重合并的就是同组合的重复 |
| 事件数 | 15 | 15 | 每条 bad access 之后 5 行内第一条 `redwood: proc backboardd pid N died on signal 11 code 11` 的 pid，跨轮去重 |

15 个事件 pid 是 `{38, 84, 99, 124, 140, 153, 167, 187, 197, 212, 221, 235, 243, 257, 265}`，与该轮 `redwood: backboardd pid N exited code -1 reason 2` 的 15 个 pid **完全相同**。两个独立来源（故障后紧跟的死亡行、进程退出行）给出同一个 15 代集合，事件口径因此站得住：每一代 backboardd 崩一次，一次故障对应一次死亡。

这个 15 与另一处出现的 15 无关，写结论时不要对上。`hackios-xnu-kernel/userland/src/redwoodmetal_blit.inc:35-38` 的注释写着「A selector nobody answers aborts the process, and backboardd died fifteen times in one run on -generateMipmapsForTexture: before anything was drawn」，那是没人应答的 selector 导致 `abort()`，信号 6，发生在绘制之前，且已经由该文件里的转发实现修掉；roundb 这 15 起是 `died on signal 11 code 11`，信号 11，发生在已经画出内容之后。两个数相同，成因、信号、发生时机都不同。本文与读数规则文档里凡出现 15 的地方都带着 `signal 11 code 11` 或 `reason 2`，两份文档对 `signal 6`、`abort`、`generateMipmaps`、`selector` 四个词的检索都是零命中。

11 个唯一故障地址按形式分类，事件口径的分布与子任务一致（小整数 2、ASCII 4、打包整数样 9、正常堆地址 0）：

| pid | 故障地址 | pc | 类 | 还原 |
|---|---|---|---|---|
| 38 | `0x1` | `0x2b0fb5ad4` | 小整数 | — |
| 84 | `0x21f800010003` | `0x2b0fb59c0` | 打包整数样 | — |
| 99 | `0x63756f5474656b63` | `0x2b0fb59c0` | ASCII | `cketTouc` |
| 124 | `0x80000c00000000` | `0x2b0fb59c0` | 打包整数样 | — |
| 140 | `0x80000c00000000` | `0x2b0fb59c0` | 打包整数样 | — |
| 153 | `0x21f800010493` | `0x2b0fb59c0` | 打包整数样 | — |
| 167 | `0x80000c00000000` | `0x2b0fb59c0` | 打包整数样 | — |
| 187 | `0x80000c00010000` | `0x2b0fb59c0` | 打包整数样 | — |
| 197 | `0x80000c00010000` | `0x2b0fb59c0` | 打包整数样 | — |
| 212 | `0x2e697269732e656c` | `0x2b0fb59c0` | ASCII | `le.siri.` |
| 221 | `0x10000` | `0x2b0fb59c0` | 小整数 | — |
| 235 | `0x21f80001083f` | `0x2b0fb59c0` | 打包整数样 | — |
| 243 | `0x616964656d2e656c` | `0x2b0fb59c0` | ASCII | `le.media` |
| 257 | `0x2e697269732e656c` | `0x2b0fb59c0` | ASCII | `le.siri.` |
| 265 | `0x82b00c2a010000` | `0x2b0fb59c0` | 打包整数样 | — |

每个 pid 只有一个故障地址，15 个事件对 11 个不同地址，重复的是 `0x80000c00000000`（3 起）、`0x80000c00010000`（2 起）、`0x2e697269732e656c`（2 起）。

「正常堆地址 0 起」的判据复核成立：该轮 backboardd 自己的数据地址在 `0x100000000..0x108000000`，共享缓存映射在 `0x180000000..0x2c2cf4000`，11 个地址没有一个落在这两个区间里。

两处形态上的规律，作为线索记下来，未定性：

- 三个 `0x21f80001xxxx` 共享高 32 位 `0x21f80001`，低 16 位分别是 `0003`、`0493`、`083f`。
- `0x10000` 等于 65536，与 `redwoodmetal.m:2408` 的 `NOCOPY_LIMIT` 同值；`0x80000c00010000` 与 `0x82b00c2a010000` 的低 24 位也含 `010000`。

## 8. 上下文对齐

**复核成立，口径是单份快照的有序流。** 相邻关系只在一份快照内部成立，跨快照拼接会破坏它，所以下面每个数都是逐份快照数完再相加，不是对合并结果数的：

| 量 | 子任务 | 本文 |
|---|---|---|
| 流内 bad access 行总数 | 225 | 225 |
| 上一行以 `tl: w ` 开头 | 217 | 217 |
| 上两行含 `rwa buffer: copied` | 209 | 209 |
| `copied` 行总数 | 1775 | 1775 |
| 其后 4 行内出现 bad access 的 `copied` 行 | 209（11.8%） | 209（11.8%） |

正反两个方向都是 209，比例 11.8%。这个数的读法要限定：崩溃与 `copied` 在时间上挨着，而 88.2% 的 `copied` 之后没有崩溃，所以「每次拷贝都导致崩溃」不成立；成立的是「崩溃前紧邻的那几行里有拷贝」。`tl: w` 那一行夹在中间，217 对 225 说明这个位置关系在这一轮里几乎恒定。

按协议 §5，同一时刻的两条打印只证明它们一起出现。要把「拷贝路径与崩溃相关」从相邻推到因果，现在手上只有 freeze 轮 0 起对 roundb 15 起这一个对照，样本是一对轮次，不足以定因果。

## 9. 共享缓存里的字符串命中

**部分成立，两项判不了。** 缓存位置与身份先更正：lead 早先说的「本地没有解出的缓存文件、缓存只在 `userland/system26.apfs` 里」不成立，实际位置是 `hackios-xnu-kernel/ios26/23G90__iPhone18,3/`，85 个文件、4.87 GiB、UUID `46E741B7-0E75-3F19-A308-0464F4140B00` 与主缓存头部 `+0x58` 的 16 字节一致。这一条已经写进读数规则文档的旧版本当作「未搜范围」，要改。

用 python 流式 `bytes.find` 扫全部 85 个文件，块 8 MiB、块间保留 `len(pattern) − 1` 字节重叠：

| 串 | 子任务 | 本文 | 结论 |
|---|---|---|---|
| `le.siri.` | 1958 命中 | 1958 字节出现 | 成立 |
| `cketTouc` | 23 命中 | 23 字节出现 | 成立 |
| `le.media` | 565 命中 | 567 字节出现 | 差 2，未定性 |
| `PocketTouches` | — | 8 字节出现 | 本文补的 |
| 1510 个不同串、约 250 个镜像 | 给出 | 未复现 | 判不了 |

`le.media` 差 2 条的原因未查，可能是分块边界处理或统计对象不同（字节出现次数与「命中」的定义）。这个差不影响任何结论：缓存里存在这些串这件事，1958 与 567 都远超 0。「1510 个不同串」与「约 250 个镜像」需要先从命中位置抽出完整字符串再按镜像归属，本文没有做这一步，标判不了。

对读数规则的影响：`backboardd` 的地址空间里有共享缓存，缓存里 `le.siri.` 有 1958 处，所以故障地址里那段 ASCII 的来源不能只按 SpringBoard 主二进制的内嵌 plist 解释，候选至少包含缓存内约 250 个镜像（这个数本文未复现）。读数规则文档 §5.1 的「未搜范围是 dyld 共享缓存」那句要删掉，换成已搜与命中数。

## 10. 复核结果汇总

| 点 | 结论 | 差异 |
|---|---|---|
| 1 slide `0xbc54000` | 成立 | 无 |
| 2 缓存本地位置 | 成立 | lead 早先的说法不成立，已更正 |
| 3 `0x2adb74640` 与 `0x2c2cf4000` | 成立 | 交接文档 §3「超出共享缓存上界」在两种 slide 下都不成立 |
| 4 归属 base／size／偏移／两条指令 | 成立 | 导出名 `_platform_memmove` 标成立（间接），本文未解 export trie |
| 5 长度分派与「故障地址就是 src」 | 成立 | 无 |
| 6 排除我们那次拷贝 | 对驱动成立，对 AIR 库不成立 | `nm -u`：驱动（`9d66dd36`）只有 `_memcpy`，AIR 库（`d7b9ced5`）有 `_memmove`，镜像里 7 个调用点。子任务的两条理由也不成立：`+0x6af4` 是 4 参的 `strlcpy` 形状而非 `memcpy`，`+0x6af4..+0x930` 里有 2 条 `bl` 进 memmove 而非 0 条。**调用方是谁在 round C 的 `lr` 落地之前是未知** |
| 7 分类与事件口径 | 成立 | 无，15 个事件 pid 与 `exited code` 的 15 代集合相同 |
| 8 上下文对齐 | 成立，单份快照口径 | 无 |
| 9 缓存字符串命中 | 部分成立 | `le.media` 565 对 567；「1510 个不同串」「约 250 个镜像」判不了 |

交接文档需要更正的三处：slide `0xb05000` 应为 `0xbc54000`；两个 pc 的距离是 `0x114` 而非 `0x10c`；「超出共享缓存上界」这个结论作废，正确的读法是两个 pc 都在缓存的 `__TEXT` 镜像区内，落在 `libsystem_platform.dylib` 的 `_platform_memmove` 里。

## 11. 对 round C 判据与后续计划的影响

三条，按影响大小排：

- **P1 的诊断价值下降，round C 仍要跑。** round C 新增的 region 后备文件名会把 `libsystem_platform.dylib` 直接打出来，与本文的离线推导互为交叉验证；exec 基址行会把「保存的 pc 不指向有效指令」那类（冻结线里 tid 306 的 `0x105f00cd8`）分开。这两个读数在归属已经离线确定的情况下仍有价值，因为它们是每轮都有的直接读数，而本文的推导依赖本地这份缓存与 roundb 那一个 slide 值。round C 的内核在这一节写完之后再换过一次（源码提交 `5c9f563`、sha256 `cf1502f5632284af…`），bad access 行在行尾追加了 `lr`／`x0`／`x1`／`x2` 四列，第 6 节留下的「调用方是谁」因此本轮就能定，不必等 round D。
- **P2 的方向要改，改到调用方。** 故障发生在系统库的 `memmove` 里，`src` 实参本身是个非法值（15 起里 4 起是字符串字节、9 起是打包整数样、2 起是小整数），所以问题在「谁把这样的值当 `src` 传给了 `memmove`」，落在调用方而不在拷贝实现。调用方候选按第 6 节分成两半：驱动排除（不导入 `_memmove`，且长度区间不相交），AIR 库不排除（导入 `_memmove`，7 个调用点）。下一步不是在源码里猜，是等 round C 的 `lr`，用第 6.4 节那套页对齐反解直接定到 7 个里的哪一个。CA 侧（共享缓存里的调用方）是第二类候选，`lr − slide` 落进缓存区间时按 `imagesText` 查表命名。
- **round D 的「内核加不节流故障计数器」必要性下降。** 邻接法已经能把事件数精确恢复到 15 起，且与 `exited code` 的 15 代集合独立吻合，那个计数器只剩交叉验证价值，不值得为它单独重建内核。共享缓存起止的设备侧直接读数那一条仍然值得排：本文的三个边界数是从本地缓存文件解出来的，设备侧没有对应读数，而 slide 每轮都变；离线这条路已经走通，所以它的价值从「没有它就判不了」降成「不必依赖本地这份缓存」。

读数规则文档已按本文改的六处：§1 的内核身份与两个库的 `nm -u` 结论、§2 的格式串与 19 个字段加三条自我否证判据、§3.2／§3.3 的候选集合分成 pc 与 lr 两组并加缓存查表那一步、§3.5 的三口径并列、§3.7 的 `lr` 归属三步、§4 的 slide 与缓存边界、§5.1 的缓存已搜与命中数、§9.4 的插桩状态、§12 里不节流计数器那一行的必要性。

## 12. roundb 的帧数据是在插桩开着的条件下采的

`air-build-record.json` 的 `library_sha256` 是 `d7b9ced5a115c08ca17c23e7322a9505c2c6352b3c9660a0d51beece91102e5f`，与 roundb 装车那份 AIR 库同一个值，它的 `holds` 块里有 `"perf draw: timing on": true`。roundb 的日志证实它在跑：`perf draw: timing on, frames over 6000 us are printed, 128 frames per summary` raw 866 条、唯一 1 条，`perf driver <N> us: <M> draws` 汇总行 raw 44 条，`perf driver worst:` raw 88 条、唯一 6 条。

插桩内容按 26 线已提交的 `hackios-xnu-kernel/tools/mesa/draw-perf.patch`（700 行）：时钟 `mach_absolute_time() / 1000`，与内核 `tl:` 行同一个钟；每次 draw 记 8 个时间点；每 128 帧一条汇总；每帧留最慢的 2 次 draw；慢帧阈值 6000 µs。

所以本文第 7、8 两节的所有计数都在插桩开着的条件下取得，第 8 节那个「217 条的上一行是 `tl: w`、209 条的上两行是 `copied`」的相邻关系里，夹在中间的日志流本身比无插桩时更密。这不改变任何计数的正确性（计数按行数和行序数，与插桩无关），但改变一件事：`copied` 与 bad access 之间那 4 行窗口里能容纳的其它打印变多了，所以「随后 4 行内」这个窗口在插桩关掉之后会对应更长的时间跨度，两个条件下的 11.8% 不可直接比。

26 线有意携带这份插桩，16.5 那条参照线不得携带，规则在 `hackios-xnu-userland/tools/mesa/NOTE.md`：`tools/mesa/*.patch` 会被 16.5 的 `mk-mesa.sh:106` 用通配符自动收下，而所有性能对比都以 16.5 为参照。两条规则各自成立，不要互相引用。读数规则文档 §9.4 记了验收轮必须关掉插桩这一条。
