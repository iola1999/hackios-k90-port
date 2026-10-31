# Spotlight 崩溃循环与系统镜像里缺的模型（2026-10-31）

`bo18` 起的巡检在今天视图里上下滚动。向下滑会打开 Spotlight 搜索，之后 Spotlight 每次启动都中止，ReportCrash 为每次崩溃写报告，处理器温度升到 66～69 °C。本文记录循环的读数、中止的位置、系统镜像缺模型的原因与修复后的读数。逐轮记录见[开机次序与性能记录](../progress/2026-10-31-boot-order-and-performance.md)。

## 1. 结论

- Spotlight 中止的原因：SpotlightServices 按名字找排序模型 `<名字>.mlmodelc`，系统镜像里没有这些文件，代码把 nil 传给 `+[NSURL fileURLWithPath:]`，抛出的异常没有被捕获。
- 系统镜像缺模型的原因：`ios165/select-system.py`（`ios26/select-system.py` 是它的链接）不从框架目录取 `.mlmodelc`，按 2026-10-26 的选择规则共有 53 个包、506 MB 的模型不在镜像里。
- 修复：选择规则加上 SpotlightResources 的 root 与 English 两个必需资源包的全部文件（21 MB），重建 `system26.apfs`。`bo21` 里 Spotlight 没有崩溃，ReportCrash 的处理器时间从 72.5 秒降到 7.1 秒，今天视图滚动每步的帧数从 10～16 回到 29～36。
- `bo19` 里 ReportCrash 的 66.9 秒处理器时间主要来自 Spotlight（399 次崩溃），duetexpertd 退出 16 次。
- 合成路径分析里 `bo18`～`bo20` 今天视图滚动的帧率是在这个循环期间测的，不能用来判断合成路径本身的开销（[合成路径的处理器开销](2026-10-31-compositor-cpu-path.md) §16）。

## 2. 循环的读数

以 `kernel-12377-cmd43-bo20` 为例：

- 第一次中止在 td2（今天视图里第二次向下滑）结束后约 0.75 秒。
- 内核日志记了 664 行 Spotlight 退出（`redwood: proc Spotlight pid N died on signal 6`），按 pid 去重后可定位时间的 308 次落在 560～620 秒，约每秒 5 次，直到日志结束没有停。
- 同一时段键盘相关进程启动（kbd、InputUI、inputanalyticsd、StickerPickerService），内核多次报「corpse slots full」。
- 两次 `ps`（巡检结束、今天视图之后）之间，全部进程的处理器时间增加 137.7 秒，其中 ReportCrash 72.5 秒。
- 处理器集群温度在循环前 41～48 °C，循环开始后 66～69 °C，GPU 54～56 °C。
- 今天视图滚动每步（1 秒）的帧数：循环开始前 tu1、td1、tu2、td2 为 27、28、18、29；之后 tu3～td8 为 7～16。

## 3. 中止的位置

- `userabort` 行给出的回溯（共享缓存 slide `0xb03c000`）：`abort` ← libc++abi 的 rethrow ← `objc_exception_throw` ← Foundation ← SpotlightServices `+0x45b64` ← `+0x42d84` ← libdispatch 工作线程。
- SpotlightServices `+0x42c9c` 调用 `+[PRSModelManager cannedInfoForType:directivesPath:modelName:]` 取得模型名与指令文件路径，日志格式串是「[Model loading] loading canned model type %@ model name %@ directive path %@」，之后 `+0x42d80` 调用 `initSpecificModel:error:`。
- `initSpecificModel:error:` 的实现（`+0x45afc`）先拼出 `stringWithFormat:@"%@.mlmodelc"`，再从 `filePathArrayForKey:@"SpotlightServices"` 返回的文件列表里找同名文件，找不到时得到 nil，随后 `fileURLWithPath:` 收到 nil 抛出异常。
- iOS 26.6.2 的 SpotlightResources 把这些模型放在框架内的必需资源包里，例如 `RequiredAssets_root.bundle/AssetData/spotlightservices/spotlight_l2.mlmodelc`。

## 4. 镜像里缺的模型

- `select-system.py` 对框架目录的文件要求不大于 4 MB、扩展名不在 `SKIP_EXT`、路径不含 `.mlmodelc/`。模型目录里的 `.bin`、`.DAT`、`model.mil` 等因此全部不在镜像里。
- 按 2026-10-26 的 `rootfs.slt` 统计，框架与应用里被排除的模型共 506 MB、53 个包，最大的是 CoreSceneUnderstanding（252 MB）、VoiceServices（62 MB）、SpotlightResources（32 MB）。
- 这次新增 `KEEP_MODELS`：SpotlightResources 的 `RequiredAssets_root.bundle` 与 `RequiredAssets_en.bundle` 整包保留，共 39 个文件、21 MB，其中模型 8.5 MB，另有原先因大于 4 MB 被排除的 `parser/lexicon.cache` 与 `safety/safety_resources.map` 各约 6 MB。
- 重建方法：用现有 `rootfs.slt` 重新生成 `system.files` 与 `system.manifest`，与旧清单相比只多这 39 个文件；从 IPSW 的根文件系统镜像只拷这些文件进 `ios26/rootfs`；按 `userland/build.sh` 的系统镜像步骤生成镜像，`/sbin/launchd` 与 `RedwoodTriangle.app` 取自旧镜像，构建 91 秒。新镜像 4944056320 字节，旧镜像保留为 `userland/system26.apfs.oct26`。
- 其他缺模型的读数：`bo20` 有一行「MCCKitCategorization/TrialLoader.swift:574: Fatal error: model compile error」，`BlackPearl.mlpackage` 读不到，只出现一次，没有形成循环。

## 5. 修复后的读数

`kernel-12377-cmd44-bo21`，巡检与 `bo20` 相同：

- Spotlight 没有退出记录。全轮退出的进程是 ScreenContinuity 12 次、`HomeWidgetLockSc`（进程名截断）4 次，以及开机阶段各 1 次的几个任务。
- 两次 `ps` 之间全部进程的处理器时间增加 45.1 秒（`bo20` 137.7 秒），ReportCrash 7.1 秒。
- 今天视图段的处理器集群温度 41～51 °C。
- 今天视图滚动每步 29～36 帧的有 11 步；tu1、td1、tu3、tu4、tu8 为 0～14 帧，其中 td1、tu3、tu4 有看门狗转储，属于没有反应的手势（[合成路径的处理器开销](2026-10-31-compositor-cpu-path.md) §12）。

## 6. 未解决

- ScreenContinuity 从 `bo18` 起每轮退出 12～16 次（SIGTRAP，`usertrap` 的 pc 在 ScreenSharingKit `+0x1ef54`，Swift 运行时的陷阱），第一次退出在键盘进程启动之后。它是 REST 登记的按需任务 `com.apple.ScreenContinuityShell`，谁在查找它的服务还没有读数。
- 其余 52 个包的模型仍不在镜像里。哪些进程会在这台设备上加载它们，目前只能等进程退出或报错时逐个发现。
