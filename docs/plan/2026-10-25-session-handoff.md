# 会话交接（2026-10-25）

目标是在 REDMI K90（`annibale`，SM8750）真机上让 HackiOS 进入带图形加速的 iOS 界面。当前 iOS 16.5 已能启动到完整桌面，渲染走 Mesa `softpipe` 软件光栅，硬件加速未启用。本轮 v7 通过 USB 恢复验收，mode 4 完成安全流路由及 MEM_ALLOC 应答并收到 HWSCHED START ACK；阶段 15、16 通过；阶段 17 的 CPU 映射范围已修正，HWSCHED 首条 RAW 仍未收到 CP 初始化 ACK；新增普通 HFI 已收到 START ACK，逐次访问记录最后到 SQE 启动写前打印，未发布 CP_INIT，随后失联并确认新启动。详细输入和结果见[恢复审查记录](../progress/2026-10-25-gpu-resume-review.md)。

## 1. 设备当前状态

原会话结束时设备仍以 `xnuloader` 枚举，但 `getvar`、`oem log`、`stage`、`reboot` 全部 60～90 秒无回包。本轮接手后由用户按键恢复到 LK，安装 v7 并通过 USB 验收。此后逐次实验的结果：

- 最近的 HFI 布局及 VRB／RAW131 实验仍自动复位；随后 ARC CX／MX 读取完成；完整时钟候选在 CX 写 3 后仍读回 0。
- 随后已完成 CX／MX 最高合法 WRITE、阶段 5 的 GMU 650／HUB 200 MHz 配置及 START 后 GMU 500 MHz 配置检查。
- RAW131 发布后仍自动复位，同内核零 RAW 对照持续可读十秒。最高依赖票编码、四字 FEATURE_CTRL ACK、RAW 发送时序及本机 TPL1 配置已修订并分别实测，仍在首条 RAW 附近自动复位。
- AHB 五项控制已按本机 KGSL 配置为 `0x1b12` 并读回，首条 RAW 附近仍失联，最近确认 loader v7 `idle`。
- `6cb0fc4` 空 powerup 对照也未取得 CP ACK，最近确认 loader 新启动。
- `5e63bb5` 普通 HFI 已收到 START ACK，逐次访问记录最后到 SQE 启动写前打印，未发布 CP_INIT。
- `0b45e55` 已通过普通模式 SQE 启用前全部配置及 100 个健康周期，GBIF halt／ACK 为 `0x8/0x3`、RBBM 为 `0/0`；`c7a5661` 已将两项 halt 清零并读回。
- `f3fc4a1` 的普通 CB0 ACTLR 已严格读回 `0x303`，stall 对照仍失联。
- `b295f97` 实读 SQE 继承值为 0，写 3 对照仍未采到下一次读取，六项常开时钟中 CXO_AON 主机启用位为 0。
- `9cc044c` 的写入仍读回 0 并在阶段 5 停止，`b17112a` 已恢复只读基线。
- `be205eb` 已通过 SQE／AQE 共 35 页的预期 PA 和完整属性校验，仍最后到 SQE 写前打印，回退 Android 后已软件恢复 A 槽。
- `27372d1` 的早期 NS TLB 同步已返回 status 0，后续仍失联。
- `1782511` 已按主线取消普通模式首次 SQE 前的 HWCG 改写、保留继承值，仍最后采到 SQE 写前打印。
- `8b87aa9` 的实际 STR／DSB RAM 标记已实测，均未采到，最后仍为原写前日志。
- `b7230db` 已取得零值访问的 STR／DSB 三条标记、读回 0 和十秒健康结果，随后主动 USB reboot 恢复；写 1／3 后的启动处理与首次取指仍待定位。
- 最近确认 v7 `idle`，现按[普通 HFI／直接 ring 诊断](2026-10-25-ordinary-ring-probe.md)继续核对取指前提。恢复耗时的测量边界见恢复记录第 31 节，详见[恢复记录](../progress/2026-10-25-gpu-resume-review.md)。

进入 LK 后 `fastboot devices` 显示 LK 的目标设备，`product` 为 `annibale`。LK 里发 `reboot` 约 17 秒回到 loader（`product: xnuloader`）。

原会话观察到内核运行后约 40～55 秒通道失去应答，停止抓日志后仍出现。本轮 v7 在 GPU 停止后的第 65 秒仍正常应答，随后 USB 复位成功；该验证范围及恢复耗时见恢复记录。

## 2. 原会话结束时的仓库状态

| 仓库 | HEAD | 状态 |
|---|---|---|
| 父仓库 | `bb5e69e` | 干净 |
| `hackios-xnu-kernel` | `c51812b` | 干净，子模块指针在父仓同步 |
| `hackios-xnu-userland` | `106f9b5` | 干净 |

原会话的新增内核提交均在 `824c7be` 之后，**未推送**：

- `d04ca4e` loader：USB IN 端点三级恢复与等待上限（详见 §5）
- `0fc2b4a` gpu：secure 翻译 3a，配置并启用 context 3，路由保持 fault
- `e88e5f9` cpufreq：平台守卫按 loader 的 GIC 描述识别 annibale
- `c51812b` loader：build-id 测试跟随 LC-USB 的桩上下文（只改测试）

`4f6ab13b…`（loader 基线）与 `824c7be` 也没有推送。推送顺序固定为先内核仓后父仓库。

## 3. 关键产物

| 文件 | 大小 | SHA-256 | 状态 |
|---|---|---|---|
| `out/handoff-loader-v5.img` | 2,222,080 | `89ed602e…` | 已验证的旧还原镜像，**不要覆盖** |
| `out/handoff-m-bit-r1.bin` | 28,414,280 | `4243d802…` | 真机验证预检通过 |
| `out/handoff-m2-r1.bin` | 28,414,280 | `982bb0c2…` | 真机验证 MP_ASSIGN 交接成功 |
| `out/handoff-sec3a-r1.bin` | 28,414,824 | `553053f2…` | 原候选未上机，保留 |
| `out/handoff-mach-sec3a` | 19,194,448 | `55f6c996…` | 同上内核 |
| `out/handoff-cbscan-r2.bin` | 28,414,136 | `cad86c5a…` | 有效 CB 扫描（CB2 阳性对照成立） |
| `out/handoff-ui-gen80000.apfs` | 9,220,096 | `582b9fb2…` | 小根盘，含 GMU 固件，阶段 9 必须带 |
| `out/handoff-loader-v6.img` | 2,224,128 | `00f2a3e1…` | 原候选结构核对通过，源码审查发现问题，保留 |
| `out/handoff-loader-v6-payload.bin` | 79,456 | `e56f76dc…` | 已按 `BUILD_ID=d04ca4e` 重建并重封 |
| `out/handoff-loader-v7.img` | 2,224,128 | `bc08a4b4…` | 已安装，USB 验收范围见恢复记录 |
| `out/handoff-mach-sec3a-fsr` | 19,211,976 | `d1a357c6…` | FSR 修订后的 3a 真机通过 |
| `out/handoff-sec3a-fsr.bin` | 28,432,360 | `53452346…` | 对应 3a 第二轮 payload |
| `userland/system.apfs` | 2,492,227,584 | `a3ab9dce…` | 真实 iOS 根盘，桌面那轮用的就是它 |

内核 `handoff-mach-mbit`、`handoff-mach-m2` 与 payload 的人工命名对应关系见 `docs/progress/2026-10-25-gpu-preflight-pass.md` 与 `docs/progress/2026-10-25-gpu-mpassign.md` 的运行身份一节。

## 4. 已经验证的事实

### 启动链

槽位引导的形态约束是用真机代价换来的：**外尾必须是合并 DTB（`b30f254e…`，956,243 B）**，镜像约 2.2 MB；空 DTB 外尾（110 B，镜像约 1.26 MB）的镜像一律在 LK 跳转后约 7 秒回 LK，没有任何一次成功。此前文档里「空 DTB 占位、LK 不消费外尾」的前提据此作废。

槽位引导需要 `--set-active=a`。`current-slot` 从 LK 读取在 10-24 曾出现一次不一致，每次刷写都要记录当时读数。

### iOS 桌面

新 loader 带起 iOS 16.5 到完整桌面：根盘 md0 挂上 APFS System 卷（45,146 文件），`launchd.ios` 起来并打完 Restore environment，`backboardd` 到 spawning，帧缓冲 1156×2510×4 全非零，截图验证过页面切换与小组件渲染。渲染是 Mesa 26.2.5 的 `softpipe`，单帧 60～140 毫秒，另有两次 10 秒级停顿。

状态栏时钟比真实时间落后约 3 分 48 秒，来源是 payload 装配时写进去的 `epoch`，与装配时刻相差 3 分 07 秒。时钟走速正常（60 秒走 1 分钟），不是时基问题。装配完立刻跑就没有这个偏移。

### GPU 内核侧

阶段 9～13 全部通过：SMMU 翻译启用（stream 5, context 2, root PA `0x8cb124000`）、GMU 固件 `0x15a50` 字节校验、SCM `0x42000601` 与 `0x42002801`、HFI 消息队列就绪、性能与带宽表。

阶段 14 在 M 位判据下通过，日志有 `preflight routing sample: scanned 24, valid 1, 0 on the candidate route or context 3; HLOS-side conditions are satisfied`。

MP_ASSIGN 交接成功：78 个数据页合并成 78 个 region、3 个页表页、4 个批次，四次 SCM 全部 `returned 0, answer 0`，这 78 页由 CP_PIXEL 持有到冷复位。

`START resource request 20 failed` 的原因是**没有构造 MEM_ALLOC 回包**，属设计内，不是故障。

### SMMU context bank 归属

CB 扫描的阳性对照成立：CB2 在阶段 9 写入后读回 `0x27`，配套 TTBR0 变成页对齐的 `0xcb124000`、TCR `0x803519`、FSR `0x400`。

CB0、CB1、CB3、CB4、CB5、CB20 六个 context 的读数在两次不同 boot 之间**逐字节相同**，且都不具备 SMMU 上下文寄存器形态。CB3 的 `0x96cc51a` 的 M 位为 0。据此「非零即拒」判据过严，已改为只判 M 位。

需要说明的边界：**CB3 的归属没有被直接证明**，现有证据只是不支持「被 secure 独占持有」这个解释。

### 渲染路径的分叉点

软件与硬件的真正分叉在 Mesa 建 screen 时的 `osmesa_create_gpu_screen()`：它去 `drmOpenWithType("msm")` 打开 `RedwoodGPU` 服务，失败才退回 softpipe，没有需要手动拨的开关。日志里的 `softpipe` 就是 `glGetString(GL_RENDERER)` 读到的值，它还连带关掉了 IOSurface 零拷贝。

annibale 的平台检查跳过旧 `redwood_adreno.c` 入口。当前 `redwood_gpu_dispatch.c` 已增加 A830 的 `RedwoodGPUStart()` 调用，阶段 23 要求标准 HWSCHED context 自测通过后才启用 BO 并注册服务；外部缓冲映射、提交、EOP 等待及故障后的资源保留已实现并通过主机检查和 XNU 构建，真机尚未验收，详见[恢复记录第 20 节](../progress/2026-10-25-gpu-resume-review.md#20-a830-用户态接口准备)。当前普通 ring 分支只做首条 CP_INIT 诊断并停止，后续 context 和服务仍使用 HWSCHED 路径；首条 CP 命令、zap、shader 和桌面加速继续按顺序实测。

Metal 侧断在发现链第一步：`IOAcceleratorES` 默认不带 `MetalPluginName`，只有 `metal=1` 的启动允许 `metal_props on` 写上去，默认 `rc.jobs` 没有 metal 步骤。驱动类、`MTLDeviceSPI` 注入、容忍无 GPU 的 `-initWithAcceleratorPort:` 都已就位。

### CPU 频率

`redwood_cpufreq.c` 的平台守卫要求 `/arm-io/gic` 的 `reg[0]` 等于 `0x17600000`，本机由 loader 的硬件描述算出 `0x15C00000`，守卫在 cpufreq 之前就返回，EPSS 与 legacy RPMh 初始化整个跳过。设备日志里 `cpufreq: legacy RPMh/EPSS initialization skipped by platform guard` 即此，加 `cpufreq=1` 也不生效。已在 `e88e5f9` 修订并随本轮内核构建；GPU 实验未增加 `cpufreq=1`，提频仍待验收。

## 5. USB 命令通道卡死

原实现的 `usb_tx` 提交后置 `usb_in_owned`，主机中途放弃后仅置 `usb_in_invalid`，记录继续保留。`usb_wait` 的 3 秒上限只在保留态、内核运行或固件故障状态生效，普通循环可能持续等待。`d04ca4e` 修改了等待预算并增加三级恢复；接手审查发现恢复期事件丢失和缓冲所有权问题，后由 `7160d4d` 修订并完成第 1 节所述真机验收。

当前 `7160d4d` 保留 3 秒／10 秒等待预算，每笔陈旧 IN 请求最多申请一次 abort，只有经过校验的终止通知释放缓冲。OUT 记录区分数据传输与命令接收，并保留 IN 等待期间已经完成的命令；空闲等待和 IN 超时继续允许下一条命令交付。实现与测试范围见恢复记录。

当前生命周期测试及 50 项变异检查通过；真机验收覆盖空闲查询、完整截图、中止截图后的查询与复位，以及 GPU 停止后的查询与复位。

## 6. 原会话保留的 v6 产物

以下记录用于核对原会话产物。本轮使用 v7 完成安装与 USB 验收，见第 1 节及恢复记录。

- loader 已按 `BUILD_ID=d04ca4ea1c4434bd9e6081b6072a3792a0efa3be` 重建，`loader-phone.efi` 79,360 字节 `028754c7…`，XNUP payload 79,456 字节 `e56f76dc…`。产物里嵌入的是 `d04ca4e` 这串，找不到 `unknown` 回退值
- `out/handoff-loader-v6.img` 2,224,128 字节 `00f2a3e1…`。回读核对：头 `ANDROID!`，`kernel_size` 2,219,684（gzip 流 1,263,441 + 合并 DTB 外尾 956,243），`page 2048`，外尾与 `b30f254e…` 逐字节相同，解压 blob 3,225,360 = 176 + 3,145,728 + 79,456，XNUP 条目为 `loader.efi`（79,360，`028754c7…`）与 `usb`（2 字节，`e79e418e…`）。我曾独立复算一次，结论与其一致
- `out/handoff-loader-v5.img` 未被覆盖，仍是 `89ed602e…`，条目 `loader.efi` 73,216 字节 `33f1cbde…`
- 记录在 `docs/progress/evidence/repack-loader-v6-20261025T063111Z/manifest.md`

原 v6 的封装与验收计划保存在 `docs/analysis/local/usb-endpoint-wedge-after-upload.md`；当前操作以[真机手册](device-test-playbook.md)与恢复记录为准。

## 7. 下一步执行顺序

1. 重新确认 loader v7 的 build-id 和 `idle` 状态；3b、START、阶段 15／16 和后续自动复位结果见[恢复记录](../progress/2026-10-25-gpu-resume-review.md)。
2. 本机运行设备树为 gen8_0_1、chip ID `0x44050001`。以下为逐项诊断结果：
   - GMU revision 和 160 MHz 最低点已修正，fault stall、默认 CB0 提前配置及 GCC GEMNOC 对照仍在 RAW131 索引发布后复位；零 RAW 的 setup-only 对照已稳定运行 10 秒。
   - HFI 队列布局与 VRB 已按实际驱动修正，真机仍复位；ARC CX、MX 读取响应均为 0，写后读回与请求 3 不符，当前票值语义仍需确认。
   - `0eaa5e0` 主机电源请求和 `0813b2f` GMU／HUB 时钟已实现并通过主机检查与构建；阶段 5 在电源读回验证处停止，MX、PLL／RCG 未写入。
   - ACTIVE TCS1 对照也读到 0 并停止；`09778fe` 最高合法 WRITE 诊断完成 CX10／MX9 请求。
   - `98b40e3` 按 PLL 字段定义修订 L 校验，阶段 5 的 LOCK／RCG 配置通过。
   - `51c09c1` 完整阶段 17 已确认 START 后 500 MHz 配置及阶段 15／16，通过全部 CP 配置后仍在 RAW131 发布后复位；同内核零 RAW 对照十秒持续可读。
   - 后续已修订依赖票高四位、FEATURE_CTRL 第四字 error 校验、producer 与通知间的暂停及本机 TPL1 bit20，分别实测后仍复位；五个功能 ACK 均为 data 0／error 0。
   - 全局 ucode 权限和 MEM_ALLOC 回包构造与实际模块一致。
   - `5c99f63` 的五路 AHB 超时配置已完成阶段 5 读回及阶段 17 对照，仍失联后确认新启动。
   - `6cb0fc4` 空表发布已实测，仍在首条 RAW 附近失联后确认新启动。
   - 接着实施精确 A830 主线的普通 HFI／直接 ring 冷启动诊断；同次启动保持单一提交模式。
   - ARC 读回语义另行核对。
   - Android TZ 日志加密，已有复位诊断未确定原因。
3. 按 `oem ramdisk` → stage 小根盘 → stage payload → `oem run` 的顺序执行，保留完整日志和输入清单。自动复位或 USB 复位均须观察断开、重新枚举与状态；A 槽重试耗尽会启动 B 槽 Android。
4. CP 初始化通过后逐步验证 zap、scratch、标准 context、用户态 shader 和桌面绘制；A830 BO 映射、C ABI 分派及阶段 23 服务发布已在 `31979ad` 实现，主机检查与 XNU 构建通过，真机验证待完成。
5. cpufreq 修复继续独立验证；当前 GPU 实验未增加 `cpufreq=1`。

## 8. 已排除的方向

- 内核抢走 USB 控制器：内核里没有任何 USB 驱动，控制器、两个 PHY、TCSR、两个 GDSC、时钟分支、复位写全部零命中
- 高频取日志导致失联：不抓日志、每 15 秒只发一次 `getvar`，通道仍在 +40 到 +55 秒之间失联
- 「165 秒整机冻结」：那次是采样上限太短（8～20 秒）加上渲染的 10 秒停顿造成的误判，设备一直能应答
- 时钟变慢：固定偏移约 3 分 48 秒，来自 payload 的 `epoch`，走速正常
- ATS1PR 验证翻译：`IDR0.ATOSNS=1`，硬件翻译操作不可用，只能用软件表走查 + 寄存器读回 + FSR
- 两次运行法取有效 CB 扫描：`adreno8_space_off` 在 `keep=0` 时显式写 `cb sctlr = 0`，第二次运行读不到 `0x27`

## 9. 操作陷阱

- `getvar` 的输出写在 **stderr**，只读 stdout 会得到空串。采样脚本必须合并两个流
- 返回态 `oem log` 只能取到 32,767 字节（`log_buf[32768]` 上限），要看内核后半段日志必须在运行中抓实时环形缓冲
- `oem ramdisk` 的真正作用是把**紧随其后那一次下载**标记为 resident root，一次性，所以顺序必须是 `oem ramdisk` → stage 小根盘 → stage payload，中间不能插别的下载
- held 状态下 `oem ramdisk`、`oem run`、`oem probe`、`oem logwrite` 等 11 条命令会被拒
- `mkpayload.py` 的条目按数据长度补零到 16 字节对齐（`mkpayload.py:145`），解析时不能假设条目之间无填充
- 从 LK 刷 `boot_a` 需要 LK；迭代 payload 只需要 loader idle，不必刷写
- 失败的内核运行会自动回到 loader，成功的运行停在 loader 并且内核 panic 在 launchd（小根盘没有 launchd，属正常）

## 10. 未解决问题

- 3a 已确认 CB3 的配置写入和启用读回，START 已使用对应安全缓冲并获 ACK，安全数据的真实 GPU 访问尚未验证。其他执行体随后重新配置 CB3 的情况仍需结合配置读回与 fault 检查判断。
- 固定 MiCode 的 `arm_smmu_write_s2cr()` 使用 TYPE、CBNDX、PRIVCFG、SHCFG 及可选 EXIDVALID，qsmmuv500 Adreno 路径未替代该写入；未发现独立 secure 属性位。`0x303` 的构造有源码依据，3b 已读回路由并完成 MEM_ALLOC 和 START ACK，真实 GPU 数据访问继续单独验证。
- GMU 侧日志格式没有核对过，固件访问失败时的表现只能靠 CB3 的 FSR／FAR／FSYNR0 与现有的 SMMU fault 打印行判断
- 方案 4（隔离可重建）与方案 5（annibale 启用看门狗）未做
- 用户态先用 `gl=1` 验证现有 GLES 路径和实际 renderer。Metal 发现还依赖 `metal=1` 及 `metal_props on`，继续单独验收；`sb3`（GL 函数 40）缺失与窗口服务器行为按[图形路径记录](../analysis/2026-10-24-metal-route.md)核对。
