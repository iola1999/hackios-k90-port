# NAS 备份补充记录（2026-10-22）

NAS 位置：`${BACKUP_DIR}/`

## 1. 布局（最终形态）

- `adb_partition_backup_annibale_20260426_022802/` — 四月原始备份（124 raw + SHA256SUMS + meta），**一个字节未动**：补入前对其做过全量 `shasum -c`（124/124 OK）；一度试验过"对齐原格式追加"，已完全回滚（SHA256SUMS.txt 恢复 124 行/9834 字节，backup-log.tsv 恢复 13615 字节，逐字节校验）。
- `supplement-20261022/` — 本次补充，**独立目录、自有格式**（gzip + 双清单 gz/raw + GPT 转储），内含 README.md 说明格式与恢复方法。落盘后已在 NAS 侧 `shasum -c` 复核 OK。

## 2. 补充了什么（四月备份没有的）

1. 4 个四月有意跳过的分区（本次作为状态快照）：`dbg`(sda3, 32KB)、`xbl_ramdump_a`(sde28, 2MB)、`xbl_ramdump_b`(sde62, 2MB)、`xbl_sc_logs`(sde80, 128KB)。注：`dbg` 内容与四月 `bk01.img` 逐字节相同（出厂相同空白区，类似 keystore/bk04 的重复关系）。
2. **二进制 GPT 转储**（四月只有文本清单）：6 个 UFS LUN 的头/尾各 32KB + 扇区数表 `units.txt`。

## 3. 对比记录（本次会话产出，详见主文档 §4）

共同 119 分区：113 逐字节一致；6 差异可解释（init_boot_b=KernelSU 后刷；modemst1/2、persist、metadata、vm-persist=运行时自然写入）。四月独有 5 个日志垃圾区未从 Mac 侧重复（当时已跳过）：ffu、gsort、mtdblk、qmcs、rescue。

## 4. SMB 小坑备忘

该 NAS 挂载不支持原子 rename（`write` 工具报 ENOTSUP），往 NAS 写文件要用直接 `cp`/重定向，不要用会先写临时文件再改名的工具。
