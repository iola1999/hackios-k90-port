# iOS 26 合成链路：注入生效与慢 draw 定性（2026-10-29）

本轮把「桌面合成为什么慢」从找不到落点推进到一条可复现的读数链，同时修掉注入链上三处静默失败中的两处，并让内核构建可复现。设备在两轮之间从 USB 掉线，最后一组探针（`state` 分段与预落页）尚未取得读数。

## 1. 注入链的三处静默失败

三处都不产生任何日志行，只能靠「加上显式读数」发现。

- **注入名单被覆盖**：`package.py` 的 `INJECT` 只列了 SpringBoard 那一行实验库，`libredwood.dylib` 从未进入 `inject.conf`。
- **架构与签名不匹配**：`libredwood.dylib` 一直是 arm64 且未签名，而 backboardd 与 SpringBoard 都是 arm64e 进程，dyld 静默跳过。改成 arm64e 并 adhoc 签名后，`redwood lib loaded pid 38 name backboardd` 立即出现。
- **窗口服务器钩子地址过期**：`inject.c` 里九处虚表穴位加一处 IMP 校验全部是 iOS 16.5 (20F66) 的常量。`VT_APPLE_CLCD_DISPLAY = 0x1d5b44520` 在 26 上落在 `dyld_shared_cache_arm64e.27`，`+0x10` 读到 `0x9907980697059604`，与运行期报的 `found 0x9907980677eb9604` 高位 32 位与低位 16 位一致；该地址在 16.5 的 43 段映射里没有任何落点。所以九个 `expected` 在 26 上必然失配，`:667` 的汇总一直写 `INCOMPLETE`。

第三处试过改成运行期取虚表基址（`-[CAWindowServer _detectDisplays]` 的 IMP → `_displays` → `*(void ***)display`），只读探针版让 backboardd 连续 15 次 `signal 11` 并重启，原因是该实现内部 `alloc`／`init` 了一个新的 `CAWindowServer` 实例。已回退，`libredwood.dylib` 回到 `1d727833…`（91,232 字节），该版桌面正常、716 帧、零 `bad access`。

## 2. 内核构建可复现

`config/newvers.pl` 从环境读版本串，`xnu26/build-macos.sh` 在 `source env-macos.sh` 之后给默认值。版本串进 `version[]`、位于 `__TEXT,__cstring`，长度一变就把后面整段字符串位移；上一轮实测差 11 字节导致 1.1 MB、15.9 万段差异，镜像大小不变。

`ld-27037.1` 不接受 `-uuid`（三种写法都报 unknown options），且对同样输入每次随机赋 UUID。改成链接后在加载命令里找 `LC_UUID` 写死 16 字节。

验收：`rm -rf out/xnu12377/BUILD` 后全量重编 37 分 52 秒，产出 `f055cc0a928e6b3a69f1043a419105362a71ea46ac1789e05387dea1db54c2c3`（20,226,616 字节）；删产物强制重链一次，哈希相同。

## 3. 慢 draw 的定性过程

结论先行：**单次 draw 的墙钟可达一到两秒半，线程 CPU 时间只有几十到几百微秒**。性质是等待，不在计算。

判读依靠四组读数对齐：

| 探针 | 读数 | 折成真实时间 |
| --- | --- | --- |
| `fd6 inner slow: post` | 26384 | 1.374 秒 |
| `fd draw slow: call` | 46471 | 2.42 秒 |
| `rwa draw call` | wall 1,374,219 µs、cpu 153 µs | 1.374 秒 |
| `rwa draw slow: draw_vbo` | 1,374,211 µs | 1.374 秒 |

### 3.1 时基换算是三轮排查的主因

`fd_perf_us()` 是 `mach_absolute_time() / 1000`，把 tick 当微秒，读数与真实值差 52.083 倍（1 tick 为 52.083 纳秒，1 个 fd 单位等于 1000 tick）。这一处让「阈值 20,000」的真实触发点变成 1.04 秒，前面几轮因此把慢 draw 判成静默。

同类换算在同一天出现在三处：驱动的 `has run for`（33 秒实为 1,724 毫秒）、AIR 侧一度怀疑的 19.2 倍（核对后不成立）、以及这里的 52.083 倍。新加计时的第一步应当是报出单位与时基，再报数值。

### 3.2 已排除的候选

- **着色器编译**：`prog_builds` 全轮累计为 0。
- **批提交**：`batch submit` 的全局最差 1 微秒；`fd_batch_check_size` 一次没有超过 50 毫秒。
- **显式映射等待**：`fd_bo_cpu_prep` 的包装探针 0 行。
- **早退分支**：五个早退点各埋读数，0 行；同轮 `fd draw calls` 有 33 条，说明探针在执行。
- **触摸注入**：无输入对照轮 `wall` 累计 8.95 秒、`cpu` 累计 28,828 微秒，与带触摸那轮的 14.3 秒同一量级。
- **`tc_draw_vbo`**：`rwa draw call` 打出的 `draw_vbo` 符号名一律是 `fd_draw_vbo`；`air_metal.c:776` 建 context 时 `flags` 传 0，`fd_context_init_tc` 因此不包 threaded context。

### 3.3 当前落点

`draw_vbos<>` 的 `state` 段（入口到 `draw_emit` 之前）独大：

```
fd draw seg slow: state wall 824045 cpu 128 flt 196 us
```

`emit`／`streamout`／`allclean` 三段各 0 条。缺页 196 次与 824 毫秒的比值是每次 4.2 毫秒，普通匿名页路径在微秒量级，而 device pager 映射可能不同——`RedwoodGPUMemory.inc:313-315` 用 `IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task, …)` 建缓冲，用户侧经 `IOUserClient.cpp:4784` 的 `createMappingInTask` 建 device pager 映射，整份文件没有 `prepare()` 调用也没有 `kIOMemoryWired`。

## 4. 未完成

- `state` 段内部分段游标与首次映射预落页已编进同一份 AIR（`57fdb85c…`，14,051,376 字节），设备在两轮之间掉线，读数未取。两版同时在场，一次运行可同时取两组读数。
- 慢 draw 触发 `kern.redwood.thread_dump` 的路径被身份挡住：backboardd 以 mobile 身份运行，写该 sysctl 返回 `errno 1`，49 条 `dumping threads` 对应 0 条 `tl: td`。

## 5. 本轮身份

| 项 | 值 |
| --- | --- |
| 内核 | `f055cc0a928e6b3a69f1043a419105362a71ea46ac1789e05387dea1db54c2c3`（20,226,616 字节） |
| 驱动 | `d6d45b6825e9101cc8ef6b78c569fd2a2715db415ea9b1aa590e1358fbcca1c6`（242,128 字节）；探针版 `868677669a794310ce1159ac37721eca9e5f726221a714e4f9ea3bd6afd71d44`（242,224 字节） |
| AIR | `95ce99956630ad64eb67ca71a67412a77a3f779d2be590640538c34d1d9e1523`（14,018,416 字节）；`state` 分段＋预落页版 `57fdb85c38bcf6892de3394ffa184963d881a99a091dae828c85dba5cb22e8eb`（14,051,376 字节） |
| `libredwood.dylib` | `1d7278335752c53cee5e43294136f52ddafb6442b542aa9db61258372911421b`（91,232 字节，arm64e、adhoc） |