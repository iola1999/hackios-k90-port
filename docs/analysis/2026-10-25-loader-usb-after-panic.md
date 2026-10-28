# 内核 panic 之后 loader 命令通道无应答的实测记录

2026-10-25 早期真机实验多次出现「内核结束之后 loader 仍在 USB 上枚举，但 fastboot 命令不再回包」。第 1～3 节保留旧 loader 的现象与未分离的条件；后续 v7 已完成空闲、传输中止和 GPU 停止后的恢复验收，见第 4 节。当前操作按[真机调试手册](../plan/device-test-playbook.md#6-故障定位与恢复)执行，通用方法见[排查与协作手册](../plan/debugging-and-collaboration.md#5-用状态和资源归属理解设备行为)。

## 1. 现象

设备在 `fastboot devices` 中仍以 `xnuloader` 出现，ioreg 中可见 VID `0x18d1`、PID `0xd00d`、一个配置；对 `getvar`、`oem log`、`stage`、`reboot` 全部超时且无任何部分输出。`lc_blocked_cmd` 只拒绝 held 状态下可能改写资源的命令，查询、日志和重启仍有处理入口。拒绝回复会产生 `FAIL` 正文，fastboot 通常显示 `FAILED`；本轮全部无输出，未取得命令已完成分派或拒绝的记录。

## 2. 逐次记录

| 运行 | 时间（UTC） | cmdline 中的 `adreno8_keep` | 收尾日志 | 之后命令通道 |
|---|---|---|---|---|
| r5 预检轮 | 20:05 前后 | 1 | `panic(cpu 0 …): Process 1 exec of /sbin/launchd failed, errno 2 @kern_exec.c:7154` → `Please go to https://panic.apple.com to report this panic` → `adreno8: GPU probe requires host cold reset before reusing kernel memory` | 无应答（`get_staged` 120 秒 0 字节） |
| cbscan-r1 第 1 次 | 20:49:57 | 1 | 同样的 launchd panic → `== END OF LOG ==`，无 cold-reset 行 | 正常（12 秒后取回 32,767 字节） |
| cbscan-r1 第 2 次 | 20:50:35 | 1 | 同样的 launchd panic | 正常 |
| cbscan-r1 第 3 次 | 20:52:15 | 1 | 同样的 launchd panic → `== END OF LOG ==`，无 cold-reset 行 | 无应答（21:00 起 `getvar` 30 秒超时） |
| cbscan-r2 | 20:56 之后 | 1 | 同样的 launchd panic → `adreno8: GPU probe requires host cold reset before reusing kernel memory` | 无应答（+40 秒起 `getvar` 30 秒超时） |
| m-bit 轮 | 21:02 起 | 未运行 | 无 | 无应答（`stage`、`oem log` 各 60 秒超时，`reboot` 90 秒超时） |

对照：桌面轮（20:20–20:35）没有内核 panic，系统在 `04:44:16` 停止推进之后 loader 仍然即时应答（`getvar` 0.02 秒、`oem log` 与 `get_staged` 每轮成功），最后 `reboot` 被受理。

## 3. 核对结论

「`adreno8_keep=1` 保留 + 内核 panic」在所有五次运行里都出现了，包括之后命令通道仍然正常的 cbscan-r1 第 1、2 次。仅凭这个组合无法判断是否会失去通道。

与失去通道同时出现的两个条件：

- `adreno8: GPU probe requires host cold reset before reusing kernel memory` 出现在 r5 与 cbscan-r2 的末尾，这两次都失去通道；cbscan-r1 的三次都没有这一行
- 失去通道的 cbscan-r1 第 3 次与 cbscan-r2，都在内核运行期间以约 0.15 秒的间隔连续执行过 `oem log` + `get_staged`

现有数据分不开这两个条件，也无法排除它们共同作用。这批旧 loader 运行进入无应答状态后，`reboot` 也未恢复，最终经用户按键进入 LK；恢复之后 loader 的 `reboot` 正常（实测 7.6 秒回到 `xnuloader`）。该结果只覆盖这些运行和旧实现，v7 的后续验证见第 4 节。

## 4. v7 的恢复修订与验收边界

反复请求用户按键增加了每轮实验的等待和操作成本。后续审查先检查 USB 请求生命周期：v6 的独立恢复循环会丢弃 OUT 命令完成和部分 IN 完成事件，重建时修改的全局缓冲也可能与调用方持有的旧指针不一致。abort 或 halt 返回后，设备仍可能访问原缓冲，直接重新分配无法确认传输已结束。

提交 `7160d4d` 的 v7 使用统一事件处理，等待应答期间收到的 OUT 完成事件保留并交付一次；每笔陈旧 IN 请求最多申请一次 abort，仅由匹配且有效的终止通知解除缓冲归属。空闲命令接收超过等待预算后，仍接收下一条完整命令；已经放弃的数据传输迟到后，只结束原请求。无法确认终止的缓冲继续保留至复位。实现见[loader_06_usb_entry.inc](../../hackios-xnu-kernel/xnuloader/loader_06_usb_entry.inc)，完整检查与产物见[恢复审查记录](../progress/2026-10-25-gpu-resume-review.md#4-loader-v7-真机验收)。

v7 真机确认 build-id 后，空闲 15 秒的首条查询正常，完整截图读回 11606240 字节；另一次截图传到 1 MiB 后中止主机进程，等待 12 秒，查询和 USB 重启仍成功。GPU 停止后第 65 秒可读到 `hung-held`，随后软件重启观察到断开、17.46 秒重新枚举及 `idle`。这组结果覆盖本轮输入和一次中止实验；固件同步调用的全部失败方式、所有旧故障的独立原因仍未确认。

资源保留与 USB 可用性分别验收。`hung-held` 允许命令循环应答，内核与设备的映射和内存仍需保护。日志中的 `requires host cold reset` 来自资源保留路径，本身没有 USB 操作；修改超时或恢复逻辑仍需保留该限制。

## 5. 恢复决策与人工操作

先合并检查 stdout、stderr、退出码、`FAILED`、实际耗时与最后成功动作。`getvar` 正文常在 stderr，只读 stdout 会遗漏正常回复。随后查询枚举与身份，区分 loader、LK 和 Android，再按操作手册选择状态查询、日志读取或软件复位；同一设备的命令串行执行。

`reboot` 需要 USB 接收并分派命令。annibale 分支先尝试回复，再调用 PSCI_SYSTEM_RESET；回复失败后也可能复位，验收需要观察 USB 断开、重新枚举及新状态。命令接收已经停滞，重复发送 reboot 可能继续无效；主机超时也不能单独确认复位是否发生。

软件恢复失败后，记录本轮实际尝试与结果，再一次说明按键动作、预期 FASTBOOT 画面和主机后续步骤；同一个待用户动作合并提示。用户报告 Android 画面后，先重新检查 ADB 与槽位重试状态。阶段 17 曾因 A 槽重试耗尽回退 B 槽，已有 loader 经 ADB／LK 恢复，案例见[A830 专题第 8 节](2026-10-24-a830-command-startup.md#8-cpu-映射越界与-raw-自动复位)。

## 6. 阅读范围与待确认事项

本次补充读取到来源会话的 v7 部署、3a／3b 与 RAW 复位实验，相关输入和最后纳入阶段见[A830 专题第 10 节](2026-10-24-a830-command-startup.md#10-增量阅读范围)。旧版多次失联的采样频率与资源保留条件尚未做独立对照；v7 通过的用例只支持对应输入下的恢复行为。后续增加 USB 故障注入，仍要检查原请求的缓冲归属、下一条有效命令与复位后的身份。
