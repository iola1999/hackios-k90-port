# GPU 恢复审查与真机记录

## 1. 目标与接手状态

本轮继续在 K90 上启动带图形加速的 iOS。完成条件包含 GPU 实际执行 shader、像素读回正确、桌面通过 GPU 绘制，以及可操作的故障恢复。输入为[会话交接](../plan/2026-10-25-session-handoff.md)、对应原始会话、当前源码和本地构建产物。接手时父仓库为 `f069112`、kernel 为 `c51812b`、userland 为 `106f9b5`，三处工作树均无修改。

初次查询只见 `xnuloader` 枚举，`getvar product` 在 8 秒内无返回。用户按键恢复后，重新读到 `product: annibale`、`current-slot: a`、`unlocked: yes`。原始 `boot_a` 备份的压缩哈希、解压长度 100663296 字节及原始哈希均核对一致；v5、v6、小根盘和 3a payload 的完整哈希也与交接记录一致。

## 2. 审查发现与处理

- v6 的专用 USB 恢复事件循环丢弃 OUT 完成事件和部分 IN 完成事件；重建会修改全局缓冲指针，接收调用可能仍引用旧缓冲；halt 调用成功也缺少释放传输所有权的接口依据。修订方向为统一处理完成事件，每笔陈旧 IN 请求最多申请一次 abort，仅由经过校验的终止通知释放缓冲，继续保留 OUT 复位命令入口。
- USB 等待预算还需要区分空闲命令接收与已经放弃的数据传输。空闲等待超过预算后，仍应接收下一条完整命令；数据传输放弃后到达的字节只能用于确认请求结束。
- 原 3a 的软件检查只核对第一个叶子描述符，未从 TTBR 根检查完整路径，也未覆盖全部缓冲。修订将遍历整个映射，并补充 secure context 的启用状态及故障寄存器诊断；交接后继续限制 CPU 访问安全内存。
- `RedwoodGPUStart()` 的唯一调用属于旧 Adreno 驱动，annibale 跳过该入口。gen8 初始化成功之后仍缺少 A830 的用户态资源管理、命令提交与 fence 实现。现有服务的失败清理也需检查，确保设备仍可能访问的内存继续保留。

## 3. 已完成的离线检查

`tools/test-adreno8-hwsched.py` 已通过。固定厂商提交 `d50b305f7da9e14715a25120a4ac7b1a4b8b97c3` 的四份 graphics-kernel 文件经 SHA-256 核对后，用于 `tools/test-adreno8-gpu.py`；4 KiB 和 16 KiB 配置均通过寄存器表、PM4、固件、启动顺序及失败保留检查。主机模型尚未覆盖真实 GPU 执行。

原始会话摘录、厂商文件、构建日志和运行产物保存在 Git 忽略的 `docs/progress/evidence/2026-10-25-codex-gpu-resume/`。后续真机结果按运行输入与实际日志补充。

## 4. loader v7 真机验收

USB 修订提交为 `7160d4d`，v7 镜像为 `out/handoff-loader-v7.img`，2224128 字节，SHA-256 `bc08a4b4d338be7e31984b49f8d81caedac0e80d1c4c5fba3bc712baa8048b4c`。相同输入的两次 EFI 构建逐字节一致；独立解包和 67 项封装检查通过。生命周期测试覆盖事件交错、空闲接收与数据接收的超时差异，50 项变异均被发现。USB 生产文件净减少 90 行，单文件 992 行；删除了恢复期的独立事件循环与重新分配路径，新增的 OUT 用途与完成长度记录用于保留先到达的命令。

安装前重新查询确认 LK 身份、A 槽和解锁状态，再写入 `boot_a`。启动后 build-id 完整匹配 `7160d4dadd9bf27cbb2b4c42e2629b9e0aa3a460`，`result: idle`，屏幕参数为 `1156 2510 4624`。本轮验证结果如下。

| 检查 | 结果 |
|---|---|
| 连续 10 次身份查询 | 全部成功 |
| 空闲 15 秒后的首条状态查询 | 成功，主机用时 0.029 秒 |
| 完整截图上传 | 11606240 字节，主机用时 0.306 秒 |
| 截图上传 1 MiB 后中止主机进程 | 等待 12 秒后首条状态查询成功，随后 USB 重启成功 |
| GPU 运行后第 65 秒查询 | 返回 `hung-held`，主机用时 0.028 秒 |
| `hung-held` 状态 USB 重启 | 观察到 USB 断开，17.46 秒重新枚举并返回 `idle` |

这些结果覆盖本轮输入和一次中止传输实验，固件同步调用的全部失败方式仍未覆盖。

## 5. 3a 首轮结果与 FSR 修订

完整映射修订提交为 `537f970`。从原始 XNU 标签重新应用 76 个补丁和 132 个新增文件，将生成结果与编译目录的 5127 个源文件比较后，只更新 10 个差异文件，再完成构建。运行内核为 `out/handoff-mach-sec3a-review-unstripped`，19211976 字节，SHA-256 `b7284078f1b8f4735a6fb870104e2ad3d28c36befd586c8fd95bdce40a3ad1d2`；payload 为 `out/handoff-sec3a-review.bin`，28432360 字节，SHA-256 `e5da659d9bc3c887879fa9feddb0cf84a5917cf2558d3f57b0833c20f09ca244`。小根盘继续使用交接中的 `582b9fb2…` 版本。

首轮日志确认全部 312 个叶子映射通过根表遍历，4 批 MP_ASSIGN 均返回 `0`、answer `0`。CB3 SCTLR 写入 0 后读回 0；CBAR、CBA2R、TCR、TTBR0 与 MAIR0 均读回成功。TCR2 写入 `0x38011`、读回 `0x38071`，差异为已允许的 TBI 位。路由保持 fault。

首个停止点为清除 FSR 后读回 `0x400`。原 3a 要求整个 FSR 为零；[固定 MiCode 的故障位定义](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/f66f8c8bcbe38044fab61d44ea7f7c224f82b3ea/drivers/iommu/arm/arm-smmu/arm-smmu.h#L217-L240)与厂商 KGSL 定义确认 `[10:9]` 是翻译格式字段，`0x400` 对应 AArch64，有效故障掩码为 `0xc00001fe`。提交 `3a4d388` 将该处改为使用已有 `FSR_ALL` 掩码。新增测试接受格式字段，并逐个验证全部 10 个有效故障位在启用前后都会停止；4 KiB、16 KiB 两套配置与 8 项变异检查成功。修订后继续单独重测 3a。

FSR 修订后的第二轮已通过 3a：内核 `out/handoff-mach-sec3a-fsr` 为 19211976 字节，SHA-256 `d1a357c683f6ee676a8c64899b8a9ac17a1f89cdb4808a777dbcff602418fe13`；payload `out/handoff-sec3a-fsr.bin` 为 28432360 字节，SHA-256 `534523460791df38ab37a1e51dac6dfb800702b1dad0981447fb6fc3693d8cd3`。日志确认 TLB 同步完成、SCTLR 写入并读回 `0x27`、FSR 为 `0x400` 且有效故障位为零，随后打印 `secure translation 3a ready`。本轮按 mode 3 设计继续保持 stream 2 为 fault，MEM_ALLOC 未应答，START 停止。采样后 USB 复位，17.47 秒重新枚举并返回 `idle`。

## 6. 3b、START 与阶段 15～17

提交 `744092c` 实现 mode 4：同次启动完成 MP_ASSIGN、3a 和 translate 路由验证后进入 READY，允许后续普通分配与原请求精确重放；新 secure handle 被拒绝，HFI／START 失败后永久关闭服务，全部资源保留至冷复位。ASSIGNED 区分移交成功与失败关闭，原 `entry.terminal` 已删除。服务测试覆盖 21 个场景及 4 KiB／16 KiB 页大小，13 个服务变异和 8 个翻译变异均被发现；既有 SMMU、memory、secure、handoff、HFI、HWSCHED、quiesce、config、GPU 检查通过。独立审查与变更必要性检查通过。

构建前重新生成 XNU 源码，5128 个源文件比对一致，更新了编译目录中的 11 个文件。内核 `out/handoff-mach-sec3b` 为 19212400 字节，SHA-256 `e72b4f36ed3802a846a86628abee0c7d93da28b8d2180662e74650f349d1dbbb`。阶段 14 payload 为 `out/handoff-sec3b.bin`，28432776 字节，SHA-256 `0f719871ac0934985655b99c3fb68102ae5b616bbc6996321a2655f5d2db72d6`。阶段 15～17 使用同一内核、小根盘和 mode 4，仅更改阶段参数与 epoch，各轮输入及完整日志保留在本地调试目录。

| 阶段 | 真机结果 |
|---|---|
| 14 | 路由读回 `0x303`、SCTLR `0x27`，有效故障位为零；kind 5 回包后继续收到 kind 7、24 请求，最终 HWSCHED START ACK 成功 |
| 15 | 125 MHz／带宽索引 2 请求获 ACK；GX 状态仍为 `0x3`，后续需要 OOB |
| 16 | 363 个映射通过软件遍历，GPU context 0 启用，stream 0 路由读回 `0x300` |
| 17 | OOB ACK 成功，随后 GPU 寄存器写入触发 CPU data abort；尚未完成 CP 初始化 |

阶段 17 的异常 PC 对应 `adreno8_wr`，调用点为 `adreno8_gpu_cp_init+0x290`，写入偏移 `0x2b840`。该轮 `adreno8_gpu` 只映射 `0x10000` 字节，该写入超出 CPU 映射范围；后续修订与重测见第 7 节。

阶段 14～16 的 USB 复位均观察到断开、约 17.4 秒重新枚举及 `idle`。阶段 17 复位后启动了 B 槽 Android；随后通过 ADB 返回 LK，确认 A 槽 `slot-successful: no`、`slot-unbootable: yes`、`slot-retry-count: 0`，B 槽为 successful。重新选择 A 槽并启动后 v7 返回 `idle`。后续实验须计入 A 槽重试次数；B 槽回退后可通过 ADB 恢复实验入口。

## 7. 阶段 17 后续定位

提交 `7faa7c1` 按固定厂商 `sun-gpu.dtsi` 将 GPU CPU 映射扩大到 `0x40000` 字节，并在寄存器索引乘以 4 前检查边界。旧测试自行提供 `0x40000`，漏掉了生产声明中的差异；修订后测试直接读取生产声明并对照固定设备树。相同内核的阶段 16 对照通过，阶段 17 仍引起整机自动复位。逐次 MMIO 日志确认 GPU 配置、1560 字节 powerup 表和 SQE／AQE 基址写入、读回均完成。

提交 `9134960` 将 kind 5 安全缓冲的 IOVA 移到 `0xf0000000` 起始的专用范围，与 GPU trusted base 一致；普通缓冲继续从 `0x10000000` 分配。软件遍历覆盖根索引 3、跨 2 MiB 边界及高地址应答，安全页移交后通过不可访问的主机映射检查 CPU 访问限制。该内核在真机继续收到 START ACK，阶段 17 仍复位。

提交 `a473130` 按厂商 MMIO 顺序为 GPU 和本文件内的 GMU／AO 写入增加前置屏障、读取增加后置屏障；直接与诊断分支均覆盖，边界检查继续先于 MMIO。4 KiB／16 KiB GPU 模型及 8 项缺失或顺序错误的屏障变异检查通过；真机阶段 17 仍复位，本轮只来得及取到启动日志。

固定 MiCode 的普通 GPU 初始化在默认 TTBR0 配置后调用 `qcom_scm_kgsl_set_smmu_aperture`。提交 `ae92c8a` 增加该前置操作：CB0 启用后调用 SMC `0x42000c1b`，参数为 `0xffff0000` 和三个 `0xffffffff`；transport 失败保留页表和映射并停止后续 GPU 操作，重复启用不重发。测试编译固定 MiCode 的 descriptor 和编码，与生产 helper 比较；4 KiB／16 KiB 及 9 项变异检查通过。

对应内核 `out/handoff-mach-scm-aperture` 为 19215576 字节，SHA-256 `cc89fff2c2dbfa435c0ef06a0e9d315b9ade6d86a08882effe32f1425f317962`；阶段 17 payload 为 `out/handoff-scm-aperture-s17.bin`，28435976 字节，SHA-256 `8da16507c98cec137da53c6fde07dd79c65f9d9ef37944d0c1c5de4e950b6215`。新编译目录与该提交重新应用得到的 5132 个源文件一致。

该轮 SMC 返回 `0`、answer `0`，CB0 ACTLR 读值为 `0x3`。RAW131 的 11 个字数据及生产者索引 `344` 均已写入，随后自动复位，日志未记录到 doorbell 写入返回。索引发布后有 1000 毫秒诊断暂停；GMU 可能在暂停期间读取队列，实际复位指令及原因尚未确定。USB 失联后约 26.7 秒重新枚举，v7 返回 `idle`。HFI ACK、CP 初始化、scratch 和 shader 均尚未通过。

## 8. 标准 context 与资源生命周期

提交 `cc0c7ec` 增加阶段 22 的标准 HWSCHED context：HFI 128 注册、134 配置、GMU context queue 提交与 EOP 内存完成检查；HFI 133 仅作为通知。单 context、单笔在途，IB 列表最多 82 项。队列与 timestamp 通过非缓存别名访问，失败保留资源至冷复位，注销成功后保留分配并延续 timestamp。离线 context、HFI、HWSCHED、memory 和服务检查通过。阶段 22 尚未上机。

提交 `9771edf`、`4f3cc11` 调整现有 IOKit／legacy 服务生命周期：映射提交、TLB 同步或解除映射失败后保留 IOVA 和 descriptor，故障后停止提交；MiniIOSurface 绘制完成标记要求实际 fence。23 个生命周期场景覆盖 4 KiB／16 KiB，8 项变异被发现，ASan／UBSan 检查通过。拆分后的新文件均低于 1000 行，现有大文件净减少。A830 对外 BO 映射、C ABI 分派及服务发布仍待实现。

## 9. RAW NOP 与 Android 对照

提交 `57bbcff` 增加 `adreno8_raw_nop=1/2` 诊断：分别发送 2 个或 10 个 PM4 字的 NOP，配置与微码基址沿用阶段 17；运行结束后停止，始终不进入 CP_READY。固定厂商定义确认 NOP 为 `{0x70100001,0}`，厂商 RAW 入口也用于通用 PM4。厂商冷启动首条 RAW 为 CP_INIT，尚无其支持 pre-init NOP 的实测。两个模式和非法参数的离线检查通过，原 GPU 模型及屏障变异检查通过。

内核 `out/handoff-mach-raw-nop` 为 19215576 字节，SHA-256 `83618e31c946c9abe6e2cb20a044b9398db18b4d064aa0baedfd251912381adb`。NOP1 payload 为 `out/handoff-raw-nop-s17-nop1.bin`，28435992 字节，SHA-256 `13ea3ea669a19a2b8f72ac32066ce17cc44dd540c198f54002130a4cb3e13d56`。真机日志记录到 RAW131 的 3 个字数据和生产者索引 `336` 发布，随后自动复位，仍未记录到 doorbell 返回。A 槽重试耗尽后启动 B 槽 Android，约 30.3 秒重新枚举 ADB；本轮没有发送复位命令。

Android ADB 为 root。PMIC 启动缓存记录 PS_HOLD、WARM_RESET 和 HARD_RESET，没有 WATCHDOG 字段；hypervisor 的 S2 Fault Counter 为 0，pstore 为空。TZ general／reset／boot／log 输出加密内容，现有诊断无法确定 XNU 复位原因。读取日志设置主机等待上限，未清空日志。

Android 的 GMU、SQE、AQE 文件长度和 SHA-256 与当前实验输入完全一致；实际 zap 文件 SHA-256 为 `297318258cb36e5cf6205332a424735c0f9c8f4ba3f9382a6b1d409431b136f7`，与现有小根盘不同，后续 zap 认证应使用本机文件。阶段 17 尚未加载 zap。

运行中的设备树为 `qcom,adreno-gpu-gen8-0-1`、chip ID `0x44050001`、型号 `Adreno830v2`，各频率档组最低为 160 MHz、level `0x32`、DDR 索引 2。此前 125 MHz 来自静态参考设备树，当前驱动仍使用该实验点。固定厂商 gen8_0_0／gen8_0_1 catalog 除 revision 和 compatible 外字段一致，寄存器表、GMEM、HBB 及固件选择相同。后续对外 CHIP_ID 必须按实际设备更新。

为读取已有 GPU 分配元数据临时挂载 debugfs，`globals` 的厂商实现仅遍历软件记录；微码属性为只读、非特权，powerup 表为特权可写，与当前实现一致。地址被内核隐藏，无法用该输出比较实际 IOVA。读取完成后卸载 debugfs。

## 10. GMU revision 修订

厂商 GMU 启动前将 `ADRENO_GMU_REV(ADRENO_GPUREV(adreno_dev))` 写入 GENERAL_10；gen8_0_1 的编码为 `0x08000100`。提交 `d6e7015` 修正了原固定 `0x08000000`，测试同时要求该写入先于 CM3 解除复位，4 KiB／16 KiB 通过。

内核 `out/handoff-mach-gpu-revision` 为 19215576 字节，SHA-256 `fabd535011c2f72202acc46cbbbf92bdaa59f80ec6463dd6d090fbd32e4367a7`；阶段 17 payload 为 `out/handoff-gpu-revision-s17.bin`，28435976 字节，SHA-256 `85f8306a0301ba9e16e9897bf09da0129fc5a211db997182796eeaa7498b37a9`。该轮仅修订 revision，仍使用原 125 MHz 实验点。日志再次记录到 RAW131 数据及生产者索引 `344` 发布后复位；约 26.2 秒重新枚举并返回 v7 `idle`。

## 11. 实际最低频率与 fault stall 诊断

提交 `189ba55` 将已有单一实验点改为运行设备树六个频率档组共有的 160 MHz／level `0x32`，DDR 索引仍为 2；未增加其他频率。HFI 测试直接读取生产频率表并检查 ARC 传参、kHz 编码与 DCVS 索引；五项变异均被发现。该值的来源为本轮实际设备树，固定公开参考中的 125 MHz 配置继续保留为历史输入。

内核 `out/handoff-mach-min160` 为 19215576 字节，SHA-256 `f03b75d485c55fe1fd30cdb2fe202c4c65186ad2f805197ea9b4dfd5e1ec57ca`；payload 为 `out/handoff-min160-s17.bin`，28435976 字节，SHA-256 `0774ac4b1588b20d40b3fc7833422b531dde03e462174d491557b37bbb34b89c`。真机确认 160 MHz、vote `0x320201`，START 和 DCVS ACK 均通过；阶段 17 再次在 RAW131 索引 `344` 发布后复位，约 26.1 秒返回 v7 `idle`。

提交 `2446329` 增加 `adreno8_gpu_stall=1` 诊断，仅将 GPU CB0／CB3 的 SCTLR 从 `0x27` 改为 `0xa7`，GMU CB2 保持 `0x27`，CFIE 保持清零。3a、3b 仍要求完整值严格读回，故障检查、停止提交及资源保留继续生效。4 KiB／16 KiB 的 SMMU、translation、handoff、service 及相关回归通过；service 覆盖 21 场景与 stall 开关，新增控制位变异及路由前后校验变异均被发现。真机阶段 17 已确认 CB0／CB3 的 `0xa7` 读回，RAW131 数据及生产者索引 `344` 发布后仍自动复位，约 26.14 秒返回 v7 `idle`，没有取得 HFI ACK 或故障寄存器报告。内核 `out/handoff-mach-gpu-stall` 为 19215648 字节，SHA-256 `837895617ad88c37e3c9fb5b35e96a57fd6f7ef8ad2228925803eea0ba7736e0`；payload `out/handoff-gpu-stall-s17-stall.bin` 为 28436056 字节，SHA-256 `5ace4666adff358a5e3aac4f85d4accbca313c199e3c12df66ab7aa2d05bfe76`。

## 12. 后续对照与启动前提

提交 `0b7744e` 增加 `adreno8_raw_nop=3`：完成 OOB、寄存器和 SQE／AQE 基址配置后不发布 RAW，每 100 毫秒检查一次状态，共 100 次，再停止并保留资源。该实验用于区分配置后的延迟复位和 RAW 发布后的复位；主机测试确认零 RAW 调用、100 次等待，以及未进入 CP_READY。真机已完成 10 秒检查，打印 `CP setup-only diagnostic remained accessible for 10 seconds; no RAW published`，随后按设计停止并保留资源；主机 USB reboot 成功，17.73 秒返回 v7 `idle`。该轮没有自动复位。

对应内核 `out/handoff-mach-cp-setup` 为 19215648 字节，SHA-256 `b1ff8b9f4282ae19c5d9bb4f60b2b50f60ac92d6190ab27c29f5f80122daff97`；payload `out/handoff-cp-setup-s17-nop3.bin` 为 28436056 字节，SHA-256 `99680e29a0a9db166157a8ddc3102046fb58bdf2c3b099df80975454fbee051e`。

厂商在 probe 阶段配置默认 GPU 页表并设置 SCM aperture，早于 HWSCHED START；原实现到阶段 16 才配置 CB0。这项时序差异正在单独检查。HFI 的 CSW_SMMU_INFO 为 kind 3，固定 host 源码未发现额外填入 magic／TTBR0 的操作；暂不修改该缓冲内容。

时钟也有明确差异：当前 GMU 和 HUB 保留晶振，HUB 分频后的 AHB 更低；厂商在加载固件前设置 GMU 650 MHz，START 后降为 500 MHz，HUB 为 200 MHz。固定 MiCode 的时钟实现位于 `gpucc-sun.c`；当前 PLL 读值没有有效 L 且未运行，现有 `adreno8_gmuclk=1` 只切换父时钟，缺少配置和启用 PLL 的步骤。HFI 性能表只提供参数，无法完成主机的时钟配置；复位是否由时钟前提造成仍待验证。

## 13. GPU 内存总线时钟调查

实际 GPU 与 GMU 设备树均引用 GCC ID `0x22` 的 `gcc_gpu_gemnoc_gfx_clk`；固定 `gcc-sun.c` 将其 enable／halt 配置为 `0x71010`，enable bit 0、HWCG bit 1、`BRANCH_HALT_VOTED`。当前实现只处理 GCC `0x71150` 的 DDRSS 分支和 GPUCC `0x90f4` 的 MEMNOC 分支，缺少 GCC GEMNOC 分支；寄存器写入对照稳定、首次 RAW 后复位与这一调查方向相符，实际继承状态尚未读取。

通过三次普通 USB 重启回到 B 槽 Android，读取实际 GCC／GMU／GPUCC／RSC 设备树。GCC 为 `qcom,sun-gcc`，节点和真实设备树目录中均未发现 `protected-clocks` 属性。Android 的 debugfs 中存在 GCC GEMNOC 分支元数据节点，空闲期间 enable／prepare 计数均为 0；该计数没有读取 XNU 的寄存器状态。临时 debugfs 已卸载，随后通过 ADB／LK 恢复 A 槽 v7 `idle`，期间未重写引导镜像。

## 14. 默认 CB0 提前配置对照

提交 `45fafb7` 将普通 CB0 和 SCM aperture 配置移到 HWSCHED START 之前，与厂商默认页表初始化顺序一致；阶段 16 改为只读校验，检查原有寄存器、SID0 路由、完整页表和 FSR，不重复 SCM、ATOS 或寄存器写入。CB0 已启用后，START 中的普通内存分配必须完成页表清理和 TLBSYNC 才回复。失败关闭分配与 HFI 服务并保留资源。安全页表继续独立移交。

主机检查通过：4 个调用顺序变异，4 KiB／16 KiB 与 stall 开关组合中的 21 个 mode 4 场景、17 个只读拒绝场景，以及 START 普通分配期间的 TLB 超时保留检查；此前 SMMU、memory、service 和 aperture 回归也已通过。独立审查未发现生产阻断项。

真机 START 应答与阶段 16 校验通过，阶段 17 再次在 RAW131 生产者索引 `344` 发布后自动复位，约 26.03 秒重新枚举并返回 v7 `idle`。该修改尚未使 CP 初始化完成。内核 `out/handoff-mach-early-cb0` 为 19216032 字节，SHA-256 `a49bc4eed948820cb9a2c040cc02f474f1b262997ca2031852fb2107e1b786b9`；payload `out/handoff-early-cb0-s17.bin` 为 28436424 字节，SHA-256 `87e4a1e74824bd8d13431d94254a689de7420499ddc8fb6855ffb97ebb91aa9b`。

## 15. GCC GEMNOC 使能与继承状态

提交 `58fe8d2` 在步骤 5 为 GCC GEMNOC 置 enable bit 0，保留 HWCG 和其他共享位；HWCG 为 1 时沿用厂商规则跳过 halt 等待，其他状态接受 CLK_OFF 为 0 或 NOC_FSM 为 ON，最多等待 200 微秒。读回失败或超时停止后续配置，已生效的投票保留到复位。主机配置测试和 HFI 回归通过，8 项变异被发现。

真机首次读回 `0x08000003`，enable 和 HWCG 在本轮操作前已置位，未发生 enable 位的状态变化。START 和阶段 16 通过，RAW131 索引 `344` 发布后仍自动复位，约 26.14 秒返回 v7 `idle`。本轮确认该分支继承了使能状态，后续继续调查其他启动前提。内核 `out/handoff-mach-gemnoc` 为 19216032 字节，SHA-256 `a15cf8f4520fee4fe03c194cb02a3871d312a7eb175803bf492ddf373baff034`；payload `out/handoff-gemnoc-s17.bin` 为 28436424 字节，SHA-256 `e60407b21f6c080ff3730d22e951b0adbbbe2b4aa63d25eca15605eb3161854b`。

## 16. Apps RSC 只读检查

提交 `6c087cc` 在步骤 1 读取实际设备树的 Apps DRV2（`0x16520000`、长度 `0x10000`），先核对 ID、solver 和 TCS 配置，再按版本读取八个 TCS 及已使能命令。该检查没有 MMIO 写入。主机 ASan／UBSan 检查覆盖 v2／v3 偏移、使能命令、未知版本与数量拒绝；独立审查和差异检查通过。

真机读到 ID `0x30800`（3.8）、solver config `0x04010100`（bit 24 为 0）、parent/child config `0x800c8104`（DRV2 八个 TCS、每个 16 条命令）；IRQ enable 为 1、status 为 0。TCS0 保留七条 BCM 请求，TCS1／2 的 wait、enable 为 0、status 为 1，sleep／wake／fast 的 enable 为 0。该快照确认了当前寄存器状态；已使能命令无法完整还原 ARC 的继承票值。现有触摸初始化会使用同一 DRV2 的 TCS0，后续写入还需处理共享寄存器的并发。

该轮只运行到步骤 2，未配置电源投票、PLL 或 SMMU。步骤 1／2 通过，主机 USB reboot 后约 16.69 秒返回 v7 `idle`。内核 `out/handoff-mach-rsc-read` 为 19216120 字节，SHA-256 `40b350789d742a1a2bc673ca08929c016895e088071f5c77f8547c3d6a9db484`；payload `out/handoff-rsc-read-s2.bin` 为 28436520 字节，SHA-256 `bff90b48db991a13522eccc8f443fd5d3ae1f40bfa220b261a5727830665cdab`。

## 17. 实际驱动二进制与 HFI 布局

通过四次普通 USB 重启进入 B 槽 Android，读取实际 `/vendor_dlkm/lib/modules/msm_kgsl.ko`，主机文件与设备端 SHA-256 一致：3214896 字节，SHA-256 `14aea73aa60814273a51f8e145e3b491471600466ddf6f42b7c45e1716b2bfd7`，ELF build-id `3fa59e049e38ef50ed5e9b0d32866bf1d798e224`。该文件保留符号，已用 idalib 定向分析；原始文件与分析结果保存在忽略目录。随后通过 ADB／LK 恢复已有 v7 `idle`，没有改写启动镜像。

实际 `gen8_hwsched_hfi_init`（模块地址 `0xd9334`）与固定厂商源码均将 840 字节的 HFI 表对齐到 16 字节，再接三个 4096 字节队列，起点为 `0x350`、`0x1350`、`0x2350`；原实现从 `0x1000`、`0x2000`、`0x3000` 开始。提交 `4361a43` 统一 GMU 地址和 CPU view 的偏移，并只为 HFI 使用连续物理分配与完整缓冲的单一 uncached view，保证队列跨页访问的映射前提。主机测试编译固定厂商的原始结构与初始化函数，逐字节对比生产表，覆盖 4 KiB／16 KiB、分配和映射失败、RAW padding 与 ring wrap；6 项变异在两种页大小下均被发现。

实际模块的 CP 初始化发送 44 字节 RAW131，成功并 idle 后才加载 zap；gen8_0_0 和 gen8_0_1 的 core 配置除 revision 与 compatible 字符串外相同。本轮修订后 START 与阶段 16 通过，阶段 17 仍在 RAW131 索引 `344` 发布后自动复位，约 26.12 秒返回 v7 `idle`，CP ACK 尚未取得。

内核 `out/handoff-mach-hfi-layout` 为 19216120 字节，SHA-256 `4d35b7dbb2f31c221746dc9810bb95798a9fc17d08cbfffd79b1758e3fca9249`；payload `out/handoff-hfi-layout-s17.bin` 为 28436520 字节，SHA-256 `1dc685e1f73f7cabffa53b8eca3ffd8b2244280ad48a86365fc60afd8890ec8c`。

## 18. ARC 继承票值读取

Qualcomm 的上游 `rpmh_read()` 返回指定资源的 HLOS／DRV2 请求值；其他 DRV 的请求由硬件另行聚合，见[原始说明](https://lkml.iu.edu/2510.3/03947.html)。固定上游提交 [`edbafe65`](https://git.kernel.org/linus/edbafe65eef2b58625db1e113fbbfb1fe10c0291) 的 ACTIVE read 协议为响应请求置位、WRITE 清零，不写 CMD_DATA，完成后读取 CMD_RESP_DATA。本机 v3.8 使用八字节长度。

提交 `d65b5c9` 增加 `adreno8_arc_read=1` 单次 CX 诊断，要求显式 `touchscreen=0`，使用空闲 TCS2。首次寄存器写入前设置冷复位要求，完成前不读取响应；超时、状态不确定或读回失败保留 TCS 和 IRQ 状态。成功后只清本次 IRQ，恢复初始 CONTROL 允许位，并从当前 IRQ_ENABLE 中移除本次新增位。48 个主机场景通过 ASan／UBSan，16 个变异被发现，独立检查通过。

真机读到 CMD_STATUS `0x10101`、完成 STATUS 1、IRQ status 4，CX 响应为 selector 0，对应 CMD DB level 0。完成回收后 TCS2 enable 为 0、CONTROL `0x10000`，IRQ status 为 0、enable 恢复为 1；步骤 2 通过，USB reboot 后约 16.79 秒返回 v7 `idle`。该值只描述 DRV2 的请求，当前跨 DRV 的实际电压仍由硬件聚合。本轮未写电压或 PLL。

内核 `out/handoff-mach-arc-read` 为 19233040 字节，SHA-256 `230d42b0bfe662e177a1772c95e0ce489c46acd456efdf599278e442d6cf953e`；payload `out/handoff-arc-read-s2.bin` 为 28453464 字节，SHA-256 `af099bc3ea8147887644e0885f15ffd5d7e6007a95dd8ba01d7d9031c9e44ebb`。

提交 `01575e5` 将诊断扩展为依次读取 CX、MX，前一项完成并恢复 TCS2 后才开始下一项；失败立即停止。78 个主机场景及 18 个变异检查通过。真机两项均返回 selector 0、level 0；阶段 2 通过，USB reboot 后约 17.71 秒返回 v7 `idle`。内核 `out/handoff-mach-arc-read-both` 为 19233360 字节，SHA-256 `d17831890ded380a7085bb511e1fecb8b0fc0f325f6d50782829b87245c7d3b1`；payload `out/handoff-arc-read-both-s2.bin` 为 28453784 字节，SHA-256 `1b9133d18065969379e61a9f2b9adf92b6e16802a833c94191a2f584aa1d22e0`。

## 19. GMU 虚拟寄存器与 trace

实际驱动在启动 CM3 前无条件分配 GMU 虚拟寄存器区（VRB）和 trace 内存，将 VRB 地址写入 GENERAL11。提交 `3eb09e0` 按该布局分配 4096 字节 VRB、16384 字节 trace，初始化 48 字节 trace header，完成缓存维护后才发布 VRB 地址。两种页大小及 7 项变异检查通过；固件、HFI 布局与初始化顺序回归通过。

真机日志确认 VRB `0x6000a000`、trace `0x6000b000`，GENERAL11 读回为 `0x6000a000`；START 与阶段 16 通过。阶段 17 仍在 RAW131 producer `344` 发布后自动复位，约 26.09 秒返回 v7 `idle`。本轮未取得 CP ACK。

内核 `out/handoff-mach-gmu-vrb` 为 19233240 字节，SHA-256 `fd912f6698e50feb3d4da1e0fabda5e25e79a912098d35c44124910a1c2764d5`；payload `out/handoff-gmu-vrb-s17.bin` 为 28453640 字节，SHA-256 `f29529e9a8c082775a24a8c0fb4c33cdca4781f09864ca94dfce9724daf5749b`。

## 20. A830 用户态接口准备

提交 `31979ad` 将既有 RedwoodGPU C ABI 按固定平台分派到 A830 BO 和标准 HWSCHED context。外部 IOVA 占用记录在现有 CB0 PTE 的软件位中，解除映射前等待最新 EOP 与 GPU idle，TLB 同步失败后关闭提交并保留描述符及内存。阶段 23 要求标准 context 自测成功，再启用 BO 并确认 IOService 已同步注册。

A830 提交入口校验 82 个 IB 上限、20 位 dword 长度、32 位地址范围和已实现 flags；未实现的外部同步与预抢占队列请求返回错误。GPU 计时 ioctl 返回 Unsupported。主机检查覆盖 16 项分派、两种页大小的 BO 与描述符生命周期、提交边界、注册失败清理、持锁和停止顺序；独立审查发现的同步过滤、legacy 注册失败回收和锁外 HFI 轮询均已修正。该提交 XNU 构建成功，全部 5139 个构建源文件与固定 Apple 源码及本次补丁展开结果一致；内核 `out/handoff-mach-a830-service` 为 19253816 字节，SHA-256 `fc0453dcd6c1f8e8dee9bb674df420b6899916dc104da2e86255c45e75935ae3`。阶段 23 真机验证待完成。

## 21. 本机 zap 固件准备

实际 Android 的 `gen80000_zap.mbn` 为 12088 字节，SHA-256 `297318258cb36e5cf6205332a424735c0f9c8f4ba3f9382a6b1d409431b136f7`，与旧小根盘中的文件不同。保留原根盘，生成 `out/handoff-ui-device-zap.apfs`（9355264 字节，SHA-256 `64b383623248bb447f83e4f20729be01b3c4f084bab44497b9884becca943543`）；旧根盘与来源目录的全部文件及链接内容一致，新目录仅替换该 zap 文件。新镜像经独立 APFS reader 核对全部文件与链接，并经 7-Zip 提取核对文件内容。生产 MBN 解析与 PAS 顺序主机测试使用本机文件，在两种页大小下通过。该根盘尚未用于真机 PAS 认证。

## 22. 主机电源票与 GMU／HUB 时钟

提交 `0eaa5e0` 增加固定 Apps DRV2 的 ACTIVE CX／MX 请求；仅 `adreno8_gmuclk=1` 启用，要求显式 `touchscreen=0 wfi=0 wfe_mode=0`，并确认 sleep／wake／fast TCS 为空。该流程读取两项响应及 CMD DB 表，按继承值与 level 128 所需 selector 的较大值请求，写后再次读取；不一致即停止，后续 PLL 不执行。139 个资源场景、15 项变异、82 个读取场景与 18 项变异通过，独立复核通过。

提交 `0813b2f` 按固定 MiCode Sun 时钟源码实现独立 GPU PLL0、共享 GCC GPLL0 输出与两路 RCG。先检查继承源，再接通父时钟，配置 GMU 650／HUB 200 MHz 后才启用 consumer 分支；START ACK 后将 GMU 调整到 500 MHz，继续保留电源票。未知继承源、未覆盖的校准字段、LOCK／ACK／UPDATE 失败均停止并保留冷复位要求。生产 C 主机测试、14 项时钟变异、3 项 START 接入变异及相关回归通过。XNU 构建成功，5141 个展开源文件全量核对一致；内核 `out/handoff-mach-gmu-clock` 为 19255184 字节，SHA-256 `6e41dcdeb55abd3cb16bf0286de67732e62db81f53702b75f64fe92cce682c03`。

首轮阶段 5 读到 CX、MX 响应 0；CX ACTIVE write 的 MSGID `0x10108`、地址 `0x30000`、DATA 3、WAIT 1 均读回一致，请求完成 IRQ 4、CMD_STATUS `0x10101`、STATUS 1，清理完成。随后读取同一资源，CMD_RESP_DATA 仍为 0，与请求 3 不符，准备函数立即停止，MX 写入、PLL 和 RCG 配置均未执行。USB reboot 后约 17.75 秒返回 v7 `idle`。此前读取响应为 0 的结果仍成立；本机 ARC 读回值与当前票值的关系需要进一步验证，初始响应 0 尚不足以确认继承票值。

本轮 payload `out/handoff-gmu-clock-s5.bin` 为 28475624 字节，SHA-256 `b94c499df63e81c9178c3274af4e045b4db449bc55a99d95d02936b2edb54134`。原始请求顺序以日志为准；相同命令及响应会重复出现，分析仅合并相邻的双路日志重复行，全局去重会丢失写后读取的上下文。

提交 `b16fead` 只将 ARC 事务改到空闲 ACTIVE TCS1，按 v3 固定偏移 `0xfc0..0xfe4` 与 IRQ bit 1，保留三个 ACTIVE 的空闲检查及原有协议、清理和失败条件。139 个资源场景／17 项变异、82 个读取场景／22 项变异通过，独立复核与 XNU 构建通过。真机仍读到 CX、MX 响应 0，CX write 3 完成后读取 0，阶段 5 停止；MX 写、PLL／RCG 未执行，约 17.75 秒经 USB reboot 返回 v7 `idle`。该结果未支持 ACTIVE 槽位差异的解释。

内核 `out/handoff-mach-arc-tcs1` 为 19255184 字节，SHA-256 `de876faa549edb21fcfc7a207ed2dec8358e58cffb9842f56dd33d0f77c445ab`；payload `out/handoff-arc-tcs1-s5.bin` 为 28475624 字节，SHA-256 `181b18b5f2e4b764df2a3dd5e30a7d9ac49f88c0011919c34fee442b898c40b7`。

## 23. 最高 corner 的阶段 5 诊断

固定 MiCode 版本的 `rpmh-regulator.c` 用同步 `rpmh_write` 的完成应答确认升压请求，`get_voltage_sel` 返回已缓存的请求值；该流程不发送 ARC READ。`rpmhpd.c` 在 `sync_state` 之前使用最高合法 selector，该文件的匹配表未列出 Sun，此处仅参考相同协议的启动策略。本机设备树中 CX／MX 主节点允许 `LEVEL_MAX`，CMD DB 的最高合法请求分别为 CX selector 10／level 480、MX selector 9／level 448。

提交 `09778fe` 增加 `adreno8_gmuclk=2`，复用原 ACTIVE 事务，只允许 `adreno8=5`、完整执行前五阶段且无前序 ARC READ；`only`／`skip` 组合在任何阶段执行前停止。两项地址、完整 level 表、AUX 长度和尾部零填充全部匹配后，才依次发出最高合法 WRITE。每笔请求检查新完成 IRQ、CMD_STATUS、TCS STATUS 和清理结果；失败后保留资源至冷复位。该模式拒绝 START。原模式 1 的读取与写后确认保留。宿主检查通过最高请求 84 场景／9 项变异、原 ACTIVE 139／17、ARC 读取 82／22、时钟 16 项变异及实际 `adreno8_init` 27 场景／3 项入口限制消融；独立审查通过。

XNU 构建成功，5141 个展开源文件全量一致。内核 `out/handoff-mach-arc-max-write` 为 19255288 字节，SHA-256 `711fd4b8669b18a3865ae59d7013c4098fa5206c73f098baaed97156680652a0`；payload `out/handoff-arc-max-write-s5.bin` 为 28475736 字节，SHA-256 `953b77e6b7fe5a96f2520dec29f5e62ecb041442858ca0741798b713cbd03ec2`。

真机 CX selector 10 和 MX selector 9 的 WRITE 均完成，MSGID `0x10108`、WAIT 1、IRQ 2、CMD_STATUS `0x10101`、STATUS 1，清理完成；未发送 ARC READ。随后 GPU PLL0 冷配置写 L `0x44440034`，读回 `0x00440034`，全字校验失败而停止。RUN、PLL LOCK 和 RCG 配置尚未执行。USB reboot 后约 20.88 秒重新枚举为 Android；A 槽重试恢复仍按操作手册执行。

该结果确认两项最高合法写请求的完成应答；物理电压尚未测量。厂商 PLL 频率与校准计算分别使用 L 的 15:0 和 23:16 位，24 位以上的写入读回差异需按本机字段范围处理，再继续 PLL／RCG 验证。

## 24. PLL 字段校验修订与阶段 5 通过

提交 `98b40e3` 保留厂商冷配置完整写值 `0x44440034`，仅该 L 寄存器读回校验低 24 位；其他寄存器仍按原 mask 验证，全 1 读数继续失败。校准前检查实际用于厂商计算的 23:16 位为 `0x44`，调频只修改低 16 位。高字节写入忽略及不可读两种模型复现旧实现停止，修后通过；时钟 19 项变异、实际 init 的 27 场景／3 项消融和独立复核均通过。高字节的完整硬件语义仍未确认。

该提交 XNU 构建成功，5141 个展开源文件一致。内核 `out/handoff-mach-pll-l-mask` 为 19255368 字节，SHA-256 `adfaa395fcd691fbf290878a9997e988cefc2e14885d2cf1a32fe333cce16875`；payload `out/handoff-pll-l-mask-s5.bin` 为 28475816 字节，SHA-256 `9ee6a7c4870e8820341154e779a9516aede69ecd0accbc39eff6f660199178ab`。

真机最高 CX10／MX9 WRITE 再次完成；GPU PLL0 校准和 RUN／LOCK 通过，L `0x00440043`、alpha `0xb555`，even divider 读回 `0x407`；共享 GCC GPLL0 USER `0x02000403`、L `0x1f`、alpha `0x4000`，HLOS vote 保持 `0x11`，GPU gate 从 `0x60257f` 改为 `0x60a57f`。GMU／HUB RCG 分别配置 `0x100201`／`0x100505`，UPDATE 完成，HUB divider 保持 1。consumer 分支检查完成，阶段 5 通过；约 16.68 秒经 USB reboot 返回 v7 `idle`。这些检查确认标称 GMU 650／HUB 200 MHz 对应的父时钟及配置，尚未使用独立频率计数器测量。

下一轮保留最高 CX／MX ACTIVE 请求，限定完整执行至阶段 17，检查完整时钟配置是否改变 CP 初始化后的复位。MiCode 时钟约束及固定 OnePlus GMU 启动顺序未要求在 HFI／CP 前降低这两项 host 请求；gfx／gmxc、DCVS、带宽和 GX 流程继续执行。触摸与 CPU 等待仍显式关闭，保持 `keep=1 return=0`，实验经冷复位结束。物理电压、长时功耗和温度、GMU slumber 与 CPU 休眠仍未验证。

## 25. 完整时钟与 RAW131 对照

提交 `51c09c1` 将最高合法请求诊断明确扩展到完整阶段 5 或 17，要求 `keep=1 return=0`，继续拒绝 `only`／`skip`。电源准备仅允许实际阶段 5；目标 17 的时钟切换仅允许阶段 14 的 START ACK 之后执行。最高请求 90 场景／11 项变异、原 ACTIVE 139／17、时钟 22 项变异、实际 init 58 场景／5 项消融通过，独立审查通过。该范围未包含阶段 18～23。

XNU 构建成功，5141 个源文件全量一致。内核 `out/handoff-mach-clock-cp17` 为 19255368 字节，SHA-256 `c93bc6d4c6c3dd1d5e872d9ecb6fe31f0c384366aff2eff9499b04659424f92c`；阶段 17 payload 为 28475816 字节，SHA-256 `10796a434169b65684399847a6dcc8ff8353f1ba00a4284e6640a66899ec0540`。

真机阶段 5 的 650／200 MHz 配置、START ACK 后 500／200 MHz 配置检查及阶段 15、16 均通过。阶段 17 仍在 RAW131 生产者索引 `344` 发布后自动复位，未取得 CP 初始化 ACK；约 26.10 秒重新枚举并返回 v7 `idle`。完整时钟配置与最高 CX／MX 写请求尚不足以解除该故障。

同内核只增加 `adreno8_raw_nop=3`，其 payload 为 28475832 字节，SHA-256 `d35eadeb06cc6af6e7bb2122aaa2573c81edd9b6ce1a3ae425045f84da2a22bf`。该轮执行全部 CP 配置及微码基址设置，十秒内电源、HFI、页表与 CP 故障检查持续可读，未发布 RAW，随后按诊断设计停止。USB reboot 约 17.76 秒恢复 v7 `idle`。该对照继续支持优先调查首次命令处理所需的配置、内存访问和固件条件；结果覆盖本次十秒观察窗口。

## 26. 电源依赖票高位修订

固定 Qualcomm `GEN8_DEP_VOTE_SET` 将 bits31:14 共十八位设为 1，本机 KGSL 的 `setup_gx_arc_votes` 在偏移 `0xdfcfc` 同样使用 `0xffffc000`。原 `adreno8_dep_vote` 使用 `0x3fff << 14`，缺少最高四位。提交 `bc3a141` 修订该常量；最低 160 MHz 的依赖票从 `0x0fffc2ff` 改为 `0xffffc2ff`。本机六组频率表在此档均无 CX dependency，低字节 `0xff` 与 MX selector 2 保持。已查 host 源码未说明最高四位各自的固件含义。

旧 HFI table 测试用固定偏移模拟票值计算，没有执行生产编码函数，GMU 频率数组也独立写成 200／500 MHz。修订后直接编译生产 `arc_vote`／`dep_vote`，使用本机 CMD DB 表和生产 GMU 数组，检查完整性能表及 `0xffffc2ff`。新用例复现旧编码失败；修后 HFI 两组测试及八项编码、序列化、GMU 输入变异通过，独立审查通过。

内核 `out/handoff-mach-dep-vote` 为 19255368 字节，SHA-256 `03bd87b93b213143615f5dece607a887c8f8ecebdd5941b8de41b2d9caee4923`；payload 为 28475816 字节，SHA-256 `a8f9fcd51b12c3922ee1bafa2f924c93f05027d18b98f1d5cf1bddc0a5641e98`。5141 个构建源文件一致。真机日志确认依赖票为 `0xffffc2ff`，RAW131 索引 `344` 发布后仍自动复位，约 26.17 秒返回 v7 `idle`。

此前还使用 `51c09c1` 原内核、仅将 `adreno8_pause` 改为 0 做对照，payload SHA-256 为 `b1583c98933e9fecd0d0b83b8a1ffef53fe4ce2ffa3d8a415745c0a29ae156d2`。该轮确认自动复位，但最后有效日志仅到阶段 14 的 kind 5 请求，后续未采全，具体触发点仍未知。该结果尚不能排除发布后诊断暂停的影响。

## 27. FEATURE_CTRL 四字 ACK 校验

本机 KGSL 的 `gen8_hfi_send_generic_req_v5` 与固定 Qualcomm 源码均检查第四字 error，error 为 0 后才返回第三字 data；HWSCHED 启动调用者要求返回值为 0。当前驱动只接受 HFI v2.6.1+，适用该四字协议。原 ACK 处理只检查第三字，可能接受 `data=0,error!=0`。

提交 `b81835d` 仅对已使用的消息 11 要求至少四字、data／error 均为 0，并记录两字段；普通 ACK、START／RAW／context 的异步状态契约保持。新模型先复现旧实现误接受 `error=6`，修后七项 ACK 消融及原八项票值变异通过；HWSCHED、context、两种页大小的 handoff／service 回归及独立审查通过。

内核 `out/handoff-mach-feature-ack` 为 19255368 字节，SHA-256 `ac83af667edea345b6aefd7cd933d61aa80c0ac7c11d04545a5300c3e64b848d`；payload 为 28475816 字节，SHA-256 `0809396f3a839caf8682b9f7873f8775b78aed4c7e8396adc3535e6a7797fb6f`。5141 个构建源文件一致。真机五个顺序发送的 FEATURE_CTRL 均取得 data 0／error 0 的 ACK，随后 START 通过，RAW131 索引 `344` 发布后仍复位；约 26.18 秒返回 v7 `idle`。日志保留十条双路输出，连续相同 ACK 需按原始次数核对，合并整段相同行会丢失请求次数。

## 28. RAW 发布与通知之间的暂停

实际 KGSL 及固定源码在 producer 写入后执行屏障，随后通知 GMU。原诊断在 producer 与 doorbell 之间执行 `adreno8_announce`，会按本轮参数暂停一秒。提交 `d9c871c` 将日志移到两次写入返回之后，保留发布前的暂停。宿主模型记录 producer 时刻，在 doorbell 检查经过时间未增加，并拒绝该区间的 announce；旧实现复现失败，修后两项时序消融及原有十五项编码／ACK 消融通过，独立审查通过。

内核 `out/handoff-mach-raw-doorbell` 为 19255368 字节，SHA-256 `b7d2c46c31727227bf74476075c48da1abb7b20ac7ca90faaffdf019599fc89e`；payload 为 28475816 字节，SHA-256 `51c7476fbe8f35d161929867b0294b307bce3b2b40f1381c63796e8ddd4881b7`。5141 个构建源文件一致。真机仍自动复位，最后采到 `RAW131 payload ready`，未取得新的 producer／doorbell 均已返回打印；无法据此区分两次写入的返回位置。约 30.34 秒枚举为 Android，随后按手册软件恢复已有 A 槽 loader。

## 29. 本机 TPL1 配置对照

本机 KGSL 的 gen8_0_0／gen8_0_1 catalog 均引用 `gen8_0_0_nonctxt_regs`，其中 `GEN8_TPL1_DBG_ECO_CNTL` 为 `0x10000000`；固定 OnePlus 表为 `0x10100000`，差 bit20。提交 `bf5e18a` 仅调整该寄存器值。测试新增必需的 `--kgsl-module`，先校验模块 SHA-256，再用 ELF 符号、重定位及表项位置核对原始输入；OnePlus 参考只替换这一个已确认的表项，其余表仍逐项比较。

旧常量在新参考下失败；修后 4 KiB／16 KiB 的生产启动模型均通过，在首次 RAW 前分别验证 MMIO 和已发布 powerup 副本中的 `0x10000000`。恢复 bit20、仅污染启动值、仅污染 powerup 三项变异在两种页大小下均被发现，原八项屏障变异保留；独立审查通过。

该提交 XNU 构建成功，5141 个源文件一致。内核 `out/handoff-mach-tpl1-catalog` 为 19255368 字节，SHA-256 `b5ed2027b37cd043729bfaa52c633325dd6ad0304710b5a44bd47ec9441c15e5`；payload 为 28475816 字节，SHA-256 `a96d3f8492631352c224181e97e24afbd0f0cfcea71b5c357e1dd563fd110c01`。真机 `0x3d2d800` 读回 `0x10000000`，随后仍自动复位；最后采到 RAW payload ready，未取得两次写返回的打印。约 26.11 秒恢复 v7 `idle`。

补充只读核对：实际全局 ucode 映射经 `kgsl_iommu_map_global` 调用同一最终 mapper，最终为 READ、允许 EXEC、非 PRIV，无隐藏 CACHE／SYS_CACHE 权限，与当前实现一致。厂商 TTBR1 高地址和当前 TTBR0 低地址仍有组织差异，尚未确认是启动限制。MEM_ALLOC descriptor 和 44 字节回包构造也与实际模块一致；原始整包未被完整采样，现有比较覆盖源码与解析后字段。

## 30. AHB 超时配置对照

实际 KGSL 的 gen8_0_1 catalog 使用 200 MHz HUB 和 3410 微秒 NOC 上限，`gen8_init` 在加载固件前给 CX_MISC 的五个 AHB 控制寄存器写入 `0x1b12`。低五位为 18，对应 2^19 个 HUB 周期，按该频率计算约 2621.44 微秒。寄存器物理范围为 `0x03d9e040..0x03d9e050`，在当前 CX_MISC 映射内偏移为 `0x40..0x50`。此前阶段 5 仅读取的 `12441e1` 实测五项均为 0，阶段完成，USB reboot 后约 17.77 秒恢复 v7 `idle`。

提交 `5c99f63` 先预读五项并拒绝全 1，确认 PLL／HUB 路径及全部 consumer branch 后，逐项写入并严格读回 `0x1b12`；写前要求保留资源至冷复位，失败立即停止。XO 路径保持只读，已匹配项保持原值。生产代码净增 12 行，无新增持久状态或接口；88 项 AHB 场景、10 项消融、相关 clock／HFI 回归及独立审查通过。

XNU 构建的 5141 个源文件一致。内核 `out/handoff-mach-ahb-timeout` 为 19255368 字节，SHA-256 `1b2590fb2912ec4c67c81f9190613862845b7090c4942a6bc4abe7ade6fb4155`；阶段 5 payload 为 28475816 字节，SHA-256 `7fcd72afe5fdf5536163cbb8fcff575aae026c768e672bf6387539407b62714d`；阶段 17 payload 同样大小，SHA-256 `8969d193d4d397ccf2284557cbb5c39a1f8ed06e8996819153d0b750987e1307`。

阶段 5 五项读回均为 `0x1b12`，阶段完成，USB reboot 后约 16.70 秒恢复 v7 `idle`。同内核阶段 17 最后有效日志仍为 `RAW131 payload ready`，未取得 producer／doorbell 返回打印、CP ACK 或后续 AHB 故障状态，随后 USB 请求失败并确认 loader 新启动。AHB 配置这一项变化尚不足以完成首条 CP 命令。

## 31. 恢复耗时的测量边界

`run-trace.py` 对任一 USB 调用失败均输出 `NATURAL_RESET_OR_USB_LOSS`。其 `reboot.json.seconds` 从失败调用返回后开始计时；该字段没有覆盖已阻塞的 USB 请求，也没有记录硬件复位开始时间。本记录前文自然恢复分支中的约 26～30 秒均沿用该字段；触发过程应按失联、随后确认新启动理解，实际复位来源尚未确认。主动 USB reboot 的计时同样单独保留。

例如本轮 AHB 阶段 17，首个失败的 `oem log` 从 run 后约 3.332 秒开始，约 6.507 秒后返回错误，再约 26.109 秒确认 v7 `idle`。这些时间不能用于确定 watchdog 或其他复位原因。后续诊断保留原始调用开始时间和持续时间，producer／屏障／doorbell 之间保持连续执行，新增状态采集先在可恢复停止路径验收。

## 32. 空 powerup list 对照

主线 A830 首次 CP_INIT 先于 powerup list 填充，新建 shmem 页的清零路径也已核对。厂商 HWSCHED 顺序为先填表，闭源 parser 对零计数的接受条件尚未确认。提交 `6cb0fc4` 增加仅允许完整阶段 17 的 `adreno8_empty_powerup=1`，要求 `keep=1 return=0` 且无 `only/skip/raw_nop`；默认行为保持。全部原配置完成后，仅清零并发布原 powerup 页，地址、权限及 CP_INIT 不变；发布失败不发送 RAW，ACK 和 idle 成功后也停止，继续保留 OOB 和全部资源。

4 KiB／16 KiB 的真实生产路径、十六项空表消融及原屏障／TPL1 变异通过，实际 init 118 场景、原五项及新增七项准入消融通过，独立复核通过。测试检查整页设备可见内容、原表先生成、其他缓冲内容和 16 KiB 分配尾部保持。生产代码净增 23 行，无新状态或接口。

内核 `out/handoff-mach-empty-powerup` 为 19255368 字节，SHA-256 `3f42da70ed0b1922d99ecf942dd7bcd94cf112a17597aa0b3322ced6ca13e945`；payload 为 28475832 字节，SHA-256 `21575a768feb18e3c4f62e194282f0c0f3d7575dd54e8a9388e172d169b76953`，5141 个构建输入一致。真机确认原 1560 字节表生成、同一 IOVA 的 4096 字节空页发布，最后仍为 RAW payload ready，随后 USB 请求失败。失败调用持续约 6.495 秒，再经过约 26.122 秒观察到 loader，状态为 `idle`；实际复位来源未知。空表这一项变化仍未取得 CP ACK。

下一轮采用[普通 HFI／直接 ring 冷启动诊断](../plan/2026-10-25-ordinary-ring-probe.md)，先限制到 CP_INIT 的消费、BR RPTR 和 idle，保持 HWSCHED 默认路径。

## 33. 普通 HFI 与直接 ring 首轮

提交 `5e63bb5` 实现[受限普通模式](../plan/2026-10-25-ordinary-ring-probe.md)。两种模式使用独立队列布局和 ready，普通模式拒绝 HWSCHED 资源请求并保持安全预检为 0；任何 HFI 失败后终止，恢复寄存器也无法继续发送。GPU 共用原分配、映射及寄存器访问，新增一个 32 KiB ring，使用独立 RW shadow 页及空 powerup 页，保持 HWCG 关闭。CP_INIT 消费、BR RPTR／shadow 和 idle 均通过后仍强制停止。

实际 C 在 4 KiB／16 KiB 下通过 ordinary 110 场景及 19 项消融，GPU 新增 26 项及原 27 项变异；实际 init 157 场景、clock／准入 44 项消融、双模式 START 顺序六项消融及既有 CB0、HWSCHED、context、service 回归成功。独立审查通过。新增状态仅包含模式选择和普通 START 生命周期，沿用原资源池，全部改动文件低于 1000 行。

XNU 构建的 5141 个输入一致。内核 `out/handoff-mach-ordinary-ring` 为 19256480 字节，SHA-256 `f8ae609ff9f6e160e8d841d24b4d7e328738d4d0049642a2991508fd5573889f`。首轮 payload 为 28476936 字节，SHA-256 `e034d956f8383a2d94013603eb24e80b0dd9e3cc773da2b4321b7f7a316ce260`，`pause=1000 fine=0`。最后采样仅包含通用启动打印，未取得 GPU 阶段日志，尚不能定位到 START、SQE 或 CP_INIT。首个失败 USB 调用约在 run 后 0.294 秒开始、持续 6.515 秒，之后约 26.022 秒确认 loader 新启动。

同内核第二轮仅改为 `pause=100 fine=1`，payload 大小相同，SHA-256 `3ef91dce5f270bb6e260caef5c76d084fdb36fb0513550fb1318e6b5b1c008b2`。日志确认 GENERAL11 为 0、普通 START ACK、GMU 500／HUB 200 MHz 配置及阶段 15／16，通过 ucode 基址和全部 ring 配置读回；最后有效日志为即将向 `0x03d02054` 写入 `CP_SQE_CNTL=1`。`adreno8_put` 在该打印后暂停 100 毫秒，再执行实际写入，因此最后一行尚不能证明该写入已执行。未取得下一次读取打印，未发布 CP_INIT。失联后约 30.345 秒观察到 B 槽 Android，随后软件恢复 A 槽已有 v7 并确认 `idle`；上述时间从失败调用返回后开始。

下一轮复用 setup-only 诊断，在普通模式完整配置及输入发布后、启用 SQE 前观察十秒，确认最后配置的稳定范围。ACTLR、页表访问与 SQE 取指前提继续核对，仍未确认失联原因。

## 34. SQE 启用前配置与 HALT 实读

提交 `0b45e55` 复用 `adreno8_raw_nop=3` 扩展普通模式的 setup-only 对照。仅放宽该组合的原始参数 3，其余严格准入条件保留。完整执行原配置、ucode 基址、三块输入整页发布和七项 ring 寄存器读回，再只读采样 GBIF／RBBM halt 与 ACK；任一全 1 立即停止。随后执行 100 个先等待、再检查 HFI／GPU 状态的周期，显式等待合计十秒，最后一个周期仍检查；结束后保留资源。全程未写 SQE、WPTR，也未发送 CP_INIT 或 RAW。

实际生产 C 在两种页大小下通过新增十一项 setup-only 消融，以及原 ring／empty／barrier／TPL1 检查，init／clock 157 场景和四十四项消融通过，独立复核通过。内核 `out/handoff-mach-ordinary-setup` 为 19256480 字节，SHA-256 `10e9a715ee562f973891d4fb919701f5cf4ff0aac47afe74729e03a8118a373e`；payload 为 28476952 字节，SHA-256 `8d5cef57c5ccc1003fdbd49fb882322f61c04cb545f2af2fe9280119668d6667`。5141 个构建输入一致。

真机使用 `pause=100 fine=1`，全部配置和 100 个健康周期通过，随后按设计停止；逐次寄存器暂停加长了观察窗口，总采样约 56.078 秒。实读 `0x03d0f114/118` 的 GBIF halt／ACK 为 `0x8/0x3`，`0x03d00028/2c` 的 RBBM halt／ACK 为 `0/0`。USB reboot 后约 17.752 秒重新确认 v7 `idle`。本轮支持 SQE 启用之前的这组配置在该窗口持续可读，SQE 写入及首次取指尚未验证。

固定主线在 OOB 后清零两项 halt 并读回；当前 stage 11 按厂商流程写入 GBIF halt bit3，此后没有对应主机清零。实际 KGSL 的 `gen8_start` 和固定厂商入口未发现同一主机清零步骤。下一轮仅对普通模式按主线解除两项 halt，严格读回，观察 SQE 启动位置是否改变；ACK 暂作原值记录，尚未把它的位值解释为本轮失联原因。

## 35. 普通模式解除 HALT 对照

提交 `c7a5661` 仅在普通模式 OOB 成功后，先清 aperture，再依主线顺序将 GBIF halt、RBBM halt 写为 0；每次写后执行屏障并严格读回 0。任一读回异常立即停止后续配置，资源和 OOB 保留。ACK 不写入，也不要求其变成 0。HWSCHED 保持原有流程。新增 halt 脚本复用已有生产 C 模型；原脚本执行段加标准主入口判断，防止加载模型时重复执行整套消融。

两种页大小的 halt 模型、六项新消融及原 GPU 检查通过，独立复核通过。内核 `out/handoff-mach-ordinary-unhalt` 为 19256480 字节，SHA-256 `fab6da85b37dda0a0dd0a3960a5b682e137d7937ecb7cfa6d7525dfd548358c2`；payload 为 28476936 字节，SHA-256 `37e0c6cdb651c03ec75749ef1f86a48cabd4ec06c9dd01488f98177011f3c425`。5141 个构建输入一致。

真机两项 halt 均读回 0，通过其余配置与 ring 寄存器读回，最后仍为 `CP_SQE_CNTL=1` 的写前打印。该打印之后仍有 100 毫秒暂停，尚无写入返回及后续读取记录，未发布 CP_INIT。首个失败 USB 调用持续约 6.477 秒，调用返回后约 26.129 秒确认 v7 新启动。解除 halt 这一项变化尚未改变最后可见位置。

厂商定义的 CLIENT／ARB halt 掩码为 bits0／1；bit3 的含义尚未确认。先前实读 `8/3` 仅保留原值，不据此判定失联原因。当前 CB0 ACTLR 继承读回 3，尚未写入；主线初值为 `0x303`，新增的 `[9:8]` 对应 DEEP prefetch，未找到首次 SQE 取指必须使用 DEEP 的契约。后续可在普通 CB0 关闭及路由 fault 期间做严格读回的单变量对照，其余 TCR、SHCFG、PTE 和上下文保持。

## 36. 普通 CB0 ACTLR 对照

提交 `f3fc4a1` 仅在普通模式配置 GPU context 0 期间写入主线使用的 `ACTLR=0x303`，增加的 `[9:8]` 为 DEEP prefetch。写前确认路由为 fault、SCTLR 已关闭，写后执行屏障并严格读回；后续活动上下文检查也要求该值。HWSCHED、GMU CB2 和安全 CB3 保持原流程。两种页大小的实际 C 模型及十三项消融通过，SMMU 回归和独立复核通过。

内核 `out/handoff-mach-ordinary-actlr` 为 19256480 字节，SHA-256 `36d6e51860f2d2319ec8ad208462d0339c773df37cbe84613d3635139c76f51f`；payload 为 28476936 字节，SHA-256 `82bfa684d6d0df9b29bfca17f5a1c59902ac98e439b9c125f8643e934aad649c`。5141 个构建输入一致。真机 ACTLR 写后读回 `0x303`，普通 START、阶段 15／16 和 ring 寄存器读回通过，最后仍为 SQE 启动写前打印，未发布 CP_INIT。首个失败 USB 调用持续约 6.451 秒，调用返回后约 26.118 秒确认 v7 `idle`；复位来源尚未确认。ACTLR 这一项变化尚未改变最后可见位置。

固定 MiCode 的 qsmmuv500 Adreno 路径在 GR0 `+0x10` 清 CACHE_LOCK bit26，该位控制 ACTLR 写权限。上述严格读回确认本轮 CB0 ACTLR 写入已经生效，尚未新增 ACR 访问。现有页表叶子均设 nG，TLBIASID 与 CB sync 覆盖当前映射；首次接管前的旧 global 项仍未确认，扩大失效范围还会影响同 VMID 的其他上下文，暂不修改。

同内核下一轮仅增加已有的 `adreno8_gpu_stall=1`，payload 为 28476952 字节，SHA-256 `de18ad272ffa15edc0b8a3a2ddf052e7ca877812d86bd480b99360a4fa01105d`。真机 CB0 SCTLR 严格读回 `0xa7`，GMU CB2 保持 `0x27`，ACTLR 仍为 `0x303`；普通 START 通过。最后成功采样到 ring 配置阶段，未采到 SQE 写前打印及新的 SMMU fault 状态。run 后约 25.747 秒开始的上传持续约 6.516 秒后失败，再约 26.110 秒确认 v7 `idle`。该参数仍未使本轮故障状态可读，无法据此确认故障类型。

stall 设置保留 CFRE，CFIE／HUPCF 为 0；现有失败路径只读 FSR／FAR，不清 FSR，也不写 RESUME。Arm SMMUv2 允许 stall 影响其他 context，当前结果不能支持 GMU／USB 必然可读的结论。后续控制访问对照将保持 SQE HALT，先验证其控制寄存器的写入和读回。

## 37. SQE HALT 控制访问与常开时钟采样

提交 `b295f97` 在普通模式复用 `raw_nop=2` 增加控制访问对照：输入发布及全部 ring 配置读回后，先读 SQE 控制继承值、拒绝全 1，再写入主线恢复路径使用的 3，执行屏障并严格读回，随后复用原十秒健康检查。原 `raw_nop=3` 的 SQE 零写入对照及 HWSCHED 的十字 NOP 保持。两种页大小的专项检查、十二项消融及原 GPU／init 检查通过，独立复核通过。没有新增启动参数、持久状态或接口。

同提交在阶段 2 仅读取小米 `gpucc-sun.c` probe 中要求常开的六项控制寄存器，任一全 1 即停止；该轮未启用这些时钟。MMIO 注释也按厂商原文限定为部分 Qualcomm 平台的 SMMU global 寄存器模拟，本机模拟范围仍未确认。内核 `out/handoff-mach-ordinary-sqe-halt` 为 19256480 字节，SHA-256 `61e1bae49e53b22fe9ebb0cf316b40c4c4caca672b8a09bc72afe0f8ef945277`；payload 为 28476952 字节，SHA-256 `b8b99d31989f43f7998d3e1a3e3b26eef55a448c2348601614600f0bde582061`。5141 个构建输入一致。

真机 SQE 控制继承值读回 0，随后最后采到写 3 前的打印，下一条读取记录未出现，未进入健康窗口，也未发布 CP_INIT。首个失败 USB 调用持续约 6.450 秒，调用返回后约 26.144 秒确认 v7 `idle`。当前采样仍无法确认实际写入的返回位置。

六项阶段 2 实读如下，bit0 为主机启用请求；其他位保持原始记录。

| 时钟 | GPUCC 偏移 | 实读 |
|---|---|---|
| cb | `0x93a4` | `0x08000001` |
| cxo_aon | `0x9008` | `0x08000000` |
| gx_ahb_ff | `0x9064` | `0x88000001` |
| rscc_hub_aon | `0x93a8` | `0x08000001` |
| rscc_xo_aon | `0x9004` | `0x08000001` |
| sleep | `0x90cc` | `0x88000001` |

其中 CXO_AON 的 bit0 为 0，当前阶段 5 尚未设置该项。固定小米 probe 为六项全部置 bit0，下一轮先对照这一配置差异，逐项保留其他位并确认请求读回；尚未将该差异判定为 SQE 故障原因。

## 38. 常开时钟请求的严格读回

提交 `9cc044c` 复用六项常量表，在已验证的 PLL／HUB 配置成功后、consumer 时钟与 GMU 启动前完整预读，任一全 1 即停止；仅为缺少 bit0 的项目写入原值 OR 1，并在屏障后要求非全 1 且 bit0 为 1。其他位保持，CLK_OFF 状态不作相等要求；默认 XO 路径继续只读。新模型覆盖两种 PLL 模式、全部 64 种启用组合、逐项读写失败及 bit31 变化，十四项运行断言消融、既有 config／clock／init 检查和独立复核通过。

内核 `out/handoff-mach-always-clock` 为 19256584 字节，SHA-256 `ce2cb174733ca144a10f1c293c7289c9d59c7cae5e2b4f678111960cef99c05a`；阶段 5 payload 为 28477032 字节，SHA-256 `2fee6b68474819f2e7ced997fe9ee2afb2c7726708d533d1e20a9dcf2c693be8`。5141 个构建输入一致。真机仅向 CXO_AON 写入 `0x08000001`，屏障后仍读回 `0x08000000`，按设计停止，后续 consumer、GMU 和 SQE 均未执行。USB reboot 后约 17.764 秒确认 v7 `idle`。

固定小米 probe 的 RMW 没有写后读取，现有源码与实际已保存 KGSL 模块无法解释该位的读回语义，该轮尚未取得实际 `gpucc_sun` 模块。当前不具备放宽成功条件的依据。提交 `b17112a` 撤回本候选的使能分支、专项测试及无消费者的 fixture 兼容改动，恢复 `b295f97` 的六项只读基线。下一轮先检查固件对象的逐页 PA 和完整 PTE 属性；扩大失效范围继续单独评估。

## 39. 普通固件对象的完整映射校验

提交 `be205eb` 复用原安全映射遍历，将私有函数改名为 `adreno8_translation_walk`。安全分支原有的 context 3／未启用条件保持；新增普通入口仅接受已启用的全局 GPU context 0。普通模式在全部参数准入之后、OOB 之前，分别校验 SQE／AQE 的完整分配范围和 READ／EXEC 权限。每个 4 KiB 页独立比较 `kvtophys(memory+offset)` 与完整 PTE，父表要求已登记的真实 PA 及精确描述符；不读取固件数据内容，不新增 MMIO、分配或状态。

两种页大小的实际 C 遍历、十六项映射消融、九项调用位置／参数消融、既有 GPU 六十四项消融及 memory／handoff／secure／service／SQE HALT 回归通过，独立复核通过。数据页设为 `PROT_NONE` 的场景仍能完成校验，移交后的安全分支继续提前拒绝。XNU 的 5141 个构建输入一致。内核 `out/handoff-mach-ordinary-object-walk` 为 19256456 字节，SHA-256 `64585fb9ea4252559f7f2d9007add2f7cdad14d1ed5dc75ff6c5400415936d4b`；payload 为 28476920 字节，SHA-256 `2a12a5dd98405afcb4e2b1a7e266e406e60b81ffbd32ddf6c16a557c50a00f5d`。

真机校验 SQE 的 114688 字节／28 页与 AQE 的 28672 字节／7 页通过，随后通过配置及 ring 读回，最后仍为 SQE 写 1 前的打印，未发布 CP_INIT。首个失败 USB 调用持续约 6.478 秒，调用返回后约 30.498 秒确认 `annibale` B 槽 Android。该结果覆盖 CPU 读取的页表及预期 PA 比较，GPU 首次取指仍未完成验收。

读取实际 B 槽 `vendor_boot` 的整分区哈希后，确认与本地分区备份解压内容一致，从该输入提取 GPUCC 模块；原备份保持。随后按手册经 Android、LK 恢复 A 槽已有 v7 并确认 `idle`。本轮没有重写启动镜像。

提取的 `gpucc-sun.ko` 为 49928 字节，SHA-256 `ee582a042c70aff13c6b31a2c82455365271aab19b072d538d44abb8b1c88249`。实际 probe 的反汇编和反编译均确认六项 RMW 与固定 MiCode 的次序、mask 1／value 1 一致，没有额外版本分支、返回值检查或写后读取。该模块核对仍未解释 CXO_AON bit0 的读回 0，候选继续保持撤回。

## 40. 早期非安全 TLB 失效对照

实际 `arm_smmu.ko` 已从同一份与 live B 槽匹配的 `vendor_boot` 备份提取，277624 字节，SHA-256 `18357e1dc13f2fe00b1a9ee1191f6594f340c909eb8d5bfbe100b5666ceeac31`。其全局 reset 使用 Hyp `+0x6c`、NSNH `+0x68`、global sync `+0x70` 与 status `+0x74`，WO 写值均为全 1，偏移与同步语义和固定 MiCode 一致。Adreno 实现没有额外 MMIO／reset 回调；完整 reset 另改写全部路由、context、FSR 和 SCR0，本诊断仅选择 NS 失效子集。

提交 `27372d1` 仅为普通模式在阶段 8 增加早期失效。先拒绝 IDR0／IDR1 全 1，确认三个自有 context 均未启用、CM3 reset 为 1、GX 两个 off 位均为 1，并要求全部可见 SMR 无有效项。预检通过后保留资源，执行写前屏障、一次 NSNH、屏障、一次 global sync，逐次读取 status；全 1 或 100 毫秒轮询预算耗尽即停止，bit0 清除后执行屏障。该预算无法中断阻塞的单次 MMIO；NSNH 可扩大失效范围，可见路由检查也无法确认 secure world 静止。HWSCHED 保持原路径，没有新增参数、可变状态或接口。

实际 C 在两种页大小下通过全部预检、非零 MMIO base、完整扫描、延迟完成／超时与失败保留场景，二十八项运行断言消融及相关 SMMU／secure／service 回归通过，独立复核通过。XNU 的 5141 个构建输入一致。内核 `out/handoff-mach-ordinary-early-tlb` 为 19256456 字节，SHA-256 `186420f80fbdf1f01fe278d56ede0023b8c136bea1655ea19d48c7360c378fce`；payload 为 28476920 字节，SHA-256 `a8d6127cd5b5ee98537f9b6b9de898c2d72728c0504504250aae05e10bc4bae6`。

真机 CM3 为 1、GX 为 3，24 项 SMR 全为 0，两项 WO 写入后取得 `global sync completed, status 0`。后续普通 START、35 页对象校验和配置继续通过；最后采到 ring 配置末尾，未取得 SQE 后续读取或 CP_INIT 发布记录。首个失败 USB 调用持续约 6.518 秒，调用返回后约 26.186 秒确认 v7 `idle`。本轮支持早期同步返回完成，扩大 NS 失效范围仍未使首条 CP 命令完成。

## 41. 普通模式首次启动的 HWCG 次序修正

重新核对固定主线 `a8xx_gpu.c` 的定义和全部调用：`a8xx_set_hwcg` 在第 199 行定义，唯一调用位于第 841 行，在首次 CP_INIT、zap 与 powerup 准备之后传入 true。先前普通模式复制了 false 分支，在首次 SQE 前改写六项控制；主线冷启动没有这一步。提交 `1782511` 修正普通分支，保留继承值，HWSCHED 配置保持原样；没有新增状态、参数或接口。

实际 C 的两种页大小检查及九项消融通过，原 GPU 六十四项消融和独立复核通过。XNU 的 5141 个构建输入一致。内核 `out/handoff-mach-ordinary-hwcg-inherited` 为 19256456 字节，SHA-256 `9ed631c61136781abfa5e49fa6699f76d2b0be2a04f3409e1d972cae40a85c50`；payload 为 28476920 字节，SHA-256 `f78bc4d55c9dcb650f4f90c8aefabd25ca198ec1dd0a9ef58d79181ff7026500`。

真机普通 START、早期 NS TLB 同步、35 页对象校验及 ring 配置继续通过，最后仍为 SQE 写 1 前的打印，未取得实际写入返回或 CP_INIT 发布记录。首个失败 USB 调用持续约 6.487 秒，调用返回后约 26.157 秒确认 v7 `idle`。本轮修正了主线次序差异，首次命令故障仍待定位。下一轮在原写前暂停之后、实际 STR 前后及原 DSB 返回之后，使用现有 RAM 日志保存固定进度；日志缺失仍受缓存与复位可见性限制。

## 42. 实际 SQE 写指令与屏障的 RAM 标记

提交 `8b87aa9` 仅为普通模式的 GPU `+0x2054` 访问，在原始 STR 前后调用现有 `loader_log_line`；两处原 DSB 返回后各增加固定行。原 `adreno8_put` 的打印及暂停、STR、屏障和读回顺序保持，HWSCHED 没有新增日志。生产代码净增十行，fixture 增加一行无操作 stub；没有新增缓冲、状态、参数或接口。实际 C 专项通过两种页大小和二十一项运行断言消融，原 GPU 六十四项消融及独立复核通过。

该日志函数仅读写 RAM、操作原子锁及 IRQ／FIQ 屏蔽，不清理缓存。主机专项执行真实 raw／put／hold 函数体，以 host store 和既有屏障模型替换对应硬件操作，只确认 C 调用的包围顺序。争锁、缓存与复位可见性仍限制缺失标记的解释。

XNU 的 5141 个构建输入一致。内核 `out/handoff-mach-ordinary-sqe-markers` 为 19256456 字节，SHA-256 `27fb8822711ac2537678ebfa57be71b12dfd632f6e79dd3894e0e64fb02e8376`；payload 为 28476920 字节，SHA-256 `e944ee1ece8bc27fc4ee681c7356200d01d9b4481f0c19ace620fdaaa9c4cf95`。真机仍最后采到 SQE 写 1 前的原有日志，216 份非空采样中均未取得新 STR／DSB 标记，未发布 CP_INIT。首个失败 USB 调用持续约 6.523 秒，调用返回后约 26.155 秒确认 v7 `idle`。本轮尚未缩小到具体停止指令。

固定厂商 `adreno_hwsched.c` 第 1899～1901 行在 ACTIVE、页故障 stall 且 GX 开启的恢复路径向 `ADRENO_REG_CP_ME_CNTL` 写 0，gen8 表将该项映射为 `CP_SQE_CNTL=0x815`。实际模块尚未确认同一写 0 路径，公开寄存器定义也没有完整位语义。下一轮复用普通 `raw_nop=2`，严格要求继承值 0 后写回 0、读回并进入原十秒观察；写 3 的既有结果保留于第 37 节。该对照可检查零值访问和日志导出范围，无法区分写 0 被忽略与原值保持。

## 43. SQE 控制继承值 0 的写回对照

10 月 26 日提交 `b7230db` 复用普通 `raw_nop=2`：输入和 ring 配置完成后，严格要求控制继承值为 0，再写 0、执行原 DSB、保存固定 RAM 行、严格读回 0，最后执行原 100 次健康周期。非 0 继承在写入前停止，非 0 读回在健康检查前停止。普通 `raw_nop=0/3` 及 HWSCHED 的五个 NOP 保持；没有新增参数、状态或接口。两种页大小通过十三项控制消融、二十二项 RAM 标记消融和原 GPU 六十四项消融，独立复核通过。模型也确认写 0 被忽略仍可读回 0，这种结果不能确认写入已被硬件接受。

XNU 的 5141 个构建输入一致。内核 `out/handoff-mach-ordinary-sqe-zero` 为 19256456 字节，SHA-256 `956627d7b3bfbc7d560138f54de6c1c2ba79bedced21db8ef78f43ef43c18e90`；payload 为 28476936 字节，SHA-256 `22d2b73c93419834fa54a9976eca98d55f5c073b3848a0b0e4c1ff2729211cc2`。

真机取得继承值 0、实际 STR 前、STR 返回、DSB 返回三条 RAM 行及写后读回 0，随后 100 次健康周期通过；显式等待合计十秒，连同访问暂停总采样约 56.371 秒。HALT／ACK 仍为 `0/3` 和 `0/0`。按设计停止并保留资源，未发布 CP_INIT；小根盘加载 `/sbin/launchd` 返回 errno 2 后出现预期 panic。主动 USB reboot 后约 17.744 秒确认 v7 `idle`。

本轮确认同一控制地址的零值访问路径、屏障返回和现有 RAM 日志导出可用；写 1／3 后仍缺少相应标记，实际执行位置继续受采样和故障后的可见性限制。后续优先核对这些值触发的首次 GPU 访问与故障报告，当前仍未取得 CP 命令消费结果。

## 44. 下一步

继续核对实际 KGSL 的首次 CP 命令前提、GPU 内存访问与 RAW 处理条件，选择能区分原因的受限实验。ARC 读取语义仍需核对；长期运行的电源请求须保留继承票值，并处理与触摸初始化共用 DRV2 的并发。CP、zap、scratch 通过后，再验证标准 context、用户态 shader 和桌面绘制；zap 使用本机 Android 固件并重新生成小根盘及输入清单。每轮重新确认设备身份与状态，结合 A 槽重试次数处理 B 槽回退。
