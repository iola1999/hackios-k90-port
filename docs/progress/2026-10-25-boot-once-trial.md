# 单次 RAM 启动试验执行记录（2026-10-25）

本轮按 [runbook](../analysis/local/device-boot-once-runbook.md) 与 Lead 的最终指令执行一次 `fastboot boot`，随后按授权执行一次恢复 reboot。序列号在本文按隐私约定掩码为 `519e…a70`；原始日志在 git 忽略的 `logs/device-boot-once/`。

## 1. 执行前置（顺序固定）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 现场重新枚举 | `fastboot devices` | 单条 `519e…a70  fastboot`，rc=0，0.02 秒，仅一台设备 |
| 复算候选哈希 | 本地 `shasum -a 256` | `087a235297cc4945b7cf880c0e4f36b7e63c08d8534a63e0c882265fd66145ac`，与批准值一致；1,267,712 字节 |
| 引导程序身份 | `getvar product` | `product: annibale` |
| 当前槽位 | `getvar current-slot` | `current-slot: a`，与批准期望一致 |
| 电量 | `getvar battery-soc-ok`、`getvar battery-voltage` | `yes`、`4209`（≥4000） |

四项前置全部满足后发送，未降级任何条件。

## 2. 单次 boot

UTC 19:21:36Z 发送，主机 0.15 秒返回，退出码 0。原文：

```text
Sending 'boot.img' (1238 KB)                       OKAY [  0.029s]
Booting                                            OKAY [  0.107s]
Finished. Total time: 0.137s
```

## 3. boot 后 90 秒观察

间隔 3 秒枚举共 30 次，19:21:36Z 至 19:23:04Z，每次结果均为 `519e…a70  fastboot`（LK），没有出现 `xnuloader`。19:23:06Z 脚本按观察预算停止，退出码 1，未重试。

分类说明：`Sending` 与 `Booting` 的 OKAY 只确认 boot 命令被接受，不确认候选 loader 进入运行。持续枚举到的仍是 LK 标识，无法区分「未离开 LK」「执行后返回 LK」「早期启动失败且无可观测新枚举」三种情况。

## 4. 恢复（唯一一次）

触发条件按 Lead 授权：boot 已发出，且 90 秒观察窗内始终未枚举到 `xnuloader`。执行前读一次状态，设备仍在 LK 应答（`product: annibale`）。

UTC 19:23:23Z 发送 `fastboot -s <serial> reboot`，原文 `Rebooting                                          OKAY [  0.000s]`，退出码 0，只发一次。19:23:42Z（reboot 后约 19 秒）重新枚举到 `xnuloader`。

恢复后身份查询，每项一次：

| 变量 | 正文 |
|---|---|
| `product` | `product: xnuloader` |
| `version` | `version: 0.5` |
| `build-id` | `build-id: `（空值） |
| `result` | `result: idle` |

## 5. 结论

- boot 命令被 LK 接受（两行 OKAY），但候选 loader 未在 90 秒内接管 USB。
- 完整 build-id `4f6ab13b…` 未取得：没有以新身份枚举的 loader 可供查询。
- 恢复后应答为 `version 0.5`、build-id 空、`result: idle`，与 boot_a 内驻留的旧 loader 行为一致；本轮未对运行字节做 hash 校验，不能据此声称旧 loader 之外的任何镜像运行过。
- 设备最终可枚举，处于 loader 应答状态，不是 LK。
- 本轮执行中没有任何协议正文带 `FAILED` 的应答；`input` 阶段的已知 FAILED 现象属上一轮 LK 查询，本轮脚本未在 LK 上查 build-id／result。

## 6. 与 2026-10-24 L1 轮的可比性

两轮签名相同：`fastboot boot` 被接受、随后 90 秒只有 LK 枚举、无 `xnuloader`、恢复 reboot 后约 18–19 秒旧 loader idle 应答回来。L1 轮用户报告黑屏，本轮屏幕物理状态未从主机侧取得，需用户确认。两轮候选不同（L1 候选 B `35769541…`，本轮 `087a2352…`），共同点与差异点的归因需要另行设计对照，本轮不做。

## 7. 证据

- `logs/device-boot-once/boot-once-20261024T192136Z.log`（17,803 字节）：boot 流程与 30 次枚举原文
- `logs/device-boot-once/boot-once-20261024T192323Z.log`（1,856 字节）：恢复 reboot 原文
- 预检记录：[device-precheck-20261025.md](../analysis/local/device-precheck-20261025.md)
- 候选：[20261024T190638Z-candidate](evidence/20261024T190638Z-candidate/out/MANIFEST.md)

## 8. 本轮未做的事项

未执行 `flash`、`erase`、`oem`、`set_active`、`stage`、adb 命令；未第二次发送 boot；未重试任何失败命令；未调整观察窗口或判定条件；未读取或写入任何分区。