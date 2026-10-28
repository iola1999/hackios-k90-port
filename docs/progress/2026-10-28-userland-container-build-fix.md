# 容器里 26 线 userland 构建的三个故障与处置（2026-10-28）

容器里跑 `userland/build.sh` 编 26 线产物，此前停在三个故障上：`CoreFoundation/CoreFoundation.h not found`、`xnu-deps/host/bin/ld64` 断链、`PREBUILT=1` 静默跳过编译。这一页记三者的调查结论、`build.sh` 与 `docker/dev.sh` 的改动、两次容器运行的记录，以及按 lead 的 A3 决定修订过的验收。

**结论先说：容器里的 clang 18 编不出可装车的 26 线产物，这一点已经查实并写进构建脚本的闸门，不再靠人记。第二次容器运行仍然停在 `src/inject_sb26.c:11` 的 `'ptrauth.h' file not found`（`BUILD_EXIT=1`），这是预期结果。26 线的产物走宿主的 `tools/k90auto/package.py` 与 `tools/k90auto/build-air.py`，见 [arm64e 构建路径](../analysis/2026-10-28-arm64e-userland-build-path.md)。**

## 1. 两个架构与工具链事实

两条都在容器里实测，都写在下面的闸门报文里。

1. **容器 clang 18 的 `__has_feature(ptrauth)` 等于 0。** 这条比缺头文件要紧：缺头文件是编译失败，`__has_feature(ptrauth)` 为 0 是「编得过、跑得错」。`ptrauth_strip()` 在没有 ptrauth 支持时退化成原样返回，`src/inject_sb26.c:26` 会把一个带 PAC 签名的指针当地址用，产物是一个有效的 Mach-O，装上车才在运行时出错。
2. **`<ptrauth.h>` 是 clang 资源目录里的头文件，不在 SDK 里。** 宿主那份在 `/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang/21/include/ptrauth.h`；容器的 clang 18.1.3 资源目录 `/usr/lib/llvm-18/lib/clang/18` 下有 204 个头文件，没有 `ptrauth.h`，iPhoneOS SDK 的 `usr/include` 里也没有。所以把这个头文件补进容器并不能让产物变对，补了之后 `__has_feature(ptrauth)` 仍是 0。

两个工具链产出的 Mach-O 头不同，这是闸门的判据来源：Apple clang 出的 arm64e `cpusubtype` 是 `0x80000002`（LIB64 位 `0x80000000` 加 ARM64E 的 2），容器 clang 18 出的是 `0x00000002`，arm64 出 `0x0`。第二次运行里两份 `input26-service` 的实测对照：

| 来源 | sha256 前 16 位 | 字节数 | cputype | cpusubtype | sdk | LC_CODE_SIGNATURE |
|---|---|---|---|---|---|---|
| 容器 clang 18（本次运行产出） | `3bc70a3fa619ff2c` | 54,848 | `0x100000c` | `0x2` | 26.0 | 有 |
| 宿主 Apple clang（`package.py`） | `5d682cc3729a9cd1` | 54,480 | `0x100000c` | `0x80000002` | 27.1 | 有 |

26 线的镜像只带 arm64e 的共享缓存（`hackios-xnu-kernel/ios26/23G90__iPhone18,3/` 下只有 `dyld_shared_cache_arm64e*`），所以装进 26 镜像的动态产物必须是 arm64e；`build.sh:612-624` 那条既有的 AIR 架构校验注释里记着代价，dyld 拒绝 arm64e 进程里的 arm64 slice 时桌面是 9-11 fps 对 60 fps。

## 2. 三个故障的调查结论与处置

### 2.1 `CoreFoundation/CoreFoundation.h not found` 的真因

`xnu-deps/26/sdk/iPhoneOS.sdk` 的 `System`、`Developer`、`Entitlements.plist` 是指向宿主 Xcode SDK 的符号链接（`System` 指向 `/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS27.1.sdk/System`）。容器里没有 `/Applications`，链接解析不到，`System/Library/Frameworks/` 整个不存在，clang 于是报找不到 `CoreFoundation/CoreFoundation.h`。

**交接文档 §5 怀疑的方向已排除**：那份文档怀疑容器里 theos 的 SDK 缺框架头。theos 的 `iPhoneOS16.5.sdk` 在容器里是完整的，26 线用的是 `xnu-deps/26/sdk/iPhoneOS.sdk`，两者是不同的 SDK，报错来自后者。

修法是把这个宿主 SDK 以同一绝对路径只读挂进容器，路径由 `readlink` 推导，见 §4。`build.sh` 里另加一段可解析性检查（`:217-226`），在花时间编译之前先说清是「SDK 坏了」还是「没挂载」：

```
build.sh: the iOS 26 SDK has no frameworks in this environment
build.sh: its System is <readlink 的结果>
build.sh: that is a path of the build host; mount it into the container at the same absolute path, read only
```

### 2.2 `xnu-deps/host/bin/ld64` 断链的来历

创建者是 `hackios-xnu-kernel/tools/mk-mesa.sh:70`：

```sh
[ -e "$LD64" ] || ln -sfn "$THEOS/toolchain/linux/iphone/bin/ld" "$LD64"
```

`-e` 跟随符号链接，`ln -sfn` 会改写已存在的那个链接。容器里 `$THEOS` 是 `/root/theos`，于是在宿主上跑过一次容器构建之后，这个链接指向了容器里的路径。

**此前指向什么已经查不出来**：`xnu-deps/host/bin/*` 被 `hackios-xnu-kernel/.gitignore:69` 忽略，没有 git 历史；宿主没有 `$HOME/theos`，`xnu-deps/setup.sh:123` 那个同样写法的 `link` 从没在宿主跑过。

结构性问题是同一路径由两个环境写、各自的 `$THEOS` 不同、互相覆盖。**lead 裁定本条不做结构性修复，只记录**，理由是宿主侧当前不需要链 userland（内核走宿主机 `xnu26/build-macos.sh`，userland 走容器），而「`obj` 必须比源新」的断言已经把「静默用旧产物」变成显式失败。`mk-mesa.sh:70` 未改。

### 2.3 `PREBUILT=1` 静默跳过

`build.sh:174` 是 `if [ -z "$PREBUILT" ] && ! command -v ld64 >/dev/null; then PREBUILT=1; fi`，环境里没有 `ld64` 就整段跳过编译。`libredwoodmetal.dylib` 有断言（`:600` 查存在、`:601-604` 查新旧），`lsprobe` 没有：装箱循环 `:495-497` 是 `if [ -f obj/$t ]`，缺了静默不装箱，旧了静默装旧的。

已补 `lsprobe` 的断言（`:488-494`，只在会编译它的路径上要求，因为 `prebuilt/userland` 不带 `lsprobe`）：

```
build.sh: obj/lsprobe missing
build.sh: obj/lsprobe is older than src/lsprobe.m; build it (IOS=$IOS) before staging
```

这条断言目前没有被一次真实构建触发过：两次容器运行都停在 `inject_sb26.c`，跑不到 `:488`。

### 2.4 容器 PATH 上没有 `ldid`

26 分支有三处无条件 `${LDID:-ldid} -S…`（`:229`、`:233`、`:238`；同文件 `:314` 起那些用 `{ … || … }` 包着，失败可以继续），`set -e` 下直接失败。`ldid` 在镜像里，路径是 `$THEOS/toolchain/linux/iphone/bin/ldid`（3,582,240 字节），只是没进 PATH。默认值落在 `build.sh:93` 起的一段里，`LDID` 未设且 PATH 上找不到时取该路径并 `export`（`:243` 那个 python 段读 `os.environ.get('LDID', 'ldid')`，所以必须 export；找不到时保持未设，否则 python 拿到空串）。`docker/dev.sh` 的 PATH 未改，这是 lead 决策二的第四条约束。

## 3. 架构加工具链闸门

`build.sh:866-925`，位置在 staging 完成之后、第一个 `mkapfs`（`:935`）之前，所以它拦的是即将进镜像的东西。范围是 26 线的全部产物，不只 AIR 库：`os.walk('root')` 遍历 staging，跳过符号链接与非 Mach-O，`MH_DYLIB` 与 `MH_BUNDLE` 按动态处理，`MH_EXECUTE` 只在有 `LC_LOAD_DYLINKER` 时按动态处理（静态程序不进 dyld，`init`、`child`、`stage0` 都是 `$CC … -static -nostdlib` 编的），拒绝 fat 二进制，要求 `cpusubtype == 0x80000002`。报文原文：

```
build.sh: <path> is an arm64 slice (cpusubtype 0x0), and this gate requires 0x80000002
build.sh: <path> is arm64e without the LIB64 bit (cpusubtype 0x2), and this gate requires 0x80000002
build.sh: <path> is a fat binary, and this gate requires one thin arm64e slice
build.sh: <path> is cputype 0xNN, and this gate requires 0x100000c (arm64e)
build.sh: N of the programs staged for this image are not arm64e with the LIB64 bit
build.sh: the 26 line has to be built on a host with Apple clang; a container clang has no ptrauth
build.sh: why this image needs arm64e, and what would falsify it: docs/progress/2026-10-28-userland-container-build-fix.md
```

退出码 1。倒数第二行是 lead 要求报文里点名的那句：这个产物是错误工具链编的，26 线要在有 Apple clang 的宿主上编。

第一版报文写的是 `and this image loads 0x80000002` 与 `N of the programs staged for this image cannot load in it`。lead 复核时指出「cannot load in it」是一个未实测的因果判断，而它出现在会阻止打包的报文里，被拒的人无从判断该不该反驳。改法是让报文只陈述这个闸门实测到的内容（每个文件的 cputype 与 cpusubtype，以及闸门应用的要求），因果解释留在下面那段与 `build.sh:859-865` 的注释里，报文末尾加一行指向本文档。`GATE_RC=1` 的行为与拒绝数都没变，变的只是它说什么；改完对已装车的 root 重跑一遍，仍是 39 个拒绝、8 个通过。

闸门的两组实测：

- 对已装车的 root（`out/ios26-resume/bbmetal-device/root`）跑一遍：**39 个拒绝、8 个通过**。39 个全是 `is an arm64 slice (cpusubtype 0x0)`，缺 LIB64 位的 0 个；9 个在 `root/lib` 下（`libredwood-app`、`-fairplay`、`-media`、`-sb`、`-store`、`-tweaks`、`libredwood.dylib`、`RedwoodMetal.bundle/RedwoodMetal`、`RedwoodAudio.driver/RedwoodAudio`），30 个在 `root/bin` 下。通过的 8 个是 `libredwoodair.dylib`、`libredwoodmetal.dylib`、`libredwood-sb26.dylib`、`libredwood-sbmetal-experiment.dylib`、`input26-service`、`lsprobe`、`framewatch`、`mg_test`。
- 对一棵合成树跑一遍：`GATE_RC=1`，拒绝了容器那份 `cpusubtype 0x2` 的产物与一个 arm64 dylib，通过了宿主那份 `input26-service`、静态的 `init`、arm64e 的 `lsprobe` 与 `libredwood-sb26.dylib`，跳过了一个文本 `motd`。

**39 这个数字要按推论读**：被拒的程序在 26 镜像里加载不了，这个结论从「26 镜像只有 arm64e 共享缓存」推出来（`hackios-xnu-kernel/ios26/23G90__iPhone18,3/` 下只有 `dyld_shared_cache_arm64e*`），没有在设备上实测这 33 个 arm64 动态可执行文件的加载。能推翻它的观察是任何一份 26 线日志里出现这个清单里某个程序的输出，例如 `rwtouch`。这一条已经报给 device，也写在 `build.sh:859-865` 的注释里；闸门自己的报文只说实测到的架构值。

## 4. `docker/dev.sh` 的挂载改动

按 lead 决策二的四条约束改：严格附加、失败开放、只读挂载、路径由 `readlink` 推导。`ROOT` 与原来那条 `docker run` 的参数都保留，新增的部分在 `exec` 之前算出 `SDK_ARGS`：`readlink` 解析 `hackios-xnu-kernel/xnu-deps/26/sdk/iPhoneOS.sdk/System`，去掉末尾的 `/System` 得到 SDK 根，是目录就加 `-v "$SDK26:$SDK26:ro"`；解析不出来或不是目录时打印一行指名路径，然后按原有参数起容器。

失败开放的两条报文：

```
dev.sh: the iOS 26 SDK points at <路径>, which is not a directory here
dev.sh: starting without it; iOS 26 userland builds will not find their framework headers
dev.sh: <路径> is not a symlink; no host SDK to mount
```

参数展开写的是 `${SDK_ARGS[@]+"${SDK_ARGS[@]}"}`：宿主的 bash 是 3.2.57，空数组在 `set -u` 下直接展开会报 unbound variable。

验证用一个 PATH 上的 `docker` 包装做（`docker run -it` 需要 TTY，而跑测试的 shell 开不了 pty，`script -q /dev/null` 报 `openpty: Operation not permitted`）：正常情形追加 `-v <Xcode 27.1 SDK>:<同一路径>:ro`；把符号链接指坏的情形打印一行、退出码 0、参数与原来一致。第二次容器运行走的是 `dev.sh` 本体加一个只去掉 `-it` 的包装，挂载表由 `dev.sh` 自己算，容器内确认 SDK 可见。

`dev.sh` 带 `-it` 的原路径今天在这个环境下没有验证过，两处都按未验证记，不要读成两者等价：照本文档复现的人会直接跑 `docker/dev.sh`，那条命令要一个 TTY，在没有 pty 的 shell 里会以 `openpty: Operation not permitted` 失败，这与挂载是否生效无关；pty 可用的环境里用 `-it` 跑出的结果与用这个包装跑出的结果是否相同，也没有实测。第二次运行的两个实质结论（构建停在 `ptrauth.h`、架构闸对容器那份产物 `GATE_RC=1`）只依赖容器内 SDK 可见与 `build.sh` 的执行，与 TTY 分配无关。

`ldid` 的默认值改在 `build.sh` 里，`dev.sh` 的 PATH 未动。

## 5. 两次容器运行的记录

两次都是 `IOS=../ios26 COMPILE_ONLY=1 bash build.sh`，都在 `src/inject_sb26.c:11` 停在 `'ptrauth.h' file not found`，`BUILD_EXIT=1`。`COMPILE_ONLY=1` 的出口在 `build.sh:926-932`，位置在第一个 `mkapfs`（`:935`）之前，所以两次都没有写任何镜像。失败点从早先的 `CoreFoundation/CoreFoundation.h not found` 变成 `ptrauth.h`，这是 `dev.sh` 那个 SDK 挂载生效的实测依据：26 分支先编 `src/input26_service.c`（`build.sh:227-228`，要 `-framework CoreFoundation -framework IOKit`），再编 `src/inject_sb26.c`（`:230-232`），两次都过了前者、停在后者的第 11 行。

| 项 | 第一次（12:37:11 到 12:37:13） | 第二次（14:15:12 前后） |
|---|---|---|
| 启动方式 | 手写 `docker run -v …` | 仓库里的 `docker/dev.sh`（`5a0b3df`）加只去 `-it` 的包装 |
| 失败点 | `src/inject_sb26.c:11` `ptrauth.h` | 同 |
| `BUILD_EXIT` | 1 | 1 |
| staging 处理 | `mv` 移开，trap 还原 | 同 |
| 三组哈希 | 前后一致 | 前后一致 |

两次运行产出的 `obj/input26-service` 逐字节相同（`3bc70a3fa619ff2c`、54,848 字节），第一次那份保留在证据目录里。容器这条路径在两次运行之间是逐字节可复现的，与 Mesa 那个库记在 `tools/mk-mesa.sh:32-37` 的不可复现相反；这也让第二次运行的产物可以直接拿第一次那份对照。

三组哈希（lead 安全措施一要求的两组，加 `obj/` 清单）在第二次运行前后的实测值，`diff` 两份快照无输出：

- `root26.apfs` 4,943,872 字节、`91271f28e4bc881148a3ba5047bce7f53fc098abbeacfabf9b83b87a919727be`
- `system26.apfs` 4,925,816,832 字节、`d11083be02820507f5639e0a29c6f35256a48d1d4f3cf4cd265eb4b8e346efe4`
- staging `root/` 的清单哈希 `0bd9e466f14711abc7231a30e78a5be2295ec4f401cac6be3e5662aaf2d39691`、59 个条目；`root/` 的 mtime 回到 Oct 28 10:11，`root.task7.bak` 已不存在
- `obj/` 七项清单前后相同

安全措施二到四的落实：每次 `mv`／`rm` 之前打印解析出的绝对路径，并用 `case` 把 `SRC` 与 `BAK` 两个路径限定在这次运行自己的名字上，不符合就拒绝执行；窗口与 device 约定过，起止各发了一条消息；trap 在退出时无条件还原 staging，两次都还原成功，当前 `root/` 是原物。第二次运行前另按 lead 的硬性前置把 `out/ios26-resume/bbmetal-device/` 整目录备份到 `docs/progress/evidence/k90auto/bbmetal-device-backup-run2/`（129 个文件、38 MB，`cp -Rp`，只读源目录），备份与 live 的四个关键哈希逐一相同。

**我在第一次运行里造成的副作用与还原**：那次运行把 `obj/input26-service` 从宿主那份 `5d682cc3729a9cd1`（54,480 字节）覆盖成容器那份 `3bc70a3fa619ff2c`（54,848 字节）。已从 `out/ios26-resume/bbmetal-device/root/bin/input26-service` 用 `cp -p` 取回，逐字节相同，容器那份保留在证据目录里。第二次运行前把还原写进了脚本，跑完自动执行并核哈希。

证据文件都在 `docs/progress/evidence/k90auto/`（git 忽略）：`task7-baseline.txt`、`task7-after-run1.txt`、`task7-compile-only.sh`、`task7-compile-only.log`、`task7-run2.sh`、`task7-run2.log`、`task7-run2-before.txt`、`task7-run2-after.txt`、`shim/docker`、`gate-test/`、`deployed-root-gate.txt`、`input26-service.container-built-3bc70a3f`、`devsh-test.sh`、`bbmetal-device-backup-run2/`。

## 6. 验收对照（按 lead 的 A3 修订）

修订后的验收不再要求「容器内 `build.sh` 跑通并产出可装车的 `obj`」。逐项：

| 项 | 状态 | 依据 |
|---|---|---|
| `dev.sh` 的挂载生效 | 通过 | 第二次运行由 `dev.sh` 本体起容器，容器内 SDK 可见，构建走到了 `inject_sb26.c` 而不是停在框架头 |
| `dev.sh` 失败开放 | 通过 | 把符号链接指坏后打印一行、退出码 0、参数与原来一致 |
| CoreFoundation 那道关（`input26_service.c` 编成 arm64e Mach-O 并签名） | 通过 | 两次运行都编出 `obj/input26-service`，`LC_CODE_SIGNATURE` 在场；`cpusubtype` 是 `0x2`，由 §3 的闸门拒绝 |
| `ld64` 断链来历 | 已结 | `tools/mk-mesa.sh:70`，此前指向什么不可考，结构性问题按 lead 裁定只记录不修 |
| `lsprobe` 断言 | 已加 | `build.sh:488-494`，未被真实构建触发过（两次都停在更早的地方） |
| 两个架构事实与闸门写进文档 | 通过 | §1 与 §3 |
| `obj/input26-service` 还原成宿主那份 | 通过 | `5d682cc3729a9cd1`、54,480 字节 |

## 7. 提交与产物身份

- `.userland.git`：`a61e457`（`build.sh` 的五处新增：`:78` 用法说明、`:93` 起的 `LDID` 默认值、`:217-226` 可解析性检查、`:488-494` `lsprobe` 断言、架构闸加 `COMPILE_ONLY` 出口），`9beb450`（闸门报文改成只陈述实测内容，位置随之变成 `:866-925` 与 `:926-932`），`e0b7b62`（`redwoodmetal.m:2405` 的注释更正，只改注释、行数不变，`:2408` 的 `NOCOPY_LIMIT` 仍在原行号）。`common/ugit status --short` 为空。
- 顶层仓：`5a0b3df`（`docker/dev.sh`）。`build.sh` 现在 1138 行，在 1200 行的约定之内。
- 未改：`root26.apfs`、`system26.apfs`、`out/ios26-resume/` 下的任何产物、`tools/mk-mesa.sh`、设备。

## 8. 未验证的部分

- `lsprobe` 的断言没有被一次真实构建触发过，两次运行都停在它之前。
- 架构闸那 33 个 arm64 动态可执行文件在 26 镜像里加载不了，是推论，见 §3 末尾那条能推翻它的观察。
- `COMPILE_ONLY=1` 的出口在闸门之后，而两次运行都没跑到闸门，所以「闸门在正常构建流程里的位置正确」这一点是由代码位置（`:866-925` 在 `:935` 之前）与两次独立跑闸门得到的，不是一次完整构建走通的。
- `dev.sh` 带 `-it` 的原路径在这个环境下没有验证过（没有 pty），包装路径与 `-it` 路径的结果是否等价也没有验证过，两处见 §4。
- 容器里补上 `ptrauth.h` 之后 `__has_feature(ptrauth)` 仍为 0 这一条，依据是 clang 的资源目录里没有该头文件与容器 clang 18 的实测值，没有实际补一个头文件再编一次来验证。
