# 2026-10-23 真机启动、桌面和外设排查

本轮继续真机调试。Android 界面恢复见[系统界面修复记录](../analysis/2026-10-23-android-systemui-recovery.md)，常用操作见[真机调试手册](../plan/device-test-playbook.md)。本页记录实测结果与尚未完成的部分。

## 1. 已确认的桌面状态

23:17 通过驻留 loader 读取 iOS 主屏幕截图，用户随后确认手机实际桌面显示正常。面板参数为 `1156 × 2510`、stride `4624`；iOS 使用 `1125 × 2436` 的逻辑帧缓冲。壁纸与半透明效果随后恢复，用户再次确认，但首次加载会停顿数秒。触摸和电量仍在排查。

第一轮桌面测试设置了 `loader_return_after=300`。用户报告时间停在 11:21，主机对应读到 `result: returned 1361841 0`；内核已按测试时限退出，屏幕保留最后一帧。后续交互测试取消该时限，通过 USB `oem stop` 主动结束。已实测停止、读取合并日志、复用 RAM 系统盘并启动下一份内核，整个过程无需按键或重插 USB。

## 2. 完整启动此前停滞的原因

`redwood_input_init()` 默认调用 CPU 频率初始化，平台判断函数又在外设开关检查前读取 `0x01fc0000`。源码曾假定该地址可返回 SoC ID；现有设备树和 Linux socinfo 定义不足以支持该读取方法。逐段检查已通过 APFS 挂载、根 vnode 和 devfs 初始化，替换该平台判断后通过输入初始化并启动 SpringBoard。

当前 `redwood_platform_blocks_legacy_drivers()` 使用 loader 提供的 GIC 地址和范围识别项目既有 redwood、QEMU 描述，其余描述阻止旧机型驱动初始化。识别过程不访问硬件寄存器。annibale 的触摸由显式参数 `touchscreen=2` 选择，其他外设使用各自的 annibale 驱动。相关约束见[项目排查与协作手册](../plan/debugging-and-collaboration.md)。

同时修复了独立发现的问题：第 10 检查点过早读取未初始化的 `PE_state.bootArgs`；SM8750 GIC redistributor 的步长和范围；固件屏幕几何；空数据 USB 上传；C 版控制台滚屏的字节数和向下复制起点。滚屏测试使用保护页、相邻数据和重叠复制，旧实现触发 SIGBUS，修复后通过。临时的内核阶段检查点已从最终源码删除。

日志现在覆盖视频控制台与 kprintf 的无 UART 分支，并在 panic 与 fatal exception 的视频输出之前保留文字和异常寄存器。触摸首次启用后的数据异常已成功返回 loader，USB 取得了完整 panic 信息。该结果覆盖内核异常返回；某些外设访问仍会导致整机重新启动，需重新上传 RAM 系统盘。

## 3. 壁纸和半透明效果

`userland/mkjobs.py` 的按需服务循环用 `name` 保存目标文件名，内部环境变量循环又把它改成 `RWA_PACKED16`。所有按需服务因此覆盖同一文件，`com.apple.PosterBoard.plist`、`com.apple.chronod.plist` 等配置缺失。运行日志对应出现 `com.apple.posterboardservices.services` 查找失败，桌面背景为黑色，小组件为空白。

修复把内部变量改为 `env_name`。重新生成镜像后有 382 个按需服务，PosterBoard 和壁纸扩展实际启动，截图显示 iOS 壁纸。回归测试覆盖环境变量设置与未设置两种情况，检查独立文件名、MachServices 和按需启动属性；原脚本两种情况均失败，修复后通过。

原始小镜像还缺少 `libredwood-gl.dylib` 与 `libOSMesa.8.dylib`，CoreAnimation 日志报告无法初始化 Metal/OpenGL ES，上屏使用内置软件渲染。对照镜像加入已构建的 Mesa 26.2.5 库，以 `gl=1` 启用 OpenGL ES。运行日志确认 `softpipe`，用户确认半透明效果恢复。此路径由 CPU 绘制，尚未启用 K90 GPU；首次加载停顿数秒仍待优化。

## 4. 触摸初始化

最初桌面的启动参数没有 `touchscreen=2`。启用前检查还发现：K90 没有旧机型的触摸识别 GPIO，诊断打印却把 `NO_STRAP=1000` 作为真实编号访问。已使该占位编号直接返回无输入，并删除重复宏定义。

首次启用后，驱动扫描 SMEM 寻找 RPMh 数据库，在对应物理地址 `0x81d9e004` 发生同步外部异常（ESR `0x96000010`）。合并设备树明确声明独立的 `qcom,cmd-db` 区域 `0x81c60000 + 0x20000`。改为直接读取该区域后，真机找到 `ldob12 = 0x40a00`。

随后分阶段检查 GPIO、供电和 SPI。时钟状态打印仍使用旧机型的 AHB 寄存器 `0x18004/0x18008`；SM8750 主线 GCC 驱动给出的偏移为 `0x23140/0x23144`。已按板型选择，SE2 时钟停止标志也改为 bit 31。来源为 [Linux v6.17 gcc-sm8750.c](https://github.com/torvalds/linux/blob/v6.17/drivers/clk/qcom/gcc-sm8750.c)。这些更改之后的触摸实测继续记录。

## 5. 产物与记录

已安装驻留 loader 为 `hackios-xnu-kernel/out/handoff-loader-v3.img`。系统盘通过 USB 上传到 RAM，大小 `2,492,227,584` 字节，单次约 62 秒。实验只写过 `boot_a`；后续内核和用户态迭代均使用 RAM。Android 保留在 B 槽。

当前桌面修复镜像为 `out/handoff-ui-root.apfs`，由独立的 `out/handoff-gl-root/` 目录生成，保留原 `userland/root.apfs` 作为对照。镜像加入 Mesa 库并重新生成按需服务。运行内核的具体版本、启动参数、日志及截图保存在本地调试目录 `/tmp/hackios-handoff/`，本轮结束时同步到忽略提交的 `docs/progress/evidence/2026-10-23-handoff/` 并更新产物清单。
