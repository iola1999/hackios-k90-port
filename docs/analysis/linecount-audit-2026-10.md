# 存量行数审计 — 内核侧（2026-10，task-15）

依据 [AGENTS.md](../../AGENTS.md) 的"代码行数约定"（单文件 ≤800 行；生成表等不可拆者文件头写明理由；存量不回溯、逐个判定）。范围 = `hackios-xnu-kernel` 的 `xnu/files/**`、`xnuloader/*.c`、`wifi/lx/**`、`tools/**`（`git ls-files` 口径，不含 xnu-src 上游树；`wc -l` 统计，2026-10-27 复测）。只读审计，一行代码未动；拆分与排期由 Lead 按本表裁决。用户态侧（`tools/mesa/air/**`、`tools/air/*.py`、userland/src）见姊妹文档 [linecount-audit-userland-2026-10.md](linecount-audit-userland-2026-10.md)（task-16），此处不重列。

## 结论速览

- 设备批次 boot-arg 触及面（touchscreen=2、hv_haptic=3、buttons、battery、torch_secs、pcie 路）中，越线文件只有两个：**redwood_goodix.c 1640**（touchscreen=2 生产路）与 **annibale_haptic.c 815**（新文件，越 15 行）。buttons/battery/torch/pcie 各路文件（redwood_buttons 588、annibale_buttons 621、redwood_battery 198、annibale_battery 640、annibale_torch 687、mhi_pcie 603）全部合规。
- **loader.c 是存量里工程风险最高的一块**：设备轮每次开机都跑它、c.img 同批重打也在动它，拆分必须等设备轮之后。
- 红杉专属驱动（wifi/camera/adreno/adsp/mic/sound/speaker/haptic/ufshc）已被 task-12 保险丝（`redwood_soc_is_sm8750()`，kernel 265d336）兜底：K90 上入口即 skip，拆分对设备轮风险很小，但属大 diff，建议设备轮后集中排。注意（独立评估 F02/F08 收紧）：保险丝依赖的 TCSR0 寄存器解释尚未实证，task-17 stepper C 的首次调用回读日志是收账点；收账前此类条目的风险按"低（依赖待验证的机型保护）"读，不读成零风险——真实风险按调用关系和产物变化判断，拆分本身不改变运行面。
- 私有头先例：内核侧已有 `xnu/files/bsd/sys/redwood_qrtr.h`、`redwood_lx.h` 这类跨文件内部头；下表"共享私有头"一律照此放置，不新增构建机制。拆分任务落地时同步进 `xnu/files/bsd/conf/files` 清单（走 patches/series 的 04 片），闸门照旧 kbuild+QEMU。

## 审计表 — 自有代码（>800 行，逐文件判定）

| 文件 | 行数 | 性质 | 建议拆法（层缝，含私有头） | 设备批次风险 | 时机建议 |
|---|---|---|---|---|---|
| xnu/files/bsd/dev/redwood_wifi.c | 4397 | 自有 | 按 step 层拆：`redwood_wifi_private.h`（共享的 say/rd/wr/block 声明）+ say_log.c（say/announce/sleep）、regs_smem.c（rd/wr/smem/smp2p 读层）、power_rpmh.c（cmd_db/rpmh/spmi/rails/pins）、q6_boot.c（固件加载/SCM/image/our_item/start）、glink_qrtr.c（glink 环+会话，qrtr 已在 sys/redwood_qrtr.h）、steps_init.c（step_* 驱动 + init/quiesce 保留）≈6 片各 ~700 行 | 无（红杉专属，保险丝兜底） | 设备轮后；单文件工作量最大，建议独立一天 |
| xnu/files/bsd/dev/redwood_camera.c | 4269 | 自有 | sensors[]/电源表进 `camera_sensors.h`（表+宏），cci_i2c.c（GPIO I2C 手拍层）、csiphy.c、titan.c（ISP 寄存器+捕获）、camera_private.h（level/fake/keep 等共享态）、init+thread 留主干 ≈4-5 片 | 无（红杉专属，保险丝兜底；cam_fake 例外路不碰硬件） | 设备轮后 |
| xnuloader/loader.c | 4174 | 自有（UEFI 频叠式，单产物） | freestanding（memset/str/print）→ efi_basic.c；dt_prop/dt_begin/dt_identity → dt_build.c；ufs_* 普查/转储 → ufs_survey.c；hc_*/block_* → power_block.c；wdt/exception/psci/run_on_other_cpu → cpuppu.c；parse_payload/nvram → payload.c；run_kernel 留主干；共享 `loader_private.h`。注意：需把新 .c 加进 loader 构建清单（构建面 touch，QEMU 与两个 .efi 都要重出） | **有**——设备轮每次开机全量经过 loader，c.img 重打同批 | 设备轮后（轮内 loader 行为必须逐字节同现状） |
| xnu/files/bsd/dev/redwood_adreno.c | 4129 | 自有 | 按 step 分组拆：clocks_fuses.c（gcc/cx/gdsc）、gmu.c（RPMh 序列器+固件）、smmu.c、zap3d.c（zap+3D 核+首帧）、display_probe.c 独立、`redwood_adreno_private.h`；init/step 表留主干 ≈5 片 | 无（红杉专属，保险丝兜底；K90 GPU 走 adreno8.c） | 设备轮后，可与 adreno8.c 收尾同批排（同一负责人手感） |
| xnu/files/bsd/dev/redwood_adsp.c | 3244 | 自有 | 两段走：先 in-file 层拆 image_load.c（mdt/b0x+SCM 认证启动）、link_glink.c（smp2p/glink/qrtr-IPCRTR）、steps_init.c 留 init；二期再把与 redwood_wifi.c **同构的** smem/smp2p/glink 三层抽共享 `redwood_pdr.c`+`redwood_lx_pdr.h`（两文件各删 ~500 行同型码，diff 大，单列任务） | 无（红杉专属，保险丝兜底；mic/sound 随它 skip） | 一期设备轮后；二期另议 |
| xnu/files/bsd/dev/redwood_apfs_check.c | 1872 | 自有（QEMU 侧验证工具） | mount.c（挂载+卷头核对）、walk.c（VFS 遍历）、report.c（对照 apfs.py 的输出比对）+ `redwood_apfs_check` 已有 sys 头补内部声明 ≈3 片 | 无（apfs_check= 只进 QEMU 验证命令） | **设备轮前可做（零风险面）** |
| xnu/files/bsd/dev/redwood_mic.c | 1847 | 自有 | 按通路拆：lpi_pins.c（LPI TLMM）、afe.c（q6afe 路由）、mixer_paths.c（mixer_ctl 表+应用）、init 留主干 + `redwood_mic_private.h`（dsp_up/down 内部态） ≈4 片 | 无（红杉专属；无 init，仅经 adsp 拉起） | 设备轮后 |
| xnu/files/iokit/Kernel/MiniIOSurface.cpp | 1814 | 自有（Apple IOSurface 替身） | 表面状态页+映射、Mach port/SendRight、分配与预算 三分 + MiniIOSurfaceInternal.h；IOKit 类边界要留单类单文件——若拆不过去，按约定在文件头写明理由走"不可拆"豁免 | 低——boot-arg 不直接触及，但它是图形启动的实际执行路径（SpringBoard 显示经它），风险按调用关系与产物变化判（F08）；拆分复验=QEMU 桌面/锁屏全套 | 设备轮后 |
| xnu/files/bsd/dev/redwood_goodix.c | 1640 | 自有 | 板表先走：K90 常数表（board_annibale 组，文件尾部）与红杉组抽 `goodix_boards.h`（纯数据，两板各自可独立复验）；再拆 qup_se.c（SPI 引擎层）、panel.c（Goodix/FT 协议+固件）+ `goodix_private.h`；init/线程留主干 | **有**——touchscreen=2 是 K90 生产路，本批开机即用 | 设备轮后为稳；若 Lead 要轮前动，**只先抽 goodix_boards.h 数据表**（纯数据搬迁，行为可 cmp 日志复验） |
| xnu/files/bsd/dev/redwood_ufs.c | 1619 | 自有 | gpt.c（分区表解析）、devs.c（/dev 注册+读写转发）、dump.c（survey/super/userdata 转储）、写回路（ufs_write=）留主干 + `redwood_ufs_private.h` | **有**——设备轮存储读走 loader 页（rootfs 在关键路径上） | 设备轮后 |
| xnu/files/bsd/dev/redwood_sound.c | 1518 | 自有 | afe_route.c、mixer_ctl.c、play_thread.c + `redwood_sound_private.h`（dsp_up/down/quiesce 内部态） ≈3-4 片 | 无（红杉专属；无 init，仅经 adsp 拉起） | 设备轮后 |
| xnu/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp | 1648 | 自有（显示驱动替身） | surface 管理、swap/vsync 线程、客户端接口 三分 + MiniIOMobileFramebufferInternal.h | 低——显示面实际执行路径（锁屏软渲染即经它），boot-arg 不直接触及；风险按调用关系与产物变化判（F08），拆分复验=QEMU 锁屏/桌面冒烟全套 | 设备轮后 |
| xnu/files/bsd/dev/redwood_ufshc.c | 1333 | 自有（红杉专属 kernel-direct UFS host） | host_init.c、descriptors.c、queue_poll.c | 无（红杉专属；**若后续 K90 存储内核化任务大改此文件，按约定"大改即须合规"顺手拆**） | 设备轮后，或被存储内核化任务触发 |
| tools/apfs/apfs-tool.c | 1790 | 自有（host 工具） | 按子命令拆 cmd_*.c + apfs_tool.h | 无（host 侧，不参与镜像） | **设备轮前可做（零风险面）** |
| wifi/lx/src/lx_80211.c | 2097 | 自有（mac80211/cfg80211 语义替身，见文件头） | regulatory.c（域表+信道应用）、scan.c、join_assoc.c（四步握手挂 lx_wpa.c，已独立）、iface_reg.c + `lx_80211_private.h` | 无（红杉 WiFi 后端，保险丝兜底） | 设备轮后 |
| wifi/lx/src/lx_base.c | 1235 | 自有（LinuxKPI 替身层，见文件头） | 锁与睡眠、工作队列与定时器、skb、内存与固件 四分 + 复用 lx.h | 无 | 设备轮后；ath11k 全量接入时此层本就要跟着长，届时顺手拆更省 |
| wifi/lx/src/lx_bus.c | 863 | 自有（ath11k ahb.c/pcic.c 的临时替身，见文件头） | 越线 63 行，两条路：①拆 regs_windows.c/ce_poll.c；②**不拆先等**——ath11k 自带 bus 层接入后此文件整体作废消失 | 无 | 设备轮后；建议随 ath11k 任务裁决（可能自然消失） |
| tools/qmi-test/test_qmi.c | 1559 | 自有（host 测试工具） | 按测试组拆 test_encode.c/test_ind.c + test_qmi.h | 无（host 侧） | **设备轮前可做（零风险面）** |
| tools/apfs/apfs.py | 1205 | 自有（host 工具） | 类拆（super/nodes/btree 一层、cli 一层） | 无 | **设备轮前可做（零风险面）** |
| xnu/files/bsd/dev/redwood_speaker.c | 1217 | 自有 | qup_i2c.c（QUP SE3 手拍 I2C）、aw88261.c（amp 寄存器）、probe_steps.c | 无（红杉专属，保险丝兜底） | 设备轮后 |
| xnu/files/bsd/dev/redwood_haptic.c | 1009 | 自有 | 波形/参数表进 `redwood_haptic_waves.h`（纯数据），状态机留主干 ≈700+300 | 无（红杉专属，保险丝兜底；K90 走 annibale_haptic） | 设备轮后 |
| xnu/files/bsd/dev/redwood_qmi.c | 957 | 自有（sys/redwood_qmi.h 的实现） | 越线 157 行：编码表接口与事务/指示两部分拆；或接受小越线，待 ath11k QMI 大改时按"大改须合规"顺手拆 | 无（支撑库） | 设备轮后，或等大改触发 |
| xnu/files/bsd/dev/annibale_haptic.c | 815 | **新文件越线 15 行，处置必填** | 波形/时序参数表抽 `annibale_haptic_data.h`（纯数据头，风格照红杉波形表先例），hv_haptic 状态机与 SPMI 层留 .c → .c 落回 ~600 行；diff 纯搬迁、可 QEMU+真机日志复验 | **有**（hv_haptic=3 是设备批次） | **设备轮前可做**：纯数据表搬迁零行为变化，是全部 22 个文件里唯一"越线且值得轮前动"的；或随该文件下一次行为改动顺手做——由 Lead 裁决 |

## 生成表与上游（分类标注，不细审）

| 文件 | 行数 | 判定 |
|---|---|---|
| xnu/files/bsd/dev/redwood_focaltech_fw.h | 7288 | 生成表（首行 `Generated from fw-touch/focaltech_ts_fw_m20.bin. Do not edit.`）——**永不拆**；AGENTS 要求的"文件头写明理由"已由生成标记满足 |
| xnu/files/bsd/miscfs/apfs/apfs_lib.c / apfs_vfsops.c / apfs_vnops.c | 4062 / 1462 / 1261 | 上游/vendored（apfs 模块导入）——**永不拆**，保持上游 diff 干净；新约定不回溯 |
| xnu/files/bsd/miscfs/apfs/libdeflate/lib/deflate_decompress.c | 1208 | 上游 libdeflate——**永不拆** |
| xnu/files/bsd/miscfs/ramfs/ramfs.c | 1998 | Apple 上游 ramfs——**永不拆** |
| xnu-deps/hostinc/** | — | vendored 主机头树——不参与内核构建行数口径 |

## 归 task-16（用户态侧，本表不展开）

tools/mesa/air/**（air_metal.c 6978、air_metal_test.c 6765、air_to_nir.c 4086、air_run.c 2093、air_intrinsics.c 1954、air_module.c 1950、air_metal.h 1313）、tools/air/**（intrincheck.py 2452、kinput.py 1451、metalcheck.py 1387、argbufcheck.py 1096）、tools/metal/owesclass.py 1002（GL 分析边界，归口请 Lead 一并裁定）。见姊妹文档 task-16。

## 新文件预警（不在 git ls-files，拆分归 its owner）

`xnu/files/bsd/dev/adreno8.c` 2599 行（task-4 在途、当前未跟踪）：**新文件必须合规**，落地时需按 step 组拆（gcc/gmu/smmu/submit/bo）+ `adreno8_private.h`，owner=adreno 队友，排期由 Lead 裁。本审计未动它。

## 统计口径复现

```
cd hackios-xnu-kernel && git ls-files 'xnu/files/**' 'xnuloader/*.c' 'wifi/lx/**' 'tools/**' | xargs wc -l | sort -rn
```
