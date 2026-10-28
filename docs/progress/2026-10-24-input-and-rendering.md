# 2026-10-24 输入修复与绘制定位

## 1. 输入与电量

GT9916K 已接受关闭 THP 原始帧的 `00 00 06 90 02 00 98 00` 与开启坐标的 `00 00 05 91 01 97 00`。驱动取得连续坐标，用户确认滑动和点击可以引起界面响应。命令来源为小米 `vendor_xiaomi_proprietary_touch-driver` 的 `warsaw-w-oss/warsaw/goodix_9916k/goodix_brl_hw.c`，具体型号与 K90 的 GT9916K 一致，分支对应其他机型。主机测试校验这两个包、ACK 重试和失败分支。

启用 `buttons=1` 后，PMIC arbiter 返回版本 `0x70020000`。PON `0x013` 对应通道 581，GPIO6 `0x18d` 对应通道 610，类型与输入配置均通过驱动检查。用户先确认电源键可锁屏和唤醒，随后确认音量加减也有响应，主要剩余问题是操作延迟。

BQ27Z561 原始电量约 94–95%，iOS 已显示百分比。充电标志仍按电流方向推算；USB 已连接，但尚未读取独立的充电器在线状态。此项继续待修。

## 2. CPU 映射

原 loader 按核心编号左移 8 位生成 MPIDR，遗漏 CPU6/7 的实际地址 `0x10000/0x10100`。改为逐核心表，同时保留内核 CPU 查找、secondary 入口和 GIC SGI 的 Aff2。`common/new-device.sh` 同步输出完整 MPIDR 表，已用本机 Android DTB 验证。

`out/handoff-loader-v4.img` 已安装到 `boot_a`。内核 `out/handoff-mach-affinity` 实测注册 `0x10100/0x10000` 并报告 `2 of 2 processors are running`；USB 停止、读取日志与后续启动已验证。loader 状态字符串改用保留的临时缓冲范围格式化，日志填满后仍能设置 `running`。`getvar screen` 仍有同类缓冲依赖，后续需要处理。

## 3. 卡顿与 GPU

软件绘制的慢调用与线程采样见 [Metal 路径对照](../analysis/2026-10-24-metal-route.md)。当前主要耗时在 Mesa `softpipe` 的解释执行和纹理采样。普通启动脚本已移除 CPU 压测及演示诊断任务；交互配置保留自动解锁。

首次 `adreno8=1 adreno8_pause=200 adreno8_return=1` 试验发生复位，日志仅覆盖 framebuffer 初始化附近。阶段日志代码此前在步骤执行后才更新目标步骤，首步的访问前停留没有生效；改为执行前设置目标，并单独记录已完成步骤。随后使用 `adreno8_pause=2200 adreno8_fine=1`，日志记录到对 `0x221c8138` 的字节读取，读取后设备复位，loader 自动重新枚举。

[Linux 的 QFPROM 修复说明](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2501.1/01877.html)要求 SM8450 及以后平台使用 4 字节读取，[v6.17 实现](https://github.com/torvalds/linux/blob/v6.17/drivers/nvmem/qfprom.c)也按字对齐后执行 `readl`。本仓将两次字节读取改为一次对齐的 32 位读取，并按本机 DT 的 `bits = <0 9>` 把掩码改为 `0x1ff`。真机返回 `0x400400e8`，随后 GCC 和 RPMh 资源读取完成，`getvar result` 返回 `returned 24374 0`；这一轮验证第 1 阶段及返回过程，尚未验证 GPU 上电和绘制。

提取出的 `speed_bin` 为 232，设备树频率表按 `qcom,sku-codes` 的 0／2／3 选择。现有代码直接比较两者并回退到 900 MHz 表，该对应关系仍需核对厂商驱动。RPMh BCM 描述的字段布局也需重新核对，日志中的 width／unit 值尚未验证。继续电源、频率和 HFI 测试前先处理这些差异。本轮复位恢复与后续启动均通过 USB 完成，无需用户重新插拔。测试后重新运行已验证的双核交互配置，状态持续为 `running`，主机截图显示完整设置页面和 94% 电量；这份配置仍使用软件绘制。

后续已完成电源、时钟、DTCM 和 SMMU 识别，SKU 与 BCM 布局的修正及 GMU 固件选择见[GPU 初始化记录](2026-10-24-gpu-initialization.md)。

## 4. 产物与验证

- loader：`hackios-xnu-kernel/out/handoff-loader-v4.img`，SHA-256 `6bd768a28d469a1749a0f8aa15feaf1cba95eb3ff550d723af8031103e561dac`。沿用 v3 的固件、BootShim 与 DTB，仅替换 loader payload。
- 内核：`hackios-xnu-kernel/out/handoff-mach-affinity`，SHA-256 `8df83d8234dcfb61fc9aae907d167dc036bedd592ff60801227e29c09bd2aedd`。
- QFPROM 修复验证内核：`hackios-xnu-kernel/out/handoff-mach-qfprom32`，SHA-256 `5369a04a38ef7995b19702c83484f8b1f4b2fde50258c2f0b81a2dd729cbe732`；仅在单独的 GPU 第 1 阶段配置中启用 `adreno8=1`。
- 正常小根盘：`out/handoff-ui-clean.apfs`；GPU 固件试验根盘：`out/handoff-ui-gpu.apfs`；临时地址诊断库根盘：`out/handoff-gl-profile.apfs`。三者分别保留。
- 内核构建通过；`tools/test-annibale-input.py` 通过。触摸传输和 FocalTech 私有实现按职责移入两个头文件，三个文件分别为 625、617、405 行；拆分保留同一翻译单元与静态状态。
- 原始日志与清单保存到忽略提交的 `docs/progress/evidence/2026-10-24-input-rendering/`。功能验收继续区分驱动读数、iOS 事件和用户实际操作。
