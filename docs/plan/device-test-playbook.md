# annibale 真机调试手册

本页按 2026-10-23 晚间接手后的实测更新。Android 界面异常的处理及早期调试问题见 [系统界面修复记录](../analysis/2026-10-23-android-systemui-recovery.md)，当前进度见 [总账](2026-10-23-tracking.md)。

## 1. 当前启动方式

- `_a` 槽存放驻留 loader 的启动镜像；`_b` 槽保留 Android。SystemUI 和息屏显示插件的编译缓存已重建，用户确认系统界面恢复。
- loader USB 命令通道已实测可用。主机通过 USB 把 `system.apfs` 传入 RAM，再传入内核和 `root.apfs`，启动参数使用 `bootcpu=1 cpus=1`。
- 单次上传系统镜像为 2,492,227,584 字节，实测约 62 秒。loader 持续运行期间可以复用该镜像；手机重启后需要重新上传。
- 真机已通过内核入口、MMU 开启、C 初始化和平台初始化后的第 21 个检查点。完整 iOS 真机启动仍在调试，不能根据 USB 断开或花屏判断 SpringBoard 已启动。

## 2. 操作前检查

1. 读取本页及总账，确认本轮内核、loader、固件和两份 APFS 镜像的文件大小与 SHA-256；修改源码后重新构建对应产物。
2. 先看 `adb devices -l` 和 `fastboot devices`，将目标 Android/LK 序列号设置为环境变量 `ANDROID_SERIAL`；驻留 loader 使用 `xnuloader`。每次切换后重新确认身份，再指定相应序列号。
3. 确认当前槽位和 `_b` 槽可用。写启动镜像仅使用 `boot_a`；调试系统盘使用 USB RAM 上传。
4. `tools/stage-system.sh` 已改为 USB 上传。旧命令中的 `--yes` 不再适用，使用无参数调用。

## 3. 安装驻留 loader

Android 可连接时，通过 `adb -s "${ANDROID_SERIAL}" reboot bootloader` 进入 LK。设备已停在无响应的内核中，需要长按电源键和音量下进入 FASTBOOT。

本次已安装的屏幕与 GIC 修复版为 `hackios-xnu-kernel/out/handoff-loader.img`。空日志 USB 协议修复版为 `out/handoff-loader-v2.img`，安装状态以总账为准。`out/` 中的文件是本地构建产物。

```sh
fastboot -s "${ANDROID_SERIAL}" getvar product
fastboot -s "${ANDROID_SERIAL}" getvar current-slot
fastboot -s "${ANDROID_SERIAL}" flash boot_a hackios-xnu-kernel/out/handoff-loader-v2.img
fastboot -s "${ANDROID_SERIAL}" set_active a
fastboot -s "${ANDROID_SERIAL}" reboot
fastboot -s xnuloader getvar product
fastboot -s xnuloader getvar screen
```

成功条件为 `product: xnuloader`。当前配置的屏幕几何应为 `1156 2510 4624`；该值来自固件配置，物理面板的显示仍要目视验证。`reboot` 的主机返回结果只能确认命令已发送，后续状态需要另行读取。

## 4. 上传系统盘并运行内核

以下命令从 `hackios-xnu-kernel/` 目录执行。`out/handoff-mach` 是本轮增量构建的内核，包含早期检查点返回修复和 GIC redistributor stride 修复；其校验记录与启动日志保存在 `docs/progress/evidence/2026-10-23-handoff/`。

```sh
bash tools/stage-system.sh
python3 xnuloader/mkpayload.py -o out/handoff-full.bin kernel=out/handoff-mach ramdisk=userland/root.apfs --cmdline "debug=0x10e serial=3 cpus=1 bootcpu=1 loader_return_after=900 epoch=$(date +%s) -v"
fastboot -s xnuloader stage out/handoff-full.bin
fastboot -s xnuloader oem run
fastboot -s xnuloader getvar result
```

`bootcpu=1` 把内核放到 MPIDR `0x100` 的 CPU 上，loader 保留当前 CPU 处理 USB。`cpus=1` 限制本轮内核只使用一颗 CPU。`loader_return_after=900` 请求内核运行 900 秒后返回；初始化失败或挂起仍可能影响返回过程。提前结束使用 `fastboot -s xnuloader oem stop`，随后确认 `result` 已离开 `running`。

## 5. 读取日志和截图

```sh
fastboot -s xnuloader oem log
fastboot -s xnuloader get_staged /tmp/hackios-kernel.log
fastboot -s xnuloader getvar screen
fastboot -s xnuloader oem screenshot
fastboot -s xnuloader get_staged /tmp/hackios-screen.raw
```

`oem log` 和 `oem screenshot` 只准备数据，`get_staged` 才把数据传回主机。截图为原始帧缓冲，按 `getvar screen` 的宽、高和每行字节数解码。本机 fastboot CLI 使用 `get_staged`；线上的 USB 协议命令名为 `upload`。

旧 loader 的空数据上传会发送 `DATA00000000`，主机拒收后未读最终状态，loader 会一直等待传输完成。本轮增加了空数据检查，直接返回 `FAIL no staged data`。旧版遇到该问题需要恢复 USB 或重新启动 loader；不应把一次超时记录成内核已重启。

## 6. 故障定位与恢复

- `result: running`：内核仍在运行，读取 USB 日志判断进度。
- `result: returned ...` 或 `checkpoint ...`：内核已返回，可取日志并上传下一份 kernel payload；RAM 中的系统盘可以继续使用。
- `result: hung ...`：CPU 仍可能运行或停在异常位置，先重启 loader，再上传系统盘。
- `result: idle` 且日志重新出现 `XNULOADER v3`：loader 已重新启动，先前 RAM 镜像需要重新上传。
- USB 有枚举记录但命令无响应：可能是内核占用 loader 的 CPU、USB 传输等待或固件异常。记录命令、耗时、USB 枚举与画面，分别排查。
- 返回 Android：先进入 LK，再执行 `fastboot -s "${ANDROID_SERIAL}" set_active b` 和 `fastboot -s "${ANDROID_SERIAL}" reboot`。loader 的 `reboot` 只执行冷重启，目标仍由当前槽位决定。
- `oem logwrite` 会覆盖 `boot_a` 开头，不能用于保存启动后的日志。当前真机调试使用 USB 日志。
- 桌面 wch 串口属于其他设备。手机 UART 为 GENI `0xa9c000`、`115200n8`，当前没有连接调试线，默认保持关闭。

## 7. 四阶段验收

| 阶段 | 本轮需要取得的结果 |
|---|---|
| loader 已运行 | `getvar product` 返回 `xnuloader`，可读取 loader 日志 |
| 内核已运行 | 内核检查点返回或 USB 日志中出现内核初始化输出 |
| 系统盘已挂载 | 日志出现 `BSD root: md0` 和 APFS System 卷挂载结果 |
| SpringBoard 已显示 | SpringBoard 进程日志、帧缓冲截图和手机实际画面相互确认 |

## 8. 外设开关（修改 kernel payload 的 cmdline）

真机显示 SpringBoard 后，逐个外设加旗标复测（payload `--cmdline` 追加）：

- `touchscreen=2`：annibale Goodix 触摸（cc9ff58 参数化）。锁屏上手指的滑动解锁就是验收；坏了指纹=日志落 USB 日志里 `goodix:` 前缀行。
- `hv_haptic=3`：PMIC 震动自检——起内核后 30 ms 直驱一次马达，**手感就是验收** （屏幕/串口都看不到它）。注意 059a59e 修正了 ppid（0x0f0→0x7f0，TI 块在 slave 7，DT 路径裁决），**旧镜像这步必然无感，必须用新 kernel**。没感觉再加 `haptic_amp=128` 试更大；仍无 → USB 日志读 `haptic:` 前缀（arbiter 表、revision、fault 都在里面）。
- `hv_haptic=4`：iOS 反馈直通马达（/dev/redwood-haptic，DIRECT_PLAY 跟随响度）。桌面点击该有震感。上限 1 s/次，fault 自动弃疗。
- `buttons=1`：音量/电源键（已入库 annibale_buttons.c，纯读零写入 PMIC）。音量上=PMI GPIO slave1 function 0x18d 低有效带上拉（DT #L9164/#L21098，**不是**任务书早先写的 TLMM GPIO6——若真机无事件先查这条）；电源/音量下=PMK8550 PON（KPDPWR/RESIN）。按键事件进 USB 日志 `buttons:` 行 + `/dev/redwood-input`。细分步 `buttons_hv_steps=1..5`。
- `torch_secs=3`：手电盲测——亮 3 秒自己灭，肉眼即验收（annibale_torch.c；先验 TYPE/SUBTYPE+无 fault 才写，每写必回读；`torch_ma=1..500` 调电流默认 125；实时 fault 直接拒亮不猜）。
- `battery=1`：电量（annibale_battery.c，纯读）——SDAM 校验 VALID=1 才发布，电量图标出数即验收；step2 全总线 TYPE/SUBTYPE 普查是**勘察红利**（FG=0x0d/SDAM=0x2e 命中自动采用，slave7 优先），USB 日志里 `battery:` 前缀可回收全部 PMIC 外设表。细分步 `battery_hv_steps=1..5`。
- **设备轮观测要点（buttons/battery/torch，drivers 按代码现状注）**：buttons 看步进断点——五步每步动手前先落日志（arbiter 版本→通道表→TYPE/SUBTYPE 首笔总线收发→按键脚配置与当前电平→值守），停在第几步失败面就在第几步；到第 5 步后每次按键必须多一条 `buttons:` 事件行，没有就先复核上面 0x18d 那条，纯读驱动排除写坏可能。battery 图标不出数先分两层：日志 step4 的 FG/SDAM 原始读数在不在（总线不通）与 VALID 位是否为 1（Android 遗留在 SDAM 的数据未过期校验通过才发布）；屏上"充电中"字样是电流符号推断（充电块走 PMIC-GLINK 本驱动不读），别当充电协议事实收账；step2 全表 dump 在失败轮也是净收益，务必回收。torch 肉眼不亮先 grep 日志 fault 与写回读不一致行——点亮前 TYPE/SUBTYPE+锁存 fault 双验不过会直接不动寄存器，实时 fault 拒亮且不清 fault（清除寄存器语义未实证，宁不亮不瞎清）；`torch_secs` 驱动内封顶 5 s，传更大值日志会说明。
- `pcie=1..3`：Wi-Fi 卡的 PCIe 勘察（redwood_pcie.c，读为主：step2 借 iATU 窗口做 BAR sizing 会存全恢，link down 时拒绝动）。屏上无效果，验收=USB 日志取得 `pcie:` 前缀行：LTSSM 状态/链路速度宽度/17cb:1107 认卡/BAR0/MHI 状态机。step1 的电源脚+GDSC 普查表是"上电拉 link"批次的输入。boot-arg 用 pcie= 是刻意避开老 redwood_wifi.c 的 wifi=。
- 外设按上述顺序逐个启用，每轮只增加一个驱动，先检查 USB 日志和对应的实际行为。日志通过 `oem log` 和 `get_staged` 读取。
- 触摸/震动都惰性于默认 cmdline（不带旗标=零动作），QEMU 同理不需要它们。
