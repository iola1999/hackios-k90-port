# 打包镜像条目的进入通道与两层对账

2026-10-28，display。task-7 的记录。这份文档回答一个问题：一次打包出来的 root 镜像里，每个条目是从哪条通道进去的，以及哪一条通道今天没有记录。起因是 round F 第一次开始一轮之后中止，`/bin/framewatch` 不在新镜像里，而 `package.py` 的两个断言都通过了。

## 1. 通道模型

`tools/k90auto/package.py` 组装镜像树的全过程：

| 步骤 | 位置 | 通道 |
|---|---|---|
| `shutil.copytree(BASE / "root", dest, symlinks=True)` | `:425` | staging 树，整棵拷进 `dest` |
| `etc/var.skel` 追加 `userland/var.skel.extra` 里 base root 太旧而没有的行 | `:431-440` | 一个文本文件 |
| 三个 dylib 覆盖进去（shim、driver、air） | `:449-451` | 本轮构建产物 |
| `for program in EXTRA_PROGRAMS: shutil.copy2(program, dest / "bin" / program.name)` | `:452-454` | 环境变量 `PAYLOAD_PROGRAMS`（`:56`） |
| `(dest / "etc/inject.conf").write_text(INJECT)` | `:493` | 脚本内的常量 |
| `shutil.copy2(probe, dest / "bin/lsprobe")`，仅当 `PROBE` | `:494-495` | 环境变量 `PROBE`，`lsprobe` 由脚本自建（`:64`、`:402`、`:495`） |
| `(dest / JOBS).write_bytes(jobs)` | `:500` | `JOBS_SOURCE`（`:90`）加脚本前置的 `PROBE_LINE` 与 `VARSTORE_LINE`（`:415-417`） |
| `add_switch`、`add_msaa`、`add_extra_jobs`、`add_diag` | `:501-506` | 环境变量 `MSAA`、`EXTRA_JOBS`、`JOBS_DROP`、`REDWOOD_DIAG` |
| `mkapfs.py -z --plain fw -o OUT/root.apfs redwood=<dest>` | `:517-518` | 打包 |

`BASE` 是 `WORKSPACE / "out/ios26-resume/air-arm64e-device/on"`（`:84`），`WORKSPACE` 是内核仓，所以那棵 staging 树在 `hackios-xnu-kernel/out/ios26-resume/` 下。

两个断言在打包之后：`:525` 断 `set(after) - set(before) == added`，`added` 只由 `EXTRA_JOBS` 的 plist（减去 `JOBS_DROP`）、`/bin/lsprobe`（当 `PROBE`）、`PAYLOAD_PROGRAMS` 的名字构成（`:522-524`）；`:527` 断 `set(before) - set(after) == set()`。`before` 是 `records(BASE / "root.apfs")`（`:419`），`after` 是新镜像的（`:521`）。

## 2. 这次丢失为什么两个断言都通过

`before` 与 `after` 的参照物是 base 镜像 `on/root.apfs`，它的 sha256 由 `:385` 断言（roundb 的记录里是 `33ed5fc9cb18367c124e6fd26a2fc982f7d80b3a44e04754f87cf74b5aa381f0`）。`/bin/framewatch` 从来不在 base 镜像里：device 实测 base 的 `/bin` 是 34 条，不含 `framewatch` 与 `lsprobe`，它是经 `PAYLOAD_PROGRAMS` 进 roundb 镜像的。通道一掉，`before` 没有它、`after` 也没有它，`:525` 与 `:527` 都成立。

参照物是 base 镜像，上一轮实际跑过的镜像不在比较范围里。device 的 `image-diff.py`（提交 `e7955f5`）拿上一轮镜像作参照，补的是这一面。

## 3. layer ②：roundb 的 11 条 added 逐条归通道

读 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundb/manifest.json` 的 `pack.changes`，21 条 changes 里 11 条是 `null→sha` 的 added 记法：

| added 条目 | 通道 | 记录里有对应字段吗 |
|---|---|---|
| 9 个 `/LaunchDaemons/*.plist`（PosterBoard、ReportCrash、biomed、chronod、contextstored、dasd、linkd、mobile.installd、replicatord） | `EXTRA_JOBS` | 有：`jobs_effective_count` 36、`jobs_dropped` `['com.apple.appprotectiond.plist']`、`jobs_source` 的 path 与 sha256 |
| `/bin/lsprobe` | `PROBE` | 有：`probe` `True`、`probe_sources` |
| `/bin/framewatch` | `PAYLOAD_PROGRAMS` | **没有：记录里不存在 `payload_programs` 这个字段** |

`pack` 记录（`package.py:615-650`）存了 `probe`、`probe_sources`、`jobs_source`、`jobs_dropped`、`jobs_effective`、`jobs_effective_count`、`redwood_diag`、`varstore_show`、`gpu_speed`、`changes`、`round_notes`、`root_sha256`，11 条 added 里 10 条的通道都能从字段读出来，唯一读不出来的是 `framewatch` 那一条。device 当时是从 `changes["/bin/framewatch"]` 这个效果反推配方的。

11 条与 device 的自洽算式一致：base 125 条 + 9 个 daemon plist + `lsprobe` + `framewatch` = 136 = roundb 输出镜像的条目数。

round F 的记录在它收尾之后再补这一层，方法与上面相同。

## 4. layer ①：staging 树对 base 镜像全树

用 device 导出的 `docs/progress/evidence/k90auto/staging-audit-base-33ed5fc9-paths.txt`（125 条 = 103 个 kind=8 文件 + 21 个 kind=4 目录 + 1 个 kind=10 符号链接）对 `hackios-xnu-kernel/out/ios26-resume/air-arm64e-device/on/root`：

- 文件 103 个，缺失 0，size 全部相同，mode 全部相同（清单里的 mode 是完整 `st_mode`，含文件类型位，比对时不能掩到 `0o7777`）。
- 目录 21 个与符号链接 1 个，mode 全部相同。那个符号链接是 `/hal/RedwoodAudio.driver -> /redwood/lib/RedwoodAudio.driver`。
- staging 侧没有多余条目。

**所以 task-7 那次重排没有改动这棵树的内容。**

一个口径限制：这一步比的是 size 与 mode，没有比内容，一个同尺寸的替换文件查不出来。

另外量到 6 个条目在 roundb 的输出镜像里而不在 staging 树里，它们的通道是：`/bin/framewatch`（`PAYLOAD_PROGRAMS`）、`/bin/lsprobe`（`PROBE`），以及 `/lib` 下 `RedwoodAudio.driver/{Info.plist,RedwoodAudio}` 与 `RedwoodMetal.bundle/{Info.plist,RedwoodMetal}` 四条。后四条的通道由断言反推：roundb 那次打包 `:525` 通过了，而 `added` 只由 `EXTRA_JOBS` 的 plist、`/bin/lsprobe`、`PAYLOAD_PROGRAMS` 的名字构成，这四条都不在其中，所以它们必须在 `before` 里，即 base 镜像自带。device 后来导出的 base 清单证实了这一点，四条都在。

## 5. 两棵 `root/` 树的关系

`package.py` 只读 `BASE/root`。`hackios-xnu-kernel/userland/root/` 是另一棵树：

| | `userland/root` | `…/air-arm64e-device/on/root` |
|---|---|---|
| 文件数 | 49 | 103 |
| `bin/framewatch` | 有，sha256 前 12 位 `8c8869b8…` | 无 |
| `etc/inject.conf`、`etc/rc`、`etc/rc.jobs`、`etc/var.skel` | 无 | 有 |
| `lib/libredwoodmetal.dylib` | 无 | 有，`1ea7c58d…` |
| `bin/rwtouch` | `2bcbda75…` | `f6505552…` |
| `sbin/init` | `0e2e63e7…` | `fdbaa55a…` |

`grep -rln "air-arm64e-device"` 在 `tools/k90auto/`、`hackios-xnu-kernel/tools/*.py`、`userland/*.sh`、`userland/*.py` 四个位置只命中 `package.py:84` 一处。所以 staging 那棵树没有生成脚本，也没有任何哈希断言：`:385` 断的是 base 镜像，与这棵树无关。它是手工维护的产物，而它所在的 `out/` 目录被 git 忽略，它的应有状态在仓库里没有任何记录。

## 6. 修法方案（只提，未动手）

方案改 `package.py`，而任何设备轮期间不碰它，所以这里只记方案。

**清单形式**：两份，都用 JSON。`tools/k90auto/staging-manifest.json` 记 `BASE/root` 下每个条目的镜像路径、kind、mode，文件另记 sha256 与 size，符号链接记 target，头部记生成时所对的 `BASE_ROOT_SHA256` 与生成命令；校验值用 sha256，因为 §4 那一步只比 size 与 mode，同尺寸的替换查不出来。pack 记录增一个 `"payload_programs"` 字段，记 `EXTRA_PROGRAMS` 的每个路径与其 sha256，放在已有的 `"probe"` 旁边。

**断言位置**：树清单的断言加在 `:425` 之后、`:449` 之前，因为 `:425` 是这棵树进入打包的唯一位置，而 `:449-506` 都是有目的地改 `dest`。报错按路径分类（缺失、多余、mode、sha256）并写出重新生成清单的命令。放行开关 `ALLOW_STAGING_CHANGE=1`，与已有的 `ALLOW_DIRTY`（`:190`）、`ALLOW_DRIVER_CHANGE`（`:215`）同形。`payload_programs` 只记录不断言；另建议打包开头打一行上一轮配方与本轮配方的差异，比对 `PROBE`、`PAYLOAD_PROGRAMS`、`JOBS_SOURCE`、`EXTRA_JOBS`、`JOBS_DROP`、`MSAA`、`REDWOOD_DIAG`、`GPU_SPEED`，读上一份 pack 记录。打印而不断言，因为一轮合法地会改这些，打印的作用是让漏设的环境变量在设备轮之前可见。

**清单由谁何时更新**：新脚本 `tools/k90auto/staging-manifest.py`，`--check` 与 `--write` 两个模式，形状与 `tools/unwrap_md.py` 一致。改了 staging 树的人在同一个提交里跑 `--write`，打包时 `--check` 那条断言强制它。清单是顶层仓库的跟踪文件，树在 git 忽略的 `out/` 下，所以清单是这棵树唯一被记录的状态。`payload_programs` 由 `package.py` 自己写，不需要维护。

**与 `:385` 的关系**：`:385` 断 base 镜像的一个哈希，清单断 base 树的 103 个哈希，覆盖 `package.py` 读的两个不同输入（`:385` 与 `:419` 读镜像，`:425` 读树），谁也不替代谁。清单头部记 `BASE_ROOT_SHA256`，重建 base 时只动一侧会被看见。

**与 `image-diff.py` 的分工**：清单是输入闸，在打包之前，比对树与仓库里记录的应有状态，回答「输入是不是我们记录的那棵树」；`image-diff.py` 是输出闸，在打包之后，比对新镜像与上一轮实际跑过的镜像，回答「这一轮的载荷改了什么」。两者在一次手工改树上都会报，差别在时机与所指。这次事故只有 `image-diff.py` 那一侧能看见，因为 `framewatch` 从来不在这棵树里，树与它自己的清单完全相符；配方缺口由 `payload_programs` 那一项补。

落地时机建议排在 round F 收尾之后，与打包闸的另一处盲区（`package.py:221-233` 的 `dirty_sources()` 只看 `common/ugit status --short` 与顶层仓库限定 `-- tools/k90auto`，所以 `xnu/files/` 下的改动对闸不可见）合成一笔，因为两处都是给 `package.py` 加断言，一次改动一次验证。

## 7. 未验证

1. round F 的 pack 记录在它收尾之前读不到那个形状（`bbmetal-device/manifest.json` 里没有 `pack` 键的这批字段），layer ② 对 round F 还没有做。
2. staging 树的内容哈希没有逐一比过，§4 比的是 size 与 mode。
3. `EXTRA_JOBS` 那 9 个 plist 的内容是否与 base 镜像里同名文件一致，没有比；它们在 `changes` 里是 added，说明 base 镜像没有同名条目。
