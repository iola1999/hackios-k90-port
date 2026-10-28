# 外部 buffer unmap 的代价与后期帧时间的构成

这一篇回答三件事：unmap 为什么等 GPU 空闲、等多久、以及后期帧时间到底跟什么走。

## 1. 调用链与频率

`RedwoodGPUUserClient::freeBuffer`（`iokit/Kernel/RedwoodGPUMemory.inc:17`）在客户端归还一个 buffer 时判断 fence：未完成就放进延迟队列 `fLeft`，完成的先看能不能留进 `keep()` 缓存，留不下就 `gpuReleaseMapping` → `redwood_gpu_unmap` → `adreno8_bo_unmap`（`bsd/dev/adreno8_bo.c:169`），后者先 `adreno8_context_wait_idle("external BO unmap")`，再清 PTE、再 publish。`reap()`、`dropKept()` 和建 buffer 失败的回退路径走同一个函数。

频率是每归还一个外部 buffer 一次。`kernel-12377-attr-speed3` 这一轮实测 137 次/秒（`1028 external buffers unmapped in 7511 ms`）。

`keep()` 的门槛是 `GPU_KEEP_FROM = 256 KB`（`iokit/Kernel/RedwoodGPU.cpp:463`），小于 256 KB 的 buffer 一律不缓存。CoreAnimation 交回来的多是 16～32 KB，全部落在门槛下，所以每次归还都要 unmap。

## 2. 等待时间：单次约 100 µs，整轮占 0.25%

日志 `adreno8: N external buffers unmapped in X ms, Y us waiting for the GPU to be idle in all` 的第二个数是窗口跨度，第三个数是窗口内累计等待。`1028 external buffers unmapped in 7511 ms, 99486 us waiting` 摊到每次是 97 µs，占该窗口 1.3%。

整轮 37 个窗口累计等待 858 ms，跨越 350 秒，即墙上时间的 0.25%，均值 115 µs 一次。TLB publish 同样便宜：平均 4 µs 一次，5 秒窗口里 1011 次（`adreno8: page tables published …`）。

按 41.7 ms 一帧折算，一个 5 秒窗口约 120 帧，99 ms 的累计等待摊到每帧不到 1 ms。

## 3. 为什么等，以及三条更便宜的做法

`adreno8_bo_unmap` 要清 SMMU 的 PTE，若 GPU 仍在用那个 VA 会取指或取数出错，所以先等 idle 再改表。

调用方在这个分支上已经知道 buffer 不再被引用：`freeBuffer` 的条件是 `b->fence != 0 && !redwood_gpu_done(b->fence)`，走到 unmap 时 fence 已完成。这里的全局 drain 在多数调用上多余。

- 给 `adreno8_bo_unmap` 加一个「已完成」参数，在 fence 已确认完成的分支里跳过全局 drain；
- 把已退休的地址范围攒成一批，一次 publish 覆盖整批，N 次 drain 合成 1 次；
- 把 `GPU_KEEP_FROM` 降到 16 KB 量级，让小 buffer 复用同一段 IOVA，从源头减少 unmap 次数。

## 4. 后期帧时间跟「每次提交的 work 数 × 每 work 成本」走

`command buffers: N committed, X works each, …` 里的 X 是最近 64 次提交的平均（`userland/src/redwoodmetal_commandbuffer.inc:466` 的 `window_works / window_commits`），不是累计值。`speed3` 这一轮：

| works each | encode | flush | 每 draw |
| --- | --- | --- | --- |
| 6～8 | 3367 µs | 2258 µs | 49 µs |
| 93～102 | 10771～12152 µs | 318～692 µs | 105～125 µs |

后期每次提交约 100 个 work、每个 work 约 105～125 µs，`100 × 105 µs ≈ 10.5 ms`，与 `encode 10.8 ms` 吻合。

## 5. 217 秒的提交不能用 idle 等待解释

`redwoodmetal[backboardd 177]: commit 9 has run for 217120 ms and is on work kind 0 (3 binds, a draw)`。同一提交的打印从 10692 ms、109493 ms 递增到 217120 ms，`commit_count` 始终是 9，说明它在工作循环里反复回到打印点。

- `gpu_wait_idle` 的上限是 2000 次 × 100 µs = 200 ms，`context_wait` 的 `CONTEXT_WAIT_NS` 也是 200 ms，单次等待到不了 217 秒；
- 整轮 `EOP timeout` 与 `queue full` 都是 0 条；
- 这一轮 cmdline 里没有 `gpu_recover`，GPU 报错后停住，不会反复恢复。

卡住的调用在 `mesa.flush`（`tools/mesa/air/air_metal.c:2795` 的 `rwa_flush` → `device->pipe->flush`）或 `runDraw` 之内，需要用单次计时定位。shim 现有的 `flushes of N us each` 是 64 次提交的平均，看不到单次 217 秒。

## 6. backboardd 的实例

`speed3` 这一轮 shim 打印过 `backboardd 36 / 104 / 177 / 199 / 241 / 260 / 288`，即五次重起，第一次 `start clearing the board for /usr/libexec/backboardd respawn` 在 04:30:25。与 217 秒那条不构成同一条链：等待上限 200 ms 与 217 秒差三个数量级，重起也发生在别的进程上。
