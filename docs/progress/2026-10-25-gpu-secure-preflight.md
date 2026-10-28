# 2026-10-24 阶段 14 实验前置：只读 secure 预检与移交门禁（Codex 执行，待审阅）

日期口径：本文标题与正文日期为实际发生日期 2026-10-24；文件名、`evidence/2026-10-25-gpu-preflight/` 目录名与 manifest 键沿用当时的 2026-10-25 写法，文件与目录不移动（处理记录见[未推送审查](../analysis/2026-10-24-unpushed-review.md) §12 DOCS-P1）。

上游输入：管理员放行的预检轮任务（四项）、协议专席确认的 vendor 顺序不变量、第二轮审阅意见与 vendor 侧更正，以及审阅后单独放行的阶段 14 一次性真机试验（§5）。本轮未推送远端、未变更 SCM function id、未写入任何 CB3 寄存器或安全路由。内核提交 `921e3f9`（前序 `ae841eb`、`7786182`），父仓文档提交随本轮更新 gitlink。

## 1. 实现：预检与门禁

- 只读预检 `adreno8_secure_preflight()`（`adreno8_smmu.c`）：先做边界检查（候选 `SECURE_CONTEXT`/`SECURE_STREAM`/`SECURE_MATCH` 相对已探测的 context 数、SMR 数与 context 寄存器组地址范围），再做 MMIO 读取；顺序写死在代码里，边界不通过时零次寄存器访问。读取集合为候选 context bank 的 `SCTLR` 与已探测范围内全部 `SMR`/`S2CR`（读取无副作用，vendor `arm-smmu.c:239,688` 同样以普通读使用）。拒绝条件：候选 context 的 `SCTLR` 非 0；任一有效 `SMR` 覆盖候选 stream 且其 `S2CR`（active 或 fault 残留字段）路由到候选 context，无论占用位于候选 match 槽还是其他槽。拒绝时零写、零 SCM 调用、保留标志不变。通过时仅报告 HLOS 侧该路由无挂载；安全世界对同一 context bank 的保留对 HLOS 不可读，留给真机确认。
- 候选路由常量进入 `adreno8_private.h`：`SECURE_STREAM 2`（vendor `sun-gpu.dtsi` 的 `gfx3d_secure` stream id）、`SECURE_MATCH 2`（候选 match 槽，开机加载器的实际分配以真机 SMR 扫描确认）、`SECURE_CONTEXT 3`。
- 真实调用点：`adreno8_memory_alloc_secure` 在任何页表与 `kmem` 动作之前调用预检；`adreno8_secure_data` 与 `adreno8_secure_page_tables` 在 staging 之前各自调用（预检失败的请求不产生 SCM 调用，也不改动不确定归属标志）。占用预检此前的缺口（只存在于未被调用的 `adreno8_space_on` 内部）由此闭合。
- 移交门禁：`adreno8_secure_execute` 默认 0 且无 boot-arg（仅主机测试置位），kind-5 分配在预检通过后停住：无 MP_ASSIGN、无 MEM_ALLOC 应答、START 沿请求失败路径提前终止（`adreno8_keep=1 adreno8_return=0` 下 postmortem 一次、全部块保留）。门禁依据（vendor 顺序不变量）：secure context 路由与 secure 页表映射必须在 kind-5 应答前就位，而 HLOS 从未挂载候选路由，CB3 占位映射后面没有 vendor 依据的 secure 翻译；kind-5 应答本身就可能让固件触碰安全缓冲。完整应答路径等 secure 翻译实现审查通过后恢复。
- boot-arg `adreno8_secure_preflight=1` 标记阶段 14 实验模式：行为与默认门禁相同（有意终止 START，不移交、不回复、不再处理后续 HFI 消息），日志额外写明停在哪一步；预检拒绝时两种模式的终止路径一致。
- 注释更正：删除「CB3 无消费者」推断（kind-5 应答本身可使固件访问安全缓冲）；「QTEE shmbridge 未启用」在文档与注释中改为桥状态未知、未读取。

## 2. 主机测试

- `tools/test-adreno8-smmu.py`：新增预检场景（走生产 `adreno8_smmu.c` 实现）：通过（写计数 0，CB3 `SCTLR` 与 SMR 扫描读取次数逐寄存器断言）、CB3 `SCTLR` 非 0 拒绝、候选 match 槽 active 指向 CB3 拒绝、其他 match 槽 fault 残留 CB 字段指向 CB3 拒绝、其他 stream active 指向 CB3 拒绝、不匹配 SID2 且不指 CB3 的精确项通过（两个条件都写入场景注释）、候选槽上 SID2 active 指向 CB4 拒绝（候选槽被占用，测试提交 `6611c5c`）、mask 覆盖 SID2 的范围项指向其他 context 也拒绝（同一测试提交）、IDR0 SMR 数缩到 2 后重探测再预检：拒绝且新增寄存器读次数为 0（边界检查先于 MMIO）。
- `tools/test-adreno8-secure.py`：新增 `preflight` 模式（同一链接单元使用真实 `adreno8_smmu.c`，寄存器播种后重新探测布局）：CB3 占用时两个移交入口均拒绝，SCM 调用 0 次、保留标志不变。
- `tools/test-adreno8-memory.py`：新增 `gated` 模式：默认 `adreno8_secure_execute=0` 时 kind-5 分配在预检后停住：SCM 调用 0 次、`adreno8_memory_failed` 未置位、保留区间为空、secure 页表数为 0，随后普通 kind-4 分配仍成功；成功与 `secure-fail` 模式显式置位执行标志，真实 MP_ASSIGN 链路断言（批次数、编码）不变。
- `tools/test-adreno8-hwsched.py`：终止效果走真实 HFI 消息循环验证：SECURE_MEM 场景下资源请求处理失败时：主机发出 7 条（START 前固定消息）、资源应答 0 条、postmortem 恰好一次、重复调用启动入口不再发出任何消息。
- 全量 10 组主机检查两种页大小（4096/16384）全部成功；vendor 目录按本地 manifest 的 `tests.gpu_vendor_dir` 提供给审阅方（路径为本地私有，不入受控文档）。

## 3. 构建产物（受版本控制输入，无手工修补）

容器 `kbuild` 内对 `/work/repo` 执行 `git fetch /src k90-port && git reset --hard FETCH_HEAD`（源码快照 = 内核提交 `921e3f9`），删除 `xnu-src` 后 `XNU_URL=file:///work/xnu-tag-source bash xnu/apply.sh`（Apple 标签 `xnu-8796.121.2`，基线 `c54f35ca`，76 个补丁、131 个新增文件），`bash xnu-deps/setup.sh`，`bash xnu-build.sh -j8 BUILD_DSYM=0 KEXT_CREATE_SYMBOL_SET=/bin/true`。首次重建暴露输入问题：`git clean -xdf` 不删除内嵌 git 仓库 `xnu-src`（删除它需要 `-ff`），`apply.sh` 因目录已存在而退出，编译沿用了上一轮的 `xnu-src` 源文件（产物哈希与上一轮相同，`strings` 无新日志行）。重做时显式 `rm -rf xnu-src` 后重新展开，复制完成用 `cmp` 与哈希核对驱动源文件，再进行编译；两轮日志均落盘。设置与构建日志全量保存在 Git 忽略的 `docs/progress/evidence/2026-10-25-gpu-preflight/setup.log`、`build.log`。

构建后核验：链接清单包含 `adreno8_secure.o`（`bsd/conf/files` 注册自动生成的规则编译）；`nm` 可见 `adreno8_secure_preflight`、`adreno8_secure_execute`、`adreno8_gpu8_secure_preflight`；`strings` 含预检与门禁日志行（`secure preflight:`、`handover gated`、`preflight-only mode`）；产物 `hackios-xnu-kernel/out/handoff-mach-secure-preflight`（新文件名，保留上一审阅轮 `hackios-xnu-kernel/out/handoff-mach-secure`，19,192,624 字节、`b9be06b8…` 不变）大小 19,193,072 字节，SHA-256 `e2df73c312257792d8388372025d4b28716cbd9b7a2929b5147fe18ca783f8d4`。文件与 manifest 记录为产物身份的唯一依据。

## 4. 真机边界与后续顺序

- 现 secure 自动移交路径默认可执行性已取消；阶段 14 实验（默认与 `adreno8_secure_preflight=1` 相同）在真机上的动作限于修订轮已列的只读寄存器读取与 HFI 终止，无 MP_ASSIGN、无应答、无写操作。keep/return 保护沿用（`adreno8_reset_required` 在启动尝试前置位，块停止时全部保留）。
- 仅 MP_ASSIGN、不回复的实验方案另行审查，本轮未实施。
- CB3 首次启用后拒绝新安全分配、允许完全匹配请求幂等重放，CB0 有效占位符的移除，以及 VA 保留覆盖未完成/保留失败区间，属于 secure 翻译实现阶段的工作，本轮未预先实现。
- vendor 侧更正记录在案：页表项 bit 11 为 nG（此前记 NS 有误，本轮未改动 PTE 属性）；vendor 安全缓冲仅映射进安全页表；vendor 在新页共享后才发布父表项、数据叶子在移交后才发布；PRR/ACTLR 省略仍是未验证偏差，非安全路径的通过历史不能作为 secure 侧依据。
- 主机验证与真机验证的分界沿用修订轮 §4/§5，新增未验证项：match 槽 2 是否即加载器为 gfx3d_secure 分配的槽位（真机 SMR 扫描确认）、安全世界对 CB3 的保留状态、预检读取在该机 SMMU 上的实际行为。
- 推送状态：内核 `k90-port` 领先 origin 三个提交（`7786182`、`ae841eb`、`921e3f9`），父仓文档提交与 gitlink（→`921e3f9`）均未推送；审阅后放行的真机一次性试验执行记录见 §5。

## 5. 真机一次性试验（已放行，实际停在阶段 9）

- 试验输入复核：产物 `out/handoff-mach-secure-preflight` 运行前实算 SHA-256 与 manifest 一致（`e2df73c3…`）。启动参数审查：`adreno8=1` 只运行阶段 1，阶段 14 的取值是 `adreno8=14`（`adreno8.c` 的分阶段循环在第一个 FAILED 阶段停止，后续阶段不尝试）；实际命令行沿用上一轮阶段 14 基线并加预检开关：`debug=0x10e cpus=1 bootcpu=7 epoch=1792797718 adreno8=14 adreno8_pause=0 adreno8_watch=0 adreno8_keep=1 adreno8_return=0 adreno8_speed=1 adreno8_secure_preflight=1 loader_return_after=25`，payload `out/handoff-preflight-full.bin`（28,261,912 字节，`fd5e634c…`），RAM 传盘，未写持久分区。
- 实际结果：主机侧输入错误，本次暂存的小根盘是交互轮根盘 `out/handoff-ui-clean.apfs`（`e9aaafbe…`，不含 GMU 固件），阶段 9 报「no fw/gen80000_gmu.bin in the small image」与「missing or invalid gen80000 GMU firmware」后 FAILED，阶段 10 及以后未尝试。HWSCHED（阶段 14）没有运行：无 kind-5 请求、无预检调用、未执行 MP_ASSIGN、无 CB3 写；本驱动自身的 SCM 调用每次有调用前 announce 与返回后结果两行打印（`adreno8_cx.c` L583、L599），run000 内核日志没有这些行，在日志完整的前提下 adreno8 驱动在阶段 9 前没有发起 SCM；日志截断时，打印行缺失单独不足以支持该推断。其它组件的 SCM 打印形式不在本日志范围内，不能凭日志缺行推断全系统 SCM 次数为 0。内核继续启动到用户态并于 25 秒时限返回 loader（`returned 574724 0`），keep 保留消息照常打印。阶段 14 实验需要含固件的根盘 `out/handoff-ui-gen80000.apfs`（9,220,096 字节，`582b9fb2…`，与 manifest 中 step14 轮记录一致）。放行的单次试验按「出现异常即结束采样」用完，重跑需要另行放行。
- 同轮对照观察（步骤 8 只读 dump 对比 `hwsched-step14b` 对照轮）：CB1 `SCTLR` 两轮相同（`0x3af42118`），CB0（`0x3d62e702` 对 `0x3d22e70e`）与 CB2（`0x107c430c` 对 `0x117c431c`）跨冷启动存在位差异，部分 `TTBR` 同样如此；本设备 GPU SMMU 的 context bank 寄存器读回值跨轮不稳定。CB3 `SCTLR`（0x3dc3000）首次读回 `0x96cc51a`，对照轮未读 CB3。预检以「`SCTLR` 非 0 即拒绝」判定占用，在该机上的真机结论需要结合这一读数不稳定性解读：单次非 0 读回不能区分真实占用与未上电读值，CB3 读数不能归因于某个占用方。
- 收尾与设备最终状态：内核返回后 loader 命令可查，`fastboot reboot`（PSCI 冷复位）后主机 fastboot 侧约 12 分钟无枚举；期间设备实际已重新枚举为 Android 复合描述符并正常启动（ADB 可连，`sys.boot_completed=1`，slot `_b`）：该次复位后loader 未驻留，bootloader 引导了 slot b 的 Android；原因未确认（待查：bootloader 对 boot_a 的重试标记）。按约束未做第二次恢复尝试。设备当前健康：Android 完整启动；整板复位结束了本次 keep 的保留，但先前安全/GPU 归属状态是否全部清除，Android 正常启动不能证明，未验证；未读任何旧 GPU 页面。原始日志与状态保存在 `docs/progress/evidence/2026-10-25-gpu-preflight/run/`（Git 忽略）。

## 6. 重跑准备（主机侧，审阅复核轮）

- 引用核对：[annibale-uefi-build.md](../analysis/annibale-uefi-build.md) L93-L94 变体 A（1.26 MB、`DTB=empty.dtb`、「`fastboot boot` 直测（LK 容量内）」）是 2026-10-23 旧变体时代（BootShim+UEFI FD 打包，早于 boot_a 驻留的 loader v5）；[rootfs-strategy.md](../analysis/rootfs-strategy.md) L105 记录 LK `fastboot boot` 镜像上限实测约 2 MiB、超限 Load Error、大镜像须 `flash boot_a`；[k90-annibale-feasibility.md](../analysis/k90-annibale-feasibility.md) L11 记录本机 XBL fastboot 接受 `boot` 命令（原厂镜像 OKAY、无损伤）。当前 v5 镜像（2,222,080 字节）没有 `fastboot boot` 实测记录，且比约 2 MiB 的实测上限大约 6%。
- APFS 只读提取核验：`tools/hostbin/7z`（7-Zip 26.04）列出根盘 `out/handoff-ui-gen80000.apfs`（`582b9fb2…`）文件表并只读提取 `fw/` 四项固件，提取内容 SHA-256 与 `hackios-xnu-userland/firmware-gen8/gen80000-manifest.json` 逐项一致（gmu 88,896 B `1ad8175e…`、sqe 111,476 B `30ee3301…`、aqe 25,044 B `67562ad5…`、zap 12,088 B `0e3ae03f…`）；`handoff-ui-clean.apfs` 的 `fw/` 条目数为 0。
- 输入校验（进入既有入口 `xnuloader/mkpayload.py`）：`--require name=sha256` 装配前实算输入哈希，`--require-cmd`/`--forbid-cmd` 校验 boot-arg 项，任一不通过即在写出前退出；完成后打印 payload 的 SHA-256。三条路径实测：错误根盘（ui-clean `e9aaafbe…`）拒绝且不产出文件；带 `loader_return_after=25` 的 cmdline 被拒绝；正确输入产出演示 payload 28,413,432 字节 `f9785da6…`（epoch=0，重跑按运行时 epoch 重新装配）。重跑命令行不含 `loader_return_after`；运行中的采样控制路径（`oem stop` 能否替代 stage-14 收尾冷重启）审查中，未授权前按既有手册用收尾冷重启。
- 恢复 loader（优先无刷写）：v5（`89ed602e…`）10-24 写入 boot_a，此后未执行 `oem logwrite`（`loader.c` 注释：只有该命令写 boot_a）也没有其它 boot_a 写。真机只读核验（10-24，Android 侧 adb root 既有权限，`dd` 整分区读回 96 MiB，未重启/未刷写/未进 fastboot）：boot_a 前 2,222,080 字节（镜像 v0 头的页对齐有效长度：pagesize 2048、kernel 2,216,083 对齐 2,217,984、头页+内核页组+ramdisk 页，与镜像全长重合）实算 SHA-256 与批准 v5 完整哈希逐字节一致；尾部只读记录：整分区哈希 `5754318d…`，[2,222,080, 8,034,304) 非零 5,796,339 B（旧 stock boot 残留区），[8,034,304, 96 MiB) 非零 20,853,988 B，未写。数据与解析见 `evidence/2026-10-25-gpu-preflight/boota/notes.md`（Git 忽略）。恢复步骤（待授权）：进 LK 记录 `getvar product`/`getvar current-slot` → `fastboot set_active a`（playbook §3 既有命令，改持久槽位元数据、不写分区内容）→ `reboot` → 预期 `getvar product`=xnuloader、`result`=idle（历史实测约 17 秒）；本核验已完成，LK 侧 fetch 比对不再必要。读回不符或未读时的后续手段：重刷 boot_a v5 + `set_active a` 需另行授权。全程禁持久写时的替代手段：`mkxnuimg.py` 以 `DTB=empty.dtb` 重打包 v5 loader 到 2 MiB 内后 `fastboot boot`（RAM 驻留，重启消失）。
- 主机测试补充：新增非候选槽 SMR5 精确匹配 SID2 且指向 CB4 的拒绝场景（该 stream 已被占用，读扫描只读、0 写），SMMU 组两种页大小成功；生产代码未改动。

## 7. 放行的重跑轮 run001（恢复成功，停在阶段 9 的既有保守检查）

- loader 恢复（无刷写）：LK 身份 `product: annibale`、`is-userspace: no`、`current-slot: b`；`set_active a`+`reboot` 后 20 秒重新枚举，`product: xnuloader`、`result: idle`、`screen` 正常。boot_a 只读核验的结论被行为证实：恢复只需 set_active。
- 输入锁定与运行：`mkpayload.py --require` 核对 kernel `e2df73c3…` 与 rootfs `582b9fb2…`，`--exact-cmd` 核对批准整串（epoch 唯一变化，取 1792802116），无 `loader_return_after`、未用 `--rdfile`/`--rdres`；payload `out/handoff-preflight-r2.bin` 28,413,448 B `2afb28dae1e73b44fbc250fa37eb38fd4dea69ff2ddabf6ac9aa10a228069fa3`。系统盘 2,492,227,584 B 上传 RAM 用时 62.3 s，全程无持久分区写。
- 结果：本轮固件在盘，阶段 9 通过了 run000 卡住的固件检查，走到「configure gmu SMMU context 2」时被修订轮 `ae841eb` 加的保守检查拒绝，原值「9: smmu cb free (0x3dc2000) = 0x107c430c」「context 2 already enabled: sctlr 0x107c430c」，阶段 10 及以后未尝试；HFI、kind-5、secure 预检、MP_ASSIGN 本轮均未执行。拒绝值按原值记录，不做占用归因；该检查同样作用于非安全的 GMU context 2，控制轮 step14b 内核没有这个检查。该拒收消息的「already enabled」措辞与数值不符：0x107c430c 的位 0（使能位）为 0；审阅确认全局门的范围缺陷，§8 本轮收敛。GMU 本轮是冷启动（阶段 4 打印「the GMU's memories were not kept: a cold start」）。
- SCM 计数边界：本驱动每次 SCM 调用有 announce 与返回两行打印（`adreno8_cx.c` L583、L599），run001 返回完整（`returned 1441823 0`，日志含完整 banner 与内核返回行），在日志完整的前提下 adreno8 驱动在停止前未发起 SCM；日志截断时该推断不成立。其它组件的 SCM 打印形式不在本日志范围内，不做全系统计数声明。
- 收尾：采样约 92 秒后 `oem stop` 一次，`result: returned 1441823 0`，返回日志含完整 banner 与内核返回行。本轮的收尾是正常返回：阶段 9 停在 HFI 之前，`adreno8_reset_required` 没有置位（该标志由 HFI DCVS 投票 `adreno8_hfi.c` L453 与 HWSCHED START `adreno8_hwsched.c` L146、L169 置位），`adreno8_quiesce()` 因此直接走普通返回路径；stage 14 运行后那种 park（`adreno8.c` L399-L408 见 reset_required 后 wfe 等待主机冷重启）本轮没有发生，两种收尾状态不能混写。`oem log` 复核后 loader `reboot`（PSCI）一次，20 秒重新枚举 `result: idle`，驻留状态保持。设备停在 slot a 的 loader idle。原始日志在 `evidence/2026-10-25-gpu-preflight/run2/`（Git 忽略）。

## 8. 最小作用域修订（审阅第三轮：普通路径恢复，预检保持严格）

- 审阅结论：`ae841eb` 把 context `SCTLR`≠0 的全局拒收加在共享 `adreno8_space_available` 上，普通 GMU 接管在本机被 CB2 读数 `0x107c430c` 永久拒收，即 run001 停在阶段 9 的回归来源；该值的位 0（使能位）为 0，「已使能」的说法与数值不符。批准的最小修复为仅本地实现、测试、构建，无设备操作。
- 实现（内核提交 `9cc2b9d`）：`adreno8_space_available` 增加显式 `strict` 参数。`adreno8_space_on`（GMU/GPU 普通接管）传 false，逐 diff 恢复 step14b 已验证的三项语义：无全局 `SCTLR` 门、复用例外要求同 match 精确项加 FAULT 路由加 CB `SCTLR` 读 0、路由冲突仅对 S2CR active 类型生效。`adreno8_secure_preflight` 传 true，严格规则保持独立：先边界再读；CB3 `SCTLR` 非零即拒，打印写明非零、不满足预检；候选 match 槽占用、任何有效 SMR 覆盖 SID2、任意 S2CR 类型指向 CB3 均拒。secure 检查全部保留，随普通路径恢复一项未丢。
- 生产路径测试：CB2 `SCTLR`=`0x107c430c` 普通接管成功，写轨迹与 `SCTLR`=0 基线逐条一致（测试桩新增写轨迹记录）；候选 match 槽同流加 FAULT 残留加 `SCTLR` 非零拒收（只读）；CB3 `SCTLR`=`0x96cc51a`（本机读数，使能位为 0）预检 0 写拒绝；fault（`0x20003`）与 bypass（`0x10003`）残留在非覆盖槽指向 CB3 预检 0 写拒绝；非候选槽精确 SID2→CB4 预检 0 写拒绝；边界检查前零 MMIO、门禁 0 MP_ASSIGN、0 kind-5 应答的既有断言不变。全量 10 组主机检查两种页大小（4096/16384）全部成功，日志 `evidence/2026-10-25-gpu-preflight/scopefix/tests-10groups.log`（Git 忽略）。
- 构建与产物：干净源码快照 = 内核提交 `9cc2b9d`，流程与 §3 相同（显式 `rm -rf xnu-src` 后重新展开标签源码与补丁）。产物 `hackios-xnu-kernel/out/handoff-mach-scopefix` 大小 19,193,072 字节，SHA-256 `1785d8d4e911e3ec67ce2408f974b772bcb128ad040a6735a07ff182cc19c498`；新文件名保存，已审版本 `out/handoff-mach-secure-preflight`（`e2df73c3…`）与 `out/handoff-preflight-r2.bin`（`2afb28da…`）不覆盖。旧 xnu-src 残留导致 apply.sh 退出、编译沿用上一轮源文件的问题在本轮再次出现并再次以显式删除解决（失败轮记录 `build-first-round-stale-xnu-src.log`）；根治方向是构建流程的源快照前置检查，留待后续轮，本轮未改工具。源快照校验记录已归档供审查：编译树 `git log -1` 与构建输入同为 `9cc2b9d`，`xnu/files/` 全部 131 个注入文件与编译树逐字节比对零差异（`injection-check.log`），xnu-src 工作树实体清单 173 项（`xnu-src-status.list`），完整重展开与编译日志 `build.log` 共 1914 行（apply 76 补丁+131 文件、deps、899 编译单元、STEP-DONE）。构建、测试与校验日志保存在 `evidence/2026-10-25-gpu-preflight/scopefix/`（Git 忽略），四份记录 SHA-256 记入 manifest，manifest 绑定提交、产物与哈希。
- 重跑方案（10-24 独立审查通过后放行，实测见 §9）：输入三件 = 本产物内核 + 根盘 `582b9fb2…` + 批准 cmdline（epoch 取运行时值，`--exact-cmd` 整串核对），`mkpayload.py --require` 装配新 payload；playbook §4：loader idle 冷启动生命周期内 stage-system 传系统盘 → stage payload → `oem run`；采样按 §5 手册（运行中 `oem log`，返回后先 `getvar result` 与 `get_staged`）；本轮预期阶段 9 GMU 接管恢复 step14b 行为，阶段 10 起进入 SCM/HFI 路径，预检严格规则不变。设备最后观测为 slot a loader idle（该状态指最后一次读取，重跑前重新确认），无刷写。
- 边界：实现、测试、构建、文档完成即冻结；未推送（内核 `k90-port` 领先 origin 八个提交，父仓文档提交含 gitlink→`9cc2b9d`），无新设备操作，未新增参数或工具行为。

## 9. run002 实测（放行后一次运行：阶段 9 恢复，kind-5 请求停在预检）

- 运行前重新确认：`getvar product`=xnuloader、`result`=idle（本轮实读，未沿用上次观测）；装配输入实算通过 `--require`（内核 `1785d8d4…` 19,193,072 字节，根盘 `582b9fb2…` 9,220,096 字节），`--exact-cmd` 整串一致（epoch=1792805517 为唯一运行时值），`--require-cmd adreno8_secure_preflight=1`、`--forbid-cmd loader_return_after`，未用 `--rdfile`/`--rdres`，无额外 token；payload `out/handoff-preflight-r3.bin` 28,413,448 字节 `2a58dc6f20c8c5e92547fd889665e594bfa846bf3900fecd88c9ac5d76e62696`。
- 上传与运行：09:32:01–09:33:03 stage-system 传系统盘 2,492,227,584 字节 62.283 秒入 RAM；09:33:14 `oem run`；全程仅 RAM 上传，无持久分区写。
- 阶段 9 恢复：本机该次冷启 CB2 `SCTLR` 读数 `0x117c431c`（run001 为 `0x107c430c`，跨冷启不稳定），普通接管按 step14b 顺序完成（FAULT→CB2 关→建表→`SCTLR`=0x27），打印「gmu translation enabled: stream 5, context 2, root PA 0x95e76c000」；run001 的阶段 9 拒收消失，作用域修复在真机生效。
- 阶段 10–13 与 SCM：固件加载校验 0x15a50 通过；阶段 11 两次 SCM 调用各按两行打印（`0x42000601` 返回 0 应答 0x1；`0x42002801` 返回 0 应答 0）；阶段 12 GMU 起动、HFI 队列 status 1；阶段 13 指令表 2 频点 12 带宽行。正常初始化 SCM 允许，与门禁预期一致。
- 阶段 14 预检：共享缓冲分配走 CB2 正常；日志出现「MEM_ALLOC kind 5 handle 0x5 flags 0x1007 size 0x138000 align 0」后紧接预检读 `0x3dc3000`=`0x96cc51a`，打印「secure preflight: context 3 SCTLR 0x96cc51a is nonzero; the context bank fails the preflight」，即按原值保守拒绝（该值位 0 为 0，严格规则只判非零，未做位解释）；预检前后 CB3 无写；全部日志无 kind-5 应答、无 MP_ASSIGN、无 START ACK；阶段 14 FAILED 后 keep 路径继续启动，内核进入用户态（launchd/SpringBoard 在实时日志中）。预检的 SCTLR 短路在路由扫描之前（`adreno8_smmu.c` L419-L452 先于 L455 起的路由循环），本轮预检时刻未读任何路由寄存器；阶段 8/9 dump 的 24 条 SMR 全 0、S2CR 全 `0x3000018` 是开机时刻的路由状态，与 kind-5 请求时刻没有对应关系，预检时刻的路由实态要靠拒绝后的只读采样获取（§10）。
- 收尾：09:35:58 `oem stop` 一次；`result` 保持 running 至 09:36:40，loader 于 09:37:19 标记「hung 1310720 0」。park 的代码路径与该状态相容：quiesce 在 `adreno8_reset_required` 置位后 wfe 等待主机冷重启（`adreno8.c` L399-L408），但两条 park 打印（`adreno8.c` L232 stop 侧、L400-L403 probe 侧）本轮日志均未捕获，最后一段实时日志止于 09:35:25，早于 `oem stop` 33 秒，日志窗口没有覆盖停止时刻；hung 只证明 loader 判定内核无响应（`loader.c` L3573-L3579 的 OTHER_CPU_HUNG 路径，行号按 2026-10-24 审查修正），park 结论按「代码路径相容但日志未确证」记录，与 run001 的正常 returned 分列。停止后的日志补采顺序已写进 playbook §5。hang 态 `get_staged` 只出 32,767 字节 loader 串行日志（截断在阶段 8 dump 行中），两次重组结果相同；完整启动日志在实时采样 002-live1（6,491 行）与 002-live2（9,363 行）。09:38:03 loader `reboot`（PSCI）一次，09:38:23 重新枚举 xnuloader、`result`=idle。
- 最后观测：slot a loader idle（指本轮收尾读取，后续运行前重新确认）。原始日志与记录在 `evidence/2026-10-25-gpu-preflight/run3/`（Git 忽略），payload 与产物哈希绑定记入 manifest `run002_2026_10_25`。
- 专项审查两项已核销（独立审查结论）：`SCTLR` 依规范允许复位后呈 UNKNOWN，CB3 该非零读数的实际来源未知，寄存器值读不出占用信息；`0x96cc51a` 位 4 的字节序核对完成。CB3 占用仍属未知，判据保持「`SCTLR` 非零即拒」。
- vendor-dir 复核：`tests.gpu_vendor_dir` 记录的路径实际存在，四个文件哈希与 `test-adreno8-gpu.py` 内 pin 值一致（`3379f615…`/`7faff3fd…`/`e85cb422…`/`f66d80cd…`），「缺路径」的说法与当前观测不符。

## 10. 诊断采样与构建溯源（审阅第四轮：本地实现、测试、构建，无设备操作）

- 实现（内核提交 `e5fdd39`）：严格预检在 SCTLR 非零拒绝时于拒绝打印（`adreno8_smmu.c` L423）之后补一次对已探测范围的只读采样（L432-L450）：SMR 逐条读、无效项跳过 S2CR；有效项命中候选 match、mask 后覆盖 SID2 或 S2CR 类型指向候选 context 3 时逐条打印（L446）；汇总行带步号与单调纳秒并声明拒绝保持原样（L450）。边界检查在采样之前，SCTLR 判据不变，采样不新增拒绝理由，扫描只一遍、返回 false 的结论不受扫描结果影响；0 写、0 SCM 调用、0 kind-5 应答；未使用 CB4-6 与 CB19-20、未新增寄存器、未引入多次冷启采样。
- 主机测试：smmu 组给测试桩补 `mach_absolute_time` 与 `absolutetime_to_nanoseconds`（定值，断言可复现），驱动打印桩 `adreno8_say` 改为转发 stdout 以支持顺序断言；新增断言覆盖 CB3 残留值 1 与 `0x96cc51a` 下的全范围采样（SMR0 与 SMR23 各读一次、无效 SMR 不触发 S2CR 读）；新增候选槽占用（SMR2）与 CB3 路由（SMR5→CB3）同非零 SCTLR 并存的场景，两条命中行各一次、只读 0 写、首次拒绝理由仍是 SCTLR；mask、槽冲突与边界 0-MMIO 的既有断言保留。runner 捕获子进程输出并断言顺序：拒绝行在前、命中行在中、汇总行每场景恰一条。10 组两种页大小全部成功，日志 `evidence/2026-10-25-gpu-preflight/diag/tests-10groups.log`（`3d5e6f68…`）。
- 停止后日志补采（playbook §5 新增程序）：`oem stop` 后 result 未转 returned 时立即 `oem log`+`get_staged` 取第一轮并完整保存，约 2 到 3 秒后取第二轮，固定两轮、不做轮询循环；结论分三档：host-stop banner 未见（抓取不完整与内核未执行停止回调无法区分）、banner 已见且无冷复位保留打印（park 未确证）、见到「requires host cold reset」打印（park 确证）。hung 本身只记录为 loader 判定内核无响应；判定 hung 后实时环形缓冲指针已清空（`loader.c` L2517），挂死判定时刻的快照只保留在 HUNG 分支 `write_logs` 预先组装的暂存内容里（L3578），直接 `get_staged` 可取回，再次执行 `oem log` 会经 `compose_logs(NULL, 0)`（L327-L347、分支 L4035-L4041）把暂存覆盖为仅 loader 日志；本程序的适用状态是挂死判定前的 running，此时 `oem log` 读实时环形缓冲。banner 命名与判据按 2026-10-24 审查修正，见[审查记录](../analysis/2026-10-25-loader-review-findings.md)。loader 未改（行号固定于 `hackios-xnu-kernel` 提交 `ec53bac`）。
- run002 措辞修订：§9 收尾改写为 park 代码路径相容但日志未确证（两条 park 打印在全部抓取中缺失，实时日志止于 stop 前 33 秒）；阶段 8/9 dump 的路由状态（SMR 全 0、S2CR 全 `0x3000018`）属开机时刻，与 kind-5 请求时刻没有对应关系，预检时刻的实态由本轮采样获取。专项审查两项已核销：`SCTLR` 依规范允许复位后呈 UNKNOWN，CB3 非零读数的实际来源未知；`0x96cc51a` 位 4 字节序已核对。CB3 占用仍属未知，判据「非零即拒」不变。
- 构建溯源（一次性前置检查，用进程命令与既有入口，未新增工具）：构建前记录 XNU 基线（本机克隆 tag `xnu-8796.121.2` commit `c54f35ca…`，447,764 KiB）；旧 `xnu-src` 先记录指纹（445,192 KiB、base commit `c54f35ca…`）再过绝对路径检查删除，删除或 apply 失败在编译前退出，不带旧树继续；`git reset --hard FETCH_HEAD` 后逐条记录 76 个补丁 SHA-256（聚合 `168e70ef…`、series 文件 `72b0303b…`）与 131 个注入文件清单（清单 `7d78b542…`、内容聚合 `372a6618…`）；apply 后编译树 base commit `c54f35ca…` 与 131 个文件逐字节比对零差异（76 个 Apple 文件被修改、97 个新增条目）；构建前后记录仓库 HEAD `e5fdd39` 与 dirty 0。流程共三回合：第一回合符号集桩变量名写错（`config/Makefile` 实际用 `KEXT_CREATE_SYMBOL_SET`）停在 check_all_exports，日志留存 `build-failed-wrong-symbolset-var.log`（`13d9b8df…`）；第二回合产物路径笔误退出，日志被第三回合覆盖、失败原因记录于此；第三回合全步成功（`build.log` `e79b3fb9…`）。
- 产物：`hackios-xnu-kernel/out/handoff-mach-diag-scan` 19,193,072 字节 SHA-256 `20368dc8f4f6c0968e14302f4bbb07d44855d8172d96e05ad82dc8faeecd1c1a`；容器与主机复测一致，`nm` 命中 `adreno8_space_available` 与 `adreno8_secure_preflight`，`strings` 命中新增打印三条（主机校验 `host-verify.log` `ffb55984…`）。旧产物 `handoff-mach-scopefix`（`1785d8d4…`）、`handoff-mach-secure-preflight`（`e2df73c3…`）与根盘（`582b9fb2…`）复测不变。日志、清单与一次性脚本保存在 `evidence/2026-10-25-gpu-preflight/diag/`（Git 忽略），哈希记入 manifest `diag_scan_2026_10_25`。
- 边界：实现、测试、构建、文档完成即冻结；未推送（内核 `k90-port` 领先 origin 九个提交），无设备操作，参数集与判据未变，playbook 与文档之外未改工具。

## 11. 日志修订轮（审阅第五轮：单遍路由视图加自有 GMU 对照，无设备操作）

- 动机：§10 产物未获放行，只读采样缺自有对照条目时无法区分真实路由视图与退化读取（全无效）。修订后由后处理核对自有 GMU 路由（有效条目覆盖 stream 5 且 S2CR 指向 context 2）是否出现在打印的 valid 条目里；日志对照只用于区分两种读取形态，作 CB3 占用判据仍不成立。
- 实现（内核提交 `bd8eca5`）：`adreno8_smmu.c` SCTLR 非零分支（L419-L468）保持单遍，循环内直接复用已读值：拒绝行在 L423，候选槽无论 SMR 有效与否打印 SMR 原值（无效行 L449 明确「s2cr not read」且不读该槽 S2CR，valid 才读 S2CR 于 L454 并逐条打印 SMR/S2CR 原始值，条数以已探测 match 数为界）；命中候选路由或候选 context 只计数不占行；汇总行 L464 带步号与单调纳秒打印 scanned/valid/hits 并声明拒绝保持原样。MMIO 仍为每槽一次 SMR 加仅对 valid SMR 的一次 S2CR，无预读、无第二遍、无新寄存器；判据不变，0 MP_ASSIGN、0 CB3 写、0 kind-5 应答不变。
- 主机测试：smmu 组场景从三个增至四个，新增自有 GMU 非冲突条目（候选槽无效、SMR6 精确 SID5 有效、S2CR 用阶段 9 实写值 `0x302`，即 `SHCFG_NSH | context 2`），断言该条目按原始值打印、只计入 scanned 与 valid；全无效场景断言 24 槽 S2CR 读次数全为 0，冲突场景断言仅槽 2 与 5 各读一次 S2CR、每槽 SMR 恰读一次（读次数不增加）；runner 断言四场景各一条拒绝行与一条汇总行、候选无效行 3 次、valid 条目行 3 次且值与场景设定一致、汇总计数 scanned 24/valid 0/0/2/1、每对拒绝与汇总之间样例行不超过 24 行且无嵌套拒绝。10 组两种页大小全部成功，日志 `evidence/2026-10-25-gpu-preflight/diag2/tests-10groups.log`。GMU 样本值改用阶段 9 实值 `0x302` 的测试与期望行修订在内核提交 `3ce4102`，仅改测试文件；产物源码保持 `bd8eca5`（生产内核未改、未重建）。
- 构建与产物：按 §10 已核验的溯源流程重跑（基线记录、旧 xnu-src 指纹后删除重建、76 补丁与 131 文件清单、apply 后逐字节比对、HEAD/dirty 记录，编译树 HEAD `bd8eca5` dirty 0），产物 `hackios-xnu-kernel/out/handoff-mach-diag-scan2` 19,193,072 字节 SHA-256 `2a5d52891dcb9d55a88f5fb03db650b57e547675ba12c9998168cf7d0750392b`，容器与主机复测一致，`nm` 命中 `adreno8_space_available` 与 `adreno8_secure_preflight`，`strings` 命中三条样例行与拒绝行；131 文件清单哈希与上轮一致、内容聚合因本轮提交变为 `54a7137d…`；旧产物 `handoff-mach-diag-scan`（`20368dc8…`）与更早各版本保留未覆盖。日志与清单保存在 `evidence/2026-10-25-gpu-preflight/diag2/`（Git 忽略），记入 manifest `diag_scan2_2026_10_25`。
- 边界：未推送（内核 `k90-port` 领先 origin 十个提交），无设备操作，参数集与判据未变，loader 未改，未新增工具；交付后冻结，等对新增日志行的审查。

## 12. run003 实测（放行一次 diag-scan2 诊断：kind-5 时刻路由视图到手，park 打印确证）

- 运行前重新确认：`getvar product`=xnuloader、`result`=idle（本轮实读）；装配输入经 `--require` 核对通过（内核 `2a5d5289…` 19,193,072 字节，根盘 `582b9fb2…` 9,220,096 字节），批准整串 `--exact-cmd` 一致（epoch=1792813370 为唯一运行时值），`--require-cmd adreno8_secure_preflight=1`、`--forbid-cmd loader_return_after`，未用 `--rdfile`/`--rdres`，无额外 token；payload `out/handoff-preflight-r4.bin` 28,413,448 字节 `ae92515bb9b350de24f75c0f217209743d101e14c60c47484c9239085741197f`。
- 上传与运行：11:42:58–11:44:01 stage-system 传系统盘 2,492,227,584 字节 62.284 秒入 RAM；11:44:23 `oem run`；全程仅 RAM 上传。阶段 9 实写 SMR(1)=`0x80000005`、S2CR translate `0x302`，root PA 0x95e7e8000。
- 阶段 14 视图：「MEM_ALLOC kind 5 handle 0x5 flags 0x1007 size 0x138000 align 0」后预检读 `0x3dc3000`=`0x96cc51a` 并打印拒绝行，随后路由视图：「match 1 smr 0x80000005 s2cr 0x302」（唯一 valid 条目，即阶段 9 自有 GMU 路由原值读回）、「match 2 smr 0 invalid; s2cr not read」（候选槽无效）、汇总「at t=7579597432760ns: scanned 24, valid 1, 0 on the candidate route or context 3; the SCTLR rejection stands」。数值判读保留原值、TYPE 用掩码运算：(0x302 & 0x30000) >> 16 = 0，context = 0x302 & 0xff = 2。自有条目在场证明该读数非退化全无效；候选槽该时刻无效；视图只覆盖 HLOS 可见路由，CB3 安全侧占用仍未知，判据「非零即拒」保持不变、未放宽。
- 反向核对：全部日志 CB3 `0x3dc3xxx` 零写（仅 0x3dc3000/0x3dc3020 两处读）；无 MP_ASSIGN、无 kind-5 应答、无 START ACK。
- 收尾：11:46:04 `oem stop` 一次（运行 101 秒，在 120 秒窗口内、按拒绝+汇总到齐结束）；`result` 保持 running；两轮补采 11:46:11/11:46:14 各 1,311,658 字节完整日志，host-stop banner「the host asked for the end of the run」与「adreno8: GPU probe requires host cold reset before reusing kernel memory」两条均在，park 按打印确证（run002 未确证项本轮补齐）；11:46:38 `reboot`（PSCI）一次，11:47:00 重新枚举 product=xnuloader、`result`=idle。最后观测：slot a loader idle；无重复试验、无恢复操作、无切槽、无刷写。
- 记录：原始日志与时间线在 `evidence/2026-10-25-gpu-preflight/run4/`（Git 忽略），哈希绑定记入 manifest `run003_diag_scan2_2026_10_25`；产物源码 `bd8eca5`，测试提交 `3ce4102` 未触及内核。

## 13. 判据变更注记（2026-10-24 未推送审查 G1 补记）

- 内核提交 `ec53bac` 把 `adreno8_secure_preflight` 对 CB3 `SCTLR` 的判据从「非零即拒」改为只判 bit 0（M 位），另加路由视图命中数为 0 与 GMU 自有路由读回一致两项条件。本文 §8 至 §12 写于该提交之前，「非零即拒」的表述在各自写作时的判据范围内成立，原文不改。
- 以 run003 读数代入（CB3 `SCTLR` `0x96cc51a` 的 bit 0 为 0；路由视图 scanned 24、valid 1、hits 0；match 1 `0x80000005`/`0x302` 与阶段 9 自有 GMU 路由一致），当前代码的预检会通过，`adreno8_secure_preflight=2` 时会实际发出 MP_ASSIGN。该结论只是日志数值的静态代入：context bank 读数跨冷启动不稳定（§5 对照轮），路由视图只反映 kind-5 请求时刻的快照，代入通过只是静态核对，当前机状态是否通过预检需要下次试验前按新判据重新实读。
- mode 2（一次移交）继续暂停：放行需要负责人对新判据单独签署，并按 §10 未验证前提逐项裁决残余风险。总账与[未推送审查](../analysis/2026-10-24-unpushed-review.md) §12 已同步该状态。
