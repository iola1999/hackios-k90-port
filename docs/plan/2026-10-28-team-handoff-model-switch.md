# 2026-10-28 team 交接文档：模型切换暂停点

本文写给模型切换后的新 team 实例。暂停时刻设备 idle、没有轮次在跑、roundb 已归档、所有离线分析已回报。阅读本文与 [运行协议](k90auto-run-protocol.md)、[总账](2026-10-23-tracking.md) 后可以接手，不需要读旧会话。本文已确认的事实错误与作废结论列在 §11，接手前先读它。

## 1. 新 goal 描述

目标与验收口径不变，全文见 [用户需求](2026-10-28-user-requirements.md) §6 与当前 goal（2026-10-28 重建，id `goal-a1b13126`，比旧版多一节「协作方式」：lead 只做协调和决策；队友仅在验收口径变更、修改 iOS 系统镜像、跨模块结构性改动、同一路径超过 2 轮不收敛、结论与 goal 冲突、`air_metal.c` 与 userland 源码归属冲突时升级；只有 device 成员可执行 fastboot／adb／打包与轮次运行）。性能验收口径为「不受热限制时 ≥60 fps」加「从冷机开始维持满频的时长」，目标是还原安卓真机性能，允许推翻现方案大幅重构。

当前主线（2026-10-28 暂停点）：两种故障形态待统一或分开。旧驱动 `31f2d6b7` 的形态是冻结（SpringBoard 主线程自 +106 秒起在私有对象上 `psynch_cvwait` 恒定等待，runloop 停泵，内容在 131 秒停止变化、提交 126.3 秒停止，两个都是轮内相对秒，见 §11）。拷贝路径驱动 `9d66dd36` 的形态是重启循环（backboardd 每约 10 秒段错误一次、SpringBoard 随后被 `9/0` 杀、面板全程黑屏档）。第一优先动作是定位 roundb 里 212 条 bad access 的共同 pc `0x2b0fb59c0` 属于哪个镜像，据此判定拷贝路径的去留。

## 2. 两种故障形态与证据链

冻结形态（freeze 轮，驱动 `31f2d6b7`，内核 `9a7a118a`，证据目录 `docs/progress/evidence/k90auto/kernel-12377-attr26-freeze/`）：

- 94 张截图 2 个唯一哈希，切换在 shot-01311（约 131.1 秒）；`tl: s`／`tl: v` 3,425 条、148.1→273.0 秒（这两个 `tl:` 值是设备钟原值，轮内相对秒要减 B≈146.7，见 §11；差值不受零点影响）、约 27 次/秒直到突然停止；触摸 237.8→248.3 秒（设备钟）落在提交窗内，提交在触摸结束后 25 秒才停。
- 主线程判读（display，墙钟锚 `09:44:16.14`，8 个 dump 时刻 +20.6/41.2/60.1/83.3/106.2/126.4/136.8/155.9 秒）：SpringBoard 主线程 tid 221 在 +41.2～+83.3 秒为 `mach_msg2_trap`，自 +106.2 秒起转入 `psynch_cvwait`、wait 恒为 `0xfffffff6e7eef800`（只在 pid 30 内出现，SpringBoard 私有），此后没有再变。内容冻结（131 秒，截图轴的轮内值）与提交停止（轮内 126.3 秒，设备钟原值 273.0 秒，见 §11）都在这之后。
- 同一时段 chronod 的 widget 扩展会话成片 watchdog 超时（−9.2 至 +28.5 秒内至少 8 条 `watchdog fired. Cancelling session`）。时间贴合，因果未证。
- 切换后固定有一个运行态线程 tid 306、pc `0x105f00cd8`（SpringBoard 私有 `__TEXT`，名字待内核 exec 基址行落地后才能给）。
- backboardd 主线程全程 `mach_msg2_trap`、wait 恒 0。
- `nil buffer from memory` 25 条、`rwa buffer: copied` 0 条（当轮驱动无拷贝路径）、pipeline 失败 0、无 bad access。
- 15 秒周期 3 秒空洞（180.5/195.5/210.5/225.5 秒，洞内 0 条 commit 告警＝没人发起提交）；240.6 秒另有一个 3.9 秒空洞带 76 条告警（一个 commit 跑不完），紧接提交永久停止。

重启循环形态（roundb，驱动 `9d66dd36` 带拷贝路径，内核同 `9a7a118a`，jobs `a4af9a9f`，payload `ef3c82e1b58ea6db`，证据目录 `docs/progress/evidence/k90auto/kernel-12377-attr26-roundb/`）：

- 94 张截图全部黑屏档（`order: black x94`），5 个唯一哈希，切换在第 1/3/6/9/15/27/50 张（1 基），其中两个哈希重现（第 6 张回到第 1 张、第 50 张回到第 15 张）。面板整轮没有显示出内容。
- `tl: s` 仅 99 条、971.0→1235.9 秒，前 120 秒占 90 条；`tl: p` 36 条、1060.3→1070.8 秒（第一次拖动落在提交窗内，但该轮无性能判读价值）。
- SpringBoard 14 代 pid（30、103、131、142、161、175、189、205、214、228、241、246、260、267），backboardd 15 代（38、84、99、124、140、153、167、187、197、212、221、235、243、257、265），每代活几秒到十几秒。死亡形态固定：backboardd 先死 `11/11`（段错误），0.2～0.7 秒后 SpringBoard 死 `9/0`（被 SIGKILL），每对间隔约 10 秒，后段拉长到 20/40/80 秒。两者各有 15 条 `exited code -1`。
- `framewatch: resumed at … after 9/10 s` 16 条（`userland/src/framewatch.m:257`）是误读：新 backboardd 起来后 `kern.redwood.frames` 从 0 重新计数，framewatch 判成「恢复」。停机段实为 14 段（9 段约 10 秒，另有 16.4/20.3/40.3/80.3 秒）。
- `rwa buffer: copied` 109 条唯一行（原始 1,775 条），尺寸分布 32768 字节占 89%（1,579 条），同一 `(contents, length)` 对出现两次的次数为 0（无重复拷贝）。`nil buffer` 1 条（1.3 MB，大于 65536 字节阈值（源码常量 `redwoodmetal.m:2408` 的 `NOCOPY_LIMIT = 0x10000`；原记 16 KiB，沿用了 `:2405` 注释里的错数，见[判读口径 §3.6](../analysis/2026-10-28-roundc-reading-criteria.md)），按设计返回 nil）。pipeline 失败 0。
- bad access 原始行 212 条（跨快照未去重，去重口径待 round-stats），pc 两种：`0x2b0fb59c0` 204 条、`0x2b0fb5ad4` 8 条（相距 0x10c，大概率同一函数）；进程名全部 `backboardd`；故障地址样本含 ASCII 字符串字节（`0x2e697269732e656c`、`0x63756f5474656b63`，形如反向域名字符串片段被当指针解引用）与 `0x1` 这类小整数。

## 3. 最高优先线索：bad access pc 的镜像归属

roundb 的 slide 为 `0xb05000`（display 按 `mach_msg2_trap` 偏移反推）。`0x2b0fb59c0 − 0xb05000 = 0x2b04b09c0`，超出共享缓存上界 `0x2adb74640`，该 pc 在缓存之上的私有映射里。候选：`libredwoodmetal.dylib`（241,488 字节）、`libredwoodair.dylib`（13,983,936 字节）、backboardd 主二进制。日志里没有各镜像的加载地址，现有数据判不了。

判定路径两条：

- 内核改动（进 round C）：bad access 打印处加打所在 region 的后备文件名（拿不到名字时打 region 起止），dump 加 `tl: td <pid> exec <基址>` 行（`vm_map` 里第一个有 vnode 后备且权限含 execute 的 entry，`osfmk/vm/vm_map.c` 的遍历方式已核可行）。
- 若 pc 落在我们的 dylib：拷贝路径实现自身引入段错误。若落在系统库：拷贝路径让 CA 走过原先 nil 失败的点、进入更深处一个既有缺陷。两种结果对拷贝路径的处置不同（修复保留或回退）。

补充实测（暂停前最后一条）：打印格式为 `redwood: <进程名> bad access at <地址> pc <pc>`，**进程名直接可读出，roundb 的样本行全是 `backboardd`**；pc 两种：`0x2b0fb59c0` 204 条、`0x2b0fb5ad4` 8 条（相距 0x10c，大概率同一函数），故障地址含 `0x1` 这类小整数。**打印点已定位：`out/xnu12377/osfmk/arm64/sleh.c:2091`**（`redwood_*.c` 与 `bsd/kern` 里 grep 无命中，它在 arm64 异常处理里），region 信息就加在这一处；代码尚未写。

## 4. 关键身份清单

| 项 | 值 | 说明 |
|---|---|---|
| 内核 | `9a7a118a1545…`（20,210,112 字节） | freeze 轮与 roundb 同内核；含 `tl: td slide` 行 |
| 驱动（旧基线） | `31f2d6b7` | freeze 形态所在版本 |
| 驱动（拷贝路径） | `9d66dd36`（源码提交 `963fbbd`） | roundb 版本；≤65536 字节拷贝并托管 deallocator（`NOCOPY_LIMIT = 0x10000`；原记 16 KiB，沿用了 `redwoodmetal.m:2405` 注释里的错数，见[判读口径 §3.6](../analysis/2026-10-28-roundc-reading-criteria.md)），大于阈值仍返回 nil |
| AIR 库 | `d7b9ced5` | freeze 与 roundb 同库，单一变量保证 |
| AIR 库（新，未上车） | `86f379dc`，源码 digest `ae0dc59b…` | 含 `prog_calls`/`prog_lookups`/`prog_builds` 三字段，等性能轮 |
| jobs | `rc.jobs.freeze` sha `a4af9a9f`（此前 `845fd77e`） | 现含第三个 framewatch（阈值 2 秒、6 次、靠前行推到约 150 秒起） |
| roundb payload | `ef3c82e1b58ea6db` | apfs 内三文件已核（驱动 `9d66dd36`、lsprobe 含 `cpu procs=`、AIR `d7b9ced5`） |

警告：`hackios-xnu-kernel/userland/obj/` 现在是半成品状态（display 的 compile-only 容器运行中断于头文件错误：`libredwoodmetal.dylib` 为 `cdb34c04`、`lsprobe` 不存在、`libredwoodair.dylib` 为 `2950f4d4`）。staging `root/` 与 apfs 未被动过。容器构建修好之前，不要从 `obj/` 做 staging 或打 apfs。

## 5. 构建线的两个已知故障

- `hackios-xnu-kernel/userland/build.sh:158`：`ld64` 不在 PATH 时自动置 `PREBUILT=1` 跳过全部编译，装箱步骤在条件之外，于是把旧产物打进 apfs。这是第七个「改了没生效」实例（freeze 轮 apfs 收 10 月 23 日驱动的根因）。已加断言（obj 必须比源新否则退出）。
- `hackios-xnu-kernel/xnu-deps/host/bin/ld64` 现在是指向容器路径 `/root/theos/toolchain/linux/iphone/bin/ld` 的符号链接（10-28 09:23 生成），在宿主机上是断链。它此前指向什么、由谁改的，未查。
- 容器内 `source xnu-env.sh` 后 `build.sh` 仍报 `src/input26_service.c:3:10: CoreFoundation/CoreFoundation.h not found`。待跑的诊断（同一条 docker 命令里换成这些打印）：`command -v xnu-clang; echo "$THEOS"; ls "$THEOS/sdks"; echo "$XNU_SDK_PATH"; ls "$THEOS/sdks/iPhoneOS16.5.sdk/System/Library/Frameworks/CoreFoundation.framework/Headers" | head`。怀疑方向：容器 theos 的 SDK 缺框架头，或 `xnu-clang` wrapper 用错了 isysroot。容器调用形如 `docker run --rm -v <仓库根>:/work hackios-dev:latest bash -c 'source /work/hackios-xnu-kernel/xnu-env.sh && …'`。

## 6. 下一步（按优先级）

- P1 bad access pc 定位：内核加 region 名与 exec 基址行并重建；device 离线把 212 条 bad access 与 17 对重起时刻对齐。产出决定 P2。
- P2 拷贝路径去留：落在我们 dylib 就修复保留（重点查 32 KB 固定分配点与 deallocator 时机），落在系统库就按「暴露既有缺陷」继续查并考虑暂时回退 `31f2d6b7` 保住显示形态。
- P3 容器 build.sh 修复，`obj/` 恢复可信；查 `ld64` 符号链接来历。
- P4 round C 组装：新内核（P1 两行）＋驱动（P2 决定）＋jobs 加崩溃报告收集（参照 crashlog 轮做法）＋驱动提交三计数（`rwa commit entry`、`rwa kernel entry`、`tl: s` 同一行每秒一条）＋ `poster_stores` 双名读数搭车。
- P5 冻结线：exec 基址行落地后给 tid 306 的 pc 命名；9/1001 扩展宿主死亡时刻表（相邻墙钟行夹逼法）；「主线程等的对象由谁持有」仍开放，chronod widget watchdog 只是时间贴合。
- P6 性能线（重启循环解决后）：长拖动覆盖出帧期的轮次＋新 AIR 库三字段＋`encode` 23 倍同口径核对＋帧密度判据（`tools/k90auto/frame_density.py` 已就绪，roundb 证明可用但该轮无判别力）。
- P7 外设与收尾：蓝牙 B0 轮、Wi-Fi stage-6 轮、镜像偏离清单、人感知项目清单交用户。

## 7. 各成员暂停时的在办事项

- display：容器诊断输出（P3）；内核 exec 基址行与 bad access region 名（P1，代码未写）；widget 宿主 9/1001 时刻表（P5）。
- device：bad access 与重起时刻对齐（P1 离线部分）；round C 打包与崩溃收集 jobs（P4）。设备 idle。
- perf：round C 三计数的判读口径设计；`crashlog`/`touchdiag`/`freeze` 洞内告警已补完（21 个三秒空洞全 0）。
- desktop：总账一行一项维护；`poster_stores` 新读数、`encode` 23 倍核对、`pipes/tex/blits` 打点、壁纸配置来源定性（均等下一轮搭车）。

## 8. 外部审阅文档的裁定

[UI 冻结与 fence 超时假设](../analysis/2026-10-28-ui-freeze-fence-timeout-hypothesis.md)（外部审阅会话）的核心假设经三条独立证据退出：九轮 `did not finish the` 零命中且两轮覆盖判据（单份环可容纳时长大于约 20 秒快照间隔、并集逐点覆盖空洞时刻）全满足；代码上 fence 超时后下一次 dispatch 会再睡 2 秒 ioctl（`air_metal.c:2748`/`:3703`），而 freeze 轮 15 次 dump 无 ioctl 类 pc、无驱动区间 pc；freeze 轮提交速率稳定 27 次/秒直到突停。「3.02 秒 ≈ 2 秒超时 + 1 秒收尾」在代码里没有固定 1 秒等待，属相加巧合。chronod 不是 15 秒空洞触发源（`nochronod` 轮空洞仍在、间隔 15.0 秒），「补 appprotectiond」的 ①d 轮已取消。审阅文档 §5（日志环覆盖率）与 §8（判读收进脚本）的建议已落地为 `round-stats.py` 的 `fence timeouts`/`ring coverage`/`swap holes` 三段固定输出。

## 9. 协议要点（新增部分，全文见运行协议）

- 轮次目录在 device 宣布收尾之前不读；读了必须标 partial 与截至快照号（roundb 实例：partial 读出 0 触摸/0 截图/45 帧，收尾实为 36/94/99）。
- `run-*.log` 只有 GUARD/RUN_STARTED/SAMPLED_SECONDS 数行属正常；轮次跑完与否看 `SAMPLED_SECONDS` 秒数约等于 RUN_SECONDS。
- 零命中要附环覆盖率，并写明并集口径还是单份口径（freeze 轮单份约 178 秒、并集 398 秒）。
- 窗口内命中数没有基率对照时没有信息量；判据写成洞内/洞外同长窗口之比或洞内独有取值。
- manifest 记「应该跑什么」、apfs 记「实际跑了什么」；核对对象是 apfs 内解出的文件。
- 行数、覆盖率、空洞一律以 `round-stats.py` 输出为准，不另算一套。
- `tl: p` 第二个字段是 FINGER、第三个是 TYPE；打印受 `RW_AGAIN` 节流，行数远小于事件数。
- `works each M` 是窗口均值；per-frame 与 per-batch 数值必须标注。
- 拿 `bbm29` 算帧率时分母只到 381.6 秒（后半段只有 `tl:` 打印没有交换）。
- Git 四处（顶层仓库、内核仓、`out/xnu12377` 的 `redwood26` 分支、`.userland.git`），全部不 push。

## 10. 对用户「原生性能能不能做到」的当前答复

能。吞吐证据：输入采样 60.1 fps、有帧时段 58.8～60.1 fps、每帧驱动 CPU 中位 2 µs/flush、GPU 每帧约 50 µs，16.66 ms 预算余量大。当前障碍全部是活性问题（冻结形态与重启循环形态），解决后才轮到每帧成本的占比修复。热侧 76 °C 截频与面板分频是物理约束，验收口径「不受热限制时 55 fps 加冷机满频时长」能容纳。

## 11. 已确认的事实错误与作废结论（2026-10-28 更正）

本节收本文已确认的事实错误与作废结论，正文保持原样。判别方式：更正能在原句内改一个值、且该段论证结构不因此作废的，正文已 inline 更正（§2 与 §4 的「16 KiB」拷贝阈值已原地改为 65536 字节）；更正会让该段论证整体作废、或要改多处互相依赖的数的，列在本节。每条给原值、更正值、依据、承载细节的文档链接。

- §2 SpringBoard 死亡代数。原值：「SpringBoard 14 代 pid（30、103、131、142、161、175、189、205、214、228、241、246、260、267）」。更正值：死亡 pid 集合 15 代（30、91、103、131、142、161、166、175、189、205、214、228、241、246、260），9/0 ×14、pid 161 一代 6/6；267 轮末存活未死，它的出处是 framewatch 的 dump 请求行与内核转储行的行中匹配。依据：device task-2 按 `redwood: proc SpringBoard pid <N> died on signal` 与 `redwood: SpringBoard pid <N> exited code -1` 两种行首匹配串实读唯一行，两集合一致；perf 按 exited 唯一行独立实读结果相同。不 inline 的理由：该句里 pid 列表、「各有 15 条 `exited code -1`」「每对间隔约 10 秒」三个数互相依赖，改一个要连着改另两个。细节见 [roundb 对齐](../analysis/2026-10-28-roundb-badaccess-alignment.md)。
- §2 周期方向。原值：「backboardd 先死 `11/11`（段错误），0.2～0.7 秒后 SpringBoard 死 `9/0`（被 SIGKILL），每对间隔约 10 秒」。更正值：稳态是 bbd 段错误 →约 10 秒后 sb 被杀 →0.2～0.97 秒后下代 bbd 段错误，后段 20/40/80 秒翻倍；0.2～0.7 秒（实测 0.2～0.97）是「sb 被杀 → 下代 bbd 段错误」方向，原文把两个方向混在一句里。依据：device task-2 逐对对齐 15 对死亡时刻。细节见 [roundb 对齐](../analysis/2026-10-28-roundb-badaccess-alignment.md)。
- §3 slide。原值 `0xb05000`。更正值 `0xbc54000`。依据：lead 独立核过，roundb 日志里 `slide 0x…` 只有这一个取值、出现 239 次，`0xb05000` 零命中。细节见 [roundb memmove 归因](../analysis/2026-10-28-roundb-memmove-attribution.md)（perf task-13，进行中）。
- §3 共享缓存上界。原值：「超出共享缓存上界 `0x2adb74640`」。更正值：该值是缓存 `__TEXT` 镜像区的上界，缓存真实映射区间是 `0x180000000..0x2c2cf4000`。依据：lead 独立核过。细节见 [roundb memmove 归因](../analysis/2026-10-28-roundb-memmove-attribution.md)（perf task-13，进行中）。
- §3 两个 pc 的距离。原值「相距 0x10c」。更正值 `0x114`（`0x2b0fb5ad4 − 0x2b0fb59c0`）。依据：两个已记录 pc 值直接相减复算，lead 核过。细节见 [roundb memmove 归因](../analysis/2026-10-28-roundb-memmove-attribution.md)（perf task-13，进行中）。
- §3 归属结论整体作废。原值：「该 pc 在缓存之上的私有映射里。候选：`libredwoodmetal.dylib`（241,488 字节）、`libredwoodair.dylib`（13,983,936 字节）、backboardd 主二进制。日志里没有各镜像的加载地址，现有数据判不了。」作废：pc 已定到 `libsystem_platform.dylib` 的 `_platform_memmove`（`+0x9c0` 是 `ldnp q2, q3, [x1]`、`+0xad4` 是 `ldr x6, [x1], #8`），待 perf task-13 复核。依据：lead 离线分析。细节见 [roundb memmove 归因](../analysis/2026-10-28-roundb-memmove-attribution.md)（perf task-13，进行中）。
- §1 与 §6 的 P1。原值：「第一优先动作是定位 roundb 里 212 条 bad access 的共同 pc `0x2b0fb59c0` 属于哪个镜像」（§1）、「device 离线把 212 条 bad access 与 17 对重起时刻对齐」（§6）。更正值：重起对齐实测 15 对（物理事件 15 条与 15 次段错误 1:1，212 是跨快照求和的原始行数）；镜像归属已由离线分析回答（见上一条），P1 剩余部分是取 `lr` 与 `x0/x1/x2`。依据：device task-2 对齐与 lead 离线归因。细节见 [roundb 对齐](../analysis/2026-10-28-roundb-badaccess-alignment.md)。
- §1 与 §2 旧冻结轮的时基混用。原值：「内容 131 秒定格、提交 273 秒停止」（§1）、「内容冻结（131 秒）与提交停止（273 秒）都在这之后」（§2）。更正值：提交停止的 273 秒是设备钟原值（该轮末次交换 `tl: s 3425 backboardd at 273031935`），轮内相对值是 126.3 秒；内容冻结的 131 秒来自截图轴（主机侧），本来就是轮内值，不改。真实先后是 settling (84.1, 105.9] → 提交停 126.3 秒 → 内容最后变化 (127.6, 131.1]，与 round C 同序，主机与设备钟的校准差在 3 秒以内。连带作废：由 273 减 131 得出的「内容冻结后提交又持续 142 秒」不成立。依据：device task-19 实测该轮设备钟零点 B≈146.7 秒，用 lsprobe 的 t=60 与 t=300 两行与最近的 `tl` µs 行夹逼，锚点差 239.5 秒对期望 240 秒。同一口径下 `tools/k90auto/jobs/rc.jobs.freeze:14-18` 注释里「3 秒洞每 15 秒从约 180 秒开始」的 180 也是设备钟，减 146.7 得轮内 33.3 秒，与 round C 和 round D 的周期洞起点 30.3／31.4 秒吻合；jobs 这一轮不动，那条注释等 round D 出结果后一并改。零点偏移不影响差值，所以 §2 那句「约 27 次/秒」与「提交在触摸结束后 25 秒才停」照旧成立。display 的 8 个 dump 时刻用墙钟锚，与 device 的 lsprobe 锚差 0.3 到 2 秒，settling 区间的结论不变。细节见 [round C 冻结形态](../analysis/2026-10-28-roundc-freeze-form.md)（device task-19，进行中）。
