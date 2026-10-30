# iOS 26 可用桌面：解锁、着色器编译与渲染缺口（2026-10-29 夜～10-30）

本轮工作的目标是让 iOS 26 开机后能进主屏并能操作，判断以截图、日志和手持操作为准，不再从帧间隔推断停帧。前一阶段的结论见[晚间会话审查](../analysis/2026-10-29-evening-session-review.md)。

## 1. 轮次与身份

| 轮次目录 | 作业 | 与上一轮的差别 | 结果 |
|---|---|---|---|
| `kernel-12377-attr26-diag3x-homecycle1` | `rc.jobs.home-cycle`（首版） | 作业换成上划解锁加左右翻页，440 秒定长，`K90_FREEZE_OFF=1` | 自动上划没有解锁；用户手动上划后进主屏，约 20 秒后停帧 |
| `kernel-12377-attr26-diag3x-interactive1` | `rc.jobs.interactive` | 注入 `libredwood-sb26.dylib`（开机自动解锁），去掉 `com.apple.appprotectiond`，驱动线程快照带调用栈，不发合成手势，600 秒 | 开机自动解锁；主屏先只有文字，图标陆续出现；能打开设置并逐级进入 |
| `kernel-12377-attr26-diag3x-lock2cpu4` | `rc.jobs.interactive` | AIR 入口锁，`iconservicesagent` 注入 Metal 注册，4 核 | 开机时 GPU 超时停用，CoreAnimation 退回软件合成；主屏图标与电池图标都显示，应用内上划仍转菊花 |
| `kernel-12377-attr26-diag3x-lock3cpu4` | `rc.jobs.interactive` | 去掉 `iconservicesagent` 的 Metal 注册（`ICON_METAL` 默认关闭） | 4 核正常，无 GPU 错误；从设置上划不再转菊花；主屏没有图标，没有电池图标 |
| `kernel-12377-cmd1-render1` | `rc.jobs.interactive` 加 `rwsh` | 内核 `12377-cmd1`、loader v10、§7.2 的第一批修复 | 开机自动解锁；主屏没有图标、电池图标与壁纸 |
| `kernel-12377-cmd1-render2` | 同上，`cycle.py` 无人值守 | §8 的第二批修复，`ICON_METAL=1` | `iconservicesagent` 第 6 次提交时 GPU 挂起；软件合成下图标与电池图标显示，回主屏后 backboardd 断言崩溃，之后一直转菊花 |
| `kernel-12377-cmd1-render3` | 同上 | AIR 支持沿循环传回的指针；驱动列出每个进程前 16 次提交用到的管线 | 开机 42 秒 GPU 停用；软件合成下主屏、设置、控制中心都能截到，回主屏那一步截到锁屏 |
| `kernel-12377-cmd1-render4` | 同上 | `iconservicesagent` 设 `REDWOOD_SYNC_DRAWS=1`，每个绘制后等它完成；SpringBoard 与 PosterBoard 设 `OS_ACTIVITY_DT_MODE=YES`，打开 os_log | 定位到没有完成的绘制；SpringBoard 的 os_log 占满日志环，开机解锁那一行丢失，巡检没有执行 |
| `kernel-12377-cmd1-render5` | 同上 | 同步模式下打印没有完成的绘制的两个着色器模块；os_log 只开 PosterBoard | GPU 在开机解锁前停用，巡检只截了主屏；取到挂起绘制的模块 |
| `kernel-12377-cmd1-render6` | 同上 | `iconservicesagent` 加 `FD_MESA_DEBUG=sysmem` | 仍然挂起；软件合成下主屏、设置可用，回主屏时 backboardd 断言崩溃，之后转菊花 |
| `kernel-12377-cmd1-render7` | 同上 | 去掉 `sysmem`；同步模式下每个绘制提交前打印一行描述；PosterBoard 加 `OS_ACTIVITY_MODE=debug` | `iconservicesagent` 还没有绘制，GPU 已停用；PosterBoard 的日志没有变多 |
| `kernel-12377-cmd1-render8` | 同上 | `iconservicesagent` 加 `FD_MESA_DEBUG=nolrz`，日志确认进程读到了这个值 | 仍然挂起 |
| `kernel-12377-cmd2-render9` | 同上 | 内核 `12377-cmd2`：打印 HFI 150 的全部字和已完成的 EOP 时间戳 | 第 11 次提交没有完成，是 `iconservicesagent` 的 `primitive__vertex` 绘制；HFI 150 在驱动的两秒等待之后才到，没有打印出来 |
| `kernel-12377-cmd3-render10` | 同上 | 内核 `12377-cmd3`：报告前再读 3 秒 HFI；绘制描述加索引；PosterBoard 注入错误探针 | 第 12 次提交没有完成，是 SpringBoard 的 57 缓冲提交；取到 HFI 150 全文；PosterBoard 的数据存储初始化返回 nil 且没有错误 |
| `kernel-12377-cmd3-render11` | 同上 | AIR 的索引绘制开启图元重启（§8.7）；SpringBoard 设 `IR3_SHADER_DEBUG=vs`；PosterBoard 探针记录数据存储初始化的四步 | 第 9 次提交没有完成，是 SpringBoard 的 57 缓冲提交；SpringBoard 的顶点着色器汇编里没有 `primitive__vertex`；PosterBoard 的迁移返回 0 |
| `kernel-12377-cmd3-render12` | 同上 | SpringBoard 与 `iconservicesagent` 都设 `REDWOOD_SYNC_DRAWS=1` | 第 10 次提交没有完成，是 SpringBoard 第 2 次提交第 3 个 work，`primitive__vertex+ffea2ba11dhmha4`；取到 `primitive__vertex` 的 A830 汇编 |
| `kernel-12377-cmd3-render13` | 同上 | 两个进程设 `AIR_DISCARD=off`，`discard_fragment` 翻译成空操作；SpringBoard 设 `IR3_SHADER_DEBUG=fs`；PosterBoard 探针加迁移的版本号 | 仍然挂起，第 10 次提交是 `iconservicesagent` 的 `primitive__vertex+ffia2ba3ca7dhmha4`；PosterBoard 从 59 迁移到 61 失败 1151 次 |
| `kernel-12377-cmd4-render14` | 同上 | 内核 `12377-cmd4`：挂起报告后打印 CP 状态与命令字；PosterBoard 的预期资源值类方法返回空字典 | 仍然挂起，第 14 次提交是 `iconservicesagent` 的 `primitive__vertex+ffia2ba3ca7dhmha4`；HFI 150 先于驱动的等待超时到达，转储没有打印；PosterBoard 迁移仍失败，替换的类方法不在有效性检查的路径上 |
| `kernel-12377-cmd5-render15` | 同上 | 内核 `12377-cmd5`：收到 HFI 150 时就转储；PosterBoard 在 NSURL 的资源值比较与设置里去掉文件保护一项 | 取到 CP 转储（§8.10）；PosterBoard 迁移成功，数据存储初始化成功，之后建海报存储时标记 purgeable 失败 |
| `kernel-12377-cmd5-render16` | 同上 | SpringBoard 与 `iconservicesagent` 设 `FD_MESA_DEBUG=sysmem`，日志确认两个进程都读到了 | 仍然挂起，第 6 次提交是 SpringBoard 的第 3 个 work；CP 已越过读帧缓冲前的屏障，停在这次绘制上 |
| `kernel-12377-cmd5-render17` | 同上 | 两个进程设 `FD_FB_READ_NO_FLUSH=1`，读帧缓冲的绘制保持 `NO_FLUSH`，日志确认读到 | 仍然挂起，同一个 SpringBoard 绘制；逐重叠刷新排除 |
| `kernel-12377-cmd5-render18` | 同上 | 两个进程设 `AIR_FB_LAYER0=1`，帧缓冲读取的层号为常数 0，日志确认读到 | 仍然挂起，同一个 SpringBoard 绘制；层号读取排除 |
| `kernel-12377-cmd5-render19` | 同上 | 两个进程设 `AIR_FB_READ_WRITEMASK=1`，片段着色器读而管线不写的目标改为四个通道都写，日志确认 `ffea2ba11dhmha4` 的 1 号目标改写 | 仍然挂起，同一个 SpringBoard 绘制；写掩码排除 |
| `kernel-12377-cmd5-render20` | 同上 | 两个进程设 `FD_FB_READ_LATE_Z=1`，读帧缓冲的绘制在片段着色器之后做深度测试，日志确认读到 | 仍然挂起，同一个 SpringBoard 绘制；z 模式排除 |
| `kernel-12377-cmd5-render21` | 同上 | 两个进程设 `AIR_FB_READ_ZERO=1`，帧缓冲读取换成常数 0，日志确认读到 | SpringBoard 的 `primitive__vertex+ffea2ba11dhmha4` 完成，继续画到第 3 次提交；之后内核在外部缓冲解除映射时等 200 毫秒超时，关闭提交，停在 `iconservicesagent` 的 `primitive__vertex+ffeba5ca7jbmhia3`，归属没有确认（§8.11） |
| `kernel-12377-cmd7-render22` | 同上 | 内核 `12377-cmd7`：等时间戳的上限 2 秒，超时打印时间戳并转储；开关同 `render21` | `ffeba5ca7jbmhia3` 完成；第 29 次提交没有完成（HFI 150），是 `iconservicesagent` 第 5 次提交第 1 个 work，`primitive_gradient_vertex+fgea14dhmha4` |
| `kernel-12377-cmd7-render23` | 同上 | 开关同 `render22`（改名 `AIR_FB_READ=zero`）；`iconservicesagent` 设 `IR3_SHADER_DEBUG=fs`；驱动先打印挂起的片段着色器 | 第 107 次提交没有完成，是重启后 `iconservicesagent` 第 4 次提交第 4 个 work，`primitive_gradient_vertex+fgea2ca11dhmha4`；取到 A830 汇编 |
| `kernel-12377-cmd7-render24` | 同上 | 帧缓冲读取恢复；两个进程设 `AIR_FS_INPUTS_PACKED=1`，片段着色器的输入去掉没被读的并从 0 编号；SpringBoard 设 `IR3_SHADER_DEBUG=fs` | 仍然挂起，第 6 次提交，SpringBoard 的 `ffea2ba11dhmha4`；汇编确认空位已去掉；输入空位排除 |
| `kernel-12377-cmd7-render25` | 同上 | 去掉压紧开关；两个进程设 `AIR_FB_READ=sample0`，帧缓冲读取的采样号为常数 0 | 仍然挂起，第 6 次提交，`ffea2ba11dhmha4`；汇编确认不再读采样号；采样号与逐采样着色排除 |
| `kernel-12377-cmd7-render26` | 同上 | 两个进程设 `AIR_FB_READ=rt0`，帧缓冲读取统一读 0 号目标 | 仍然挂起，第 7 次提交，`ffea2ba11dhmha4`；1 号目标排除 |
| `kernel-12377-cmd8-render27` | 同上 | 内核 `12377-cmd8`：挂起后打印整条命令树与片段阶段 bindless 描述符；`FD_FB_READ_DUMP=1`；`AIR_FB_READ=log`（backboardd 也开） | 仍然挂起，第 6 次提交，`ffea2ba11dhmha4`；GPU 读到的描述符与 freedreno 写入的一致；绘制的寄存器状态与 freedreno 的设计一致 |
| `kernel-12377-cmd8-render28` | 同上 | 两个进程设 ir3 的 `IR3_FB_READ_ISAM=1`，帧缓冲读取用 `isam`，不带采样坐标 | 仍然挂起，第 7 次提交，`ffea2ba11dhmha4`；汇编确认是 `isam`；`isamm` 排除 |
| `kernel-12377-cmd8-render29` | 同上 | 两个进程设 `AIR_FB_READ=coord0`，帧缓冲读取的坐标为常数 (0, 0) | 仍然挂起，第 7 次提交，`ffea2ba11dhmha4`；汇编确认不读片元坐标；片元坐标排除 |
| `kernel-12377-cmd8-render30` | 同上 | 两个进程设 ir3 的 `IR3_FB_READ_BINDLESS_SAMP=1`，读帧缓冲的着色器同时设 `bindless_samp` | 仍然挂起，第 6 次提交，`ffea2ba11dhmha4`；`SP_PS_CONFIG` 读数 0x40503，`BINDLESS_SAMP` 已置上；排除 |
| `kernel-12377-cmd8-render31` | 同上 | 两个进程设 `IR3_SHADER_DEBUG=noaliasrt,noaliastex,nopreamble,noearlypreamble,nodescprefetch` | 两分钟内没有挂起，同步模式下 261 个绘制完成，读帧缓冲的着色器都画过；驱动拒绝 `fpba2ma11bemha4` 的绘制（§8.12） |
| `kernel-12377-cmd8-render32` | 同上 | 只关 `alias.rt` 与 `alias.tex`（`IR3_SHADER_DEBUG=noaliasrt,noaliastex`） | 第 9 次提交挂起，`iconservicesagent` 的 `ffia2ba3ca7dhmha4`；两项 alias 排除 |
| `kernel-12377-cmd8-render33` | 同上 | 只关描述符预取（`nodescprefetch`） | 第 7 次提交挂起，SpringBoard 的 `ffea2ba11dhmha4`；描述符预取排除 |
| `kernel-12377-cmd8-render34` | 同上 | 只关提前预备代码（`noearlypreamble`） | 两分钟内没有挂起，同步模式下 218 个绘制完成；提前预备代码是挂起原因 |
| `kernel-12377-cmd8-render35` | 同上 | 设备 Mesa 的 A830 关掉 `has_early_preamble`，不设 `IR3_SHADER_DEBUG`；测量开关撤掉 | 两分钟内没有挂起，同步模式下 304 个绘制完成；图标管线仍被拒绝（§8.13） |
| `kernel-12377-cmd8-render36` | 同上 | AIR 不再要求绑定 `air.arg_unused` 的纹理与采样器；同一缓冲内的指针 `select` 与 phi 改用偏移；freedreno 接受只差末级行对齐的线性导入 | `fpba2ma11bemha4` 的拒绝、路径顶点着色器的拒绝、RGBA16Float 图标表面的导入失败都消失；主屏仍没有图标 |
| `kernel-12377-cmd8-render37` | 同上 | 驱动支持纹理视图；`MTLSamplerMinMagFilterCubic` 按线性采样；驱动打印拼接库与链接函数的描述 | 控制中心、设置、锁屏都画出来；`compute_average_luma` 不再失败，`iconservicesagent` 不再因采样器中止；没有打印到拼接库调用 |
| `kernel-12377-cmd8-render38` | 同上 | 驱动接管 `_MTLLibrary` 的 `-newFunctionWithDescriptor:error:`，一律返回未特化函数的代理；没有片段函数的管线用空片段着色器 | 没有解锁，提前结束：RenderBox 与 QuartzCore 的特化变体原本在进程内就能取到，代理让管线以未特化的入口名建出，全部被拒绝 |
| `kernel-12377-cmd8-render39` | 同上 | 钩子先走 `_MTLLibrary` 自己的实现，返回 nil 时才用代理；管线的链接函数在翻译时内联进片段着色器；没有片段函数的管线用空片段着色器 | 自定义效果与 `path_edges` 管线的拒绝都消失；主屏仍没有图标；点开设置后到结束都没有画出设置，控制中心也没有出现（§8.13） |
| `kernel-12377-cmd8-render40` | 同上 | 库不变；没有设 `ICON_METAL=1`，`iconservicesagent` 用软件渲染；boot-arg 加 `systrace=1` 与 `ustacks=Preferences` | 图标、Dock、小组件与设置列表的图标都画出来，设置点开即显示；backboardd 的 `compute_average_luma` 因单级纹理视图失败 11 次（§8.13） |
| `kernel-12377-cmd8-render41` | 同上 | 同 `render40`；boot-arg 改为 `systrace=1 systrace_name=nosuchproc`，只留异常打印，`ustacks_at=80` | 与 `render40` 相同；异常打印只有几个应用扩展的 SIGTRAP |
| `kernel-12377-cmd8-render42` | 同上 | 纹理视图可取一段连续的级别；`rwa_texture_generate_mipmaps` 从视图的第一级生成；boot-arg 同 `render41` | `compute_average_luma` 的 11 次失败消失，没有纹理视图被拒绝；画面与 `render41` 一致 |
| `kernel-12377-cmd8-render43` | 同上 | 同 `render42`，去掉 `systrace` 与 `ustacks` | 起轮后改了计划，提前结束，没有读数 |
| `kernel-12377-cmd8-render44` | 同上 | 库同 `render42`；`ICON_METAL=1`；boot-arg `systrace=1 systrace_name=nosuchproc` | `iconservicesagent` 仍然 SIGTRAP 10 次，异常打印给出位置：IconRendering 里一个弱引用读出 nil（§8.13） |
| `kernel-12377-cmd8-render45` | 同上 | 驱动的 buffer 纹理持有并返回 buffer，GPU 写过的纹理拷回 buffer；`ICON_METAL=1`；没有设 `JOB_ENV`，SpringBoard 与 `iconservicesagent` 不逐个等待绘制 | `iconservicesagent` 不再 trap，连续 105 个 commit；约 45 秒后出现 GPU SMMU 缺页，内核关闭提交，之后 BO 分配失败，三个进程崩溃（§8.13） |
| `kernel-12377-cmd8-render46` | 同上 | 同 `render45`，补上 `render39` 的 `JOB_ENV` | 设置列表的图标由 GPU 画出；仍出现 SMMU 缺页（读访问，叶 PTE 为空），之后用户态重启，主屏只剩转圈 |
| `kernel-12377-cmd10-render47` | 内核 `12377-cmd10`：cmd8 加 BO 预留记录，SMMU 缺页时打印持有该地址的 BO 与前后最近的 BO | 同 `render46` | 没有缺页；GPU 画的图标是花的：成块的矩形与横向条纹，有的图标错位，设置列表的图标为空 |
| `kernel-12377-cmd10-render48` | 同上 | 同 `render47`，`iconservicesagent` 加 `FD_MESA_DEBUG=sysmem` | 日志开始后约 45 秒出现 SMMU 缺页，地址紧接在最后一个 BO 之后；重启后的 `iconservicesagent` 拿不到 GPU，截图里的图标是软件渲染的，sysmem 的效果没有读到（§8.13） |
| `kernel-12377-cmd11-render49` | 内核 `12377-cmd11`：cmd10 加 BO 保护页 | 同 `render48` | 没有缺页，三个进程都没有重启；`iconservicesagent` 用 GPU 并走 sysmem，图标仍然成块错乱、带横向条纹，与 `render47` 相同（§8.13） |
| `kernel-12377-cmd11-render50` | 同上 | 同 `render49`，`iconservicesagent` 加 `REDWOOD_THUMBS=600`，从 commit 2 起每次绘制后采样 | 600 张采样只还原出 220 张，日志上传丢了大段；0 号附件全程透明，形状只写进 1 号附件 |
| `kernel-12377-cmd11-render51` | 同上 | 改为每个 commit 结束时采样一次 | 输入的花瓣、椭圆等图层正确；合成到 160×160 与 192×192 时只剩横条或透明 |
| `kernel-12377-cmd11-render52` | 同上 | 只采 `path_` 着色器的绘制，绘制前后各一次 | 路径的覆盖率在 1 号附件里逐笔累积，形状正确（App Store 的「A」三笔） |
| `kernel-12377-cmd11-render53` | 同上 | 同 `render49`；no-copy buffer 上的纹理从调用方内存取数据，结果写回调用方内存 | 开机约 80 秒 backboardd 访问已释放的内存崩溃，之后一直转圈，没有图标读数 |
| `kernel-12377-cmd11-render54` | 同上 | 调用方内存只写不读 | 没有崩溃；图标开始出现正确的底色（Mail 的蓝色圆角方块、Photos 的渐变），图形本身缺失，FaceTime、App Store 等是成块缺失的马赛克 |
| `kernel-12377-cmd11-render55` | 同上 | 加 commit 结束时的采样，标出 buffer 与 IOSurface 纹理；库打印前 64 次回写 | 最终的 192×192 BGRA 图标纹理回写时几乎全为 0；花瓣等 IOSurface 图层正确，`plane_image_stretch` 把它们贴进 192×192 buffer 纹理后只剩横条或透明 |
| `kernel-12377-cmd11-render56` | 同上 | 只采 `plane_image_stretch` 的绘制，绘制前后各一次，并打印顶点缓冲的前 16 个浮点数 | 矩阵与纹理坐标正确；绘制后 0 号附件多数仍透明，一次绘制的输入「Fr」出现在 2 号附件里，灰色圆形输入在 0 号附件里变成灰色方块 |
| `kernel-12377-cmd11-render57` | 同上 | 同 `render54`，AIR 在翻译时按 function constant 求颜色附件号 | 求值没有触发（特化位码里附件号已是常数）；图标仍是横条，出现的图标与 `render54` 不同 |
| `kernel-12377-cmd11-render58` | 同上 | 同 `render54`；每批工作前读取 no-copy buffer 的调用方内存，有变化时拷入 | 调用方内存变化 31 次，buffer 大小（16384～114688 字节）与 backboardd 的 no-copy buffer 相同；`iconservicesagent` 的 34176、161408 字节 buffer 没有变化，图标仍是横条 |
| `kernel-12377-cmd11-render59` | 同上 | IOSurface 比描述符大时按描述符的大小导入左上角；探针：`kfmha4` 管线逐次采样、`REDWOOD_DUMP_AIR` 打印位码 | 「no drawable」拒绝从 2 次降到 0；48 个模块集中打印，日志丢了前 38 条管线的记录，位码没有取到；`kfmha4` 绘制的 0 号输入纹理本身全透明 |
| `kernel-12377-cmd11-render60` | 同上 | 探针：按 commit 采样、只打印 `kfmha4` 函数的位码 | 取到完整的 `primitive_image_vertex` 特化模块，其中写着特化常量；commit 2 的 96×64 中间层画完就是透明的 |
| `kernel-12377-cmd11-render61` | 同上 | 探针：commit 2 逐次采样 | 第一段之后 1 号附件的采样全黑，之后的 `primitive_color` 全部丢弃（采样把负值截成 0，见 `render65`） |
| `kernel-12377-cmd11-render62` | 同上 | 探针：同步日志加 depth 比较函数，采样前打印 buffer 原始字 | 比较函数是 6（`GreaterEqual`）；日志环在 commit 2 前几次绘制处翻转，前 7 次绘制的读数丢失 |
| `kernel-12377-cmd11-render63` | 同上 | 同步日志只在采样的 commit 里打印 | 合并日志从约 10 MB 降到 7.4 MB，仍有 1 处缺口，commit 2 前 5 次绘制的读数在缺口里 |
| `kernel-12377-cmd11-render64` | 同上 | 探针：只采 `path_` 管线，绘制前后各一次，打印每个顶点缓冲的前 24 个字 | 路径绘制里只有 commit 1 与 commit 6 的一部分在 1 号附件留下正值，其余采样为 0 |
| `kernel-12377-cmd11-render65` | 同上 | `iconservicesagent` 加 `nolrz`；探针：buffer 打印 192 个字，同步日志打印清除值 | 与 `render64` 相同，LRZ 不是原因；按特化 IR 在 CPU 上算出 commit 8 第 1 次路径的覆盖率是 −1，采样截成 0 |
| `kernel-12377-cmd11-render66` | 同上（库：两通道浮点纹理的采样带符号） | 探针：从 commit 1 起采每次绘制 | 采样额度用在 commit 1～2，这一轮这两个 commit 没有路径 |
| `kernel-12377-cmd11-render67` | 同上 | 探针：`REDWOOD_THUMB_WHOLE` 采含 `path_exterior` 的整个 commit | commit 7 的 w3 路径与 CPU 计算一致（采样 102 个对 106 个）；w4 路径与两次覆盖率填充什么也没写，之后的 `primitive_color` 全部丢弃 |
| `kernel-12377-cmd11-render68` | 同上 | 探针：深度附件采样 | 深度采样没有输出；commit 1 的覆盖率填充在深度清成 0、自身深度为 0 时也没有写；没写出东西的绘制，常量 buffer 偏移都不是 16 的倍数 |
| `kernel-12377-cmd11-render69` | 同上（库：常量 buffer 偏移不是 64 的倍数时拷贝后绑定） | 同 `render68` | 覆盖率填充写出 R，图标的形状与颜色出现；News、Health、Games、Wallet、Settings 的图形仍有横条，图标上有一条对角细线，Weather 与 Calendar 小组件是白块（§8.13） |
| `kernel-12377-cmd11-render70` | 同上（库：拷贝的门槛改为偏移不是 16 的倍数） | 探针：采含 `plane_image_stretch` 的整个 commit | 图标与 `render69` 一致，Weather（「Location Access Needed」）与 Calendar 小组件也画出来了；FaceTime、Mail、News、Games、Health、Wallet、Safari 与 dock 第 4 个图标的图形仍是横条 |
| `kernel-12377-cmd11-render71` | 同上（库：片段着色器按导数与隐式 LOD 采样声明需要辅助线程） | 探针：采含 `fi2a2ea3dna6dhmha4` 的整个 commit | 图标上的对角细线和方框四角外的暗点都消失了；News、Games、Health、Wallet、Settings 的图形仍是横条 |
| `kernel-12377-cmd11-render72` | 同上（驱动：同步日志只在逐次采样时自动打印） | 探针：`iconservicesagent` 每个 commit 结束时采样一次，共 900 张 | Phone、Photos、App Store、Fitness、Health、Books、News、Maps 的图标在 `iconservicesagent` 里都画对了，主屏上 News、Health 的横条不来自这个进程 |
| `kernel-12377-cmd11-render73` | 同上 | SpringBoard 也加 `FD_MESA_DEBUG=sysmem` | 横条不变，与 GMEM 分块无关；巡检中主屏进入了编辑模式；SpringBoard 有一条 `custom_effect` 管线（`ffgea5caca5gemhba3`）因片段着色器把指针存进内存被拒 |
| `kernel-12377-cmd11-render74` | 同上 | SpringBoard 采含 `custom_effect` 的整个 commit | SpringBoard 自己也画图标：commit 75 用 iconservicesagent 的 194×194 `RGB10A2Unorm` buffer 纹理和一张 101×94 的圆角矩形 IOSurface 画 FaceTime，相机图形里出现斜向的点状线；采样拖慢了 SpringBoard，巡检的主屏截图没有图标 |
| `kernel-12377-cmd11-render75` | 同上 | SpringBoard 按 `render74` 的变体名匹配 | 没有采样：同一着色器的变体名每次开机都变，匹配不到 |
| `kernel-12377-cmd11-render76` | 同上（驱动：采样边长可设，`REDWOOD_THUMB_SIZE`） | SpringBoard 按 `primitive_custom` 匹配整个 commit，采样 128×128 | 90 张的额度在 commit 4（256×128 的内容）用完，没有采到图标；日志 13 MB，超出两次拉取之间的环形缓冲，采样行有缺失 |
| `kernel-12377-cmd11-render77` | 同上（驱动：纹理 buffer 的对齐查询与线性纹理答同一个值；记录每个 buffer 纹理的行字节数） | 无采样 | 图标上的文字碎片与黑块消失，Settings、Wallet、Notes、Reminders、Clock、App Store、Maps 画对，两个小组件都有内容；FaceTime、Mail、News、Games、Health、Safari、Music 的图形里仍有斜向条纹 |
| `kernel-12377-cmd11-render78` | 同上（驱动：`REDWOOD_THUMB_ONLY` 按角色和槽位挑采样） | SpringBoard 按 `custom_effect` 匹配整个 commit，128×128，只采 0、1 号附件与 0 号纹理 | commit 2 画一把钥匙的玻璃效果：取轮廓、两组各 4 次的乒乓滤镜、输出法线样的光照纹理；按 Metal 的语义逐次核对后没有找到错误（§8.13） |
| `kernel-12377-cmd11-render79` | 同上（驱动：`REDWOOD_DUMP_AIR` 可给多个名字） | SpringBoard 打印 `render78` 中按地址查到的管线位码 | 取回的是 stroke 等其他管线：管线对象释放后地址被新管线复用，`render78` 的名字要按日志顺序取最近一次建立的那条 |
| `kernel-12377-cmd11-render80` | 同上（驱动：位码打印带上片段阶段链接的函数） | SpringBoard 打印 `fpba`、`foba` 开头的管线位码 | 取到 9 个完整模块；这些管线没有链接 `custom_fn`。`fp` 类是 `filter_distance`，`fo` 类是 `filter_blur` |
| `kernel-12377-cmd11-render81` | 同上 | SpringBoard 按 `path_exterior` 逐次采样 1 号附件，192×192，带顶点数据 | 5 次采到的是别的管线：驱动按地址记管线名，地址被新管线复用后仍返回旧名字。真正的那次 `path_exterior`（120×120 圆角矩形）覆盖率干净 |
| `kernel-12377-cmd11-render82` | 同上（驱动：同一地址的新管线替换旧记录） | 同 `render81` | SpringBoard 整轮只有这一次 `path_exterior`，图标的图形不走路径绘制；采样拖慢 SpringBoard 后，几个图标上又出现「Passcode」等文字碎片 |
| `kernel-12377-cmd11-render83` | 同上（驱动：`REDWOOD_THUMB_TEXTURE` 按绑定纹理的尺寸挑绘制） | SpringBoard 采读 194×194 图层的绘制，192×192 | 194×194 的图层是平滑的法线样光照图；FaceTime 在 commit 58，镜头的白色条纹出现在 w4 与 w7 之间，中间的 w5、w6 读 50×83 的 IOSurface 图形 |
| `kernel-12377-cmd11-render84` | 同上（驱动：IOSurface 导入打印尺寸与行字节数） | SpringBoard 采读 50×83、101×94 IOSurface 的绘制 | 处理器读到的 IOSurface 图形干净，GPU 采样画出的已经错切：镜头 50×83 按 224 字节一行建，按 256 读；机身 101×94 按 416 建，按 448 读 |
| `kernel-12377-cmd12-render85` | 内核 `12377-cmd12`：IOSurface 的行字节数补齐到 64 | 无采样 | 三次尝试都在启动早期 panic（`cpu_id <= ml_get_max_cpu_number()` 断言）。`12377-cmd12` 由 `build-kernel.py` 构建，那是 xnu-8796 的内核，不是 12377 线，panic 出自用错内核 |
| `kernel-12377-cmd13-render86` | 内核 `12377-cmd13`（同样由 `build-kernel.py` 构建，xnu-8796） | 无采样 | 启动早期 panic（`(cpuid & MACHDEP_TPIDR_CPUNUM_MASK) == cpuid` 断言），查出 `cmd12`、`cmd13` 用错了构建工具 |
| `kernel-12377-cmd14-render87` | 内核 `12377-cmd14`：`cmd11` 的源码树加行字节数补齐与 `kern.redwood.env`，用 `xnu26/build-macos.sh` 构建 | 无采样；`--hold` 后用 `respin.py` 打开采样并重启 SpringBoard | SpringBoard 的图形 IOSurface 按 256、448 字节一行导入，图标的条纹仍在，斜度变小；`respin.py` 的设置生效，重启后的 SpringBoard 停在转圈界面 |
| `kernel-12377-cmd14-render88` | 同上 | SpringBoard 采读 50×83、101×94 IOSurface 的绘制 | 处理器读到的 IOSurface 图形也已错切：SpringBoard 仍按自己要求的 224、416 字节一行写，内核补齐行距不起作用 |
| `kernel-12377-cmd15-render89` | 内核 `12377-cmd15`：`cmd11` 加 `kern.redwood.env`，撤回补齐（驱动：行距不是 64 倍数的 IOSurface 经拷贝采样） | 同 `render88` | 50×83、101×94 的输入和画出的结果都干净，commit 100 的图标图集里 App Store、Maps、FaceTime、Mail、Safari 没有斜纹；SpringBoard 的 16 个、backboardd 的 4 个 surface 走拷贝；采样拖慢 SpringBoard，巡检没回到主屏 |
| `kernel-12377-cmd15-render90` | 同上 | 无采样 | 主屏图标与 Control Center 的图标都画对，斜纹消失；Mail 信封下方、Maps 圆形右上各有一块黑色弧形 |
| `kernel-12377-cmd15-render91` | 同上（驱动：同一 surface、格式与尺寸的请求共用一个拷贝纹理） | 无采样 | Mail 的弧形消失，Notes、Maps、Clock 上出现同样的黑色弧形，同一轮的三张主屏截图里位置不变；第一张截图里 Notes、Clock、TV 的边缘另有零散黑点 |
| `kernel-12377-cmd15-render92` | 同上（驱动：拷贝路径的日志带格式与用途） | SpringBoard 采读 17×17、1×1、72×37、72×72、72×73 纹理的绘制 | 这些小 surface 的内容都正确，用途都是只读；commit 43 的 96×128 中间目标在第一次绘制之前，scissor（96×97）以外的行里已有一块前一个图标的阴影 |
| `kernel-12377-cmd15-render93` | 同上（AIR 库：新建的颜色与深度目标先清零） | 无采样 | 主屏图标没有黑色弧形，也没有边缘黑点；关闭通知中心后的最后一张截图是黑屏加 home 条，没有 GPU 挂起，像是截在过渡动画中 |

两轮内核相同（`out/xnu12377-f055cc0a-restored.bin`），cmdline 相同（`cpus=2 bootcpu=7`，`adreno8_speed=3`）。`interactive1` 的驱动为 `ceefc187…`，AIR 仍为 `b5b44d51…`。

## 2. 解锁

- 首版 `rc.jobs.home-cycle` 的 rwtouch 行有约 200 个词，`init` 每行只解析前 63 个词（`userland/src/init.c` 的 `run_command()`），rwtouch 执行到第 63 个词报 `bad step "swipe"` 退出。现在的版本每行不超过 49 个词。
- 两次自动上划发生在锁屏可操作之前：SpringBoard 23:41:24 连上 backboardd，开机 logo 层 23:41:42.3 移除，23:41:37.6～40.6 与 42.3～45.6 两段背光关闭（backboardd 记 `canceling events for suppression reason: backlight dim/off`）。第一次上划在 31.9 s 落在 logo 层上，第二次约 38 s 落在背光关闭期间。用户 23:45:2x 手动上划一次就解锁了，iOS 26 本身的解锁路径没有问题。
- 16.5 的 `inject_sb.c` 在 SpringBoard 启动 10 秒后调用 `-[SBLockScreenManager unlockUIFromSource:withOptions:]`（来源 24）。iOS 26 的 `inject_sb26.c` 没有这一段，而且打包脚本的 `INJECT` 从未加载 `libredwood-sb26.dylib`。
- 现在 `inject_sb26.c` 从第 10 秒起每 3 秒查一次 `isUILocked`，见过锁屏且解锁后停止，最多 60 次；注册 `com.redwood.unlock` 通知（`rwtouch notify com.redwood.unlock`）；`autounlock=0` 保留锁屏。`package.py` 从源码编这个库并注入 SpringBoard。`interactive1` 日志：`sb26: unlock boot: answer=1 locked_after=0`，第 2 次检查时完成。

## 3. 停帧与着色器编译

`homecycle1` 解锁后最后一帧在 23:45:44。之后用户的触摸照常到达 backboardd 并分给 SpringBoard，两个进程的驱动每秒打印 `tl: cnt 0 0 0 0 0`，进程都还活着，只是没有提交。停住时 SpringBoard 的驱动记 `draw 3 has run for 424 ms` 与 `commit 3 has not moved for 2708 ms inside a recorded work`，线程快照里编译线程停在 `libredwoodair.dylib`。收尾时的 `THE KERNEL HUNG ... no sign of life for 50 seconds` 出现在 `oem stop` 之后，是 GPU 资源未归还时的正常收尾（`hung-held`），使用期间内核没有挂死。

`interactive1` 的线程快照带上了调用栈（驱动 `rw_print_threads()`，库内偏移用 `atos -arch arm64e -l 0x0` 还原）：

- 渲染线程：`rwa_render_draw → fd_draw_vbo → fd6_draw_vbos → get_program_state → ir3_cache_lookup → ir3_get_shader → _util_queue_fence_wait`。
- 编译线程：`util_queue_thread_func → create_initial_variants_async → … → ir3_compile_shader_nir`，三次采样分别停在 `nir_opt_cse`、`nir_opt_shrink_stores`、`ir3_legalize`。

第 280 秒前的统计（`ir3q job:` 与 `ir3 wait:` 行）：

| 量 | 值 |
|---|---|
| backboardd 编译线程任务数 | 193 个，墙钟合计 4.97 s，线程 CPU 合计 0.50 s |
| 排在前面的任务数最大值 | 33 |
| 入队到开始的最长时间 | 2.87 s |
| backboardd 渲染线程等待 | 67 次，合计 5.06 s，最长 0.77 s |
| 另一个等待线程（tid 483） | 16 次，合计 6.78 s，最长 1.79 s |

编译队列的线程数是在线 CPU 数的一半，`cpus=2` 下只有 1 个。任务的线程 CPU 只占墙钟的 10%，编译线程多数时间处于可运行但未被调度的状态，或者在等待。

改动（`hackios-xnu-kernel/tools/mesa/ir3-compile-steal.patch`，AIR `62eced7a…`）：

- `util_queue_steal_job()`：把还没开始的任务从队列里取走，且不发出 fence 信号。`ir3_get_shader()` 用它把自己要的任务拿过来在本线程编译，编完再发信号，其他线程照常在 fence 上等。
- 编译队列线程在 Darwin 上设为 `QOS_CLASS_USER_INITIATED`，仍低于渲染线程。在渲染线程上就地执行的任务不改该线程的 QoS。

### 3.1 SpringBoard 主线程永久卡死：`Unhandled ALU op: ffma`

两轮的 SpringBoard 都卡在同一处，日志里各有一次 `Unhandled ALU op: ffma`：

- 着色器是 RenderBox 的片段着色器 `feanea4fba6dhmha4`（管线标签 `primitive_coverage`），出错指令是 `%63 = ffma %62, 0.25, %59`。AIR 前端在 Metal 的 `fma()`（非 fast）和 `llvm.fmuladd` 上发出严格融合的 `nir_ffma`（`tools/mesa/air/air_intrinsics.c`、`air_llvm.inc`）。ir3 的 `float_mul_add32` 只声明了 `has_fmad` 和 `fuse`，NIR 不会为它降级严格 `ffma`，`emit_alu()` 走进 `default` 分支。
- `ir3_context_error()` 结尾是 `UNREACHABLE("")`，release 构建里展开为 `__builtin_unreachable`。编译线程（`interactive1` 的 tid 289）的调用栈停在 `ir3_context_error < ir3_context_error < emit_alu`，之后没有返回。
- SpringBoard 主线程（tid 221）停在 `RenderBox → Metal → rwa_render_draw → fd_draw_vbo → … → ir3_get_shader → _util_queue_fence_wait`。驱动记 `commit 3 has not moved for 2735 ms inside a recorded work` 之后，SpringBoard 每秒的 `tl: cnt` 全是 0，直到收尾。
- 用户看到的现象都由 SpringBoard 主线程负责，因此一起失效：小白条不画，上划回主屏、下拉通知中心和控制中心没有反应，状态栏时间停在 11:58，设置里的侧边返回没有反应。设置本身是另一个进程，页面内的点按照常响应。

修复（`hackios-xnu-kernel/tools/mesa/ir3-ffma-as-mad.patch`，AIR `66ea12d0…`，同时带第 3 节的取任务与 QoS 改动）：

- `emit_alu()` 把 `nir_op_ffma` 按 `nir_op_fmad` 发射。Mesa 在同一处注明 a6xx 以后的 mad 不融合，所以结果比源码多一次舍入。
- `ir3_context_error()` 结尾改为 `abort()`：进程带着着色器转储退出，由 launchd 重启，不再无限等待。

### 3.2 `ffma1` 的结果与 backboardd 崩溃

`ffma1`（AIR `66ea12d0…`，900 秒）用户手持操作的结论：小白条出现，桌面时钟指针走动，控制中心能下拉。整轮 17,152 帧，`interactive1` 为 4,057 帧。编译等待的变化：

| 量 | `interactive1` | `ffma1` |
|---|---|---|
| 单个等待线程的等待合计 | 5.06 s 与 6.78 s | 每个线程 0.03～0.59 s，tid 1056 为 2.03 s |
| 单次等待最长 | 1.79 s | 0.53 s |
| 在渲染线程上就地编译的任务 | 无 | 例如 tid 351 的 43 个任务，墙钟 0.07 s，CPU 0.07 s |

从设置底部上划回主屏会转菊花。这一轮 backboardd 崩了 4 次（pid 38、141、164、184），都是 SIGSEGV，位置在 `libredwoodair` 的 `fd6_vsc_update_sizes` 与附近的 fd6 绘制代码（`fd6_draw_vbos`，`x0` 为 0）。每次崩溃前一行都是驱动的 `commit N started while commit N-1 was still running`；`interactive1` 与 `homecycle1` 没有这一行。backboardd 每次退出后 SpringBoard 被结束（`reason 15`），重启后着色器重新编译，最后一次重启在收尾前没有回到锁屏。

修复（驱动 `5bb05bfd…`）：`-commit` 进入时取一把进程内的递归锁，`redwoodReturnSlot` 之后释放，完成回调在锁外执行。

### 3.3 `lock1`：提交锁之后仍然崩溃

`lock1`（驱动 `5bb05bfd…`）里 backboardd 在同一位置崩溃（pc 在 `fd6_vsc_update_sizes`+32，`x0` 为 0），这次之前没有并发提交的日志行。`fd_draw_vbo()` 在调用 `draw_vbos` 之前刚确认过 `ctx->batch`，`fd6_draw_vbos` 里再读到的却是 NULL。可能的来源是驱动在 `-commit` 之外调用的入口（纹理上传与读回、缓冲纹理刷新）从别的线程刷掉了当前 batch。

修复（AIR `c5bc52ec…`）：`air_metal.c` 加一把进程级递归锁 `rwa_lock`，33 个会碰到 pipe_context 的 `rwa_*` 入口第一句是 `RWA_LOCKED`，用 `__attribute__((cleanup))` 在任何返回路径上解锁。`air_metal_copy.inc` 与 `air_metal_compute.inc` 里也有入口，`tools/k90auto/build-air.py` 的 `FILES` 加上这两个文件，否则改动不会进入构建树。

同一轮另有两条读数：

- backboardd 调用 `IOSurfaceClientQueryTransactionList`（MiniIOSurface 58 号调用，5 个标量入、3 个标量出），内核答 `kIOReturnUnsupported`。`MiniIOSurface.cpp` 对 58 号返回成功和空列表，内核 `12377-cmd1` 起生效：`lock3cpu4` 记 2848 次 `got non-success return from kernel`，`render1` 为 0。
- `iconservicesagent` 没有 Metal 设备，230 次 `Failed to serialize finalized icon ... TextureIOError.usingSoftwareRenderer`。`package.py` 的 `ICON_METAL=1` 把 Metal 注册库注入它，并在它的任务 plist 与 launchd 缓存里设 `REDWOOD_SB_METAL=1`；注册库的目标表有 `iconservicesagent`。`lock2cpu4` 之后默认关闭，见 §6。

## 4. 其他读数

- `appprotectiond` 在 `homecycle1` 里 159 秒平均占 56% 的 CPU（内核 `caught burning CPU`），`interactive1` 起用 `JOBS_DROP` 去掉。
- `iconservicesagent` 开机后 12 秒内做了 1149 次图标缓存垃圾回收，之后持续报 `Failed to serialize finalized icon`。
- `homecycle1` 主核簇最高 78.3 °C（`cpufreq: ... hottest 78.3 C`）。
- 插着 USB 时电池在放电：`lock1` 的电量计电流为 -300～-760 mA，SOC 一直是 80%。loader 读高通 UEFI 充电缓存 25 次失败 13 次，最后一次是 `charger=0 charging=0`，内核据此报「not on a charger」。状态栏右上角的电池图标不显示，控制中心里显示 80%、未充电。

## 5. 截图里的渲染缺口（`interactive1`、`ffma1`）

- 设置页向下滚动后，顶部导航栏的滚动边缘模糊不对：背后的列表内容被拉成横向条纹，没有纵向模糊；模糊区下半段整片发黑，没有渐隐到下面的内容。backboardd 在这段时间建的管线里有 `variable_blur_vert_lph`／`glass_background_no_bleed_lph`、`downsample_blur_vert_lph` 配 `downsample_4_frag_lph`、`downsample_8_frag_lph`、`narrow_blur_19_frag_lph`。用户另报滚动时闪烁较多。
- 设置「通用」页各行左侧图标和页首大图标都是灰色空方块；设置首页的「电池」一行缺图标。
- 103～332 秒之间所有截图的状态栏时间都是 11:58。
- 「关于本机」的歌曲、视频、照片一直是 Loading…，容量为 Zero KB。这一条属于系统数据服务，与渲染无关。

## 6. `lock2cpu4` 与 `lock3cpu4`

- `lock2cpu4` 给 `iconservicesagent` 注册了 Metal。它的绘制被拒绝了 3 类：`device` 缓冲绑在 40、344 字节偏移；RGBA16Float 表面每行 576、448、192、704 字节；格式 90（RGB10A2Unorm）17 次。随后内核报 `adreno8: context EOP timeout failed; submissions closed`，GPU 停用到冷启动，CoreAnimation 改用软件合成，主屏图标和电池图标在软件合成下都能显示。
- `lock3cpu4` 去掉了这项注册，`GenericARMPE: 4 of 4 processors are running`，12 份日志快照里没有 GPU 错误。从设置上划返回不再转菊花（用户确认）。主屏只有文字、没有电池图标。

## 7. 从日志自动找渲染问题

### 7.1 工具

`tools/k90auto/render-health.py` 合并一轮的日志快照，把驱动、AIR 库、QuartzCore 的 Metal 日志、MiniIOSurface 与 GPU 驱动里的失败行按类别分组计数，并能和另一轮逐行对比。用法与读法见 `tools/k90auto/README.md` §8。合并时发现两点：

- 每份快照是同一段开机日志头加一个 1 MB 的环。`lock3cpu4` 里有 3 次两次拉取之间环已转过一整圈，这几处的行丢了；之前的合并在这里把整份快照连同日志头重新接上，开机阶段的行会被数 4 次。现在只接日志头之后的部分，并报告缺口数。
- backboardd 每个慢提交按 work 各打一行 `commit N has run for`，`lock3cpu4` 的一个快照窗口里有 2489 行，占满了环的三分之一。现在每当提交时长翻倍才打一行；`rd in` 的门槛从 50 ms 提到 500 ms；无拷贝缓冲的 `copied` 行只打前 32 次和每第 256 次。

### 7.2 `lock3cpu4` 的读数与第一批修复（`render1`）

| 类别 | 次数 | 原因 | 修复 |
|---|---|---|---|
| QuartzCore `Failed to allocate MTLTexture from IOSurface` | 988（其中 0xf8 号表面 883） | 驱动的 IOSurface 导入不认格式 30（RG8Unorm） | 格式表加 30 对 `'LA08'`（SpringBoard 与 Spotlight 建的两字节像素表面） |
| `compute_average_luma` 调度失败、命令缓冲报错 | 各 160 | 线程组缓冲的长度由 `-setThreadgroupMemoryLength:atIndex:` 给，调度入口没有这个参数 | AIR 新入口 `rwa_dispatch_threadgroup`，动态线程组缓冲排在静态线程组数组之后，Gallium 用 `variable_shared_mem` 加上这段长度；驱动记下编码器给的长度 |
| SpringBoard `the draw failed` | 10 | 渐变着色器的 `device` 缓冲绑在 124 字节偏移，Gallium 的 `shader_buffer_offset_alignment` 为 64 | 改为 4，与 turnip 的 `minStorageBufferOffsetAlignment` 相同（`tools/mesa/freedreno-ssbo-offset-4.patch`） |
| `nil buffer from memory`（640x155，114688 字节） | 12 | 无拷贝缓冲只接受 64 KiB 以内 | 上限改为 16 MiB |
| `Failed to allocate [281 x 609] BGRA framebuffer` | 3 | QuartzCore 在这之前调用 `newTextureWithDescriptor:iosurface:plane:` 得到 nil | 由拒绝日志定位，见下一行 |
| 驱动 `no drawable` | 按 2 的幂打印 | 打印次数由所有原因共用一个计数 | 前 64 次逐条打印，带 Metal 格式、用途和表面的 FourCC、尺寸、行字节数 |
| IOSurface 58 号调用 | 2848 | 内核未实现 | 内核 `12377-cmd1` |

RGBA16Float 表面的行字节数第一批放宽到 64 字节（只采样的导入）。`render1` 对比 `lock3cpu4`：上表各项在 `render1` 均为 0，但这一轮没有打开设置，部分路径没有走到，需要 `render2` 的固定巡检对比。

## 8. `render1`：图标、电池图标与壁纸

截图（`kernel-12377-cmd1-render1/run/tour-sheet.png`）：壁纸全黑，应用图标、小组件内容和程序坞里的图标都没有，标签和程序坞底板在；状态栏只有时间。缺的都是其他进程以 IOSurface 交来的内容，SpringBoard 自己画的部分都在。

- `iconservicesagent` 仍是软件渲染：231 次 `Failed to serialize finalized icon ... TextureIOError.usingSoftwareRenderer`，开机后反复做图标缓存垃圾回收（1148 次）。图标没有生成出来。
- `sb26: icon rendering Metal device=1`：SpringBoard 有 Metal 设备，`SBIconImageView` 走 Liquid Glass 的 Metal 绘制。SpringBoard 把一张 120x120、每行 960 字节的 RGBA16Float 表面当渲染目标导入（`usage 0x5`），被 128 字节的行对齐拒绝。
- PosterBoard（pid 38）在运行，日志里没有它的输出；三个线程都在等待。壁纸由谁绘制、为什么没有内容，留给图层树读数。

第二批修复（`render2`）：

- 行字节数按用途放宽：只采样的导入只要求整像素，A8XX 纹理描述符的 `TEX_LINE_OFFSET` 以位为单位；颜色渲染目标要求 64 字节，这样的渲染目标由 `fd_gmem_render_tiles` 改用 sysmem 直接写入，GMEM 回写按 16 像素块写，会越过行尾。`fdl_pitch` 的第 0 级返回导入时给的行字节数。补丁 `tools/mesa/fdl6-linear-import-pitch.patch`，驱动侧的 64 字节检查一并去掉。
- AIR 格式表加 90～94（RGB10A2Unorm、RGB10A2Uint、RG11B10Float、RGB9E5Float、BGR10A2Unorm），按首个通道在低位的布局对应 Gallium 格式。
- SpringBoard 注入库加图层树读数：rwsh 发 `notify com.redwood.layers.<过滤词>`，见 `tools/k90auto/README.md` §8。
- `ICON_METAL=1`：上面三项覆盖了 `lock2cpu4` 里 `iconservicesagent` 被拒绝的绘制，这一轮重新给它注册 Metal。

### 8.1 `render2`

- 开机 41 秒（01:48:52）`iconservicesagent` 的 `path_exterior` 管线被拒绝（顶点模块里有一个沿循环回边传回的指针 phi），RenderBox 记 `precondition failure: pipeline error`。
- 接着它的第 6 次提交（20 个缓冲，10x10 的三个颜色附件加深度，管线 `primitive_coverage`、`primitive_color`）没有完成：GMU 发 `HFI fatal message 150 data 0x1`，内核关闭 GPU 提交，驱动报 `THE GPU DID NOT FINISH`。KGSL 的编号里 150 是上下文出错，`0x1` 是 GPU 硬件挂起。
- 之后 CoreAnimation 走软件合成，主屏图标、小组件和电池图标都显示（`tour-sheet.png` 0、1 号）；打开设置并滚动正常；上划回主屏后 backboardd 在 `ogl-context.cpp` 的 `push_surface` 断言失败，SpringBoard 与 backboardd 各重启两次，屏幕停在菊花。
- `render3` 的改动：AIR 支持沿循环传回的指针（偏移放进寄存器，资源必须相同）；驱动在每个进程的前 16 次提交里列出用到的管线，`render-health.py` 在 GPU 停止时把最后几次提交和这些管线按着色器名打印出来。

### 8.2 `render3`

- `path_exterior` 不再被拒绝。新出现的拒绝：顶点模块里 phi 的某个操作数本身是运行时选出的指针（`iconservicesagent` 4 次，SpringBoard 1 次）；片段模块调用只声明未定义的 `custom_fn.MTL_VISIBLE_FN_REF`（2 次）；`fpba2ma11bemha4` 读 1 号纹理而只绑定了 1 张纹理（3 次）。
- 01:55:31 内核报 `context EOP timeout failed; submissions closed`。停止前最后几次提交来自 `iconservicesagent`（9～13 号）和 SpringBoard（14 号），几个进程的提交交错，`trace commit` 列出的管线不能指出是哪一个绘制没有完成。
- 截图（`kernel-12377-cmd1-render3/run/tour-sheet.png`）：主屏图标、小组件、设置、控制中心都在，壁纸仍是黑色；设置滚动后顶部的「Settings」小标题和底部搜索栏下面没有模糊背景，列表文字直接透出来；回主屏那一步截到的是锁屏。01:56:30 backboardd 在 `push_surface` 断言失败，SpringBoard、backboardd、`iconservicesagent` 各运行了 3 个进程。

### 8.3 `render4`

- 驱动的 `REDWOOD_SYNC_DRAWS=1`（打包时由 `JOB_ENV` 加给指定任务）在每个绘制之后提交并等待完成，没有完成的那个绘制按管线、附件数和绑定数打印。`iconservicesagent` 第 1 次提交的第 2 个绘制没有完成：`primitive__vertex` 加片段着色器 `fe2baca3dba6dhmha4`，3 个颜色附件，没有纹理，1 个缓冲。同一提交的第 1 个绘制（`ffebaca3ca7dhmha4`）完成了。
- `fe2baca3dba6dhmha4` 不在 RenderBox 的 `default.metallib` 里。`archive.metallib` 是一个 Mach-O，装着 17 个约 732 字节的函数拼接描述，这类着色器在运行时拼出，模块只能从日志里取。
- SpringBoard 打开 os_log 后，合并日志有 180 MB、12 处缺口，开机解锁那一行落在缺口里，`cycle.py` 没有执行巡检。本轮各类计数也受缺口影响，`render3` 的部分拒绝在这里计为 0 不能说明已经消失。
- `render5` 的改动：同步模式下驱动保留每个渲染管线的两个模块，绘制没有完成时以 `AIRFAIL begin hung-vertex`／`hung-fragment` 打印出来，`render-health.py` 单独归为 `hung-shader`；os_log 只开 PosterBoard。

### 8.4 `render5` 与 `render6`：挂起的绘制

三轮里没有完成的绘制都来自 `iconservicesagent`，形状相同：顶点着色器 `primitive__vertex`，片段着色器是 RenderBox 运行时拼出的 `primitive` 类，3 个颜色附件，没有纹理，1 个缓冲。

| 轮次 | 位置 | 片段着色器 | 帧缓冲读取 |
|---|---|---|---|
| `render4` | 第 1 次提交第 2 个 work | `fe2baca3dba6dhmha4` | 未取到模块 |
| `render5` | 第 2 次提交第 4 个 work | `ffia2ba3ca7dhmha4` | 读 1 号渲染目标 `coverage` |
| `render6` | 第 1 次提交第 4 个 work | `ffeba5ca7jbmhia3` | 没有 |

- 两个取到的片段着色器都没有循环和内存写入：先由 `fwidth` 算边缘覆盖率，覆盖率为 0 时 `discard_fragment`（NIR 里是 `demote`），再写 `color`（half4）和 `coverage`（half2）两个输出。宿主上用当前 AIR 源码编的 `air2nir` 翻译结果没有发现异常。
- `render6` 用 `FD_MESA_DEBUG=sysmem` 让 `iconservicesagent` 的批次不走 GMEM，仍然挂起；这个开关是否生效，日志里没有读数。
- `render4`～`render6` 的内核不打印已完成的时间戳，同步模式下没有完成的绘制可能排在别的进程挂起的提交之后（§8.5），上表三行的归属都没有确认。
- `render6` 里第 2、3、4 个 work 各自一次提交，命令流都是 353 个字，只有第 4 个没有完成；内核报 `RedwoodGPU no answer; last timestamp 9; SMMU fault 0`，没有缺页。
- 软件合成下回到主屏时 backboardd 在 `ogl-context.cpp` 的 `push_surface` 断言失败（`render3`、`render6` 都出现），这一步只在 GPU 停用之后发生。
- `render7` 的改动：同步模式下每个绘制在提交前打印一行，包括图元类型、顶点与实例数、每个颜色附件的格式、尺寸、采样数、是否基于 IOSurface、是否清除，以及深度附件、视口与裁剪，用来对照同一个 pass 里完成和没完成的绘制；PosterBoard 加 `OS_ACTIVITY_MODE=debug`。

### 8.5 `render7` 与 `render8`

- 内核给所有进程只用一个 GMU context（`adreno8_context_submit`），提交按顺序完成；同步模式下某个绘制没有完成，只有它之前所有进程的提交都完成了，挂起的才是这个绘制。`render11` 里 `iconservicesagent` 报没有完成的绘制排在 SpringBoard 挂起的第 9 次提交之后。归属以 retired 时间戳和 HFI 150 的时间戳为准（`render9` 起）。
- `render7` 里 GPU 停在 SpringBoard 的第 4 次提交（57 个缓冲、3385 个字）或 `iconservicesagent` 没有绘制的第 5 次提交（150 个字），日志分不出是哪一个。
- `render3`、`render5`～`render8` 停用前一秒内都有 SpringBoard 的 `fpba2ma11bemha4 reads texture 1 and 1 texture was bound`。这次拒绝发生在 CPU 侧、在设置任何 Gallium 状态之前，和挂起同时出现，是因为两个进程都在解锁时开始画图标。
- `render8` 的绘制描述：`iconservicesagent` 画图标的 pass 有三个颜色附件，依次是 RGBA16Float（115）、RG16Float（65）、RGBA16Float，深度附件是 Depth32Float_Stencil8（260），深度附件清除，深度测试并写入，绘制是带裁剪的索引三角形带，尺寸在 64x64 到 128x128 之间。
- 各轮完成的 `iconservicesagent` 绘制都用 `plane__vertex`，挂起的都是第一个用 `primitive` 类顶点着色器（`primitive__vertex`、`primitive_gradient_vertex`）的绘制。两个着色器翻译成 NIR 后没有循环和异常结构。
- `render8` 关掉 LRZ 后仍然挂起，LRZ 不是 `iconservicesagent` 挂起的原因。
- 内核只打印 GMU `context bad`（150）消息的第二个字。`render9` 换内核 `12377-cmd2`：打印这条消息的全部 26 个字，`RedwoodGPU ... no answer` 一行加上已完成的 EOP 时间戳。

### 8.6 `render9` 与 `render10`：GMU 的挂起报告

- `render9` 的内核行是 `last timestamp 12, retired 10`：第 11 次提交没有完成，即 `iconservicesagent` 第 2 次提交第 4 个 work，`primitive__vertex+ffia2ba3ca7dhmha4`，10 个索引的三角形带。同一 pass 里完成的绘制是 4 个索引的四边形（索引 `1 0 2 3`）和 64 个索引、多实例的路径。
- `render10` 挂起的是第 12 次提交，即 SpringBoard 的 57 缓冲提交，其中也有一个 `primitive__vertex` 绘制（`ffea2ba11dhmha4`）。两个进程挂起的批次都含 `primitive__vertex`，片段着色器各不相同。
- `primitive__vertex` 用 16 位的 `vertex_id` 做整数运算（`and`、比较），按 `vid > 3` 分支算外圈顶点，10 个索引是绕矩形一圈的三角形带。`render12` 取到的 A830 汇编见 §8.9。

`render10` 的 HFI 150 全文（26 个字）按 KGSL 的布局读：

| 字 | 值 | 含义 |
|---|---|---|
| 1 | 1 | 版本 |
| 2、3、4 | 1、2、0xc | GC context 1，policy 2，时间戳 12 |
| 5、6、7 | 0xffffffff、1、0 | 没有 LPAC context |
| 8 | 0x259 | 错误码，对应的名称还没有查到 |
| 9 | 0x00100002 | 第 2 类（ringbuffer）的段，16 个字 |
| 10～25 | 键值对 | RB 0，RPTR 0x548，WPTR 0x5f9，大小 0x2000 字，已排队时间戳 13，已完成时间戳 11，基址 0x10028000 |

报告里没有错误寄存器段（第 1 类），GMU 报的是 CP 停在第 12 次提交上，没有报操作码错误或受保护寄存器写入。

### 8.7 Metal 的图元重启

Metal 的索引绘制总是开启图元重启：16 位索引的 0xFFFF、32 位索引的 0xFFFFFFFF 结束当前图元，所有图元类型都是这样（Apple `drawIndexedPrimitives` 文档，gpuweb issue 1220 引用了原文）。AIR 的绘制原先写的是 Metal 没有重启索引并关闭了重启，现在改为索引绘制都开启，重启值不计入索引范围。这一项从 `render11` 起在机上，`render13` 挂起的仍是 10 个索引的 `primitive__vertex` 绘制，挂起和图元重启无关。

### 8.8 PosterBoard 的数据存储

- `render10` 的探针读数：`-[PBFPosterExtensionDataStore initWithURL:...]` 的 URL 是 `file:///var/mobile/Library/Application%20Support/`，返回 nil，错误为 nil；调用方随后生成 `Data store could not be created for an unknown reason which evades explanation`。
- 传入的 extension provider 是 nil，这是调用方 `buildDataStoreForURL:` 写死的（`mov x4, #0`），不是失败原因。
- 初始化里没有新建 NSError。之前的 57 个错误来自旧壁纸迁移读 `/var/mobile/Library/SpringBoard/LockBackground*.jpg`、`HomeBackground*.jpg` 等文件不存在，以及 `com.apple.managedconfiguration.profiled.public` 查找失败。
- 初始化会在四处返回 nil：迁移失败、bundle ID 迁移失败、完整性校验失败、SQLite 数据库打开失败。这四处只发 `os_signpost`，控制台看不到，探针在 `userland/src/inject_posterboard.c`。
- `render11`、`render13` 的读数：`isDataStoreUpToDateForCurrentVersion` 为 0，`_mostUpToDateValidDataStoreToMigrateFrom` 为 NSNotFound，`+migrateDataStoreAtBaseURL:fromVersion:59 toVersion:61 ...` 返回 NO 且没有错误，初始化随后返回 nil。PosterBoard 一直重试，`render13` 里重试了 1151 次。
- 迁移的版本范围由两个类方法给出，最低 59、当前 61。一个版本有效的条件（`_PBFDetermineDataStoreViabilityForVersionWithinBaseURL`）是数据存储、扩展容器、图库缓存三个目录存在，60 起还要有 SQLite 库，并且每一项都满足 PosterFoundation 的 C 函数 `PFPosterPathURLResourceValues()` 给出的资源值，其中有文件保护等级。
- RAM 盘所在的卷不支持数据保护（同一日志里 chronod 记 `volume does not support data protection`），文件保护等级读回来不会相符，任何版本都不会有效，迁移每次都失败。`render14` 替换的是 `PBFPosterModelStoreCoordinator` 的三个预期资源值类方法，不在这条路径上，迁移照样失败。
- `render15` 改在 NSURL 的四个资源值方法（`pbf_URLIsReachableAndConformToResourceValues:error:`、`pbf_URLConformsToExpectedResourceValues:error:`、`pbf_updateResourceValues:error:`、`pbf_recursivelyUpdateResourceValues:error:`）里去掉 `NSURLFileProtectionKey`。从 59 到 61 的迁移成功，SQLite 库打开，完整性校验通过，数据存储初始化返回非 nil。
- 下一处失败：`+[PBFPosterModelStoreCoordinator createNewStoreCoordinatorWithPath:error:]` 约 50 次，`errno=-1`，同时有 `Error marking ... as purgable`。PosterFoundation 用 `fsctl(path, 0xc0084a44, …)` 标记 purgeable，即 APFS 的 `'J'` 68 号调用；我们的 APFS 对所有 ioctl 回 ENOTTY。内核 `12377-cmd6` 让这一个调用返回成功，还没有上机。

### 8.9 `render11`～`render13`：挂起绘制读帧缓冲

- `render12` 的 HFI 150 时间戳是 10，已完成 9，即第 10 次提交，SpringBoard 第 2 次提交第 3 个 work：`primitive__vertex+ffea2ba11dhmha4`，4 个索引的四边形，128x128 的三个颜色附件，深度测试只读，绑定 1 个纹理。同一提交的第 1、2 个 work 完成。
- 第 2 个 work 的顶点着色器 `vhia3ea2dba6dhmha4` 与 `primitive__vertex` 的 A830 汇编只差常量偏移、一组输出和指令顺序，两者都没有循环，主体里都没有内存访问。顶点着色器不是挂起的区别所在。
- `render13` 去掉 `discard_fragment` 后仍然挂起，HFI 150 时间戳 10，是 `iconservicesagent` 第 2 次提交第 4 个 work，`primitive__vertex+ffia2ba3ca7dhmha4`，10 个索引。日志确认两个进程都读到了 `AIR_DISCARD=off`。丢弃片元不是挂起的原因，这个开关只用于这一轮，AIR 源码里没有保留。

有时间戳确认的两个挂起绘制，片段着色器都读帧缓冲：`ffea2ba11dhmha4` 读 0 号目标 `dest` 与 1 号目标 `coverage`，`ffia2ba3ca7dhmha4` 读 1 号目标。`render13` 的片段着色器汇编里，帧缓冲读取是两条 `isamm.a.s2en.uniform.base4`，按片元坐标、`VARYING_SLOT_LAYER` 与采样号读 bindless 描述符 0x37、0x38。有汇编可查的完成绘制（`fca15dhmha4`、`fhia3ea2dba6dhmha4`、`fpba2ia11bemha4`）都不读帧缓冲。

freedreno 对读帧缓冲的绘制有三处特殊处理，挂起可能出在其中之一：

- 批次带 `FD_GMEM_FB_READ`，总走 GMEM。描述符由 `patch_fb_read_gmem` 的 A8XX 分支从零拼出，基址是 GMEM 内偏移；turnip 的同类描述符从完整的视图描述符改出（`tu_cmd_buffer.cc`），两者至少 7 号字（数组层偏移）不同：freedreno 填资源的层大小，turnip 在单层时填 0。
- `GRAS_SC_CNTL.single_prim_mode` 在 GMEM 下设为 `FLUSH_PER_OVERLAP`，因为 AIR 把帧缓冲读取标为 coherent。
- `freedreno-darwin.patch` 在一个批次里第一个读帧缓冲的绘制之前加 `CCU_CLEAN_COLOR` 与 `CACHE_INVALIDATE`。这一段是为 a642l 写的，同步模式下每个绘制自成一个批次，每个读帧缓冲的绘制都会带上。

`render6` 用 sysmem 仍然挂起，但那一轮的归属没有确认（§8.4），不能据此排除 GMEM 路径。为了区分这三处，内核 `12377-cmd4` 在挂起报告之后读 RBBM 与 CP 状态、各级 IB 的基址与剩余长度，并打印 CP 位置前后的命令字，用 `tools/k90auto/cp-words.py` 解成包名。还没有上机。

### 8.10 `render15` 的 CP 转储

`render15` 挂起在第 6 次提交（HFI 150 时间戳 6，已完成 5）。转储的读数：

- BR 与 BV 两个流水线的 IB1 都是 `0x10986000`，`REM_SIZE` 0、`INIT_SIZE` 495；BR 的 IB2 是 `0x10996500`，`REM_SIZE` 0、`INIT_SIZE` 78。CP 把这次提交的命令全部取完了。
- IB1 的最后几个包依次是绘制流 IB（`0x1098e000`，124 个字）、`CP_SET_DRAW_STATE`、IB2（78 个字，两次 `CCU_RESOLVE`，即 GMEM 写回）、`LRZ_CACHE_FLUSH`、`CCU_RESOLVE_CLEAN` 和带时间戳写入的 `CACHE_FLUSH_TS`。时间戳没有写出，CP 在等前面的工作排空。
- `RBBM_STATUS` 为 0xfe1007：CP 忙、`HLSQ_BUSY`、slice 忙；`PC_BUSY`、`VPC_BUSY`、`UCHE_BUSY`、`VSC_BUSY` 都为 0。停住的是着色器一侧，图元装配之前的部分已经空闲。
- 读帧缓冲的片段着色器用 `isamm` 按 bindless 描述符 0x37、0x38 取像素，GMEM 下这两个描述符由 `patch_fb_read_gmem` 的 A8XX 分支拼出（§8.9）。转储与「着色器等这次纹理读取」一致，`render16` 用 sysmem 让描述符改走普通视图来验证。
- 命令字用 `tools/k90auto/cp-words.py` 解码；它对取完的级别把位置放在末尾，标出最后一个包。
- `render16` 用 sysmem 仍然挂起，GMEM 描述符排除。绘制流 IB 的最后几个包是读帧缓冲前的屏障（`CCU_CLEAN_COLOR`、`CACHE_INVALIDATE`、`CP_WAIT_FOR_IDLE`、`CP_CCHE_INVALIDATE`）和挂起的 `CP_DRAW_INDX_OFFSET`。屏障里的 `CP_WAIT_FOR_IDLE` 已经完成，屏障也排除。`RBBM_STATUS` 仍是 0xfe1007。
- 10-26 iOS 16.5 的 GLES 路径在 A830 上读帧缓冲正常（[GPU 桌面记录](2026-10-26-gpu-desktop-acceleration.md)），同一个 Mesa、同一套 `nir_lower_fb_read` 和屏障。这次的两个挂起管线有一个那时没有的特征：片段着色器读 1 号目标 `coverage`（RG16Float），而管线对 1 号目标的写掩码是 0。
- 读帧缓冲的绘制设了 `single_prim_mode`（GMEM 为 `FLUSH_PER_OVERLAP`，sysmem 为 `FLUSH_PER_OVERLAP_AND_OVERWRITE`），硬件按重叠等前面图元的写入。推断读一个不写的目标时这一等待不会结束。`render17` 用 `FD_FB_READ_NO_FLUSH=1` 让这类绘制保持 `NO_FLUSH`，仍然挂起，这一推断不成立。这个开关只用于这一轮，设备 Mesa 树里没有保留。
- 与 iOS 16.5 正常的 GL 帧缓冲读取相比，`nir_lower_fb_read`、屏障、单图元模式都相同，不同的是附件组合（三个附件、RG16Float）、读不写的目标、深度附件，以及顶点与片段着色器的 varying 组合。`nir_lower_fb_read` 的层号来自 `VARYING_SLOT_LAYER` 的 flat 读取，`primitive__vertex` 不写这一项；`ffea2ba11dhmha4` 除此之外不读任何 varying，读的是 4 号位置。
- `render18` 用 `AIR_FB_LAYER0=1`：AIR 自己生成 `txf_ms_fb`，层号为常数 0，片段着色器不再读 `VARYING_SLOT_LAYER`；单层目标的结果不变。仍然挂起，同一个 SpringBoard 绘制，层号读取排除。这个开关只用于这一轮，AIR 源码里没有保留。
- `render19` 用 `AIR_FB_READ_WRITEMASK=1`：片段着色器读、而管线写掩码为 0 的目标改为四个通道都写。仍然挂起，同一个 SpringBoard 绘制，「读一个管线不写的目标」排除。开关只用于这一轮，AIR 源码里没有保留。
- `render20` 用 `FD_FB_READ_LATE_Z=1`：同一次提交的第 2 个 work 同样开着只读深度测试，能完成；freedreno 对读帧缓冲的着色器在深度测试开启时选 `EARLY_Z`，10-26 的 GL 绘制没有深度附件，走 `LATE_Z`。这一轮让读帧缓冲的绘制改用 `LATE_Z`，仍然挂起，z 模式排除。开关只用于这一轮，设备 Mesa 树里没有保留。
- `render18`～`render20` 逐项改状态都没有结论。下一批改为从着色器里减：`render21` 用 `AIR_FB_READ_ZERO=1` 把帧缓冲读取换成常数 0，freedreno 的批次标记不变，先确认挂起是否由读帧缓冲引起。

### 8.11 `render21`～`render30`：拆分读帧缓冲的挂起

- `render21` 的 SpringBoard 第 2 次提交第 3 个 work（`primitive__vertex+ffea2ba11dhmha4`）在帧缓冲读取换成常数 0 后完成，SpringBoard 接着完成第 2 次提交的第 4、5 个 work 和第 3 次提交的两个 work。读帧缓冲是这一绘制挂起的原因。
- 开关只替换着色器里的读取，`uses_fbfetch_output` 等标记照旧，freedreno 仍按读帧缓冲的批次处理（`FD_GMEM_FB_READ`、`single_prim_mode`）。剩下的区别在着色器一侧：两条 `isamm`、片元坐标、采样号（读采样号会打开逐采样着色）和 bindless 描述符 0x37、0x38。
- 这一轮停在 `iconservicesagent` 第 1 次提交第 4 个 work，`primitive__vertex+ffeba5ca7jbmhia3`。这个片段着色器不读帧缓冲，用 `fwidth` 和 `discard_fragment`；`render6` 没有确认归属的挂起绘制也是它。
- 这次没有 HFI 150，也没有转储。内核在外部缓冲解除映射前等全部提交完成，`CONTEXT_WAIT_NS` 只有 200 毫秒，在 backboardd 第 15 次提交之后 200 毫秒超时并关闭提交，没有打印时间戳。`iconservicesagent` 的「did not finish」是提交关闭的结果，不能据此认定它挂起。
- 内核 `12377-cmd7`（在 cmd5 上改，不含 cmd6 的 APFS 改动）把这一等待改为 2 秒，超时时打印等待的、最后提交的和已完成的时间戳并转储 CP。`render22` 用 cmd7、开关同 `render21`，确认停在哪一个绘制。
- `render22`：`iconservicesagent` 第 1 次提交第 4 个 work（`ffeba5ca7jbmhia3`）完成，`render21` 的停止是 200 毫秒等待造成的误报。GPU 跑到第 29 次提交，HFI 150 时间戳 29、已完成 28，是 `iconservicesagent` 第 5 次提交第 1 个 work：`primitive_gradient_vertex+fgea14dhmha4`，96x96 的三个颜色附件，深度清除且读写，绑定 4 个纹理。
- 这次的转储与 `render15` 相同：IB1、IB2 都取完，最后一个包是 `CACHE_FLUSH_TS`，`RBBM_STATUS` 0xfe1007。驱动打印挂起模块时 `iconservicesagent` 被结束，只打出半个顶点着色器，片段着色器没有取到。驱动改为先打印片段着色器；`render23` 开关不变，`iconservicesagent` 加 `IR3_SHADER_DEBUG=fs`，取 `fgea14dhmha4` 的 A830 汇编。
- `render23`：GPU 跑到第 107 次提交（HFI 150 时间戳 107、已完成 106），停在重启后的 `iconservicesagent`（pid 100）第 4 次提交第 4 个 work，`primitive_gradient_vertex+fgea2ca11dhmha4`。同一管线在 pid 63 画过一次并完成。两次的区别如下：

| | 完成（pid 63） | 挂起（pid 100） |
|---|---|---|
| 附件尺寸 | 87x87 | 192x192 |
| 颜色附件 0 | IOSurface，清除 | IOSurface，载入 |
| 在 pass 中的位置 | 第 1 个绘制 | 第 4 个绘制 |

- `fgea2ca11dhmha4` 的 A830 汇编：用片元坐标除以 512 作坐标取纹理 t#3，有条件 `kill`，输出 DATA1、DATA2。
- 各片段着色器的输入（`IR3_SHADER_DEBUG=fs`）里，两个挂起的着色器（帧缓冲读取未替换的 `ffea2ba11dhmha4`、`fgea2ca11dhmha4`）都有两项：0 号输入是空位，同时读片元坐标。空位来自 AIR 为每个 `[[stage_in]]` 成员按声明顺序分配 driver_location，没被读的成员（这里是 `primitive_position`）也占一个位置；ir3 的 `so->inputs[0]` 保持零值，打印成 `VARYING_SLOT_POS cm=0`。读片元坐标而没有空位的 `fpba*`、`foba*` 能完成，`fpba2ia11bemha4` 在 192x192 下也完成；有空位而不读片元坐标的着色器，未见挂起。
- GL 的 st/mesa 在编译前删去没被读的输入并从 0 重新编号，10-26 的 GL 着色器没有这种空位。`render24` 用 `AIR_FS_INPUTS_PACKED=1` 在 `finalize_for_gallium` 里做同样的处理，帧缓冲读取恢复为真实读取，以必挂的 `ffea2ba11dhmha4` 检验。
- `render24`：`ffea2ba11dhmha4` 的输入只剩 `VARYING_SLOT_LAYER`（`il=0`）和系统值，空位已去掉，仍然在第 6 次提交挂起。输入空位排除，开关只用于这一轮，AIR 源码里没有保留。`fgea2ca11dhmha4` 与 `ffea2ba11dhmha4` 的共同点剩下「用片元坐标算坐标的纹理读取」，而 `fpba*` 也这样读却能完成，这一共同点不足以解释挂起。
- `render25` 用 `AIR_FB_READ=sample0`：AIR 自己生成 `txf_ms_fb`，采样号为常数 0，片段着色器不再读 `SYSTEM_VALUE_SAMPLE_ID`，逐采样着色随之关闭。
- `render25`：汇编里 `SYSTEM_VALUE_SAMPLE_ID` 已经不在输入中，`ffea2ba11dhmha4` 仍在第 6 次提交挂起，采样号与逐采样着色排除。挂起的 `ffea2ba11dhmha4` 与 `ffia2ba3ca7dhmha4` 都读 1 号目标（RG16Float，描述符 0x38），10-26 的 GL 只读 0 号目标。`render26` 用 `AIR_FB_READ=rt0`：读取照常生成 `txf_ms_fb`，只把目标统一改为 0 号。
- `render26`：仍在 SpringBoard 第 2 次提交第 3 个 work 挂起（这一轮是第 7 次提交），1 号目标与 RG16Float 排除。
- `render18`～`render26` 从读帧缓冲里逐项去掉层号、采样号、目标号，并改写掩码、z 模式、单图元模式、GMEM／sysmem，都仍然挂起；只有整个读取换成常数 0 时完成。剩下的是 `isamm` 本身、片元坐标与 bindless 描述符的组合，以及绘制的其余状态，逐项减已经得不出新信息。
- `render27` 改为一次取全量状态：内核 `12377-cmd8` 在挂起后打印 BR 的整条 IB1，并沿 `CP_INDIRECT_BUFFER`、`CP_SET_DRAW_STATE` 打印它引用的 IB 与状态组（三层），再按 `SP_GFX_BINDLESS_BASE[4]` 打印片段阶段 bindless 描述符的 55～58 槽，即 GPU 读到的帧缓冲描述符；freedreno 用 `FD_FB_READ_DUMP=1` 打印修补时写入的描述符；AIR 用 `AIR_FB_READ=log` 打印每个读帧缓冲的片段着色器及其目标，backboardd 也打开，用来找能完成的读帧缓冲绘制。
- `render27` 的读数：
  - GPU 从 bindless 描述符 55～57 槽读到的内容，与 freedreno 修补时写入的逐字相同，描述符的写入与缓存一致性排除。三个 GMEM 描述符：RGBA16F、RG16F、RGBA16F，GMEM 基址 0、0x30000、0x48000，128x128，bin 宽 192。
  - `tools/k90auto/cp-state.py` 从命令树还原出挂起绘制的寄存器状态（GMEM pass 生效的 draw-state 组）。片段输入相关的寄存器与 freedreno 按着色器算出的一致：`SP_REG_PROG_ID_0` 采样号在 r2.x，`SP_REG_PROG_ID_2` 片元坐标 xy 在 r0.x、zw 在 r0.z，`SP_PS_CNTL_1.SYSVAL_REGS_COUNT` 为 5，`GRAS_CL_INTERP_CNTL` 与 `RB_INTERP_CNTL` 的 `COORD_MASK` 为 3。
  - backboardd 这一轮没有读帧缓冲的片段着色器；SpringBoard 读帧缓冲的还有 `fpba2iba10bemha4` 与 `compositeSphere`，都排在挂起绘制之后。
- 能完成与挂起的着色器对照下来，最小的挂起组合是片元坐标加 bindless 的帧缓冲读取：`fpba*` 读片元坐标、用非 bindless 的 `sam`，能完成；`render18` 去掉 varying、`render25` 去掉采样号，`ffea2ba11dhmha4` 仍然挂起。turnip 在 A8XX 上读 input attachment 用单采样的 `isam`，ir3 的 `txf_ms_fb` 生成带采样坐标的 `isamm`。`render28` 用 ir3 的测量开关 `IR3_FB_READ_ISAM=1`，帧缓冲读取改用 `isam`，不带采样坐标。
- `render28`：汇编里两条读取都是 `isam.a.s2en.uniform.base4`，`ffea2ba11dhmha4` 仍在第 7 次提交挂起，`isamm` 排除，开关只用于这一轮，设备 Mesa 树里没有保留。我们的 Metal 路径里普通纹理都走非 bindless 的 t#，帧缓冲读取是片段着色器里唯一的 bindless 纹理访问。`render29` 用 `AIR_FB_READ=coord0`：读取仍是 bindless 的 `txf_ms_fb`，坐标换成常数 (0, 0)，着色器不再读片元坐标，用来区分「bindless 读取本身」与「片元坐标加 bindless 读取」。
- `render29`：`ffea2ba11dhmha4` 的输入里已经没有 `SYSTEM_VALUE_FRAG_COORD`，仍在第 7 次提交挂起。挂起不依赖片元坐标，片段着色器经 bindless 描述符 0x37、0x38 读帧缓冲本身就会挂起。
- ir3 为读帧缓冲只设 `so->bindless_tex`，指令里的采样器序号同样走 base4 的 bindless 编码，`SP_PS_CONFIG` 的读数是 `BINDLESS_TEX=1`、`BINDLESS_SAMP=0`；turnip 的着色器纹理与采样器都走 bindless，两个位都置上。`render30` 用 ir3 的测量开关 `IR3_FB_READ_BINDLESS_SAMP=1` 让读帧缓冲的着色器同时设 `bindless_samp`。
- `render30`：命令树还原出的 `SP_PS_CONFIG` 为 0x40503，`BINDLESS_TEX`、`BINDLESS_SAMP` 都置上，仍在第 6 次提交挂起，开关只用于这一轮，设备 Mesa 树里没有保留。同一份还原里 `SP_GFX_BINDLESS_BASE[0..4]` 都写了 64 字节描述符的基址，fb-read 槽的内容与 `render27` 相同。
- 另外两条可能也已排除：
  - 描述符集 BO 的 `FD_BO_GPUREADONLY | FD_BO_CACHED_COHERENT`：redwood DRM 把所有 BO 都做成写合并内存，不区分这两个标志；挂起后 SMMU 没有故障位。
  - turnip 用 `CP_LOAD_STATE6` 预装 bindless 纹理描述符：这是优化，turnip 对 input attachment 也不预装。
- `render31` 用 ir3 自带的调试开关关掉 A7XX 起的可选特性，作为一个变量：`IR3_SHADER_DEBUG=noaliasrt,noaliastex,nopreamble,noearlypreamble,nodescprefetch`。挂起的片段着色器都在预备代码里用 `alias.rt` 把 1 号目标的 y 分量设为常数，读帧缓冲时还用 `alias.tex` 传描述符序号。

### 8.12 `render31`：关闭 ir3 的可选特性后不再挂起

- `render31` 关掉 ir3 自 A7XX 起的五项可选特性（`alias.rt`、`alias.tex`、预备代码、提前预备代码、描述符预取）后，整轮没有 HFI 150。同步模式下 SpringBoard 与 `iconservicesagent` 共完成 261 个绘制，`ffea2ba11dhmha4`、`ffia2ba3ca7dhmha4`、`fhe2afea2ca7dhmha4`、`fhea2ceabmca6dhmha4` 等读帧缓冲的着色器都画过。
- 巡检截图：主屏有图标名称、搜索框和灰色 Dock，没有图标；点 Settings、滑出控制中心与通知中心后截图没有变化；末尾三张是 GPU 合成的模糊主屏。
- 挂起不再出现之后，日志里出现两类绘制被拒绝：
  - SpringBoard 与 `iconservicesagent` 的 `fpba2ma11bemha4`：「reads texture 1 and 1 texture was bound」。这一绘制所在的 encoder 只绑了 0 号纹理，着色器的 9 次纹理读取都落在 gallium 的 0 号槽，即 Metal 的 1 号纹理。驱动改为在同步模式下给被拒绝的管线打印一次模块（`refused-fragment`），下一轮据此核对 AIR 读到的纹理序号。
  - backboardd 的计算着色器 `compute_average_luma`：「reads texture 0 and 1 texture was bound」，即 0 号槽绑定的是 nil。
- 五项特性里是哪一项引起挂起，还要二分：`render32` 只关 `alias.rt` 与 `alias.tex`。
- `render32` 只关两项 alias，`iconservicesagent` 的 `ffia2ba3ca7dhmha4` 在第 9 次提交挂起，原因在预备代码一组。`render33` 只关描述符预取，`ffea2ba11dhmha4` 在第 7 次提交挂起。读帧缓冲的 `txf_ms_fb` 用立即数描述符序号，不经过 `bindless_resource_ir3`，`ir3_nir_opt_prefetch_descriptors` 本来就不会为它生成预取，汇编里也没有预取指令。
- 剩下普通预备代码与提前预备代码。挂起绘制的 `SP_PS_CNTL_0.EARLYPREAMBLE` 为 1，汇编统计有一行「1 early-preamble」。`render34` 只关提前预备代码（`noearlypreamble`）。
- `render34` 只关提前预备代码，整轮没有 HFI 150，同步模式下 218 个绘制完成。读帧缓冲绘制的挂起由提前预备代码引起：`SP_PS_CNTL_0.EARLYPREAMBLE` 为 1 的片段着色器经 bindless fb-read 描述符读帧缓冲时，GPU 停在这次绘制上。
- 修法：设备 Mesa 树的 `freedreno_devices.py` 在 A830 条目末尾加 `GPUProps(has_early_preamble = False)`，覆盖从 `a7xx_gen3` 继承的值，A829、A840 不变；改动记在 `tools/mesa/rebase-26/0004-a830-no-early-preamble.patch`。`render35` 用这份构建、不设任何 `IR3_SHADER_DEBUG` 开关做验证。
- `render18`～`render30` 的测量开关（`AIR_FB_READ`、`FD_FB_READ_DUMP` 等）都已从源码撤掉。内核 cmd7 的 2 秒等待、cmd8 的命令树转储和 `tools/k90auto/cp-state.py` 保留，作为之后挂起排查的工具。

### 8.13 `render35`～`render57`：图标管线与图标内容

- `render35` 验证 §8.12 的修法：同步模式下 SpringBoard 与 `iconservicesagent` 完成 304 个绘制，整轮没有 HFI 150。主屏仍没有图标，`iconservicesagent` 的日志列出四类拒绝，下面逐项处理。
- 未使用的纹理：`fpba2ma11bemha4` 的 `[[texture(1)]]`（`shape_tex`）带 `air.arg_unused`，RenderBox 不绑定它，AIR 仍把它列为必须绑定的资源，驱动拒绝绘制。`air_to_nir.c` 改为不登记带 `air.arg_unused` 的纹理与 API 采样器，对应 Metal 反射里的非活动参数。
- 指针选择：RenderBox 路径顶点着色器（`vjba6la7dhmha4` 等三个）在分段缓冲里二分查找，循环里的 `select` 在同一缓冲的两个位置之间选，循环出口的 phi 合并两个不同偏移。`select` 两侧同属一块内存时改为对偏移做 `bcsel`，phi 的各个输入同属一块内存时偏移进寄存器，与沿循环传回的指针相同；不同资源之间仍然拒绝。RenderBox 把管线失败记为 precondition failure。
- 图标表面导入：`iconservicesagent` 的 45x42、42x42 RGBA16Float IOSurface 每行 384 字节，分配 16384 字节；`fd6_layout.c` 为 GMEM 的 16x4 读写把末级补到 4 行的倍数，布局为 16896 字节，导入因大小检查失败。`fd6_resource.cc` 在线性、单级、单层且各行都落在内存内时接受导入，资源标记 `sysmem_only`，`fd_gmem_render_tiles` 对它直接画在内存里，不经过补齐的行。改动记在 `tools/mesa/rebase-26/0005-linear-import-last-level-padding.patch`。
- `render36`：上述三类拒绝都消失，没有挂起。剩下的拒绝是自定义效果的 `custom_fn.MTL_VISIBLE_FN_REF`、没有片段函数的 `path_edges` 管线，以及 `iconservicesagent` 因 `unable to allocate sampler state: 4` 中止。
- 采样器：RenderBox 的采样器 `minFilter`/`magFilter` 为 2。SDK 头文件只有 0 和 1，Metal.framework 的字符串表里 2 是 `MTLSamplerMinMagFilterCubic`。Gallium 没有三次滤波，`air_metal.c` 按线性采样；着色器自带的 bicubic 采样器仍然拒绝。
- 纹理视图：`backboardd` 的 `compute_average_luma` 绑定的是纹理视图，驱动原来返回 nil，派发因 0 号纹理为空失败。`rwa_texture_view` 用同一个资源建第二个纹理，按视图的像素格式建采样视图、图像视图和渲染目标，要求每个纹素大小相同；驱动只接受覆盖全部层级与切片、类型不变的视图。
- `render37`：`compute_average_luma` 不再失败，`iconservicesagent` 不再中止。控制中心、设置、锁屏与通知中心都画出来，设置的列表与搜索栏可见；主屏与设置列表仍没有图标。点开设置后十多秒才显示。
- 自定义效果：`custom_fn` 来自 IconRendering 的 `[[stitchable]]` 函数（`sdfFill`、`glow`、`glassHighlight` 等）。RenderBox 的 StitchShader 先用 `-newFunctionWithDescriptor:error:` 取带 `specializedName` 的函数，再用 `-newLibraryWithStitchedDescriptor:error:` 生成拼接库，最后放进管线的 `fragmentLinkedFunctions.privateFunctions`。`_MTLLibrary` 把第一步交给 `MTLCompilerService`，后者在本系统上被 SIGKILL，后面两步没有发生；`render37` 的拼接库打印因此为空。`render38` 由驱动直接返回未特化的函数加名字与常量值，并打印三步的描述。
- `render38` 的打印显示，RenderBox 与 QuartzCore 的着色器几乎都经 `-newFunctionWithDescriptor:error:` 取带 `specializedName` 与常量值的变体（`filter_distance_fragment` 特化为 `fpba2ma11bemha4` 等），`_MTLLibrary` 在进程内就能给出这些变体。驱动的代理绕过了这一步，管线按未特化模块的入口名建出后全部被拒绝，开机没有解锁，这一轮提前结束。之后的钩子先走 `_MTLLibrary` 自己的实现，只有它返回 nil 时才用代理。
- IconRendering 的每个 `[[stitchable]]` 函数都有一个 `_v1` 版本，签名与 `custom_fn` 相同：`(float2, half4, constant*, device*, device*, device*, device*)`。不带 `_v1` 的版本参数是展开的标量、纹理结构和 `[5 x float2]` 变换，需要拼接图把参数从缓冲里取出来；RenderBox 自带 `__RB::Lfloat`、`__RB::Llayer`、`__RB::C0`～`C7` 等可拼接的取值函数。StitchShader 用公开的 `MTLFunctionStitchingInputNode`、`MTLFunctionStitchingFunctionNode`、`MTLFunctionStitchingGraph` 建图。
- 链接函数的翻译：`air_link.inc` 把管线给出的链接函数按拼接图的节点顺序内联进调用处。每个节点的模块只读一次、全局变量只规划一次，节点之间直接传纹理、指针和含指针的结构体，NIR 的函数参数传不了这些值。主机上用 `air2nir --link` 可以复现同一翻译。
- `render39`：`custom_fn` 以 `_MTLFunctionInternal` 出现在 `fragmentLinkedFunctions.privateFunctions` 里，特化在进程内完成；整轮没有调用 `-newLibraryWithStitchedDescriptor:error:`，代理也没有用到。自定义效果与 `path_edges` 管线都建成，管线与着色器的拒绝清零。
- `render39` 的主屏仍没有图标。`iconservicesagent` 在 `render37` 与 `render39` 里都以 SIGTRAP 退出 10 次，每次都紧跟在它的一个 commit 跑完之后；每次退出后 `MTLCompilerService` 被 SIGKILL。日志里没有 trap 的位置。
- `render39` 点开设置后，backboardd 连续 24 秒没有 commit，`render37` 的同一段也一样。`render37` 在点击后 16～32 秒之间画出设置；`render39` 只在控制中心手势时做了 19 个 commit，之后到结束没有 commit，截图从控制中心一步起停在黑色的圆角应用窗口。
- `render40`～`render42` 起轮时没有设 `ICON_METAL=1`，`package.py` 因此不把 Metal 注册注入 `iconservicesagent`，它退回软件渲染：主屏图标、Dock 与设置列表的图标都画出来，进程也不再 SIGTRAP。`render31`～`render39` 都设了 `ICON_METAL=1`，`iconservicesagent` 走 GPU，每次 commit 结束后 SIGTRAP。软件渲染下 IconRendering 拒绝序列化图标（`TextureIOError.usingSoftwareRenderer`），设置「通用」页的图标是灰块（见 `package.py` 的说明）。
- 这三轮的 boot-arg 加了 `systrace=1`（`render41` 起配 `systrace_name=nosuchproc`）与 `ustacks=Preferences`。`systrace` 同时打开 `osfmk/arm64/user_exception_trace.c` 的异常打印与 `bsd/dev/arm/systemcalls.c` 的失败系统调用打印，后者要用 `systrace_name` 限制进程，否则合并日志从 3 MB 涨到 20 MB。`ustacks_at` 从内核启动算起。
- `render40` 新出现的拒绝：backboardd 的 `compute_average_luma` 绑定一个只含第 2 级的纹理视图（3 级纹理的 `levels 2+1`），驱动只做整张纹理的视图，派发因 0 号纹理为空失败 11 次。
- 纹理视图改为可以只含一段连续的级别：视图的第 L 级是资源的第 `first_level + L` 级，采样视图、图像视图、渲染目标、读写与拷贝都按这个换算；切片仍然只接受全部。`rwa_texture_generate_mipmaps` 原来把 `util_gen_mipmap` 的源级别传成 1，第 1 级从来没有由第 0 级生成，两级的纹理什么都不生成；现在从视图的第一级开始。
- `render44` 的异常打印：10 次 trap 的 PC 都是 `0x1cdd62208`（slide `0x1a4b4000`，IconRendering `+0x55208`），调用链 CoreUI → TextureIO → IconRendering。trap 前的代码对纹理取 `bufferBytesPerRow` 与 `height`，再对旁边的一个字段调 `swift_unknownObjectWeakLoadStrong`，结果为 nil 时执行 `brk #1`。日志里这段代码之前打印 `synchronously awaiting texture completion`。
- 那个弱引用是纹理底下的 MTLBuffer。驱动的 `-buffer` 恒返回 nil、`-bufferBytesPerRow` 返回 0，纹理也不持有 buffer；Metal 里从 buffer 建的纹理会强引用这个 buffer。另外 `rwa_texture_from_buffer` 的纹理是 buffer 的一份拷贝，GPU 写进纹理的结果从来没有拷回 buffer，而 IconRendering 在等待完成后读的正是 buffer。
- 修法：驱动的纹理持有它的 buffer，并如实返回 `-buffer`、`-bufferOffset`、`-bufferBytesPerRow`；库给 buffer 纹理记一个「已写」标记，绘制的颜色与深度目标、可写图像、纹理拷贝的目标、MSAA 解析目标与处理器写入都会置上；`-waitUntilCompleted` 等到栅栏后调 `rwa_buffer_textures_writeback` 把已写的纹理拷回 buffer，每次 commit 前的刷新对已写的纹理也改为拷回，不再用 buffer 的旧内容覆盖。
- `render45`：`iconservicesagent` 不再 SIGTRAP，pid 64 跑了 105 个 commit、建了 119 条管线。之后 `adreno8: gpu SMMU fault 0x2 at 0:0x2545a000`，叶 PTE 为 0，内核关闭提交并保留页面到冷启动；随后 `fd_bo_new` 返回 NULL，`iconservicesagent`、SpringBoard、backboardd 都在 `fd_bo_mark_for_dump(NULL)` 处 SIGSEGV。
- `render44`、`render45` 起轮时都没有带 `render31`～`render39` 用的 `JOB_ENV`（SpringBoard 与 `iconservicesagent` 的 `REDWOOD_SYNC_DRAWS=1`、PosterBoard 的 `OS_ACTIVITY_DT_MODE=YES`），绘制不逐个等待 GPU。缺页是否与这一差异有关，由 `render46` 补上 `JOB_ENV`、其余与 `render45` 相同来区分。
- `render46` 带上 `JOB_ENV` 后仍然缺页：缺页时在跑的是 `iconservicesagent` 的 `vkba6pa7dhmha4` + `path_distance_fragment`（实例化的路径绘制）和 SpringBoard 的 `vhea3ecaca8fmha4`。FSYNR0 为 `0xe0003`，是一次读访问，叶 PTE 为空。内核把 BO 首尾相接地排在 GPU 地址空间里，越界读一般落进下一个 BO，缺页说明地址落在空洞里：已释放的 BO，或者最后一个 BO 之后。内核 `12377-cmd10` 记录最近 4096 次 BO 预留（地址、大小、pid、预留与释放时间），缺页时打印。
- `render47` 没有出现缺页。GPU 画的图标成块错乱、带横向条纹，像是 GMEM 分块渲染的 tile 没有正确加载或写回。`render48` 只给 `iconservicesagent` 加 `FD_MESA_DEBUG=sysmem`，强制直接在内存里渲染。
- `render48` 的缺页报告：地址 `0x24892000` 不在最近 4096 次预留的任何 BO 里，下方最近的存活 BO 是 SpringBoard（pid 30）8 毫秒前预留的 `0x2486a000+0x28000`，缺页地址正好是它末尾之后的第一个字节，上方没有存活的 BO，GPU 读过了地址空间里最后一个 BO 的末尾。
- `render48` 缺页后提交关闭，三个进程重启。重启后的 `iconservicesagent`（pid 133）打开 GPU 被拒绝（`RedwoodGPU client refused (0xe00002c7)`），之后的图标都是软件渲染。缺页发生在第一张 GPU 画的图标截图之前，这一轮没有 sysmem 下 GPU 图标的读数。
- 内核 `12377-cmd11` 按 KGSL 的做法给每个 BO 后面多预留一页保护页，映射到同一个清零的只读物理页，释放 BO 时一起清掉。GPU 读过末尾时读到零，不再缺页。
- `render49` 整轮没有 SMMU 缺页，SpringBoard、backboardd、`iconservicesagent` 各只有一个 pid。`render45`、`render46`、`render48` 都缺页，`render47` 没有，保护页的效果还要看后面几轮。
- `render49` 的 `iconservicesagent` 打开了 GPU，也设了 `FD_MESA_DEBUG=sysmem`，图标仍然错乱：圆角底板的形状和深色底色是对的，图形所在的下半部分是成段的绿、品红和白色横条。sysmem 与 GMEM 的结果相同，错乱与 GMEM 分块无关。
- 下一步直接看中间结果。驱动加了 `REDWOOD_THUMBS=N`（配合 `REDWOOD_SYNC_DRAWS`）：从 `REDWOOD_THUMB_FROM` 号 commit 起，每次绘制完成后把每个颜色附件和每个片段纹理采成 32×32，打印进日志，共 N 张；`tools/k90auto/thumbs.py` 把它们还原成图，一行一次绘制，左边输入、右边输出。
- `render50`～`render52` 的采样说明 GPU 这一侧大体正确：路径覆盖率逐笔累积成正确的形状，输入图层也对；图标在 GPU 之外出错。
- 根因在驱动的 `-newBufferWithBytesNoCopy:`：它在创建时把调用方的内存复制一次，之后 GPU 写进 buffer 上纹理的结果只回到驱动的副本，调用方读的是自己那块内存。日志里 `iconservicesagent` 建了 147456 字节（192×192×4）、161408、34176 字节等 no-copy buffer，图标里成块的绿、品红、白色是这些内存原来的内容。
- 修法：库给 no-copy buffer 记下调用方内存（`rwa_buffer_set_mirror`）。buffer 上的纹理从这块内存取数据，结果同时写回驱动的副本和调用方内存。写进 `-contents` 的数据仍然到不了调用方，这一点没有变。`render53` 只换这一处，其余同 `render49`。
- `render53` 里 backboardd 在库的刷新路径上读到已释放的调用方内存（EXC_BAD_ACCESS，地址 `0x107d00040`）：buffer 还活着，调用方已经释放了自己那块内存。改为只写不读，只在 GPU 刚写完的纹理拷回时写进调用方内存，`render54` 验证。
- `render54` 之后图标有了正确的底色，图形本身仍缺失。`render55` 的采样显示 IOSurface 上的花瓣等图层正确，`plane_image_stretch` 把它们贴进 192×192 的 buffer 纹理后只剩横条或透明。`render56` 只采这类绘制，变换矩阵与纹理坐标都对（commit 18 的第 2 次绘制把整张纹理贴到 12～134 像素）。没画出东西的绘制分两种：输入是 89×89 的 buffer 纹理时，输入本身就全透明；commit 18 的输入正确，绘制后 0 号与 2 号附件仍全透明。
- `plane_image_stretch_fragment` 等 22 个 RenderBox 片段着色器在未特化的位码里，颜色输出的附件号是 function constant 的表达式（`air.render_target` 后面跟一个全局变量）。设备用的是 `_MTLLibrary` 特化后的位码；在 macOS 上用 `-newFunctionWithName:constantValues:error:` 特化同一函数，`bitcodeData` 里附件号已是常数（`i32 2`），构造函数也被删掉。`render57` 加的翻译期求值没有触发，已撤回；`render56` 里「Fr」写进 2 号附件是正确结果。
- 库在每批工作前用 `vm_read_overwrite` 读取 no-copy buffer 的调用方内存，哈希变化时拷进驱动的副本。读到未映射的页时放弃这一次，不会再出现 `render53` 的崩溃；调用方经 `-contents` 写的数据在调用方内存不变时保留。`render58` 里 backboardd 大小的 buffer 有 31 次变化，`iconservicesagent` 的没有，图标没有变化。
- `render56` 的回写打印说明，`iconservicesagent` 里全透明的 89×89 与 194×194 `RGB10A2Unorm` 纹理是 GPU 渲染目标，回写时 34176、161408 字节里非零的只有 0～253 个；同一批的 `R8Unorm` 目标有内容。commit 17 最后一段画进 194×194 `RGB10A2Unorm` 的管线是 `alpha_effect`（`fec2a2kdadba6kfmha4`）与 `fhe2ae2a2ca7kfmha4`、`fhe2afea2ca7kfmha4`，它们都读帧缓冲。`render59` 采这三条管线每次绘制前后的附件，并把设备上特化出的位码打进日志（`REDWOOD_DUMP_AIR`，`tools/k90auto/airdump.py` 还原）。
- `render59` 的采样：`kfmha4` 管线的 0 号输入是 384×128、224×128 的 `RGBA16Float` 中间纹理，绘制前就全透明，输出因此为空，问题在更早画这些中间纹理的绘制。驱动的 IOSurface 检查改为只拒绝比描述符小的 surface（`redwooddrawable.m`），这一轮的两次拒绝都消失。
- 位码打印改为只打印名字含 `REDWOOD_DUMP_AIR` 所给文字的函数，最多 16 个，每行间隔 2 毫秒。`render57`～`render59` 是一批，下一批改为按 commit 采样，先找出画坏中间纹理的那次绘制。
- 设备上 `_MTLLibrary` 特化出的模块带 `air.linked_constants_signature`，`render60` 的 `vhe2ae2a2ca7kfmha4` 是 `primitive_image_vertex` 加常量 `(4457543, 2, 31834, 12)`。在 macOS 上用同一组常量调 `-newFunctionWithName:constantValues:error:`，`bitcodeData` 的函数体与设备的相同。特化名把前三个常量字按 16 进制半字节从低到高编码，`a`～`p` 表示 0～15，后跟的数字是重复次数；`render38` 的打印给出特化名与原函数名的对应。
- commit 2 的图标分四段：96×64 或 64×64 层先用 `path_exterior` 把路径的有向覆盖率累加进 1 号附件的 G，覆盖率填充（标签 `accumulator_coverage`，`plane_color` 的 `fbfa6dba6dhmha4` 特化）之后 R 的范围与填充前 G 的范围相同，`primitive_color` 再读帧缓冲的 R 上色；128×128 层由 `custom_effect` 调 IconRendering 拼接的 `custom_fn`；然后是一串 `filter_distance` 与 `filter_blur`；最后 `primitive_image` 把结果贴进 89×89 的 `RGB10A2Unorm` 图标。
- 每次绘制都打印同步日志时，`iconservicesagent` 一轮写 35838 行、约 10 MB，超过日志环（约 1.3 MB）在两次拉取之间能装下的量，`render59`、`render62` 都丢了开头的读数。同步日志改为只在 `REDWOOD_SYNC_LOG` 或 `REDWOOD_THUMBS` 采样的 commit 里打印，其余只在绘制没有完成时打印。
- 采样把每个通道截到 [0, 1]，逆向绕行的路径在 1 号附件里是负值，采出来是 0。`render64` 把 commit 7 起的路径都读成「没画」，`render65` 打印完整的顶点缓冲后，按 `vjba6la7dhmha4` 与 `path_exterior_fragment` 的特化 IR 在 CPU 上重算（会话内的临时脚本），commit 8 第 1 次路径的覆盖率是 −1。库的采样改为：两通道浮点纹理的 R、G 取绝对值，B 记符号（负 R 为 128，负 G 为 64）。
- 新增的探针：`REDWOOD_THUMB_WORDS=N` 打印每个 buffer 的前 N 个字，每行 24 个、各带偏移；`REDWOOD_THUMB_WHOLE=1` 把 `REDWOOD_THUMB_MATCH` 从单次绘制放宽到含匹配绘制的整个 commit；同步日志打印清除颜色与清除深度；采样与 buffer 的每行打印后等 1 毫秒，`render66` 起合并日志没有缺口。深度附件的采样（槽位 8）在 `render68` 没有输出，原因未查。
- 没画出东西的绘制与常量 buffer 偏移的对应：`render64`～`render68` 里偏移为 736、1216、2352 的路径与填充都画出了，偏移为 584、636、776、788、1268、1720、2984、4248 的都没有写任何像素，前一组都是 16 的倍数，后一组都不是。`render68` 的 commit 1 排除了深度测试：深度清成 0，填充的深度也是 0，比较函数 `GreaterEqual`，填充仍没有写。
- 库把 Metal 的偏移原样交给 freedreno（`air_metal.c` 的 `bind_stage`），freedreno 报的常量 buffer 对齐是 64 字节，A830 按未对齐的地址读 UBO 时取到的数据错位。`render69` 起，偏移不是 64 的倍数时库按 `air.buffer_size` 拷贝这一块，交给 freedreno 上传到对齐的位置。这正是开源版本里的做法，当时为省每次绑定 221 us 的拷贝改成了原样传偏移。之后改为只在偏移不是 16 的倍数时拷贝，上面偏移为 736、2352 的绘制说明 16 的倍数够用。拷贝读的是处理器侧映射，同一次提交里先由 GPU 写的常量块会读到写之前的内容。
- `render69` 的覆盖率填充写出了 R，主屏图标的形状和颜色都出现了（FaceTime、Calendar、Photos、Clock、App Store、Maps 等）。剩下三处问题：News、Health、Games、Wallet、Settings 的图形是带间隙的横条；多数图标上有一条从左上到右下的细线，图标方框四角外有零散暗点；Weather 与 Calendar 小组件是白块。
- `render70` 把拷贝门槛降到 16 之后图标不变，两个小组件也有了内容。剩下的问题是图形里的横条和对角细线。
- 对角细线出在用 `fwidth` 做边缘抗锯齿的绘制：`render70` 的 commit 13 里，`primitive_custom`（`fi2a2ea3dna6dhmha4`）写出的 1 号附件沿四边形对角线有一条低值线，它读的纹理没有这条线。翻译路径不跑 `nir_shader_gather_info`，`needs_coarse_quad_helper_invocations` 与 `needs_full_quad_helper_invocations` 一直是 false，ir3 因此不打开 A830 的 `PIXLODENABLE`、`LODPIXMASK`，三角形边上的导数读到没有运行的辅助线程。翻译结束时按 `nir_gather_info.c` 的规则补上这两项（`air_intrinsics.c` 的 `air_gather_quad_helpers`），`render71` 的细线消失。
- `render72` 的采样里 Health（白底粉心）、News（白底红色 N）都正确，主屏上同一图标却是紫色横条。SpringBoard 也建了同一批 RenderBox 管线（`custom_effect`、`filter_distance`、`kfmha4` 等），它没有设 `FD_MESA_DEBUG=sysmem`，走 GMEM 分块；`render73` 只给 SpringBoard 加 sysmem。
- `render71` 主屏的图标上除了横条，还有标签文字的碎片（「Games」「Settings」的片段等）和黑色方块。`render72` 的日志里，两个进程都查询了 RGB10A2 的两种对齐：驱动对线性纹理答 64，对纹理 buffer 答 16；`iconservicesagent` 的 194×194 buffer 纹理按 832 字节一行写回，是 64 对齐。
- `render77` 让纹理 buffer 的对齐查询返回线性纹理的值（`redwoodmetal.m` 的 `minimumTextureBufferAlignmentForPixelFormat:`），文字碎片和黑块都消失，Settings、Wallet、Notes、Reminders、Clock、App Store、Maps 画对。这一轮 SpringBoard 建的 194×194 buffer 纹理都是 832 字节一行；此前的轮次没有记录行字节数，按 16 对齐读的推断没有直接读数。
- `render77` 之后 FaceTime 相机图形的轮廓位置正确，填充里有一组间距约 13 像素、略向右上倾斜的细缝，镜头部分的条纹越过了轮廓；Photos 的花瓣上也有同样的斜线。轮廓本身没有错切，这些细缝出在图形的绘制过程里。
- `render78` 采到 SpringBoard commit 2（一把钥匙）的整条滤镜链，管线名按日志顺序对应如下。
  - w7 `fpba2ia11bemha4`：由轮廓求初始距离。
  - w8～w11 `fpba2ma11bemha4`：4 次 9 点的距离传播。
  - w12 `fpba3ba10bemha4`、w13 `fpba2iba10bemha4`：各一次。
  - w14～w17 `foba3bia9bemha4`：4 次 8 点模糊。
  - w18 `fpba2eca10dhmha4` 输出法线样的光照纹理，w19 把它写进 122×122 的 `RGB10A2Unorm` buffer 纹理。
- 按 Metal 的语义逐次核对，这条滤镜链没有找到错误。
  - 距离传播结果里的横竖色带来自采样的显示方式：分量超过 1 时截到 1。竖直边左侧的最近点都在水平方向，G 为 0，显示为整块红色。
  - 模糊管线的 writeMask 是 0x8，即 Metal 的 Red，只写 R；G 保留上一次的内容，所以相邻两次的输出交替相似。
- 剩下的斜向条纹出在 IOSurface 的行距上。`render84` 的导入记录里，SpringBoard 的图形 IOSurface 由客户端指定 32 字节对齐的行字节数（50×83 为 224，101×94 为 416，146×117 为 608），A830 采样这些线性纹理时按 64 字节的整数倍取行距，每行多走 32 字节，图形成了一组斜向色带。行字节数是 64 倍数的图形（124×105 的 512、110×110 的 448）画对。
- freedreno 的 `fd6_layout.c` 对线性布局的行距同样至少按 64 字节对齐，8 字节和 16 字节像素分别按 128、256，与 `render84` 的读数一致。
- 在内核里补齐行距不可行。`render88` 里 MiniIOSurface 已把这些 surface 的行距报成 256、448，处理器按这个行距读到的图形同样错切，说明 SpringBoard 写图形时用的是它创建 surface 时要求的 224、416，不读 surface 报回的行距。内核 `12377-cmd15` 撤回了补齐。
- 修法改在驱动：`-newTextureWithDescriptor:iosurface:plane:` 遇到单平面、二维、行距不是 64 倍数的 surface，用一个覆盖 surface 内存的 no-copy buffer 和其上的 buffer 纹理代替原地导入。每次提交前按 surface 自己的行距把内容拷进纹理，GPU 写过的内容写回 surface（`redwoodmetal_texture.inc` 的 `rw_surface_through_copy`）。驱动在原地导入行距不是 64 倍数的 IOSurface 时仍打印 GPU 实际读取的行距，每个进程最多 16 行。
- `render82` 拖慢 SpringBoard 后图标上的「Passcode」等文字碎片，可能出自同一处：50×83 的图形按 256 字节一行读，比 224 字节一行多读约 2.6 KB，读到相邻内存里 Settings 列表的文字。
- `render89` 采样确认拷贝路径：50×83、101×94 的输入与画出的图形都干净，SpringBoard 有 16 个、backboardd 有 4 个 surface 走拷贝（行距 32～608 字节不等）。`render90` 不采样，主屏的 FaceTime、Mail、News、Games、Health、Wallet、Safari、Music 与 Control Center 的飞行模式图标都画对。剩下 Mail 与 Maps 上的黑色弧形，`render77`、`render82` 的截图里没有，随拷贝路径一起出现。
- 黑色弧形出自中间目标里残留的内容。`render91` 让同一 surface 的请求共用一个拷贝纹理后，弧形换到别的图标上，同一轮内位置不变，说明它画进了图标图像。`render92` 采到 SpringBoard 的 96×128 中间目标在第一次绘制前已有前一个图标的阴影，位置在 scissor 以外；RenderBox 的距离与模糊滤镜会读到所画区域以外的像素。freedreno 新建资源时从已释放的 buffer 缓存里取内存，不清零。AIR 库改为新建颜色与深度目标时先清零（`air_metal_resource_private.h` 的 `texture_start_zeroed`），`render93` 的主屏图标没有弧形和边缘黑点。只有一轮读数，弧形原本就随机出现，需要再跑几轮确认。

## 9. 无人值守的一轮

- 命令通道：loader v10 的 `oem sh`、内核 `kern.redwood.cmd`、iOS 上的 `rwsh`、主机上的 `tools/k90auto/rsh.py`，`render1` 里 `ps` 与 `dump 38` 都有回应。
- `tools/k90auto/tour.py` 经命令通道点按、滑动并截图，同一步的两张截图在状态栏以下比较差异，所有截图拼成一张编号的图。
- `tools/k90auto/cycle.py` 串起打包、payload、上传、等开机解锁、固定巡检、提前结束和渲染报告，每两轮在 LK 重置 A 槽重试次数，loader 状态不对就停止。

