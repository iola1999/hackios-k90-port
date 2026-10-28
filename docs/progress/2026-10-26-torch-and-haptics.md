# K90 手电与震动驱动实测（2026-10-26）

手电驱动 `bsd/dev/annibale_torch.c` 和震动驱动 `bsd/dev/annibale_haptic.c` 在 K90 上的首批无人值守运行。原始日志保存在 Git 忽略的 `docs/progress/evidence/2026-10-25-codex-gpu-resume/`，下文用目录名指代各轮运行。启动参数的含义见 [playbook](../plan/device-test-playbook.md) 第 8 节。

## 1. 结论

- 手电：`torch_secs=2 torch_ma=50` 时，驱动依次写入安全定时器、目标电流、模块使能和通道 0 使能，每次写入都读回一致，报告通道 0 以 50 mA 点亮 2 s 后熄灭。`torch=3` 时 iOS 经 AVFlashlight 和 mediaserverd 控制手电，控制中心出现手电按钮（第 4 节）。灯是否实际亮起没有人在场确认。
- 震动：`hv_haptic=3` 时，驱动完成配置（1300 mV、5714 µs 周期、闭环制动、正弦波形），以幅度 0x60 直驱马达 30 ms，故障寄存器为 0。`hv_haptic=4` 时，长按图标弹出快捷菜单，iOS 播放的触感经 `/dev/redwood-haptic` 驱动马达（第 6 节）。马达是否实际振动没有人在场确认。
- 两个驱动原来都用 Extended Register Write（仲裁器操作码 2）写 1～4 字节，K90 上寄存器值不变；改用 Extended Register Write Long（操作码 0）后写入生效（第 2 节）。
- 修复过程中出现过两次 panic，均来自 SPMI 仲裁器写通道窗口的映射方式，已修复（第 3 节）。

## 2. SPMI 仲裁器写入

两个驱动经 PMIC 仲裁器 v7（版本 `0x70020000`，896 个通道）访问 PMIC：读走观察窗口 `0xc440000`，写走通道窗口 `0xc500000`，每个通道 `0x1000` 字节，布局按 Linux `drivers/spmi/spmi-pmic-arb.c`。

- 读取用 Extended Register Read（操作码 13），按键驱动和这两个驱动的读数都与原厂设备树和寄存器定义一致。
- 写入原来用 Extended Register Write（操作码 2）。`kernel-iova-s23-auto-periph` 中，手电驱动把安全定时器 `0x3e` 从 `0x93` 写为 `0x13`，仲裁器报告传输完成且没有错误位，读回仍为 `0x93`，驱动按规则停止全部写入。
- Linux 的 `regmap-spmi-ext` 对 16 位寄存器地址发送 Extended Register Write Long（操作码 0），旧设备的 `redwood_torch.c` 也用操作码 0。手电（内核 `4d6eee3`）和震动（内核 `1f83244`）改用操作码 0 后，同一写入读回一致。操作码 2 写入无效的原因没有确认。
- 手电驱动在读回不一致时会在 1 ms 后再读一次并一起报告，用于区分寄存器延迟更新和写入无效。

## 3. 手电

模块为 PM8550（SPMI slave 1）的 flash LED，寄存器 `0xee00`，仲裁器通道 617，写入方为系统 0（APPS）。启动时读到的状态：type `0x18`、subtype `0x07`，无实时故障和锁存故障，安全定时器 `0x93`（定时器使能，200 ms），strobe `0x01`。

- 第一次 panic（`kernel-bufsize-s23-auto-periph`，内核 `861f9bd`）：Kernel data abort。驱动只映射了写通道窗口的前 64 KB，通道 617 位于 `0x269000`，写入地址落在映射之外。
- 第二次 panic（`kernel-lockwait3-s23-auto-periph`，内核 `f1f2665`）：改为映射整个 4 MB 窗口后，启动早期 `kmem_alloc(..., 4194304, ...)` 返回 3（`KERN_NO_SPACE`）。
- 内核 `5557759` 只映射用到的通道各 4 KB，之后各轮没有 panic，并在发现模块后才映射。
- 原厂驱动 `leds-qti-flash.c` 在探测和关闭时清除安全定时器使能位，只在闪光模式下设置。本驱动点亮前清除该位，熄灭时恢复启动时的值。
- `kernel-torchwl-s23-auto-torch`（`4d6eee3`）、`kernel-publish-s23-auto-periph`（`d4df543`）和 `kernel-hapclr-s23-auto-periph`（`5847dd3`）三轮都点亮 2 s 后熄灭，熄灭后模块使能、电流档位、strobe 和通道 0 目标电流均为 0。

## 4. iOS 手电（`torch=3`）

内核 `a56627f` 在 `torch=3` 时创建 `/dev/redwood-torch`，接口与 redwood 相同：写入 32 位档位 0～1000（`torch_ma` 的千分之几，0 为关），读出当前点亮的档位。根盘中 `libredwood-media.dylib` 已有的 FigFlashlight 替换直接使用这个设备。点亮期间每 100 ms 检查一次：仍处于点亮状态、没有实时故障、电池温度不超过 45 °C；单次点亮最长 `torch_max_s`（默认 30 s，最多 120 s），到时熄灭，直到 iOS 写入 0 后才能再次点亮。点亮状态下改变档位只写 ITARGET。loader 在任何 `torch=N` 时告诉 iOS 相机有闪光灯，控制中心因此显示手电按钮。

`kernel-hcache-s23-auto-torch3`（内核 `00259e5`，根盘 `out/handoff-ui-auto-torch.apfs`，`rc.jobs` 在解锁后运行 `torch_test`）：

- mediaserverd 报告「the kernel has a flashlight (/dev/redwood-torch)」；`torch_test` 报告 AVFlashlight 的 `hasFlashlight` 为 YES、`available` 为 YES。
- 档位 1.0：内核写入安全定时器、ITARGET `0x03`、模块使能和通道使能，读回一致，通道 0 以 50 mA 点亮，`torch_test` 读到「LIT at 1000 of 1000」。档位 0.25：ITARGET 改为 `0x00`（12.5 mA），读到「LIT at 250 of 1000」。关闭：通道和模块使能清零，读到「dark」。
- 控制中心截图中出现手电按钮，灯亮时按钮为点亮状态。
- 第二次点亮后，另一个 `torch_test` 进程执行关闭时，它新建的 AVFlashlight 读到的档位已是 0，没有向 mediaserverd 发出关闭，灯保持点亮；内核在亮满 30 s 时按上限熄灭。这说明时长上限生效。

`kernel-hcache-s23-auto-torchcc`（同一内核，根盘 `out/handoff-ui-auto-torchcc.apfs`）用 `rwtouch` 打开控制中心，点按手电按钮（屏幕坐标 0.386, 0.611），5 s 后再点按一次，按 home 收起，再用 `torch_test state` 读内核状态，共 3 轮。每轮 mediaserverd 先收到档位 850，内核点亮（ITARGET `0x02`，37.5 mA），再收到 0，内核熄灭；3 次读到的状态都是 dark。

## 5. 震动

模块为 PMIH010x（SPMI slave 7）的 HV haptics：驱动 `0xf000`、波形引擎 `0xf100`、升压 `0xf200`，对应仲裁器通道 648、649、650，写入方为系统 0；通道 577、578 是同一组外设的另一组通道，写入方为系统 3。

- 只读检查（`hv_haptic=1`，`kernel-iova-s23-auto-periph`）：驱动和波形引擎 revision `0x5.0x1`，升压 `0x1.0x1`，故障 0，实时状态 `0x8`，HPWR 0，阻抗读数 0，FIFO ready 1。
- `kernel-publish-s23-auto-periph`（`d4df543`）：模块使能写入成功；随后写 `FAULT_CLR`（`0xf066`）= `0x07`，读回 0，驱动停止。`FAULT_CLR` 是写 1 清除的命令寄存器，写入后自动归零，原驱动对它也做读回比较。这一轮退出时模块保持使能：原退出路径只在配置全部完成后才关闭模块。
- 内核 `5847dd3`：`FAULT_CLR` 写入后改为检查故障状态寄存器 `0xf00c` 为 0；只要写过寄存器，退出路径和 quiesce 都关闭模块。
- `kernel-hapclr-s23-auto-periph`（`5847dd3`）：VMAX `0x1a`、制动模式 `0x41`、波形选择 `0x11` 写入并读回一致；直驱 30 ms 后故障寄存器为 0，HPWR 从 0 变为 `0x3`，阻抗读数仍为 0。

## 6. iOS 触感反馈（`hv_haptic=4`）

`hv_haptic=4` 时内核创建 `/dev/redwood-haptic`，根盘中 RedwoodAudio 插件把 iOS 在「Actuator」设备上播放的波形写入这个设备，驱动按波形峰值直驱马达，单次最长 1 s，出现故障即停止使用马达。

`kernel-gpugov-s23-auto-hap4`（内核 `ffca661`，根盘 `out/handoff-ui-auto-haptic.apfs`）在解锁后进行 6 轮操作，每轮长按「备忘录」图标 1.2 s、按 home 收起快捷菜单，再下拉控制中心和左右翻页：

- 截图中长按后出现「备忘录」的快捷菜单，背景模糊。
- 驱动记录 7 次短触感和 1 次持续振动。短触感中 6 次波形峰值为 23519／32768，按 `0x60` 直驱；1 次峰值 906，按 `0x3e` 直驱。持续振动在 iOS 停止播放后 301 ms 结束。整轮没有故障，驱动没有停止使用马达。
- 运行 420 s，没有 panic，98 张截图没有色块。

## 7. 需要人工确认

- 手电：`torch_secs=2` 时相机闪光灯是否亮 2 s 后自己熄灭。
- 震动：`hv_haptic=3` 时开机后是否有一次约 30 ms 的振动；`hv_haptic=4` 时长按图标弹出快捷菜单是否有震感。
- 控制中心手电按钮（`torch=3`）：点按后闪光灯是否实际亮起和熄灭。
