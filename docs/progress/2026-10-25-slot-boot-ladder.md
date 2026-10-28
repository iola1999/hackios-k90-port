# 槽位引导阶梯与 M_full 成功（2026-10-25）

本轮从「RAM boot 不接管」出发，先做 RAM boot 对照，再改走槽位引导，用五张镜像把「形态」与「部件」分开，最后新 loader 在真机跑起来并应答完整 build-id。设备序列号按约定掩码为 `519e…a70`；原始日志在 git 忽略的 `logs/device-boot-once/`，本轮的临时驱动日志在本地 `/tmp`。

## 1. 授权与边界

用户授权范围覆盖单次 RAM boot、软件 `reboot` 恢复，随后扩大为「设备能响应即可自行决定操作」，目标是让真机进入带图形加速的 iOS。本轮实际执行的动作：`fastboot boot` 三次尝试、`fastboot reboot` 一次、`adb reboot bootloader` 一次、`fastboot flash boot_a` 五次、`fastboot --set-active=a` 五次、只读 `getvar` 若干。未执行 `erase`、`oem`、`stage`、`oem logwrite`，未写 boot_a 以外的分区。

## 2. RAM boot 对照实验

目的是区分「RAM boot 通路坏」与「镜像差异」。镜像取 10-23 有接管记录的变体 A（`xnu-annibale-log.img`，1,263,616 B `e02ea4f8…`）。

| 轮次 | 发送 | boot 正文 | 观测 |
|---|---|---|---|
| 1（19:31:37Z） | 变体 A | `Sending 'boot.img' (1234 KB) OKAY [0.029s]` / `Booting OKAY [0.101s]` | 90 秒内 146 次枚举全部是 LK，零空枚举；期间有约 10.5 秒观测盲区（管道被截断导致驱动进程提前退出） |
| 2（19:33:49Z） | 变体 A | `Sending OKAY [0.029s]` / `Booting FAILED (usb_read failed with status e00002ed)` | 无法观测，设备随后复位进入 Android slot b |

第 2 轮说明「`Booting FAILED` 后设备从 USB 消失」本身就是设备离开 fastboot 的信号，脚本当时把它当作终止条件，挡住了后续观测；该行为已在脚本里改为记录后继续观测。

## 3. 槽位引导阶梯

每轮的固定序列：只读确认（`devices`、`product`、`current-slot`）→ 复算镜像哈希 → `flash boot_a` → `--set-active=a` → 复读 `current-slot` → `reboot` → 0.3 秒间隔枚举并记录空结果。

| 镜像 | shim | FD | loader | 外尾 DTB | 文件大小 | 结果 | 起来／回 LK 时刻 |
|---|---|---|---|---|---|---|---|
| v5 `89ed602e` | 176 `ddfccdd8` | `109c477b` | 73,216 `33f1cbde` | 合并 956,243 `b30f254e` | 2,222,080 | 成功 | +17.7s |
| F1 `9f11578c` | 176 | `85415cc4` | 73,216 `33f1cbde` | 空 110 `27c2b2f1` | 1,263,616 | 失败 | LK +7.00s |
| D `e17b8c2c` | 176 | `109c477b` | 78,848 `5fccaa8f` | 空 110 | 1,267,712 | 失败 | LK +7.34s |
| R_v5 `a4280f94` | 176 | `109c477b` | 73,216 `33f1cbde` | 空 110 | 1,265,664 | 失败 | LK +7.31s |
| **M_full `42a9591a`** | **368 `0a5cbe63`** | **`85415cc4`** | **78,848 `5fccaa8f`** | **合并 956,243** | **2,224,128** | **成功** | **+16.99s** |

两张成功件的外尾都是合并 DTB、体积在 2.22 MB 量级；四张失败件的外尾都是同一个 110 字节 `empty.dtb`、体积在 1.26 MB 量级。失败件回 LK 的时刻集中在 +7.0 至 +7.3 秒，成功件起来在 +17 秒附近，两类有各自稳定的时间签名。

R_v5 与 v5 只差外尾（合并 DTB 换成空 DTB），结果从成功变失败，这是外尾形态与成败相关的最直接一条。M_full 则同时换掉三个新部件并保留合并外尾，结果成功，说明新 shim、新 FD、新 loader 本身不是失败原因。

## 4. M_full 运行结果

UTC 19:54:18 写入 boot_a，19:54:24 `reboot`，19:54:41（+16.99s）枚举到 `xnuloader`，其间 50 次空枚举。身份查询各一次：

| 变量 | 正文 |
|---|---|
| `product` | `product: xnuloader` |
| `version` | `version: 0.5` |
| `build-id` | `build-id: 4f6ab13bdbab08314745e04ad77fcc8d6967e1d6` |
| `result` | `result: idle` |

`build-id` 是完整 40 位，与批准 BUILD_ID 逐字符一致。这是新 loader 第一次在真机运行并应答身份，此前所有候选（RAM boot 与槽位引导两条通道）都没有做到。

## 5. 判读

- 槽位引导通路可用：`flash boot_a` → `--set-active=a` → `reboot` 这条序列本身没有问题，v5 与 M_full 都通过它起来。
- 失败集中在「空外尾 + 1.26 MB」这一形态，四张同形态镜像全部失败，与部件组合无关。
- 新部件无罪：M_full 的三个新部件在合并外尾下正常启动。

## 6. 未解决项

- 变体 A（空外尾 `empty.dtb`、1,263,616 B）2026-10-23 有接管记录，2026-10-25 两次 RAM boot 都不接管。同一字节、同一设备，说明 10-23 之后设备或引导状态有变化，或 10-23 那轮观测本身不成立（当时无原始枚举日志，记录自标待验证）。现有数据分不开，未下定论。
- LK 的 `current-slot` 读哪一份元数据未确定：本轮实测序列 19:21 `a`、19:31 `a`、19:36 Android 侧 `ro.boot.slot_suffix=_b`、19:40 `b`、19:41 起连续 `a`。详见 [runbook](../analysis/local/device-boot-once-runbook.md) §3。
- `set_active b` 回 Android 未实测，见 [runbook](../analysis/local/device-boot-once-runbook.md) §8。

## 7. 证据

- RAM boot 记录：[2026-10-25-boot-once-trial.md](2026-10-25-boot-once-trial.md)
- 各镜像清单：`evidence/20261024T194110Z-candidateF1/out/MANIFEST.md`、`evidence/20261024T194110Z-candidateD/out/MANIFEST.md`、`evidence/20261024T194110Z-candidateR_v5/out/MANIFEST.md`、`evidence/20261024T194110Z-candidateM_full/out/MANIFEST.md`
- 驱动脚本与仿真：`tools/device-boot-once.py`、`tools/device_boot_common.py`、`tools/device_flow_support.py`、`tools/device_ladder.py`、`tools/test-device-boot-once.py`
- 执行手册：[device-boot-once-runbook.md](../analysis/local/device-boot-once-runbook.md)