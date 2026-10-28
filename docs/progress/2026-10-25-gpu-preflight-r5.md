# GPU 预检 payload r5 运行记录（2026-10-25）

新 loader 在真机运行（build-id `4f6ab13bdbab08314745e04ad77fcc8d6967e1d6`，见 [槽位引导阶梯记录](2026-10-25-slot-boot-ladder.md) §4）之后，用 r5 payload 跑 GPU 预检到阶段 14。上一轮卡在阶段 9 的 GMU 固件检查，本轮通过；预检在阶段 14 的 SMMU 安全预检门禁处按设计终止。内核随后在用户态启动阶段因 `launchd` 缺失 panic，`result` 未转 `returned`。设备序列号掩码为 `519e…a70`。

## 1. 运行身份

| 项 | 值 |
|---|---|
| payload | `hackios-xnu-kernel/out/handoff-preflight-r5.bin`，28,413,448 B，`eccd474dc346513ae8f93fdbef29ee2a634bbfbaa03293089a4e22e3d6700c5b` |
| loader | `5fccaa8f4d86e992e64e3fa72703d2c8ad05d840d235d000bf5819696312974c` |
| 构建提交 | `4f6ab13bdbab08314745e04ad77fcc8d6967e1d6` |
| epoch | `1792871831`，与内核日志 cmdline 中的 `epoch=1792871831` 一致 |
| 根盘 | `hackios-xnu-kernel/out/handoff-ui-gen80000.apfs`，9,220,096 B `582b9fb28693ade94e0e374b3e55870ef986cea0a8660fc3e39d27b59f5c376e` |
| cmdline | `debug=0x8 rd=md0 debug=0x10e cpus=1 bootcpu=7 epoch=1792871831 adreno8=14 adreno8_pause=0 adreno8_watch=0 adreno8_keep=1 adreno8_return=0 adreno8_speed=1 adreno8_secure_preflight=1` |

装载摘要（内核日志前 12 行）：`payload entry 'kernel' size 124dcf0`、`'ramdisk' size 8cb000`、`resident image at pa 8c8000000 size 8cc000: it is the root (md0), the payload ramdisk is md1`。

## 2. 阶段推进

`result` 轨迹：`oem run` 后 +40s、+45s 均为 `running 0 0`，+50s 转 `hung-held 71624 0`，未出现 `returned`。

阶段 1 至 13 全部通过。上一轮失败的阶段 9 本轮通过：

```
adreno8: 9: gmu translation enabled: stream 5, context 2, root PA 0x8cb12c000
adreno8: 9: completed
adreno8: step 10: load GMU firmware and verify each segment
adreno8: 10: GMU firmware loaded: 0x15a50 bytes verified
adreno8: 10: completed
```

阶段 11 进入 SCM 与 HFI 路径：

```
adreno8: 11: SCM 0x42000601 returned 0, answer 0x1
adreno8: 11: SCM 0x42002801 returned 0, answer 0
adreno8: 12: gmu DTCM HFI version (0x3d74ff0) = 0x20070001
adreno8: 12: THE GMU'S MESSAGE QUEUES ARE UP
adreno8: 13: THE FIRMWARE HAS ITS ORDERS: 2 speeds, 12 bandwidth levels
```

阶段 14 出现 kind-5 资源请求，门禁判据是 SMMU context 3 的 SCTLR：

```
adreno8: MEM_ALLOC kind 5 handle 0x5 flags 0x1007 size 0x138000 align 0
adreno8: 14: smmu cb preflight (0x3dc3000) = 0x96cc51a
adreno8: 14: secure preflight: context 3 SCTLR 0x96cc51a is nonzero; the context bank fails the preflight
adreno8: 14: FAILED; the steps after it are not attempted
adreno8: keeping everything up (adreno8_keep): the GMU's firmware goes on running and answering
adreno8: over; the system goes on starting
```

`adreno8_cx.c` 的 announce／result 两行在本轮日志中没有出现，日志里不存在含 `announce` 的行。阶段 14 直接进入 SMMU 预检读值。

## 3. 未返回的原因

预检结束后内核继续启动，BSD root 是本次 stage 的小根盘（md0），APFS 挂载为 479 个文件、19 个目录；`load_init_program` 两次尝试后 panic：

```
BSD root: md0, major 1, minor 0
apfs: volume 0 "Data" of container 0 (at 0 MB): 479 files, 19 directories, 1909 blocks of 4096 used
load_init_program: attempting to load /usr/appleinternal/sbin/launchd.development
load_init_program: attempting to load /sbin/launchd
PANIC caller 0xfffffff0077cedcc: Process 1 exec of /sbin/launchd failed, errno 2 @kern_exec.c:7154
```

该根盘是 GPU 预检用的最小根盘，不含 `/sbin/launchd`，用户态无法启动。panic 与 GPU 路径无关，是 `result` 停在 `hung-held` 的直接原因。

## 4. 采集方式

- 第一次运行把日志采集压到挂死之后，`get_staged` 在 `Uploading …` 之后无数据，120 秒超时并留下 0 字节文件；此后 loader 命令通道不响应，直到物理重启。
- 第二次运行改为运行中取日志：+10s 与 +35s 各取一轮，两次字节完全相同（`9636ae44…`，各 72,560 B），说明日志内容在 +10s 前已经固定。结论是每轮取一轮实时日志足够，挂死后取快照只能作补充。
- 日志每行出现两次，是 loader 合成日志时的重复写入，不是执行两次。

## 5. 挂死后命令通道

`fb_command()` 在 `kernel_resources_held` 为真时按 `lc_cmd_denied()` 应回 `FAIL "a kernel may still hold memory or devices: reboot to start over"`（`hackios-xnu-kernel/xnuloader/loader_06_usb_entry.inc` L469-L471，判定函数在 `loader_01_base_log_dt.inc` L428）。两次实测都完全无输出（8 至 20 秒超时），命令处理没有走到该分支。设备在主机侧仍然枚举，说明 gadget 配置还在。推断是内核失控后 USB 控制器被留在异常状态、loader 的事件循环收不到请求；这一条只有观察，源码层面未确证。操作含义固定：内核 panic 或 hang 的每一轮都以物理重启收尾。

## 6. 产物

- 日志：`logs/kernel-r5/live1-t10.log`、`logs/kernel-r5/live2-t35.log`（各 72,560 B，git 忽略）
- 空文件：`logs/kernel-r5/hung-snapshot.log`（第一次运行的失败上传）
- payload 清单：`docs/progress/evidence/20261024T194110Z-candidateR_v5/out/` 与 `handoff-preflight-r5.bin` 同级产物
- 手册：[device-test-playbook.md](../plan/device-test-playbook.md) §4、§5