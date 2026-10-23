# annibale 桌面交互、外设与性能调试案例

本文整理 2026-10-23 晚间至 10-24 凌晨的桌面运行结果。通用判断方法见[项目排查与协作手册](../plan/debugging-and-collaboration.md)，操作命令见[真机调试手册](../plan/device-test-playbook.md)，此前的启动问题见[启动案例](2026-10-23-boot-debugging-sop.md)。下文分别标明实测、源码确认和待验证范围，设备现状由负责实现的会话重新读取。

## 1. 阅读范围与当前边界

来源为 [Codex 调试会话](codex://threads/01a16907-fb8e-7961-916d-c4e38c11085d)。第一次整理截止到触摸响应确认与 `bootcpu=7` 启动失败；本次增量继续读到三个按键验收、loader v4 与高性能核心上线、softpipe 耗时定位、GPU 第 1 阶段 32 位读取成功，以及速度分档／SKU 和 BCM 字段布局开始核对的阶段。已核对 `returned 24374 0` 后恢复桌面的记录，以及随后补充的 Metal 路径说明。实现会话尚未结束，后续整理从第 9 节列出的未决问题继续。

| 功能 | 本次确认 | 结论边界 |
|---|---|---|
| 持续运行与恢复 | 取消 300 秒退出参数后继续运行；主机停止内核、读取合并日志、复用 RAM 系统盘并再次启动已实测 | 外设访问仍曾引起整机重启，重启后必须重新上传系统盘 |
| 壁纸与半透明 | 服务配置修复后壁纸出现；Mesa `softpipe` 路径启用后用户确认半透明 | 后续一轮壁纸扩展超时，背景再次变黑；长期稳定性和加载速度待验收 |
| 小组件 | 最新用户反馈顶部小组件已加载 | 未逐项验证内容更新和联网 |
| 触摸 | 坐标模式修改后出现连续触点日志，用户将「无响应」修正为「有响应，太卡了」 | 已确认输入能引起界面响应；延迟、坐标精度、多指和连续操作待测 |
| 电量 | BQ27Z561 多次返回有效读数，`RedwoodBattery` 发布约 95% | 用户仍报告 USB 连接期间缺少充电标志；实际充电状态未确认 |
| CPU 与性能 | 修复完整 MPIDR 传递后，`0x10100`、`0x10000` 两颗高性能核心在线；CPU 时间、慢调用与符号采样共同指向 softpipe 软件绘制 | 软件绘制仍有长耗时；核心切换的独立收益和完整输入延迟尚未量化 |
| 实体按键 | 启用 `buttons=1` 后，用户确认电源键锁屏／唤醒及音量加减均有响应 | 响应仍慢，连续操作与其他按键组合未逐项验收 |
| GPU 初始化 | 对齐的 32 位 QFPROM 读取及第 1 阶段返回通过，USB 可继续使用 | GPU 上电、固件运行、命令提交与实际绘制尚未在本轮验证；分档与频率表对应关系待查 |

用户要求优先处理触摸和卡顿，联网、摄像头、振动等留待可操作后调查。正常交互启动中的压测清理也已获明确要求。按键能够响应后，用户要求继续查清具体耗时，并提出 UniXNU 作为图形选型参考；后续重点转向软件绘制定位和 GPU 初始化，其他外设仍按原先顺序安排。

## 2. 同一画面现象需要按运行状态重新分类

### 时钟停止与时钟间歇更新

首轮桌面配置带有 `loader_return_after=300`。用户报告时间停在 11:21，主机读到 `result: returned 1361841 0`，屏幕保留内核返回前的最后一帧。此轮先检查运行状态就能解释静止画面，无需先修改定时器或时钟应用。

后续取消退出时限，用户观察到时钟指针每隔几秒更新一次。该现象确认界面仍在更新，调查应转向输入、调度、绘制和显示提交的时间；不能沿用上轮内核已退出的原因。用户起初认为触摸无响应，等待后确认有响应，也提示验收必须记录动作、等待时间和界面变化，防止过短观察窗口遗漏延迟响应。

主机会话已实测 `oem stop → result: returned → get_staged` 取得合并日志，然后复用同一 loader 生命周期中的系统盘运行下一份 payload。内核返回后的读取顺序见操作手册；屏幕上的旧桌面无法说明新 payload 是否启动成功。

### 壁纸缺失的两种已观察路径

最初缺失来自启动服务配置：[`mkjobs.py`](../../hackios-xnu-userland/userland/mkjobs.py) 的环境变量循环覆盖外层文件名变量，按需服务反复写入 `RWA_PACKED16` 文件，PosterBoard、chronod 等独立配置缺失。修复改用 `env_name`，重新生成得到 382 个按需服务，PosterBoard 与壁纸扩展随后启动。回归测试覆盖环境变量设置与未设置两种输入；旧脚本两个子用例均失败，修复版通过，见 [`test_mkjobs.py`](../../hackios-xnu-userland/userland/test_mkjobs.py)。后续遇到生成器报告数量正常，仍需核对实际文件名集合、服务标识和最终镜像内容。

原小镜像还缺少 `libredwood-gl.dylib` 与 `libOSMesa.8.dylib`。对照镜像加入 Mesa 26.2.5 库并使用 `gl=1` 后，日志确认 renderer 为 `softpipe`，用户确认半透明出现。该路径由 CPU 绘制，K90 GPU 尚未在此轮启用。服务修复与库补齐分阶段进行，分别检查服务启动和渲染日志比仅比较最终截图更有助于确定变化。

后续 `touch-latest.log` 已出现 `CollectionsPoster` 启动，但多次记录 `XPC_EXIT_REASON_EXTENSION_CHECK_IN_TIMEOUT`，用户再次看到黑色背景。此轮优先调查扩展启动超时；此前修复仍需通过镜像检查确认。调度、绘制和诊断开销对超时各有多少影响尚未分离，不能仅凭黑色背景恢复旧结论。

## 3. 外设地址、访问权限与诊断副作用

触摸初始化依次暴露了不同前提，已修复项保留来源与边界，详细过程见[运行记录](../progress/2026-10-23-runtime-debugging.md)：

| 检查对象 | 已核对内容 | 可复用的判断 |
|---|---|---|
| 机型专属 GPIO | annibale 没有旧机型的识别脚，`NO_STRAP=1000` 曾被诊断打印作为 GPIO 访问 | 占位值必须在访问前处理，诊断代码也要遵守板型约束 |
| RPMh command database | SMEM 扫描在 `0x81d9e004` 触发同步外部异常；设备树声明独立 `0x81c60000 + 0x20000`，修正后找到 `ldob12 = 0x40a00` | 明确资源范围后定点读取，不能从旧平台布局推导扫描范围 |
| GCC 时钟状态 | SM8750 的 AHB 偏移为 `0x23140/0x23144`，SE2 停止标志为 bit 31 | 名称相同仍要逐项核对寄存器偏移与位域 |
| TLMM GPIO | 厂商 DT 描述 `0x0f000000 + 0x202000`；主线 SM8750 GPIO 窗口为 `0x0f100000 + 0x102000`，寄存器按 GPIO 号乘 `0x1000` 访问 | 资源起点与 GPIO 寄存器起点分别计算，确认额外偏移已经包含几次 |

旧 TLMM 地址计算少了 `0x100000`，一次诊断输出停在 GPIO43 配置读取之前，随后设备回到 Android。改正后，`touch-fixed2/179.log` 记录同组 GPIO 和时钟读数，后续供电与 SPI 初始化继续执行。这些结果支持地址计算修复；此前各次重启的完整异常原因仍未全部取得。

Android 中读取 `pinmux-pins`／`pinconf-pins` 的整组调试命令也曾随后失去 USB 连接，用户报告重新回到 Android。已有记录未区分具体是哪项读取，也未取得足以确认权限异常的故障栈。后续不重复整组读取，先从保存的 DT、驱动和单项状态核对。文件读取可能调用驱动并访问硬件，操作影响需按实现判断。

同一触摸设备的 DT 还声明 `trusted-touch` 与 `tvm` 环境。该配置提示需要检查所有权和访问路径；它本身不能确定上述重启由权限拒绝造成。日志确认 GENI `interface 0x1`，驱动据此判断 FIFO 接口禁用，改用 GPIO 模拟 SPI 后读到芯片身份。这次成功覆盖替代传输路径，硬件 SPI 恢复及性能仍需单独验证。

## 4. 芯片通信成功后继续检查报告模式

`touch-ready.log` 已读到 Goodix `BERLIN`／`9916K` 固件、`1156 × 2510` 坐标范围，并开始每 `8000 us` 检查中断线，但统计仍为 0 个报告。`ui-clean/179.log` 又记录报告地址 `0x10308`、头长 8、点长 8、命令地址 `0x10174`，重复版本校验有效，报告内容却全为零。稳定身份读取与有效校验支持通信可用，下一步应检查工作模式和报告条件。

Android 日志记录 `goodix_ts_probe IN THP`。主会话参考 MiCode `vendor_xiaomi_proprietary_touch-driver` 的 `warsaw-w-oss` 分支 `warsaw/goodix_9916k/goodix_brl_hw.c` 中 `goodix_htc_enable()`：关闭原始帧上报，再开启坐标上报。该参考来自同型号触摸芯片的其他机型分支，适用性还要通过本机返回和事件验证。

[`redwood_goodix.c`](../../hackios-xnu-kernel/xnu/files/bsd/dev/redwood_goodix.c) 随后增加 `0x90`、数据字节 `02 00` 和 `0x91`、数据字节 `01` 两条命令，并按数据长度计算命令长度和校验。新版 `coordinate-live.log` 出现连续的 `goodix: finger 0 at ...` 坐标；用户先反馈无响应，随后确认有响应但延迟很大。该结果支持这轮固件、配置与传输路径下坐标上报及界面响应已通；冷启动、复位后重配、多指和坐标精度尚未完成验收。

下一次排查按「驱动开关 → 芯片身份与校验 → 报告模式 → 有效触点 → `/dev/redwood-touch` → 用户态注入 → 界面响应时间」逐层核对。芯片命令应答、内核坐标日志和实际手势分别记录，不能仅靠 `touch screen ready` 完成输入验收。自动解锁脚本产生的手势也要与用户手指操作分开识别。

实体按键出现了相同的反馈修正。启用 `buttons=1` 后，日志取得按下与释放事件；用户先确认电源键能锁屏和唤醒，随后补充音量加减也有响应。PMIC 的 PON `0x013` 和音量上 GPIO6 `0x18d` 分别匹配通道 581、610，类型及输入配置检查通过。此处 GPIO6 属于 PMIC，定位硬件需同时记录控制器、外设地址和通道。后续优先量化输入后的显示延迟，不再重复以「没有任何按键事件」为前提调查。

## 5. 电量来源与充电状态分别验证

Android 实际设备树及 I²C 设备 `uevent` 确认电量计为 TI BQ27Z561，地址 `0x55`，控制器为 QUP1 SE5，SDA/SCL 为 GPIO52/53。同一总线还连接地址 `0x6e` 的充电泵。旧 PMIC FG/SDAM 搜索路径未取得有效电量，调查应先确认真实硬件与数据来源。

本次 [`annibale_battery.c`](../../hackios-xnu-kernel/xnu/files/bsd/dev/annibale_battery.c) 通过 GPIO 开漏传输读取标准命令，采样后恢复引脚配置，检查读取完整性及数值范围再发布。所谓读取电量仍会修改传输用的 GPIO 状态，需要检查总线占用、异常退出和恢复；本次未验证所有并发访问情形。

`battery-first/179.log` 最初得到温度 `65535`，样本被拒绝；后续多次取得约 `95%`、`4377–4381 mV`、`34.75–34.85°C`，`battery-live.log` 确认 iOS 电源服务收到 95%。前面的 UEFI 缓存读取失败与后面的 BQ 有效样本属于两个数据来源，应按发布者和时间解释日志。

当前实现用有符号电流推导 `status`，并用正电流设置 `external`。用户报告 USB 已连接且正在充电，界面仍未显示充电标志；日志同时显示负电流。USB 连接、电池净电流、充电器在线状态和充电策略需要独立来源验证。此次有效电量读数只支持采样与发布已完成，充电识别和控制继续保留为待验证项。Android 先前显示 99%、本轮原始 SOC 为 95%，采样时间和处理路径都不同，无法据此量化误差。

## 6. 性能检查先确认测试输入和统计范围

### 清理负载与解释计时

用户要求清理正常启动中的压测。主会话最初把 `cpu_test 240` 解释为持续压测 240 秒，检查 [`cpu_test.c`](../../hackios-xnu-userland/userland/src/cpu_test.c) 后修正为等待 240 秒再执行固定工作量。解释参数前应核对解析和调用，不能从数字猜测持续时间。

源 `rc.jobs`／`rc.jobs.unlock`、kernel overlay 和打包目录的 `/etc/rc.jobs` 随后同步，重建 `out/handoff-ui-clean.apfs`；交互启动取消 `touch_lat=1` 与 `-enable_kprintf_spam`。该镜像仍保留自动解锁任务，`init.c` 中的 `hello_dyn` 检查也独立存在。验收记录应列出实际移除的启动任务和最终输入；日志缺少某个字符串只能辅助判断，因为采集覆盖范围有限。

清理后的 `coordinates-return.log` 有一条前 30 帧统计：`547554 us a frame`，其中命令提交约 `1036 us`、等待 `0 us`、拷出约 `840 us`。[`eagl.c`](../../hackios-xnu-kernel/userland/src/eagl.c) 用 `frame_begin()` 到 `frame_end()` 的经过时间累计该值，包含这一段期间的调度等待。该数值不能直接换算成稳定桌面帧率，也不能全部归为某个绘制函数的 CPU 时间；应区分启动期、稳定桌面和输入后的帧，并结合调用栈、CPU 时间与用户观察。

两颗 CPU 的早期日志曾为 `1 of 2 processors are running`。[`GenericARMPE.cpp`](../../hackios-xnu-kernel/xnu/files/iokit/Kernel/GenericARMPE.cpp) 对带 L2 access penalty 标记的非启动 CPU 默认延迟 28 秒启动；完整返回日志随后记录 `cpu 1 online` 和 `2 processors running`。即时统计和完整生命周期日志需要一起看，初期单核状态不足以判断第二颗启动失败。

早期切换 `bootcpu=7 cpus=2` 的试验返回 `no-such-core 6 0`。`bigcores/179.log` 显示 loader 尝试 MPIDR `0x700`，固件返回 PSCI 错误，内核未进入。旧源码按 `core << 8` 换算地址，设备树记录 CPU 地址为 `0x0–0x500` 及 `0x10000/0x10100`。该次失败没有产生性能对照，也不能从状态名称推断硬件缺少对应核心。

后续修复采用逐核心 MPIDR 表，并在内核 CPU 查找、secondary 入口及 GIC SGI 编码中保留 Aff2；设备生成脚本也改为输出完整表。只修改 loader 的启动地址仍会让其他消费者截断核心身份。主机测试覆盖地址映射和 SGI 编码，真机 `prime/179.log` 则记录 `0x10100/0x10000` 注册及 `2 of 2 processors are running`，USB 停止、日志返回和再次启动也通过。该结果验证 loader v4 与 `handoff-mach-affinity` 的配套组合，全部 CPU 与其他设备仍需各自验收。

### 从现象定位到具体执行阶段

五颗 CPU 在线的一轮中，`input-confirmed.log` 的两个 5 秒窗口记录 `backboardd` 使用约 90.3% 和 88.8% 的单核 CPU 时间。`profile-live.log` 多次记录 `glDrawElements` 耗时 0.3–1.9 秒，同阶段 framebuffer 驱动的上屏耗时约 2–3 毫秒。另一轮 `gl-profile-live.log` 取得 134 条慢绘制记录，最大为 `1756698 us`。这些记录来自不同窗口，能够区分主要耗时所在层次，不能相加成为一次手势的完整延迟。

为解释用户线程地址，临时诊断库用 `dladdr(OSMesaCreateContextAttribs)` 取得本轮 Mesa 加载基址，再匹配带符号的构建副本。比较 Mach-O `__text` 大小和 SHA-256 后确认代码段一致，不能仅靠相同库名选择符号表。17 个有效显示线程 PC 落在 `_tgsi_exec_machine_run`、`_exec_tex`、`_fetch_source`、`_store_dest` 等解释执行与纹理采样函数。

[`user_exception_trace.c`](../../hackios-xnu-kernel/xnu/files/osfmk/arm64/user_exception_trace.c) 读取线程最近保存的用户寄存器；运行线程的记录受最近进入内核的时机影响。17 个 PC 的分布只能说明这组样本，不能作为全部执行时间的比例。结合进程 CPU 时间与逐调用计时，当前严重卡顿的主要耗时已定位到 softpipe 软件绘制；其他开销的占比及高性能核心带来的独立改善仍未量化。高性能核心上线后的首帧仍记录约 `730478 us` 的慢绘制，增加核心或切换核心尚未消除长耗时。

诊断镜像生成还发生过一次输入不完整：`copytree()` 默认跟随 `RedwoodAudio.driver` 的目标环境符号链接，宿主解析失败；后续 shell 命令仍继续打包和启动。改用保留符号链接的复制方式并检查前置命令失败后，重新生成带诊断库的镜像，才取得有效基址记录。复制、替换库、打包和上传分别检查后置条件，不能用最终命令成功概括整串操作。

## 7. GPU 首阶段先验证访问与诊断条件

### 状态响应与阶段暂停也可能失效

旧 loader 多轮出现 `getvar result` 返回空值，同时日志长度继续增长。源码用日志尾部临时格式化状态字符串；日志缓冲满后，格式化没有可用空间。v4 的 `set_result()` 改用缓冲尾部保留的临时范围，并恢复原日志内容和长度。由此取得有效状态后再判断内核运行情况；本次读取的 `getvar screen` 分支仍依赖日志剩余空间，尚未取得对应修复验收。

首轮 `adreno8=1` 复位前只采到 framebuffer 附近日志。GPU 调试器用 `adreno8_step == adreno8_newest_step` 决定是否暂停，但旧代码在步骤成功后才更新后者，首步访问前的等待没有执行。修复提前设置目标步骤，另用 `completed` 保存已完成步骤，供后续观察与资源停止条件使用。目标阶段、当前阶段和已完成阶段需分别表达，否则诊断等待或清理可能依据错误状态执行。

启用逐访问记录并延长停留后，`gpu-step1-traced/077.log` 保留了 `0x221c8138` 字节读取前的标记，之后设备复位并重新枚举 loader。首次缺失日志只能说明采集覆盖不足；修正诊断逻辑后的记录才把调查范围缩小到这次访问。

### 访问宽度、字段提取和字段含义分别核对

[Linux v6.17 QFPROM 实现](https://github.com/torvalds/linux/blob/v6.17/drivers/nvmem/qfprom.c) 使用对齐的 `readl`，并调整 nvmem 单元的偏移和位位置。本机 DT 的 `bits = <0 9>` 描述所需字段，硬件总线访问宽度还需按驱动契约核对。修复将两次字节读取改成一次对齐的 32 位读取，再按 `0x1ff` 提取低 9 位。新版实测读到 `0x400400e8`，随后 GCC 与 RPMh 资源读取完成，主机取得 `result: returned 24374 0`，USB 可继续使用。

这轮同时修改读取宽度和字段掩码，确认的是该组合通过第 1 阶段；访问方式有上游实现支持，单次成功仍不覆盖其他寄存器、GPU 上电、固件运行或绘制。原复位的底层异常状态未完整取得。

字段读取成功后还需检查解释。提取的 `speed_bin` 为 232，DT 频率表按 `qcom,sku-codes` 的 0／2／3 选择；现有代码直接比较后回退到最高 900 MHz 的表，映射尚未确认。RPMh BCM 读数也出现 `width=15872`、`version=73` 等待核对值，应回到厂商结构布局、字节序和单位检查。取得非零数值或较低频率表，都不足以确认可以继续应用电源与频率配置；本轮尚未执行对应上电验收。

## 8. 图形选型按实现层次与验收范围比较

用户提出 UniXNU 的 Metal 路径后，实现会话检查了 NativeMetal、metal2vulkan、Turnip 与 NativeAdreno 的职责和接口。[UniXNU 的公开驱动说明](https://unixnu.com/drivers/native-adreno)报告 A740 上的 Metal 桌面合成，并记录首次 pipeline 编译停顿。其结果为评估提供了实现参考，K90 的 A830 仍需独立完成电源、固件、地址映射、提交和同步验证。

当前 GLES 桌面实际使用 CPU 上的 softpipe；GLES 和 Metal 的接口名称都不能单独说明执行硬件。比较路径需分别检查 API 覆盖、着色器转换、内核服务 ABI、缓冲与 fence、IOSurface 和显示提交。现有 `RedwoodGPU` 与 UniXNU `NativeAdreno` 的用户客户端契约不同，替换动态库前需要核对每层的生产者和消费者。实现会话提出优先验证 Metal→metal2vulkan→Turnip，同时保留现有 GLES 对照；本次尚未把该路径接入 K90。

评估结果按编译、提交、完成和实际内容分别计数。本仓 [`docs/air.md`](../../hackios-xnu-userland/docs/air.md) 记录 456 模块中 321 个入口编译为机器码、30 个入口在旧设备 GPU 完成执行；这些结果不能推广到 K90 的系统着色器覆盖。验收新路径还需分别测量首次编译、缓存后运行和输入到显示延迟，保留正常镜像与恢复入口。

## 9. 后续增量整理入口

原始材料仍留在本地 `hackios-handoff` 调试目录，长期保存位置沿用忽略提交的 `docs/progress/evidence/2026-10-23-handoff/`。本次只读取这些材料，没有移动、删除或提交原始文件。关键定位名为 `touch-ready.log`、`touch-latest.log`、`ui-clean/179.log`、`android-touch/live.dts`、`battery-first/179.log`、`battery-live.log`、`coordinate-live.log`、`coordinates-return.log` 和 `bigcores/179.log`；这些文件名用于关联对应输入，不能据此推定设备仍运行该版本。

本次增量核对了 `input-confirmed.log`、`profile-live.log`、`gl-profile-live.log`、`profile-symbolized.txt`、`prime/179.log`、`gpu-step1-traced/077.log` 和 `gpu-qfprom32` 目录。实现会话将对应采样和产物清单保存到忽略提交的 `docs/progress/evidence/2026-10-24-input-rendering/`。精确命令与产物选择以操作手册及对应清单为准。

继续整理优先读取 `speed_bin`／SKU 映射、BCM 描述布局、GPU 上电与命令提交的实际结果，以及独立充电状态来源、交互延迟对照和 `getvar screen` 缓冲修复。实现会话仍持有内核、用户态和其他文档的未提交修改，本轮仅提交本专题与协作手册，不更新子模块指针。
