# iOS 26 显示与响应时间调查（2026-10-26）

目标为 iOS 26.6.2（23G90）在 K90 上通过 GPU 桌面验收。当前 QEMU 软件绘制用于启动和接口排查；数秒级手势响应、灰色图标、白色组件及黑色壁纸均未通过体验验收。GPU 为必需项，Metal 按系统实际接口推进，Turnip 的独立验收继续保留。运行输入与各轮结果见[QEMU 记录](../progress/2026-10-26-ios26-qemu.md)。

## 1. 当前计时范围

`q26-input26-smp2-fixed` 使用两颗 neoverse-n2、TCG、14 GiB QEMU RAM、12 GiB 请求窗口，内核 SHA-256 为 `41888cad8bbc3ba9fa05959a9cf0d987e3e7191b51cd6fded3ebbddcf510c908`。根盘仍为单核正式轮的 `63990569e96217cfafaefc81494e37929f7398c3d96e247ece4b8f54b0ee9ddf`，未包含 PosterBoard。当前生成目录的后续变化不影响该冻结输入。

两次横向手势各有 27 条触摸记录，从输入服务读取首条到派发末条分别耗时 3044.92／3508.19 ms；最大队列等待为 2367.81／3127.75 ms。相应窗口内 driver 的图像复制耗时中位数为 1.318／1.302 ms，最大值为 1.670／1.414 ms。`tl:v` 的 shown 到 done 包含 drawLayer，帧提交之前的用户态处理继续单独计时。

两段窗口分别只有 7／5 个提交画面，相邻提交帧间隔中位数为 361.436／569.018 ms，最大值为 1265.736／638.928 ms，全部间隔超过 33.333 ms。这些窗口从触摸产生到末条事件派发，覆盖有限的操作阶段；它们没有覆盖完整动画，也不能外推 K90 帧率。原始统计为忽略目录 `hackios-xnu-kernel/out/ios26-resume/touch-frame-timing.json`。

`q26-input26-profile` 保持双核及同一用户态任务集，运行 600 秒并正常返回。计时服务 SHA-256 为 `1607e2ed5c4e5824e6ce094eeb03d2d6f6d9b0a99b6203e6fe711b3a48ae7b8b`，最多采样 128 条触摸；完整镜像哈希保存在 `out/ios26-resume/q26-input26-profile-manifest.json`。首个横向手势的 27 条记录中，事件构造累计 2.989 ms，派发 API 累计 1742.260 ms、中位数 56.821 ms、最大 271.748 ms，派发期间输入线程 user/system CPU 增量合计 21.831 ms。线程 CPU 差值包含查询边界的部分开销；末条事件之后的查询另耗时 131.611 ms，未计入该条 API wall 时间。原始统计为 `out/ios26-resume/profile-first-gesture.json`。

23G90 的 `IOHIDVirtualServiceClientDispatchEvent` 在序列化后获取 client 递归锁，随后调用 MIG。该调用使用 `mach_msg(options=1, send_size=0x40, rcv_size=0, rcv_name=0)`，只发送消息。现有结果支持继续检查锁竞争、Mach 发送队列等待和调度延迟，尚未分配各部分耗时。20 秒进程采样窗口的双核 CPU 使用合计约 198%，SpringBoard 为 77.9%、iconservicesagent 为 58.4%、launchd 为 27.9%、backboardd 为 25.5%，输入服务为 0.1%；窗口平均值不能确定单次派发的等待原因。

`q26-input26-qos` 运行 600 秒并正常返回，使用相同任务集，把输入主线程及 HID 回调队列请求的 QoS 调为 `USER_INTERACTIVE`。对照产物 SHA-256 为 `9fa6ef0d1611eb3587cd61e6d56759c9dd6c58e28348b66a7b864df889e44c5d`，根盘为 `14df31eed59a7add64dc41aa6c8e9bde65daec9b244f9c71e3afb9644b0a0159`；逐文件比较确认只替换 `/bin/input26-service`，内核、系统盘和手势脚本与 profile 轮一致。线程及队列的请求等级读回均为 33，线程设置返回 0。`___ulock_wait2` 样本需结合调用者确认具体锁；`TH_RUN` 的寄存器来自上次保存的用户状态，不能直接计算瞬时热点占比。反汇编与地址表保存在 `out/ios26-resume/input26-qos/analysis.txt`。

三次手势各包含 27 条记录，下表比较 profile 轮与 QoS 对照。前两次为横向操作，第三次为控制中心手势；单位均为毫秒。数字取自各轮 540 秒日志，完整统计保存在 `out/ios26-resume/q26-input26-{profile,qos}-metrics.json`。

| 项目 | profile 第一／二／三次 | QoS 第一／二／三次 |
|---|---|---|
| 首次读取至末条派发完成 | 1755.796／2037.588／2266.368 | 229.296／224.118／376.184 |
| 最大输入队列等待 | 1353.524／1814.752／1873.386 | 17.596／21.238／147.040 |
| 派发 API 累计 wall 时间 | 1742.260／1781.571／2058.791 | 145.863／120.353／342.390 |
| 派发区间输入线程 CPU 增量 | 21.831／25.522／25.894 | 29.124／24.696／27.018 |

QoS 轮的首手势实际生成时长为 228.088 ms，profile 轮为 293.902 ms；宿主和客体调度都可能影响时序。两轮 20 秒窗口的双核总 CPU 使用均约 198%。该对照支持优先级对输入等待有明显影响，但同时调整了主线程与回调队列，尚未区分两者贡献，实际动态优先级也未采集。第一轮手势的五次线程栈均落在派发区间之外，主线程正在读取触摸设备，不能据此判定派发期间的等待类型。

420 秒截图仍为桌面第一页，本轮横向翻页未通过；540 秒截图显示控制中心，灰色图标、白色组件、黑色壁纸和控制中心背景异常仍存在。QoS 先保留为实验输入，下一轮单独检查主线程优先级及完整手势处理。输入吞吐改善与显示正确性分别验收。

共享内核的 `ustacks_task` 已增加独立 `ustate:` 行，在 `splsched → thread_lock` 内读取 state、block_hint、sched_pri、base_pri、req_base_pri，解锁后输出，原用户栈格式保持不变。

- `TH_WAIT` 配合 hint 4 可识别端口发送等待，配合 hint `0xa` 可识别用户锁等待；后者还需用户调用链确认具体锁。
- `TH_RUN` 仍包含执行中与运行队列中的线程。
- 8796／12377 字段和锁序已核对。
- 12377 构建已通过，产物 SHA-256 为 `6b7f1665fa6ce5a39b43e79a849dc08216b23406cf66f4d033987054de1bb871`，20,208,608 字节；相对 CPU-order 产物的 20 项实际输入仅变更 `user_exception_trace.c`。
- 8796 构建也已通过，产物为 `b6bbf613bf24bbbc694a074bd1ca90d457fb25000b16c6be4d9a6eb3c6ce7e06`，15,491,024 字节。
- 12377 的 `q26-ustate-boot` 已运行 60 秒并正常返回，三次采样均取得独立状态行，输入主线程在读等待，三项优先级均为 31；8796 尚未运行新增诊断。

后续输入对照先使用 `kernel12377-ustate` 与未修改的 profile 根盘，在首个手势附近采集主线程状态，再换仅主线程请求 QoS 的根盘。后者为 `out/ios26-resume/input26-main-qos-root/root.apfs`，SHA-256 `beff35588ed850b4bd1dcd9de5719da281c1e111e907e58ce900e91dcdc4c585`，仅替换输入程序为 `5d682cc3729a9cd1d1f142453456dcee3ca1b334a63fbdc6c6408f7db0394e49`，回调队列配置保持原样。两轮需使用相同采样参数，随后再组合已验证的输入和显示改动。该对照尚未运行。

`q26-waitstate-base` 使用诊断内核和原 profile 根盘运行 450 秒并正常返回，参数增加 `ustacks=input26-service ustacks_at=359 ustacks_ms=20 ustacks_count=400 ustacks_threads=1`。400 个主线程样本覆盖 365.432138～374.302130 秒。首个手势的读取／派发窗口为 370.930014～374.799900 秒，其中取得 152 个样本，全部为 `TH_RUN`；151 个样本优先级为 `31/31/31`，一个为 `46/31/31`。147 个样本落在单条事件 read→sent 区间。没有采到 `TH_WAIT`，仍无法排除采样间隙及末尾未覆盖的约 498 ms 内发生短暂等待。`TH_RUN` 同时包含执行中和运行队列中的状态，不能直接换算为纯排队时间。

源码核对确认 `thread_read_times → recount_thread_times` 只读取已记账累计值，不主动补当前查询尚未结束的内核片段；本构建启用 `PRECISE_USER_KERNEL_TIME=1`，EL0 进出和线程切换都会更新 user/system 累计值。因此派发返回后的查询能覆盖已完成派发的 CPU 执行，区间仍包含相邻查询边界的部分时间，不能给出精确阻塞比例。后续将以相同采样参数比较仅主线程 QoS 的根盘；`q26-waitstate-main-qos` 已运行 450 秒并正常返回。原始分析为 `out/ios26-resume/q26-waitstate-base-analysis.json` 与 `q26-waitstate-base-window.json`。

仅主线程 QoS 对照使用相同内核、根盘任务和 400 次采样参数，实际优先级在全部样本中为 `37/37/37`，请求／读回等级仍为 33。首个手势各有 27 条记录，生成时长为 226.696 ms，首读至末条派发为 227.592 ms，最大排队为 25.534 ms；基线对应为 231.768／3869.886／3303.764 ms。手势窗口取得 11 个样本，其中 9 个为执行或排队状态，2 个为其他等待，保存用户栈仍需按各样本解释。该结果支持将主线程 QoS 请求加入输入服务，回调队列的显式配置保持原样；请求上下文可能影响回调的实际 QoS，当前没有排除这部分继承作用。正式源码及默认 obj 已更新为该验证输入，binary SHA-256 为 `5d682cc3729a9cd1d1f142453456dcee3ca1b334a63fbdc6c6408f7db0394e49`。

原 `y=0.85` 手势后，390 秒截图仍为第一页。395 秒经 QMP／virtio 追加 `y=0.55`、25 次 MOVE 的 200 ms 手势后，410 秒截图已到第二页；日志收到 27 条触摸，实际生成时长 230.414 ms、首读至末条派发 238.342 ms。两次操作的位置及注入入口均不同，不能直接认定某一个因素导致差异。后续用同一 `rwtouch` 入口检查中部短手势，并与显示改动组合验证。该轮 420 秒截图位于追加手势之后，不能用于验收原先的低位置手势。

## 2. RenderBox 与图标生成

图标服务的 306.398／484.771 秒样本均执行 RenderBox 函数 `0x196b2e4d0`；分别位于反向和正向邻像素扫描，上层调用和递归层不同，不能把两次采样间隔计为一次请求耗时。该函数处理半精度像素，输入来自 CGBitmapContext 的 vImage_Buffer，临时缓冲宽高各增加 2、像素为 64 bit。循环主体约执行 `4×W×H` 次更新，未发现按收敛条件重复执行的循环。读取该函数栈帧的 `FP-0x98` 与 `FP-0x110` 可核对输入和临时缓冲的 data、height、width、rowBytes，尚未采集这些运行值。

`TextureIOError.usingSoftwareRenderer` 出现在图标完成后的可选分层数据序列化。`ISGenerationRequest generateImageReturningRecordIdentifiers:` 先取得平面图，再请求 layerData；序列化拒绝后仍以 CGImage 和空 layerData 建立图像及缓存记录。已检查的序列化函数没有重试循环，错误次数不能直接换算成生成失败次数或 CPU 耗时。

灰色占位另有明确条件：`IFConcreteImage ICRIconLayer` 要求可用 Metal device 和分层数据。普通应用经 `SBHIconServicesOptionsForImageOptions` 执行 `(options & 3) ^ 1`，不会提供允许平面图回退的 bit 2；通用占位路径则设置该位。平面图片已经生成仍可能没有普通图标层。

系统已有平面图选择。`SBIconImageView shouldForceBitmapImages` 在非 Glass 外观下检查对象的平面图偏好、方形图标、真实低电量模式或 thermalState；结果经 bit 4 选择 `makeIconLayerFromImageWithInfo:...`。正常低电量模式探针已编译并签名，通过 powerd 原生 XPC 设置和读回状态。

- `q26-native-lpm` 对照运行 600 秒并正常返回：根盘 SHA-256 为 `8399f0563d648ef390e3c0ec23d7af52bfb8dd2b8488bee304c7b4827677b29a`，从 profile 冻结盘派生，只新增 probe 与一条后台任务；进程启动后 240 秒查询并保存原值、开启低电量模式，500 秒恢复，非法原值或读数不一致就跳过设置。原手势时序保持不变。
- 保存恢复守卫和五条流程主机测试通过，客体在进程启动后 240.017 秒开始操作，原始 native／notify 状态均为 0；powerd 接受开启请求，两项读回均为 1，输出 `LPM_SET_VERIFIED value=1`。
- 进程启动后 500.054 秒请求恢复，powerd 接受关闭请求，native／notify 均读回 0，输出 `LPM_RESTORE_VERIFIED value=0`，503.441 秒结束。
- 该轮与主机构建重叠，只用于状态和显示检查，不作性能对照。
- 420 秒同页截图中，profile 轮 11 个灰色应用图标已有 8 个显示内容：Weather、Stocks、Find My、Podcasts、Preview、Translate、Tips、AppleVisionPro；Home、Journal、Triangle 仍为灰色，壁纸仍为黑色。
- 恢复后的 570 秒截图为第一页，应用图标全部有内容，两个组件仍为白色，壁纸仍为黑色。
- 追加 Home 和左滑操作因脚本启动较晚，在约 554.36 秒连续执行，未成功回到第二页；本轮没有取得该页恢复前后的对应截图。
- 默认图标策略暂不修改。

23G90 的 `SBIconImageView lowPowerModeDidChange:` 在开启状态直接返回，关闭才调用图标更新。开启低电量模式后，已有图标不会由该通知回调主动重建；新建或正常重新加载的非 Glass 图标仍可选择 bitmap。截图没有变化还需核对图标是否重建及 Glass 状态。该对照保持默认图标策略，GPU 路线继续独立验收。

`q26-bitmap-observe` 从 LPM 根盘单独增加只读观察库，保持原方法返回，600 秒运行正常结束，低电量模式已验证恢复为 0。守卫确认 23G90、iPhone18,3／V57AP、方法 encoding、IMP 地址和入口字节后安装成功。关闭状态的 16 条记录均为 `original=0 hasGlass=0 lowPower=0`；开启状态的 16 条记录均为 `original=1 hasGlass=0 lowPower=1`，外观类均为 `SBHLightIconImageAppearance`，包含 Clock 子类。本轮为图标路径选择取得了运行结果；仍不能从这些有限样本推导所有图标的行为。

`inject_sb26.c` 已加入候选：仅在真实 Metal 设备缺失且图标为非 Glass 外观时选择现有平面图路径，保留系统原返回为 YES 的情况及有 Metal 设备的路径。

- 设备按进程首次需要时查询一次，返回对象立即释放；首次查询后才注册设备的场景需重启 SpringBoard。
- 原方法、外观方法的指纹和 encoding 均检查，缺项保持原行为。
- 主机分支和 64 路并发 once／release 检查、arm64e 编译与签名验证通过。
- 候选保持低电量设置，`q26-software-icons` 的独立 600 秒对照已正常结束，根盘 SHA-256 为 `c4dcfffe9621fe1ef76dd5134d2b219615bdbb5de7510df8d129bd642c61b330`，相对 profile 仅替换 SB26 库；420 秒截图成功翻到第二页，profile 轮 11 个灰色应用图标中有 8 个显示内容，剩余 Home、Journal、Triangle 和黑色壁纸继续排查。
- 日志确认全部指纹校验通过，`software_icons_installed=1`，真实 Metal 查询为 0。
- 首个手势的首读至末条派发仍为 1892.266 ms，输入等待尚未解决。
- 已将验证过的 SB26 库更新到默认 obj（SHA-256 `b95b22df74099770b1e43a5e8b2ad82e6a56eeeaa478fd1e5f9d33ed41225b98`）；正式根盘仍保留原文件，后续组合验证后再重建。

## 3. 壁纸与组件服务

`com.apple.posterboardservices.services` 由 PosterBoard.app 原生 LaunchAngel 提供。缺失任务会使图标缓存清理查询不到壁纸／主屏配色，但已记录的 947 次失败均有对应清理完成，删除计数为 0。加入 PosterBoard 的单核对照中，前 90 秒查询失败降为 0；壁纸仍未正确显示，默认配置创建需要继续检查。

23G90 的原生初始壁纸路径为 `PBFPosterRoleCoordinator _addChangesForInitialPostersTo:modelCoordinatorProvider:role:` → `PBFInitialPosterHelper initialPosterConfigurationsWithModelCoordinatorProvider:role:`，随后添加并选中 poster。Helper 查询 WallpaperKit 的默认 bundle，缺少 hero 配置时使用 `com.apple.PaperBoard.LegacyPoster`；系统镜像已包含该扩展和壁纸资源。后续先验证原生初始化结果。

当前任务集还缺少 `com.apple.chronod`；程序和原生 plist 已在系统镜像，其服务包括 `com.apple.chronoservices` 与 `com.apple.chrono.widgetcenterconnection`。白色组件需要单独验证这些依赖、扩展启动及内容提交，当前尚未取得完整组件内容。

## 4. Metal 的实际缺口与下一项验收

23G90 RenderBox 会调用 `MTLCreateSystemDefaultDevice`，随后使用设备能力查询、heap、纹理复制和 IOSurface 导入；QuartzCore 还使用 blit encoder、shared event 的创建、导入、信号和等待。当前 `redwoodmetal.m` 的 heap 与 shared texture handle 返回 nil，event wait/signal 为空；blit 子集进度见本节后文。系统 GPU 渲染需要这些接口按资源和提交顺序工作。

现有 Metal 原型使用 AIR → NIR → freedreno。Turnip 的 Vulkan 传输、计算和三角形读回结果只覆盖该后端的独立测试，目前没有 Metal → Turnip 适配。下一步优先复用已存在的资源和提交实现，先验收真实 IOSurface 纹理的 compute 写入、纹理采样绘制及 GPU blit 读回，覆盖 BGRA8／RGBA16Float、非零偏移和行距；随后验证跨提交、跨进程纹理及 shared event 顺序，再启用系统 Metal 渲染。设备枚举和 capability 返回值只作为前置检查。


Metal 已完成一项独立的资源生命周期修正：记录 Work 后保留其引用的 pipeline、附件、buffer、texture 和 sampler，Work 析构时释放，防止编码结束后资源提前销毁。主机生命周期测试通过，删除 retain、删除 release、重复 retain 的三项变异均被测试发现；arm64e 动态库编译与严格签名检查通过，SHA-256 为 `7ef04a648d15759068363ec233f9f56c3c2449353ccddb5a49439a99bd8f8221`。该检查尚未覆盖 GPU fence 和 encoder 绑定至 Work 记录之间的生命周期，blit 与系统 Metal 渲染仍待实现和验收。


blit 的首个子集已写入源码：buffer 到 buffer，以及同格式、单采样 2D／2D-array 纹理之间的区域复制。

- 编码器把参数记录到原 Work 列表，commit 按已有顺序调用 Gallium `resource_copy_region` 并等待 fence，资源沿用 Work 的引用保留。
- 跨设备、越界、重叠区域及带 argument-buffer 编码的 buffer 均报告错误；深度／模板、压缩纹理与 buffer／texture 互拷仍未实现。
- ObjC 库和后端隔离构建通过。
- softpipe C 测试覆盖 12 次 buffer 请求（3 次完成）和 20 次 texture 请求（4 次完成），其余非法输入按预期拒绝；BGRA8 与 RGBA16Float 的 array slice、origin、row pitch、偏移、哨兵及同资源不重叠复制检查通过。
- 生产 ObjC encoder／executor 的主机测试通过 5 次 buffer 和 1 次 texture 后端调用，覆盖延迟执行、提交顺序、同列表依赖和提前释放；提前执行及丢失 source offset 的临时变体分别被断言检测到。
- 默认系统 Metal 配置未启用，K90 GPU 执行待验证。


最终 Metal 产物 SHA-256 为 `e2c9dd833df1fd92cadc51b3faab830d04c10ab9e5423c9a44cba91bdb834745`（arm64e），Mesa 后端为 `cdf4eaba82a0ddc91a59cd20ad24b88fd2a497d0ae010fd6dcbc69c33d8e5471`（arm64），两者 minOS 均为 26。

- Xcode 链接器拒绝 arm64e 探针直接链接当前 arm64 后端。
- 随后 `q26-rwa-dlopen` 使用独立 arm64e 探针运行 60 秒并正常返回，探针仅链接 libSystem，在 `dlopen` 阶段被 23G90 dyld 拒绝，错误为 `have arm64, need arm64e`；设备创建和复制均未执行。
- 独立 arm64e Mesa／AIR 及依赖现已完整构建，产物 SHA-256 为 `8e2f34c257f5f737d203f067a8c7334deb722ac46641f18c92d0c92adcf67b4b`，13,932,752 字节，包含 33 个 `rwa_*` 导出；723 个目标对象及 23 个静态库中的 722 个成员均为 arm64e／iOS／minOS 26。
- 原 16.5 产物保留。
- 构建记录见 `out/ios26-resume/mesa-arm64e/manifest.json`。
- `q26-rwa-arm64e` 仅替换旧探针根盘中的后端库，45 秒日志确认 `dlopen` 与全部符号解析成功，后端为 softpipe；257 字节的 `src=29 → dst=53` 复制返回 0，读回、目标周边哨兵、源内容与资源清理检查均通过。
- 该结果覆盖 arm64e C 接口，A830 执行仍待验证。
- 后续需再次验证加载、复制、Metal 私有 ABI 和 A830 执行。
- 构建脚本、两套配置、源码、测试日志及产物已归档至 `out/ios26-resume/metal-blit/`，manifest 另记录 588 个外部构建输入的哈希。


随后 `q26-metal-runtime` 使用同一 arm64e 后端和已签名 Metal 候选，在 23G90 运行 60 秒并正常返回。

- 探针直接实例化 `RedwoodMetalDevice`，未注册系统默认设备；实际 `_MTLDevice` 大小为 656 字节，创建了真实 `RedwoodMetalCommandQueue`、`RedwoodMetalCommandBuffer` 和 `RedwoodMetalBlitEncoder`。
- buffer 依赖复制为 `29 → 53 → 101` 偏移，两个目标在 commit 前保持哨兵，commit 后逐字节读回正确；19×11 的 BGRA8／RGBA16Float 纹理使用不同上传和读回行距，区域内容和行尾填充均通过。
- 共 4 次复制、3 个 command buffer，wait 后状态均为 4（Completed），error 为 nil，日志最终输出 PASS。
- 该轮仍为 softpipe；着色器、IOSurface 导入、系统默认设备注册和 GPU 执行尚未覆盖。运行清单为 `out/ios26-resume/q26-metal-runtime-manifest.json`。


原始 `q26-metal-pipeline` 与带采样的重复轮均在首次 compute commit 中输出 `Unknown NIR opcode: u2f16`，随后探针产生 corpse；创建 pipeline 已通过，计算尚未提交到后端。失败位于 softpipe 的 NIR→TGSI 编译。

- 独立候选为无原生 FP16 的软件后端增加转换处理，保留 half 的舍入和存储语义；未覆盖的 half 运算明确拒绝，freedreno 路径保持原有处理。
- 候选 `ab8ff6a468cad95c965c3bf4e31c32d2ef70669834c12e4573a88ca461767704` 的 `q26-metal-half` 运行 90 秒正常返回，同一探针完成 1 次 compute、2 次 draw、1 次 blit 和 3 个 command buffer。
- 8×8 RGBA16Float 计算结果、系统 AppleMetalGLRenderer 的常色／纹理绘制、四个附件与复制目标的内容及行尾填充均通过；后端仍为 softpipe。
- 完整输入和运行日志位于 `out/ios26-resume/metal-half/` 与 `q26-metal-half-manifest.json`，A830 提交、IOSurface 和跨进程同步仍待验证。

AIR 前端另增加 23G90 的 `air.get_read_sampler` 及相应 2D 读取参数解析，保持旧签名。真实 QuartzCore `read_write_surf_compute` 在主机 softpipe 完成 187 个像素复制，60 个目标边界像素与 187 个源像素保持不变；旧前端对同一输入因缺少 intrinsic 失败。两个实际 fragment 的动态 LOD 在 NIR 中保留，16.5 旧读取着色器的 NIR 与改动前相同。任意 sampler、非零 offset 等未覆盖形式明确拒绝；该前端改动尚未进入已测 arm64e 候选，记录位于 `out/ios26-resume/read-sampler-host/manifest.json`。
