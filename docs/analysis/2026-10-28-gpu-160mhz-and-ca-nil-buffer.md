# GPU 停在 160 MHz 与 CoreAnimation 的 nil buffer 两条读数

这两条都是读数，不是结论：一条说明 GPU 全程跑在我们表里最低的档位上，另一条说明 CoreAnimation 每条 `nil buffer from memory` 都对应一次我们静默返回 nil 的分配。

## 1. 160 MHz 来自 boot 参数，DVFS 路径没有坏

`adreno8_speed_tick()`（`adreno8_hfi.c:598`）在每次 GPU 提交时被调用（`redwood_gpu_dispatch.c:126`），用 `adreno8_retired_total` 算负载千分比：≥20% 或 300 ms 内有触摸时升到 `adreno8_speed_asked`，<10% 持续 500 ms 降回 1，GPU 温度 ≥70 °C 强制降到 1、<60 °C 放开。投票走 HFI 消息 30，格式 `{1, want, bus}`。

它的第一行是开关：`if (adreno8_speed_asked <= 1 || adreno8_speed_asked >= adreno8_gx_count || !adreno8_hfi_tables_sent) return;`。性能轮的 cmdline 里是 `adreno8_speed=1`，于是这个函数每次都直接返回，档位停在开机时硬编码的 160 MHz（`adreno8_hfi.c:543` 的 `uint32_t msg[3] = {1, 1, 2}`）。

表里一共三点（`adreno8_cx.c:112` 的 `adreno8_boot_speeds`）：160 MHz / GX level 0x32 / DDR bus 2，222 MHz / 0x34 / 2，342 MHz / 0x38 / 3，另加一个 `0 Hz` 空闲点。只取这三点的理由写在注释里：六张现役 K90 DT 表在这些点上一致。

温度不构成阻碍：整轮 `cpufreq:` 行里 GPU 读数 46.7～48.2 °C，而闸门是 70 °C。`annibale_gpu_temperature()` 用的 `tsens_hottest(TSENS_GPU, …)` 与打印那行是同一个 helper。

判据：`adreno8_speed=3` 之后开始画桌面时，`gpu_log` 的 speed changes 必须在头几秒内 > 0（1.7 ms/帧对应的负载远超 20% 门槛）。仍为 0 就说明卡在投票 ACK 或温度读，而不是开关。

## 2. `nil buffer from memory` 是我们静默返回 nil 的 buffer 分配

CoreAnimation 这条日志的格式串在 QuartzCore 的 `__TEXT,__oslogstring`（`0x18428e17f`）：`nil buffer from memory: [b:%08lx o:%04lx l:%06zx], w:%u h:%u bpr:%zu bpi:%zu`，同族还有 `nil linear texture from buffer: …`（`0x18428e1cd`）。`[b:…]` 是 GPU 地址，`l` 是长度，后半是它要叠上去的纹理形状。

引用点 `0x183fdcb88` 的逻辑：取回 buffer 存入 `[x24, #0x40]`，`cbz` 为空时走日志块并 `b 0x183fdc9e4` 返回失败；非空时置 `[x24, #0x7b]` 的第 `0x200` 位并返回 1。所以 nil 的后果是**这次分配放弃**，不是拿着 nil 继续画，也不是等待。

nil 的来源不是 IOSurface 纹理：`newTextureWithDescriptor:iosurface:plane:` 在 `redwoodmetal.m:2345` 有实现，失败会打 `no drawable: …`，而整轮 `no drawable` 与 `nil linear texture from buffer` 都是 0 条。来源是两个静默 `return nil` 的 buffer 选择子，其中 `newBufferWithIOSurface:` 只出现在 Metal.framework 的选择子表里，`newBufferWithBytesNoCopy:length:options:deallocator:` 在 QuartzCore 与 Metal.framework 都有——调用方是后者，实现见 `redwoodmetal.m:2379`，注释是「wrapping the caller's own pages needs the kernel to map them: not yet」。

这条不解释坏轮次。同一条日志的条数：`bbm29`（桌面 15 个图标、被判好的一轮）712，`biomed` 584，`linkd` 585，`perf-draw-v6` 304。最好的一轮最多，最差的一轮最少。要补它需要把调用方的页映射进 GPU 地址空间，或者改成创建时拷贝并像 `rwa_buffer_textures_refresh` 那样在每次 commit 重拷；收益是补齐一些小资源，不是每帧省下时间。

## 3. 一条被数据否掉的假设（lead 提出）

lead 曾据 `nil buffer from memory` 的邻居字符串（`Failed to allocate MTLTexture from IOSurface …`、`update_surface for IOSurface id=…`）提出：我们的 Metal 可能没有实现「从 IOSurface 建 texture」，于是 CoreAnimation 拿 nil 去画，提交因此变慢。

这条不成立，三点证据：

- `newTextureWithDescriptor:iosurface:plane:` 在 `redwoodmetal.m:2345` 有实现，失败路径会打印 `no drawable: …`；四轮日志里 `no drawable` 0 条。
- 同族的 `nil linear texture from buffer`（CA 叠在 buffer 上的纹理）0 条。
- 条数方向相反：`bbm29`（桌面 15 个图标，最好的一轮）712 条，`biomed` 584，`linkd` 585，`perf-draw-v6`（最差的一轮）304。若它是原因，最好的一轮不该最多。

nil 的真实来源是 `newBufferWithBytesNoCopy:length:options:deallocator:` 这个静默 `return nil` 的实现（`redwoodmetal.m:2379`），其后果是 CA 放弃这一次分配并返回失败，不拖慢提交。

## 4. `adreno8_speed=3` 的实测：升频成立

`kernel-12377-attr-speed3` 那一轮的读数：

```
RedwoodGPU: GPU at 160 MHz, 0 speed changes since it started
RedwoodGPU: GPU at 160 MHz, 10 speed changes …
RedwoodGPU: GPU at 342 MHz, 3 speed changes …
RedwoodGPU: GPU at 342 MHz, 9 speed changes …
```

- 变化次数最大 28，不是 0。§1 那条判据（开关是唯一阻塞点时 changes 必须 > 0）成立。
- 频率采样里 342 MHz 出现 44 次、160 MHz 91 次，两档都在用；160 是空闲回落的档。
- GPU 温度 47.5～49.8 °C，温度闸门没有介入。
- 没有 `the GPU speed vote … was not acknowledged`，投票都被 ACK。

同一轮有一个 217 秒的提交（`commit 9 has run for 217120 ms and is on work kind 0 (3 binds, a draw)`，`backboardd 177`），比此前讨论的 3 秒量级大两个数量级。升频不消除提交卡住。

线程 dump 那一轮没有数据：7 条 `thread dump for pid N refused (errno 2)`，`errno 2` 是 ENOENT，即运行的内核里没有 `kern.redwood.thread_dump`。三轮（`linkd`、`crashlog`、`speed3`）的 `manifest.json` 里 `kernel.sha256` 都是 `c1f192495ee4ded85c20f3be34e7549d4a784ac363da52df4127677c9c0f66a7`，是 `ade518a` 之前编的内核。观察线程本身在工作（它按 2500 ms 阈值触发了 7 次），缺的是内核侧。
