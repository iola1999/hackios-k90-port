# 2026-10-28 round C payload 复用可行性核查

task-3 的产出。问题：round C 能否直接复用 roundb 验证过的 `root.apfs`、只换内核，全程不碰半成品 `hackios-xnu-kernel/userland/obj/`。核查于 2026-10-28 13:2x～13:4x 完成，全程只读（shasum、git status、按显式路径读文件；apfs 内容用 `hackios-xnu-kernel/tools/apfs` 的 Python 模块解出后核，未对任何镜像本体做文本搜索），设备未动。

## 1. 结论

**能复用（路径 A），且当下只有这条路径无风险。** roundb 的 `hackios-xnu-kernel/out/ios26-resume/bbmetal-device/root.apfs` 自打包后未被改写：现盘 sha256 `e36caefb25f09e6e…` 与 roundb manifest 及其旁边 pack manifest 的 `root_sha256` 三方一致；镜像内解出的 7 个关键文件哈希全部与 roundb pack 记录一致（§2 表）。`make-payload.py` 接受现成 root.apfs 作为 RAMDISK 位置参数，只做断言不做重建，所以 round C 的打包不需要 `package.py`、不需要任何编译、不触碰 `userland/obj/`，也就不被容器构建修复或 `build.sh` 新增的架构闸阻塞。

`package.py`（路径 B，重打包）经全文检索与 `userland/obj/` 零关联：driver/shim/probe 由 `xcrun clang` 直接从 `userland/src/*.m` 编（`:168`、`:274-282`），AIR 取 `bbmetal-device/libredwoodair.dylib` 并对 `mesa-arm64e/air-build-record.json` 校验（`:392`、`:472-473`）。半成品 `obj/` 只影响 `build.sh` 一系的重建流程，与 round C 无关。**路径 B 在 round C payload 做出之前不要跑**：它会覆写 `bbmetal-device/root.apfs`（复用目标），且当前会被 clean gate 拦下（§3）。

路径 A 的前置链只有一环未到：task-14 的新内核。`make-payload.py:48` 断言内核文件实哈希等于 `docs/progress/evidence/k90auto/kernel-12377-attr26/kernel.json` 记录值；该文件现在记录 task-1 内核（`81f54468…`，与现盘一致，已复核），task-14 重建后文件字节必变，kernel.json 需要像 task-1 那样手工更新为新 sha（build-kernel.py 只管 kbuild 容器的 16.5 线，不会代写）。断言失败时按协议停下报 lead，不改 json。

## 2. 核对数字

镜像内文件用 `tools/apfs` 模块（`package.py:records()` 同一入口：`Container` → `pick_volume` → `walk` → `inode.contents()`）解出后逐个 sha256；「pack 记录」列取自 `bbmetal-device/manifest.json`（roundb manifest 的 `pack` 段与其一致）。

| 对象 | 镜像内实测 | pack 记录 | 判定 |
|---|---|---|---|
| `/lib/libredwoodmetal.dylib`（241,488 B） | `9d66dd367d09af4d9b526c73c8407627357d1e32d0cd392639bd5e2b35600f26` | 同 | ✓ |
| `/lib/libredwoodair.dylib`（13,983,936 B） | `d7b9ced5a115c08ca17c23e7322a9505c2c6352b3c9660a0d51beece91102e5f` | 同 | ✓ |
| `/lib/libredwood-sbmetal-experiment.dylib`（89,296 B） | `d15c90cdbb2eb0ab9c39a5e8614cc6220512efd77f425cce5183c66a14924181` | 同（new_shim） | ✓ |
| `/bin/lsprobe`（70,368 B） | `54697751bac5af07ecf1e2e6a9c50a1a7d5a361c8fcebc2978a3d2eec2e61b07` | 同；解出体含 `cpu procs=` | ✓ |
| `/bin/framewatch`（67,232 B） | `8c8869b8f1fa65a8bf716ceb31683b4d834e87149ccf3a366f1141fe36ed57e6` | 同 | ✓ |
| `/etc/rc.jobs`（1,252 B，22 行） | `88326d5e58686dcf155a04a3a4dd1606e69f803cb4eade15410bebba668fc5d8` | 同（`jobs_sha256`）；首三行 `lsprobe 60 &`／`lsprobe 300 &`／`var_store show` | ✓ |
| `/etc/inject.conf`（72 B） | `d64d1363c1142ee507debba59570fe532c8f3659716258cc01d40f79175777ef` | 同；内容 `…libredwood-sbmetal-experiment.dylib SpringBoard backboardd` | ✓ |

镜像外配套：

| 对象 | 实测 | 预期 | 判定 |
|---|---|---|---|
| `bbmetal-device/root.apfs`（5,226,496 B） | `e36caefb25f09e6e353980a13e7294445b629c4dbe44963d4a08fa3368e56c46` | roundb manifest `ramdisk.sha256` | ✓ |
| `bbmetal-device/manifest.json` 的 `root_sha256` | `e36caefb…` | 与上一行相等（`make-payload.py:98` 的断言对象） | ✓ |
| `userland/system26.apfs`（4,925,816,832 B） | `d11083be02820507f5639e0a29c6f35256a48d1d4f3cf4cd265eb4b8e346efe4` | roundb manifest `system.sha256` | ✓ |
| 内核 `out/xnu12377/BUILD/obj/mach.development.bcm2837`（20,210,232 B） | `81f544688809a2e8603451fe77732153a8648ad94fdbccd6b2f069e7473edbc1` | kernel.json 现值（task-1 内核；task-14 后两处都要换新值） | ✓ |
| base `air-arm64e-device/on/root.apfs` | `33ed5fc9cb18367c124e6fd26a2fc982f7d80b3a44e04754f87cf74b5aa381f0` | pack `protected_verified`（仅路径 B 用） | ✓ |
| `tools/k90auto/jobs/rc.jobs.freeze` | `a4af9a9f1384fbacfb7e04e34267ecfe3fd8ca8270ff5c69cb5989fa32067102` | roundb pack `jobs_source.sha256`；task-4 rev3 要求值 | ✓（已跟踪、无未提交修改） |

bbmetal-device 旁的散件 `libredwoodmetal.dylib`／`libredwoodair.dylib`／`lsprobe` 与镜像内解出体同哈希（旁件是打包输入，镜像内才是装车对象，两处都核了）。`mesa-arm64e/libredwoodair.dylib` 现为 `7b8e29ed…`，与其 `air-build-record.json` 记录的 `library_sha256`（`d7b9ced5…`，library 字段指向 bbmetal-device 副本）不一致——该目录里的是更新一次构建的原始产物，`package.py` 校验的对象是记录指名的 bbmetal-device 副本（现值 `d7b9ced5` ✓），路径 A 与路径 B 都取后者，此不一致不影响 round C，报给 lead 备查。

## 3. 闸与基线

- **路径 A 不经过 clean gate 与 baseline gate**：两道闸都只在 `package.py`（clean gate `:221-244`，baseline gate `:580-608`）；`run-queue.sh` 无任何闸钩子（检索 baseline/library/dirty/ALLOW 零命中）；`make-payload.py` 只有内核 sha、pack manifest root sha、gpu_speed 一致、必备 boot-args 四道断言。
- clean gate 现状（实测）：`common/ugit status --short` 空 ✓（display 的 `e0b7b62` 注释提交后）；顶层仓 `git status --short -- tools/k90auto ':!tools/k90auto/library-baseline.json'` 有一项 ` M tools/k90auto/summary.py`（ff_s 指标与 hung-held.log 合并读取的进行中修改，归属像 perf，已另行报 lead）。这一项只拦路径 B。
- baseline gate 逻辑（`package.py:580-608`）：只比 `driver_sha256` 与 `air_sha256` 两个二进制哈希（`EXPECT_DRIVER_SHA256`／`EXPECT_AIR_SHA256` 可临时覆盖）；drift 且无 `ALLOW_DRIVER_CHANGE=1` 时拒绝打包；`UPDATE_BASELINE=1` 时用本次 pack 全量重写基线（含 source_sha256）。`source_sha256` 段只记录、不参与闸。
- `tools/k90auto/library-baseline.json` 现值：driver `31f2d6b7…`（旧值）、air `d7b9ced5…`（与实测一致）。按 lead 决定，round C 不用 `ALLOW_DRIVER_CHANGE`，改为把 driver 更新为 roundb 验证值。**从 apfs 解出体实测的两个哈希（装车口径）**：driver `9d66dd367d09af4d9b526c73c8407627357d1e32d0cd392639bd5e2b35600f26`、air `d7b9ced5a115c08ca17c23e7322a9505c2c6352b3c9660a0d51beece91102e5f`，与 lead 预期一致，已先报 lead 核，未动文件。
- 写入建议（等 lead 确认）：`driver_sha256` ← `9d66dd36…`，`air_sha256` 不变；同时把 `source_sha256` 段整体替换为 roundb pack manifest 的 `source_sha256`（`redwoodmetal.m` `40066a5d…`、`lsprobe.m` `85311cac…` 等九项）。理由：现基线的 source 段已过期（`redwoodmetal.m` 记录 `f1b2245e…`，既与 roundb pack 时的 `40066a5d…` 不一致，也与 `e0b7b62` 注释提交后的现值不一致），只改两个二进制哈希会留下「记录不对应产物」的状态，`package.py:601-604` 的注释正是这个教训（3d7ea90e 无从复现）。注意 `e0b7b62` 只改注释，若日后重编 driver，源哈希与基线 source 段会再差一次，二进制是否仍为 `9d66dd36` 未实测。
- 路径 B 附加风险：重跑 `package.py` 会从当前树重编 driver（注释提交后源已变，产物理论上同字节但未验证）；`mkapfs` 输出是否逐字节可复现未验证，覆写后 `e36caefb…` 可能找不回。round C 之后如需重建基线记录，用 `UPDATE_BASELINE=1` 整包重写更自洽。

## 4. 路径 A 的 make-payload 参数（预案，等 task-14 内核与 lead 放行）

命令与 roundb 的唯一差异是内核（kernel.json 记录换新）与 LABEL；EXTRA BOOT-ARGS 与 roundb 的 `extra_boot_args` 逐字相同：

```
GPU_SPEED=3 \
SYSTEM=hackios-xnu-kernel/userland/system26.apfs \
SYSTEM_WINDOW=0x300000000 MEMSIZE=300000000 IDENTITY=v57 \
python3 tools/k90auto/make-payload.py 12377-attr26 roundc \
  out/ios26-resume/bbmetal-device/root.apfs \
  "gpu_log=1 metal=1 cpufreq=1 fb_threads=2 touch_lat=1"
```

CPU_ARGS 用默认（roundb 即默认值）。`GPU_SPEED=3` 是 roundb 的实测档位（roundb manifest `gpu_speed: 3`、cmdline `adreno8_speed=3`），`make-payload.py:109` 会断言其与 pack 记录一致，档位写错打包即失败。`epoch=` 由脚本注入当前时间，是每轮唯一合法变动参数。

打包后核对（对 round C 的 `manifest.json`）：`kernel.sha256` == task-14 新内核值（lead 将发）；`pack.driver_sha256` == `9d66dd36…`、`pack.air_sha256` == `d7b9ced5…`；`pack.root_sha256` == `e36caefb…`；`cmdline` 与 roundb 除 `epoch=` 外逐字段相同。**jobs 核对目标更正**：task-4 rev3 写的「`pack.jobs_sha256` 等于 `a4af9a9f1384fbac`」对不上字段——`a4af9a9f…` 是 `pack.jobs_source.sha256`（源文件 `rc.jobs.freeze`），`pack.jobs_sha256` 是镜像内生效 `/etc/rc.jobs` 的 `88326d5e…`。正确核对是两项：`jobs_source.sha256 == a4af9a9f…` 且 `jobs_sha256 == 88326d5e…`，两项都与 roundb 相等才构成「jobs 原样」。

运行：设备现为 fresh idle，需整盘上传，预算约 9.4 分钟（123 s 上传 + 420 s 跑 + 18 s 复位）；`bash tools/k90auto/run-queue.sh docs/progress/evidence/k90auto/kernel-12377-attr26-roundc 420`。

## 5. 遗留与边界

- task-14 内核未到，kernel.json 现值对应 task-1 内核；lead 已明示现在不打包。新内核 sha 与 bad access 打印格式串到位后，先核 kernel.json 已更新再跑 make-payload。
- task-1 内核无 dSYM（`BUILD_DSYM=0`，kernel.json 的 `dsym_skipped` 字段有说明）；对 `81f54468…` 做 pc 符号化需要另建。task-14 内核是否带 dSYM 由 display 的构建决定，round C 的 lr 判据按 lead 通报走离线命名（imagesText 加 export trie），不依赖 dSYM。
- `summary.py` 未提交修改与 16.5 仓 `tools/mesa/draw-perf.patch` 残留（会污染 16.5 基线重建的链戳）都已单独报 lead，本文档只记状态：两者都不影响路径 A。
- task-4 清单里「framewatch 有 hole-capture 行」一项：解出的 `/bin/framewatch` 不含 `hole`/`gap`/`swap` 子串（身份以哈希 `8c8869b8…` 与 pack 记录一致为准），该验收项的具体标记串等 lead 发 round C 判读标准全文时再定，届时按串重核。
- 本文档全部数字的复核入口：`shasum -a 256 <路径>`；镜像内文件用 `hackios-xnu-kernel/tools/apfs` 模块按 §2 所列路径解出后哈希。检索遵守 2026-10-28 的纪律：未对任何 apfs／共享缓存本体做文本搜索。
