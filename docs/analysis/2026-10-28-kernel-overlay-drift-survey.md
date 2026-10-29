# 内核 overlay 与构建树的双向差异普查

2026-10-28，display。这份文档记一次对账：仓库里手工维护的内核 overlay（`hackios-xnu-kernel/xnu/files/` 与 `xnu26/patches/`）与实际用来构建的那棵树（`hackios-xnu-kernel/out/xnu12377/`）之间，两个方向各有哪些不一致，每一处的机制是什么，用什么命令查出来的。全部离线核出，构建与设备都没有碰。

对账在 2026-10-28 完成，落地提交是内核仓 `2142061`。本文引用的行号与尺寸都以那一天两侧的状态为准。

## 1. 两侧是什么，为什么会对不上

三个位置各承担一件事：

| 位置 | 内容 | 谁写它 |
|---|---|---|
| `xnu/files/` | 从红杉（xnu-8796）那条线沿用下来的内核文件，159 个 | 手工维护，两条线共用 |
| `xnu26/patches/` 与 `xnu26/files/` | iOS 26 这条线对 Apple 原始文件的改动（73 个 patch）与新增文件（2 个 bcm2837 文件） | `xnu26/export.sh` 生成 |
| `out/xnu12377/` | 实际构建的那棵树，分支 `redwood26` | `xnu26/apply.sh` 铺一次，之后由人直接改 |

`xnu26/apply.sh` 把树铺出来一次：Apple 标签 `xnu-12377.121.6`（BASE `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`）→ 建分支 `redwood26` → 把 `BUILD/` 写进 `.git/info/exclude` → 按 `xnu26/patches/series` 依次 `git apply` 73 个 patch → `cp -P -p` 把 `xnu/files/` 的 157 个文件（减去 `xnu26/files.skip` 里的一项 `osfmk/arm64/kpc.c`）拷进去 → `cp -R -P -p xnu26/files/.` 拷那 2 个文件。

**铺出来之后没有任何一步会再同步这棵树。** 守卫在 `xnu26/apply.sh:19`：

```
[ -e "$DIR" ] && { echo "apply.sh: $DIR already exists; not touching it" >&2; exit 1; }
```

反方向只有 `xnu26/export.sh`，它写仓库这一侧：重新生成 `xnu26/patches/`（对 BASE 有改动的每个 Apple 文件一个 patch，先 `rm -rf patches.new`（`:19`）再 `mkdir`（`:20`）再 `rm -rf patches`（`:29`），命名 `NN-<路径里的 / 换成 %>.patch`）与 `xnu26/files/`（相对 BASE 新增或未跟踪的文件，与 `xnu/files/$f` 用 `cmp -s` 相同就跳过）。它有一个 JUNK 正则排除 `BUILD/`、`__pycache__`、`.orig/.rej/.pyc/.o/.swp`、`.bak*`、`~`、`.DS_Store`。

**`export.sh` 从不写 `xnu/files/`。** 它的 `:12` 把那个目录读作 `SHARED=$HERE/../xnu/files`，只用来比对，`xnu/files/` 的内容完全由人维护。这是两个方向都会产生差异的根源：改了树不导出，仓库这一侧就旧；改了 `xnu/files/` 不重新铺树，树这一侧就旧。

`xnu26/patches/series` 的 mtime 是 2026-10-27 15:18:48，也就是这次对账之前最后一次全量导出的时间。

## 2. 实测到的差异

用 `export.sh` 自己的选择逻辑在 160 个候选文件上重跑一遍对账，2026-10-28 的状态是：

| 文件 | 方向 | 树侧 | overlay 侧 | 差异内容 |
|---|---|---|---|---|
| `bsd/dev/annibale_cpufreq.c` | overlay 较新 | 30,524 B，2026-10-27 14:51:34 | 30,352 B，2026-10-27 16:32:59 | 树侧 `492,497` 六行换成 overlay 侧 `492,495` 四行，十行全在同一个注释块里，代码零改动 |
| `bsd/dev/mhi_pcie.c` | overlay 较新 | 39,071 B，2026-10-27 09:56:59 | 40,583 B，2026-10-28 03:01:49 | 树侧 4 行、overlay 侧 31 行。新增 5 个寄存器定义（`SMMU_SCR0_CLIENTPD`、`SMMU_GBPA` 0x044、`SMMU_GFSR` 0x048、`SMMU_GFSYNR0` 0x050、`SMMU_GFSYNR1` 0x054），PCIe step 6 多读四个 apps SMMU 全局寄存器、多一处 `mhi_pcie_pause(...)`、多一个读到全 F 就提前 return 的分支，step 6 那行 printf 文字也变了 |
| `bsd/dev/redwood_net.c` | overlay 较新 | 13,602 B，2026-10-23 19:04:01 | 15,094 B，2026-10-28 02:54:06 | 树侧 1 行、overlay 侧 43 行。新增一条 boot-arg 控制的无线 stub 链路：`net_wireless=1` 建一个背后没有射频的 en0（`stub_transmit` 恒返回 false、`stub_link` 的 MAC 是本地管理位 `02:6e:65:74:77:6c`），`net_wireless_up=1` 才把链路拉起，新增 `redwood_net_stub_init()` 与 `:417` 的一处调用 |
| `osfmk/kern/redwood_threads.c` | 只在树上 | 存在 | 对账前不存在 | 3,317 B，mtime 2026-10-28 11:45:12 |
| `bsd/dev/redwood_threads.c` | 只在树上 | 存在 | 对账前不存在 | 6,009 B，mtime 2026-10-28 11:47:55 |

`redwood_net.c` 那一条对读数的影响是零：round C、D、E 的 cmdline 里没有 `net_wireless`，`PE_parse_boot_argn` 失败即 return。`mhi_pcie.c` 那一条改了启动行为，两侧同步那一轮之后的第一轮要把 PCIe step 6 的输出标成预期变更。`annibale_cpufreq.c` 那一条全是注释，`ff_s` 与热读数在它拷进树之后仍可与 C、D、E 直接比。

两个孤儿文件与 `bsd/dev/redwood_input.c`（+7 行）、`bsd/sys/redwood_input.h`（+13 行）一起随 `2142061` 落进仓库。两处 diff 都是纯增加，树上那份是 overlay 那份的严格超集，所以覆盖没有丢东西。

报行数按两侧分开数（树侧几行、overlay 侧几行）。`diff` 的原始输出行数含 `---` 与 hunk 标记，`annibale_cpufreq.c` 按那个口径是 12 行，按两侧分开是 6 与 4。

## 3. 三例缺口与它们的共同形状

对账查出三例「文件在，启用它的条目不在」，都已经在 `2142061` 或之前的提交里补上：

1. `bsd/dev/redwood_bt_probe.c` 在树上、在 `xnu/files/` 里，而它的注册行 `bsd/dev/redwood_bt_probe.c		standard` 从来不在 patch 集里。铺出来的树能构建、能启动，只少一个探针，没有任何一步报错。
2. `osfmk/kern/redwood_threads.c` 与 `bsd/dev/redwood_threads.c` 两个文件在树上，而 `bsd/conf/files` 与 `osfmk/conf/files` 里对应的两行注册都不在 patch 集里，两个文件本身也不在 overlay 里。
3. `redwood_input.c` 的 `kern.redwood.frames` 那半个 sysctl 在树上，overlay 里只有 `redwood_frames_shown` 的定义而没有 `SYSCTL_INT` 那一行。

三例的共同形状是：**用一个存在性事实去支撑一个路径性结论。** 文件在树上是一个存在性事实，它被编进内核是另一件事，取决于 `conf/files` 里那一行。两边都要对账，只查一边会得出「改动已经在跑」的结论。

同一形状在这次对账之外还出现过三次，一并记在这里，因为它们来自三个人、三个领域：

4. 一个配平的计数式要先分清哪一侧是实测、哪一侧是推断。device 第一次报的「旧镜像 36 条 = staging 34 条 + 这 2 个」两边都是实测，所以那 2 条必然来自别处；第一次读成「staging 丢了」，第二次读成「打包加了」，第二次对。
5. 产物里一个符号有调用者，与该次调用走没走那个分支是两件事，守卫必须读到。`_threaded_context_create` 在 `libredwoodair.dylib` 里有 2 个直接调用者，而 `freedreno_context.c:773-774` 的 `if (!(flags & PIPE_CONTEXT_PREFER_THREADED)) return pctx;` 配 `air_metal.c:320` 的 flags 0 让它一次也没有走到 `threaded_context_create`。
6. 查一个产物的全部来源时，包含关系要跟着走。`rwa_texture_read` 的设备侧调用者在 `redwoodmetal_texture.inc:145`，而 `redwoodmetal.m:2803` 才 include 它；只 grep `.m` 会得出「唯一调用者是测试程序」的结论。
7. 一条通路的两侧资源类型要分别核。`air_metal.c:474` 的 `pipe_buffer_map` 被当成故障入口，而 `util_resource_copy_region` 对 PIPE_BUFFER→PIPE_BUFFER 走 `u_surface.c:317` 的直接 memcpy、到不了故障点 `util_copy_rect`，两侧都是纹理才走 `:346`。
8. 一个推导的前提死了，推导要跟着撤。「355 = 5×71 只能由 blocksize 1 得出，即 PIPE_BUFFER 按 R8 上传」是在 `rwa_texture_write` 那个假设下推的，那个假设被排除之后这条推断仍然写在报告里。
9. 一条核验命令写出来之后，没有对着已知的正反两个状态各跑一次。判断守卫有没有落地的命令写成数 `rsc->b.is_shared` 的出现次数、预期改前 0 改后 1，而同一份说明里已经引用过那 4 处赋值（`freedreno_resource.c:1097`、`:1391`、`:1527`、`:1742`），按它跑得到改前 4 改后 5，会读成「patch 没进去」的假失败。同一个事实既支撑了「守卫不存在」这个结论，又会让检验守卫是否落地的命令失效，而这两次使用之间没有对照。命令改成数 `if (rsc->b.is_shared)`，并在树上核过基线是 4 与 0。

操作性的规则有两条。**下路径性结论之前，先写出这次查了什么、没查什么，没查的那一项若翻转会推翻结论，就先查它。** 上面几处失败点各自对应一个没查的项：第 5 条没查守卫，第 6 条没查 include 关系，第 7 条没查资源类型，第 8 条没查前提还成不成立，第 1 到第 3 例没查启用条目。**写出一条核验命令之后，先在已知的正反两个状态上各跑一次，确认它给出预期的两个不同结果。** 第 9 条是这一条的对象。

## 4. 方法与命令

### 4.1 一条读数 caveat：调用图只由直接调用边构成

用「枚举 `__text` 里每条 `bl` 与 `b`、按符号表归属到函数」这个办法建出来的调用图，**经函数指针的调用看不见**。所以「某函数的直接调用者是 0 个」这个读数不能读成「没人调它」，只能读成「没有直接调用它的指令」。两个实例：`_fd_resource_copy_region` 是 `pipe->resource_copy_region` 这个 vtable 项，`_u_default_texture_subdata` 是 `pipe->texture_subdata`，两处的直接调用者都是 0，而两者都能被经函数指针的调用到达。

补法是两条：一是在源码里 grep 那个函数指针成员的调用形式（`->resource_copy_region(`、`->texture_subdata(`），二是把「直接调用者 0 个」的节点标成待确认，不当作排除依据。

### 4.2 一个正面样板：用日志排除一条代码路径

`air_metal.c:6961` 的 `pipe->blit` 是 MSAA resolve，`:6948-6949` 是 `if (from->nr_samples <= 1) continue;`。四轮日志里 `samples` 的取值只有 1（roundb 39 行、round C 61、round D 60、round E 53，`samples 4` 零命中），所以那条 blit 一次也没有执行。

这个排除比只读源码强，因为它同时排除了「代码上有这条路」与「实际走了这条路」两件事。凡是有日志能答的可达性问题，先用日志答。

### 4.3 核验一条 patch 有没有进构建树

**一个退出码为 0 只有在已经证明「被测对象缺失时它会失败」之后才构成证据。** 这一条来自同一天两个独立的实例。

第一个实例是一条 grep 判据。判断守卫有没有落地，命令写成数 `rsc->b.is_shared` 的出现次数、预期改前 0 改后 1，而那个表达式改前就有 4 处（`freedreno_resource.c:1097`、`:1391`、`:1527`、`:1742` 四个赋值），按它跑得到 4 与 5，会读成「patch 没进去」的假失败。同一个事实既支撑了「守卫不存在」这个结论，又会让检验守卫是否落地的命令失效，两次使用之间没有对照。可用的判据是数条件那一处：`grep -c 'if (rsc->b.is_shared)'`，改前 0、改后 1，并且先在树上核过基线确实是 4 与 0。

第二个实例是 `git apply` 的一个工具陷阱。`out/` 被 `hackios-xnu-kernel/.gitignore:4` 的 `/*` 忽略，`git apply` 在被忽略的目录里打印 `Skipped patch '…freedreno_resource.c'.` 之后**退出 0 而文件一个字节没动**，加 `--no-index` 也一样静默退出 0，所以 `git apply --check` 的退出 0 是空的。这个仓库的 `out/` 整个被忽略，以后任何对构建树的 patch 操作都会遇到这一条。

三种核法按强度排：

| 核法 | 测的是什么 | 强度 |
|---|---|---|
| 应用之后在树里 grep 改动引入的那个条件 | 树里有什么 | 最终判据，只有它能定 |
| `patch -p1 -R --dry-run` 喂 `diff --git` 之后的那一段（反向干跑） | 树里已应用的内容与当前 patch 文件是否逐字一致 | 事前最强，因为它同时证明「在树里」与「与文件同版」 |
| `patch -p1 --dry-run` 喂 `diff --git` 之后的那一段（正向干跑） | 这个 patch 能不能进这棵树 | 事前够用，但不说明树里已有什么 |

本机的 `patch 2.0-12u11-Apple` 嚼不动散文前言，喂整个文件会报 `malformed patch at line 90`；容器里的 GNU patch 能吃下整个文件，`mk-mesa.sh:115` 用的就是它，而 `tools/mesa/` 下另有 6 个 patch 带散文前言且都在容器里跑通过，所以前言格式不是新问题。

### 4.4 磁盘上的 patch 文件与树里已应用的 patch 可以是两个版本

`out/ios26-resume/mesa-arm64e/mesa-26.2.5/.redwood-patches` 的 mtime 是 2026-10-23 16:18:11，说明 `mk-mesa.sh` 自那时起没有重新打过 patch；而 `tools/mesa/draw-perf.patch` 与 `draw-perf2-extra.patch` 的 mtime 是 2026-10-28 09:25 与 09:35。**所以树里的插桩是 10-23 那个版本，磁盘上的 patch 文件是 10-28 编辑过的版本，两者可以不同，而没有任何记录说明差别。**

这一条与 §5 那条「构建身份是构建树的工作状态」放在一起读，它与内核那边 `xnu/files/` 与构建树成对副本的问题同类，差别是那边有 `cmp` 可核、这边没有。这边唯一现成的记录是 `mk-mesa.sh:248-250` 写的 `out/patch-survey.txt`，头部一行是 `# mesa-$VERSION, patches $PATCHES`，正文是 `.rej` 与 `.orig` 的排序清单，所以它在的时候能直接回答「这棵树是哪一套 patch 打的」；而 `hackios-xnu-kernel/out/patch-survey.txt` 现在不存在。

引用后果：凡是从磁盘上的 patch 文件引行号，都要标一个限定，因为树里可能是另一个版本。实例是 `draw-perf.patch` 的 `:637`、`:271`、`:227`、`:108`、`:148` 这几处引用，它们是磁盘版本的行号。那些结论本身有实测支撑（51.72 对 52.083 的经验定标、`calls 7` 配 `draws 7` 逐条相等），所以结论不受影响，受影响的只是行号。

`mk-mesa.sh:106` 的 `PATCHES` 戳是 `cat tools/mesa/*.patch` 的内容哈希，所以它只对「跑过 `mk-mesa.sh` 的那一次」有效：手工应用到树上的改动不进这个戳，而 `package.py` 也不查它。这一轮的 AIR 就是这种状态，身份要按构建树的工作状态记，即「冻结那次的树加一个手工应用的 patch」。

### 4.5 对账命令

对账用 `export.sh` 自己的选择逻辑，而不是另写一套判据，理由是两套判据会在下次导出时给出不同答案。

单个文件的 patch 用这条命令重新生成，与 `export.sh` 产出的字节相同：

```
git -C out/xnu12377 -c core.abbrev=12 diff --binary --no-renames --no-color --no-ext-diff \
    ac9718fb1af618d5ce8678d0dc6e8a58f252216f -- <file>
```

`04-bsd%conf%files.patch` 与 `46-osfmk%conf%files.patch` 两个 patch 就是这样重新生成的，不手工插行。手工插进去的行在下次全量导出时会被 `rm -rf patches.new` 那一步静默丢掉，而重新生成的字节与将来导出的字节相同。

验证分两步。第一步把 BASE 的原始文件取出来：

```
git -C out/xnu12377 show ac9718fb1af618d5ce8678d0dc6e8a58f252216f:bsd/conf/files > /tmp/patchcheck/bsd/conf/files
```

第二步在一个临时仓库里 `git apply --check -v`，两个 patch 都返回 0。

落地之后核了四件事：两个 patch 对 BASE 的纯净副本 `git apply --check` 退出 0；四个文件与树上那份 `cmp` 逐位相同；overlay 里 `redwood_frames_shown` 的命中数从 0/0 变成 2/1；隐私扫描（`/Users/`、`/Volumes/`、`fan@`）零命中。构建树全程没有被写过。

### 4.6 一个值的形状不符合手里那一支的编码规则时，先查它属于哪一支

实例是 EXC_GUARD 的 `flavor=0x43`。文件描述符那一支的 flavor 是 `1u << 0` 到 `1u << 6`（`out/xnu12377/bsd/sys/guarded.h:104-110`），按它去套会把 `0x43` 读成三个 bit 的组合，进而判成字段归属不明。它实际属于 mach port 那一支：`out/xnu12377/osfmk/mach/port.h:637` 是 `kGUARD_EXC_DESCRIPTOR_VIOLATION = 67`，单个枚举值，而 `:616-618` 的注释正好解释了那些稀疏取值——原文是 Note: these had been designed as bitfields, hence the weird spaced values, but are truly an enum, please add new values in the `holes`.

字段布局有两处树内来源：`out/xnu12377/osfmk/kern/exc_guard.h:74` 的注释表画出 `[63:61] GUARD_TYPE_MACH_PORT | [60:32] flavor | [31:0] target`，`:187-192` 是三个编码宏（type 移 61、flavor 移 32 并取 `0x1fffffff`、target 取低 32 位），`:58-63` 是三个解码宏。类型表在 `:67` 到 `:183`，八个值从 `GUARD_TYPE_NONE 0x0` 到 `GUARD_TYPE_FROZEN_SWAPIN 0x7`。

规则：**一个值的形状看起来不符合某一支的编码规则时，先查它属于哪一支，不要按手里那一支的规则去套。**

### 4.7 mach IPC 与 guard 异常这一类枚举，先搜构建树的 doc 目录

`out/xnu12377/doc/mach_ipc/` 下有四份文档：`guard_exceptions.md`（21,908 字节）、`ipc_security_concepts.md`、`kmsg.md`、`port_types.md`。

- `guard_exceptions.md` 按码值逐条列出 ReportCrash 名字、Target meaning 与 Payload meaning。
- `:283-291` 那一节的标题就是 `### kGUARD_EXC_DESCRIPTOR_VIOLATION 0x00000043`，与日志里的 `flavor=0x43` 逐字对得上。
- 该节给出 Target meaning 是「The IPC space policy」（所以 `target=0x800407` 装的是 IPC space policy，不是端口名）。
- Payload meaning 是 `(violation_type << 56) | aux`（按它解 `subcode=0x300000000000011` 得 `violation_type = 0x03`、`aux = 0x11`，即 17）。

规则：**遇到这一类枚举先搜构建树的 `doc/`。** 它是树内来源，而此前查这一类值一直在树外找（公开文档、记忆里的枚举形状），树外找会得到形状相近而取值不同的另一支。

### 4.8 写在 `xnu/files/` 也提供的路径上的补丁，会被复制那一步整份覆盖

`apply.sh` 的三步是有序的：先按 `series` 逐件 `git apply`，再 `cp -P -p` 把 `xnu/files/` 拷进树，最后 `cp -R -P -p xnu26/files/.`。补丁改的是 Apple 的原文件，只要同一条路径在 `xnu/files/` 里也有一份，拷进去的那份会整份替换掉打过补丁的版本，补丁的每一行都不留，而 `apply.sh` 不报错、退出 0。

2026-10-29 实测过一例。`san/memory/ubsan_minimal.c` 加了诊断打印，写成 `73-san%memory%ubsan_minimal.c.patch` 挂进 `series`；同一晚 `7c3eec4` 把 8796 线那份 356 行的同名文件放进了 `xnu/files/san/memory/ubsan_minimal.c`。在干净目录重铺之后，树里那一份是 8796 的 356 行版本，带的是它自己的 `panic("UBSAN trap taken in early startup code: trap %u pc %p fp %p")`，补丁里新增的 `trap/elr/lr/fp/esr` 一个字都没有。

`xnu26/files.skip` 就是给这种情况用的：它列出「这些路径不取 `xnu/files/` 里的版本」，`apply.sh` 用 `grep -vxF -f "$HERE/files.skip"` 把它们从复制清单里剔掉。`4.8` 这一例加进 `san/memory/ubsan_minimal.c` 之后，12377 树用 Apple 自己那份（178 行），补丁才落地。副作用是两条线在这一个文件上分开：8796 线仍用 `xnu/files/` 里那份。

写补丁之前先查这条路径归谁：`git ls-files xnu/files/<路径>` 有输出就说明共用目录里也有一份，补丁要么改共用那份，要么把路径写进 `xnu26/files.skip`。铺完树之后再 `cmp` 一次目标文件与预期版本，`git apply` 的退出 0 对这件事没有信息量。

同日的状态数字：`series` 74 件（§1 的 73 是 10-28 那天的），`files.skip` 两项（`osfmk/arm64/kpc.c`、`san/memory/ubsan_minimal.c`）。

## 5. 两个结论与它们的查法

**`c2ccc7c` 那处改动在跑的内核里。** round C 跑的内核 sha256 是 `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492`。四条依据：

- 行为依据（最强）：round C 的 `s008.log:18970` 写着 `watching kern.redwood.frames from 3611`，3611 正是那一轮 `tl: v` 的最大帧号，所以那个 sysctl 在跑的内核里存在。
- `git show --stat c2ccc7c` 在外层仓库能解析，它改的正是 `xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp`（2 处插入，2026-10-28 05:29:27）。
- overlay 那份的 `:46` 有 `extern "C" uint32_t redwood_frames_shown;`、`:1015` 有 `redwood_frames_shown = fSwapsShown;`。
- 构建树那份与 overlay 那份 `cmp` 逐位相同（61,915 B），inode 不同，mtime 05:31，而 round C 的构建时间是 13:28:58 到 13:29:03。

这四条分三类：文件同一性（`cmp` 与 mtime）、仓库提交、运行时行为。前两类可以被「构建了但没刷进去」骗过，第三类不能。引用一个改动有没有生效时要说清用的是哪一类。

**一份构建出来的内核，可复现的身份是构建树的工作状态。** 具体是 `out/xnu12377` 的 HEAD 加它的未提交已跟踪改动加它的未跟踪文件。仓库这一侧在两个方向上都可能旧（§1），所以不能用它当身份。这条口径的一个具体陷阱：`git -C out/xnu12377 show 5c9f563:iokit/Kernel/MiniIOMobileFramebuffer.cpp` 返回空，因为那个路径在那棵树里是未跟踪的，空结果容易被读成「改动不在」。

## 6. 未验证

1. `xnu/files/` 里那 157 个文件与树上对应文件的逐一 `cmp`，这次只在有差异嫌疑的候选上做，160 个候选之外的没有全比。
2. `export.sh` 的 JUNK 正则会不会漏掉某类构建产物，没有构造用例试过。
3. 三个 overlay 较新的文件拷进树之后，round C、D、E 的读数哪些会变，只有 `mhi_pcie.c` 的 step 6 输出是已知的预期变更，另两个的判断建立在「boot-arg 缺席即 return」与「全是注释」这两条上，没有跑过一轮验证。
