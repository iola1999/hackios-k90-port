# iOS 26 Metal IOSurface 行距约束

## 1. 已复现的导入拒绝

iOS 26.6.2 `23G90` 的 SpringBoard 创建了 `120×120`、`RGhA`、每行 `960` 字节的 IOSurface 3。`redwooddrawable` 已通过 `kRedwoodDescribe` 查询和格式检查，随后 AIR 的 `resource_from_handle` 返回空值。原诊断把剩余原因限定为用户内存或不可共享的 ID；该诊断缺少依据，已改为报告实际参数和后端返回位置。

Mesa 26.2.5 的 `fdl6_layout_image` 对 A830 显式线性布局要求每行至少对齐到 16 个像素，同时至少对齐到 64 字节。`RGBA16Float` 每像素 8 字节，要求 128 字节。`960` 与 `1088` 均不满足该要求；`1024` 与 `1152` 满足。这里的对照只检查布局，尚未验证后一组行距的真机 GPU 导入和绘制。

## 2. 行距查询来源

`MiniIOSurface.cpp` 的 `MINISURF_ROW_ALIGN` 当前为 64。`MiniIOSurfaceABI.inc` 的初始化方法通过 `minisurfInitReply` 返回 `rowMask=63`，写在初始化回复偏移 4。23G90 的 IOSurface 初始化以选择器 13 调用 `IOConnectCallMethod`，将 0x28 字节回复直接写到全局地址 `0x1ecd7d5e8`；`IOSurfaceAlignProperty` 和 `IOSurfaceGetPropertyAlignment` 从其偏移 4 读取行距掩码。`IOSurfaceBytesPerRow` 和 `IOSurfacePlaneBytesPerRow` 共用该值。

该接口只接收属性名和值，不接收像素格式。当前内核会按 64 字节计算缺省行距，同时保留调用方显式提供的非零行距。本轮保留这两项行为。修改全局掩码会影响其他格式及所有调用该接口的进程；直接改写显式行距还需要处理调用方的容量与读写方式。

23G90 的 `_MTLDevice minimumLinearTextureAlignmentForPixelFormat:` 经像素格式检查后返回 64。RedwoodMetal 先前继承该方法；其 `minimumTextureBufferAlignmentForPixelFormat:` 自行返回 16。SDK 明确规定前者给出线性纹理的 offset 与 rowBytes 对齐要求，后者用于 buffer texture。当前 buffer texture 创建尚未实现，本轮保留后者返回值并记录实际调用。

QuartzCore 静态调用扫描找到四处 `IOSurfaceAlignProperty` 调用，未找到上述两个 Metal getter 的直接调用点。扫描范围和动态 Objective-C 分发限制仍然存在。IOSurface 3 的生产者是否查询 Metal getter 尚未确定，getter 修正的验收需要真实调用记录和新 surface 行距。

## 3. 两个独立候选

AIR 候选只调整显式线性导入的行距检查和失败诊断。幂次像素大小使用 `max(64, 16×cpp)`；三分量格式按 Mesa 的规则使用 `64×next_power_of_two(cpp)`。后端仍返回空值的情况保留为未细分失败，记录格式、尺寸、行距、offset 和对齐要求。没有更改 surface 分配、GPU 布局或像素内容。

Metal 候选覆盖 `minimumLinearTextureAlignmentForPixelFormat:`：`RG32` 和 `RGBA16` 返回父类值与 128 的较大值，`RGBA32` 返回父类值与 256 的较大值，其他格式沿用父类值。父类查询保留像素格式校验及未来更强的约束。两个 getter 各记录每进程前 64 次查询的格式和返回值，便于判断真实生产者是否经过该接口。

`newTextureLayoutWithDescriptor:isHeapOrBufferBacked:` 继续返回 `nil`。现有 QuartzCore 调用还要求对象实现存储初始化、复制和结束操作，仅提供 size/alignment 无法满足该契约。本轮只校正对应说明和拒绝日志。

| 候选 | 基线 SHA256 | 候选 SHA256 | 本地目录 |
| --- | --- | --- | --- |
| AIR 行距诊断 | `69dd95e3597eb9469b3b5f645d9dab0b87714daa36f53f2d1c9f9c05c89c910c` | `75c0c32933f653d981731286847ded9bfaf2ed8fcb42455c878826594dd489e1` | `hackios-xnu-kernel/out/ios26-resume/sb-iosurface-pitch-diagnostic/` |
| Metal getter 与调用记录 | `1ea7c58ddb8ad6506749527fac41d1ca7ea10f977c3a9f0deefdd39b5880a907` | `cdc44d4e1b1e5d1d90403210fa5ece7a4cbd982740bb376ae3cd108a81688309` | `hackios-xnu-kernel/out/ios26-resume/sb-metal-linear-alignment-trace/` |

原始反汇编、布局对照和查询分析位于 `hackios-xnu-kernel/out/ios26-resume/sb-iosurface-layout/`。三个目录均为本地忽略目录，包含完整编译命令、源代码快照、测试日志及产物清单。原有桌面 on/off 包保持原文件。

## 4. 主机验证与边界

实际 Mesa `fdl6_layout_image` 测试使用 A830 `chip_id=0x44050001`、`120×120`、单层、单 mip、单采样和线性无 UBWC 布局，对六种格式共调用 12294 次。结果为 cpp 1/2/4 对齐 64，cpp 8 对齐 128，cpp 16 对齐 256，cpp 12 对齐 1024，ASan/UBSan 检查通过。

实际 AIR 导入 API 在 softpipe 上测试 `RGBA16Float` 的 960/1024/1088/1152 行距。960 和 1088 在行距检查处返回 128 字节要求；1024 和 1152 继续执行，随后由不支持外部存储的 softpipe 返回拒绝。该测试验证诊断顺序，不包含 GPU 导入。

Metal 主机测试使用从生产源码提取的 getter 方法和可控父类，覆盖 14 个格式、父类查询次数、父类返回 512 的保留行为，以及非法格式异常的传播；ASan/UBSan 检查通过。该测试验证返回值和继承行为，未执行 iOS 上的实际 `_MTLDevice` 实例。

两个 arm64e 动态库均编译和签名校验通过。AIR 的 46 个其余链接输入与基线哈希相同，Metal 的其余源文件与生产基线相同；导出符号清单分别保留 37 项和 116 项。新增逻辑没有增加对象、缓存或公共 API。行距公式与 Mesa 规则重复，由直接调用实际 fdl 的测试检查一致性；后续升级 Mesa 必须重跑该测试。Metal 主文件保持 5249 行，AIR 主文件减少。

## 5. 尚需真机确认

本轮未操作设备或 QEMU。先选择可持续产生帧的基线，只替换 Metal 候选，读取 `linear alignment query` 和 `texture-buffer alignment query` 日志，再核对 `RGhA` 创建行距。若没有 getter 调用，继续定位 IOSurface 创建方及其属性字典。若 getter 返回 128 但行距仍为 960，检查生产者是否采用了其他分配结果。随后再验证纹理导入、图标内容、持续帧更新及交互；查询成功和布局测试通过均不足以完成桌面验收。

## 6. 独立桌面包

基于 `sb-metal-mps-diagnostic/on` 的压缩开启桌面构建了 getter 验证包，仅替换 Metal 库为 `cdc44d4e1b1e5d1d90403210fa5ece7a4cbd982740bb376ae3cd108a81688309`。包位于 `hackios-xnu-kernel/out/ios26-resume/sb-metal-linear-alignment-package/on/ios26-sb-metal-linear-alignment-on.bin`，大小 25370088 字节，SHA256 为 `32c775472547b0537a374955484cb075585a61b073e4865499f6c58f0a7418da`；根盘 SHA256 为 `6d13d7e796e293e0119c0f9dca969c729012abc6b7b8590d0712cf13748fc973`。

APFS 读回比较了 125 条记录的内容、符号链接、元数据和扩展属性，仅 Metal 库内容及其压缩数据扩展属性变化。AIR 保持 `69dd95e`，实验 shim 保持 `ca26f9d`，SpringBoard job 与 launchd 缓存一致，`REDWOOD_SB_METAL=1` 保持。XNUP 仅 ramdisk 条目变化，其内容与新根盘逐字一致；kernel、cmdline、memsize、identity 与基线逐字一致。签名和保护输入哈希检查通过。完整记录位于同目录的 manifest、readback、APFS 记录和 SHA256SUMS。本包尚未在设备或 QEMU 上运行。
