# 120 Hz 刷新档位：实现方案（2026-10-29）

## 1. 问题

桌面长期停在 60 Hz 满帧流（末帧间隔中位数 16,646 到 16,663 微秒，见[冻结征兆表](2026-10-29-freeze-symptom-table.md)）。按 upstream 的发现，渲染服务器给显示定时器定速靠 `IOMFBDisplayRefresh` 的 `displayMinRefreshInterval`；缺这个属性就退回 1/60 秒的心跳，通用 slot 301 又把最小值固定为 1/60。

## 2. 改法

驱动文件是 `hackios-xnu-kernel/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp`，目前没有 slot 301 与 `IOMFBDisplayRefresh` 的任何处理。

1. **覆盖通用 slot 301**：把它指到自写的处理函数，不再落到通用实现。该函数负责设置刷新区间属性，返回值与参数校验按原 slot 的签名走。
2. **区间按面板当前档位写**：`displayMinRefreshInterval` 与 `displayMaxRefreshInterval` 取当前模式对应的周期。60 Hz 档是 16,666,667 纳秒，120 Hz 档是 8,333,333 纳秒。两值都从模式表算，不写字面量，避免换面板后两份数不一致。
3. **在 `registerService()` 之前调用原始 `setDisplayRefreshProperties`**：属性必须在 launchd、backboardd、SpringBoard 起来之前进注册表，否则先起的进程拿不到。这与该文件 1487 行记的「属性发布时机」是同一个约束。

## 3. 落地顺序与前置条件

先把「属性发出去了」做成可判，再谈间隔：驱动侧在设置时打印一次目标区间（最小与最大，纳秒与对应的档位），用户态用 `IORegistryEntryCreateCFProperty` 读 `IOMFBDisplayRefresh` 的两个值并打印。这两行打印属于改动本身，不做成可选项；否则间隔不变时分不清「没发出去」与「发出去了但没被采用」，两年后重读日志也分不清。

顺序：驱动打印目标区间 → 用户态读回比对 → 再测末帧间隔。前两步不过，第三步的读数不成立。

## 4. 验收

- 主判据：末帧间隔中位数从 16,65x 微秒降到接近 8,333 微秒，且帧号在同样时长内翻倍。
- 间隔不变时先查属性有没有发布成功：驱动侧打印一次目标区间，用户态读 `IORegistryEntryCreateCFProperty` 取 `IOMFBDisplayRefresh` 的两个值并与打印比对。发布成功而间隔不变，说明渲染服务器没有按这个属性定速，下一步查渲染服务器侧读属性的时机。
- 不把 120 Hz 当性能基线：帧间隔达标的同一轮要同时记录 `rwa draw:` 每帧绘制数与 hot ticks 分布，否则无法与 60 Hz 轮比较。

## 5. 与 `fb_hz` 的关系

`fb_hz` 只改 vsync 定时器的周期，改不到这条路径：它决定中断多久来一次，渲染服务器的显示定时器按 `displayMinRefreshInterval` 定速，两者不同层。所以 `fb_hz=120` 的轮次不会出现 8.33 毫秒的帧间隔，`fb_hz` 也不能用来验收本方案。

## 6. 与 memmove 故障的关系

现有记录不支持「120 Hz 触发该故障」：round E（`fb_hz=120`）与 round F（默认 60）在同一调用点、同一 `pc` 偏移上出了同一个故障，来源见 [roundb 归因](2026-10-28-roundb-memmove-attribution.md)。所以本方案与该故障无因果关系，改完不需要重跑 memmove 判据；若改完 bad access 形态变化，按新现象单独立项，不并进这条。

## 7. 未做与风险

槽位 301 的原始签名与调用方要先从 26 内核的 `IOMobileFramebuffer` 用户客户端里核一遍，本方案按 upstream 的名称写，落地前要确认 12377 里的实际符号。120 Hz 对显示驱动拷贝（`tl: v`）与 SMMU 带宽的影响没有实测，第一次跑 120 Hz 的轮次要单独看 `tl: v` 的三段时间。
