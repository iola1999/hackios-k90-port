# 离线产物与算术核对（2026-10-29）

设备在 2026-10-29 13:42 前后从 USB 消失，本文的四项核对都在宿主机上完成，没有使用真机。文中的「实测」指本次读到的文件大小、哈希、`otool`／`nm`／`llvm-objdump` 输出或编译结果；「推断」指由这些读数与源码关系推出、没有在运行中的进程里另取读数的部分。读数照抄，不做单位换算与四舍五入。

## 1. `-0x55bf0` 的十进制值与调用点偏移

### 结论

- `-0x55bf0` 的十进制值是 **-351,216**。`352,240` 这一处错误，它等于 `0x55ff0`，比正确值多 `0x400`（1,024）。`351,216` 这一处正确。实测。
- `0x5c2b0 - 0x55bf0 = 0x66c0`，十进制 26,304。device 记录里的「0x6e0 附近」错误；复盘文档里的「0x6c0」也错误。`0x6c0` 与 `0x66c0` 相差 `0x6000`（24,576）。实测。
- 调用点的返回地址是 `0x66c0`，`bl`／`blraaz` 指令本身在 `0x66bc`。该返回地址在 `rwa_texture_write` 内，与源码 `air_metal.c:2130` 的 `texture_subdata` 调用对应。实测加推断。

### 证据

device 记的三行 `tl: za` 读数如下，三行的 `ret - self` 都写成 `-0x55bf0`：

```
data 0x342d393837362d41  ret 0x1023627b8  self 0x1023b83a8  ret-self -0x55bf0
data 0x80000c000c0000    ret 0x1029627b8  self 0x1029b83a8  ret-self -0x55bf0
data 0x80000c000c0000    ret 0x1024f67b8  self 0x10254c3a8  ret-self -0x55bf0
```

把第一行代入：`0x1023b83a8 - 0x1023627b8 = 0x55bf0 = 351,216`。另外两行相同。`0x55bf0` 的十进制是 351,216，`0x55ff0` 的十进制是 352,240；`0x55bf0 + 0x400 = 0x55ff0`，所以 352,240 比正确值多 1,024 字节。

`0x5c2b0` 的十进制是 377,520。`0x5c2b0 - 0x55bf0 = 0x66c0 = 26,304`；`0x5c2b0 - 0x55ff0 = 0x62c0 = 25,280`。device 写的 `0x6e0`（1,760）与这两个结果都不符；复盘文档写的 `0x6c0`（1,728）与 `0x66c0` 相差 `0x6000`（24,576）。

源码侧：`hackios-xnu-kernel/tools/mesa/air/air_metal.c:2043` 是 `rwa_texture_write` 的入口，`:2130-2132` 是它唯一一处 `texture->device->pipe->texture_subdata(...)` 调用。调用点在参数检查之后、`return 0` 之前。

符号侧：`hackios-xnu-kernel/out/ios26-resume/bbmetal-device/libredwoodair.dylib` 为 14,051,376 字节，sha256 `57fdb85c38bcf6892de3394ffa184963d881a99a091dae828c85dba5cb22e8eb`。`nm -n` 给出 `_rwa_texture_write` = `0x66e4`、`_u_default_texture_subdata` = `0x5c704`。`llvm-objdump --disassemble-symbols=_rwa_texture_write` 在函数尾部给出源码 `:2130` 对应的调用：`ldr x8, [x0, #0x3a8]` 与 `blraaz x8`，`blraaz` 的地址是 `0x6a08`，返回地址是 `0x6a0c`。`0x5c704 - 0x6a0c = -0x55cf8`（351,480）。

这一份是 2026-10-29 13:35 的构建，和会话里 `fd68e664…` 那一份（14,001,408 字节）是两个不同的镜像。两份的 `ret - self` 相差 `0x108`（264）字节：`u_default_texture_subdata` 的地址差 `0x454`，调用点返回地址差 `0x34c`，`0x454 - 0x34c = 0x108`（推断）。会话里 `u_default_texture_subdata` 在 `0x5c2b0` 这个值来自 air 的 `nm` 记录；`0x5c2b0` 与 `ret - self = -0x55bf0` 相加得到返回地址 `0x66c0`，该地址在源码调用点所在的 `rwa_texture_write` 内。当前构建的同类返回地址 `0x6a0c` 落在 `_rwa_texture_write`（`0x66e4` 起）内，两处关系一致。

会话里的 `fd68e664…` 镜像没有留在 `hackios-xnu-kernel/out/`；本次按名字找到的 10 份 `libredwoodair.dylib` 中没有这个哈希，所以 `0x5c2b0` 不能今天重新量。`0x55bf0` 已由三行运行时地址直接相减得到，`0x66c0` 由 `0x5c2b0 - 0x55bf0` 得到，这两步不依赖那份镜像。

## 2. `4246c32b…` 比 `cf1502f5…` 多 16,384 字节的来源

### 结论

- 两份都在磁盘上。`hackios-xnu-kernel/out/keep/4246c32b.mach` 为 20,226,616 字节，sha256 `4246c32b463724900c69ec44dd4b70362d0468d3b26503a616068e238d587c30`；`hackios-xnu-kernel/out/xnu12377-cf1502f5-restored.bin` 为 20,210,232 字节，sha256 `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492`。两份都是 `Mach-O 64-bit executable arm64`。实测。
- 16,384 字节全部落在 `__TEXT` 段：`vmsize` 与 `filesize` 都从 1,916,928 增到 1,933,312，差 16,384；其余 17 个段的 `vmsize`／`filesize` 不变，`vmaddr` 与 `fileoff` 除 `__PRELINK_TEXT` 的固定 `vmaddr` 外都加 16,384。实测。
- 段内实际内容只增加 84 字节：`__TEXT,__cstring` 从 `0x1346ed`（1,263,341）增到 `0x1346fd`（1,263,357），差 16；`__TEXT_EXEC,__text` 从 `0x99ea94`（10,087,060）增到 `0x99ead8`（10,087,128），差 68。其余 42 个 section 的 `size` 不变。实测。
- 文件大小的 16,384 是 `__TEXT` 段按 `0x4000` 对齐取整的结果。cf1502f5 的最后一个 `__TEXT` section（`__eh_frame`）结束在段内偏移 `0x1d3ff8`，离 `0x1d4000` 边界 8 字节；4246c32b 的同一位置结束在 `0x1d4008`，越过边界 8 字节，段 `vmsize` 因此从 `0x1d4000` 跳到 `0x1d8000`。实测。
- `docs/progress/2026-10-29-kernel-build-line-summary.md:16` 把 `out/keep/` 的文件大小写成 202,266,616 字节，实际 `stat -f %z` 是 20,226,616 字节，前者多一个前导 2，差 182,040,000 字节。实测。

### 证据

`stat -f %z` 与 `shasum -a 256` 的读数：

| 文件 | 字节数 | sha256 |
| --- | --- | --- |
| `out/keep/4246c32b.mach` | 20,226,616 | `4246c32b463724900c69ec44dd4b70362d0468d3b26503a616068e238d587c30` |
| `out/xnu12377-cf1502f5-restored.bin` | 20,210,232 | `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492` |
| `out/xnu12377-f055cc0a-restored.bin` | 20,226,616 | `f055cc0a928e6b3a69f1043a419105362a71ea46ac1789e05387dea1db54c2c3` |

`otool -l` 的逐段读数如下，零尺寸段没有列出，它们的 `vmsize`／`filesize` 也都是 0 且两份相同：

| 段 | cf1502f5 vmsize | 4246c32b vmsize | cf1502f5 filesize | 4246c32b filesize | 变化 |
| --- | --- | --- | --- | --- | --- |
| `__TEXT` | `0x1d4000` | `0x1d8000` | 1,916,928 | 1,933,312 | +16,384 |
| `__DATA_CONST` | `0x134000` | `0x134000` | 1,261,568 | 1,261,568 | 0 |
| `__TEXT_EXEC` | `0x9a0000` | `0x9a0000` | 10,092,544 | 10,092,544 | 0 |
| `__KLD` | `0x4000` | `0x4000` | 16,384 | 16,384 | 0 |
| `__LASTDATA_CONST` | `0x4000` | `0x4000` | 16,384 | 16,384 | 0 |
| `__KLDDATA` | `0x8000` | `0x8000` | 32,768 | 32,768 | 0 |
| `__DATA` | `0x488000` | `0x488000` | 458,752 | 458,752 | 0 |
| `__BOOTDATA` | `0xd8000` | `0xd8000` | 884,736 | 884,736 | 0 |
| `__LINKINFO` | `0x48000` | `0x48000` | 294,912 | 294,912 | 0 |
| `__LINKEDIT` | `0x500000` | `0x500000` | 5,235,256 | 5,235,256 | 0 |

除 `__PRELINK_TEXT` 的 `vmaddr` 固定在 `0xfffffff004004000` 之外，其余所有段的 `vmaddr` 与 `fileoff` 都加 16,384。

section 级别的差异只有两处：

| section | cf1502f5 size | 4246c32b size | 变化 |
| --- | --- | --- | --- |
| `__TEXT,__cstring` | `0x1346ed`（1,263,341） | `0x1346fd`（1,263,357） | +16 |
| `__TEXT_EXEC,__text` | `0x99ea94`（10,087,060） | `0x99ead8`（10,087,128） | +68 |

`nm -n` 在两份产物上都是 89,065 行。符号名集合只有三处自动编号不同：`gGPUKeep_466`／`gGPUKeep_464`、`gWaitLines_290`／`gWaitLines_289`、`kalloc_type_view_529`／`kalloc_type_view_527`，没有新增或缺失的全局符号；`__TEXT` 之后的符号地址随所在段整体加 16,384。实测。

`__TEXT` 的最后一个 section 是 `__eh_frame`。cf1502f5 里它的段内起始偏移是 `0x1d3948`、`size` 是 `0x6b0`，结束于 `0x1d3ff8`（1,916,920），比 `0x1d4000`（1,916,928）低 8 字节；4246c32b 里起始偏移是 `0x1d3958`、结束于 `0x1d4008`（1,916,936），比 `0x1d4000` 高 8 字节。段 `vmsize` 按 `0x4000` 取整，cf1502f5 得到 `0x1d4000`，4246c32b 得到 `0x1d8000`，差 `0x4000`（16,384）。

`strings -a` 查看 `tl:` 前缀的格式串：cf1502f5 有 `tl: f %s %llu at %llu` 与 `tl: s %u %s at %llu`；4246c32b 有 `tl: f %d %llu %s %llu at %llu` 与 `tl: s %u %d %llu %s at %llu`。pid／tid 两列在这两个串里。`__cstring` 的净增长是 16 字节，`__text` 的净增长是 68 字节，两个 section 合计 84 字节；16,384 字节的量级由段对齐决定，两列本身只占段内 84 字节增长的一部分。

`out/xnu12377-f055cc0a-restored.bin` 与 4246c32b 的 18 个段尺寸表相同，文件大小同为 20,226,616 字节，但 `__TEXT,__cstring` 是 `0x134763`（1,263,459）、`__TEXT,__text` 是 `0x99eb14`（10,087,188），与 4246c32b 不同；两份的 sha256 也不同。`strings` 显示 f055cc0a 也有与 4246c32b 相同的两组 pid／tid 格式串。

`f055cc0a` 是 2026-10-29 10:35 的纯净重编产物，当前 `hackios-xnu-kernel/out/xnu12377/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837` 就是这一份（20,226,616 字节，sha256 `f055cc0a928e6b3a69f1043a419105362a71ea46ac1789e05387dea1db54c2c3`）。`out/keep/4246c32b.mach` 只是 4246c32b 的一份保留件，当前 BUILD 已经换成 f055cc0a。

4246c32b 与 cf1502f5 相差 16,384 字节这一事实成立；4246c32b 与 f055cc0a 的文件大小相同，说明 16,384 字节的增量在 f055cc0a 这一版已经存在，不能单独归给 4246c32b 的 pid／tid 两列。

## 3. 装车驱动 `827045e4…` 的源码来源

### 结论

- 装车那份 `827045e4…`（242,096 字节）由内核仓提交 `f69b1b8`（2026-10-29 10:25:52，提交说明「驱动：iOS 26 驱动源码入库，加 region、bytes、fence 与心跳探针」）的 `tools/userland-driver/` 源码树编出。用该提交的树在 `/tmp` 重编，产物 242,096 字节、sha256 `827045e48792cf0b9ef46137eb068b4e9d65fb6353e70f961215339d921daa8f`，与装车值逐位一致。实测。
- 编译参数是 `tools/k90auto/package.py` 的 `DRIVER_FLAGS`，随后做 adhoc 签名。manifest 的 `build_commands.driver` 记录的编译参数与源码路径与这一条相同，输出路径按当次目录不同。实测。
- 工作树现编 241,328 字节 `6ec005e8…` 的记录来自 2026-10-29 09:41 前后的一次构建，早于 `f69b1b8` 的首次提交（10:25:52）。那次构建用的 `redwoodmetal_commandbuffer.inc` 版本没有留在磁盘上，也没有进 git；git 里该文件的第一版是 `f69b1b8` 的 `b9303943…`（40,580 字节）。缺的信息是那份 09:41 的 `commandbuffer.inc` 内容。推断加缺信息。
- 今天从当前 tree 编，得到 242,512 字节 `529d19bf…`（`tools/userland-driver/`，与 `out/ios26-resume/bbmetal-device/libredwoodmetal.dylib` 相同）；从 `hackios-xnu-kernel/userland/src/` 编得到 242,480 字节 `a8e473f9…`；从 `hackios-xnu-userland/userland/src/` 编得到 218,048 字节 `d73f1671…`。三份的字节数与 241,328 都不相同。实测。

### 证据

`f69b1b8` 的 `tools/userland-driver/` 树在 `/tmp/o4build/f69b1b8` 解出后，用下面这条命令重编：

```
mkdir -p /tmp/o4build/f69b1b8
git -C hackios-xnu-kernel archive f69b1b8 tools/userland-driver | tar -x -C /tmp/o4build/f69b1b8
```

```
/usr/bin/xcrun -sdk iphoneos clang -arch arm64e -miphoneos-version-min=26.0 -O1 -framework Foundation -framework IOKit -framework Metal -fno-objc-arc -dynamiclib -install_name /redwood/lib/libredwoodmetal.dylib tools/userland-driver/redwoodmetal.m tools/userland-driver/redwooddrawable.m -lobjc -o /tmp/o4build/f69out/libredwoodmetal.dylib
/usr/bin/codesign --force --sign - /tmp/o4build/f69out/libredwoodmetal.dylib
```

结果：242,096 字节，sha256 `827045e48792cf0b9ef46137eb068b4e9d65fb6353e70f961215339d921daa8f`。`strings -a` 在该产物里找到 `tl: cnt` 1 次、`tl: fw` 1 次，与心跳版驱动的格式串一致。

源码文件的哈希与大小：

| 文件 | `f69b1b8` | 当前 `tools/userland-driver/` |
| --- | --- | --- |
| `redwoodmetal.m` | `4513f3e823a70d6c4c88cb50405193dea4f7e53b4428b61b40ee2a06dc8b5e34` | `4513f3e823a70d6c4c88cb50405193dea4f7e53b4428b61b40ee2a06dc8b5e34` |
| `redwooddrawable.m` | `0a994aff638ec66e775d74cc54613665adab63a28b3aebcba43c4a93dc08fcec` | `0a994aff638ec66e775d74cc54613665adab63a28b3aebcba43c4a93dc08fcec` |
| `redwoodmetal_commandbuffer.inc` | `b93039436289d4361f44cc6b4b2c611872d52f12deeeadbddffa36df71827751`（40,580 字节） | `6550e4612dd4c60b4997b74e3aa13f3a0b91ab28a16a92a3dfd10e7d2d7f2bcc`（46,659 字节） |

`f69b1b8` 树里的其余 driver 文件与当前 `tools/userland-driver/` 副本逐字节相同，只有 `redwoodmetal_commandbuffer.inc` 不同。

`docs/progress/evidence/k90auto/kernel-12377-attr26-diag3-heartbeat2/manifest.json` 的 `pack.driver_sha256` 与 `pack.expected_driver_sha256` 都是 `827045e48792cf0b9ef46137eb068b4e9d65fb6353e70f961215339d921daa8f`；`pack.build_commands.driver` 的编译参数与源码路径与上面的命令相同，输出路径按当次目录不同；`pack.sources["tools/userland-driver/redwoodmetal.m"]` 是 `4513f3e8…`。`kernel-12377-attr26-diag3-heartbeat3` 与 `kernel-12377-attr26-diag3-one-tap` 的 manifest 记录同一驱动。

manifest 的 `pack.sources` 里与驱动有关的条目只列了 `redwoodmetal.m`、`redwooddrawable.m`、`redwoodmetal_blit.inc` 和两个 userland `.inc`，没有列 `redwoodmetal_commandbuffer.inc`、`redwoodmetal_work_private.h`、`redwoodmetal_mesa.inc`、`redwoodmetal_archive.inc`、`redwoodmetal_texture.inc`、`redwoodmetal_work.inc`。驱动构建通过 `#include` 读这些文件，manifest 的 `source_sha256` 因此不能唯一确定驱动源码。

`6ec005e8…`（241,328 字节）出现在 2026-10-29 09:41 前后的回报里；`f69b1b8` 的提交时间是 10:25:52，git 里 `tools/userland-driver/redwoodmetal_commandbuffer.inc` 的第一版就是 `f69b1b8` 的 `b9303943…`。09:41 那次构建使用的 `commandbuffer.inc` 内容没有留在磁盘或 git 里；本次按 `6ec005e8`、`241328`、`241,328` 三个字符串扫描了 `hackios-xnu-kernel/out/` 三层内、单个不超过 2 MB 的 `.log` 与 `.json`，没有命中（实测）。缺的信息是那份 09:41 的 `commandbuffer.inc` 内容。

## 4. `userland/src/inject.c` 的 51 行 `tl: b` 去留

### 结论

- 建议保留。这 51 行今天还能编过，依赖的 `micros()` 与 `say()` 都在当前文件里；2026-10-29 11:14 之前的「backboardd 的构造器没执行」这个前提已经失效，后续轮次已经实际打印出 `tl: b` 读数。实测。
- 它回答的问题是：帧流停止之后，backboardd 的主运行循环是否还在转。`tl: b WOKE COMMIT DONE` 的三个值给出该轮被唤醒、CoreAnimation 提交开始、提交返回的时刻；`DONE - COMMIT` 是提交本身的耗时。`tl: b` 继续出现，停顿在 CA 提交之后或更上游；`tl: b` 停止，消费提交的这一侧停了。实测加推断。
- 启用方式：boot cmdline 带 `touch_lat=1`；`libredwood.dylib` 通过 `inject.conf` 注入 backboardd（当前 `tools/k90auto/package.py` 的 `INJECT` 已有 `/redwood/lib/libredwood.dylib backboardd` 一行）；用 `userland/build.sh` 从 `src/inject.c` 编 `obj/libredwood.dylib`，打包进系统盘；日志里与 `tl: a` 一起看。`kernel-12377-attr26-diag3x-statefault` 的 cmdline 已带 `touch_lat=1`。实测。
- 这 51 行仍未提交，工作树 hash `08bd2297…`。保留的含义是随下一批用户态改动提交，并同步改掉复盘文档里「`tl: b` 建在库已注入上而注入当时没生效」的说法；继续以未提交改动留在工作树里会被下一次构建覆盖或遗忘。建议。

### 证据

`git -C hackios-xnu-userland diff --stat` 显示 `userland/src/inject.c` 一处 51 行新增。当前文件 sha256 是 `08bd2297d4e859d6e1012922a4ebbbf5a5a7398f3424db4dadd5bfad1e316952`，与 `kernel-12377-attr26-diag3-heartbeat2` manifest 的 `pack.inject_source_sha256` 相同。

编译验证：

```
cd hackios-xnu-userland
clang -fsyntax-only -target arm64-apple-ios16.5 -Wall -Wextra userland/src/inject.c
```

退出码 0。两条 warning 在 `inject.c:496-497` 的 `__builtin_return_address(1)`／`__builtin_return_address(2)`，属于原有代码；另有一条 `-Wincompatible-sysroot` warning，原因是本机默认使用 macOS SDK 而 target 写成 iOS 16.5。新增的 51 行没有产生 warning。

依赖项：`say()` 在 `inject.c:62`，实现是 `write(2, …)`；`micros()` 在 `inject.c:1024`，使用静态变量 `timebase`（`:1021`）；`timebase` 在 `input_start()` 的 `:1047` 与 `watch_window_server_loop()` 的 `:1165` 各初始化一次。`watch_window_server_loop()` 在 `redwood_init()` 的 backboardd 分支里、`input_start()` 之后调用，`input_start()` 只创建线程后返回。

`kernel-12377-attr26-diag3x-statefault` 的 run 日志里有构造器与注入生效的直接读数：

- `run/s001.log` 有 `redwood lib loaded pid 38 name backboardd`。
- 同一份日志有 `redwood: input: touch screen service 0x101c930c0, buttons 0x101c93480`。这一行由 `input_start()` 创建的线程打印，只有 `redwood_init()` 的 backboardd 分支执行到 `input_start()` 才会出现。
- manifest 的 `pack.inject_source_sha256` 是 `e71cdc00eac7e6f7fb986c6525ccbad429861b204576c54c1585bf8fb5a7f224`，`pack.userland_sha256` 是 `1d7278335752c53cee5e43294136f52ddafb6442b542aa9db61258372911421b`，`inject_conf` 包含 `libredwood.dylib backboardd` 一行，cmdline 含 `touch_lat=1`。

statefault 的注入库源码哈希 `e71cdc00…` 与当前工作树 `08bd2297…` 不同；会话记录显示当时为区分 stdout／stderr 在构造器里加过一条 `redwood lib loaded` 横幅，`tl: b` 的行号映射与当前新增段落一致。`tl: b` 代码逐字节相同这一点按行号与格式核对，没有做整文件差分（推断）。

`diag3x-statefault` 的 `tl: b` 去重后共 66 条，第一条是 `tl: b 290703704 290703737 290703737`，最后一条是 `tl: b 351306413 351306430 351306432`。该轮最后一帧是 `tl: v 913 ready 334028172 shown 334028172 done 334029426`；在最后一帧 `done` 334,029,426 微秒之后还有 12 条 `tl: b`，最后一条的 WOKE 是 351,306,413 微秒，两者相差 17,276,987 微秒。主运行循环在帧流停止后继续有 `tl: b` 输出，时间跨度为 17,276,987 微秒。该轮所有日志里 `redwood lib loaded` 只有 pid 38 与 name backboardd 一对，`signal 11` 为 0 条，没有看到 backboardd 重启。实测。

其他轮次的同类读数：`diag3x-arm64e` 的 `run/s002.log` 有 38 条 `tl: b`，`diag3x-revertcheck` 的 `run/s002.log` 有 30 条，`diag3x-noinput` 各 `s*.log` 有 11 到 52 条，`diag3x-verdict` 有 12 到 56 条，`diag3x-segflt` 有 10 到 56 条，`diag3x-batchcheck` 有 11 到 50 条，`diag3x-drawcall` 有 12 到 53 条。`tl: b` 已经在多轮里稳定出现。

`redwood: input:` 是 `say()` 的 `write(2, …)` 输出，statefault 日志里的 `redwood lib loaded` 是当时构造器里的临时 `printf`／`fflush(stdout)` 输出，两者在同一批日志里都出现。`tl: b` 也走 `say()`，同一通道在 `diag3x-statefault` 里可见。

## 5. 顺带发现

- `docs/progress/2026-10-29-kernel-build-line-summary.md:16` 把 `out/keep/` 的文件大小写成 202,266,616 字节，实际是 20,226,616 字节；同一份文档第 14 行写的 20,226,616 正确。实测。
- 同一行写「`cf1502f5…` 的二进制已被覆盖，没有留存」，`hackios-xnu-kernel/out/xnu12377-cf1502f5-restored.bin` 有一份 sha256 为 `cf1502f5…`、20,210,232 字节的副本。这份副本的来源标记为 restored；它能不能替代原始产物另说，文件本身在磁盘上。实测。
- 同一行写「`out/keep/` 里放了当前产物 `4246c32b.mach`」，当前 `out/xnu12377/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837` 已经是 `f055cc0a…`（20,226,616 字节），不再指向 4246c32b。实测。
- `docs/progress/2026-10-29-kernel-build-line-summary.md:13-14` 把 `cf1502f5…` 标成「纯净基线」、把 `4246c32b…` 标成「带 `tl: s`／`tl: f` 的 pid／tid」。`f055cc0a…` 也是 20,226,616 字节，也有同样的两组 pid／tid 格式串；16,384 字节的增量在 `f055cc0a…` 这一版已经存在。该文档第 28 行的「尚未闭合」项可以用 `out/keep/4246c32b.mach` 与 `out/xnu12377-cf1502f5-restored.bin` 的现成产物闭合，不需要重编纯净内核。实测。
- `docs/progress/2026-10-29-kernel-tlpid-builtin.md` 的第 103 行写「做这件事要重编一次纯净内核，而当前 out/xnu12377 的产物就是真机在用的 4246c32b…，重编会覆盖它」。今天 `out/keep/4246c32b.mach` 与 `out/xnu12377-cf1502f5-restored.bin` 都在，逐段比较已经完成，重编不再必要。实测。
- `docs/analysis/2026-10-29-session-review.md:141` 写「`tl: b` 那 51 行建在『库已注入』上，而注入当时根本没生效」。`diag3x-arm64e`、`diag3x-revertcheck`、`diag3x-statefault` 等轮次的日志里有 `redwood lib loaded pid 38 name backboardd`、`redwood: input: touch screen service …` 与 30 到 66 条 `tl: b` 读数，说明这段探针在注入修好之后已经执行并打印。该句只适用于 2026-10-29 11:14 之前的轮次，不能用来判定这 51 行作废。实测。
- `docs/plan/2026-10-29-offline-work-queue.md:46` 的「工作树现编得到 241,328 字节 `6ec005e8…`」在今天不成立：当前 `tools/userland-driver/` 编出 242,512 字节 `529d19bf…`，`hackios-xnu-kernel/userland/src/` 编出 242,480 字节 `a8e473f9…`，`hackios-xnu-userland/userland/src/` 编出 218,048 字节 `d73f1671…`。241,328 那次的 `commandbuffer.inc` 版本缺失。实测加缺信息。
- `tools/k90auto/package.py` 的 driver `source_sha256` 只记录 `redwoodmetal_blit.inc`，没有记录 `redwoodmetal_commandbuffer.inc`、`redwoodmetal_work_private.h`、`redwoodmetal_mesa.inc`、`redwoodmetal_archive.inc`、`redwoodmetal_texture.inc`、`redwoodmetal_work.inc`。本次为 827045e4 找源码时，`.m` 的哈希在 manifest 里对得上，真正的差异在未记录的 `commandbuffer.inc` 上；建议把驱动所有 `#include` 的文件都加进 `pack.sources`。实测。
- `out/xnu12377-f055cc0a-restored.bin` 与 `out/keep/4246c32b.mach` 大小相同、18 个段尺寸表相同，但 `__TEXT,__cstring` 与 `__TEXT,__text` 的 `size` 不同，sha256 也不同；两份是两个不同的构建，不能当作同一份产物的副本。实测。