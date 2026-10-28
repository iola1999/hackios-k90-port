# 桌面首次启动成功（2026-10-25）

新 loader 在真机上带完整 iOS 用户态启动成功，桌面渲染出来并通过 USB 取回截图。这是新 loader 世代（`build-id` `4f6ab13b…`）第一次走到用户态，也是首次在该 loader 上用 RAM 系统盘跑起桌面。画面来自软件绘制，GPU 未参与。设备序列号掩码为 `519e…a70`。

## 1. 做法与顺序

沿用 [playbook](../plan/device-test-playbook.md) §4：运行前只读确认 → `oem ramdisk` 提升下载上限 → 传 2.3 GB 系统盘 → 传 payload → `oem run` → 运行中取一轮实时日志 → 查屏幕几何与截图。

与上一轮 r5 的两处改动：根盘改用完整的 `hackios-xnu-kernel/userland/system.apfs`（2,492,227,584 B），上传手工走 `oem ramdisk` 加 `stage`、上限 300 秒（`stage-system.sh` 内 `stage` 的超时固定 180 秒，2.3 GB 上传实测 62.3 秒，余量不大）；日志只取一轮，按 r5 的实测两轮内容相同。

## 2. 运行身份

| 项 | 值 |
|---|---|
| 构建提交 | `4f6ab13bdbab08314745e04ad77fcc8d6967e1d6` |
| loader | `5fccaa8f4d86e992e64e3fa72703d2c8ad05d840d235d000bf5819696312974c` |
| payload | `handoff-desktop-r1.bin`，28,261,832 B，`497a624220d655425ecf278b8da0df7c87b165e9398330529695ceec3a22b6fb` |
| 内核 | `2a5d52891dcb9d55a88f5fb03db650b57e547675ba12c9998168cf7d0750392b`，19,193,072 B |
| 根盘 | `userland/system.apfs`，2,492,227,584 B，`a3ab9dce59e527b65feb4ef161680f094087da26e79aabdddfa6e9ac9ee10b71` |
| epoch | `1792872968` |
| cmdline | `debug=0x8 rd=md0 battery_shared_pa=0x00000000cf9de000 debug=0x10e cpus=2 bootcpu=7 small_cores_after=0 epoch=1792872968 touchscreen=2 buttons=1 gl=1 battery=1` |

`battery_shared_pa` 由 loader 运行前注入，装配期 cmdline 中没有这一项。原始产物见 `evidence/2026-10-25-desktop-first-boot/MANIFEST.md`。

## 3. 判据结果

| 判据 | 结果 | 依据 |
|---|---|---|
| `result` 是否转 `returned` | 未转 | +30 至 +130 秒六次均为 `running 0 0`；+161 秒取截图时仍在运行；之后命令通道静默 |
| `BSD root: md0` 与 APFS 挂载 | 通过 | `BSD root: md0, major 1, minor 0`；`volume 0 "System"` 45,146 文件、16,548 目录；另有 `redwood` 卷 |
| `launchd` 是否成功 | 通过 | `$ exec /sbin/launchd.ios`、`hello from launchd.ios.1`、`Darwin Bootstrapper Version 7.0.0`、`Restore environment starting`；`backboardd` 走到 `spawning` |
| 屏幕是否出画面 | 通过 | `screen: 1156 2510 4624`；截图 11,606,240 B 与几何吻合；2,901,560 像素 100% 非零；解出的图像是 iOS 主屏 |
| payload ramdisk 是否成为 md1 | 通过 | `resident image ... it is the root (md0), the payload ramdisk is md1`；`/dev/md1`、`/dev/rmd1` 可见；`rd=md0` 在 boot-args 中 |

`oem sound` 在运行期被拒：`FAILED (remote: 'a kernel is running (oem stop ends it)')`，这一项没有数据。

截图内容：状态栏 `4:18`、电量 `79%`，图标网格含 Weather、Stocks、Find My、Books、iTunes Store、Fitness、Mail、Contacts、Translate、Files、News、Utilities、Freeform、Tips、Maps，底部 Dock 四个图标，页面点与壁纸渐变正常。图像见 `evidence/2026-10-25-desktop-first-boot/screen-t155.png`。

## 4. 渲染路径：软件绘制

`gl=1` 这一轮走的是软件渲染，日志里有三处直接依据：

```
redwood-gl: 8 of 8 methods of EAGLContext are ours; OpenGL ES by Mesa, off-screen (OSMesa)
redwood-gl: an OpenGL ES 3 context for CoreAnimation, by Mesa, off-screen (OSMesa): OpenGL ES 3.1 Mesa 26.2.5; softpipe; shaders OpenGL ES GLSL ES 3.10
redwood-gl: asked for string 0x1f01: softpipe
```

`0x1f01` 是 `GL_RENDERER`，返回 `softpipe`。CoreAnimation 的绘制请求由 `/redwood/lib/libredwood-gl.dylib` 与 `/redwood/lib/libOSMesa.8.dylib` 接管，离屏合成后写入帧缓冲。

GPU 侧没有任何活动：`adreno8` 在本轮日志中出现 0 次，`IOGPU`、`AGX` 同样 0 次。该 payload 的 cmdline 不含 `adreno8*` 参数，GPU 初始化路径没有被调用。

Metal 只出现在文件清单里（`/redwood/lib/RedwoodMetal.bundle`、`libredwoodmetal.dylib`、`/redwood/bin/metal_*`）与 `com.apple.MTLCompilerService` 的端点创建行，日志中没有 Metal 设备创建成功的记录。

这一轮的成果是「画面经由 CoreAnimation 走完整绘制链路画出来」，硬件加速仍未启用。

## 5. 与 2026-10-23 桌面轮的差异

| 项 | 2026-10-23 | 本轮 |
|---|---|---|
| 驻留 loader | `handoff-loader-v3.img` | 新 loader，`version 0.5`，`build-id 4f6ab13b…`（40 位完整应答） |
| 内核 | `handoff-mach-affinity`，19,192,112 B，`8df83d8234dcfb61fc9aae907d167dc036bedd592ff60801227e29c09bd2aedd` | 19,193,072 B，`2a5d5289…`，比 10-23 多 960 B |
| 结束方式 | 首轮用 `loader_return_after=300`，读到 `returned 1361841 0` | 无 `loader_return_after`，`result` 停在 `running`，+161 秒后命令通道静默 |
| 渲染路径 | Mesa 26.2.5 `softpipe`，由 CPU 绘制 | 同为 `softpipe`，GPU 未参与 |
| 画面 | 1156 × 2510、stride 4624 | 1156 × 2510、stride 4624 |

两轮的画面参数一致。本轮的差异集中在 loader 世代与结束方式：新 loader 的 `build-id` 能完整应答，内核不设时限时保持运行，取完截图后命令通道不再应答，需要物理重启才能回到 loader。

## 6. 设备状态

设备停在 `result: running`，没有 reboot。恢复方式是物理断电重启进 LK，再由 `reboot` 按 boot_a 的 M_full 回到 loader。

### 运行期变慢（观察）

用户报告：桌面出现后可以操作，但整体很慢，时钟显示比真实时间落后约 3 至 4 分钟，触摸有响应、延迟很大。

主机的观测与此一致，并且纠正了两个早期判断：

| 时刻 | 观测 |
|---|---|
| 20:19:15Z（+0 秒） | `oem run` 应答 `OKAY` |
| +30 至 +130 秒 | `result` 六次均为 `running 0 0`，单次应答 0.02 至 0.05 秒 |
| +161 秒（20:21:56Z） | `getvar screen` 与 `oem screenshot`、`get_staged` 成功，取回完整帧缓冲 |
| +165 秒起 | `getvar` 三次在 8 至 15 秒内无输出 |
| 20:31:04Z 起 | 用 60 至 120 秒的上限重问，`getvar product`、`getvar result`、`getvar screen`、`oem log`、`get_staged`、`oem screenshot` 全部在 0.0 至 0.03 秒内应答 |

20:31 之后取得的日志共 1,311,636 字节，最新的用户态行一直在推进：SpringBoard、wifid、backboardd 与电池驱动都在持续输出，`redwood-gl` 的帧计数从 460 涨到 580 以上。系统在运行，没有冻结。「命令通道静默」这一判断由 8 至 15 秒的短上限造成，重测不成立。

时钟读数与时钟来源：

| 主机时刻（+0800） | 屏幕上的时钟 |
|---|---|
| 04:21:56 | 4:18 |
| 04:34:48 | 4:31 |
| 04:35:48 | 4:32 |

两次相隔 60 秒的截图显示时钟推进 1 分钟，走速与真实时间相当（分钟分辨率，误差上限约每分钟 1 分钟）。落后量约 3 分 48 秒，来源是 payload 的 `epoch=1792872968`，它等于 04:16:08，而 `oem run` 发生在 04:19:15，固定落后 3 分 07 秒，其余为开机耗时与运行期的小幅偏差。

慢的来源在日志里可读：

```
redwood-gl: frame 460: 28 GL calls, 4 draws, 8 triangles, 1 clears; ... 104214 us (10170 handing on, 1 waiting, 4934 copying out)
redwood: CoreAnimation's OpenGL ES renderer has no function 40 ("sb3"): what needs it is not drawn
```

单帧耗时在 60 至 140 毫秒之间，并出现 10.2 秒与 11.3 秒的长停顿。绘制由软件完成，见 §4。时钟落后与画面慢是两件独立的事：前者是 `epoch` 固定偏移，后者是软件绘制的单帧开销与长停顿。

## 7. 产物

- 原始产物与清单：`evidence/2026-10-25-desktop-first-boot/`（`desktop-screen.raw`、`screen-t155.png`、`live-t10.log`、`MANIFEST.md`，Git 忽略）
- 前置轮次记录：[GPU 预检 r5 运行记录](2026-10-25-gpu-preflight-r5.md)、[槽位引导阶梯记录](2026-10-25-slot-boot-ladder.md)
- 手册：[device-test-playbook.md](../plan/device-test-playbook.md) §4、§5