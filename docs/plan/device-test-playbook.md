# annibale 真机调试手册

本页按 2026-10-24 凌晨已读取的实测更新。Android 界面异常及早期调试问题见[系统界面修复记录](../analysis/2026-10-23-android-systemui-recovery.md)，触摸、BQ 电量、性能与阅读截止位置见[桌面交互案例](../analysis/2026-10-24-interactive-runtime.md)，当前进度见[总账](2026-10-23-tracking.md)。操作前仍需确认设备与产物现状。

## 1. 当前启动方式

- `_a` 槽存放驻留 loader 的启动镜像；`_b` 槽保留 Android。SystemUI 和息屏显示插件的编译缓存已重建，用户确认系统界面恢复。
- loader USB 命令通道已实测可用。主机通过 USB 把 `system.apfs` 传入 RAM，再传入内核和小根盘。`bootcpu=1 cpus=1` 已进入桌面，后续 `bootcpu=1 cpus=2` 已确认两颗 CPU 在线。
- 单次上传系统镜像为 2,492,227,584 字节，实测约 62 秒。loader 持续运行期间可以复用该镜像；手机重启后需要重新上传。
- 真机已挂载 System 卷并显示 SpringBoard，用户确认触摸有响应，但延迟很大。启动、显示、输入和性能分别验收；最新设备状态仍以本轮查询与用户反馈为准。

## 2. 操作前检查

1. 读取本页及总账，确认本轮内核、loader、固件和两份 APFS 镜像的文件大小与 SHA-256；修改源码后重新构建对应产物。
2. 先看 `adb devices -l` 和 `fastboot devices`，将目标 Android/LK 序列号设置为环境变量 `ANDROID_SERIAL`；驻留 loader 使用 `xnuloader`。每次切换后重新确认身份，再指定相应序列号。
3. 确认当前槽位和 `_b` 槽可用。写启动镜像仅使用 `boot_a`；调试系统盘使用 USB RAM 上传。
4. kernel 子模块的 `tools/stage-system.sh` 使用无参数调用，经 USB 把系统盘传入 RAM；调用前检查 loader 身份、内核状态和镜像长度。
5. 交互测试使用已清理启动任务的小根盘，核对镜像内 `/etc/rc.jobs`、按需服务及所需动态库。按需启用逐帧或触摸延迟日志，并记录采集窗口；正常交互配置保持低日志量。

## 3. 安装驻留 loader

Android 可连接时，通过 `adb -s "${ANDROID_SERIAL}" reboot bootloader` 进入 LK。内核无响应先保存可读日志并检查软件停止与返回能力；软件恢复不可用，再请用户长按电源键和音量下进入 FASTBOOT。沿用用户已尝试过的动作和结果，减少重复操作。

本次已安装 `hackios-xnu-kernel/out/handoff-loader-v5.img`，包含 v4 的屏幕、GIC、空上传、MPIDR 映射与状态字符串修复，并将 annibale USB reboot 改为直接 PSCI 复位。空闲与 GMU/DCVS 内核运行期间的两次 USB 重启均约 17 秒重新连上 USB，哈希与范围见[GPU 初始化记录](../progress/2026-10-24-gpu-initialization.md)。以下为安装该记录版本的命令，重装前核对本轮实际文件与 SHA-256。`out/` 中的文件是本地构建产物。

```sh
fastboot -s "${ANDROID_SERIAL}" getvar product
fastboot -s "${ANDROID_SERIAL}" getvar current-slot
fastboot -s "${ANDROID_SERIAL}" flash boot_a hackios-xnu-kernel/out/handoff-loader-v5.img
fastboot -s "${ANDROID_SERIAL}" set_active a
fastboot -s "${ANDROID_SERIAL}" reboot
fastboot -s xnuloader getvar product
fastboot -s xnuloader getvar screen
```

成功条件为 `product: xnuloader`。当前配置的屏幕几何应为 `1156 2510 4624`；该值来自固件配置，物理面板的显示仍要目视验证。`reboot` 的主机返回结果只能确认命令已发送，后续状态需要另行读取。

## 4. 上传系统盘并运行内核

以下命令从 `hackios-xnu-kernel/` 目录执行，复用本次已取得触点的双核配置。`out/handoff-mach-affinity` 与 `out/handoff-ui-clean.apfs` 分别为该轮内核与小根盘，使用前按产物清单核对版本和哈希。系统盘只需在本次 loader 生命周期首次运行或更换镜像时上传。

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

## 6. 故障定位与恢复

- `result: running`：内核仍在运行，读取 USB 日志判断进度。
- `result: returned ...` 或 `checkpoint ...`：内核已返回，可取日志并上传下一份 kernel payload；RAM 中的系统盘可以继续使用。
- `result: hung ...`：CPU 仍可能运行或停在异常位置，先重启 loader，再上传系统盘。
- 重启命令后重新枚举且 `result: idle`：loader 已重新启动，先前 RAM 镜像需要重新上传。
- `result: reset-failed`：PSCI 复位调用返回，直接读取日志中的返回值；loader 保留 USB 命令循环。
- `adreno8=15` 的最低档 DCVS 实验要求 `adreno8_keep=1 adreno8_return=0`，采样后通过 loader USB reboot 冷重启，再上传系统盘。当前阶段保留映射和内存；普通退出与 panic 返回都受 `dcvs_requested` 限制。固件 ACK 成功或失败均需要冷重启，不能直接上传下一份内核继续运行。
- `result: no-such-core ...`：先保存 loader 原始日志，核对目标 MPIDR 和 PSCI 返回值。该状态下的旧画面无法用于评估本轮性能。
- USB 有枚举记录但命令无响应：可能是内核占用 loader 的 CPU、USB 传输等待或固件异常。记录命令、耗时、USB 枚举与画面，分别排查。
- 返回 Android：先进入 LK，再执行 `fastboot -s "${ANDROID_SERIAL}" set_active b` 和 `fastboot -s "${ANDROID_SERIAL}" reboot`。loader 的 `reboot` 只执行冷重启，目标仍由当前槽位决定。
- `oem logwrite` 会覆盖 `boot_a` 开头，不能用于保存启动后的日志。当前真机调试使用 USB 日志。
- 桌面 wch 串口属于其他设备。手机 UART 为 GENI `0xa9c000`、`115200n8`，当前没有连接调试线，默认保持关闭。
- Android 整组 `pinmux-pins`／`pinconf-pins` 调试读取后曾发生重启。优先使用已保存的设备树和驱动定义，再决定定点读取；文件读取的硬件副作用需按实现检查。

## 7. 四阶段验收

| 阶段 | 本轮需要取得的结果 |
|---|---|
| loader 已运行 | `getvar product` 返回 `xnuloader`，可读取 loader 日志 |
| 内核已运行 | 内核检查点返回或 USB 日志中出现内核初始化输出 |
| 系统盘已挂载 | 日志出现 `BSD root: md0` 和 APFS System 卷挂载结果 |
| SpringBoard 已显示 | SpringBoard 进程日志、帧缓冲截图和手机实际画面相互确认 |

## 8. 外设开关（修改 kernel payload 的 cmdline）

第 4 节的已测交互配置启用触摸与电量。继续调查其他外设前，按用户确定的优先级选择一项，再向 payload 的 `--cmdline` 追加对应参数：

- `touchscreen=2`：annibale Goodix 触摸。先查芯片身份、报告模式和有效触点，再验证用户滑动与点击的坐标及延迟。当前已取得 9916K 坐标和用户响应确认，延迟仍明显；`ready` 日志及自动解锁脚本的手势都不足以完成手指操作验收。
- `hv_haptic=3`：PMIC 震动自检——起内核后 30 ms 直驱一次马达，**手感就是验收** （屏幕/串口都看不到它）。注意 059a59e 修正了 ppid（0x0f0→0x7f0，TI 块在 slave 7，DT 路径裁决），**旧镜像这步必然无感，必须用新 kernel**。没感觉再加 `haptic_amp=128` 试更大；仍无 → USB 日志读 `haptic:` 前缀（arbiter 表、revision、fault 都在里面）。
- `hv_haptic=4`：iOS 反馈直通马达（/dev/redwood-haptic，DIRECT_PLAY 跟随响度）。桌面点击该有震感。上限 1 s/次，fault 自动弃疗。
- `buttons=1`：音量/电源键（已入库 annibale_buttons.c，纯读零写入 PMIC）。音量上=PMI GPIO slave1 function 0x18d 低有效带上拉（DT #L9164/#L21098，**不是**任务书早先写的 TLMM GPIO6——若真机无事件先查这条）；电源/音量下=PMK8550 PON（KPDPWR/RESIN）。按键事件进 USB 日志 `buttons:` 行 + `/dev/redwood-input`。细分步 `buttons_hv_steps=1..5`。
- `torch_secs=3`：手电盲测——亮 3 秒自己灭，肉眼即验收（annibale_torch.c；先验 TYPE/SUBTYPE+无 fault 才写，每写必回读；`torch_ma=1..500` 调电流默认 125；实时 fault 直接拒亮不猜）。
- `battery=1`：当前 annibale 实现读取 I²C 地址 `0x55` 的 BQ27Z561，通过 GPIO52/53 传输并在采样后恢复引脚。检查有效电量、电压、温度及 `RedwoodBattery` 发布结果；电流符号推导的状态仍需与独立的充电器状态核对。实现及样本边界见[桌面交互案例](../analysis/2026-10-24-interactive-runtime.md)。
- 按键验收依次查看 arbiter、通道表、TYPE/SUBTYPE、引脚状态和 `buttons:` 事件，再核对 iOS 行为。手电无光先查 TYPE/SUBTYPE、fault 与写入回读；现有实现遇到 fault 拒绝点亮，清除 fault 的语义仍待核实，`torch_secs` 在驱动内最多为 5 秒。
- `pcie=1..3`：Wi-Fi 卡的 PCIe 勘察（redwood_pcie.c，读为主：step2 借 iATU 窗口做 BAR sizing 会存全恢，link down 时拒绝动）。屏上无效果，验收=USB 日志取得 `pcie:` 前缀行：LTSSM 状态/链路速度宽度/17cb:1107 认卡/BAR0/MHI 状态机。step1 的电源脚+GDSC 普查表是"上电拉 link"批次的输入。boot-arg 用 pcie= 是刻意避开老 redwood_wifi.c 的 wifi=。
- 每轮只增加一个待测驱动，先检查 USB 日志和对应的实际行为。日志按第 5 节区分运行期间与内核返回后的读取顺序。
- 触摸/震动都惰性于默认 cmdline（不带旗标=零动作），QEMU 同理不需要它们。
