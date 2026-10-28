# 无人值守收尾：从 `oem stop` 到 idle loader 的实测与人工边界

本篇回答两件事：现有收尾路径是否需要人按键，哪些状态人必须到场。判断依据同时给出源码位置和实测数据。源码行号固定于 `hackios-xnu-kernel` 提交 `da3d02c`（内核侧 `xnu/files/osfmk/arm64/loader_return.c`、`xnu/files/bsd/dev/adreno8.c`，loader 侧 `xnuloader/`）。命令细节见[真机手册](../plan/device-test-playbook.md)，USB 层面的恢复规则见[USB 恢复经验](2026-10-25-usb-recovery-lessons.md)。

## 1. 结论

- 收尾全程不需要人按键。本轮从 idle loader 起跑一次（证据目录 `docs/progress/evidence/k90auto/kernel-12377-attr-teardown-a/`）：`oem stop` 后 50 秒 loader 判 `hung-held`，主机保存日志并 `reboot`，复位落到 B 槽 Android，`recover-loader.py` 经 ADB 回到 LK、`set_active a`、再回到 loader，`result` 为 `idle`、`ramdisk-state` 为空。
- 2026-10-27 的 16 轮（`kernel-12377-attr-bbmetal8`～`bbmetal25`）复位直接回 loader：`oem stop` 到 `hung-held` 50.5～51.5 秒，判 `hung-held` 到发出 `reboot` 0.1 秒，`reboot` 到 `result: idle` 16.8～17.9 秒，单轮收尾 67～70 秒。
- 那 50 秒是 loader 对内核心跳的静默预算，内核在这段时间停在停止路径的 park 自旋上。本轮 `oem stop` 后 2 秒取到的快照里已经同时有 host-stop banner 和 `adreno8: GPU probe requires host cold reset before reusing kernel memory`，此后日志没有新内容（`run/stop1.log` 第 7611 行起）。

## 2. 判断依据：源码链

1. 主机 `oem stop`：loader 把 `running_live->stop` 置 1 并回 OKAY（`xnuloader/loader_06_usb_entry.inc` 的 `oem stop` 分支，`lc_stop_action` 在 live 时返回 `LC_STOP_NOTIFY`）。本轮实测这个应答 0.001 秒返回。
2. 内核每秒一次的 `loader_stop_poll`（`loader_return.c` L521）看到 stop：打印 `--- the host asked for the end of the run: back to the loader ---`（L526）、`redwood_var_save_on_return()`、`redwood_adreno_stop()`（L531）、`redwood_wifi_stop()`、`redwood_adsp_stop()`，然后 `loader_return()`（L534）。
3. 返回路径进入 `adreno8_quiesce()`（`adreno8.c` L471）：`adreno8_reset_required || adreno8_memory_retained()` 为真时打印「GPU probe requires host cold reset before reusing kernel memory」，随后 `for (;;) wfe`（L476-L481），函数不返回。`adreno8=23 adreno8_keep=1` 的载荷每轮都满足这个条件。
4. 内核不再自增心跳。心跳由每 10 秒的 `hv_wdt_pet` 加一（`loader_return.c` L556、L613-L632），park 之后不再执行。
5. loader 的观察循环在 `seconds_since(last_beat_at) >= SILENCE_SECONDS` 时判 `OTHER_CPU_HUNG`（`xnuloader/loader_03_ufs_block_watch.inc` L852-L858；阈值 `SILENCE_SECONDS 50` 在 `loader_02_platform_cpu_ufs_survey.inc` L410）。资源仍被持有时结果写成 `hung-held`（`loader_05_layout_run_kernel.inc` L935-L941）。
6. held 状态下 `reboot` 仍然放行（`loader_06_usb_entry.inc` L716）：annibale 走 `psci_reset_attempt()`，只有该调用返回才写 `reset-failed`（同处 L719-L727）。held 状态下被拒的是 `oem ramdisk`、`download:`、`oem run`、`oem selftest`、`oem probe`、`oem logwrite` 等写入口（`loader_01_base_log_dt.inc` 的 `lc_blocked_cmd`），查询、日志、截图、`reboot` 不在其中。
7. 复位后 `run-auto.py` 轮询到 loader 重新应答 `idle` 且 RAM 系统盘为空，记为回到 loader；若落到 B 槽 Android，`run-queue.sh` 调 `recover-loader.py` 恢复 A 槽。

## 3. 判断依据：实测

16 轮 `commands.jsonl` 的时间差（主机单调时钟，同一轮内相对起点）：

| 段 | 观测值 | 轮数 |
|---|---|---|
| `oem stop` → 读到 `hung-held` | 50.5～51.5 秒 | 16 |
| 读到 `hung-held` → 发出 `reboot` | 0.1 秒 | 16 |
| `reboot` → 读到 `result: idle` | 16.8～17.9 秒 | 12 |
| `reboot` → 落到 B 槽 Android | 1.1～22.1 秒 | 4 |

四个落到 Android 的轮次（`bbmetal13`、`bbmetal15`、`bbmetal17b`、`bbmetal21`）中，`bbmetal21` 由 `recover-loader.py` 全自动恢复（adb 认到 `ro.product.device=annibale`、`ro.boot.slot_suffix=_b`，`set_active a` 后回到 loader idle）；`bbmetal13` 与 `bbmetal15` 的恢复在 `adb devices` 还没有设备时断言退出，需要人把设备带回，见第 5 节第 4 条。本轮的复位也落到 Android（A 槽 `slot-retry-count:a: 0`、`slot-unbootable:a: yes`），`recover-loader.py` 恢复后我在 LK 用 `set_active a` 把重试次数由 6 恢复到 7。

## 4. 怎样区分「内核主动 park」与「驱动卡住」

两种情况的观测完全一样：心跳停下、50 秒后落到 `hung-held`。区分只能靠停止后的打印，三档判据见真机手册第 5 节。本轮拿到的是 park 确证：`stop1.log` 里 banner 之后紧跟 `adreno8: secure service closed; all pages retained until cold reset` 与 `GPU probe requires host cold reset before reusing kernel memory`，`hung-snapshot.log` 以 `== END OF LOG ==` 结束。

时间关系可以作旁证，不能单独定论：心跳周期 10 秒，若内核在 stop 之后又运行一段才卡死，`hung-held` 会落在 stop 之后 40～50 秒的任意位置；16 轮全部落在 50.5～51.5 秒，与「停止回调在 1 秒内执行完并进入 park」一致。

`bbmetal22`～`bbmetal25` 的收尾日志里没有这两行，原因在工具：`run-auto.py` 判到 `hung-held` 后先执行 `oem log`，该命令走 `compose_logs(NULL, 0)`，把 HUNG 分支预先组装好的快照覆盖成 loader 自己的 32,767 字节串口日志（`log_buf[32768]`，`loader_01_base_log_dt.inc` L86）。本轮改为判到 `hung-held` 后直接 `get_staged`，拿到 739,676 字节的完整快照。收尾若要每轮留证，取日志要在 `oem log` 之前。

## 5. 只能靠人工离开的状态

| 状态 | 现象 | 现在的处理 | 改法 |
|---|---|---|---|
| `result: running` 长时间不变 | `oem stop` 只置标志，内核的 `loader_stop_poll` 每秒轮询一次；该线程被挡住就永远看不到标志 | `run-auto.py` 在 stop 之后再查一次仍为 running 时保存 `running.log` 并退出，不发复位 | 先补发一次 `oem stop` 并做两轮停止后补采；日志里没有 host-stop banner 且心跳仍在增长，判定轮询线程被挡，记录后请人长按电源键。软件兜底需要改内核侧轮询的位置（中断上下文或更高优先级），不属本轮范围 |
| `result: reset-failed` | `psci_reset_attempt()` 返回了错误，loader 保留 USB 循环 | 尚未遇到过 | 主机对同一状态重试 `reboot` 两次；仍失败则保存日志并请人长按电源键 |
| USB 枚举在、所有命令超时 | 陈旧 IN 未取得终止通知，缓冲区一直被占 | 见 [USB 恢复经验](2026-10-25-usb-recovery-lessons.md) 第 4 节 | 有界等待后重试一次 `reboot`；两次无应答再请人 |
| 复位落到 B 槽 Android 且 adb 未枚举 | `recover-loader.py` 在 `adb devices` 为空时断言退出（`bbmetal13`、`bbmetal15`） | 当时由人工带回 | 已在 `recover-loader.py` 加 40 秒内轮询 `adb devices` 的等待（`ADB_WAIT`）；仍等不到再请人。本轮该等待生效，恢复走完 |
| A 槽重试次数耗尽 | `slot-retry-count:a: 0`、`slot-unbootable:a: yes`，复位后进 Android | 恢复后 `set_active a` 把重试次数复位为 7（本轮实测 6 → 7） | 队列每 6 轮或每次进 Android 后跑一次 `set_active a`，避免连续实验把它耗到 0 |
| 固件故障分支（`firmware_fault`） | 状态名与 held 同时出现，写入口全部拒绝 | 尚未真机覆盖 | 按 held 处理：保存日志、`reboot`；仍不通再请人 |

驻留 loader 的 `getvar build-id` 现在返回 `unknown`（2026-10-28 实测），恢复脚本对这一项从固定哈希断言改为记录，`reboot.json` 里也照旧写 `loader_build_id`。恢复日志里看到 `unknown` 按正常值处理，不当作身份异常；需要核对 loader 版本时用镜像文件哈希与冻结清单，不用这个字段。

## 6. 缩短 50 秒的三条路

1. 内核在 park 之前把状态写进 `kernel_live` 的一个字段，loader 在观察循环里读到就结束本轮等待。预期 1～2 秒，要同时改内核与 loader。
2. loader 在日志环里看到 `GPU probe requires host cold reset` 或 host-stop banner 就判 held。同样 1～2 秒，只改 loader，代价是要解析新增日志字节。
3. 只调小 `SILENCE_SECONDS`。改动最小，代价是真正卡住但仍在运行的短时停顿会被误判成 hung。

三条都要重新验收，本轮不做。省这 50 秒的收益：一轮 420 秒的实验里占 12%，队列每轮都要付。

## 7. 证据位置

- 本轮：`docs/progress/evidence/k90auto/kernel-12377-attr-teardown-a/run/`（`commands.txt`、`s000.log`、`stop1.log`、`stop2.log`、`hung-snapshot.log`、`system-upload.log`），Android 恢复记录 `docs/progress/evidence/k90auto/loader-recover-kernel-12377-attr-teardown-a/`。
- 16 轮时间差来自各轮 `run/commands.jsonl` 与 `run/reboot.json`。
- 本轮第一次尝试因 `STAGE_SYSTEM_IMAGE` 用了工作区相对路径而失败（`stage-system.sh` 会切到 `hackios-xnu-kernel/`），那次运行记在 `run-void-missing-system/`，不作结论依据。