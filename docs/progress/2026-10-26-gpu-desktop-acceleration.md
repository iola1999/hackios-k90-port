# A830 GPU 加速桌面与显示修复（2026-10-25～26）

本记录接续[恢复审查记录](2026-10-25-gpu-resume-review.md)。目标为在 REDMI K90 上启动带 GPU 图形加速的 iOS 16.5 桌面。原始日志、截图和产物清单保存在 Git 忽略的 `docs/progress/evidence/2026-10-25-codex-gpu-resume/`，下文用目录名指代各轮运行。

## 1. 结论

- A830 初始化阶段 14～23 全部通过，`RedwoodGPU` 注册成功。CoreAnimation 通过 `eagl.c → OSMesa → freedreno` 在 GPU 上绘制，日志中的渲染器为「OpenGL ES 3.2 Mesa 26.2.5; Adreno (TM) 830」。
- 触摸（`touchscreen=2`）与 GPU 路径可以同时工作。用户在设备上确认滑动、翻页和控制中心可用，交互比 softpipe 时明显流畅。
- 主屏标签旁的闪烁色块和控制中心背景异常已修复：Mesa 在 a8xx 上读帧缓冲前补充 CCHE 失效（userland `94e4c97`）。修复前后各约 95 张自动截图，异常截图数由 31 张降为 0 张。
- 帧率见第 7 节。双核运行（`cpus=2 bootcpu=7 small_cores_after=0`）、向量化显示缩放、SCMI 大核调频后，显示驱动每帧从约 21 ms 降到 1.3～2.8 ms。GPU 提交改为最多 4 个排队后，控制中心下拉主动画从 40 帧/秒提高到 54 帧/秒（2026-10-28 按修正后的手势口径重算，见第 7.6 节）；新建 GPU 缓冲区从每个约 2.1 ms 降到约 0.2 ms（第 7.8 节）、提交路径的健康检查改为 1 ms 内复用（第 7.9 节）后，控制中心下拉为 58.7 帧/秒，帧间隔 p95 为 17.5 ms，左右翻页为 58.8／60.8 帧/秒，整轮 78% 的帧间隔低于 18 ms（原来单核时约 80% 落在 26～35 ms）。GPU 在 160 MHz 下只有 12%～15% 的时间忙碌，剩余帧时间在窗口服务器的 CPU 侧。
- CPU 不再开机固定在约 3 GHz：`cpufreq=1` 按负载调频，83%～85% 的时间在最低档 1017 MHz，大核达到 70 °C 时降到最低档，真机上触发过（第 7.2 节）。
- GPU 档位随负载和触摸在 160～342 MHz 之间切换（内核 `ffca661`）：手势期间升到 342 MHz，静止时停在 160 MHz，每帧绘制 p50 从 13.2 ms 降到 9.6 ms，控制中心 58.8 帧/秒；GPU 达到 70 °C 时降回 160 MHz，真机尚未触发。GPU 工作时间随档位按频率比变化，功耗没有测量（第 7.10 节）。Turnip 在 iOS 上通过设备枚举、传输、计算和三角形绘制读回（第 7.10 节）。其他风险见第 8 节。

## 2. RAW131 复位与直接 ring CP_INIT 超时的根因

HWSCHED 的 RAW131（H2F CP_INIT）复位和普通 HFI 直接 ring 的 CP_INIT 超时是同一个原因：LPAC 微引擎使用的 SMMU stream 没有路由。

- 直接 ring 超时后读取 `CP_SQE_STAT`，索引 0 为 SQE 的 PC：BR 停在 `0xe3`，BV 停在 `0x4a`。对照 `gen80000_sqe.fw`（版本 `01500077`）的反汇编，两处都在启动屏障里循环读 `THREAD_SYNC`。
- `THREAD_SYNC` 初值为 `0x7`，BR、BV、LPAC 各自清掉 bit 0、bit 1、bit 2 后才继续执行。LPAC 一直没有清 bit 2。
- 内核按厂商值写 `CP_SMMU_STREAM_ID_LPAC = 0x101`，LPAC 取微码时使用 SID 1。设备树中 `gfx3d_user` 为 SID 0、`gfx3d_lpac` 为 SID 1、`gfx3d_secure` 为 SID 2；当时 SMMU 只为 SID 0（GPU）和 SID 5（GMU）建了 SMR／S2CR。
- 修复为 `adreno8_space_route()`：在 match 3 写入 SID 1 的 SMR，S2CR 指向 GPU context 0（Linux msm 也把 SID 0 和 1 放在同一个 domain）。写入顺序为先置 fault、写 SMR、读回，再切到 translate，并检查 context 无故障；任一步失败都把该 slot 恢复为 fault（内核 `a10067e`，主机测试 `b7d3b95`）。

修复后，直接 ring 的 CP_INIT 被消费且空闲（BR／BV 读指针均为 10）；HWSCHED 的 CP_INIT 收到应答；随后 zap（PAS 13）、退出 secure、scratch 写回、标准 context 两条 IB 的 SOP／EOP 均通过。

## 3. 从阶段 23 到桌面的其他修改

| 问题 | 处理 | 提交 |
|---|---|---|
| `adreno8_gmuclk=2` 只允许阶段 5 和 17，阶段 23 被拒 | 准入改为阶段 5 或 ≥17，RPMh 与时钟测试同步 | 内核 `4d2aa99` |
| 阶段 23 静默失败 | 服务注册各拒绝分支补日志；查出 `redwood_platform_is_annibale()` 中 GIC 重分发器地址写错，改为 `0x15C80000`（GICR 基址 `0x16080000`） | 内核 `8eebac5`、`33808b4` |
| 阶段 23 校验 CB0 寄存器失败 | GPU 运行后 CB0 的 TCR 读回 EPD1（bit 23）为 0；TTBR1 为 0 且所有 IOVA 低于 39 位 TTBR0 范围，GPU 空间容忍该值并只报告一次 | 内核 `4d93f52` |
| 一轮中阶段 22 失败，Mesa 退回 softpipe | 第 2 条测试 IB 的 EOP 已写回、GPU 已空闲时，GMU 队列读指针尚未追上写指针。改为最多等待 20 ms，超时打印读写指针 | 内核 `3d9c53f` |

直接 ring 超时诊断（`aef3da7`、`2d75c8f`）保留在 `adreno8_gpu.c`，只在超时路径运行。

## 4. 桌面运行记录

| 运行目录 | 配置 | 结果 |
|---|---|---|
| `kernel-tcr-epd1-s23-desktop` | `adreno8_gmuclk=2`，`touchscreen=0` | 首次 GPU 绘制桌面，无 SMMU 故障；标签旁有蓝色色块 |
| `kernel-tcr-epd1-s23-desktop-xo-touch` | XO GMU 时钟，`touchscreen=2` | 触摸可用；用户拍摄的视频中控制中心背景为纯色，有阶梯形三角块 |
| `kernel-queue-wait-s23-desktop-noprefetch` | `FD_DEV_FEATURES=has_fs_tex_prefetch=0` | 色块仍在，控制中心背景变为纯黑 |
| `kernel-queue-wait-s23-desktop-sysmem` | `FD_MESA_DEBUG=sysmem` | 主屏蓝色色块消失；控制中心有模糊背景，但叠有蓝色与黑色阶梯块 |
| `kernel-queue-wait-s23-desktop-noubwc` | `FD_MESA_DEBUG=noubwc` | 色块仍在；控制中心第一次纯黑，第二次为模糊背景 |
| `kernel-queue-wait-s23-auto-default` | 无人值守脚本，原 Mesa | 94 张截图中 31 张有异常 |
| `kernel-queue-wait-s23-auto-fbread1` | 无人值守脚本，Mesa 补 CCHE 失效 | 97 张截图中 0 张有异常；用户目视确认无闪烁、控制中心正常 |
| `kernel-queue-wait-s23-auto-ccche` | 无人值守脚本，正式 Mesa（去掉实验开关） | 95 张截图中 0 张有异常 |

`kernel-tcr-epd1-s23-desktop-noubwc` 一轮因阶段 22 失败退回 softpipe，结果作废，第 3 节已修复其原因。环境变量通过 `eagl.c` 的 `glenv=NAME=VALUE` 启动参数传给 Mesa。

## 5. 显示异常分析

下列特征和推算确定了色块的来源。

- 色块在源图坐标中为 16×4 像素并按 16×4 对齐，连续 4 行形状相同。CPU 缓存行只覆盖一行 16 像素，因此排除 CPU 侧缓存一致性。
- 色块颜色 (9,126,201) 与屏幕顶部状态栏一带的壁纸颜色一致；用户在闪烁区域中看到过右上角的电池图标。
- freedreno 的分 bin 算法：A830 的 12 MiB GMEM 扣除 6 个 CCU 的缓存区后剩约 10.27 MB，1125×2436×4 B 需要两个 bin，`bin_h` 按 32 对齐为 1248。截图中色块从源图第 1248 行开始，所以下半个 bin 的部分块显示的是上半个 bin 同一相对位置的内容。
- 色块集中在图标标签和控制中心材质处。CoreAnimation 在这些位置使用 framebuffer fetch。上游 hackios 在 A642L 上遇到过同类问题：读帧缓冲的第一个三角形读到另一个 tile 的像素，修法是在第一个读帧缓冲的 draw 前清理 CCU 并失效 UCHE（`fd6_draw.cc` 中的 Darwin 补丁）。
- A8xx 在纹理读取路径上多了一级 CCHE。Mesa 26.2.5 在 a8xx 的 sysmem 收尾和快速清除处都会发 `CP_CCHE_INVALIDATE`，上述补丁位置没有发。

修复方法是在同一位置对 `CHIP >= A8XX` 追加 `FD6_INVALIDATE_CCHE`。改动写入 `tools/mesa/rebase-26/0003-restore-osmesa-26.x-drift-adaptations.patch`（userland `94e4c97`）。内核仓的 `tools/mesa` 为 Git 忽略的副本，已同步。正式小根盘为 `out/handoff-ui-ccche.apfs`，由 `device-zap-root-1` 的根目录替换 `lib/libOSMesa.8.dylib` 后重新打包。

下表为修复前后的性能（无人值守脚本、`cpus=1`，统计帧数不少于 20 的 5 秒窗口）。

| 运行 | 显示帧率 | 显示驱动每帧 | 等 GPU 每帧 | GL 帧耗时 p50／p90 |
|---|---|---|---|---|
| `auto-default` | 9.2 帧/秒 | 21.5 ms | 1.87 ms | 3.9 ms／32.8 ms |
| `auto-fbread1` | 9.5 帧/秒 | 20.5 ms | 1.87 ms | 3.9 ms／31.1 ms |
| `auto-ccche` | 9.1 帧/秒 | 21.1 ms | 1.87 ms | 3.9 ms／38.1 ms |

三轮差异在采样波动范围内，CCHE 失效没有带来可测的性能下降。`auto-fbread1` 使用带实验开关 `FD_FB_READ_BARRIER` 的库（默认值等同正式修复），`auto-ccche` 使用正式库。

## 6. 无人值守测试方法

1. 小根盘的 `etc/rc.jobs` 改为 `rwtouch` 脚本：32 s 滑动解锁，约 120 s 起循环 8 轮，每轮下拉控制中心停 8 s、按 home 收起，再左右翻页。init 每行最多 63 个参数，每轮单独一行。打包命令与 `device-zap-root-1/manifest.json` 记录的 `mkapfs.py` 参数相同。
2. `run-auto.py`：每 20 s 拉一次日志，100 s 起每 3 s 截一次全分辨率图。
3. `run-queue.sh`：依次运行多个 payload 目录；USB 重启后若退回 Android B 槽，调用 `recover-loader.py` 切回 loader A 槽，loader 不处于 idle 时停止队列。
4. 截图用 ffmpeg 转为 PNG 并拼接缩略图；按第 1286～1400 行（面板坐标）统计状态栏蓝色像素，判断 bin 边界处的异常。

脚本均在上述 evidence 目录中。A 槽重试次数用尽后退回 Android B 槽的情况本轮出现过两次，均由恢复脚本自动处理，没有人工按键。

## 7. 帧率：CPU 调频、显示缩放与 GPU 提交

### 7.1 CPU 频率

- SM8750 的 CPU 时钟和电压由 CPUCP 固件管理，操作系统通过 SCMI 性能协议（0x13）请求档位。通道为共享内存 `0x17b4e000`，门铃为 `0x17830000 + 0x104`（原厂设备树 `mmio-sram@0x17b4e000`、`qcom,cpucp@0x17830000`；Linux `arm_scmi/shmem.c`、`qcom-cpucp-mbox.c`）。`redwood_cpufreq.c` 原有的 EPSS（`0x18591000`）和 RSC（`0x18220000`）地址属于旧设备，SM8750 原厂设备树在这两处没有设备，annibale 不再走该路径。
- 固件报告协议 4.0、两个性能域，都使用按索引设置档位的模式（属性 bit 25）：`NCC0` 为簇 0，16 档，384～3532 MHz，启动时在第 8 档（1996 MHz）；`NCC1` 为两颗大核，16 档，1017～4320 MHz，启动时在第 0 档（1017.6 MHz）。
- `NCC1` 给出的可持续频率为 4089.6 MHz，可持续档索引却是 15，对应 4320 MHz。内核因此按频率选档：取不超过可持续频率、也不超过启动参数 `cpufreq_mhz` 的最高一档。
- 内核的两颗核心都在 `NCC1`。启动时依赖链加法测得 1017 MHz；`cpufreq_mhz=2500` 选第 6 档后测得 2437 MHz，`cpufreq_mhz=3100` 选第 9 档后测得 3070 MHz。
- 启动参数：`cpufreq=2` 只报告档位、温度和加法链速度；`cpufreq=1` 按负载调频并启用温控（第 7.2 节）；`cpufreq=3` 固定在上限档，同样受温控约束，用于对照。

### 7.2 按负载调频与温控

开机后不再固定在约 3 GHz，改为按负载选档。iOS 的 CPU 调频由闭源的 CLPC 内核扩展决定，开源 XNU 只有它注册回调用的接口（`sched_perfcontrol_register_callbacks`），iOS 16.5 中没有可以直接接上的调频策略，因此规则写在本项目内核里（`bsd/dev/annibale_cpufreq.c`，内核 `95b5606`）：

- 每 50 ms 取本域最忙的一颗核心，按 Linux schedutil 的方式选档：目标频率为当前频率 × 忙碌比例 ÷ 0.8，取不低于目标的最低一档。需要升档时立即升，降档要求持续 200 ms 后才执行。忙碌比例由 `ml_cpu_idle_time()` 的空闲时间累计算出。
- 触摸后 300 ms 内不低于 2438 MHz，触摸事件立即唤醒调频线程。
- 上限取 `cpufreq_mhz`（默认 3100）和固件可持续频率中较低的一档。
- 本簇任一传感器达到 70 °C 时降到最低档 1017 MHz，全部低于 60 °C 后恢复按负载选档；没有有效读数时停在最低档。阈值远低于原厂的 95 °C；用户要求测试期间不让机器接近 90 °C。
- 每 30 s 写一行日志：各档时间占比、换档次数、每次 SCMI 请求耗时、达到 70 °C 的次数（内核 `6d5cb85` 起）和最高温度。

真机结果：

- 调频的各轮中，84%～93% 的时间在 1017 MHz，帧间隔低于 18 ms 的比例与固定 3.07 GHz 相同（第 7.7 节）。
- 温控在真机上触发过。`kernel-quiet-s23-auto-gov-log0` 启动后桌面加载的 30 s 内，大核有 41% 的时间在 3072 MHz，最高读数 72.9 °C，下一个 30 s 窗口最高 71.7 °C，之后各窗口最高 48～55 °C。`kernel-inflight-s23-auto-if4` 在同一阶段的两个窗口分别有 22 次和 13 次达到 70 °C，最高 73.6 °C；之后各窗口为 0 次，最高 50.8～53.1 °C。
- 大核在 3 GHz 附近升温很快，30 s 内可以在 60 °C 与 70 °C 之间往返 20 多次。持续高负载下的温度还没有测。

### 7.3 显示缩放

显示驱动每帧把 1125×2436 双线性缩放到面板的 1156×2510。缩放循环移到 `MiniFramebufferScale.h`，四个面板像素对应四个相邻源像素时用向量代码一次处理四个，其余用原标量代码。`tools/test-fb-scale.py` 在主机上逐像素对比新旧实现（含 ASan 与精确长度的行缓冲），K90、`fbscale=2`、redwood 面板和非整数图层都一致。

### 7.4 设备树遍历竞态

两轮带 SCMI 代码的测试分别在运行约 4～6 分钟后 panic：「Device tree pointer outside of device tree region」，调用链为 `IOMobileFramebuffer::presenter()` → `redwood_gpu_ready()` → `redwood_platform_is_annibale()` → `pe_arm_get_soc_base_phys()` → `find_entry()`。XNU 的 `find_entry()` 用静态变量 `startingP` 记录遍历位置，多个线程同时调用会互相改写；GPU 路径在每帧和每次提交时都调用 `redwood_platform_is_annibale()`。

修复分两处：两个平台判断只在 `redwood_input_init()` 中计算一次（内核 `2249d0b`）；`find_entry()` 的遍历位置改为由调用方传入，`SecureDTFindEntry()` 每次调用使用自己的局部变量（内核 `940e513`，补丁 `xnu/patches/69a-pexpert%gen%device_tree.c.patch`），其他调用方并发查找时也不再互相改写。修复后的各轮都运行满 420 s，没有 panic。

### 7.5 出帧时间线

`touch_lat=1` 时，SpringBoard 主循环的每一轮（`tl: a`）、窗口服务器每帧的绘制（`tl: g`）、交给显示驱动（`tl: s`）和写入面板内存（`tl: v`）都带时间戳。`kernel-quiet-s23-auto-timeline`（内核 `150b9c8`）的结果：

- 翻页动画本身接近 60 帧/秒：从首帧起的 600 ms 内，帧间隔 p50 16.3 ms，超过 18 ms 的占 11%，平均 53～54 帧/秒。
- 动画结束后的低频出帧来自 CoreAnimation 自己的动画：第 1 页的时钟图标秒针每 100 ms 出一帧；翻到第 2 页后每 33.3 ms 出一帧，每帧 15 次 draw、绘制 1.5～3 ms，来源未确认。`tools/frames.py` 统计手势后 2.5 s 内的全部帧，所以向左翻页的 p50 为 32.5 ms。这两种间隔与绘制耗时无关。
- 控制中心下拉的主动画（首帧起 1.8 s）只有 31 帧/秒，44% 的帧间隔超过 18 ms。窗口服务器每帧约 241 次 draw，绘制 p50 21.5 ms，其中 15～20 ms 花在 glFlush 内（`eagl.c` 每 20 帧一行的「handing on」）。`gpu_log=1` 的 `kernel-quiet-s23-auto-gov-log1` 显示，这一阶段每帧约 10 次提交，相邻提交间隔 2～3.6 ms。
- 原因在内核提交路径：`adreno8_context_submit()` 排队新提交前，先等上一次提交在 GPU 上执行完，等待期间持有 `gGPULock`。Mesa 在 glFlush 时按渲染 pass 逐个提交，控制中心的模糊背景有多个 pass，一帧的 glFlush 因此逐个等待每个 pass 在 160 MHz 的 GPU 上执行完。
- SpringBoard 主循环每轮都在 8 ms 以内，慢帧与它无关。
- 连续出帧时，帧在显示驱动中等下一个刷新节拍约 14 ms（`tl: v` 的 ready 到 shown）。从 `MiniIOMobileFramebuffer.cpp` 的 `show()` 看，`fb_queue=2` 时后一帧在前一帧复制完成后才被取出，节拍调整以取出时间为参照，这段等待因此停在约一个刷新周期减去复制时间，达不到设计的 6 ms，触摸到上屏的延迟多出约一帧。

### 7.6 GPU 提交排队

内核 `968ac2d` 允许最多 `adreno8_inflight`（默认 4，取值 1～8）个提交同时排在 GPU 上下文队列中，新提交只在已有这么多个未完成时等最早的一个。上下文队列写满时等 GMU 读走，超过 200 ms 才判定失败，原来是立即判定失败。`adreno8_inflight=1` 恢复逐个等待。`tools/test-adreno8-context.py` 覆盖排队深度、取值越界、写满后等待和超时，两处变异都能被测试发现。

同一内核、同一根盘的对照（`touch_lat=1`，8 轮操作；主动画指控制中心首帧起 1.8 s、翻页首帧起 600 ms，统计脚本为 `tools/k90auto/gestures.py`）：

| 运行 | `adreno8_inflight` | 控制中心主动画 | 控制中心帧间隔 > 18 ms | 控制中心每帧绘制 p50／p95 | 翻页主动画（左／右） | 整轮帧间隔 < 18 ms | GL 帧 p90 |
|---|---|---|---|---|---|---|---|
| `kernel-inflight-s23-auto-if1` | 1 | 40.3 帧/秒 | 44% | 21.7／94.8 ms | 54.3／57.1 帧/秒 | 60% | 22.0 ms |
| `kernel-inflight-s23-auto-if4` | 4 | 53.9 帧/秒 | 7% | 12.1／27.5 ms | 53.9／55.5 帧/秒 | 74% | 12.8 ms |

- 控制中心稳定阶段每帧约 260 次 draw，绘制 12～14 ms，按 60 帧/秒出帧。翻页本来就接近 60 帧/秒，排队前后没有变化。
- 两轮都运行满 420 s，没有 panic，各 97 张截图都没有色块。
- 改动前的 `kernel-quiet-s23-auto-timeline`（内核 `150b9c8`）与 `if1` 一致：控制中心 40.8 帧/秒、40% 超过 18 ms，整轮 62% 低于 18 ms。
- 2026-10-28 更正本节的帧率与因果。`gestures.py` 原来会把 1.8 秒窗口里不小于 90 ms 的空档一起算进帧率，而这两轮的下拉窗口里各有 22～24 个这样的空档（下拉结束后动画已停，窗口还没结束），把帧率摊低：`if1` 31.4→40.3、`if4` 39.1→53.9、`quiet-timeline` 31.1→40.8。所以「提交排队把控制中心从 31 帧/秒提高到 39」这句缩成 40→54，省下的时间仍然成立，只是起点没有当年记的那么低。同表「控制中心帧间隔 > 18 ms」一列按同一算法重算后，`if1` 是 44%、`if4` 是 7%。
- 剩余的慢帧集中在控制中心刚下拉的前 0.5 s：每帧绘制 60～250 ms。这段时间每 5 s 新建 300～600 个 GPU 缓冲区，平均每个约 2 ms（`RedwoodGPU: buffers:` 日志行），耗时组成和修改见第 7.8 节。

2026-10-28 说明：本节的「帧间隔 < 18 ms／18～35 ms／更长」三列由 `summary.py` 的窗口口径给出，其中一部分轮次的合并受当时的日志环缺陷影响（见[iOS 26 性能差距分析](../analysis/2026-10-28-ios26-perf-gap.md)第 1.1 节）。合并修好后重算，`kernel-publish-s23-auto-lw` 的这一列是 76%、19%、5%（本节记 76%、20%、5%），逐次下拉的帧率与上面第 7.6 节的更正一致。要按新口径复核整张表时以那份文档第 3.1 节的十轮为准。

### 7.7 测量

无人值守脚本，`cpus=2 bootcpu=7 small_cores_after=0 fb_threads=2`。帧间隔只统计帧数不少于 20 的 5 秒窗口（显示驱动每 5 s 一行的直方图），包含手势后 CoreAnimation 低频出帧的间隔（第 7.5 节）。「最低档占比」为整轮 30 s 报告中 1017 MHz 的时间占比。

| 运行 | 内核 | 缩放 | 大核频率 | 显示驱动每帧 | GL 帧 p50／p90 | 帧间隔 < 18 ms | 18～35 ms | 更长 | 大核温度 |
|---|---|---|---|---|---|---|---|---|---|
| `kernel-queue-wait-s23-auto-ccche-cpus2-fbt2` | | 标量 | 1017 MHz | 11.4 ms | 3.9／24.6 ms | 36% | 50% | 15% | 未记录 |
| `kernel-scmi-neon-s23-auto-cpufreq2` | | 向量 | 1017 MHz | 3.56 ms | 3.9／24.3 ms | 47% | 42% | 11% | 30 s 采样最高 43.0 °C |
| `kernel-dtcache-s23-auto-2400` | `2249d0b` | 向量 | 固定 2437 MHz | 1.65 ms | 2.4／18.6 ms | 63% | 30% | 7% | 30 s 采样最高 41.5 °C，温控未触发 |
| `kernel-dtcache-s23-auto-3072` | `2249d0b` | 向量 | 固定 3070 MHz | 1.32 ms | 2.4／14.3 ms | 63% | 31% | 5% | 30 s 采样最高 44.9 °C；温控多次触发，读数 70.2～73.6 °C |
| `kernel-governor-s23-auto-gov` | `95b5606` | 向量 | 调频，最低档占比 85% | 2.82 ms | 3.8／22.5 ms | 62% | 31% | 7% | 最高 72.1 °C（启动阶段） |
| `kernel-quiet-s23-auto-gov-log1` | `150b9c8` | 向量 | 调频，83% | 2.91 ms | 3.8／22.2 ms | 61% | 32% | 6% | 最高 72.5 °C（启动阶段） |
| `kernel-quiet-s23-auto-gov-log0` | `150b9c8` | 向量 | 调频，84% | 2.85 ms | 3.8／20.6 ms | 62% | 31% | 8% | 最高 72.9 °C（启动阶段） |
| `kernel-inflight-s23-auto-if1` | `968ac2d` | 向量 | 调频，83% | 2.91 ms | 3.8／22.0 ms | 60% | 33% | 6% | 最高 72.5 °C（启动阶段） |
| `kernel-inflight-s23-auto-if4` | `968ac2d` | 向量 | 调频，84% | 2.80 ms | 3.3／12.8 ms | 74% | 20% | 6% | 最高 73.6 °C（启动阶段） |
| `kernel-lockwait3-s23-auto-lw` | `f1f2665` | 向量 | 调频，84% | 2.77 ms | 3.7／11.8 ms | 72% | 22% | 6% | 最高 71.7 °C（启动阶段） |
| `kernel-iova-s23-auto-lw` | `19cb049` | 向量 | 调频，84% | 2.78 ms | 3.7／13.2 ms | 73% | 22% | 5% | 最高 72.5 °C（启动阶段） |
| `kernel-publish-s23-auto-lw` | `d4df543` | 向量 | 调频，82% | 2.73 ms | 3.7／12.9 ms | 76% | 20% | 5% | 最高 72.9 °C（启动阶段），之后 48～61 °C |

- `kernel-scmi-neon-s23-auto-cpufreq2` 因第 7.4 节的 panic 只采样了 261 s；其余各轮都运行满 420 s，没有 panic，截图都没有色块（`band.py`，每轮 93～97 张）。
- 2249d0b 的 30 s 报告只采样当时的温度，两轮固定频率的「最高温度」偏低；温控日志显示 3.07 GHz 一轮多次达到 70 °C。`95b5606` 起 30 s 报告取调频线程每 50 ms 读数中的最高值。
- 调频后显示驱动每帧从 1.3 ms 增加到约 2.8 ms（复制面板内存时大核多在低档），帧间隔分布与固定 3.07 GHz 相同。
- `gpu_log=1` 与 `gpu_log=0` 两轮的帧间隔分布相同，GPU 日志不影响帧率。
- 帧间隔 < 18 ms 的比例从 62% 提高到 74% 来自 GPU 提交排队（第 7.6 节）。后三轮的变化集中在控制中心下拉，整轮分布变化不大，按手势的统计见第 7.8 节。

### 7.8 新建 GPU 缓冲区

第 7.6 节的对照之后，控制中心刚下拉时每帧绘制仍有 60～250 ms。内核 `2ebb43e` 起，`RedwoodGPU: buffers:` 日志行拆分了新建缓冲区的耗时：控制中心下拉的 5 秒窗口新建约 290 个缓冲区，其中约 250 个小于 64 KB；每个耗时中位数 2.1 ms，其中取得内存（`IOBufferMemoryDescriptor`）50～80 µs，等 `gGPULock` 0～26 µs，其余在把缓冲区写进 GPU 页表的过程中。这一部分有两处耗时：

- 分配 IOVA：`adreno8_space_find_range()` 每次从 IOVA 起点逐页检查，经过所有已占用的页，每检查一页还要线性查找所属的叶表。内核 `19cb049` 记录最低空闲页作为查找起点，释放时再下调；`adreno8_space_table()` 按 2 MB 缓存叶表在 `tables[]` 中的位置。
- 发布页表：每次映射和解除映射外部缓冲区，都把全部 141 张页表（564 KB）清出 CPU 缓存后再失效 TLB，平均 118 µs；缓冲区的每一页还都做一次完整的 GPU 健康检查（GPU 状态寄存器、HFI 队列、三个 SMMU context 的故障寄存器）。内核 `d4df543` 只清理本次改动的页表项，新建的页表由 `adreno8_space_add_table()` 在建立时清理；健康检查改为只在分配 IOVA 和提交映射时各做一次。发布页表的平均耗时降到 3 µs。

`2ebb43e` 同时让每段物理连续的内存只查一次物理地址，并在上下文队列满时放开 `gGPULock` 等待；`kernel-lockwait3-s23-auto-lw` 与 `if4` 的结果相同，这两处没有可测的效果。

同一根盘、`touch_lat=1 glslow=3000`，8 轮操作，主动画的统计方法与第 7.6 节相同：

| 运行 | 内核 | 控制中心窗口每个新建缓冲区（中位数） | 控制中心主动画 | 帧间隔 p95／最长 | 每帧绘制 p50／p95 | 左／右翻页主动画 | 超过 3 ms 的 `glTexImage2D` |
|---|---|---|---|---|---|---|---|
| `kernel-inflight-s23-auto-if4` | `968ac2d` | 2.09 ms | 39.1 帧/秒 | 75.6／544.0 ms | 11.8／83.8 ms | 50.8／55.5 帧/秒 | 未记录 |
| `kernel-lockwait3-s23-auto-lw` | `f1f2665` | 2.09 ms | 38.3 帧/秒 | 76.4／553.4 ms | 12.2／79.2 ms | 50.7／55.3 帧/秒 | 494 次，共 7.8 s |
| `kernel-iova-s23-auto-lw` | `19cb049` | 0.78 ms | 49.5 帧/秒 | 43.9／235.3 ms | 12.7／38.5 ms | 55.6／60.5 帧/秒 | 310 次，共 5.5 s |
| `kernel-publish-s23-auto-lw` | `d4df543` | 0.20 ms | 57.0 帧/秒 | 27.1／71.4 ms | 12.9／21.5 ms | 58.5／60.8 帧/秒 | 140 次，共 1.4 s |

- `d4df543` 一轮中，控制中心下拉后的前 8 帧每帧绘制 15～26 ms；例外是每轮第一次下拉的前 5 帧（30～54 ms）和第二次下拉的第一帧（64 ms）。`if4` 一轮中，前 8 帧里约 5 帧为 50～250 ms。
- 不带数据的 `glTexImage2D` 只新建缓冲区。`19cb049` 一轮中 1082×1226 的平均 65.7 ms、1125×2436 的约 123 ms，超过 3 ms 的共 142 次；`d4df543` 一轮中共 6 次，屏幕尺寸的为 3.2～3.5 ms，最长一次是 640×1152 的 13.6 ms。
- 四轮都运行满 420 s，没有 panic，各 97 张截图都没有色块。
- 剩余耗时主要在 `glFlush`：每轮约 4300 次超过 3 ms，平均 6.2 ms。提交前把 IOSurface 清出 CPU 缓存每次 110～340 µs（`RedwoodGPU: N submissions` 日志行），是其中一部分，其余在第 7.9 节拆分。

### 7.9 GPU 工作时间与提交开销

内核 `db0dc22` 从 GMU 的 TS_RETIRE 通知（kgsl 的 `hfi_ts_retire_cmd`）取每次提交的 sop 与 eop（19.2 MHz 计数），把差值记入 5 秒一行的提交统计；同一行还给出每次提交在内核中的耗时，以及其中检查上下文队列空位的耗时。TS_RETIRE 的数量与提交数相同。

- `kernel-worked-s23-auto-if4` 的控制中心窗口中，每次提交 GPU 工作 1.0～1.7 ms，GPU 忙碌时间占 12%～15%。`adreno8_inflight=8` 一轮（`if8`）与 4 的结果相同。该轮统计优先支持继续检查窗口服务器 `glFlush` 的 CPU 侧：稳定阶段每帧 11～17 ms，其中 `glFlush` 7～13 ms（`eagl.c` 每 20 帧一行的「handing on」）。
- 每次提交在内核中 0.45～0.65 ms：检查队列空位 0.12～0.24 ms，IOSurface 缓存清理 0.12～0.34 ms。队列空位几乎不需要等待，耗时来自 `adreno8_bo_ready()` 的完整健康检查（约二十个 GPU、GMU、SMMU 寄存器读取和一次 HFI 队列读取），一次提交和每次轮询都要经过几次。内核 `00259e5` 在上一次完整检查通过后 1 ms 内只看 BO 状态，故障最晚在 1 ms 后的下一次完整检查中发现；`test-adreno8-bo.py` 驱动时钟验证这一间隔，三种变异都能被发现。
- `kernel-hcache-s23-auto-fixed3`（`cpufreq=3`，大核固定 3072 MHz）与调频一轮的控制中心帧率相同，提高 CPU 频率没有减少剩余的慢帧。
- `glenv=FD_MESA_DEBUG=sysmem` 让 freedreno 不分 GMEM bin，直接在内存中绘制。控制中心每帧绘制 p50 从 13.7 ms 降到 11.2 ms；同一时刻的控制中心截图与 GMEM 模式逐像素比较，没有差值超过 8 的像素。代价是 GPU 直接读写内存，内存带宽和功耗的变化没有测量，默认参数没有改。

| 运行 | 内核 | 参数 | 控制中心主动画 | 帧间隔 p95／最长 | 每帧绘制 p50／p95 | 左／右翻页 | 整轮 < 18 ms | 最低档占比 |
|---|---|---|---|---|---|---|---|---|
| `kernel-worked-s23-auto-if4` | `db0dc22` | | 56.7 帧/秒 | 31.1／114.8 ms | 12.8／22.3 ms | 56.8／60.9 帧/秒 | 75% | 84% |
| `kernel-worked-s23-auto-if8` | `db0dc22` | `adreno8_inflight=8` | 56.5 帧/秒 | 32.6／73.1 ms | 12.9／22.5 ms | 58.6／60.5 帧/秒 | 75% | 84% |
| `kernel-hcache-s23-auto-lw` | `00259e5` | | 58.7 帧/秒 | 17.5／75.5 ms | 13.7／18.1 ms | 58.8／60.8 帧/秒 | 78% | 86% |
| `kernel-hcache-s23-auto-sysmem` | `00259e5` | `glenv=FD_MESA_DEBUG=sysmem` | 59.3 帧/秒 | 17.4／87.8 ms | 11.2／13.7 ms | 58.2／60.7 帧/秒 | 81% | 84% |
| `kernel-hcache-s23-auto-fixed3` | `00259e5` | `cpufreq=3` | 58.4 帧/秒 | 17.4／96.8 ms | 11.3／17.9 ms | 58.2／60.4 帧/秒 | 79% | 2% |

- 各轮都运行满 420 s，没有 panic，各 97 张截图都没有色块。启动阶段大核最高 72.1～73.6 °C，之后操作期间最高 50.8～59.7 °C。
- 第 7.5 节的显示驱动等待：`kernel-hcache-s23-auto-lw` 控制中心动画期间，帧从取出到上屏（`tl: v` 的 ready 到 shown）p50 7.7 ms、p90 12.6 ms，接近设计的 6 ms；`fb_queue=1` 一轮（`kernel-hcache-s23-auto-q1`）为 7.2／12.4 ms，控制中心 58.3 帧/秒。两者相近，默认保持 `fb_queue=2`。
- `00259e5` 两轮中，控制中心主动画里超过 18 ms 的帧间隔集中在下拉的第一个间隔（33～88 ms）和动画中偶尔一次 32～33 ms（少出一帧），其余帧间隔都在 18 ms 以内。8 次下拉中，GMEM 模式共 26 个、sysmem 模式共 13 个超过 18 ms 的间隔。
- 插桩版 libOSMesa（根盘 `out/handoff-ui-auto-prof.apfs`，内核 `2fb0f69`，`kernel-torchlog-s23-auto-prof` 与加 sysmem 的 `-profsys`）每 2 s 输出一次 freedreno 计时。控制中心窗口中，`fd_context_flush` 平均每次 0.16 ms（sysmem 0.10 ms）；GMEM 每个批次平均 1.3 个 bin，按 bin 生成命令 5 µs；每个批次交给内核（`flush_ring`）0.22 ms（sysmem 0.15 ms）。msm 后端在调用线程中同步提交，本版 Mesa 只有 virtio 后端建立提交线程。
- 窗口服务器的控制中心帧有 1400～1600 次 GL 调用、240～270 次绘制和 14～36 次清屏，`glFlush` 5～13 ms。freedreno 运行在 `u_threaded_context` 上（st 创建上下文时带 `PIPE_CONTEXT_PREFER_THREADED`，CPU 多于一颗时生效），非异步的 `glFlush` 在 `tc_flush` 中等驱动线程执行完已排队的调用。`fd_context_flush` 本身不到 0.2 ms，`glFlush` 的其余时间花在驱动线程执行绘制和提交批次上，其中各项的耗时还没有拆分。
- `00259e5` 之后，控制中心窗口里每次提交在内核中 0.9～1.2 ms，检查队列空位占 0.65～0.9 ms；`db0dc22` 时这一段为 0.12～0.32 ms，主要是健康检查。轮询不再每次做完整健康检查后，这段时间主要是等待 GPU 完成第 4 个之前的提交，GPU 在 160 MHz 下每次提交工作 1.5～1.7 ms。帧内连续提交时 GPU 速度已经影响帧时间，GPU 频率档位需要重新评估（第 8 节）。
- 桌面静止时每秒约 30 次提交。两张相隔约 3.5 s 的静止截图只在时钟图标和状态栏时间处不同，时钟图标的秒针在走动。每次提交在内核中清理 3.6 MB IOSurface 缓存，耗时 0.62 ms，合计约占一颗核心 2% 的时间。

### 7.10 GPU 档位对照与最新验证边界

内核 `34209c1` 增加 222 MHz、342 MHz 两个 GPU 档位，`e00c376` 同步报告频率表上限。这两个档位在原厂设备树的六张 GPU 档位表中取值相同，都不带 ACD；160 MHz 不在 SKU 3／0 的表中。`adreno8_speed=1` 固定请求 160 MHz，2、3 是允许达到的最高档。档位经 HFI 消息 30（`GX_BW_PERF_VOTE`）请求，GMU 应答后才算切换。`2957405` 在 5 秒一行的提交统计后加一行 `RedwoodGPU: GPU at N MHz, N speed changes`，记录最近一次请求的档位和累计切换次数。

内核 `ffca661` 让 GPU 档位随负载变化，判断在提交路径上进行，最多每 100 ms 一次。负载取上次判断以来 TS_RETIRE 报告的 GPU 工作时间，换算到 160 MHz 下的占比：

- 占比达到 20%，或最近 300 ms 内有触摸（与 CPU 调频共用触摸时间），升到 `adreno8_speed` 指定的档位。
- 占比连续 500 ms 低于 10%，降回 160 MHz；介于两者之间时保持当前档位。
- 任一 GPU 传感器达到 70 °C 或没有有效读数时请求 160 MHz，全部低于 60 °C 后才恢复上述规则。GMU 没有应答某次请求时，本次运行不再切换。
- 桌面完全没有提交时不做判断，GPU 停在最后一次请求的档位。

`test-adreno8-hfi.py` 驱动时钟和工作时间验证升档、降档、触摸、温控和应答失败，10 种档位相关变异都能被发现。GPU 温控降档仍没有真机触发结果，各轮 GPU 传感器最高 43.6 °C。

同一含 CCHE 修复的根盘、双核动态调频配置下，各轮均完成约 420 s 采样，没有 panic，截图没有色块。按 `tools/k90auto/gestures.py` 统计：

| 运行 | 内核 | GPU 档位 | 控制中心主动画 | 帧间隔 p95／最长 | 每帧绘制 p50／p95 | 左／右翻页 |
|---|---|---|---|---|---|---|
| `kernel-gpugov-s23-auto-gov3` | `ffca661` | 随负载 160～342 MHz | 58.8 帧/秒 | 17.4／60.1 ms | 9.6／14.2 ms | 59.0／60.7 帧/秒 |
| `kernel-gpuspeed-s23-auto-g342` | `34209c1` | 固定 342 MHz | 59.4 帧/秒 | 17.4／58.6 ms | 9.8／13.9 ms | 59.0／60.8 帧/秒 |
| `kernel-gpuspeed-s23-auto-g160` | `34209c1` | 固定 160 MHz | 58.7 帧/秒 | 17.5／68.9 ms | 13.2／18.1 ms | 58.7／60.7 帧/秒 |
| `kernel-setparam-s23-auto-c3` | `811abcb` | 固定 160 MHz，`cpus=3` | 58.6 帧/秒 | 25.1／47.3 ms | 13.4／18.1 ms | 57.8／60.7 帧/秒 |

- `gov3` 整轮切换 46 次，手势循环期间的提交统计行交替报告 342 MHz 和 160 MHz。手势循环结束后的约 45 s 静止期间停在 160 MHz，没有切换；这段时间每 5 s 约 150 次提交，每次 GPU 工作约 0.6 ms，忙碌占比约 2%。
- 窗口服务器每帧绘制时间与固定 342 MHz 相同，帧率差异在各轮波动范围内。
- 桌面静止时每秒约 30 次提交，内容相同。每次提交的 GPU 工作时间在固定 342 MHz 时为 260～273 µs，固定 160 MHz 时为 548～573 µs，比值约 2.1，与频率比 2.14 接近，据此判断 GMU 按请求改变了 GPU 时钟。没有直接的时钟读数，功耗也没有测量。
- `gov3` 启动阶段大核最高 74.0 °C，之后最高 52.3 °C；GPU 传感器 39.7～43.6 °C。
- 持续操作（`kernel-gpugov-s23-auto-soak`，内核 `ffca661`，根盘 `out/handoff-ui-auto-soak.apfs`）：解锁后连续 30 轮控制中心与左右翻页，共运行 1260 s，没有 panic 和崩溃记录，58 张截图没有色块。按 `gestures.py` 统计，控制中心 59.0 帧/秒（帧间隔 p95 17.4 ms），左右翻页 58.3／60.6 帧/秒。启动阶段之后大核每 30 s 的读数在 41～48 °C，单次最高 61.6 °C；GPU 传感器 40.1～43.6 °C；GPU 档位切换 178 次。`summary.py` 对这一轮输出的帧间隔分布与 `gestures.py` 不一致，原因未查，本轮不采用该列。
- 控制中心下拉从手指按下到连续出帧（首帧时间加第一个帧间隔）在 `gov3` 中为 53～131 ms，在固定 342 MHz 的 `g342` 中为 52～129 ms。GPU 档位不影响这一段；第 7.9 节大核固定 3072 MHz 的 `fixed3` 也有同样的首个长间隔，这段时间的组成还没有拆分。
- 三核（`c3`）控制中心 8% 的帧间隔超过 18 ms，双核为 2%～4%，启动阶段大核最高 75.2 °C；四核（`c4`）启动阶段 76.4 °C。c2／c4 误用了缺少 CCHE 修复的旧根盘，只用于比较温度。默认继续使用双核。

Turnip 探针 `kernel-gpuspeed-s23-auto-tu4`（内核 `34209c1`，根盘 `out/handoff-ui-auto-tu4.apfs`）在 K90 上通过设备枚举、传输、计算和绘制读回。同一次启动中探针运行两次，结果相同：

- 枚举到 1 个设备 `Adreno (TM) 830`，API 1.4.354，一个队列族（flags `0x7`），堆 4608 MB；`vkCreateDevice` 返回 0。
- 传输：`vkCmdFillBuffer` 填满 1 MB 缓冲区，再 `vkCmdCopyBuffer` 到第二个缓冲区，三轮的 262144 个字都等于填充值，每轮提交加等待 1.3～1.5 ms。
- 计算：compute shader 写 4096 个字，没有错误值。
- 绘制：64×64 图像清为黑色后画覆盖左上半部分的三角形，复制出来有 2016 个着色像素和 2080 个黑色像素，对角线另一侧没有着色像素。

tu3 之后修正了两处：Mesa 的 `util/libdrm.h` 在没有 `HAVE_LIBDRM` 时把 `drmGetDevices2` 换成空实现，枚举结果为 0 个设备；Mesa 在 EL0 读 `CTR_EL0` 取缓存行大小，XNU 的 `SCTLR_EL1` 没有置 UCT 位，读取触发 SIGILL，改为从 sysctl `hw.cachelinesize` 计算。这两处修改、用户态 syncobj 实现、`RedwoodGPU` 缓冲区映射和探针已进入用户态提交 `24641cc`（本地，未推送），用 `TURNIP=1 REBASE=26 tools/mk-mesa.sh` 构建。从干净目录按仓库内容重新构建的库和探针在 `kernel-gpugov-s23-auto-tu5`（内核 `ffca661`）中得到相同结果。

用户反馈物理按键无响应和电量信息消失后，检查确认这些无人值守载荷缺少 `buttons=1 battery=1`。`tools/k90auto/make-payload.py` 补入两项后，tu4 中按键驱动完成初始化，每 16 ms 轮询电源键和两个音量键，总线读取没有失败；电量计读到 82%，截图状态栏显示 82%。这一轮没有人按键，按键的实际响应需要人工确认。电流为负（放电），状态栏没有充电标记；充电器在线状态继续按路线图单独处理。

发布前离线复核还修正了 `tools/k90auto/summary.py`：低于 18 ms 的比例应包含低于 10 ms 与 10～18 ms 两个桶。三个离线用例验证统计分组，以及队列失败后即使 loader 为 idle 也会停止；该检查不操作设备。手势帧率来自独立的 `gestures.py` 时间轴统计。

## 8. 风险与后续工作

- CB0 的 TCR EPD1 在 GPU 运行后被清零，写入方未确认。当前依赖 TTBR1 为 0 且 IOVA 不超过 39 位。
- `adreno8_gmuclk=2` 的 GMU 时钟路径与触摸共用 DRV2，两者不能同时使用；带触摸的运行使用 XO GMU 时钟。
- 内核未指定 `adreno8_speed` 时固定 160 MHz；`tools/k90auto` 的载荷从内核 `ffca661` 起默认 `adreno8_speed=3`，GPU 随负载在 160～342 MHz 之间切换。实际时钟只由 GPU 工作时间间接确认，功耗和 GPU 温控降档仍没有真机读数（第 7.10 节）。第 7.9 节的忙碌时间只覆盖对应提交配置与采样窗口。
- 温控阈值 70 °C 和 60 °C 是保守取值，长时间高负载下的温度还没有测。启动阶段大核会在 30 s 内多次达到 70 °C。
- 控制中心下拉的第一个帧间隔为 33～88 ms，动画中偶尔少出一帧；窗口服务器每帧 `glFlush` 7～13 ms 的 CPU 耗时只拆出了内核部分，Mesa 部分未拆分，见第 7.9 节。
- 连续出帧时帧在显示驱动中等待上屏，提交路径提速后控制中心动画期间 p50 为 7.7 ms（第 7.9 节），第 7.5 节测得的约 14 ms 来自提速前。
- 用户反馈滑动中偶尔被识别为点击，未复现，未判断是卡顿还是触摸报告问题。
- RedwoodGPU 提交路径没有 Linux msm 在每次提交前后加入的缓存失效和清理。gallium freedreno 按 msm 的提交语义开发，这一差异需要评估是否补齐。
- 天气小组件显示「No weather data」，与网络缺失有关，未单独调查。
