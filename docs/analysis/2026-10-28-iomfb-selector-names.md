# IOMobileFramebuffer 的 selector 名字：12 个未命名号的定名与 iOS 26.6 完整表

本篇落档一次只读调研的结果。调研目标是给 `MiniIOMobileFramebuffer.cpp:49-70` 那个 enum 里 20 个名字之外的 12 个未命名 selector 定名，并核实已命名的 72、73、74 三个。结果是 12 个全部拿到形状，其中 11 个有 Apple 的 `kern_*` 符号名且各有两个以上独立公开来源，第 12 个（88）只有调用点与形状。72、73、74 与项目 enum 的名字一致，74 的实现有一处具体缺陷。

调研除了公开检索，还在项目自带的 iOS 26.6 共享缓存上独立做了一遍反汇编（`hackios-xnu-kernel/ios26/23G90__iPhone18,3/dyld_shared_cache_arm64e*`，`IOMobileFramebuffer` 镜像基址 `0x229493000`），把导出 wrapper、对象分派槽、`kern_*` 实现、`IOConnectCall*` 的 selector 立即数整条链打通，得到 26.6 这个 build 上的完整表。项目 enum 现有的 20 个名字在本地全部对得上。

调研全程只读，脚本与抓取内容都写在系统临时目录，工作区未被改动。本篇由 lead 直接从调研回报落档，因为脚本在临时目录里会随会话结束丢失，而报告内容此前不在任何文件里。驱动侧的判断（第 5 节两处缺陷与第 3 节的实现建议）由 display 在 task-24 里核实后再改代码。

## 1. 主表

「独立来源」的计数口径是不同项目或不同作者，同一仓库的多个文件算一个。本地列是在 iOS 26.6 共享缓存上反汇编确认的结果。

| sel | 名字（Apple 符号） | 公开来源 | 独立来源数 | 本地 26.6 复核 |
|---|---|---|---|---|
| 15 | `kern_SetDebugFlags` | S1 S2 S6 | 3 | slot `0xa80`，2 scalar in / 1 scalar out |
| 17 | `kern_SetGammaTable` | S1 S2 S6 | 3 | slot `0xa90`，struct in `0xC0C` = 3084 |
| 18 | `IOMobileFramebufferIsMainDisplay` | S1 S2 S6 S8 | 4 | 导出函数内直接调用，1 scalar out |
| 22 | `kern_SetDisplayDevice` | S1 S2 S6 | 3 | slot `0xaa8`，1 scalar in |
| 27 | `kern_GetGammaTable` | S1 S2 S6 | 3 | slot `0xaa0`，struct out `0xC0C` = 3084 |
| 33 | `kern_EnableDisableVideoPowerSavings` | S1 S2 | 2 | slot `0xb38`，1 scalar in |
| 50 | `kern_SetBrightnessCorrection` | S1 S2 | 2 | slot `0xa70`，2 scalar in，第二个是 display type，取自 `fb+0x888` |
| 68 | `kern_SetParameter` | S1 S2 | 2 | slot `0xb98`，1 scalar in 加 `8 * count` struct in |
| 78 | `kern_SetBlock`，内核 `IOMobileFramebufferUserClient::s_set_block` | S1 S2 S3 S5 | 4 | slot `0xb88`，scalar in = extra+2，struct in 按 4096 分块 |
| 84 | `kern_SetContrast` | S1 S2 S8 | 3 | slot `0xa98`，struct in 4 字节即 float |
| 86 | `IOMFBGainEncoderFinishEncoding` | S1 S2 S5 | 3 | 导出函数内直接调用，struct in `0x48` = 72 / 1 scalar out |
| 88 | 查不到 Apple 符号名 | S1 给调用点，S8 给自拟名 | 0 个命名来源 | `IOMobileFramebufferOpenByName` 内联，1 scalar in |

88 的细节：调用点在 `IOMobileFramebufferOpenByName` 内部，本地函数地址 `0x2294bd5a4`、call site `0x2294bdaec`，形式是 `IOConnectCallScalarMethod(conn, 0x58, &displayType, 1, 0, 0)`，只在 open 成功且 `s_thread_notified == 1` 时发一次，传的是刚打开那个 display 的 display type。同一个 u32 也存在 `fb+0x888`，就是 selector 50 用的第二个 scalar。S8 把它叫 `SelectDisplay`，那是作者自拟标签：iOS 26.5 SDK 的 190 个导出里没有任何 `Select*` 符号，ipsw-diffs 的 framework 符号增删记录里也从未出现 `Select*`。

内核侧有一条推断线索。`Allenwdk/UniXNU-uke` 的 `docs/PROGRESS.md` 记录真机日志出现 `IOMobileFramebufferUserClient::s_map_display_type ... UserClient display type is 0`，行为是把 userland 传入的 scalar 写进 user client 的 `+0x10c` 再返回 0，时机在 client 打开之后、selector 8／15／8 之前。语义与形状都对得上 88，而没有任何公开来源把 `s_map_display_type` 和数字 88 写在一起。这一层只能当推断，写进代码注释时要标注。

## 2. 来源清单与派生关系

- S1 `EthanArbuckle/iPhone17-1_18.2_22C152_Restore` 的 `System/Library/PrivateFrameworks/IOMobileFramebuffer.framework/IOMobileFramebuffer.m`，237 KB，是 iOS 18.2 / iPhone17,1 / 22C152 的反编译全文。`kern_*` 函数里 selector 是字面常量，`IOMobileFramebufferOpen` 里能看到函数指针表填充（形如 `*(void *)(*a4 + 2712) = kern_SetBlock;`）。15、17、22、27、33、50、68、72、73、74、78、84、86、88 的常量已逐个函数核对。
- S2 `dipa-studio/ios-sweet` 的 `NOTES.md`，来自 iPhone X / iOS 16.7.16 / 20H392 的共享缓存，用 `ipsw dyld disass --image IOMobileFramebuffer` 取的。有一行完整的 `3 _kern_GetLayerDefaultSurface[ScalarMethod_stub]; 4 _kern_SwapBegin[...] ... 86 _IOMFBGainEncoderFinishEncoding[Method_stub]; UNKNOWN {}`，表在 86 处终止。另有通知 ABI 段落写明 `sel 72 scalars [NotifyCallbackFuncs[type], fb, type, 0]` 与 type 的取值（0 HotPlug、1 Power、3 FrameInfo、4 CRC、5 Vsync）。
- S3 Google Project Zero，Ian Beer，《The curious tale of a fake Carrier.app》（CVE-2021-30983）。原文是「The exploit only calls 3 different external method selectors on the AppleCLCD2 user client: 68, 78 and 79. The one with the largest and most interesting-looking input is 78, which corresponds to ... `IOReturn IOMobileFramebufferUserClient::s_set_block(...)`」。这是 78 的内核符号名唯一直接来源。
- S4 `jsherman212` 的 CVE-2021-30656 文章，L153 到 L156 写「Here is the structure that represents IOMobileFramebufferUserClient's external method 74」并给出 `IOExternalMethodDispatch <s_supported_frame_info, 1, 0, 1, 0x40>`。同文 L143 与 L146 给出 external method 0 = `s_rotate_surface`（3 scalar in），L174 给出 `s_swap_submit` 行 `<0, 0xFFFFFFFF, 0, 0>`。这是 iOS 14 时代的表，74 当时是 1 个 scalar out。
- S5 `ma6x9x/Lum1na` 的 `LabIntelOffsets.m` L235 与 L245，直接读 kernelcache 的 `sMethods`。iOS 26.5（23F77/T8101）的表在 `0xFFFFFFF007EF0C90`，stride `0x18`，记为「88 rows sel0..0x57」，rows 59-64 与 70-71 是 fn=0 的退役行，row5 的 sin 是 `0x588`，row68 的 sin 是 `0x100`，special sels `0x44`／`0x4e`／`0x4f`／`0x55` 即 68／78／79／85 会先把整行拷到栈上。
  - iOS 27.0（24A435/T8150）的表在 `0xFFFFFE000832FD70`，stride `0x28`，记为「93 rows sel0..0x5c」，新增 `+0x20` 的 entitlement 列：row23 是 `com.apple.private.iomfb.set-block`、row83 是 `com.apple.private.allow-explicit-graphics-priority`、row86 是 `com.apple.private.gain-map-access`；
  - row5 的 sin 从 `0x588` 变成 `0x6e0`，row68 的 sin 从 `0x100` 变成 `0xffffffff`，rows78 与 79 的 ci 与 sin 从 0 变成 `0xffffffff` 即变长。这一份只有行号、大小与 entitlement，没有符号名。
- S6 `samhenrigold/qemu-ios` 的 `docs/research/gap-display-stack-kernel.md` L81，是古董 iOS（iPod touch 2G 与 iPhone 3GS 时代）的表：`0xf SetDebugFlags`、`0x11 SetGammaTable(struct)`、`0x12 IsMainDisplay`、`0x16 SetDisplayDevice`、`0x1b GetGammaTable (0xc00 out)`、`0x20 VideoPowerSavings`，另外 `1 SwapSurface`、`2 WaitSurface`、`9 VSync notify on/off`、`0x15 HotPlug notify` 都是旧真方法后来退役，这解释了 S5 那些 fn=0 的空洞行。
- S8 `orhunnx/beyond2lte-ios` 的 `xnu-overlay/iokit/Kernel/arm/B2LFramebuffer.cpp`，自称对 iOS 26.6.2 共享缓存做过逆向并给了地址。独立作者，不是从 ios-sweet 派生。

派生关系不计入独立来源：`lechaukha12/xnu-xzs` 的 `XZSFramebuffer.cpp` 用 `kSweetFB*` 前缀（34 处），selector 列表来自 ios-sweet；`Allenwdk/UniXNU-uke` 与 `GFander/UniXNU-kebab` 在文档里明文署名 ios-sweet；`Floppikrob/ios-galaxy-s8`、`turgayasuk-sketch/ios-topaz`、`edi194/ios-fajita`、`nftuoa/ios-sweet-sagit` 逐字复制同一份 NOTES.md；本项目 `hackios-xnu-kernel` 及其全部 fork 共享同一份 20 名字 enum，算一个来源。

未复核的四条来自并行检索，调研没有重新抓取原文，引用时要带这个限定：`WebKit/WebKit` 的沙盒 profile `Source/WebKit/GPUProcess/mac/com.apple.WebKit.GPUProcess.sb.in` 给 macOS GPU process 授权 `(iokit-method-number 82 88)`，这一条只证明 88 在 macOS 上存在，不给名字；`Snapintosh/tools/replay-panel-mode.py` 点名 macOS 27 的 `s_set_digital_out_mode` 是 native selector 23；`blacktop/symbolicator` 与 ipsw-diffs 的内核 `s_*` 与 framework `_kern_*` 符号词表；`Lakr233/vphone-cli` 独立确认 `_kern_SwapEnd` 是 external method 5。

## 3. 本地反汇编方法

脚本写在系统临时目录，会随会话结束丢失，所以方法记全。

- 共享缓存解析：dyld4 拆分缓存，mmap 全部 subcache，主缓存头 magic 是 `dyld_v1`，`mappingOffset` 与 `mappingCount` 在 `0x10`，images 数组在 `0x1c0`，每条 32 字节，形式是 `(address, _, _, pathOffset, _)`。
- 镜像内定位：section 表、`__LINKEDIT` 的 bias 按 `vmaddr - fileoff` 算、FUNCTION_STARTS 取函数列表、LC_DYLD_EXPORTS_TRIE（`0x80000033`）遍历导出表，再用 capstone 逐函数分析。这个镜像有 779 个函数、202 个导出。
- stub island 解析是这次的关键一步。这个镜像不通过 `__auth_stubs` 调 IOKit，`bl` 的目标是 dyld 的 stub island，16 字节，形式是 `adrp x16,#page; add x16,x16,#off; br x16; brk #1`。解出 island 到目标地址再到目标镜像的导出名之后，三个入口是 `0x22c859ac0` 的 `_IOConnectCallMethod`、`0x22c859ad0` 的 `_IOConnectCallScalarMethod`、`0x22c859ae0` 的 `_IOConnectCallStructMethod`。
- 把导出 wrapper 与 selector 连起来：wrapper 里 `ldr xN, [x0, #slot]` 加 `braaz xN` 取 slot，slot 的值来自 `_IOMobileFramebufferOpen`（`0x2294979e0`）与 `_IOMobileFramebufferOpenByName`（`0x2294bd5a4`）里的 `adrp`／`add`／`paciza`／`str x16,[x0,#slot`。有一批是先写栈数组再用 `str xN,[x0,xM]` 寄存器偏移批量装入，需要跟着 `mov wN,#0xa00` 这类立即数还原。

两个坑：`__auth_stubs` 的 GOT 槽是 chained fixup 编码，原始值形如 `0x80140000XXXXXXXX`，目标地址是 `0x180000000 + (raw & 0xFFFFFFFFF)`；按「任何 stub 调用点的小 w1 立即数」筛 selector 会大量误报，因为 memcpy 与 printf 的长度参数也是小立即数，必须先确认调用目标是 `IOConnectCall*` 才计数。

形状只作二次校验，不作命名依据。所有名字都来自符号（S1 与 S2 的 `kern_*`、S3 与 S4 的内核 `s_*`），形状吻合只用来确认版本没变，因为 selector 编号跨版本会变。

## 4. iOS 26.6 完整 selector 表

按 selector 排序，名字取本地导出符号，形状取反汇编里的常量。这一份可以直接当 26.6 的实现基线。

```
 3 GetLayerDefaultSurface      4 SwapBegin                5 SwapEnd(struct 0x588)
 6 SwapWait                    7 GetID                    8 GetDisplaySize
10 SetTVOutMode               11 SetWSSInfo              12 RequestPowerChange
13 EnableStatistics           14 SetFlags                 15 SetDebugFlags(2 in/1 out)
16 SetTVOutSignalType         17 SetGammaTable(0xC0C in) 18 IsMainDisplay
19 SetWhiteOnBlackMode        20 SwapSignal              22 SetDisplayDevice(1 in)
23 SetDigitalOutMode          24 GetHDCPDownstreamState  25 GetDigitalOutState
27 GetGammaTable(0xC0C out)   28 GetDotPitch             29 GetDisplayArea
30 EnableDisableDithering     31 SetUnderrunColor        33 EnableDisableVideoPowerSavings(1 in)
34 SetVideoDACGain            35 SetLine21Data           41 EnableMirroring
42 GetMirroringCapability     43 SetRenderingAngle       44 SetMirrorContentRegion
47 HDCPSendRequest            48 HDCPGetReply            49 SurfaceIsReplaceable
50 SetBrightnessCorrection(2 in) 51 SetColorRemapMode    52 SwapCancel
53 SetCanvasSize              54 GetMatrix               55 SetMatrix
57 GetColorRemapMode          66 SPLCSetBrightness       67 SPLCGetBrightness
68 SetParameter(1 in + 8*n struct) 69 SwapSetColorMatrix 72 Enable/DisableNotifications(4 in)
73 ChangeFrameInfo([3,index]) 74 SupportedFrameInfo(1 in/2 out/64 struct) 75 FactoryPortal
77 GetCurrentAbsoluteTime     78 SetBlock                79 GetBlock
80 GetLinkQuality             81 SwapCancelAll           82 GetProtectionOptions
83 CopyLayerDisplayedSurface  84 SetContrast(float 4B)   85 GetBufBlock
86 GainEncoderFinishEncoding(72 in/1 out) 87 AnnounceNextSwapTimestamp
88 (OpenByName 内联, display type) 89 SetClamshellState 90 GetDotPitchFloat
91 SwapGetCurrent             92 SwapCancelAllGetCurrent
```

交叉验证：项目 enum 现有的 20 个名字（3、4、5、6、7、8、12、20、25、28、29、52、57、72、73、74、77、79、81、82）在本地 26.6 上全部对得上，一个不差。83 的 `CopyLayerDisplayedSurface` 与 iOS 14 那篇 exploit 文章里的 `s_displayed_fb_surface` 是同一个操作。

两个不要混的地方：`kern_DisplayWall{Enumerate,ValidateConfig,Enable,Disable,Status}` 内部的 3、4、5、6、7 属于 AppleDisplayManager 这个另外的 user client，本地 `_AppleDisplayManagerOpen` 在 `0x2294b79e4`；`IOMobileFramebufferCalibrationToolboxCommand` 里的 2、3、4、5 走 AppleNVMeEAN 连接，本地有字符串 `AppleNVMeEAN` 与 `UserCalibration_EraseEAN`。两者都与 IOMFB 的 selector 无关。

## 5. 72、73、74 与项目 enum 的对照

enum 在 `MiniIOMobileFramebuffer.cpp:49-70`，case 实现在同文件 `:1328-1372`。三个名字都对，语义注释有两处要改。

72 `kFBMethodNotifications` 名字对，而 26.6 上是两个实现，enable 与 disable 分开。本地 enable 在 `0x2294bb218`、装在 slot `0xa28`，disable 在 `0x2294bb2a0`、装在 slot `0xa30`，都是 `IOConnectCallScalarMethod(conn, 0x48, scalars, 4, 0, 0)`。

- enable 的 4 个 scalar 是 `[NotifyCallbackFuncs[type], fb, type, 0]`，回调函数指针从 `__AUTH_CONST,__const + 0xe20` 的表里按 type 取；disable 是 `[0, 0, type, 0]`，即 4 个 scalar 先清零再把 type 写到 index 2。
- 公开名字是 `kern_EnableNotifications` 与 `kern_DisableNotifications`（S1、S2），导出 wrapper 是 `IOMobileFramebuffer{Enable,Disable}{VSync,Power,HotPlugDetect,NeedSwap,CRC}Notifications`，五个 Enable 共用 slot `0xa28`，五个 Disable 共用 slot `0xa30`。
- 项目实现读 `in[0]` 当 callback、`in[2]` 当 type，与 26.6 一致，不用改。日志里 72 从未出现，说明 backboardd 还没注册通知，而正常路径会注册 Vsync 即 type 5。


73 `kFBMethodChangeFrameInfo` 名字对。本地实现在 `0x2294bb314`、装在 slot `0xba8`，形式是 `IOConnectCallScalarMethod(conn, 0x49, scalars, 2, 0, 0)`，scalars 是 `[3, index]`，3 是 framework 硬编码常量。导出 wrapper `IOMobileFramebufferChangeFrameInfo(fb, bool)` 的流程是先查 74 拿描述符，再把选中的 index 存到 `fb+0x828`，然后调 73。所以 74 返回 count 0 时 73 不会被调用，与日志一致。项目现在直接 `return kIOReturnSuccess`（`:1333`），够用。

74 `kFBMethodSupportedFrameInfo` 名字对，内核符号是 `IOMobileFramebufferUserClient::s_supported_frame_info`，S4 明文点名并贴了 iOS 14 的表行。本地实现在 `0x2294bb384`、装在 slot `0xbb0`，形式是 `IOConnectCallMethod(conn, 0x4a, &type, 1, NULL, 0, output, &outputCnt, outputStruct, &structSize)`，其中 `outputCnt` 初始化成 2、`structSize` 初始化成 64，返回后 framework 直接 `*a3 = output[0]`、`*a5 = output[1]`，不检查实际写回了几个。

项目实现（`:1350-1358`）只写 `out[0] = 0` 并把 `args->scalarOutputCount` 设成 1，还 bzero 了那个 struct。26.6 的 framework 请求 2 个 scalar，所以第二个槽位保持它自己栈上的初值 `0xAAAAAAAAAAAAAAAA`，调用方拿到 `0xAAAAAAAA` 当 selected index。

- count 是 0 的情况下正常路径不会去用这个 index，所以目前没出问题，而把两个 scalar 都写 0 更稳。enum 的注释 `/* in: type; out: how many, and their tags: none */` 里「their tags」在公开资料里找不到对应物，26.6 的实际输出是 2 个 scalar（count 与 selected index）加 64 字节 struct，注释可以按这个改。
- S5 给的 iOS 14 表行是 `<1, 0, 1, 0x40>`，即 14 上是 1 scalar in、1 scalar out、`0x40` struct out，18.2 起变成 2 scalar out，所以跨版本别写死。


这一处与 task-20 直接相关：74 返回 count 0 正是「CA 可能被封顶而与 `fb_hz` 无关」那一层的机制，两处要互引。

## 6. 78 的分块协议与三次实际调用

框架侧的分块协议有公开定义，payload 内容没有。

S1 给出的 `kern_SetBlock(a1=fb, a2=blockType, a3=data, a4=dataSize, a5=extraU32Array, a6=extraCount)` 算法是：scalar 数组长度等于 `a6 + 2`，全部先填 `0xAA`；`scalars[0] = blockType`；

- `scalars[1] = 0` 作分块偏移 cookie；`scalars[2 .. a6+1]` 是 a5 指向的 a6 个 u32，每个零扩展成 u64；然后循环 `IOConnectCallMethod(conn, 0x4E, scalars, a6+2, data + offset, min(4096, dataSize - offset), 0,0,0,0)`，返回后 `scalars[1] += 4096`，直到 `offset >= dataSize` 或返回非 0；
- 没有任何输出参数。本地 26.6 的 `0x2294bcc3c` 已逐条对过，算法一致（`mov w1,#0x4e`，`mov x3,x21` 取 extra+2，`csel x5, x10, x24, hi` 取 min(剩余, 0x1000)，回写是 `ldr x8,[x22,#8]; add x8,x8,#0x1000; str x8,[x22,#8]`）。
- S5 说 27.0 上 rows78 与 79 的 `checkScalarInputCount` 与 `checkStructureInputSize` 都是 `0xffffffff` 即变长，与分块协议一致。


导出 wrapper `IOMobileFramebufferSetBlock` 是纯转发（`ldr x6,[x0,#0xb88]; braaz x6`），所以公开签名就是上面那 6 个参数。同一个 slot `0xb88` 还被 `IOMobileFramebufferSwapSetToneMapConfig` 用，它自己固定传 `blockType = 0x6b`、`dataSize = 0x4c` 即 76 字节、`extraCount = 1`。

日志里 SwapBegin(4) 与 SwapEnd(5) 之间有三次 78 调用，原始 scalar 与 struct 长度是 `[0x32 0x0 0x1 0x4]` 配 64 字节、`[0x32 0x0 0x1 0x5]` 配 64 字节、`[0x33 0x0 0x1 0xc]` 配 656 字节。

- 按上面的协议读出来：blockType 是 `0x32` 即 50 两次、`0x33` 即 51 一次；chunk offset 都是 0，因为都小于 4096，单次就传完；extra u32 分别是 `{1, 4}`、`{1, 5}`、`{1, 0xc}`。block type `0x32` 与 `0x33` 的含义以及 64 与 656 字节 payload 的字段布局在公开资料里查不到：S1 与 S2 只给框架侧算法，S3 只贴了内核 handler 开头几行（读 `args->structureInput` 与 `extra_args`），S5 只给行属性。
- 656 是 `0x290`，与 tone-map 的 76 字节、74 的 64 字节都不是同一个结构。三次调用的 blockType 都不是 `0x6b`，所以它们不是 tone-map 路径。


内核侧的准入检查有公开符号：`isSetBlockEnumAllowed` 与 `detectSetBlockClientType`，配 entitlement `com.apple.private.iomfb.set-block`，backboardd 持有它。S5 说 27.0 上这个 entitlement 挂在 row23，这与 23 是 SetDigitalOutMode 冲突，按语义它更可能在 row78。

项目 enum 里目前没有 78，只有 79 `kFBMethodGetBlock`。要接住 backboardd 的这三次调用需要新增 78 的 case，最小实现是收下 scalar 与 struct、返回 `kIOReturnSuccess`，因为框架侧只在返回非 0 时中断循环。

## 7. 查不到的项

以下四项查不到，原样记录。

- 88 的 Apple 符号名查不到。公开资料里只有「`IOMobileFramebufferOpenByName` 内联发出的 1 scalar 调用，传 display type」这个事实。
- 78 的 payload 结构查不到，包括 block type `0x32` 与 `0x33` 的含义、64 与 656 字节的字段布局。
- 73 的第一个 scalar 为什么恒等于 3 查不到。S1 与 S2 都显示是 framework 硬编码常量，没有任何来源解释含义。
- 91 与 92 的公开名字查不到。本地确认 26.6 上 91 是 `IOMobileFramebufferSwapGetCurrent`（slot `0xa00`）、92 是 `IOMobileFramebufferSwapCancelAllGetCurrent`（slot `0xa08`），S5 说 27.0 的表有 93 行即 sel 0 到 `0x5c` 也就是 0 到 92，与之吻合，而公开资料没有把这两个数字和名字写在一起。

## 8. 冲突与未解释项

四条冲突照实记，不替任何一方下结论。

- selector 23 的归属。S2 给 `_kern_SetDigitalOutMode`，Snapintosh 点名 macOS 27 的 `s_set_digital_out_mode` 是 native selector 23，两者说是 SetDigitalOutMode；S5 说 27.0 的 row23 挂 `com.apple.private.iomfb.set-block`。
  - 本地 26.6 的证据支持前者：`_IOMobileFramebufferSetDigitalOutMode`（`0x2294b8afc`）取 slot `0xab0`，`_IOMobileFramebufferOpen` 在 `0x2294982a8` 把 `0x2294bc2c0` 装进 slot `0xab0`，而 `0x2294bc2c0` 调 `IOConnectCallScalarMethod(conn, 0x17, ...)` 即 23。
  - S5 的 row83（`allow-explicit-graphics-priority`，与 83 是 `s_displayed_fb_surface` 吻合）和 row86（`gain-map-access`，与 86 是 GainEncoderFinishEncoding 吻合）都对得上，只有 row23 对不上，倾向 S5 在这一行抄错或串列，而没有证据判定。
- 表长度。S5 说 iOS 26.5 是「88 rows sel0..0x57」即最大 87，而 S1 的 iOS 18.2 framework 已经在用 87、88、89、90，本地 26.6 还找到 91 与 92。两者不能同时成立，S5 的 26.5 行数偏少。
- row68 的 struct 大小。S5 说 26.5 上 `checkStructureInputSize` 是 `0x100` 即 256，27.0 改成 `0xffffffff`。S1 与本地都显示 framework 按 `8 * count` 传，日志里是 8 字节。XNU 的 `checkStructureInputSize` 是精确比较，8 字节过不了 256 的检查。这一条没有解释。
- swap record 即 selector 5 的大小逐版本变：`0x8c`（古董 iOS）、`0x46c`（16.7）、1288（17）、`0x588`（26.5 与 26.6）、`0x6e0`（27.0）。不能写死。本地 26.6 的 `_IOMobileFramebufferOpen` 初始化路径里确实有 `mov w1, #0x588` 配 `__bzero`。17 与 27 的 gamma 表大小也版本相关：26.6 上是 `0xC0C` 即 3084，与 S1 的 18.2 相同，与 S6 古董表的「`0xc00` out」不同。

## 9. 工具故障

调研那个会话的 `web_fetch` 全部返回 `DeepSeek API error (HTTP 404): failed to fetch URL`，所有网页与仓库内容改用 `curl` 加 `gh api` 抓取，`gh` 已登录可用，GitHub 代码检索正常。StackOverflow 的页面用 `curl` 也被拦，改用 StackExchange API 成功；Apple 论坛帖用 `curl` 成功。这一条影响以后所有调研子代理的工具选择，所以单独记一节。

## 10. 实现建议

四条建议按优先级排，代码改动归 task-24，排在 round F 之后的排期里，因为它改内核身份、要重新构建，不能与任何一轮同时进行。

1. 74 改成写满 2 个 scalar，count 与 selected index 都给 0，并把注释里的输出描述改成「2 scalar out 加 64 字节 struct」。
2. enum 补 78 `kFBMethodSetBlock`，名字用 S1、S2、S3 三方一致的 SetBlock，case 实现收下 scalar 与 struct 返回成功。
3. 88 的实现按「1 scalar in 是 display type，存进 client 的 display type 字段（本地是 `fb+0x888`），返回 0」，注释里写清名字来源是调用点事实，`s_map_display_type` 那一层是推断。
4. 按 round C 的实际调用序列补齐其余在用的号。序列是 `88 57 18 15 22 8 29 33 79(2056) 79(3164) 74(64) 25 12 79(44) 6 27(3084) 17(3084) 84 50 4 78(656) 78(64) 78(64) 68 5 3`，其中 88、15、22、33、74、27、17、84、50、78 都在里面。17 与 27 的 3084、5 的 `0x588` 都按 build 取值，别写死常量。

改的是两份拷贝：权威副本 `hackios-xnu-kernel/xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp`，构建树那一份 `hackios-xnu-kernel/out/xnu12377/iokit/Kernel/MiniIOMobileFramebuffer.cpp`。`xnu26/apply.sh` 开头有守卫，目录已存在就退出，所以树铺出来之后没有任何脚本再同步它，两个方向都靠人，改完要 `cmp` 一致再构建。

新增打印沿用现有的两个节流机制：`:1255-1265` 的 `fbtrace` 每选择器只记前 3 次调用并带调用进程名，`:1385-1387` 的「not implemented」由 `gFBLogged` 每启动一次。判读时引读数规则 §14.7：`not implemented` 这个子串跨三个驱动族且字段进制不同，framebuffer 的 15 个选择器是十进制、surface 的 5 个是十进制、keystore 的 2 个是十六进制，一把过滤会解析错。
