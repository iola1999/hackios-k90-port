# HackiOS K90 移植独立评估报告

审查日期：2026-10-23，北京时间。审查对象：顶层工作区及 kernel、userland 两个子模块，重点覆盖启动、构建、镜像装配、图形测试、真机诊断和工作安排。本轮审查完成；后续修复应按本文记录的提交和产物重新验收。

## 1. 总体评价

当前工作已经建立了可运行的 QEMU 基线，并完成了一批有实际用途的离线准备。独立实验确认：已提交内核能够启动 iOS 16.5 的 SpringBoard，73 片 XNU 补丁可以在原始 Apple 源码上重新应用，部分 AIR 转换与运行检查可以复验。这些成果值得保留。

K90 真机工作仍处于早期启动验证阶段。当前最大的限制是缺少可靠的启动阶段观测，同时源码、构建产物、待测镜像和测试手册之间存在不一致。已经发现会让下一次真机实验失败、或让实验结果被误判的具体问题。继续增加外设代码之前，应先修正这些问题，建立能重复执行的最小真机实验。

从教师和工程评审的角度，我对研究方向持肯定意见，对现阶段真机验收结论保持保留。离线开发的产出速度较快，真机验证的覆盖范围需要追上。项目管理应分别记录已实现、已编译、已在 QEMU 运行、已在 K90 实测四种状态。

| 评价角度 | 判断 | 对后续工作的含义 |
|---|---|---|
| 已有技术基础 | 上游已经提供 XNU 与 iOS 用户态适配及 QEMU/redwood 路线；本项目完成了主机适配、自建内核和 K90 相关扩展 | 描述成果时分别列出继承的基础与本机新增结果，便于判断哪些问题已被解决 |
| 调研方法 | 设备树、公开驱动、构建记录相互对照，有多次主动纠正地址和硬件归属的记录 | 继续保留来源和原始输出；把静态资料中的声明与真机观测分别记录 |
| 工程组织 | 双子模块、固定提交、补丁 series、产物哈希已有实际作用，本轮也复验了其中一部分 | 下一步集中解决产物组合和失败传播，优先于继续扩大脚本或抽象层 |
| 硬件移植成熟度 | loader 平台、镜像传输和外设代码有准备，K90 的可靠阶段日志及完整启动仍缺验收 | 当前应按早期 bring-up 管理，先完成一个可重复的最小启动实验 |
| 测试方法 | 有具体输入、LLVM 对照、软件运行和读回检查；部分测试存在失败遗漏或覆盖缩减 | 测试结果必须带输入集合、配置与跳过原因；默认关闭的新驱动只获得关闭路径的回归 |
| 推进顺序 | 设备不可操作期间做离线准备有实际用途，GPU 和外设扩展也有已记录的批准 | 真机恢复后按启动依赖安排实验，避免用新增代码量估算距开机目标的剩余工作 |

## 2. 审查基线与范围

| 对象 | 本轮固定的提交 |
|---|---|
| 顶层工作区 | `66b6ec18f56d9862a8072d1c3494a71e609b05d5` |
| kernel | `0b19a3a9b727b1abeab610a3afeeab95e066a95c` |
| userland | `68e1e7ffc91bca966e3dcc580591603611ce160e` |

开始审查时，内核已有未提交的 Adreno 8 文件和三个既有文件的修改，顶层已有未跟踪的用户态行数审计文档。本轮使用上述提交的仓库外快照进行实验。审查期间原工作区的内核 prebuilt 又发生了变化，因此本文的 QEMU 结论只适用于表中的固定提交及下述镜像哈希；在做的 GPU 代码没有经过本轮运行验收。

收尾核对时，顶层已更新到 `6ddc915`，kernel 已更新到 `80c7f11`，新增 Adreno 8 分片实现和对应 prebuilt；userland 仍为 `68e1e7f`。已重新比较本文问题涉及的 10 个源码文件，均与审查快照逐字节一致，因此这些源码问题在新提交下仍然存在。新提交的 GPU 行为和新 prebuilt 未在本轮独立运行。

除本文外，本轮未修改原仓库文件，未提交代码，未执行手机启动、刷写或分区读写。实验目录为 `review-workspace/`，包含源码快照、脚本、日志和截图。主机实验中的 adb 为记录参数的模拟程序。

本文使用以下优先级：P1 表示应在下一轮相关真机实验或验收前处理；P2 表示应在后续工程整理中处理。确定性缺陷与尚未验证的硬件假设分别说明。

## 3. 已执行的独立实验

| 实验 | 结果 | 能确认的范围 |
|---|---|---|
| 固定提交的默认 loader 重新编译，配合已提交内核和现有系统镜像运行 QEMU | 通过：进程运行约 452.84 秒后返回 0；180、300、400 秒采集画面；300 秒截图可见完整 SpringBoard 桌面，日志记录 `kernel returned` | QEMU 启动、软件显示和返回 loader 的路径可运行；日志中未发现 `panic(cpu` |
| 手机 loader 使用 `-DDIRECT_PHONE_PLAT` 重新编译 | 通过：编译成功，产物 70,144 字节 | 手机配置可以编译；执行情况仍需真机确认 |
| 从 Apple 的 `xnu-8796.121.2` 重放 `xnu/apply.sh` | 通过：73 片补丁全部应用；109 个新增文件与快照逐字节一致 | 补丁拆分后的源码重建路径可用；本轮没有重新编译整个 XNU |
| 主机 AIR 二进制与源码核对 | 通过：构建树中的 17 个 AIR 源文件与 userland 快照一致 | 后续主机测试使用了与本轮源文件相符的已有构建产物 |
| `loweringcheck.py` | 通过：20/20；其中 18 个与 LLVM 比较，2 个按预期拒绝 | 已覆盖的转换语义成立 |
| `argbufruncheck.sh` | 通过：修复实验副本的 macOS 签名后，20 项检查全部通过 | 参数缓冲相关的主机运行检查通过 |
| 四个系统 metallib 的 `corpus.py` | 通过：456/456 可读取；321/456 可转换 | 271 个 fragment、47 个 kernel、3 个 vertex 全部转换；135 个 visible library 模块未直接转换，不能仅按总百分比判定缺陷 |
| 三组缺少 ir3 的检查 | 注意：fbfetch 7/7、vattr 16/16、discard 2/2，退出码均为 0，部分检查显示 SKIPPED | NIR 或接口检查仍在执行，GPU 指令检查存在空缺 |
| `texopcheck.py` 的语料对照实验 | 未通过：无 rootfs 时为 27/27、退出 0；提供现有 rootfs 后为 99 项、74 符合、18 WRONG、7 refused、退出 1 | 测试集合受语料目录影响；当前完整纹理测试未通过 |
| GL 六个产物的 SHA-256 | 通过：6/6 与清单一致 | 当前 `userland/obj/` 的六个文件身份可核对；运行语义仍需对应测试 |
| loader 构建失败注入 | 未通过：子步骤返回 42，总构建入口返回 0 | 构建失败传播存在缺陷，见 F04 |
| `check.sh` 管道失败注入 | 未通过：模拟 CPU 比较返回 42，`cpu_rc` 仍为 0 | 测试总入口可能遗漏失败，见 F05 |
| 现有 C 镜像解包与 system 镜像长度对照 | 未通过：相差 16,384 字节；按现有 tail 算法会跳过 APFS 开头 | 下一次按当前文件组合执行会读错镜像位置，见 F01 |
| 暂存脚本默认拒绝与 `--yes` 分支模拟 | 通过：默认返回 1；注意：`--yes` 直接生成 userdata 裸写命令 | 默认确认要求有效；确认之后仍缺少块占用和镜像一致性校验 |
| 原始分区探针函数配合内存 BlockIo | 未通过：自动执行五次首块覆盖，未恢复原内容 | 确认正常 USB 入口中的存储副作用；真实设备写入是否成功未在本轮验证 |
| 原始 rdfile 调用分支配合加载记录函数 | 未通过：连续内存不足时先调用加载，随后才拒绝 | 确认范围检查顺序错误；本轮未执行真实越界写入 |

实验过程中遇到的两个环境问题已经单独排除：修改实验副本的动态库路径后，macOS 因签名失效终止程序，重新对副本签名后参数缓冲测试通过；QEMU 的 PPM 输出每行带对齐填充，直接交给普通转换工具会出现画面错位，按仓库截图脚本已有的行长度处理后画面正常。两项均未列为仓库缺陷。

## 4. 问题清单

| 编号 | 优先级 | 结论 | 状态 |
|---|---|---|---|
| F09 | P1，先处理 | USB 诊断模式自动向五个分区首块写入探针，包含 misc 和 metadata | 原函数配合内存模拟确认 |
| F10 | P1 | rdfile 镜像写入 RAM 发生在连续内存容量检查之前 | 源码和分支模拟确认 |
| F01 | P1 | C 镜像中的 rdfile 长度与当前 system 镜像不一致，tail 读取起点偏移 16 KiB | 离线复验确认 |
| F02 | P1 | SM8750 识别保护依赖尚未核实的寄存器解释，识别失败时允许旧驱动继续执行 | 源码确认，硬件读值待确认 |
| F03 | P1 | 自动化诊断丢弃 fastboot 的 getvar 输出，成功响应也可能被判为失败 | 源码与输出通道实验确认 |
| F04 | P1 | 总构建入口没有可靠传播失败，annibale 默认调用也没有设置手机 loader 编译参数 | 失败注入与参数记录确认 |
| F05 | P1 | 测试入口遗漏管道失败，缺少测试依赖时的汇总也不完整 | 失败注入与真实测试确认 |
| F06 | P1 | userdata 尾部暂存仍可能覆盖 Android 数据，确认开关未解决分配与并发问题 | 源码与命令模拟确认，未对手机写入 |
| F07 | P1 | 当前真机显示和启动阶段的部分结论超出了已有观测 | 文档与代码交叉检查，待真机验证 |
| F08 | P2 | 工程质量的若干结论过强，版本记录和排期需要围绕实际消费路径调整 | 文档与代码交叉检查 |

### 处置状态表（Lead 裁决，2026-10-27 起持续更新；成员只改自己名下行，改前先重读本文）

图例：已闭环 · 处理中（负责人/任务/stepper）· 暂缓（复杂或收益不足，附理由）· 按设计（现行机制即结论）

| 编号 | 状态 | 负责人/任务 | 说明 |
|---|---|---|---|
| F09 | 完成（kernel efe0e55） | adreno / task-19 stepper 3 | 自动路径 inspect_storage() 只读零写；写探针收进显式 oem probe 且五步非破坏 保存→写→验→恢复→验（日志 /tmp/task19/probe-simulation.log）；boot_a 回退仅在显式 oem logwrite 运行期间生效（F09LW 标记段+flag 门），自动 flush 无 logdump 时走 console 回显、USB 面纯读，oem logwrite 已入 busy 拒收列表；host harness 五例全过（logdump 恒优先/无 flag=NULL/flag 期=boot_a/命令结束回 NULL），日志 /tmp/task19/logwrite-simulation.log。闸门（Lead）：双编译变体过、QEMU 420s SpringBoard×2 零 panic；新增 oem probe/oem logwrite 两命令，命令面见 playbook |
| F10 | 完成（kernel efe0e55） | adreno / task-19 stepper 1 | 布局与全部容量/溢出/目标区域检查抽成 plan_layout()，run_kernel 仅在检查通过后才触内存与读盘；host 分支测试逐字提取 loader.c F10 标记段，7 例（含验收四输入：刚好/差一页/远小于/异常长度）拒绝路径零加载调用，日志 /tmp/task19/rdfile-order-simulation.log；loader 两编译变体零告警。闸门（Lead）：QEMU 420s 正常路径行为零变化，kernel efe0e55 入库 |
| F01 | 已闭环（流程性） | Lead / 轮末重打 | 设备轮最终 c.img 重打本就按**实际 system 文件**重新生成 rdfile 参数并记录 kernel/loader/root/system 产物清单（既定流程），16 KiB 偏移随重打消失；loader 内自动长度/哈希对账的**代码加固** 暂缓——重打纪律先收账，观察一轮再定是否值得改 loader |
| F02 | 已闭环（观测先行部分，kernel b77eb0c） | drivers / task-17 stepper C | 观测一行已入库：redwood_soc_is_sm8750() 首调无条件打印原始 TCSR0 整字（`redwood: TCSR0 @0x1fc0000 reads 0x%08x`，每 boot 恰一次），QEMU 闸门已见空窗值 0x00000000 按预期现形（strings+控制台双确认，SpringBoard×2 零 panic）；K90 应回 0x26a/红杉应回 360 的真机读数待设备轮日志对账，为三态实证的唯一遗留收账点；评审建议的**可信身份源+fail-closed 重构**保持暂缓（复杂：需 SMEM/固件协议核实，先用真机读数收编报告质疑，再定重构是否必要） |
| F03 | 已闭环（kernel 75fb322 + 父仓，host 验收全过） | adreno / task-20 | tools/device-test.sh 重写同批入库：`tools/device-test.sh` F03 标记段，`getvar product 2>&1` 连退出码一起收，rc124 判超时、rc≠0 判死链（附首行错误原文）、product 含 xnuloader 判 loader 在位、is-userspace:yes 判 fastbootd、其余判 LK，类别变化才播报，PROBE_TRIES 可覆盖便于测试；宿主仿真用 stub 把应答写在 stderr（与真 fastboot 一致）跑通五输入（loader 在位/LK/fastbootd/rc3 失败/超时），日志 /tmp/task20/f03-f05-simulation.log |
| F04 | 已闭环（kernel 75fb322 + 父仓，host 验收全过） | adreno / task-20 | kernel 75fb322：xnuloader/build.sh 按变体分产物（带 -DDIRECT_PHONE_PLAT 只写 loader-phone.efi，默认只写 loader.efi 并落同内容 loader-generic.efi 别名，trap 9 结构性不可能）；common/build.sh 经 conf 新增 LOADER_CFLAGS 把宏传给 loader 步骤，loader/images/mkpayload/mkxnuimg 逐步 die；验收：编译失败注入 rc1 且旧 boot.img mtime 不动，交替构建互不覆盖（phone 构建后 loader.efi 哈希不变、别名与主产物一致；注意本机工具链本身不可比特复现，同变体重编译哈希稳定在宿主从来不成立），记录 shim 证明 qemu 入口 EXTRA_CFLAGS 为空、annibale 入口宏生效，annibale 全量入口装载的是 loader-phone.efi（payload 内 phone 独有字符串命中），redwood 行为零变化 |
| F05 | 已闭环（kernel 75fb322 + 父仓，host 验收全过） | adreno / task-20 | tools/device-test.sh 同批：`tools/device-test.sh` 入口加 pipefail；相关 grep 全部读尽管道替代 grep -q（40 万行 stub 流上旧形在 pipefail 下被 SIGPIPE 打成 141 把在位设备误报缺席，新形无恙，对照见同一仿真日志）；入口新增依赖汇总，fastboot/adb/timeout 与 xnu-annibale-log.img 缺哪个报哪个一次性列全后 exit 1，剥 PATH 实测 MISSING 行正确 |
| F06 | 按设计 | Lead | RAM-only 零持久化 + stage-system.sh --yes 用户同意门是既定裁决；「分配与并发」层面的重设计暂缓（同意门在，风险受控） |
| F07 | 已闭环 | mesa / task-21 | 已审查入库：trials 分级口径段+事实 1/2/7 观测/归属两级、playbook 间接指纹+boot_a 取证标注当前不可用+行 C 指纹说明+四阶段分级段、hw-map GOP 待验证注（随本次父仓提交） |
| F08 | 已闭环 | mesa / task-21 | 已审查入库：mesa-rebase §9.1 收紧到符号名称层+§10.3 GL 观察项排期、内核审计零风险→低（F02 收账点）+Mini 两行改判、porting-plan 间接指纹+UEFI 构建输入记录待办、gpu-plan 状态对齐实现期、README 上游状态行（Lead 补批）（随本次父仓提交） |


### F09：USB 诊断模式带有自动覆盖分区首块的探针

位置：`hackios-xnu-kernel/xnuloader/loader.c:404–442,4161–4165`。

入口在 payload 存在、USB 模式开启且 `usb_start()` 成功后，直接调用 `flush_log()`、`probe_boot_a()`，然后才进入 USB 命令循环。`probe_boot_a()` 依次调用五次 `probe_one()`，目标为 `boot_a`、`misc`、`metadata`、`logfs`、`xbl_sc_logs`。每次写入从 LBA 0 开始的 4096 字节，内容为 `XNUPROBE-<分区名>-001` 和填充字符，随后只检查读回内容，没有保存或恢复原始块。

这里没有单独的诊断授权参数，也不受 `stage-system.sh --yes` 控制。文档把变体 A 列为 RAM 诊断路线时，遗漏了 loader 自身的存储副作用。此前五个分区没有观察到内容改变，反映的是当时写路径的行为。后续修复 UEFI 或存储驱动后，这些调用可能开始生效。

建议在下一次真机实验前，先从正常启动和 USB 诊断路径中移除这组写探针。若确实需要验证 BlockIo 写入，应使用已经明确授权并预留的测试区间，包含原始内容保存、错误处理和恢复验证。尤其需要检查修复存储驱动后是否会使旧的诊断调用突然产生写入。`flush_log()` 使用 boot_a 作为回退日志位置，也需要与 boot_a 正在承载启动镜像的用途协调。

将原始 `probe_one()` 和 `probe_boot_a()` 提取到主机程序，用内存实现的 BlockIo 替换固件服务，实际记录到五次 LBA 0、4096 字节写入，最后一个块未恢复。日志在 `logs/probe-simulation.log`。本文尚未认定此前分区已经损坏。本轮没有对真实设备执行任何探针。

### F10：rdfile 在检查目标内存容量之前开始写入

位置：`hackios-xnu-kernel/xnuloader/loader.c:2964–2999`，`rdfile_load():482–491`。

`run_kernel()` 取得已申请的连续内存后，在 2985 行调用 `rdfile_load()`。该函数立即对整个目标范围执行 `memset`，随后分块读取和复制镜像。检查 `win_size` 是否足以容纳镜像、设备树和预留空间的条件，直到 2997 行才执行。因此，如果最大连续空闲块小于 system 镜像需要的空间，函数可能先覆盖已申请范围之外的内存，之后才输出容量不足。

主机分支模拟使用原始 2964–2999 行的控制流程，设置已申请窗口为 256 MiB、system 镜像为 2,492,219,392 字节，并把实际加载替换成只记录范围的函数。结果是先调用越界加载，再返回容量不足。模拟没有分配或写入越界内存。日志在 `logs/rdfile-order-simulation.log`。

该情形与当前真机计划直接相关：测试手册已把连续空闲窗口不足列为待确认条件。建议在任何清零、磁盘读取或复制之前，完成镜像长度、地址加法溢出、窗口大小和全部目标区域的检查。验收应覆盖窗口刚好足够、差一页、远小于镜像、异常长度四种输入，并确认拒绝情况下加载函数完全没有被调用。

### F01：C 镜像与 system 镜像的长度不一致

位置：`hackios-xnu-kernel/tools/stage-system.sh:16–23`、`hackios-xnu-kernel/xnuloader/loader.c:473–486`、`docs/plan/device-test-playbook.md:17`。

解包当前 `xnu-annibale-c.img` 后，payload 中的参数为 `rdfile=userdata:2492203008:tail`。当前 `userland/system.apfs` 的长度为 2,492,219,392 字节，两者相差 16,384 字节。

暂存脚本按当前文件长度计算写入起点 `TOTAL - SZ`，loader 按 payload 中的旧长度计算读取起点 `total - size`。在分区容量一致的条件下，读取会从文件内部偏移 16,384 字节开始。只读检查确认：原文件偏移 32 处为 APFS 的 `NXSB`，偏移 16,384 后的前 64 字节全零。即使 BlockIo 读操作成功，内核收到的镜像开头也已经错误。

同一 C 镜像内的 kernel SHA-256 为 `4cd48d23…`，与提交 `4f5ab24` 的 prebuilt 完全一致；本轮已提交基线中的 kernel 为 `9482540d…`。因此 C 镜像尚未包含之后的机型保护改动。它内置的 root.apfs 仍为 4,194,304 字节，本轮 QEMU 使用的 root.apfs 已为 11,255,808 字节。这些文件需要作为同一套输入验收。

建议：重打手机镜像时，从实际 system 文件生成 rdfile 参数；在执行任何传输前，比较镜像内的长度、实际文件长度和哈希。先用一份小型产物清单记录 kernel、loader、root、system、命令行和构建配置即可。验收条件是：换一个长度不同的 system 文件时，流程必须拒绝继续或重新生成对应 payload；正确组合能够读回同一 APFS 头部。仅更新文档中的容量数字无法解决此问题。

### F02：机型识别保护尚不能承担硬件隔离职责

位置：`hackios-xnu-kernel/xnu/files/bsd/dev/redwood_input.c:60–85`；旧驱动入口的 `redwood_soc_is_sm8750()` 调用；`docs/progress/2026-10-23-offline-prep.md:49`。

当前函数读取物理地址 `0x01fc0000` 的低 16 位，与 618 比较。

- 注释把 `drivers/soc/qcom/socinfo-tcsr.c` 和 `TCSR_ID_MASK` 作为依据。此次公开源码核对未找到该文件或宏。
- 实际 Linux `socinfo.c` 从 SMEM 的 `SMEM_HW_SW_BUILD_ID` 读取 `info->id`，`qcom,ids.h` 将 SM8750 的 SoC ID 定义为 618。
- 设备树中的 `qcom,msm-id=<0x26a ...>` 能确认所声明的 SoC ID，仍需另外确认硬件寄存器地址、字段和编号之间的对应关系。
- 来源：[Linux socinfo 实现](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/refs/heads/master/drivers/soc/qcom/socinfo.c)、[SoC ID 定义](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/refs/heads/master/include/dt-bindings/arm/qcom,ids.h)。

代码还明确规定：映射失败时令 `number=0`，返回 false。未知读值同样返回 false。调用方随后继续旧驱动流程，因此识别失效会失去保护。QEMU 的成功回归只能覆盖 QEMU 上该分支的结果，无法确认 K90 能命中 618。

具体影响包括：旧按键驱动在设置 `touchscreen` 时可默认启动；旧 cpufreq 的 DDR 写操作则还要求 `cpufreq` 开启，不能仅凭 `ddr` 默认值为 2 就认定每次启动都会写 DDR。参见 `redwood_buttons.c:544–556`、`redwood_cpufreq.c:563–579`。

建议：下一次真机启动前，明确平台身份来源，并在身份未知时停止执行机型专属寄存器操作。可选用已经核实的固件协议、SMEM 结构或显式平台交接字段，具体选择应结合当前启动代码确定。验收至少包括 K90、原 redwood、QEMU、未知身份四种情况。当前缺少 K90 对应地址的实测值，本文不认定设备已经发生错误写入。

### F03：USB 诊断脚本会忽略正常的 getvar 响应

位置：`tools/device-test.sh:35–39`。

`probe_loader()` 把 `fastboot getvar product` 的 stderr 重定向到 `/dev/null`，随后只在 stdout 中搜索 `xnuloader`。Android fastboot 的变量输出使用 stderr。输出通道实验中，模拟成功响应 `product: xnuloader` 写入 stderr 后，当前管道返回 1；合并 stderr 后返回 0。[Android fastboot 源码](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fastboot/fastboot.cpp)。

这会使 USB 已恢复的设备仍被自动脚本判为无响应，从而继续执行错误的排查步骤。此结论针对自动脚本，不能据此推翻此前手工执行 getvar 得到的无响应记录。

建议：保留输出和退出码，再判断响应内容；同时区分 LK、fastbootd、loader、命令失败与超时。用模拟成功、未知 product、失败响应三个输入即可在主机上验证，无需刷机。

### F04：总构建入口不能可靠交付正确的设备配置

位置：`hackios-xnu-kernel/common/build.sh:35–59`，`hackios-xnu-kernel/common/lib.sh`，`hackios-xnu-kernel/xnuloader/build.sh`。

`common/build.sh` 没有启用遇错退出，也没有逐步骤检查所有返回码。实验在独立目录中保留原入口和配置，将 loader 构建脚本替换为返回 42 的模拟脚本，跳过其他步骤，执行 QEMU 构建入口。入口最终返回 0。真实装配中若旧 loader 仍存在，就有继续使用旧文件的条件。

另一次参数实验执行 annibale 构建入口，模拟 loader 打印收到的 `EXTRA_CFLAGS`，结果为空。该入口没有自动设置 `-DDIRECT_PHONE_PLAT`。而 `loader.c:4111–4135` 显示：GOP 缺失时，只有带此宏的构建才选择 annibale 并设置备用显示参数。手工流程能够构建手机版本，总入口仍未完整表达这个要求。

建议：先修正失败传播和配置传递，保留现有脚本结构；再将默认 loader 与手机 loader 输出分到不同路径。验收时应故意让编译失败，确认入口返回非零且不打包旧产物；交替构建 QEMU 与 annibale，确认两种配置各自选择正确产物。没有必要为此引入新的构建框架。

### F05：测试通过条件与实际覆盖范围存在缺口

位置：`hackios-xnu-userland/tools/air/check.sh:64–69`、`fbfetchcheck.py:263–266`、`vattrcheck.py:439–443`、`texopcheck.py:477–491,529–584`。

第一处是确定性错误：`check.sh` 的 CPU 比较使用 `python3 ... | tail ... | sed ... || cpu_rc=1`，没有 `pipefail`，也没有像其他检查那样读取 `PIPESTATUS[0]`。模拟第一段返回 42 时，末段成功导致 `cpu_rc=0`。失败会在这一层被遗漏。

第二处是覆盖统计问题：缺少 ir3 时，fbfetch 和 vattr 的相应分支返回成功，同时打印 SKIPPED。本轮复验分别得到 7/7 和 16/16；discard 同样得到 2/2。保留可以运行的 NIR 检查是合理选择，但总报告应分别记录通过、失败、跳过、缺少语料。当前退出码无法表达 GPU 指令检查的缺失。

第三处是环境相关的测试集合：`texopcheck.py` 自动扫描自身工作树的 `ios165/rootfs`，再加入固定的额外声明。没有 rootfs 时仍有 27 项检查并返回成功；接入现有 rootfs 后变为 99 项，其中 74 符合、18 WRONG、7 refused，返回 1。这解释了 27 项与 99 项两种结果如何产生，原报告中将 27/27 仅描述为历史子集仍不充分。

对于 18 个 i16 WRONG 和 7 个 f16 refused，已有文档将其归因于 softpipe 的窄类型限制。这是需要单独记录和验证的解释。当前脚本实际返回失败，且只有特定的 `nir_to_tgsi` 错误才进入排除分支。建议建立逐项列出的预期限制，并保留其他差异导致失败的行为；实际 Adreno 输出仍需设备测试。

验收条件：模拟一个 CPU 比较失败，总入口必须失败；移除 ir3 后，汇总明确显示跳过数；移走语料目录时，输出明确说明覆盖减少，完整验收配置应拒绝缺少语料的运行。

### F06：userdata 尾部暂存需要重新确定存储方案

位置：`hackios-xnu-kernel/tools/stage-system.sh:2–24`、`docs/plan/device-test-playbook.md:72–87`。

脚本开头仍声称不改 userdata 头部即可保证 Android 的 `/data` 不受影响。实际代码把当前镜像直接写到 userdata 末尾，没有查询 F2FS 的块分配，没有预留目标区间，也没有阻止 Android 并发使用这部分空间；容量和设备序列号还是固定值。模拟 `--yes` 分支确认，实际调用序列只有等待设备、push、裸设备 dd、删除临时文件。

默认拒绝执行和文档中的确认要求已经降低了误运行风险，应该保留。确认操作本身无法验证目标区间是否可写。内核用 RAM 作为系统盘，也仍然需要审查此前将镜像放到存储设备上的步骤。

建议优先恢复 USB 向 RAM 传输的路线；需要存储暂存时，先确定拥有明确用途、容量和生命周期的区间，并验证 Android 当前布局、写入后的读回结果以及后续启动期间的使用关系。`super` 中的空闲 extent 也需要明确保留和更新策略。下一次试验前应解决 F01 的长度问题，并继续维持对 userdata 裸写步骤的暂停。

### F07：显示与启动阶段需要更直接的验收

位置：`docs/progress/2026-10-23-annibale-device-trials.md:7–13`、`docs/plan/device-test-playbook.md:62–68`、`hackios-xnu-kernel/xnuloader/loader.c:4121–4135`、`docs/analysis/annibale-hw-map.md:86–92`。

现有记录将 USB 消失、驻留时长、共用 VID/PID 和 getvar 无响应用于推断固件运行阶段。这些现象可以帮助缩小排查范围，但不能唯一确定 BootShim、EDK2、loader 或内核分别运行到了哪里。记录中已经纠正了 fastboot reboot 回显和错误串口的解释，后续应继续按相同标准审查其他间接现象。

GOP 缺失时，代码固定使用 `0xFC800000`、1440×3200、每行 5760 字节。设备树同时包含 1440×3200 的默认面板节点和用于生成 XML 的 1156×2510 面板节点。现有材料尚未给出 LK 本次启动实际选择的模式、stride、像素格式与接管后的扫描状态。保留内存地址相同，仅能支持该内存区可以定位；仍需验证面板是否继续扫描以及软件写入能否显示。

建议先用很小的诊断镜像输出明确阶段标记，随后验证静态色块或文字的地址、尺寸、格式和缓存处理，再挂载完整 iOS 镜像。若屏幕输出仍未确认，USB 日志应继续保持较高优先级。下一轮成功条件应能区分至少四个阶段：loader 已运行、内核已运行、系统盘已挂载、SpringBoard 已显示。

### F08：工程质量评价和工作安排需要收紧表述

位置：`docs/analysis/mesa-rebase-2026-10.md:119–125`、`docs/analysis/linecount-audit-2026-10.md:9–27`、`docs/plan/porting-plan.md`、`README.md`。

Mesa 文档用导出符号集合相同来说明交叉构建与主机构建等价。导出集合只确认符号名称这一层，不能确认类型布局、调用约定、行为、着色器结果或设备适配。当前可以确认的是构建流程已完成、产物可识别、部分主机测试通过；报告应保留这一范围。

行数约定有助于限制新文件增长，但按文件行数拆分，未必能减少共享状态和维护成本。行数审计把若干原机型驱动列为零风险，依赖的是 F02 中尚待验证的机型保护；MiniIOSurface 和 MiniIOMobileFramebuffer 又属于图形启动的实际执行路径。风险应按调用关系和产物变化判断。建议保留新文件的 1000 行要求，旧文件优先在行为修改时按职责拆分，每次改动提供对应回归。

文档之间还存在状态冲突：顶层 README 仍描述原先的上游跟进方式，规划已记录策略变化；GPU 计划开头仍写仅作调研，进度已进入实现；测试手册同时保留日志写分区流程和 BlockIo 写失败的说明。应先明确当前入口、待测产物和有效步骤，再整理历史过程记录。设备暂时不可用时开展 GPU、Mesa 和外设准备有合理用途，但下一次真机窗口应优先处理观测和启动，减少一次同时启用多个新驱动的情况。

UEFI 也需要进入同一份构建输入记录。当前 Mu-Silicium 位于被忽略的独立工作树，HEAD 为 `87416d23…`，存在 BootShim、Mu_Basecore 等本地状态；顶层两个子模块的指针无法单独记录这些输入。文档已有 annibale UEFI 构建说明和补丁应用脚本，本轮未重建该 FD，也未判定这些修改是否全部可以由脚本恢复。建议记录 Mu 提交及子模块状态、应用的补丁、合并 DTB 和 FD 哈希，并在独立目录验证一次完整恢复流程。

## 5. 处理难度、复杂度与修改风险

下面评估的是采用最小修复方案时的工作量和风险，属于工程判断。实现难度关注需要修改的逻辑和接口数量；验证难度关注能否在主机上确认修复，以及是否依赖真机状态；修改风险关注修复可能破坏的现有行为。问题未修复时的后果与修改本身的风险分别考虑，例如撤下自动分区写探针的修改风险较低，继续保留该调用的后果却可能很严重。

| 问题 | 实现难度 / 复杂度 | 验证难度 | 修改风险 | 最小处理范围与主要依赖 |
|---|---|---|---|---|
| F09 自动分区写探针 | 低。调用点和五个目标都明确 | 低。用本轮 BlockIo 模拟确认正常启动路径没有探针写入；真机只作后续确认 | 低。移除探针会减少诊断输出；日志保存路径需要另作选择 | 先移除正常 USB 入口中的覆盖探针，重新构建 A 镜像并核对产物；需要写测试时另定明确的测试区间 |
| F01 镜像长度与产物不一致 | 低到中。单次重打包容易，持续保证多个产物一致需要调整装配与传输脚本 | 低到中。长度、哈希、payload 内容和 tail 偏移均可主机验证；最终启动仍需真机 | 中。影响 system 读取起点和内置 root/kernel 组合，旧镜像仍存在时容易继续选错 | 从实际文件生成参数，传输前验证一份小型清单；依赖安全的传输或暂存方案，暂不通过写 userdata 验收 |
| F03 getvar 输出被丢弃 | 低。局部处理标准错误输出和返回码 | 低。正常、错误、无响应模拟即可覆盖主要分支 | 低。主要影响诊断判断；需防止错误文本被误判为正常 product | 修正输出捕获并按完整响应识别设备阶段，保留原始输出供排查 |
| F04 构建失败与机型参数 | 中。涉及总入口、设备配置、loader 选择和打包步骤 | 中。需要故障注入、旧产物存在场景、QEMU/annibale 交替构建 | 中。脚本被多个设备共用，粗略增加 `set -e` 可能改变原有条件判断 | 显式传播关键步骤失败，将设备参数传到 loader；独立输出路径可以随后加入。无需更换构建系统 |
| F05 测试失败和覆盖统计 | 中。管道返回码修复简单；跳过、语料缺失、窄类型限制需要逐项定义验收语义 | 中到高。主机控制流程可完全模拟；GPU 指令和部分纹理语义仍需设备 | 中。过宽的预期失败规则会隐藏新缺陷，过严的规则会使可运行的主机检查全部中止 | 先修返回码和语料清单，再记录通过/失败/跳过；按具体用例维护限制说明，保留完整验收模式 |
| F10 先写 RAM 后检查容量 | 中。需要整理范围检查顺序，并覆盖加法溢出和多段内存布局 | 中。边界模拟可覆盖拒绝分支；QEMU 可验证正常启动；真机确认实际连续窗口 | 中到高。位于每次启动都会执行的 loader 路径，错误修改会阻止启动或覆盖其他内存 | 把所有目标区域的合法性检查移到任何清零、读取和复制之前；保留现有数据布局，暂不同时拆分 loader |
| F02 机型识别保护 | 中到高。复杂度取决于选择固件、SMEM 或显式平台字段；会影响多个驱动入口 | 高。K90、redwood 和 QEMU 的身份来源及未知分支都需要验证；手头缺少两种真机的共同验证环境 | 高。过宽放行会执行错误寄存器操作，过严拒绝会使原设备功能失效 | 先停止依赖未经核实的寄存器解释；选一个能说明来源和生命周期的平台标识，明确未知状态。避免同时改名、拆驱动和修改 ABI |
| F06 userdata 暂存 | 高，取决于路线选择。继续做共享存储裸写需要处理分配、并发、恢复和系统更新 | 高。必须核对实际设备布局及恢复条件；单纯模拟无法验收数据保全 | 高。错误可能影响 Android 用户数据或可启动性 | 保持暂停。USB RAM 路线的存储改动较少，但 USB 修复仍有独立难度；预留存储区间需要另行确定使用和恢复规则 |
| F07 真机显示与阶段观测 | 高。参数、固件接管、缓存和面板扫描状态可能同时影响结果 | 高。核心结果只能在 K90 上确认，需要可以重复进入和退出的设备状态 | 中到高。只增加阶段日志影响较小；修改显示时钟、供电或控制器状态的风险更高 | 分开做日志与显示。先验证阶段标记和静态色块，再启动完整 iOS；不在同一轮加入多个外设 |
| F08 文档与工程安排 | 文档修正为低到中；存量代码拆分需按文件单独评估 | 文档为低；涉及 loader、显示服务和 ABI 的重构为中到高 | 文档低；大文件拆分可能达到中到高 | 先统一当前状态、有效命令和验收范围。保留行数约定；历史文件的拆分随实际维护需求安排，不集中插入下一次真机实验之前 |

建议将工作分成三批。第一批处理 F09、F03、F01 及 F04/F05 中的失败传播，主要依靠主机实验验收，能够立即减少无效或危险的真机操作。第二批单独处理 F10 和 F02，先验证边界与身份，再做设备实验。第三批处理 F06/F07 的实际传输、观测与显示，集中使用真机窗口。

时间估算应在确定 F02 的身份来源、F06 的传输路线和可用真机窗口后再做。现阶段将这些硬件问题统一估成几个小时或几天，会忽略访问权限、固件行为和反复恢复设备的成本。可以先要求每个任务提交最小改动方案及验收样例，再安排具体工期。

## 6. 建议的下一阶段验收顺序

1. 先处理 F09 的自动分区写探针和 F10 的内存检查顺序。固定一套构建输入和待测产物，处理 F01、F03、F04、F05；继续保持 userdata 写入暂停。主机上先验证失败能被正确报告，镜像之间的长度和哈希一致。
2. 明确 K90 的平台识别来源，确认未知身份不会执行原 redwood 的硬件写操作。为诊断镜像保留最少的功能开关。
3. 取得可靠的 loader 和内核阶段记录。屏幕若承担日志用途，先完成静态输出测试；USB 若恢复，先验证命令、日志和 RAM 传输。
4. 验证完整系统镜像在 RAM 中的长度和内容，再推进挂载、launchd、SpringBoard。分别记录每一步成功的判据。
5. 触摸、振动、按键、电池和手电逐项启用。GPU、Wi-Fi 和相机按各自硬件前置条件推进；每次增加功能前保留可以恢复的已知可运行组合。

## 7. 最新动态

审查开始时的远端查询中，私有顶层与两个 `k90-port` 分支的提交与本轮基线一致。最近提交主要完成 Mesa 26.2.5 构建装配、AIR 测试适配、XNU 补丁拆分、机型保护和行数审计。审查期间，18:42 的 kernel `80c7f11` 提交了 Adreno 8 的五个实现文件及私有头，18:44 的顶层 `6ddc915` 更新了子模块指针和进度记录。本文保留这一最新动态，同时明确运行实验使用的是此前固定基线。

公开 userland 上游当前 HEAD 为 `a79ff077…`，可以确认新增了 `thermald`、`var_store bootok` 和独立的 `thermal_probe`。`thermald` 将内核温控状态传递给 iOS，`bootok` 服务于上游自己的启动状态协议；移入本项目时需要相应内核接口和存储布局，当前未进行合入。[thermald 与 bootok 提交](https://github.com/oosexgang/hackios-xnu-userland/commit/fcc3214c7f72edba71484288e96a39deb4c29961)、[thermal_probe 提交](https://github.com/oosexgang/hackios-xnu-userland/commit/a79ff0772a3454fd1ef127e181e5b3bce6c9ce18)。

## 8. 复验材料索引

所有实验文件保存在仓库外的本地审查工作目录，下表按该目录下的相对路径定位。本文没有将 Apple 系统镜像加入仓库。

主机工具版本：QEMU 11.0.1、Apple clang 21.0.0、LLVM 22.1.7。本轮 QEMU 使用单核 cortex-a76、7 GiB 客体内存和 TCG；没有启用 GPU 硬件路径，也没有验证 K90 外设。AIR 复验使用已有主机构建副本，核对源文件后执行测试；本轮没有从零重建 Mesa 交叉工具链。

| 内容 | 文件 |
|---|---|
| 初始提交、状态和差异 | `logs/initial-state.json`、`logs/*-initial-diff.patch` |
| 收尾提交与相关源码一致性 | `logs/final-state.json`、`logs/final-source-check.json` |
| QEMU 参数、输入哈希、运行结果 | `logs/qemu-manifest.json`、`logs/qemu-review.log` |
| QEMU 桌面截图 | `logs/qemu-300s.rowstride.png` |
| 两个实验运行脚本 | `experiments/qemu_review.py`、`experiments/offline_review.py` |
| XNU 补丁重放 | `logs/patch-replay.log`、`logs/patch-replay-summary.json` |
| C 镜像与 rdfile 检查 | `logs/phone-image-inventory.json`、`logs/rdfile-consistency.json` |
| 分区写探针和内存检查顺序模拟 | `experiments/probe_simulation.c`、`experiments/rdfile_order_simulation.c`、`logs/probe-simulation.log`、`logs/rdfile-order-simulation.log` |
| 构建与管道失败注入 | `logs/loader-failure-propagation.log`、`logs/pipeline-failure.log` |
| annibale 参数传递 | `logs/annibale-loader-flags.log` |
| fastboot 输出通道 | `logs/fastboot-output-routing.json`、`logs/android-fastboot.c` |
| 测试结果 | `logs/*check*.log`、`logs/corpus.json`、`logs/corpus.md` |
| GL 产物哈希 | `logs/gl-hashes.json` |
| 外部源码核对 | `logs/primary-source-check.json`、`logs/linux-socinfo-google.c`、`logs/linux-ids-google.c` |
| Mu-Silicium 状态 | `logs/mu-state.json` |

QEMU 输入的 SHA-256：kernel `9482540dfb57edb9d7e52d4ccf36a9c7aab908c3af58ed0fc78b84020f1b0c94`；root `cc746d976053e6580f096410fd3192f0cd3f8a3c7977e97142472c16bfb28a46`；system `f0d18b3382305cec5f63a8e1fff3bfe557be854d04b7190821c16e0232deb7cb`；本轮重新编译的默认 loader `8242991c7a7a8c4129c5fe09d0b7e0062f4df16b56d71ac09148694146f737f7`。
