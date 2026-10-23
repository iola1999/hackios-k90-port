# xnuloader/loader.c 拆分评估（2026-10-23）

结论先行：**拆得动（中等工作量，六片方案见下）；有必要拆（800 行约定 + 单函数 662 行已经大到观测困难），但必须排在设备轮之后**——拆分改 PE 产物字节，c.img 要重打，QEMU 回归 + task-20 变体隔离验收都要重跑一遍，设备轮前动它违背"上车产物冻结"纪律。

## 现状数据

4335 行、227 个 `static` 符号（函数+全局混计）。最大的函数与聚簇（行数=函数体）：

| 行数 | 函数 | 域 |
|---|---|---|
| 662 | run_kernel | 内核交接（args/DT/launch 三段可再分） |
| 184 | fb_command | 屏上控制台命令 |
| 131+90 | block_start / block_poll | USB BlockIo 会话 |
| 78 | efi_main | 入口编排 |
| 74 | charger_poll | 充电口探测 |
| 65+54+45+40 | block_io2_probe / ufs_survey / ufs_check_gpt / ufs_dump_super | 存储勘察 |
| 64 | parse_payload | XNUP 容器解析 |
| 59 | hc_take_back | 主机侧收尾 |
| 55 | choose_window | 物理内存窗口选择 |
| 53 | rdfile_load | userdata 尾预读 |
| 50 | ramfb_phone_screen | 屏 |
| 40 | usb_start | USB 栈起栈 |

## 六片方案（adreno8 拆分先例复用）

1. 平台表 + 屏：`platform_*` 表、fb/ramfb/splash、fb_command、ramfb_phone_screen。
2. USB/固件胶水：usb_start、charger_poll、hc_take_back、block_start/block_poll。
3. 存储勘察与预读：probe_one、ufs_*、block_io2_probe、rdfile_load、`oem probe/logwrite`。
4. 内存布局：choose_window、plan_layout。
5. 内核交接：run_kernel（先拆 args 准备 / DT 写入 / launch+日志回传 write_logs）、parse_payload。
6. 入口与命令：efi_main、inspect_storage 自动路径、命令分发。

跨片符号走 `loader_private.h`（adreno8 private.h 393 行先例，全 non-static + `nm` 核重）。

## 风险与消费方（拆分必须同 commit 覆盖）

- `xnuloader/build.sh` 单 .c 编译 → 多 .o 链接（lld-link 原生支持；F04 后 build.sh 只 15 行，改动面小）。
- 引用 loader.c 文本的活消费方实测就三处逻辑点：`tools/ufs-survey.py`、`tools/ufs-super.py`（按字符串/结构取参）、`common/new-device.sh`+`_template.conf`+`annibale.platform.c`（注释性指引，指向"平台表所在处"）。grep 复核过其余无。
- 产物字节必变 → c.img 重打包 + `--cmdline` 回放；trap 9 已由 F04 变体分产物结构性堵死，交替构建隔离三件套（task-20 验收项）直接当回归用。

## 必要性论证

AGENTS.md 约定：单文件 ≤800 行，大改文件净增长越线必须处理或在文件头写明不可拆理由；loader.c 已 5.4 倍越线且 task-19 刚大改（+193/−52）。run_kernel 662 行的单函数规模已经造成实测伤害：F09 布局校验要插在它中部，插入点定位全靠行号考古。不拆的代价是每次设备轮取证都在放大这个成本；拆的收益另有一条：平台表独立成片后，新 SoC 移植（new-device.sh 产物）不再往主干里粘 60 行表项。

## 排期

设备轮之后、与 redwood_* 系列同批（各自独立 commit，消费方同 commit 动）。验收 = kbuild 外全 host：拆分后每文件 ≤800、交替构建哈希隔离、QEMU 420s SpringBoard×2 零 panic、annibale 打包入口装的仍是 phone 产物且字符串命中与拆分前等价。
