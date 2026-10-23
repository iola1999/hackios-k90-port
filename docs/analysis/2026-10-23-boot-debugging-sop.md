# annibale 调试案例：启动、显示与 Android 异常

记录日期：2026-10-23。适用设备为 REDMI K90（`annibale`），接手的 dsh 会话为 `session-DSH_SESSION_ID`，后续来源为 [Codex 主会话](codex://threads/SOURCE_CONVERSATION_ID)。本次更新包含主会话 22:19 的构建、随后的 USB 检查、v2 镜像打包及上传脚本的五项模拟检查：kernel 基于 `75fb322`，已有未提交修复。主会话仍在继续，本文记录对应阶段的结果。通用方法见[项目排查与协作手册](../plan/debugging-and-collaboration.md)，进度继续记入[总账](../plan/2026-10-23-tracking.md)。

原始材料在本机 `/tmp/hackios-handoff/`，首轮摘录为 `docs/analysis/data/2026-10-23-loader-debug.txt`，主会话还将 loader、自检和检查点日志复制到 `docs/progress/evidence/2026-10-23-handoff/`。这些日志与截图按本地产物忽略；本文保留独立阅读所需的关键结果。

## 本次解决到哪里

本次恢复了 USB 驻留调试流程：在 `boot_a` 写入只包含 loader 的镜像，经槽位启动进入 loader，再通过 USB 上传内核测试 payload。loader 日志、内存图和 framebuffer 均已成功读回。返回路径自检通过，内核检查点 1、2、3、4、5 均返回对应结果。

首轮检查点 10 未取得返回结果，后续仍能枚举 `xnuloader`，命令请求超时。源码检查发现，早期返回代码读取了尚未设置的 `PE_state.bootArgs`。主会话修复该前置条件，并改用 `cpus=1 bootcpu=1` 复测，取得 `result: checkpoint 10 0`。随后一次运行返回 669 字节内核日志，包含 `Unclassified kernel abort (fault_code=0x10)`，实际故障已可继续定位。

随后修复 GIC redistributor 区间及步长、GOP 和 fallback 屏幕尺寸，完成内核、loader 与固件构建。K90 已返回检查点 20、21，loader 上报 `1156 2510 4624`。新 QEMU 回归取得 `BSD root: md0`、System/redwood 卷挂载和 `Successfully spawned SpringBoard[7] because system support` 日志。K90 的面板实际显示、完整系统盘挂载和 iOS 界面仍需验证。QEMU 既有桌面记录见[独立记录](../progress/2026-10-23-ios-booted-qemu.md)。

Android 先重建 SystemUI 编译缓存，再根据新崩溃栈定位 MIUIAod 插件并重建其编译缓存。用户于 22:10 左右确认系统界面恢复；其他应用的异常单独排查。完整系统盘已通过 USB 上传 RAM，返回 `OKAY`；随后空日志读取失败，USB 请求持续超时，主会话正在处理协议恢复。零长度上传修复已编译，尚待真机复测。

### 新增结果与验证范围

| 项目 | 实际变更或读数 | 本次可确认的范围 |
|---|---|---|
| 检查点 10 返回 | `loader_jump()` 增加 `PE_state.bootArgs != NULL` 条件；复测为 `checkpoint 10 0` | 修复后的内核在 `bootcpu=1` 条件下可执行并返回该检查点；本轮同时改变了启动 CPU，单变量对照尚未完成 |
| CPU 分离调试 | 日志为 `core 100: the firmware answers 0`，随后内核返回 | MPIDR `0x100` 已通过该次启动与返回验证；其他 CPU 分别验收 |
| 实际内核异常 | 一轮平台初始化后出现 `fault_code=0x10`，返回 669 字节日志 | 日志返回路径可用；后续修复后的输入已通过检查点 20、21，完整启动继续验证 |
| GIC 参数 | loader 输出范围 `0x200000`、stride `0x40000`；内核读取并校验该属性 | 新输入在 K90 返回检查点 20、21，尚未完成所有 CPU 和中断行为的验收 |
| 屏幕尺寸 | `annibale.dsc` 与 loader fallback 改为 `1156×2510`；真机 `getvar screen` 返回 `1156 2510 4624` | 新配置已进入真机 loader，面板实际扫描与花屏修复待确认 |
| Android 缓存 | 分别重建 `com.android.systemui`、`com.miui.aod` 后，进程保持运行且状态栏、导航栏窗口恢复 | 用户已确认系统界面恢复；其他应用分别验收 |
| USB 系统盘 | `oem ramdisk` 后上传 2,492,227,584 字节，`stage` 返回 `OKAY`，耗时 62.298 秒 | 传输完成；内容校验、挂载和 iOS 启动仍待完成 |
| 空日志上传 | `get_staged` 收到零长度结果后，后续请求超时；新增 `FAIL no staged data` 分支 | 新 loader 已编译；恢复后的协议往返和完整启动待验证 |

## 接手先核对什么

1. 阅读最近几轮完整用户消息、实际命令及输出，再对照当前源码。此次用户明确反馈过画面逐行向左偏移、反复回到 Android，以及希望减少重复写入。这些反馈直接决定了先建立驻留调试流程的顺序。
2. 检查父仓库与子模块的工作区状态、设备操作进程和产物时间。保留其他工作留下的修改；串行执行同一设备的 fastboot 请求。
3. 读取设备实际状态。Android 使用 `adb devices -l`、`ro.boot.slot_suffix`、`ro.build.fingerprint`、`sys.boot_completed`；fastboot 使用枚举结果、`getvar product` 和 `getvar is-userspace`。状态判断同时保留命令退出码、标准输出和标准错误。
4. 核对写入目标与备份范围。本工作区约定 `boot_a` 用于实验，`_b` 保留 Android。`annibale-backup/20261023-2100/` 的 userdata 尾部备份建立于此前已有写入之后，只能恢复备份时刻的该段内容。
5. 把主机与设备环境分开记录。构建成功、命令受理、USB 枚举、内核检查点和用户界面分别验收。

## 本次查明的问题

| 现象或旧操作 | 本次核对结果 | 后续做法 |
|---|---|---|
| 固定使用 Android 的 USB 序列号轮询 loader | LK/ADB 实测序列号为 `${ANDROID_SERIAL}`；loader 枚举序列号为 `xnuloader`。固定旧序列号的请求超时后，用 `-s xnuloader` 立即成功 | 每次 USB 模式切换后重新枚举，再向实际序列号查询 `product` |
| 使用 `fastboot upload` 抓截图 | 本机 fastboot 报 `unknown command upload`；命令行接口提供 `get_staged` | `oem screenshot` 后执行 `get_staged`；`upload` 是 loader 接收的协议命令 |
| 只执行 `oem log` 并保存它的命令输出 | 该命令准备日志缓冲，命令响应只有 `OKAY` 等协议状态 | 随后执行 `get_staged`，读取日志正文 |
| 通过 `oem logwrite` 准备保存随后运行的日志 | 源码只在本次 `flush_log()` 调用期间允许回退到 `boot_a`，随后立即清除标志。此前读取的 `boot_a` 开头已有 loader 文本 | 常规调试使用 USB；`boot_a` 存放启动镜像期间保留其镜像头 |
| `oem run` 后一次 `getvar` 超时，记录为「两秒后 loader 消失」 | 单次请求只给出超时结果；同一 CPU 运行内核期间也无法处理 loader USB 请求 | 分别记录 USB 是否枚举、请求是否应答、是否出现新一次启动和返回结果 |
| 认为设置 `loader_return_after=8` 就能自动恢复 | 该功能依赖内核进入相应启动阶段并运行定时回调；本版 `wdt_arm()` 只为 `platform_redwood` 启用虚拟看门狗 | annibale 的早期停滞需要单独安排恢复；本轮结束条件不得只依赖这个参数 |
| 检查点 10 返回无响应 | 返回函数在 `PE_init_platform()` 之前解析 boot-args，会访问尚未设置的指针；增加前提检查后在 `bootcpu=1` 复测成功 | 同时检查被测功能与诊断代码的初始化依赖 |
| 按 `1440×3168` 解释屏幕 | 首轮 GOP 上报 `1440 3168 5760`，来自固件配置；Android DRM 模式及现有面板 XML 均为 `1156×2510` | 配置已修改，继续核实实际扫描分辨率、stride 和像素格式 |
| Android 缺失通知栏、手势条和动画，重启后仍异常 | `com.android.systemui` 持续崩溃，栈经过 `art::VdexFile::ComputeClassStatus`，出现字符串索引校验失败 | 单独排查 SystemUI 使用的文件与编译缓存；修复后验收界面及崩溃日志 |
| fastboot 退出码为 0，输出却含失败 | `getvar result` 返回 `FAILED (Write to device failed (No such process))` | 同时检查退出码、协议状态和预期结果，失败后停止后续依赖操作 |
| 大镜像已传完，随后的日志读取失败 | 系统盘 `stage` 返回成功；日志读取报告 0 字节，后续请求超时 | 分别记录传输结果和读取状态，先检查协议状态，再决定是否重传镜像 |

### 日志缓冲的使用顺序

[`loader.c`](../../hackios-xnu-kernel/xnuloader/loader.c) 的 `write_logs()` 会合并 loader 与内核日志，并准备 `get_staged` 的内容。内核正常返回后，先读取 `getvar result`，再直接执行 `get_staged`。空闲状态的 `oem log` 调用 `compose_logs(NULL, 0)`，会用 loader 的 `log_buf` 重新生成暂存内容，原先合并的内核缓冲随之被替换。

无日志分区的路径还会经 `put_char()` 将返回的内核文本写入 `log_buf`，因此此次 669 字节的短日志在再次 `oem log` 后仍能看到。该缓冲只有 32 KiB，文本写入超过容量会截断；重复准备日志无法保证保留完整的内核输出。直接读取已经合并的结果可保留该次原始内容。

截图与日志共用 `staged_data`。`oem screenshot`、`oem log`、`get_staged` 必须按一次准备、一次读取的顺序完成，中间插入另一个准备命令会改变读取内容。日志读取后保存为独立文件，再开始下一次运行。

### 对旧记录的修正

[设备手册](../plan/device-test-playbook.md) 和[下午试跑记录](../progress/2026-10-23-annibale-device-trials.md) 中关于 USB 不通、BlockIo 写入未观察到落盘的描述保留其当时的测试条件。此次已取得 loader USB 应答与日志，并从此前的 `boot_a` 读回 loader 文本。后续操作按这些新结果重新判断相应路径。

`oem logwrite` 需要检查其实际实现：本版会在缺少 `logdump` 分区时覆盖 `boot_a` 开头，写入范围随日志长度对齐到块大小。该行为能够破坏 A 槽启动镜像；每次回到 Android 的完整原因仍需结合槽位标志和启动日志确认。

## 真机调试 SOP

### 确认入口与恢复方式

先读[设备手册](../plan/device-test-playbook.md)及本篇修正，再识别 Android、LK fastboot、fastbootd、loader 或仅有 USB 枚举的状态。进入方式也要记录：`fastboot boot` 与从 `boot_a` 启动会经过不同的显示初始化过程。

本次使用 `handoff-loader.img` 写入 `boot_a`、设置 A 槽后重启，进入带 `--usb` 的 loader。该镜像只负责驻留和接收后续 payload。后续只改内核或 boot-args，优先用 `fastboot stage` 更新 RAM 中的 payload；修改 loader 或 UEFI 后才重打相应启动镜像。A/B 槽位重试仍可能影响后续启动选择，驻留镜像的存在只确认本次启动路径。

恢复前先确认设备还能处理哪些请求。loader 返回命令循环后可继续测试；命令持续无响应则记录最后成功的步骤，再安排恢复到 LK。需要返回 Android 时，在 LK 确认设备身份后选择 B 槽。每次恢复后重新读取槽位和 USB 身份。

### 建立可读取的基线

在 loader 空闲状态读取 `product`、`version`、`result`、启动日志、内存图和屏幕参数。命令行 fastboot 常将有效结果写入标准错误，采集时合并两个输出流。本机脚本使用 Python `subprocess.run(..., timeout=...)` 限定单次执行时长；超时、非零退出和输出中的 `FAILED` 都要单独记录，并停止依赖该结果的操作。

以下示例只读取 loader 数据，序列号须先由 `fastboot devices` 确认。`get_staged` 的目标目录在主机上创建。

```python
from pathlib import Path
import subprocess

out = Path("logs/bringup-baseline")
out.mkdir(parents=True, exist_ok=True)

def fb(*args, seconds=10):
    result = subprocess.run(
        ["fastboot", "-s", "xnuloader", *map(str, args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=seconds,
        check=True,
    )
    print(result.stdout, end="")
    if "FAILED" in result.stdout:
        raise RuntimeError(result.stdout)
    return result.stdout

if "product: xnuloader" not in fb("getvar", "product"):
    raise RuntimeError("unexpected fastboot product")
fb("getvar", "version")
fb("getvar", "result")
fb("oem", "log")
fb("get_staged", out / "loader.log")
fb("oem", "memmap")
fb("oem", "log")
fb("get_staged", out / "memory-map.log")
fb("getvar", "screen")
fb("oem", "screenshot")
fb("get_staged", out / "screen.raw", seconds=30)
```

示例中的 10 秒和 30 秒用于限制主机请求等待时间，设备执行阶段由返回内容与后续观测判断。旧版 loader 的空日志读取曾引起后续请求超时；使用前确认已加载含零长度处理的版本，首次启动也要确认日志缓冲已有内容。本次原始 framebuffer 大小为 `18,247,680` 字节，与首轮上报的 `5760 × 3168` 一致；后续画面按该轮实际读数解析。

### 先验证返回路径，再逐段进入内核

本次测试 payload 包含现有内核、小 `root.apfs` 和 `debug=0x10e cpus=1 loader_return_after=8 -v`，未包含 `rdfile`。小镜像只服务早期启动与检查点测试，完整 iOS 启动还需要系统盘。

| 步骤 | 操作 | 成功条件 |
|---|---|---|
| 上传测试 payload | `fastboot stage <payload>` | 命令成功，记录实际文件大小与 SHA-256 |
| 返回路径自检 | `oem selftest` | `getvar result` 返回 `selftest-ok`，日志含 `return-path self test passed` |
| 分段检查 | 每次只运行一个 `oem run N` | `getvar result` 返回对应的 `checkpoint N`，随后直接读取 `get_staged` |
| 缩小失败范围 | 对照最后成功与首个未返回的检查点 | 阅读两点之间的源码，同时检查检查点自身的返回路径 |
| 继续完整启动 | 前述阶段有可重复结果后再增加系统盘或驱动 | 新增阶段有明确日志或画面，保留前一版可复现输入 |

`selftest` 会准备内核布局并测试跳转、返回，不进入内核入口。本次检查点 1–5 的具体位置来自 [`start.s` 补丁](../../hackios-xnu-kernel/xnu/patches/53-osfmk%arm64%start.s.patch)：入口保存参数后、设置低位异常向量及 OS 锁后、启动页表写入后、开启 MMU 前、开启 MMU 后。检查点 10 来自 [`arm_init.c` 补丁](../../hackios-xnu-kernel/xnu/patches/46-osfmk%arm%arm_init.c.patch)，位于复制 boot args 之后、`cpu_data_init()` 之前。

只调整一个影响执行的条件，并保存运行 payload、命令参数和结果。例如先验证一个检查点，再调整 CPU 启动方式；先验证系统盘来源，再增加外设开关。重复相同输入应有明确目的，例如确认问题能否复现。

### 区分内核运行方式与 USB 可用性

源码中的实时日志和 `oem stop` 依赖 `run_on_other_cpu()` 循环继续调用 `usb_poll_command()`。内核在 loader 当前 CPU 上运行，控制权会进入内核，USB 命令要等内核返回才能处理。`cpus=1` 只限制内核使用的 CPU 数量；选择启动 CPU 使用 `bootcpu=`。

首轮检查点 10 无响应后，主机仍能枚举 `xnuloader`，因此记录为「USB 枚举存在、命令无响应」。后续 `bootcpu=1` 已取得检查点返回和内核异常日志，其他 CPU 的启动与返回路径仍需真机验证。只有观察到重新枚举、启动日志或系统状态变化，才能继续判断是否发生重启。

GIC 几何问题已修复到本次检查点验证范围：设备树记录 redistributor 区间大小为 `0x200000`、步长为 `0x40000`；旧 loader 生成的区间大小为 `0x100000`，内核按 `0x20000` 扫描。当前修改让 loader 写出区间及 `redistributor-stride`，内核读取该属性并检查尺寸、最小步长、上界和对齐。22:14 的 `gic-checkpoint-20.log`、`gic-checkpoint-21.log` 均取得对应返回，启动参数包含 `cpus=1 bootcpu=1`。其他 CPU、完整中断功能和完整启动仍需验收；检查点 10 的返回缺陷与这项修复分别记录。

### 检查点自身的初始化依赖

`arm_init()` 的检查点 10 位于 `PE_init_platform()` 之前；`loader_jump()` 为判断是否使用其他 CPU，会解析 `bootcpu`。其调用的 `PE_boot_args()` 从 `PE_state.bootArgs` 读取命令行。该指针在此阶段尚未设置，返回路径因此包含无效访问。修复先检查该指针，再调用解析函数。

本次经验是先验证诊断函数所需的状态，再解释检查点结果。后续应检查早期异常处理中使用的锁、CPU 编号、地址转换和日志缓冲是否已经可用。能够返回检查点 5，只覆盖该汇编返回路径；进入 C 代码后的返回逻辑还有自己的依赖。

### 最后加载系统盘并验证用户界面

早期检查点通过后，主会话执行 `oem ramdisk`，通过 USB 上传完整 `system.apfs`。本次 2,492,227,584 字节传输返回 `OKAY`，耗时 62.298 秒。现有实现把系统盘放入已申请的内存窗口；后续仍需核对内容、payload 中的磁盘来源及实际挂载日志。

随后 `oem log` 返回成功，但 `get_staged` 报告设备可上传 0 字节。下一次 payload 上传超过 20 秒，之后 `getvar result` 也超时。主机 USB 复位返回 `-7`，继续查询仍无响应。源码中的 `oem ramdisk` 会清空日志，已有内存窗口的路径可以不产生新日志；主会话据此为 `upload` 增加零长度检查，空数据返回 `FAIL no staged data`，并编译出新 `loader-phone.efi`。协议恢复及新版本往返测试尚未完成，零长度响应与持续超时之间的完整复现仍需补充。

同轮将 kernel 仓库的 `tools/stage-system.sh` 改为 USB 到 RAM：检查镜像与 loader 身份，拒绝缺少状态字段以及 `running`、`hung`、`no-such-core` 状态，检查退出码和 `FAILED`，大镜像传输等待时间为 180 秒。该脚本已通过 shell 语法检查，以及设备缺失、运行中、停滞、协议失败和成功五项模拟检查；只有成功场景执行镜像上传。新脚本的完整真机运行待验收。

最新一次 USB 检查已无法枚举手机，用户反馈屏幕仍显示 loader 文字或花屏。主会话已打包 `out/handoff-loader-v2.img`，等待进入 FASTBOOT 后装载。后续复位后先确认系统盘是否仍在 RAM，再决定是否重新上传；当前尚未取得完整系统盘挂载和 iOS 界面结果。

userdata 尾部仍属于 Android 文件系统的地址范围。原始块写入绕过文件系统分配，分区剩余容量和尾部备份均无法确认目标块当前的使用情况。此次后续流程选择 USB 传输；既有尾部数据恢复也需核对备份时刻及之后的写入，避免覆盖新数据。

完整启动逐项验收：loader 日志可读、内核有独立运行标记、出现根盘挂载日志、SpringBoard 有显示。画面验证还应包含真机观察；仅有 SpringBoard 进程日志仍需检查显示结果。

## 显示与 Android 异常分开排查

### 分辨率、stride 与实际扫描

首轮 GOP 参数取自 `Mu-Silicium/Platforms/Xiaomi/annibalePkg/annibale.dsc` 的固定值，经 `SimpleFbDxe` 提供给 loader。设备树面板 XML 与 Android DRM 模式提供了另一组参数。主会话沿 `annibale.dsc → SimpleFbDxe → SCREEN → BootArgs.video` 确认消费路径，已修改固件配置与 loader fallback，并重新构建对应产物。

主机按首轮 GOP 参数解释 framebuffer 后能读到文字，本地文件为 `docs/progress/evidence/2026-10-23-loader-framebuffer.png`。该图确认对应内存里已有可读内容；面板实际显示仍需观察。用户描述的逐行偏移支持检查 stride、宽度及像素格式。新固件启动后，loader 已返回 `screen: 1156 2510 4624`，确认配置已生效；面板的实际扫描参数与最终显示结果继续单独验收。

### SystemUI 崩溃

用户反馈通知栏、底部手势条及动画消失，重启未恢复。日志连续记录 `com.android.systemui` 的 `SIGABRT`，错误为 `Check failed: string_id.index_ - num_ids_in_dex < number_of_extra_strings`，调用栈经过 `art::VdexFile::ComputeClassStatus`，并涉及 `/data/dalvik-cache/arm64/` 下的 SystemUI 编译产物。

主会话已把对应的 `classes.dex`（61,274,600 字节）和 `classes.vdex`（849,144 字节）拉取到本机，再执行 `pm delete-dexopt com.android.systemui` 与 `pm compile -m verify -f com.android.systemui`，随后重启 SystemUI 进程。命令分别返回释放 62,123,744 字节和 `Success`，窗口列表出现 `StatusBar` 与 `NavigationBar0`。

后续复查发现 PID 继续变化，22:09 的新日志记录 `SIGSEGV`，栈经过 `art::ClassLinker::LoadClass`、`PluginInstance.loadPlugin` 和 MIUIAod 的编译文件。主会话继续备份该插件的 `.dex`（43,783,984 字节）、`.vdex`（18,834,612 字节），再执行 `pm delete-dexopt com.miui.aod`、`pm compile -m verify -f com.miui.aod` 并重启 SystemUI。两个命令分别返回释放 62,618,596 字节和成功；随后进程保持运行，用户于 22:10 左右确认恢复。

完整命令、路径与验收方法见[系统界面修复记录](2026-10-23-android-systemui-recovery.md)。本次恢复结论覆盖系统界面；`com.xiaomi.aicr:cognitionService` 的崩溃另行调查。第一轮编译成功、窗口短暂出现后仍发生故障，验收因此需要同时检查进程持续运行、新崩溃和用户实际反馈。

此次尚未确认异常数据来自何处，userdata 尾部写入与该崩溃之间的因果关系也待验证。后续修改先保存具体文件和校验值，再处理已确认异常的对象；日志按修复前后时间比较，只统计本轮新增的崩溃。

## 记录与交接规则

- 每轮保存镜像、loader、kernel、ramdisk 的哈希，payload 参数、设备模式、USB 序列号、请求实际耗时和退出结果。哈希与原始日志放在实测材料中，状态放在总账。
- 将「已观察」「源码确认」「推断」「待验证」分开描述。检查点返回覆盖该次输入与返回路径；配置修复完成构建后继续进行真机复测。多个条件同轮变化要说明对照范围。
- 检查注释、脚本和实际调用是否一致。此次 `oem logwrite` 的作用范围、日志读取顺序和 CPU 运行方式都直接影响诊断结果。
- 优先使用已有的 `--usb`、`stage`、`get_staged`、`selftest` 和检查点接口。新增诊断代码前先明确现有接口缺少哪项信息，避免增加重复状态或新的调试协议。
- 本轮归档仅覆盖已经取得的结果。后续修复应补充可复现输入与验证结果，再更新相关结论。

## 相关入口

- [loader 实现](../../hackios-xnu-kernel/xnuloader/loader.c)：`fb_command()`、`write_logs()`、`compose_logs()`、`run_kernel()`、`run_on_other_cpu()`、`wdt_arm()`。
- [内核返回实现](../../hackios-xnu-kernel/xnu/files/osfmk/arm64/loader_return.c)：`loader_checkpoint()`、`loader_jump()`、`loader_return_timer_init()`。
- [GICv3 实现](../../hackios-xnu-kernel/xnu/files/osfmk/arm64/gic_v3_irq.c)：`redistributor-stride` 读取、校验和扫描；本轮 K90 验证到检查点 20、21。
- [硬件读数](annibale-hw-map.md)、[内核构建流程](kernel-build-linux.md)、[根文件系统方案](rootfs-strategy.md)。
