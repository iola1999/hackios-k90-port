# Android 系统界面异常与编译缓存修复（2026-10-23）

设备为 REDMI K90（annibale），Android 位于 `_b` 槽。本文记录系统界面异常的本次实测。Android 构建指纹为 `Redmi/annibale/annibale:16/BP2A.250605.031.A3/OS3.0.303.0.WPKCNXM:user/release-keys`。

## 1. 表现与检查结果

用户反馈通知栏、动画和底部手势条消失，重启菜单也有变化；重启后持续存在。ADB 能连接，`sys.boot_completed=1`，`ro.boot.slot_suffix=_b`。`com.android.systemui` 进程反复退出，原生日志在 `art::VdexFile::ComputeClassStatus` 报以下断言失败：

```text
Check failed: string_id.index_ - num_ids_in_dex < number_of_extra_strings
(string_id.index_ - num_ids_in_dex=2945118909, number_of_extra_strings=1126026389)
```

重建 SystemUI 的编译缓存后，崩溃位置转到息屏显示插件 `MIUIAod.apk`，调用栈经过 `art::ClassLinker::LoadClass`、`PluginInstance.loadPlugin` 和 `/data/dalvik-cache/arm64/product@priv-app@MIUIAod@MIUIAod.apk@classes.dex`。继续重建 `com.miui.aod` 的编译缓存后，SystemUI 进程保持运行，窗口列表重新出现 `StatusBar` 和 `NavigationBar0`；用户于 22:10 左右确认界面恢复。

## 2. 本次修复步骤

先读取 `logcat -b crash`、确认崩溃包名和 APK 路径，再备份对应的 `.dex`、`.vdex`。本次 adbd 已具备 root 权限。普通 adbd 需要通过已授权的 `su` 访问这些文件。

先通过 `adb devices -l` 确认目标，将其序列号设置为环境变量 `ANDROID_SERIAL`，再执行下列命令。

```sh
adb -s "${ANDROID_SERIAL}" shell 'getprop ro.boot.slot_suffix; getprop ro.build.fingerprint'
adb -s "${ANDROID_SERIAL}" shell 'logcat -b crash -d -t 300'
adb -s "${ANDROID_SERIAL}" shell 'pm path com.android.systemui; pm path com.miui.aod'
adb -s "${ANDROID_SERIAL}" shell 'ls -l /data/dalvik-cache/arm64/*MiuiSystemUI* /data/dalvik-cache/arm64/*MIUIAod*'
adb -s "${ANDROID_SERIAL}" shell 'pm help'
```

本次备份了以下文件，保存在主机 `/tmp/hackios-handoff/android-cache/`；该目录为本次诊断的临时文件，后续操作应另建备份目录。

| 文件前缀 | `.dex` 字节数 | `.vdex` 字节数 |
|---|---:|---:|
| `/data/dalvik-cache/arm64/system_ext@priv-app@MiuiSystemUI@MiuiSystemUI.apk@classes` | 61,274,600 | 849,144 |
| `/data/dalvik-cache/arm64/product@priv-app@MIUIAod@MIUIAod.apk@classes` | 43,783,984 | 18,834,612 |

设备的 `pm help` 确认支持 `delete-dexopt`。按包名删除生成的编译产物，再执行校验编译；本次命令均成功，两个包分别报告释放 62,123,744 和 62,618,596 字节。

```sh
adb -s "${ANDROID_SERIAL}" shell 'pm delete-dexopt com.android.systemui'
adb -s "${ANDROID_SERIAL}" shell 'pm compile -m verify -f com.android.systemui'
adb -s "${ANDROID_SERIAL}" shell 'pm delete-dexopt com.miui.aod'
adb -s "${ANDROID_SERIAL}" shell 'pm compile -m verify -f com.miui.aod'
adb -s "${ANDROID_SERIAL}" shell 'pkill -f "^com.android.systemui$"'
```

这些命令的作用范围由 [AOSP ART 的 `ArtShellCommand`](https://android.googlesource.com/platform/art/+/3d595da66e87255b28bb3de11180c37719d8bd09/libartservice/service/java/com/android/server/art/ArtShellCommand.java) 和设备自身帮助确认。操作对象为指定包的编译产物，应用安装和用户数据保留。

验收同时检查进程是否持续运行、崩溃日志是否新增、窗口是否恢复，并请用户确认实际显示。仅看 `pm compile` 返回 `Success` 不能结束检查；本次第二个插件的故障就在第一轮缓存重建后才出现。

```sh
adb -s "${ANDROID_SERIAL}" shell 'pidof com.android.systemui; date'
adb -s "${ANDROID_SERIAL}" shell 'logcat -b crash -d -t 120'
adb -s "${ANDROID_SERIAL}" shell 'dumpsys window windows | grep -E "StatusBar|NavigationBar"'
```

本次确认恢复的是系统界面。另有 `com.xiaomi.aicr:cognitionService` 崩溃记录，尚未调查原因，Android 全部应用的状态仍需分别验证。

## 3. 与 userdata 暂存操作的关系

此前的 `tools/stage-system.sh` 多次把 2,492,227,584 字节的 `system.apfs` 直接写入 userdata 尾部，起始偏移为 245,412,089,856。脚本没有检查该区间的文件系统块分配情况。文件系统仍有可用空间、目标位于分区尾部、Android 能开机，都不足以确认这段区间可以覆盖。

本次未取得损坏文件与上述区间的物理 extent 对照，缓存损坏的具体原因仍未确认。后续调试应通过 loader 的 USB ramdisk 接口把系统盘写入 RAM。向裸分区写测试镜像之前，必须先确认目标区间的所有权及恢复方法；已挂载的 userdata 尾部不能作为默认暂存区。

`annibale-backup/20261023-2100/userdata-tail-2492227584.bin` 的创建时间晚于第一次暂存操作。它保存的是备份时刻的尾部内容，不能恢复更早已被覆盖的数据。Android 继续运行后，文件系统状态可能再次变化，整段写回旧尾部备份需要重新评估。

## 4. loader 调试中的相关问题

- 主机的 Android/LK 序列号是 `${ANDROID_SERIAL}`，loader 的 USB 序列号是 `xnuloader`，应分别指定目标。
- 日志读取需要 `fastboot -s xnuloader oem log` 后接 `fastboot -s xnuloader get_staged <文件>`。截图同样先 `oem screenshot`，再 `get_staged`；当前主机 fastboot 的 CLI 没有 `upload` 子命令。
- `oem logwrite` 在缺少 logdump 分区的设备上会覆盖 `boot_a` 开头。代码仅在本次 `flush_log()` 调用期间允许写入，随后立即关闭；后续内核日志不会因此自动写入 `boot_a`。本机已实测能通过 USB 读取日志，调试过程使用 USB 通道。
- 内核在 loader 所在 CPU 上运行期间，loader 无法处理 USB 命令。主机命令超时需要结合 USB 枚举和后续状态判断，不能直接记录成「设备已重启」或「内核已退出」。本次 `bootcpu=1 cpus=1` 已验证可让 loader 保留 USB 通道。
- 设备树记录的显示模式为 `1156×2510`，旧固件的 SimpleFb 配置为 `1440×3168`。GOP 返回的是固件配置，实际面板显示仍需真机确认。
