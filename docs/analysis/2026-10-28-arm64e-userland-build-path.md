# 26 线 arm64e 用户态产物的宿主构建路径（2026-10-28）

## 0. 两条内核构建线，以及哪一条是项目的

**26 线（本项目内核，唯一可用于真机）**

```
cd hackios-xnu-kernel && XNU26_SRC=out/xnu12377 xnu26/build-macos.sh -j10 BUILD_DSYM=0
```

产物 `out/xnu12377/BUILD/obj/mach.development.bcm2837`（符号链接自 `BUILD/obj/DEVELOPMENT_ARM64_BCM2837/`），基线 20,210,232 字节、sha256 `cf1502f5632284af4ab11d182f62913663f7205ec4376f4abc0f274f834b2492`。2026-10-29 在这棵树上不加任何源码改动重跑，得到的正是这个哈希。

**8796 线（容器，另作它用）**

`tools/k90auto/build-kernel.py` 在 `kbuild` 容器里编 `/work/repo/xnu-src/xnu-8796.121.2`，产物是 `out/handoff-mach-attr26-*`，约 19.3 MB。**它的产物不作为本项目内核使用。** 2026-10-29 有四颗这样的内核被当作「新内核」送上真机，全部 0 帧，当晚的归因结论因此作废。

**身份口径**

`out/xnu12377` 的**构建树工作状态**是可复现身份：HEAD 加脏的已跟踪文件加未跟踪文件内容。`xnu/files/` 只是 8796 线的输入，`xnu26/patches/` 同理。改 26 线内核时直接改构建树里的文件，不改 `xnu/files/`。

这棵树本来就带脏的已跟踪文件（`bsd/kern/bsd_init.c`、`kern_exec.c`、`devfs_vfsops.c`、`config/MASTER.arm64.bcm2837`、`iokit/Kernel/IOStartIOKit.cpp` 等），它们属于身份的一部分，不能为了「干净」而还原。

**两边同名文件当前内容一致，这是状态不是机制**

`out/xnu12377/iokit/Kernel/` 下的 `MiniIOMobileFramebuffer.cpp` 与 `RedwoodGPU.cpp` 与 `xnu/files/` 里的同名文件当前 `cmp` 相同，但两者之间没有任何同步机制，`xnu/files/` 从未参与 26 线构建。2026-10-29 把「两边一致」当成「改哪份都行」的机制，改了不生效的那一份，代价是四颗内核与六次真机引导。

**编完自检**

比产物 sha 与期望值：纯净构建应为 `cf1502f5…`，叠加改动后应为该轮记录的值。不相等就停下核对，不把产物送上设备。


roundb 装车那份 arm64e 驱动与 AIR 库是怎么编出来的，这一页给答案。结论是两条已存在于仓库的宿主构建入口，都在 `tools/k90auto/`：`package.py` 编驱动、shim、探针并打 `root.apfs`，`build-air.py` 编 AIR 库。命令行逐字记在 round 目录的 `manifest.json` 与 `air-build-record.json` 里，工具链是宿主的 Apple clang，架构 arm64e，签名 adhoc。`userland/build.sh` 服务的是 16.5 线，26 线的产物不经过它。

调查只读，没有跑任何构建，没有改脚本，没有碰设备与 round 目录里的产物。

## 1. 驱动、shim、探针：`tools/k90auto/package.py`

仓库里那份 663 行（sha256 前 16 位 `06ca549260923ad8`）。构建部分：

- `:168` 工具链：`SDK = ["/usr/bin/xcrun", "-sdk", "iphoneos", "clang", "-arch", "arm64e", "-miphoneos-version-min=26.0"]`。
- `:274-282` `build(sources, install_name, flags, out, dynamic=True)`：`command = SDK + flags + ["-fno-objc-arc", *kind, *sources, "-lobjc", "-o", str(out)]`，`kind` 在 `dynamic` 为真时是 `["-dynamiclib", "-install_name", install_name]`。它先把命令行写进 `<out>.build.log`，再以 `cwd=SRC_ROOT` 跑编译，然后 `codesign --force --sign -` 做 adhoc 签名。docstring 自己写着「One arm64e library (or one program, dynamic=False) from the current source, signed as build.sh signs one」。
- `:52` `SRC_ROOT` 取 `PAYLOAD_SRC_ROOT`，默认是 `hackios-xnu-kernel`，所以源文件在命令行里是 `userland/src/redwoodmetal.m` 这种相对形式。
- `:84` `BASE = out/ios26-resume/air-arm64e-device/on`，`:167-170` 一开头断言 BASE 的 `root.apfs` 与三个库的哈希，`:196-199` `shutil.copytree(BASE/root)` 之后把新产物 `copy2` 覆盖进去，`:209` 用 `tools/apfs/mkapfs.py -z --plain fw` 打 `root.apfs`。

roundb 那次跑的三条命令行，原文取自 `out/ios26-resume/bbmetal-device/manifest.json` 的 `build_commands`：

```
driver  /usr/bin/xcrun -sdk iphoneos clang -arch arm64e -miphoneos-version-min=26.0 -O1 -framework Foundation -framework IOKit -framework Metal -fno-objc-arc -dynamiclib -install_name /redwood/lib/libredwoodmetal.dylib userland/src/redwoodmetal.m userland/src/redwooddrawable.m -lobjc -o <round>/libredwoodmetal.dylib
shim    /usr/bin/xcrun -sdk iphoneos clang -arch arm64e -miphoneos-version-min=26.0 -Os -Wall -Wextra -Werror -framework Foundation -framework Metal -framework UIKit -framework IOKit -fno-objc-arc -dynamiclib -install_name /redwood/lib/libredwood-sbmetal-experiment.dylib userland/src/sb_metal_experiment.m -lobjc -o <round>/libredwood-sbmetal-experiment.dylib
probe   /usr/bin/xcrun -sdk iphoneos clang -arch arm64e -miphoneos-version-min=26.0 -Os -Wall -Wextra -framework Foundation -fno-objc-arc userland/src/lsprobe.m -lobjc -o <round>/lsprobe
```

`<round>` 是 `out/ios26-resume/bbmetal-device`，原文里是它的绝对路径，这里按仓库相对路径写。probe 那条没有 `-dynamiclib` 与 `-install_name`，对应 `dynamic=False`。

`-sdk iphoneos` 解析到宿主默认那个 iPhoneOS SDK。`libredwoodmetal.build.log` 里的头文件路径写着 `iPhoneOS27.1.sdk`，与 `hackios-xnu-kernel/xnu-deps/26/sdk/iPhoneOS.sdk/System` 那个符号链接指向的是同一个，也就是 `docker/dev.sh` 这次挂进容器的那个。

产物的实测身份（`otool` 的头 32 字节交给 python 解析，`codesign -dv`）：

| 产物 | 字节数 | sha256 前 16 位 | cputype | cpusubtype | filetype | 签名 |
|---|---|---|---|---|---|---|
| `root/lib/libredwoodmetal.dylib` | 241,488 | `9d66dd367d09af4d` | `0x100000c` | `0x80000002` | 6（MH_DYLIB） | adhoc，`Identifier=libredwoodmetal-5555494499a05997d7cf3bfc8713dc5479edb271` |
| `root/lib/libredwoodair.dylib` | 13,983,936 | `d7b9ced5a115c08c` | `0x100000c` | `0x80000002` | 6 | adhoc |

`cpusubtype` 的 `0x80000002` 是 LIB64 位加 ARM64E，正是 task-7 那个架构闸要求的值；容器里的 clang 18 出的是 `0x00000002`。

### 1.1 重建这份驱动库的步骤与可复现条件

源码在 `hackios-xnu-kernel/tools/userland-driver/`（两个 `.m`、两个 `.h`、七个 `.inc`，其中 `air_metal_copy.h` 也在这份源码集里；`redwoodmetal_mesa.inc` 的 include 写的是同目录）。`tools/k90auto/package.py` 的 `DRIVER_SOURCES` 指向该目录。

```
cd hackios-xnu-kernel
/usr/bin/xcrun -sdk iphoneos clang -arch arm64e -miphoneos-version-min=26.0 -O1 \
  -framework Foundation -framework IOKit -framework Metal -fno-objc-arc \
  -dynamiclib -install_name /redwood/lib/libredwoodmetal.dylib \
  tools/userland-driver/redwoodmetal.m tools/userland-driver/redwooddrawable.m \
  -lobjc -o <目录>/libredwoodmetal.dylib
codesign --force --sign - <目录>/libredwoodmetal.dylib
```

**输出文件名必须是 `libredwoodmetal.dylib`。** adhoc 签名把标识符写成 `<文件名>-<UUID>`，输出叫别的名字时签名 blob 随之改写，整份 sha256 完全不同，而 `__TEXT,__text` 与 `LC_UUID` 都一样。2026-10-29 曾因此误判成「工具链变了」，实际同一台机器、同一套 clang（21.0.0、SDK 27.1）就能编出 `9d66dd36d09af4d…`。

核对两项：241,488 字节、sha256 `9d66dd367d09af4d9b526c73c8407627357d1e32d0cd392639bd5e2b35600f26`。源文件路径不写进产物，所以从 `userland/src/` 或 `tools/userland-driver/` 编出的结果相同；能改哈希的只有输出文件名。

### 1.2 kbuild 容器是持久仓库

`tools/k90auto/build-kernel.py` 用的 `kbuild` 容器跨构建保留它的内核仓库与展开后的源码树，可能停在另一条线上。2026-10-29 它停在 `c4f5dd9`，这个提交在本地存在但不是当前分支的祖先，`git merge --ff-only` 在源码同步之后才报 `fatal: Not possible to fast-forward`，一次构建就此作废。

脚本现在在建之前先判「容器 HEAD 是不是本次提交的祖先」，不是就停下并打印两边的哈希与两条处理路径（把那条线 cherry-pick 进本分支，或把容器指到本次提交）。判断之外不改容器里的任何东西。

## 2. AIR 库：`tools/k90auto/build-air.py`

125 行。`package.py:57-61` 的注释说明为什么 AIR 不在那个脚本里编：「The AIR library is not compiled here; tools/k90auto/build-air.py is the only entry point that builds it, because the arm64e build reads its own copy of the sources and an unsynced edit builds a valid library that is missing what the round is meant to measure.」

路径常量（`:25-32`）：`SRC = tools/mesa/air`、`TREE = out/ios26-resume/mesa-arm64e`、`MESA = TREE/mesa-26.2.5/src/compiler/air`、`BUILD = TREE/build`、`LIB = BUILD/src/gallium/drivers/freedreno/libredwoodair.dylib`、`OUT = out/ios26-resume/bbmetal-device/libredwoodair.dylib`、`RECORD = TREE/air-build-record.json`、`TARGET = src/gallium/drivers/freedreno/libredwoodair.dylib`。

流程：`:38` `FILES = ["air_metal.c", "air_metal.h", "air_to_nir.c"]` 先复制进 `MESA`，`:80-81` 断言复制生效，`:85-89` 断言 `tools/mesa/air/` 里没有未复制的文件（有就报错并要求加进 `FILES`）；`:93` `ninja -C BUILD -j8 TARGET`；`:98-99` `OUT.write_bytes(LIB.read_bytes())`；`:100` adhoc 签名；`:104-116` 写 record，含两侧源摘要、库字节数与 sha256、`signed = adhoc`、以及 `holds` 里九个格式串是否在册。docstring 记了这一步存在的原因：arm64e 那棵树只读自己那份源，`tools/mesa/air/` 的改动不复制过去就等于没改，构建照样成功、库照样有效，唯一的迹象是 420 秒后日志里少一个字段。

工具链（`:40-45`）：一个 venv 里的 meson 1.12.1 加 homebrew 的 ninja，bison 排在系统那个前面（前端的 parser 要它），三者可用 `AIR_VENV`／`AIR_BISON`／`AIR_NINJA` 覆盖。今天实测都在：`/tmp/mesa-rebase/venv/bin/meson --version` 给 1.12.1，`/opt/homebrew/opt/bison/bin/bison` 在，`ninja` 是 `/opt/homebrew/bin/ninja` 的 1.13.2。venv 在 `/tmp` 下，重启或清理之后就没有了；宿主另有 meson 1.12.1（miniconda 那份），版本相同。

交叉构建配置 `out/ios26-resume/mesa-arm64e/cross.ini`：

- c／cpp／objc 都是 Xcode toolchain 的 clang 加 `-arch arm64e -isysroot <Xcode>/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS27.1.sdk -miphoneos-version-min=26.0`。
- ar／ranlib／strip 取自同一个 toolchain，`pkg-config = /usr/bin/false`。
- `[host_machine]` 是 `system = darwin`、`subsystem = ios`、`cpu_family = aarch64`、`cpu = arm64e`；`needs_exe_wrapper = true`。
- 构建选项在同目录 `cmd_line.txt`：`buildtype = release`、`prefix = /redwood`、`gallium-drivers = softpipe,freedreno`、`freedreno-kmds = msm`、`osmesa = true`、`llvm = disabled`、`gles2 = enabled`、`shader-cache = disabled`、`build-tests = false`。

`--check` 是只读模式（`:58-78`，只算摘要并打印，不复制、不构建、不写文件）。今天跑的结果：三个 `FILES` 两侧一致（没有任何 `out of sync` 行），`LIB` 是 13,956,392 字节、sha256 前 16 位 `0c9b9a9f5063b971`。独立算过 `tools/mesa/air/` 那三个文件：`air_metal.c` `e85482501842ee83`、`air_metal.h` `762dc822c13c6877`、`air_to_nir.c` `35b6f62ef90982f9`，与 `air-build-record.json` 里的 `source_sha256` 和 `tree_sha256` 六个值逐一相同。

## 3. roundb 那份产物的来历记录

`out/ios26-resume/bbmetal-device/manifest.json`（14,883 字节）里与构建相关的字段：

- `driver_sha256` = `9d66dd367d09af4d…`，`air_sha256` = `d7b9ced5a115c08c…`，`expected_driver_sha256` = `31f2d6b7b5fefeb8…`（基线那份），`library_change_accepted` = true。
- `source_sha256` 九项：`redwoodmetal.m` `40066a5dea3b0fb2…`、`redwooddrawable.m` `0a994aff638ec66e…`、`redwoodmetal_blit.inc` `add5b13f9dc48b1f…`、`sb_metal_experiment.m` `987f9154f441db2b…`、`sb_metal_registration_sequence.inc`、`sb_metal_compression_policy.inc`、`lsprobe.m` `85311cacf6b53138…`、`air_metal.c` `e85482501842ee83…`、`air_to_nir.c` `35b6f62ef90982f9…`。
- `base` = `out/ios26-resume/air-arm64e-device/on`，`base_root_sha256` = `33ed5fc9cb18367c…`，`root_sha256` = `e36caefb25f09e6e…`，`root_bytes` = 5,226,496。
- `dirty_worktree` = false，`worktree_status` = []，`redwood_diag` = false。
- `build_commands` 三条，已在 §1 抄出。

`air-build-record.json` 里 `library` 指向 `out/ios26-resume/bbmetal-device/libredwoodair.dylib`、`library_bytes` 13,983,936、`library_sha256` `d7b9ced5a115c08c…`、`signed` adhoc。

目录里另有一份 `package.py`，281 行、16,045 字节（`35184ba0bd9d5b78`），与仓库里那份 663 行、43,310 字节（`06ca549260923ad8`）不同：目录里那份是当次跑的快照，头部的 docstring 记的是那一轮的变量（backboardd 的 Metal 注册、blit selector 的转发、AIR 的 `[[depth]]` 补丁）。`.build.log` 那几个文件是快照那次写出来的。两者谁新谁旧没有查，`build()` 与 `SDK` 的形状在两份里一致。

## 4. 与 `userland/build.sh` 的分工

- `build.sh:87` 的 `$DYN` 是 `xnu-clang -arch arm64 -isysroot ${THEOS:-$HOME/theos}/sdks/iPhoneOS16.5.sdk -O1`。宿主没有 `$HOME/theos`，这条在宿主跑不了；容器里跑得出 arm64，而 26 线的镜像只带 arm64e 的共享缓存，arm64 的动态产物在里面加载不了。
- 所以「26 线的产物要在有 Apple clang 的宿主上编」在仓库里已经有实现，实现是 `tools/k90auto/` 那两个脚本。task-7 给 `build.sh` 加的架构闸拦的是 `build.sh` 自己的 staging，两条路径的产物不混。
- 两边写的目录不重叠：`build.sh` 写 `userland/obj/` 与 `userland/root/`，`package.py` 写 round 目录（`out/ios26-resume/<name>/`）里的产物、`root.apfs` 与 `manifest.json`。这解释了 `userland/obj/libredwoodmetal.dylib` 为什么是 arm64 且比 `src/redwoodmetal.m` 旧，而装车那份是 arm64e：它们出自两条路径。
- 按这个分工，`build.sh` 不需要为 26 线加分支；加了就有两条路径写同一批产物名。要动的话，动的是让 `build.sh` 在 `V = 26` 时明确拒绝，架构闸已经在做这件事。

## 5. 可复现性的边界

- Mesa 那个库不是逐字可复现的，仓库里有实测记录。`tools/mk-mesa.sh:32-37` 的注释原文：
  - 「This build is NOT reproducible byte for byte, so do not compare one of its outputs with another by hash. Measured on 20 October: two builds from the same source tree, the second with build-softpipe-freedreno deleted first, gave different libOSMesa.8.dylib and air_run -- same size to the byte, 9 132 774 of 14 855 048 bytes different in the library and 4 171 752 of 9 789 824 in air_run, with 5 of the 6 named text symbols at new addresses.」
  - 那是容器那条 Mesa 构建的实测；宿主这条 arm64e meson 构建是不是同样性质，这轮没有验证。
- 这轮能说的是：`ninja -C build -n src/gallium/drivers/freedreno/libredwoodair.dylib` 干跑报 6 步待做，含重新编 `src/freedreno/common/libfreedreno_common.a.p/freedreno_uuid.c.o`、重链 `libgallium.a` 与 `libfreedreno_common.a`、重链 dylib。今天跑一次真构建会重新链接，产物哈希与 `d7b9ced5` 相同的概率低。这一条没有实测，因为实测会覆盖装车那份。
- 由此得到 baseline 闸的一个方向性读法：**产物哈希相同可以推出源相同，产物哈希不同推不出源不同**。重编 AIR 之后哈希与 `d7b9ced5` 不同，第一处置是核 `air-build-record.json` 的 `source_sha256` 与 `tree_sha256` 两侧六个值，两侧一致就说明库是按当前源编的，哈希变了来自布局；两侧不一致才是真的不同步。当成污染停下会浪费一轮。
- 驱动那三个产物的可复现性这轮没有实测：`manifest.json` 记了命令行、九个源摘要、cwd 与签名方式，输入不变则输出应当不变，但「应当」这一步没有跑第二次来验证，而验证会写 round 目录。

## 6. 三个同名 `libredwoodair.dylib`

`out/ios26-resume/mesa-arm64e/` 这棵树里有三个同名的 `libredwoodair.dylib`，字节数与哈希各不相同，核对身份时必须按完整路径：

| 路径 | 字节数 | sha256 前 16 位 | 是什么 |
|---|---|---|---|
| `mesa-arm64e/build/src/gallium/drivers/freedreno/libredwoodair.dylib` | 13,956,392 | `0c9b9a9f5063b971` | ninja 的输出，即 `build-air.py` 的 `LIB` |
| `mesa-arm64e/libredwoodair.dylib` | 13,949,888 | `7b8e29edd0bdce0f` | 来历未查 |
| `bbmetal-device/libredwoodair.dylib` | 13,983,936 | `d7b9ced5a115c08c` | `OUT`，装车那份 |

`OUT` 比 `LIB` 大 27,544 字节，与 adhoc 签名的 CodeDirectory 尺寸 27,471 相符（`codesign -dv` 给 `size=27471 flags=0x2(adhoc) hashes=852+2`，852 个 16 KiB 页正好覆盖签名前那 13,956,392 字节），所以 `OUT` 是 `LIB` 加签名。这个尺寸差也解释了为什么三者的哈希两两不同：签名占 `__LINKEDIT` 的尾部，页哈希随内容变。树根那份比 `LIB` 小 6,504 字节，与签名差对不上，它是另一次构建的产物，没有追。

## 7. 两个操作上的危险

- `build-air.py` 不带 `--check` 时会就地覆盖 `OUT`，也就是 `out/ios26-resume/bbmetal-device/libredwoodair.dylib`。`OUT` 是硬编码的，没有环境变量能改。roundb 的产物身份不能变（round C 复用 roundb 已核的 apfs，device 的 baseline 闸也指着 `d7b9ced5`）。
  - **硬性前置：任何真构建之前，先把 `out/ios26-resume/bbmetal-device/` 整个目录备份到 git 忽略的目录。不做这一步就不许跑。**
  - 具体做法（task-7 第二次运行前实际执行过一遍）：`cp -Rp out/ios26-resume/bbmetal-device/. docs/progress/evidence/k90auto/bbmetal-device-backup-<标识>/`，`-p` 保留时间戳，末尾的 `/.` 连隐藏文件一起拷；拷完立刻核四个关键文件的哈希与 live 一致（`libredwoodair.dylib` `d7b9ced5a115c08c`、`libredwoodmetal.dylib` `9d66dd367d09af4d`、`root.apfs` `e36caefb25f09e6e`、`manifest.json`），并记下文件数与体积（那次是 129 个文件、38 MB）。
  - 已存在的备份：`docs/progress/evidence/k90auto/bbmetal-device-backup-run2/`。
  - 重编之后 `build-air.py` 自己会重写 `air-build-record.json` 的 `library_bytes` 与 `library_sha256`，而 device 那个 baseline 闸期望的 `air_sha256` 要按 lead 的裁定另行更新，不能用 `ALLOW_DRIVER_CHANGE=1` 绕过。
- `package.py` 写 round 目录里的产物、`root.apfs` 与 `manifest.json`，`main()` 一开头断言 BASE 的四个哈希（`:167-170`），BASE 变了它拒绝跑。这个脚本属于 device 的跑轮流程，改完驱动要它出产物，先跟 device 约。device 打包或跑轮期间不要运行任何会写 `out/ios26-resume/` 或 `userland/obj/` 的命令，`build.sh` 也在其中（它写 `userland/obj/`，`:232` 有 `rm -rf root`）。只读复核不受此限：`build-air.py --check`、`ninja -n` 干跑、`shasum`、`codesign -dv`、`otool`。

## 8. round D 的前置结论

- 改驱动（提交入口三计数 `rwa commit entry`／`rwa kernel entry`／`tl: s`）与重建 lsprobe（task-8）今天就能出可装车的 arm64e 产物：改 `userland/src/` 下的源，跑 `package.py`，命令行与源摘要自动记进 round 目录的 manifest。宿主的 Apple clang 有 ptrauth，容器 clang 18 那个 `__has_feature(ptrauth)` 等于 0 的问题在这条路径上不存在。
- 若 round C 的 `lr` 落在 AIR 库、要在自己一侧加校验：改 `tools/mesa/air/` 之后跑 `build-air.py`，先按 §7 备份。`FILES` 已覆盖 `air_metal.c`／`air_metal.h`／`air_to_nir.c`，加新文件要同时加进 `FILES`，否则 `:85-89` 的断言会拦下来。
- 两条路径都在 `tools/k90auto/`，都在顶层仓里被跟踪（`package.py` 最近一次改动是 `ffda571`，`build-air.py` 是 `9c4405a`）。协议里「`out/ios26-resume/bbmetal-device/` 不是 `build.sh` 的产物目录，它由历史手工流程产生，全仓没有任何脚本写它」这句要更正：写它的脚本是 `tools/k90auto/package.py` 与 `tools/k90auto/build-air.py`。
- lead 的裁决（2026-10-28）：task-11 到此结束，「把这条路径写成脚本或写进 `build.sh` 的一个分支」这个第二步作废，因为路径已经存在；不接进 `build.sh`，理由是 §4 那三条（两边写的目录不重叠，接进去就有两条路径写同一批产物名），这个理由与 `package.py:57-61` 自己的说法一致：那句话说的是 arm64e 构建只读自己那份源，两条路径各读各的源，合起来会掩盖不同步的编辑。要做的是把协议那句话改对，并让 `build.sh` 的 `V = 26` 分支保持 task-7 那个架构闸的拒绝。

## 9. 未验证的部分

- 没有跑 `build-air.py` 的真构建，也没有跑 `package.py`。两者都写 round 目录里的产物，而这轮那些产物的身份不能变。
- 宿主这条 arm64e meson 构建的字节可复现性没有实测，实测的前置见 §7 第一条的备份要求。
- `mesa-arm64e/` 根下那份 13,949,888 字节、`7b8e29ed` 的 `libredwoodair.dylib` 来历没有查。
- 两个脚本只读了构建与打包相关的部分，没有逐行读通（`package.py` 663 行、`build-air.py` 125 行）。
- 那三条命令行今天重跑会不会给出与 roundb 相同的字节，没有验证；`manifest.json` 里的 `source_sha256` 与当前工作树是否仍逐项相同，也没有对（`redwoodmetal.m` 在 roundb 之后有一次仅注释的改动，`.userland.git` `e0b7b62`，行数未变）。

### 1.3 容器里那条线与主线不是包含关系

2026-10-29 发现 kbuild 容器的 `/work/repo` 停在 `c4f5dd9`，与主线分叉，`merge --ff-only` 过不去。取证结果：

- 容器 HEAD `c4f5dd98652eea30e81e1703e0b56c3990a7a09d`，分支 `k90-port`，`git status` 干净，相对它自己的 `origin/k90-port` 是 ahead 200、behind 4。
- 那条线以六笔 BlueTool 探针提交为主：`baa499c`（boot-arg `bt_probe=1` 注册 BlueTool 找的两个控制套接字，只记录不回包）、`a48a496`（连接与断开行带累计计数）、`01bc649`（去掉 `ctl_enable`）、`fc9c340`（每十秒打一行累计值）、`1133be5`（心跳行打真实秒数），以及 `caa71dc`（`mhi_pcie` 阶段 6 读 GBPA 与全局故障状态）；其上还有两笔 `check-launchd-programs.py` 的工具提交 `3fc04f0`、`c4f5dd9`。
- 两条线不是包含关系：容器带着 `redwood_bt_probe.c` 的 34 行后续，主线带着线程转储的源文件（`bsd/dev/redwood_threads.c` 178 行、`osfmk/kern/redwood_threads.c` 68 行）、`redwood_input.h` 与 `redwood_input.c` 的改动、驱动源码入库（`tools/userland-driver/`）与两份 mesa 补丁。

合并之前必须解决一件事：`xnu26/patches/04-bsd%conf%files.patch` 与 `46-osfmk%conf%files.patch` 里 `redwood_bt_probe.c`、`redwood_threads.c` 的登记归属。两边各登记了自己那份源文件，直接合并会在构建清单上出现缺项或重复登记，要单独核对一次，合成一份完整登记。

取回与复现这条线的方式（下次不用再摸索）：

```
docker exec -w /work/repo kbuild git bundle create /work/container-line.bundle --all
docker cp kbuild:/work/container-line.bundle /tmp/container-line.bundle
cd hackios-xnu-kernel && git fetch /tmp/container-line.bundle 'refs/heads/*:refs/container/*'
git log --oneline refs/container/k90-port -6      # c4f5dd9 及其以下六笔
```

取回之后容器可以安全地 `git reset --hard` 回主线提交：那条线已经在本地仓库里可达。2026-10-29 按这个顺序执行过，容器从 `c4f5dd9` 指到 `8fe1b15`。

### 1.4 构建实际消费哪一棵树

构建链上有两棵同名的 XNU 树，2026-10-29 因为它们混用废掉了一次内核构建：

- **构建实际消费的**：容器里 `/work/repo/xnu-src/xnu-8796.121.2`，由 `tools/k90auto/build-kernel.py` 从 git 归档应用 `xnu/files/` 覆盖与 `xnu26/patches/` 之后展开。产物从这棵树的 `BUILD/obj/DEVELOPMENT_ARM64_BCM2837/` 里取。
- **`hackios-xnu-kernel/out/xnu12377`**：另一条构建路径留下的展开树，版本不同。`san/memory/ubsan_minimal.c` 在这棵里有 `kern/trap_telemetry.h`、早期 panic 分支在第 81 行；8796 那棵没有那个头文件，分支在第 229 行。
- **seed 来源**：容器里的 `/work/xnu-tag-source`，`XNU_URL=file:///work/xnu-tag-source` 指的就是它。需要某个 Apple 原文件的原文时从这里取。

改 XNU 源码之前，先确认手上的文件来自构建树（`/work/repo/xnu-src/xnu-8796.121.2` 或 `/work/xnu-tag-source`），不从任何 `out/` 目录下取。`out/` 下的树是历史构建的残留，同名不同版本。

三条同类问题的前两条是 §1.2 的容器仓库分叉与 §1.3 的另一条线，加上这一条，它们的共同点是构建输入不明确。

### 1.5 判新鲜度用内容哈希，不用 mtime

2026-10-29 有两次「工具按时间戳判定、结果是陈旧产物」。内核构建那一次有源码依据：`apply.sh` 用 `copy2` 保留了归档里的旧 mtime，`make` 因此跳过重编，一颗内核的 `K9CANARY` 标记连续留在后面三颗产物里，修复在 `6ebca15`。

打包那一次我推测 `build()` 也有同样的跳过逻辑，**这个推测是错的**：`package.py` 里没有 `st_mtime`／`getmtime`，`build()` 每次都跑 clang。查找原因时只有「形状相似」这一条依据，没有源码支持。`62d368b` 里落的两道断言与这条口径仍然成立，但它们解决的是另一个问题：镜像里实际装的驱动必须等于刚编出来的那份、也等于基线记的那份。

两次的共同结论写成一句：任何「产物是否最新」的判断都用内容哈希，不用 mtime；推出机制时要先找到源码里的那一行，形状相似不算依据。

## 10. `tools/mesa-patches/*.patch` 的应用链：补丁可复现，构建树不可重建

`hackios-xnu-kernel/tools/mesa-patches/` 下有两个已跟踪的补丁（`fixguard6-shadow-counters.patch`、`freedreno-shared-no-shadow.patch`），仓库里没有脚本应用它们。在 `hackios-xnu-kernel` 的 `tools/` 下 88 个已跟踪的 `.sh`／`.py` 与顶层 `tools/` 下 47 个同类文件里检索 `mesa-patches`，匹配数是 0。写 `tools/mesa/*.patch` 的是另一条链：`tools/mk-mesa.sh:99` 把 `tools/mesa/*.patch` 与 `tools/mesa/rebase-26/*.patch` 的内容算成一个 sha256 存进 `PATCHES`，`:116` 逐个 `patch -p1` 打进容器里的 `mesa-$VERSION`，`:128` 把那个哈希写进 `.redwood-patches`。`tools/mesa-patches/` 不在这条链上。

构建树 `out/ios26-resume/mesa-arm64e/mesa-26.2.5` 不属于任何 git 仓：`git check-ignore -v` 给的是 `hackios-xnu-kernel/.gitignore:4:/*`，`git ls-files out/ios26-resume` 是 0 项。它由 `xnu-deps/build/mesa/mesa-26.2.5` 复制而来（`out/ios26-resume/mesa-arm64e/setup-inputs.json` 的 `source` 字段，`created_at` 是 2026-10-26T21:36:44）。两个 `tools/mesa-patches/` 补丁的改动只存在于这棵树里：2026-10-29 实测源树 `xnu-deps/build/mesa/mesa-26.2.5/src/util/format/u_format.c` 里 `rwa_copy_record` 出现 0 次、`rwa row` 0 次，`src/gallium/drivers/freedreno/freedreno_resource.c` 里 `fd_shadow_calls` 也是 0 次；构建树同名两份分别是 3 次与 4 次。重新复制一次源树会丢掉这两块改动，从零重建这棵树要把两个补丁手打上去。

**补丁可复现与树可重建是两件事。**

- 补丁文件可复现：同一份补丁打到同一份原文上，得到逐字节相同的文件。2026-10-29 改 `u_format.c` 时按本节的方法验过。
- 树不可重建：仓库里没有那份原文。`xnu-deps/build/mesa/mesa-26.2.5` 由 `tools/mk-mesa.sh` 打出（同目录有 `patch.log`），它自己不在版本控制里。所以「打了补丁」只说明在这一棵树上做了这一处改动，说明不了这棵树能重建出来。
- 一个容易读错的标记：构建树里也有 `mesa-26.2.5/.redwood-patches`，按 `tools/mk-mesa.sh:99` 它只由 `tools/mesa/*.patch` 与 `tools/mesa/rebase-26/*.patch` 算出，见到这个文件不代表 `tools/mesa-patches/` 打过了。两棵树的这个值当前不同：`xnu-deps/build/mesa/mesa-26.2.5` 是 `3a43c7c4…`，arm64e 构建树是 `216c4533…`。

**与 §0 的内核身份口径并列**：`out/xnu12377` 的可复现身份是「构建树工作状态」，即 HEAD 加脏的已跟踪文件加未跟踪文件内容，那些改动落在 `out/xnu12377` 那个 git 仓里。AIR 这棵树没有这样的身份。它上面的改动只由 `tools/mesa-patches/*.patch` 记录，而 `air-build-record.json` 的 `source_sha256`／`tree_sha256` 只覆盖 `build-air.py` 的 `FILES` 三项（`air_metal.c`、`air_metal.h`、`air_to_nir.c`），`u_format.c` 与 `freedreno_resource.c` 不在其中。查一轮的 AIR 库由什么编出来，前三项读构建记录，这两份读补丁文件的提交。

**改这类文件走四步**（2026-10-29 改 `u_format.c` 时走了一遍）：

1. 拿改动前树里的那份反向应用旧补丁，得到原文：

```sh
cp out/ios26-resume/mesa-arm64e/mesa-26.2.5/src/util/format/u_format.c post.c
python3 - <<'PY'
t = open('tools/mesa-patches/fixguard6-shadow-counters.patch').read()
i = t.index('--- a/src/util/format/u_format.c\n')
open('/tmp/uf.patch', 'w').write(t[i:])          # 该文件那一段
PY
mkdir -p tree/src/util/format && cp post.c tree/src/util/format/u_format.c
cd tree && patch -p1 -R < /tmp/uf.patch && cp src/util/format/u_format.c ../pristine.c
```

2. 在 `pristine.c` 上改出目标内容，另存为 `new.c`。
3. 生成新段，替换补丁文件里从 `--- a/src/util/format/u_format.c` 那一行到文件末尾的部分：

```sh
diff -u pristine.c new.c \
  | sed -e '1s|^--- .*|--- a/src/util/format/u_format.c|' \
        -e '2s|^+++ .*|+++ b/src/util/format/u_format.c|' > uf-new.patch
```

4. 把新补丁打回 `pristine.c` 的副本，`cmp` 与 `new.c` 比较，一致再拷进构建树。

**检查法**：改完 `tools/mesa-patches/` 覆盖的文件、跑 `build-air.py` 之前，先 `cmp <构建树里那份> <按补丁打出来的那份>`，不一致就停下再改。补丁是记录，构建树是编译输入，两者不一致时构建照样成功、库照样有效，唯一的迹象是一轮跑完在日志里少几行。

这两份补丁既不进 `package.py` 的库哈希闸，也不进 `air-build-record.json` 的源摘要。要判「这一轮的库里有没有这份插桩」，用 `strings <库> | grep -c '<格式串>'`；`build-air.py` 的 `holds` 段做的是同一件事。
