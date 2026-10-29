# annibale 真机调试手册

本页已补充 loader v7、槽位恢复及 2026-10-26 的 GPU 交互配置。Android 界面异常及早期调试问题见[系统界面修复记录](../analysis/2026-10-23-android-systemui-recovery.md)，早期触摸和 BQ 电量见[桌面交互案例](../analysis/2026-10-24-interactive-runtime.md)，最新性能见[GPU 桌面记录](../progress/2026-10-26-gpu-desktop-acceleration.md)，当前进度见[总账](2026-10-23-tracking.md)。操作前仍需确认设备与产物现状。

## 1. 当前启动方式

- `_a` 槽存放驻留 loader 的启动镜像；`_b` 槽保留 Android。SystemUI 和息屏显示插件的编译缓存已重建，用户确认系统界面恢复。
- loader USB 命令通道已实测可用。主机通过 USB 把 `system.apfs` 传入 RAM，再传入内核和小根盘。`bootcpu=1 cpus=1` 已进入桌面，后续 `bootcpu=1 cpus=2` 已确认两颗 CPU 在线。
- 单次上传系统镜像为 2,492,227,584 字节，实测约 62 秒。loader 持续运行期间可以复用该镜像；手机重启后需要重新上传。
- 真机已挂载 System 卷并显示 SpringBoard，GPU 桌面已验证触摸、翻页和控制中心。双核动态调频配置的主动画接近 60 帧/秒；首次下拉慢帧及偶发断触继续保留为待确认。启动、显示、输入和性能分别验收；最新设备状态仍以本轮查询与用户反馈为准。

## 2. 操作前检查

1. 读取本页及总账，确认本轮内核、loader、固件和两份 APFS 镜像的文件大小与 SHA-256；修改源码后重新构建对应产物。
2. 先看 `adb devices -l` 和 `fastboot devices`，将目标 Android/LK 序列号设置为环境变量 `ANDROID_SERIAL`；驻留 loader 使用 `xnuloader`。每次切换后重新确认身份，再指定相应序列号。
3. 确认当前槽位、A 槽重试状态和 `_b` 槽可用。写启动镜像仅使用 `boot_a`；调试系统盘使用 USB RAM 上传。连续实验启动未标记成功会耗尽 A 槽重试次数，LK 随后回退到 B 槽 Android；2026-10-25 已实测 `slot-retry-count:a: 0` 与 `slot-unbootable:a: yes`。Android 可连接后，通过 ADB 返回 LK、检查槽位，再执行 `set_active a` 恢复已有 loader，无需重写镜像。
4. kernel 子模块的 `tools/stage-system.sh` 使用无参数调用，经 USB 把系统盘传入 RAM；调用前检查 loader 身份、内核状态和镜像长度。
5. 交互测试使用已清理启动任务的小根盘，核对镜像内 `/etc/rc.jobs`、按需服务及所需动态库。按需启用逐帧或触摸延迟日志，并记录采集窗口；正常交互配置保持低日志量。

## 3. 安装驻留 loader

Android 可连接时，通过 `adb -s "${ANDROID_SERIAL}" reboot bootloader` 进入 LK。驻留 loader 可连接且符合第 10 节前置条件时，使用软件 LK 入口。内核无响应先保存可读日志并检查软件停止与返回能力；软件恢复不可用，再请用户长按电源键和音量下进入 FASTBOOT。沿用用户已尝试过的动作和结果，减少重复操作。

2026-10-29 已安装 `hackios-xnu-kernel/out/handoff-loader-v9.img`，build-id 为 `893f478634533bd9b6fb086def780458b07fd2a3`，镜像 SHA-256 为 `e860325ace27bf78c449df8341f9694c94b595c96e41d4ac2196b8b3653c9ec5`。v9 在 USB 等待与传输期间往屏幕下方画阶段、进度条与日志尾部，内核接管屏幕后不再画；镜像由 `hackios-xnu-kernel/tools/reseal-loader-img.py` 以 v8 为参考重封，shim、FD 与 DTB 与 v8 相同。

上一版 v8（`7ffbdd44…`，build-id `unknown`）与 v7、v5 的镜像都保留，回退时按同样的命令刷回。v7 的 USB 恢复验证范围见[恢复审查记录](../progress/2026-10-25-gpu-resume-review.md)。重装前仍核对实际文件与哈希。`out/` 中的文件是本地构建产物。

```sh
fastboot -s "${ANDROID_SERIAL}" getvar product
fastboot -s "${ANDROID_SERIAL}" getvar current-slot
fastboot -s "${ANDROID_SERIAL}" flash boot_a hackios-xnu-kernel/out/handoff-loader-v9.img
fastboot -s "${ANDROID_SERIAL}" set_active a
fastboot -s "${ANDROID_SERIAL}" reboot
fastboot -s xnuloader getvar product
fastboot -s xnuloader getvar build-id
fastboot -s xnuloader getvar screen
```

成功条件为 `product: xnuloader`。当前配置的屏幕几何应为 `1156 2510 4624`；该值来自固件配置，物理面板的显示仍要目视验证。`reboot` 的主机返回结果只能确认命令已发送，后续状态需要另行读取。

## 4. 上传系统盘并运行内核

以下命令从 `hackios-xnu-kernel/` 目录执行，保留 2026-10-24 已取得触点的双核软件绘制配置。`out/handoff-mach-affinity` 与 `out/handoff-ui-clean.apfs` 分别为该轮内核与小根盘，使用前按产物清单核对版本和哈希。系统盘只需在本次 loader 生命周期首次运行或更换镜像时上传。当前 GPU 配置与匹配产物见[README](../../README.md#5-如何启动-ios)和[无人值守工具](../../tools/k90auto/README.md)，使用新配置前检查根盘含有 Mesa CCHE 修复。

```sh
bash tools/stage-system.sh
python3 xnuloader/mkpayload.py -o out/handoff-full.bin kernel=out/handoff-mach-affinity ramdisk=out/handoff-ui-clean.apfs --cmdline "debug=0x10e cpus=2 bootcpu=7 small_cores_after=0 epoch=$(date +%s) touchscreen=2 buttons=1 gl=1 battery=1"
fastboot -s xnuloader stage out/handoff-full.bin
fastboot -s xnuloader oem run
fastboot -s xnuloader getvar result
```

`bootcpu=7` 使用 MPIDR `0x10100`，第二颗为 `0x10000`，loader 保留当前 CPU 处理 USB。该组合已确认两颗 CPU 在线。此命令要求 loader v4 或 v5 与 `handoff-mach-affinity` 配套，较早版本缺少完整 Aff2 处理。

上述交互配置持续运行，使用 `fastboot -s xnuloader oem stop` 结束，再确认 `result` 已返回。限时测试可单独添加 `loader_return_after=N`，记录期限；该机制依赖对应初始化与回调，早期挂起仍可能无法返回。屏幕停在最后一帧先查询 `result`，避免重复调查已经退出的系统。

## 5. 读取日志和截图

内核运行期间按下面的顺序准备并读取数据，每组串行执行：

```sh
fastboot -s xnuloader oem log
fastboot -s xnuloader get_staged /tmp/hackios-kernel.log
fastboot -s xnuloader getvar screen
fastboot -s xnuloader oem screenshot
fastboot -s xnuloader get_staged /tmp/hackios-screen.raw
```

`oem log` 和 `oem screenshot` 只准备数据，`get_staged` 才把数据传回主机。截图为原始帧缓冲，按 `getvar screen` 的宽、高和每行字节数解码。本机 fastboot CLI 使用 `get_staged`；线上的 USB 协议命令名为 `upload`。

内核返回后，loader 已准备合并日志。先查询状态，确认返回后直接读取；本步骤之前不要再调用 `oem log` 或 `oem screenshot`，两者会替换暂存内容。异常返回日志可能因缓冲上限截断，持续采集时同时保留返回前的实时日志和状态记录：

```sh
fastboot -s xnuloader getvar result
fastboot -s xnuloader get_staged /tmp/hackios-return.log
```

旧 loader 的空数据上传会发送 `DATA00000000`，主机拒收后未读最终状态，loader 会一直等待传输完成。本轮增加了空数据检查，直接返回 `FAIL no staged data`。旧版遇到该问题需要恢复 USB 或重新启动 loader；不应把一次超时记录成内核已重启。

`oem stop` 后 `result` 迟迟不转为 returned（内核停在 park 一类状态）时，按两轮补采停止时刻之后的打印。park 打印在停止动作之后才产生，第一轮可能尚未包含该行。先取第一轮并完整保存：

```sh
fastboot -s xnuloader oem log
fastboot -s xnuloader get_staged /tmp/hackios-stop1.log
```

约 2 到 3 秒后取第二轮并完整保存，到此为止；间隔是固定的一个等待，不做循环轮询：

```sh
fastboot -s xnuloader oem log
fastboot -s xnuloader get_staged /tmp/hackios-stop2.log
```

分类结论只用三档：

- host-stop banner（内核停止轮询打印「the host asked for the end of the run: back to the loader」，`loader_return.c` L513-L540）未见，此时抓取不完整与内核未执行停止回调两种情况无法区分。
- banner 已见、无冷复位保留打印（park 未确证）。
- 出现「requires host cold reset」打印（park 确证）。

读取路径：

- 两轮补采的适用状态是 loader 判定 hung 之前的 running：此时 `oem log` 读内核实时环形缓冲。
- 判定 hung 后实时环形缓冲指针已清空（`loader.c` L2517），HUNG 分支的 `write_logs` 已把挂死判定时刻的快照组装进暂存（L3578），直接 `get_staged` 可取到该快照。
- 再次执行 `oem log` 走 `compose_logs(NULL, 0)`（L327-L347，分支 L4035-L4041），清空暂存、只复制 loader 日志，快照被覆盖，run002 取回的 32,767 字节 loader 串行日志与该覆盖行为一致。
- loader `hung` 状态本身只表示判定内核无响应，不足以单独支持 park 结论。分类以实际取回内容为准，截断记录为截断。
- 行号固定于 `hackios-xnu-kernel` 提交 `ec53bac`。

## 6. 故障定位与恢复

- `result: running`：内核仍在运行，读取 USB 日志判断进度。
- `result: returned ...` 或 `checkpoint ...`：先确认没有 held／fault 状态且资源已释放，再取日志、上传下一份 kernel payload；同一 loader 生命周期中的 RAM 系统盘可以继续使用。
- `result: hung ...`：先保存可读日志，核对 build-id 和资源保留状态，再重启。旧提交 `ec53bac` 曾允许 hung 后继续上传或运行，该行为存在资源重用风险；v7 的命令限制按实际 held／fault 状态执行。
- `result: returned-held ...` 或 `hung-held ...`：设备可能仍访问原内核的内存和映射。v7 拒绝会改写资源的上传、运行及探测命令，查询、日志和复位入口保留；无 live 内核可通知时，`oem stop` 返回 `FAIL`。先保存已有日志，再软件复位并确认断开、重新枚举与 `idle`，随后重新上传 RAM 镜像。
- v7 已在 GPU 停止后第 65 秒读到 `hung-held` 并经 USB 重启恢复 `idle`；`returned-held` 和全部固件故障分支尚未逐项真机验收。主机生命周期测试及真机覆盖范围分别见[恢复审查记录](../progress/2026-10-25-gpu-resume-review.md#4-loader-v7-真机验收)与[USB 案例](../analysis/2026-10-25-loader-usb-after-panic.md)。软件等待预算仍依赖固件同步调用能返回，无法确认请求终止就保留缓冲至复位。
- 重启命令后重新枚举且 `result: idle`：loader 已重新启动，先前 RAM 镜像需要重新上传。
- `result: reset-failed`：PSCI 复位调用返回，直接读取日志中的返回值；loader 保留 USB 命令循环。
- 当前源码从 `adreno8=14` 开始执行 HWSCHED START，要求 `adreno8_keep=1 adreno8_return=0`；旧第 14 阶段只有 CORE_FW_START，产物与阶段对应关系见[实测交接](../progress/2026-10-24-gpu-execution.md)。采样后通过 loader USB reboot 执行 PSCI_SYSTEM_RESET（本手册称冷重启），结果以重新枚举与 `result` 为准；后续 3a／3b 多轮已再次完成 MP_ASSIGN、配置与 START，但尚未直接读取复位后的完整安全内存归属；随后按本轮清单重新上传系统盘。普通退出与 panic 返回都检查 `adreno8_reset_required` 和 `adreno8_memory_retained()`；ACK 成功、失败或分配中途失败均可能要求保留资源，不能直接上传下一份内核重用内存。`loader_return_after` 无法取消该保护。
- `result: no-such-core ...`：先保存 loader 原始日志，核对目标 MPIDR 和 PSCI 返回值。该状态下的旧画面无法用于评估本轮性能。
- USB 有枚举记录但命令无响应：可能是内核占用 loader 的 CPU、USB 传输等待或固件异常。记录命令、耗时、USB 枚举与画面，分别排查。
- 返回 Android：先进入 LK，再执行 `fastboot -s "${ANDROID_SERIAL}" set_active b` 和 `fastboot -s "${ANDROID_SERIAL}" reboot`。loader 的 `reboot` 在 annibale 上只执行 PSCI_SYSTEM_RESET（`usb_command_loop` 的 annibale `reboot` 分支，`loader.c` L4498-L4509，行号固定于提交 `c0716bf`；不经 UEFI reset 回调），目标仍由当前槽位决定，成功与否以重新枚举与 `result` 判断。三种引导目标之间的完整切换步骤、成功判据与实测耗时见[引导目标切换 SOP](device-boot-target-sop.md)：这一条只是其中一跳，进 loader 走 `set_active a` 加 `reboot`，从 LK `fastboot boot` 载荷不会把 loader 带起来。
- `oem logwrite` 会覆盖 `boot_a` 开头，不能用于保存启动后的日志。当前真机调试使用 USB 日志。
- 桌面 wch 串口属于其他设备。手机 UART 为 GENI `0xa9c000`、`115200n8`，当前没有连接调试线，默认保持关闭。
- Android 整组 `pinmux-pins`／`pinconf-pins` 调试读取后曾发生重启。优先使用已保存的设备树和驱动定义，再决定定点读取；文件读取的硬件副作用需按实现检查。
- 2026-10-29 事故：一天内连续起轮十几轮后，loader 从 USB 消失。起轮时 `ATTEMPT` 的 `left`／`elapsed` 全为空，`adb devices` 短暂列出一台但序列号为空，随后 `adb reboot bootloader` 返回 `unknown command`，两分钟内 `adb devices`、`fastboot devices`、`ioreg -p IOUSB`、`system_profiler SPUSBDataType` 全部查不到设备，只能长按电源键冷启。处置与约束见 [AGENTS.md](../../AGENTS.md) 第 5 节，故障形态见 [USB 恢复经验](../analysis/2026-10-25-usb-recovery-lessons.md) 第 4 节。

## 7. 四阶段验收

| 阶段 | 本轮需要取得的结果 |
|---|---|
| loader 已运行 | `getvar product` 返回 `xnuloader`，可读取 loader 日志 |
| 内核已运行 | 内核检查点返回或 USB 日志中出现内核初始化输出 |
| 系统盘已挂载 | 日志出现 `BSD root: md0` 和 APFS System 卷挂载结果 |
| SpringBoard 已显示 | SpringBoard 进程日志、帧缓冲截图和手机实际画面相互确认 |

图形交互验收同时检查 SpringBoard、backboardd、前台应用的 `userabort`／`usertrap` 与断言，并记录 SpringBoard／backboardd PID。原始日志可能含 NUL，检索使用文本模式。采集和软件恢复成功后，若界面进程中止或重启，功能结果仍记为失败；Home 返回案例见[实测记录](../progress/2026-10-27-ios26-k90.md#25-应用内-home-返回触发软件合成中止)。

## 8. 外设开关（修改 kernel payload 的 cmdline）

第 4 节的已测交互配置启用触摸与电量。继续调查其他外设前，按用户确定的优先级选择一项，再向 payload 的 `--cmdline` 追加对应参数：

- `touchscreen=2`：annibale Goodix 触摸。先查芯片身份、报告模式和有效触点，再验证用户滑动与点击的坐标及延迟。当前已取得 9916K 坐标，GPU 桌面滑动与翻页已获用户确认；滑动偶尔被识别为点击的反馈尚未复现。`ready` 日志及自动解锁脚本的手势都不足以完成手指操作验收。
- `hv_haptic=3`：PMIC 震动自检——起内核后 30 ms 直驱一次马达，**手感就是验收** （屏幕/串口都看不到它）。注意 059a59e 修正了 ppid（0x0f0→0x7f0，TI 块在 slave 7，DT 路径裁决），**旧镜像这步必然无感，必须用新 kernel**。没感觉再加 `haptic_amp=128` 试更大；仍无 → USB 日志读 `haptic:` 前缀（arbiter 表、revision、fault 都在里面）。
- `hv_haptic=4`：iOS 反馈直通马达（/dev/redwood-haptic，DIRECT_PLAY 跟随响度）。桌面点击该有震感。上限 1 s/次，fault 自动弃疗。
- `buttons=1`：音量/电源键（已入库 annibale_buttons.c，纯读零写入 PMIC）。音量上=PMI GPIO slave1 function 0x18d 低有效带上拉（DT #L9164/#L21098，**不是**任务书早先写的 TLMM GPIO6——若真机无事件先查这条）；电源/音量下=PMK8550 PON（KPDPWR/RESIN）。按键事件进 USB 日志 `buttons:` 行 + `/dev/redwood-input`。细分步 `buttons_hv_steps=1..5`。
- `torch_secs=3`：手电盲测——亮 3 秒自己灭，肉眼即验收（annibale_torch.c；先验 TYPE/SUBTYPE+无 fault 才写，每写必回读；`torch_ma=1..500` 调电流默认 125；实时 fault 直接拒亮不猜）。
- `battery=1`：当前 annibale 实现读取 I²C 地址 `0x55` 的 BQ27Z561，通过 GPIO52/53 传输并在采样后恢复引脚。检查有效电量、电压、温度及 `RedwoodBattery` 发布结果；电流符号推导的状态仍需与独立的充电器状态核对。实现及样本边界见[桌面交互案例](../analysis/2026-10-24-interactive-runtime.md)。
- 手电需要内核 `4d6eee3` 及以后，震动需要 `5847dd3` 及以后：更早的内核用 Extended Register Write 写 PMIC，寄存器值不变，驱动在第一次读回不一致时停止，见[手电与震动实测](../progress/2026-10-26-torch-and-haptics.md)。
- `torch=3`：提供 `/dev/redwood-torch`，iOS 经 AVFlashlight 和 mediaserverd 控制；单次点亮时长默认 30 s，`torch_max_s` 最多 120 s，保留故障和电池温度检查。控制中心按钮已通过自动操作，实际灯光待人工确认。
- iOS 26／V57 原生显示对照使用 `fbwidth=1206 fbheight=2622 fbpitch=460`，需要包含 `fbpitch` 支持的内核；2026-10-27 的 fd917 内核已在 K90 验证 screen class 36 和 62／0／34／0 点安全区。参数缺省继续原 1125×2436 配置，`fbpitch=0` 保留按宽度缩放的密度。完整配置与性能边界见[实测记录](../progress/2026-10-27-ios26-k90.md#22-k90-原生显示配置与软件动画实测)。
- `cpufreq=1`：annibale 按负载调频、空闲降档、触摸短时提频；CPU 达到 70 °C 后降到最低档，低于 60 °C 后恢复。`cpufreq=2` 只报告，`cpufreq=3` 为固定频率对照；日常交互使用模式 1。
- GPU 无人值守载荷曾缺少 `buttons=1 battery=1`。生成工具已补回两项；出现按键或电量缺失，先查本轮载荷的实际参数，再查初始化日志，新载荷的人工操作仍需验收。
- 按键验收依次查看 arbiter、通道表、TYPE/SUBTYPE、引脚状态和 `buttons:` 事件，再核对 iOS 行为。手电无光先查 TYPE/SUBTYPE、fault 与写入回读；现有实现遇到 fault 拒绝点亮，清除 fault 的语义仍待核实，`torch_secs` 在驱动内最多为 5 秒。
- `pcie=1..5`：Wi-Fi PCIe 分阶段诊断（`mhi_pcie.c`）。依次检查电源／时钟／引脚、根复合体、端点与 BAR、MHI、BHI／BHIe 与端点 RID `0x100` 的 SID 路由。`pcie_power=1` 会按既有步骤上电并配置 BAR，保持到复位；新增第 5 阶段只读取已映射范围中的寄存器。第 5 阶段已实测：设备处于 PBL、BHI 错误为零、PARF bypass=1；下一步确认实际 SID 与 apps SMMU 映射后再决定 DMA 实现，见 [PCIe 记录](../progress/2026-10-26-wifi-pcie-survey.md#5-bhi-执行环境与-sid-读取2026-10-27)。
- 每轮只增加一个待测驱动，先检查 USB 日志和对应的实际行为。日志按第 5 节区分运行期间与内核返回后的读取顺序。
- 触摸/震动都惰性于默认 cmdline（不带旗标=零动作），QEMU 同理不需要它们。


## 9. 大于单次 fastboot 长度的 RAM 系统盘

新分块协议已在 K90 完成 4,925,816,832 字节系统盘实传、12 GiB 窗口状态回读和 iOS 26 双核启动，耗时 124.486 秒，见[首轮记录](../progress/2026-10-26-ios26-k90.md)。现有 v7 不提供该协议。调用前仍按第 2、6 节确认 loader 产物、内核状态和资源归属；`getvar ramdisk-protocol` 必须返回 `1`。

`tools/stage-system.sh` 对超过 `0xffffffff` 字节的镜像使用分块协议，要求 `STAGE_SYSTEM_WINDOW` 提供十六进制内存窗口字节数。窗口必须按 32 MiB 对齐，并容纳系统盘、loader 保留区与内核运行空间；已分配窗口必须与请求完全一致，调整窗口需重启 loader。当前 4,925,816,832 字节的 iOS 26 系统盘需要该路径。较小镜像继续使用原单次上传流程。

| 命令 | 行为 |
|---|---|
| `getvar ramdisk-protocol` | 返回协议版本 `1` |
| `oem ramdisk begin TOTAL_HEX WINDOW_HEX` | 校验长度和窗口，开始新的顺序上传，清除已发布镜像长度 |
| `download:SIZE_HEX` | 标准 fastboot 数据传输，追加一个完整块；主机脚本使用 256 MiB 块 |
| `getvar ramdisk-state` | 返回状态、已完成块的总字节数、镜像总长度、窗口长度；三个数值均为十六进制 |
| `oem ramdisk none` | 取消上传，清除镜像长度；继续保留内存窗口及现有 USB 缓冲归属 |

状态查询只用 `getvar ramdisk-state`。loader 按 `oem ramdisk` 前缀决定下载归属，`begin` 和 `none` 之外的任何 `oem ramdisk` 参数都会清除已发布镜像长度并把下一次 `download:` 指向 RAM 区，`max-download-size` 随即变为 `0xffffffff`。发现该值后用 `oem ramdisk none` 清除归属，确认 `max-download-size` 回到 `0x03700000` 再继续；`reboot-lk.py` 的前置检查会以「Loader download target is not its payload buffer」拒绝这种状态，且不会发出 reboot。

只有全部数据接收完成才发布 `resident_rd_size`。分块短传、非法长度、断线或 USB 通道失效后进入失败状态，拒绝续传和运行；需要取消或重新开始。主机未收到成功应答就停止，不重发含义不确定的块，也不执行内核。最后一块可能已经完整接收但应答未到主机，此时仍需重新查询状态并记录该轮结果。已有单次上传的短传后运行行为保持原样，分块完整性检查的结论只覆盖新协议。

主机验证包括 105 项实际 C 控制流检查、4 项协议变异检查、9 项上传脚本场景，以及既有 loader 生命周期、build-id 与 payload 检查。原始输出、独立构建源码及 EFI 哈希位于忽略目录 `hackios-xnu-kernel/out/ios26-resume/loader-ramdisk-protocol/`。首轮真机已完成整盘实传；分块短传、断线及重传的固件行为仍待单独验证。

## 10. 从驻留 loader 软件进入 LK

2026-10-27 已连续验证两轮「准备启动目标 → loader reboot → LK → A 槽 loader」往返，正式主机工具又完成一轮进入 LK 及后续回程，均无需人工按键。入口为 [reboot-lk.py](../../tools/k90auto/reboot-lk.py)，参数和固定测试载荷哈希见[工具说明](../../tools/k90auto/README.md#5-软件进入-lk-fastboot)。`--return-loader` 已完成 25.964 秒真机往返：确认 B 槽 successful=yes、unbootable=no，再恢复 A 槽重试次数至 7，返回后核对 loader idle 和空 RAM；连续启动实验可在上传系统盘前运行。工具默认停在 LK，方便更新 boot_a；当前 loader 的 `reboot-bootloader` 尚未增加目标设置，仍执行普通复位。

该入口先使用最小内核校验本机 PMIC 的 PPID、写入权限及 SDAM 容量，准备并读回 bootloader reason，再返回 loader。主机取得本轮完整 prepared 日志后调用已经验证的 loader 复位入口。直接从 XNU 测试核心发出的 PSCI 复位曾原值返回，该路径已从准备载荷移除；实测与来源见[后续记录](../progress/2026-10-27-ios26-k90.md#3-软件进入-fastboot-与剩余验收)。

前置条件为 loader idle 或无 held 的 returned、RAM 系统盘为空、没有其它主机任务访问该设备。GPU held／fault 先按第 6 节保存日志并完成软件冷复位；系统盘非空也先完成本轮采集与复位。工具不会自行覆盖 resident 镜像或丢弃保留资源。准备失败后不复位、不重试目标写入，先保存日志；USB 已失去可用命令入口的情况仍按第 6 节恢复。进入 LK 后重新查询产品与槽位，返回 A 槽后确认 xnuloader idle；复位后系统盘需要重新上传。
