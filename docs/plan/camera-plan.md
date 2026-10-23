# camera-plan.md — annibale（REDMI K90 / SM8750 "sun"）相机路线

状态：调研稿（离线，35 分钟时间盒）。前提 = iOS 已能开机（软渲染锁屏之后）；porting-plan.md 已把相机排在开机之后（[porting-plan.md#L81](./porting-plan.md#L81)、#L91）。

## 0. 结论（TL;DR）

- 红杉（POCO X5 Pro / SM7375 "yupik"）的相机栈**不是半成品，是端到端能跑的裸寄存器方案**：kernel `redwood_camera.c`（cam=1..5 分级）出 RAW10 帧 → mediaserverd 里注入 dylib 冒充 H10ISP 的 FigCaptureDevice → 软 ISP（camera_isp.c）出图，Camera.app 预览 + 快门拍照 + 点按对焦 + 手电都有真机回归脚本（rc.jobs.camera / rc.jobs.photo）。
- iOS 用户态**没有被裁剪/魔改相机框架**：CMCapture/CMCore 原样跑在 mediaserverd 内，靠 `inject_media.c` 换 `BWFigCaptureDeviceVendor` 的 create 函数接管；camerad/MMCS 不参与出画面。annibale 复用这套用户态零改动，要重写的全部在 kernel/资源层。
- annibale 的 CAMSS 资源：`/tmp/hw_check.dts`（annibale-dtbo 反编译，model "Sun SoC"）里全套节点都在（CSIPHY×6 / CSID×3+lite×2 / IFE×3+lite×2 / camcc / CCI×3 / CPAS / SMMU / GDSC / 4 路 sensor 供电与 GPIO），**本档即为第一份相机资源表**；annibale-hw-map.md 目前只有 camera_region 两行 reserved-memory（#L266-L267）和 SE8/SE9 摄像头 I2C 总线（#L196-L197），CAMSS MMIO 全空白。
- 最大未知数 = **主摄 OV50E（光影猎人800，OV 定制）的上电/初始化寄存器表与模式表**，只存在于设备 `/vendor/lib64/camera/com.qti.sensormodule.*.bin`（红杉同款来源），当前 annibale-backup 只有 vendor_boot，**没有 vendor 分区 dump** → 这是 L0/L1 的第一道门。
- 建议：L1（单摄预览，先 TPG 后真 sensor）3–5 周 + 6–10 个真机窗口；L2（拍照）+2–3 周。sensor 表拿不到则停在 TPG 演示或回 L0。

## 1. 红杉现状盘点（以仓库实际代码/注释为准）

### 1.1 kernel：`hackios-xnu-kernel/xnu/files/bsd/dev/redwood_camera.c`（4264 行）

纯手写寄存器驱动，零 IOKit 相机框架、零 Qualcomm 固件（不碰 CamX/CHI，IFE-lite 本身无固件；ICP 固件不用）。文件头注释即完整设计文档（[redwood_camera.c#L1-L72](../../hackios-xnu-kernel/xnu/files/bsd/dev/redwood_camera.c#L1)）。

- boot-arg 分级（同文件 #L46-L58）：
  - `cam=1` 只读勘察（时钟/电源域/引脚/PM8008i 状态）；`cam=2` 上电读 chip ID 再下电（每写读回）；`cam=3` 无 sensor，CSID test pattern → RDI0 → IFE-lite0 → 内存，`xl camera` 回收给 host；`cam=4` 真 sensor 帧走同路径；`cam=5` iOS 模式（#L3233 起，出 `/dev/redwood-camera`）。
  - 修饰项：`cam_sensor=macro|wide|front|ultra`（默认 macro；cam=5 默认 wide）、`cam_mode`、`cam_shutter`/`cam_gain`、`cam_pattern=1`（彩条）、`cam_fake=1`（QEMU 假帧，#L3622）、`cam_keep_mb`。
- 依赖的硬件路径（全是手写字节级，每写必读回、失败即全下电）：
  - 时钟/电源：GCC camera AHB/XO、camcc（yupik）titan_top GDSC、PLL2 1440MHz、MCLK RCG/branch（#L821-L1063）。
  - 供电：PM8008i 走手撸 I2C（SE1，GPIO4/5），PM8350C GPIO3 复位，LDO 只写设备树给定电压。
  - I2C：CCI（摄像头控制总线）两 master 手撸位时序（#L376-L422 含总线卡死恢复）。
  - 数据通路：CSIPHY（sensor 那路）→ CSID-lite0（RDI0）→ IFE-lite0 → 内存；cam SMMU 只配一个 match register + context。
  - sensor 初始化序列不在代码里：来自 Android sensormodule `.bin` 转出的 `fw/camera-*.tab`（ov02b10 / s5khm2sd / ov16a1q / s5k4h7）。
- 四摄档案在 `sensors[]`（#L181-L240）：CCI 总线、slave 地址、chip ID、reset/MCLK GPIO、rail 与电压、CSI lane 型（C-PHY 3trio / D-PHY 4lane）一应俱全。
- 设备接口：`/dev/redwood-camera`，帧头 `redwood_camera_frame`（RAW10、bayer 序、black level、曝光行、gain、帧长上下限、focus 位）+ `redwood_camera_command`（EXPOSURE/KEEP/SENSOR/FOCUS），见 [redwood_camera.h](../../hackios-xnu-kernel/xnu/files/bsd/sys/redwood_camera.h)。

### 1.2 iOS 用户态：`hackios-xnu-userland/userland/`

- `src/inject_media.c`：注入 mediaserverd（注释即权威说明，[inject_media.c#L1-L40](../../hackios-xnu-userland/userland/src/inject_media.c#L1)）：
  - 跳过 portrait 的 CoreImage prewarm（无 GPU 会跳 0 地址）；
  - `cam=5` 时把 `+[BWFigCaptureDeviceVendor sharedCaptureDeviceVendor]` 的 create 函数换成我们的 FigCaptureDevice（顶替 H10ISP.mediacapture 的角色）；
  - 无相机时只给 FigFlashlight 一个假 vendor（torch=3 接 `/dev/redwood-torch`）。
- `src/camera_device.c`：FigCaptureDevice + 两条 FigCaptureStream（后=wide、前=front），格式名照抄 iPhone X 的 `CMCapture D22/AVCaptureSession.plist` 让 AVCaptureDevice 格式/会话预设能解析；帧经 `VideoOutputHandlers` 的 PixelBufferHandler 进图；StillImageCaptureNow 出全幅一帧；wide 有 VCM：`af_frame()` 点按对焦。未实现的属性打日志放行。
- `src/camera_isp.c/.h`：软 ISP——黑电平、lens shading 网格、AWB（grey-world）+AE 增益、CCM、sRGB gamma；预览最近邻抽样、拍照双线性 demosaic；CCM/shading 可吃 sensor 自带 tuning（`isp_load_tuning()`）。无降噪、无视频稳像（明确拒绝给硬件没有的东西）。
- 测试/回归：`camera_test.c`（raw/cycle/noise 三模式，帧率、四摄轮切、黑电平噪声表征）、`camera_avtest.m`（AVFoundation 枚举）、`rc.jobs.camera`（开 Camera.app 预览 40s + 快门/切前摄/变焦/点按对焦，靠 loader 假 `/arm-io/isp` 节点出图标）、`rc.jobs.photo`（关 Live Photo 后连按两次快门）。
- **能做到什么程度（文档口径）**：四摄取流、预览、静止拍照、AF、变焦、手电、噪声测量都写成了真机流程；没有录像/视频稳像/RAW 域多帧。结论：annibale 移植时用户态这一半≈免费，**改动全在 kernel**。

## 2. annibale 侧资源

### 2.1 来源

`/tmp/hw_check.dts` 在（43867 行，`model="Qualcomm Technologies, Inc. Sun SoC"`，compatible `qcom,sun`）= `docs/analysis/data/annibale-dtbo.dtb`（自 vendor_boot 剥出）的反编译。以下均引其行号。

### 2.2 CAMSS 块基址（hw-map 未收录，本档补录）

| 块 | 基址/大小 | 备注（dts 行） |
|---|---|---|
| camcc | `0xade0000+0x20000`，compatible `qcom,sun-camcc`,`syscon` | #L18463；GDSC 偏移：titan_top `0x134c`、tfe0/1/2 `0x1004/0x1084/0x10ec`、ipe0 `0x17c`、ofe `0xc8` |
| camcc_crmc / cambistmclkcc | `0xadcd600`（syscon）/ `0x1760000` | #L18457、#L43050 |
| CSIPHY0–5 | `0xada9000` 起步进 `0x2000`（各 8K） | csiphy **v2.3.0**（CSIPHY2 带 p11 修订），C/D-PHY 通用，`cphy_rx_clk_src`；#L39330-L39490 |
| CCI0/1/2 | `0xac7b000` / `0xac7c000` / `0xac7d000` | #L39485、#L39671、#L39857 |
| CSID0/1/2 | 节点名 `@ad26/29/2c000`，reg `0xad27000`/`0xad2a000`/`0xad2d000`（0x2b00） | compatible `qcom,csid980`；**节点名与 reg 差 0x1000，写文档时以 reg 为准** |
| CSID-lite0/1 | reg `0xad6d000`/`0xad72000`（0xa00） | `qcom,csid-lite980`——红杉同款 lite 思路在 sun 上仍有硬件对应 |
| IFE0/1/2 | `0xac86000`/`0xac96000`/`0xaca6000`（各 64K） | `qcom,ife0..2`，时钟名 **tfe_0..2**（TFE 血统），UBWC static cfg；#L41027+ |
| IFE-lite0/1 | `0xad6d000+0x2800` / `0xad72000+0x2800` | 与对应 csid-lite 同窗（lite 把 CSID+IFE 打包）；#L41161+ |
| CAM-CPAS | `0xac13000` | reg-names：cam_cpas_top / camnoc_nrt / camnoc_rt / rpmh / cesta；client 表含全部 csiphy/csid/ife/ipe/cdm/icp——**titan 访问前必须先起 CPAS/CAMNOC，红杉没有这一步** |
| CAM SMMU | `qcom,cam_smmu` 多 context：ife / icp / jpeg / cdm / secure，各带 resv region | #L39947-L40182；红杉只配 1 个 match reg+context，这里至少 IFE 一路 + RT buf |
| ICP0/ICP1 | `0xac05000` / `0xac150000`（dts 原值，疑 `0xac15000`+页对齐笔误，待复核） | #L41322+；配 `qcom,ofe`——L1 不用 |
| CSIPHY TPG13–15 | `0xad8b000`+（各带 `0xac04000` 第二窗） | TPG 演示路径存在（cam=3 等价物的依托） |
| RT-CDM | `cam-cdm-intf` + `rt-cdm2_2`×5（cam_hw_pid 0x18..0x1c） | #L40865-L40978；IFE980 主要靠 RT-CDM 缓冲编程，非纯直写 |
| 预留内存 | `camera_region 0x9b300000+8M`、`camera_2 0x9bb00000+8M` | hw-map §10 #L266-L267（**唯一已映射项**） |

### 2.3 sensor 配置（dts 内 4 摄；主摄 = wide）

| 角色 | 控制总线 | CSI | MCLK/reset | 供电（min=max，µV） |
|---|---|---|---|---|
| wide（主摄，eeprom_wide，AF+flash） | **CCI0 m1** | csiphy-sd-index **3** | MCLK1 19.2MHz（GPIO90），RESET GPIO6 | VIO 1.8V、VDIG 1.15V、VANA 2.8V（=`camera_wide_avdd_ldo` 固定轨，GPIO127 开关，#L757-L768）、VAF 3.1V、BOB2 2.7V |
| tele（eeprom_tele，AF） | **CCI1 m0** | sd-index 1 | MCLK3（GPIO92），RESET 113（`0x71`） | VIO 1.8V、VDIG 1.1V、VANA 2.8V、VAF 2.8V |
| ultra（eeprom_ultra） | **QUP SE8 I2C `0x880000`，slave 0x7a**（eeprom 0x50） | sd-index 2 | MCLK2（GPIO91），RESET 3 | VIO 1.8V、VDIG 1.0–1.2V、VANA 2.8V；`aon-camera-id`（AON 低功耗模式） |
| front（eeprom 0x51） | **QUP SE9 I2C `0x884000`，slave 0x10** | sd-index 4 | MCLK4（GPIO93），RESET 7 | —（#L33217 起，同构） |

- 主摄身份：光影猎人800 = **OmniVision OV50E 的小米定制版**，50MP、1/1.55"、OIS（[百度百科](https://baike.baidu.com/item/%E5%85%89%E5%BD%B1%E7%8C%8E%E4%BA%BA800/68104798)、[fonearena 发布稿](https://www.fonearena.com/blog/467264#1)）；K90 另配 50MP 2.5x 长焦 + 超广角（[ixbt](https://www.ixbt.com/news/2025-10-23/120-ip68-ip69-7100-100-2-5-bose-nfc-redmi-k90.html)）。DTS 不含型号/寄存器表：CamX 从 vendor 用户态 bin 探测加载 → **chip ID、上电序列、模式表全部待取**。
- 供电 phandle（0x3f8/0x411/0x3f6/0x3fd…）是 RPMH PMIC LDO，具体 LDO 名待从 base dts 反查（红杉的 PM8008i-手撸-I2C 经验不适用，annibale 应走 SPMI/RPMH，更接近 redwood_battery/buttons 的路子）。

### 2.4 映射状态小结

已映射：SE8/SE9 摄像头 I2C 总线（hw-map §8 #L196-L197）、camera_region×2（§10）。**完全空白**：camcc/CSIPHY/CSID/IFE/CPAS/CDM/SMMU-ife 全部 MMIO 与中断、CSIPHY↔sensor 路由、GDSC/时钟 id（sun camcc 的 RCG/branch 编号）、sensor 供电轨 LDO 名、vendor 侧 sensor 驱动 bin。本档 §2.2/§2.3 应先原样搬进 annibale-hw-map.md 新章节。

## 3. 结构性差异与最小路线

### 3.1 SM7375(yupik) → SM8750(sun) 的差异（对"红杉式裸写"的影响）

1. **CPAS/CAMNOC/cesta 是新必经环节**：不初始化 CPAS（`0xac13000`，含 RPMH bw voter），titan 域访问起不来；红杉完全没有这块 → 纯盲写，靠读回+报错二分。
2. camcc 换 `sun-camcc`：GDSC 偏移变了（titan_top=+0x134c）、多出 camnoc_rt/cesta 时钟族；红杉 camcc 例程的偏移/时钟 id 全要重排，但"RCG+branch+GDSC+PLL"套路一致。
3. **CSID980/IFE980 走 RT-CDM 缓冲编程**（rt-cdm2_2 + cam-cdm-intf + UBWC），不再是红杉那种 CSID-lite/IFE-lite 直写 RDI 就能出帧的最短路径；好在 **csid-lite980/ife-lite0 仍在**（`0xad6d000`），L1 首选复刻红杉 cam=3/4 的 lite 路径，TPG13–15 可先证通路。
4. CSIPHY 升到 v2.3.0（6 个，C/D-PHY 混合，timer/clk 结构不同）：D-PHY4lane 主摄的 settle/时序常数需真机标定。
5. sensor 控制总线分裂：wide/tele 在 CCI（红杉 CCI 位时序代码可移植，寄存器窗 `0xac7b000`）；**ultra/front 在普通 QUP GENI I2C（SE8/SE9）**，红杉没有 GENI I2C 手撸例——好在 L1 只做 wide，用不到。
6. SMMU：至少 IFE context + RT buffer 区要配（camera_region `0x9b300000` 就在手边），比红杉 1 个 context 复杂但仍是有限寄存器。
7. 供电：RPMH LDO/SPMI + GPIO127 固定轨，替代 PM8008i；写轨前先从 base dts 解出 LDO 身份（TODO）。

### 3.2 iOS 侧要骗过谁

**不是 camerad。** 出画面的门在 mediaserverd 里的 CMCapture 栈：AVFoundation → mediaserverd → `BWFigCaptureDeviceVendor` → FigCaptureDevice/Stream 属性表 + PixelBufferHandler。红杉已经证明：kernel 出 `/dev/redwood-camera` + loader 假 `/arm-io/isp` 节点 + inject_media 换 vendor，Camera.app 就肯预览/拍照；iOS 16.5 用户态（本仓库固定在 `ios165`）无需再裁再改。annibale 上唯一 iOS 侧改动 = dylib 里 device 属性表若被 iOS 版本差异卡住再调（此处零风险，版本冻结）。

### 3.3 分级路线

| 级别 | 内容 | 盲写比例 | 真机窗口 | 工作量 |
|---|---|---|---|---|
| L0 | 不做（现状默认，porting-plan 口径） | — | — | — |
| **L1a 通路验证** | sun-camcc/CPAS/GDSC/SMMU-ife 手撸 → CSIPHY **TPG13** 或 CSID TPG → csid-lite0→ife-lite0 → camera_region → `/dev/redwood-camera`；用户态零改动看到彩条/TPG 预览 | **~70–80%**（CPAS、sun camcc、CDM-lite 编程全是新写的；骨架/日志/分级思想 100% 复用 redwood_camera.c） | 4–6 个（复刻 cam=1→3 分级勘察节奏） | 2–3 周 |
| **L1b 真 sensor 预览** | 拿 OV50E bin 解出上电序列+一条 4032×3024@~30 模式 → CCI0 初始化 wide → 同 lite 路径出帧；替换 cam_fake | 上表基础上 +sensor 表 ~50%（bin 解析器可复用 sensormodule 解码逻辑） | +2–4 个 | +1–2 周 |
| **L2 拍照** | 全幅模式、`REDWOOD_CAMERA_KEEP` NV12 回收、用户态 camera_isp 已就绪；eeprom tuning（shading/CCM）+ VAF/actuator 点按对焦（CCI 写 VCM 表） | tuning bin 解析 ~40% 盲；actuator 例程可抄 redwood wide AF | +3–5 个 | +2–3 周 |
| 暂缓 | 录像（要视频编码+稳像）、多摄并发、AON、HDR/多帧、IFE980 全量 CDM/UBWC、ICP/OFE | — | — | — |

合计 L1 = 3–5 周（TPG 先行则风险主要在 CPAS/camcc）；L2 累计 5–8 周。均为周级、单人。

## 4. 放弃 / 推迟准则

1. **vendor dump 门**：拿不到 `/vendor/lib64/camera/com.qti.sensormodule.annibale_*.bin`（或等价 sensor 驱动）且真机 `cam=2` 式探针两次窗口内读不到 OV50E chip ID → **L1b/L2 立即冻结，只保留 L1a TPG 演示或回 L0**；sensor 表反推（从 Android logcat/CamX trace 抠寄存器）不进本期。行动项：下次真机窗口顺路 `adb pull /vendor/lib64/camera`（annibale-backup 现在只有 vendor_boot，无 vendor 分区）。
2. **CPAS 门**：CPAS/CAMNOC 初始化连续 2 个真机窗口无法让 tfe/gdsc 稳定上电（读回失败/总线挂死）→ 降级为"仅 TPG 内存图 + loader 直接铺 framebuffer"的静态相机演示，相机整体转 perf backlog（与 GPU 同排，见 [gpu-plan.md#L113](./gpu-plan.md#L113) 的先例）。
3. **窗口预算门**：单周窗口数 < 1 时只做盲写与离线校验（fw tab 解析、寄存器读回白名单），不开新硬件路径。
4. iOS 侧出现必须动用户态才通的新依赖（capture stack 探测了 annibale 才有的东西）→ 记录后推迟，不阻塞 kernel 分级验证。

## 5. TODO（未及，留待下轮）

- 反查 supply phandle（0x3f8/0x411/0x3f6/0x3fd/0x5e）→ 具体 PMIC LDO 名与 SPMI 地址；`0x5e`=cam_clk 域供电疑为 titan GDSC 的 regulator。
- sun camcc 时钟 id 表（dts `clocks=<0x42 N>` 的 N）：从 AOSP `camcc-sun.c` 对表，补进 hw-map。
- `0xac150000`（icp1）与 csid 节点名/reg 差 0x1000 两处 dts 怪值复核。
- GPIO 控制器 phandle 0x27 的 base（TLMM 基址 hw-map §11 已有，换算实际 GPIO 号）。
- loader 假 `/arm-io/isp` 节点在 annibale loader 里的注入点核对。
- 把 §2.2/§2.3 原样搬入 docs/analysis/annibale-hw-map.md 新章节"§ 相机（CAMSS）"。
