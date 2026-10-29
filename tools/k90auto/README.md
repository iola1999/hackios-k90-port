# K90 无人值守桌面测试

这组脚本在没有人操作手机的情况下完成一轮桌面测试：启动带 GPU 加速的 iOS，自动解锁、下拉控制中心、翻页，定时截图并拉取日志，结束后重启回 loader，再汇总帧率、温度、CPU 档位和截图检查结果。方法的由来和历次结果见 [GPU 桌面记录](../../docs/progress/2026-10-26-gpu-desktop-acceleration.md)。

## 1. 前提

- 设备处于驻留 loader 的 idle 状态（`fastboot -s xnuloader getvar result` 输出 `result: idle`），USB 连接主机。同一设备一次只跑一个队列。
- `kbuild` 容器在运行，挂载方式见[内核构建说明](../../docs/analysis/kernel-build-linux.md)。
- 主机需要 Python 3.12 或更新版本、`adb`、`fastboot`；截图转换需要 `ffmpeg`，色块统计需要 NumPy。`run-auto.py` 按 `manifest.json` 校验载荷与系统盘的字节数和 SHA-256，并要求 loader 报告 `ramdisk-protocol: 1`；build-id 记进 `reboot.json`，不再作为前置条件。
- 输出目录默认是 `docs/progress/evidence/k90auto`（Git 忽略），可用环境变量 `K90_EVIDENCE` 改。日志、截图和产物清单只放在这里。

## 2. 自动操作的根盘

在一份可启动桌面的根目录副本里，把 `etc/rc.jobs` 换成 [rc.jobs.desktop](rc.jobs.desktop)：32 s 滑动解锁，约 120 s 起循环 8 轮，每轮下拉控制中心停 8 s、按 home 收起，再左右翻页。init 每行最多 63 个参数，所以每轮单独一行。打包命令与原根盘目录中 `manifest.json` 记录的 `mkapfs.py` 参数相同，产物放在 `hackios-xnu-kernel/out/`。

## 3. 一轮测试

```sh
python3 tools/k90auto/build-kernel.py NAME                   # 构建内核子模块 HEAD 提交，约 2 分钟
python3 tools/k90auto/make-payload.py NAME LABEL out/ROOT.apfs "gl=1 gpu_log=1 fb_threads=2 cpufreq=1"
bash tools/k90auto/run-queue.sh docs/progress/evidence/k90auto/kernel-NAME-LABEL ...
bash tools/k90auto/sheets.sh docs/progress/evidence/k90auto/kernel-NAME-LABEL/run    # 可选：PNG 与缩略图拼图
python3 tools/k90auto/summary.py --markdown docs/progress/evidence/k90auto/kernel-NAME-LABEL ...   # 两个工具都接受轮次目录或其 run/ 子目录，解析到同一处
python3 tools/k90auto/gestures.py docs/progress/evidence/k90auto/kernel-NAME-LABEL ...             # 需要 touch_lat=1；找不到 s[0-9]*.log 时报原因并以退出码 1 结束
```

- `build-kernel.py` 只构建已提交的内容，未提交的修改不会进入内核。
- `make-payload.py` 的固定参数包括触摸屏（`touchscreen=2`）、音量键与电源键（`buttons=1`）和电量计（`battery=1`）。
  - CPU 部分可用环境变量 `CPU_ARGS` 替换（默认 `cpus=2 bootcpu=7 small_cores_after=0`）。
  - GPU 档位上限用 `GPU_SPEED` 设置（即 `adreno8_speed`，默认 3）：1 固定 160 MHz；2、3 时内核按 GPU 负载和触摸在 160 MHz 与 222 MHz 或 342 MHz 之间切换（内核 `ffca661` 起，`34209c1`～`2957405` 固定请求该档）。
  - `34209c1` 之前的内核只支持 1。
  - 系统盘由环境变量 `SYSTEM` 指定（工作区相对路径，默认 `hackios-xnu-kernel/userland/system.apfs`）；超过 0xffffffff 字节的镜像还要给 `SYSTEM_WINDOW`（十六进制字节数，32 MiB 对齐），两者写进 `manifest.json`，`run-auto.py` 据此改用 `hackios-xnu-kernel/tools/stage-system.sh` 按 256 MiB 分块上传。
- `run-queue.sh` 依次运行各目录，每轮默认 420 s，100 s 起每 3 s 截图一次，每 20 s 拉一次日志（`RUN_SECONDS`、`RUN_TIMING` 可改）。USB 重启后若退回 Android B 槽，自动调用 `recover-loader.py` 切回 loader A 槽；loader 不处于 idle 时停止整个队列。每轮结束都把设备带回 idle 的 loader：`oem stop` 只是请求，loader 要等内核静默满自己的 50 秒才把结果报成 `hung-held`，所以收尾在 stop 之后按秒轮询状态（`K90_STOP_WAIT`，默认 70 秒），离开 running 后按状态名保存 loader 持有的日志再复位；内核始终不应答时不复位（loader 会拒绝），保存 `running.log` 并以非零退出交给主机复位。复位前的状态记在 `reboot.json` 的 `left` 字段，复位可能快过一次轮询，因此判定条件是 loader 重新应答 idle 且 RAM 系统盘为空，不要求观察到断开。
- `gestures.py` 按手势统计主动画的帧间隔：控制中心下拉取首帧起 1.8 s，翻页取首帧起 600 ms，输出 p50／p95／最长间隔、超过 18 ms 的比例、帧率、触摸到首帧的时间和窗口服务器每帧绘制时间。需要在 EXTRA BOOT-ARGS 中加 `touch_lat=1 glslow=3000`。
- `summary.py` 每轮输出一行：内核提交、关键启动参数、实际运行秒数、panic 次数、动画窗口帧率、显示驱动每帧耗时、GL 帧耗时 p50／p90、帧间隔分布（低于 18 ms、18～35 ms、更长）、大核最高温度、最低档时间占比、截图数与异常截图数、崩溃记录数（数内核报的进程退出行；2026-10-28 修正前该列数的是日志里 `ReportCrash` 这个名字的出现次数，修正前各轮的值不是崩溃计数）。

## 4. 判读

- 汇总的帧间隔只统计帧数不少于 20 且报告帧率不低于 10 帧/秒的窗口，静止屏幕几十秒里的零星重绘不计入；低于 18 ms 的比例用于检查帧间隔分布。各手势的实际帧率由 `gestures.py` 按主动画时间轴计算。
- `summary.py` 只把 `s[0-9]*.log` 当日志快照（`system-upload.log` 是 fastboot 的上传记录），并把同一轮的快照按重叠部分对接：loader 的日志区是 263,349 字节的头加 1,048,576 字节的环（单份快照上限 1,311,925 字节，roundb、round C、round D 三轮实测一致，结构与 30 字节差值备注见[运行协议 §6](../../docs/plan/k90auto-run-protocol.md)），一轮 300 秒能写到 1.18 MB，环满之后开头的帧窗口被覆盖。同一窗口只算一次。
- 异常截图指 GMEM 分 bin 边界下方出现状态栏蓝色块的截图，对应 2026-10-25 的 framebuffer fetch 缓存问题。其他显示异常（例如控制中心背景纯黑）需要看拼图，或由人在设备旁确认。
- 温度和 CPU 档位来自 `cpufreq=1` 或 `2` 时内核每 30 s 写的日志。窗口行尾部的 `N by temperature, M without a reading` 区分限频由读数触发还是没有读数触发，`sensor sets changed` 是有读数传感器集合的变化次数，接近 `ticks` 说明 VALID 位每拍都在掉；紧跟的 `hot ticks` 一行给出热段内的档位占比，判断限频是否守住看这一行，窗口峰值 `hottest` 说明不了 30 s 的占比。
- 震动、亮度、声音等需要人感知的项目不在这组脚本的判定范围内。

离线检查使用 `python3 tools/k90auto/test-tools.py`，覆盖帧间隔分组、重叠快照的合并、队列失败后停止、收尾遇到的 loader 状态（`hung-held`、`returned`、中途离开 `running`、已经 `idle`、stop 之后 50 秒才变 `hung-held`、内核始终不应答）、复位快过一次轮询、大镜像缺窗口的拒绝和分块上传的窗口传递；全部设备命令均由临时替身执行，替身也打印 fastboot 自己的 `Finished.` 行。

## 5. 软件进入 LK FASTBOOT

`reboot-lk.py` 已在 K90 验证。工具运行已校验的最小准备载荷，在本机 PMIC 中设置并读回启动目标；确认本轮 prepared 日志后调用 loader 的普通 reboot，识别指定设备的 LK product 和槽位后停止。入口、来源与三轮真机验证见[后续记录](../../docs/progress/2026-10-27-ios26-k90.md#3-软件进入-fastboot-与剩余验收)。当前 loader 自身的 `reboot-bootloader` 仍只有普通复位行为。

调用前设备需处于 idle 或无 held 的 returned 状态，resident 系统盘为空。同一设备的命令必须串行；GPU held／fault、仍在运行或 RAM 系统盘非空，先保存日志并按[真机手册](../../docs/plan/device-test-playbook.md#6-故障定位与恢复)完成软件冷复位，再检查状态。工具拒绝这些状态，保留现有内容。

```sh
python3 tools/k90auto/reboot-lk.py docs/progress/evidence/k90auto/reboot-lk-RUN \
  --payload hackios-xnu-kernel/out/ios26-resume/reboot-lk-prepare/annibale-reboot-lk-prepare.bin \
  --sha256 6b81e800ae789cf30adbaaa9c98768012e264c66a4e56110c6449cecf93fb7d7 \
  --serial "${ANDROID_SERIAL}"
```

`ANDROID_SERIAL` 使用手机在 LK／Android 中的序列号；缺少 `--serial` 时工具读取该变量。输出目录必须尚未存在，原始记录保持 Git 忽略。载荷变更后重新核对完整哈希，不能继续采用上述旧值。每条命令的 stdout、stderr、退出码、时限和耗时写入 `commands.jsonl`，准备日志及最终状态分别写入 `prepared.log`、`result.json`。哈希、状态或 prepared 校验失败后，工具停止且不发送 reboot。复位应答丢失后仍有界检查目标枚举，成功条件是实际读到 LK。

增加 `--return-loader` 可完成「准备启动目标 → LK → 重新选择 A 槽 → 驻留 loader」往返。工具在 LK 再次确认 `product=annibale` 与当前槽位，要求 B 槽 `slot-successful:b=yes`、`slot-unbootable:b=no`，然后执行 `set_active a`。只有读回 A 槽已激活、`slot-retry-count:a=7`、`slot-unbootable:a=no` 才发送后续 reboot。该模式用于补充多轮冷复位消耗的 A 槽启动重试次数；只修改活动槽位及相关启动元数据，不刷写镜像。

回程仍按实际枚举验证复位结果，USB 应答丢失后继续有界等待。成功条件为 LK 已消失，重新读到同一 build-id 的 xnuloader、`result=idle`、空 resident RAM、协议 1 和载荷下载窗口 `0x03700000`。B 槽条件不满足则停在 LK；A 槽读回失败则保存记录且不发送回程 reboot；回程身份或状态不符则报错并保留现场，不继续上传或复位。2026-10-27 新增 CLI 已完成一次真机往返，耗时 25.96 秒，A 槽重试次数在 LK 从 5 恢复为 7，随后确认 fresh idle／空 RAM。该轮两端 build-id 均为 `unknown`，此项只确认字段一致；loader 的源码与产物身份继续依据冻结清单核对。

离线检查为 `python3 tools/k90auto/test-reboot-lk.py`，使用 fastboot 替身覆盖输入保护、默认停在 LK、往返、槽位失败、复位应答丢失及返回状态验证，共 19 项测试。它不会操作设备。工具默认停在 LK；需要往返时，在上述命令末尾增加 `--return-loader`。

## 6. 界面进程状态检查

`ui-health.py` 检查同一次启动的多份日志，默认跟踪 SpringBoard 和 backboardd。日志包含 NUL 也继续解析；进程中止、异常、断言、内核 panic 或同一进程名出现多个 PID 均判为失败。进程记录缺失或断言没有进程前缀则要求人工审阅。多次启动的日志必须分开检查，否则正常重启也会触发 PID 变化判定。

```sh
python3 tools/k90auto/ui-health.py docs/progress/evidence/k90auto/RUN/device-*.log \
  --output docs/progress/evidence/k90auto/RUN/ui-health.json
```

本轮实际打开前台应用后，可用 `--process Preferences` 等参数增加预期进程。退出码 0 表示所选日志中进程状态已观察到且未检出上述故障；2 表示失败；3 表示需要审阅。显示内容、手势结果、帧率与 GPU 绘制继续单独验收。离线检查 `python3 tools/k90auto/test-ui-health.py` 覆盖 backboardd 中止、跨快照重启、重复采集、日志缺失、无归属断言、前台应用异常、无关服务中止及内核 panic。

## 7. payload 打包

`package.py` 一条命令完成 iOS 26 payload 的组装：用 xcrun clang 编译 shim 与驱动两个 arm64e 库、把 AIR 库与两个库装进根盘副本、写入 backboardd 的 `REDWOOD_SB_METAL=1` 与 `etc/rc.jobs`、补上 `jobs/` 里的三个 launchd job（chronod 延后到约 120 秒启动、PosterBoard、replicatord）、`mkapfs.py` 打包，最后按根盘内容逐文件回读校验并把哈希写进 `manifest.json`。

```sh
python3 tools/k90auto/package.py          # 从工作区根目录运行
```

产物仍写在 `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/`（`root.apfs`、两个库、`manifest.json`、构建日志），该目录 Git 忽略；`jobs/` 与 `rc.jobs.desktop` 跟着脚本放在 `tools/k90auto/` 下并纳入版本管理。

- AIR 库不在这里编译，脚本只取该目录里 ninja 构建的 `libredwoodair.dylib` 并用 `codesign -dv` 断言它带 adhoc 签名，漏签名会让 dyld 拒绝加载、整轮退回 CPU 合成。
- 脚本对基线根盘、三个冻结库、变更文件集合、登记断言都做硬校验，任何一项不符直接退出。
- AIR 库只被复制、不在这里编译，所以打包前先确认目录里那份是哪一版：带逐帧计时的插桩库会在日志里多打 `perf frames` 行，要干净库就按 `out/ios26-resume/mesa-arm64e/manifest.json` 里记录的命令从无插桩源树重编，不要直接沿用上一位留下的文件。
- `JOBS_SOURCE` 可换掉根盘里的 `etc/rc.jobs`（例如诊断轮用 `jobs/rc.jobs.ccdrag`）。
- `JOB_ENV="任务.plist:变量=值 ..."` 给指定任务的 plist 和 launchd 缓存各加一个环境变量，一项一个变量。现在用到下面三个变量。
  - `OS_ACTIVITY_DT_MODE=YES`：任务的 os_log 随 stderr 进控制台日志；backboardd、iconservicesagent、chronod 的任务本来就有这一项。SpringBoard 的 os_log 量大，`render4` 里两次拉取之间日志环转过整圈 12 次，开机解锁那一行丢失，不要给它打开。
  - `REDWOOD_SYNC_DRAWS=1`：驱动在每个绘制之后提交并等待完成，没有完成的绘制打印 `sync: commit N work M did not finish`，带管线名、颜色附件数、纹理数和缓冲数，并把这个管线的两个着色器模块以 `AIRFAIL begin hung-vertex`／`hung-fragment` 打出来，用 `hackios-xnu-kernel/tools/mesa/air/airfail-extract.py` 取回。每个绘制都要等 GPU，只给怀疑的进程打开。
  - `FD_MESA_DEBUG=...`：freedreno 自带的调试开关，例如 `sysmem` 让所有批次不走 GMEM。
  - `IR3_SHADER_DEBUG=vs`／`fs`：ir3 把这一类着色器的 NIR 和 A830 机器码打进 stderr（`Native code for unnamed VERT|FRAG shader 名字`），量大，只给一个进程打开。

## 8. 渲染问题的无人值守检查

`cycle.py` 从工作树跑完一轮：打包、做 payload、上传并启动，等 SpringBoard 报出开机解锁后执行一段固定的操作与截图，然后提前结束这一轮，最后写出渲染报告。

```sh
ANDROID_SERIAL=<序列号> python3 tools/k90auto/cycle.py LABEL --baseline docs/progress/evidence/k90auto/kernel-NAME-上一轮
python3 tools/k90auto/render-health.py docs/progress/evidence/k90auto/kernel-NAME-LABEL [--baseline 另一轮]
python3 tools/k90auto/tour.py docs/progress/evidence/k90auto/kernel-NAME-LABEL "home@3*2" "settings=/redwood/bin/rwtouch tap 0.616 0.70@4*2"
```

- `cycle.py` 起轮前要求 loader 已枚举、`result` 为 idle、RAM 盘为空，任一项不满足就停止；每两轮先经 LK 把 A 槽重试次数重置为 7（`reboot-lk.py`、`set_active a`），LK 由 `ANDROID_SERIAL` 指定。打包开关（如 `ICON_METAL=1`）按 `package.py` 的环境变量透传。
- `render-health.py` 先按重叠部分合并 `s*.log`，再把驱动、AIR 库、QuartzCore 的 Metal 日志、MiniIOSurface 与 GPU 驱动里的失败行按类别分组计数，每类写明它在屏幕上的后果；没有归类但带失败字样的图形日志列在 unclassified 下。`--baseline` 在每行后给出另一轮的计数，并标出只在一侧出现的行。驱动的部分拒绝只在首次或 2 的幂次打印，计数 1 或 2 的幂可能代表更多次。
- `tour.py` 的每一步是 `标签=命令@等待秒数*截图张数`，命令经 `rsh.py` 发给设备上的 rwsh；同一步拍两张以上时比较前后两张，状态栏以下有变化的比例和范围写进 `run/tour.json`，用于发现闪烁。全部截图缩成一张 `run/tour-sheet.png`，编号与 `tour.json` 的顺序一致。
- GPU 挂起后，12377-cmd4 起的内核打印 RBBM 与 CP 状态，以及每个流水线各级 IB 的基址、剩余与初始长度和 CP 位置前后的命令字。`python3 tools/k90auto/cp-words.py ROUND_DIR` 把这些命令字按 type 7／type 4 包头解成包名并标出 CP 位置；CP 会预取，停住的包可能在标记之前一两个。
- SpringBoard 的图层树可以用 rwsh 的 `notify com.redwood.layers.<过滤词>` 打到日志里（`all`、`Icon`、`Wallpaper`、`Poster`、`StatusBar`、`Battery`、`Widget`）。过滤词在任意层级匹配图层类或所属视图类，匹配处向下再列 3 层；每行是层级、图层类、所属视图类、尺寸、在父图层里的位置、隐藏与透明度、内容类型和尺寸，用来区分「图层没有内容」和「有内容但没有画出来」。
