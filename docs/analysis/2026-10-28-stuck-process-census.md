# 被判卡的进程名单与次数（2026-10-28）

统计对象是内核日志里的 `memorystatus_perform_idle_demotion() timed out stuck process <pid> [<name>], moving to idle band`。匹配串是 `stuck process (\d+) \[([A-Za-z0-9_.+-]+)\]`，行中匹配，方括号形式。同一轮内按 `(pid, name)` 去重，因为相邻快照会重复装同一条事件。

## 1. 总量

58 个证据目录里 11 个含有这份日志（其余是早期没有快照的轮次）。

| 次数 | 进程 | 出现轮数 |
|---|---|---|
| 17 | `AudioConverterService` | 11 |
| 11 | `pkd` | 11 |
| 7 | `iconservicesagent` | 7 |
| 5 | `extensionkitservice` | 5 |
| 2 | `installd` | 2 |

**只有这五个名字，58 轮里没有出现过第六个。**

## 2. 逐轮

| 轮次 | 被判卡的进程 |
|---|---|
| `attr-bbm29` | `pkd`、`extensionkitservice`、`iconservicesagent`、`AudioConverterService` |
| `attr-biomed` | `AudioConverterService`×2、`installd`、`pkd`、`extensionkitservice` |
| `attr-crashlog` | `AudioConverterService`×2、`pkd`、`extensionkitservice` |
| `attr-linkd` | `AudioConverterService`×3、`pkd`、`extensionkitservice` |
| `attr-perf-draw-v6` | `installd`、`AudioConverterService`、`pkd`、`extensionkitservice`、`iconservicesagent` |
| `attr-speed3` | `AudioConverterService`、`pkd` |
| `attr26-continuous` | `AudioConverterService`×3、`iconservicesagent`、`pkd` |
| `cpufreq-report-airarm64e-a` | `AudioConverterService`、`pkd`、`iconservicesagent` |
| `cpufreq-report-airarm64e-b-metal` | `AudioConverterService`、`pkd`、`iconservicesagent` |
| `cpufreq-report-airarm64e-c-metal3` | `AudioConverterService`、`pkd`、`iconservicesagent` |
| `cpufreq-tsens-airarm64e-a` | `AudioConverterService`、`pkd`、`iconservicesagent` |

## 3. 两个结论

**判据没有乱判。** 名单窄且稳定：58 轮里只有五个名字，没有 `lsd`、没有 `SpringBoard`、没有任何随机进程。所以「memorystatus 的判据在我们这儿坏了、随手把进程标成卡住」这个怀疑不成立。

**但被判卡不是「好轮与坏轮」的分界线。** `attr-linkd` 是迄今最干净的一轮（11,015 帧、无停帧、`linkd.registry` 从 412 行归零），它同样有五个事件：`AudioConverterService`×3、`pkd`、`extensionkitservice`。所以「被判卡」是一种长期存在的背景状态，不能用来预测停帧。

由此得出一条判据上的修正：**补服务不能拿「stuck 消失」当验收条件**，因为干净的轮次里它也出现。补服务的验收只能看效果——容器建了没有、记录写了没有、`Code=4099` 归零了没有。

## 4. 五个进程各自在等什么

- `pkd`（PlugInKit）、`extensionkitservice`、`iconservicesagent`、`installd` 都是**服务端**：它们等客户端来查，空闲时被压缩、被 reclaim 是正常形态。
- `AudioConverterService` 是唯一反常的一个：它通常由音频守护进程按需拉起，而这个镜像里没有 `mediaserverd`。它在**每一轮**都出现，包括最干净的那一轮，说明它在我们的环境里被反复拉起又卡住，属于「本来就缺父进程」的那一类。
- **`AudioConverterService` 与桌面无关，先不处理。** 它是这份统计里次数最多的（17 次、11 轮），说明「缺守护进程」这一类问题在音频线上比在图形线上更重，但它不影响图标、小组件或停帧。记在这里是为了以后不要把它当成新发现重查一遍。
- 它的出处已核（display）：`/System/Library/Frameworks/AudioToolbox.framework/XPCServices/AudioConverterService.xpc/AudioConverterService`，是 AudioToolbox 内置的按需 XPC 服务，客户端是任何做音频转换或解码的进程，由 AudioToolbox 在需要时拉起。**`mediaserverd` 不在它的父链上**，所以它反复出现与 `mediaserverd` 缺失是两件独立的事；原先把它归到「缺父进程」的说法作废。它在共享缓存里有两处服务名登记（`.05` 与 `.17` 分片），与「每轮都出现」一致。

## 5. 补服务的顺序

按提供者分组，服务名的归属决定判据，与作业标签无关：

| 服务名 | 提供者 | 判据 |
|---|---|---|
| `com.apple.coreduetd.context` | `com.apple.contextstored` | 该名字的 `Code=4099` 归零 |
| `com.apple.duetactivityscheduler`、`com.apple.dasd.end-prewarm` | `com.apple.dasd` | 两个名字的 `Code=4099` 归零，停帧变化单列 |

先上 `contextstored`：那 132 条 `Code=4099` 的服务名是 `com.apple.coreduetd.context`，清掉它一轮就能看到明确效果，而它不接管后台调度，不会搅浑性能与温度测量。`dasd` 放到下一轮，因为它会接管后台调度；若 `contextstored` 之后反而冒出 `duetactivityscheduler` 的 4099，那正好说明两者互相依赖。

## 6. 未验证

- 五者的卡住时长没有统计。判卡需要跨过两个 aging 期限，所以「被判卡」只说明它们至少跨过了一次期限，不说明卡了多久。
- 它们各自在等哪个 XPC 名字没有查。`pkd` 在整个 `bbm29` 轮里一行日志都没有，`extensionkitservice` 只有判卡那一行，所以从日志侧拿不到它们在等什么。