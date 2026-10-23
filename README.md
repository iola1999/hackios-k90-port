# hackios-k90-port — HackiOS 移植工作区（REDMI K90 / annibale）

把 [HackiOS](https://github.com/oosexgang/hackios-xnu-kernel)（XNU + 未修改 iOS 16.5 用户态）移植到 **REDMI K90（SM8750，代号 `annibale`）**。本仓库保存文档、脚本、配置和两个代码子模块的版本。项目仍在实验阶段，当前体验以启动桌面、观察界面及协助调试为主。其他机型需要独立移植和验收。

## 1. 上游来源、致谢与仓库关系

本项目基于 [OOSEX GANG 的 HackiOS 内核仓库](https://github.com/oosexgang/hackios-xnu-kernel)和[用户态仓库](https://github.com/oosexgang/hackios-xnu-userland)开展 K90 移植。感谢原作者与贡献者开放 XNU 移植、EFI loader、用户态适配、镜像构建、图形工具及相关文档；本项目沿用这些实现，并在其基础上维护 annibale 适配和调试修复。

| 仓库 | 职责与来源 | 本项目分支 |
|---|---|---|
| [hackios-k90-port](https://github.com/iola1999/hackios-k90-port) | 本顶层工作区，保存文档、辅助脚本及两个子模块的具体版本 | `main` |
| [hackios-xnu-kernel](https://github.com/iola1999/hackios-xnu-kernel) | 保留原内核仓库历史，维护 K90 的 XNU、loader 和固件相关修改 | `k90-port` |
| [hackios-xnu-userland](https://github.com/iola1999/hackios-xnu-userland) | 保留原用户态仓库历史，维护用户态适配、APFS 与图形构建工具 | `k90-port` |

两个代码仓库已建立与对应上游的 GitHub fork 关系，默认分支均为 `k90-port`。顶层工作区为独立仓库，默认分支为 `main`。三个仓库均已公开。原有许可证和版权声明保留，各组件许可范围见所属仓库的 `LICENSE` 及文件声明。上游的 POCO X5 Pro／QEMU 功能说明按其原有设备范围阅读，K90 的验证结果见本工作区的调试文档。

## 2. 当前适配进展

截至 2026-10-24，真机已进入 iOS 16.5 桌面，当前优先处理触摸和卡顿。下表包含正在进行的本地调试结果；触摸、电池及启动任务的最新修改尚未全部提交，克隆公开仓库后需要核对实际 commit 和构建产物。

| 项目 | 当前结果与限制 |
|---|---|
| 启动与桌面 | XNU、APFS、launchd、SpringBoard 已在 K90 上运行，取得主屏幕截图并经用户确认；QEMU 也已有启动记录 |
| USB 调试 | 驻留 loader 可上传 RAM 系统盘、运行内核、停止内核并读回日志和截图；整机重启后需重新上传系统盘 |
| 显示与性能 | 壁纸和 Dock 半透明效果曾实测恢复；后续测试仍出现壁纸启动超时，最新反馈确认顶部小组件已加载。时钟指针仍有数秒一次的卡顿 |
| 图形加速 | 当前使用 CPU 软件渲染，OpenGL ES 对照镜像使用 Mesa `softpipe`；K90 GPU 加速尚未启用，当前调试配置为 `cpus=1 bootcpu=1` |
| 触摸 | 本地驱动已读到 Goodix 9916K 芯片信息，触摸报告仍为零；用户确认点击、滑动无响应 |
| 电量与充电 | 本地调试已从 TI BQ27Z561 读到电量、电压、温度，并交给 iOS 电源服务；充电状态显示与实际情况仍不一致 |
| 其他外设 | 联网、摄像头、震动等待触摸可操作后继续验证；按键、音频、手电等也尚未完成 K90 的可用性验收 |
| 数据持久化 | iOS 系统盘与运行数据走 RAM。当前真机启动方式会写实验槽的 `boot` 分区；保留可启动的 Android 槽用于回退 |

较早的已验证过程见[真机运行记录](docs/progress/2026-10-23-runtime-debugging.md)和 [QEMU 启动记录](docs/progress/2026-10-23-ios-booted-qemu.md)。外设驱动已有源码、编译通过和用户实际操作成功需要分别记录。

## 3. 开始前准备

准备一台已解锁 bootloader 的 REDMI K90、可传数据的 USB 线，以及能使用 `adb`、`fastboot`、Git、Python 3 的电脑。原始分区备份需要已授权的 root／恢复环境；缺少权限就先停在检查阶段。解锁或重新锁定 bootloader 涉及清除用户数据，本文从已解锁的设备开始，参见 [AOSP bootloader 说明](https://source.android.com/docs/core/architecture/bootloader/locking_unlocking)。

备份范围为重要分区与 `userdata` 尾部。记录 Android 版本、当前槽位、解锁状态和分区清单，确认 Android 能正常启动，OTA 更新及快照合并已完成。Virtual A/B 的动态分区使用快照和共享存储，切换槽位仍使用共享的用户数据，参见 [AOSP Virtual A/B](https://source.android.com/docs/core/ota/virtual_ab)。

```sh
git clone --recurse-submodules https://github.com/iola1999/hackios-k90-port.git
cd hackios-k90-port
git submodule status
```

先读 [AGENTS.md](AGENTS.md) 和[排查与协作手册](docs/plan/debugging-and-collaboration.md)，也可以直接把第 7 节提示词交给 Agent。子模块初始状态指向顶层记录的 commit；如需修改代码，再由 Agent 创建工作分支。

构建可参考 [Docker 环境](docker/README.md)、[Linux 内核构建说明](docs/analysis/kernel-build-linux.md)和 [UEFI 构建说明](hackios-xnu-kernel/uefi/README.md)。`ios165/fetch.sh` 从 Apple CDN 下载所需内容，脚本记录约 7.4 GB 下载量、约 8 GB 提取期间磁盘用量；SDK、UEFI、XNU、Mesa 和构建副本另计。分区备份空间与构建空间分别计算。

K90 构建需要匹配的 UEFI、DTB、phone loader、内核和两份 APFS 镜像。`common/devices/annibale.conf` 仍有待核对的 UEFI／DTB 默认路径及旧实验参数 `cpus=8`；Agent 应逐项确认输入后构建。历史文档中的 `out/handoff-*.img` 是当次本地产物，需要重新生成并核对大小、SHA-256 与来源。首次体验先做桌面启动验收，再逐项启用外设。

## 4. 备份哪些内容，需要多少空间

### 备份范围

首次写入实验槽之前完成备份。每份备份记录分区名、原始字节数、Android 版本、槽位和 SHA-256，至少再保存一份副本到另一块磁盘。备份晚于修改，只能恢复备份时刻的内容。

| 范围 | 应保存的内容 |
|---|---|
| 启动与验证分区 | 两个槽位的 `boot`、`init_boot`、`vendor_boot`、`dtbo`、`vbmeta`、`vbmeta_system`，按本机实际存在的分区备份；当前实验直接改写的目标是所选实验槽的 `boot` |
| 固件与启动组件 | 本机实际存在的 `xbl`、`xbl_config`、`abl`、`uefi`、`tz`、`hyp`、`aop`、`aop_config`、`devcfg`、`keymaster`、`qupfw`、`pvmfw`、`modem`、`modemfirmware`、`dsp`、`bluetooth` 等及其 A/B 副本；保留完整分区清单，由 Agent 检查遗漏 |
| 本机校准与状态 | `persist`、`vm-persist`、`modemst1`、`modemst2`、`fsg`、`fsc`、`keystore`、`devinfo`、`secdata`、`metadata`、`misc` 等实际存在的分区；这些镜像只供原设备恢复，并保存在私有备份目录 |
| 分区表 | 每个 UFS LUN 的主／备 GPT、LUN 容量、扇区大小和分区映射；本测试机为 6 个 LUN，实际布局需重新读取 |
| `userdata` 尾部 | 保存从分区末尾向前指定长度的原始字节，同时记录分区总字节数、尾部起始偏移、长度和 SHA-256；本项目已有范围为 2,492,227,584 字节，约 2.32 GiB |

尾部备份覆盖的是记录的字节区间。Android 后续写盘会改变文件系统状态，尾部快照也会过时；恢复前需要停止相关写入并重新核对数据布局。当前启动路径通过 USB 使用 RAM，常规切回 Android 保留现有 `userdata`、`metadata`、`super` 和 GPT。

### 空间估算

按上表具体分区名在本测试机清单中筛选，共 55 个重要分区。下表由这些分区的原始长度、对应 gzip 文件大小及尾部长度计算，MiB／GiB 按 1024 换算。新设备以自己的分区清单和选定尾部长度为准。

| 内容 | 本机实测大小／计算结果 |
|---|---:|
| 单个 `boot_a` 或 `boot_b` 原始镜像 | 96 MiB |
| 55 个重要分区原始数据合计 | 约 1.76 GiB |
| 对应 gzip 文件合计 | 约 622.6 MiB |
| `userdata` 尾部原始数据 | 约 2.32 GiB |
| 重要分区原始镜像 + 尾部 | 约 4.08 GiB |
| 重要分区 gzip + 尾部 | 约 2.93 GiB |
| 同时保留重要分区原始镜像、gzip 与尾部 | 约 4.69 GiB，GPT 与清单另计 |

本机按至少 **5 GiB** 准备一套备份及解包校验空间；保存在另一块磁盘的副本需要另计容量。构建目录另留空间。其他设备、固件版本或尾部范围变化后，重新求和；压缩前按原始大小预算，压缩率以实际文件为准。

### 单个分区备份示例

以下仅演示读取 `boot_a`，本轮备份还需覆盖上表与本机清单。先填写 `ANDROID_SERIAL`，`BACKUP_DIR` 使用自己选择的私有目录。命令在电脑上执行，`adb exec-out` 的重定向把数据保存到电脑。

```sh
: "${ANDROID_SERIAL:?请先填写目标设备序列号}"
: "${BACKUP_DIR:?请先填写备份目录}"
mkdir -p "$BACKUP_DIR"
adb -s "$ANDROID_SERIAL" shell 'su -c id'
adb -s "$ANDROID_SERIAL" shell 'su -c "blockdev --getsize64 /dev/block/by-name/boot_a"'
adb -s "$ANDROID_SERIAL" exec-out 'su -c "cat /dev/block/by-name/boot_a"' > "$BACKUP_DIR/boot_a.img"
wc -c < "$BACKUP_DIR/boot_a.img"
adb -s "$ANDROID_SERIAL" shell 'su -c "sha256sum /dev/block/by-name/boot_a"'
shasum -a 256 "$BACKUP_DIR/boot_a.img"
```

逐步检查命令是否成功。确认 root 权限后再读取分区；本地字节数必须与 `blockdev` 输出一致，SHA-256 必须与设备侧一致。没有完成校验就保留原设备状态，先排查传输。已有同名备份应换新目录，保留首次写入前的版本。Linux 主机也可使用 `sha256sum` 计算本地哈希。

### `userdata` 尾部备份示例

从本机读取分区大小，再计算尾部起始偏移。下例默认保存末尾 2,492,227,584 字节，长度来自本项目原有尾部范围；Agent 应核对本次需要保护的范围后确定 `TAIL_BYTES`。示例采用 4096 字节读取块，先检查对齐。使用新的备份目录，在 Bash 中执行：

```bash
(
    set -euo pipefail
    : "${ANDROID_SERIAL:?请填写目标设备序列号}"
    : "${BACKUP_DIR:?请填写新的私有备份目录}"
    TAIL_BYTES=${TAIL_BYTES:-2492227584}
    USERDATA_BYTES=$(adb -s "$ANDROID_SERIAL" shell 'su -c "blockdev --getsize64 /dev/block/by-name/userdata"' | tr -d '\r\n')
    [[ "$USERDATA_BYTES" =~ ^[0-9]+$ && "$TAIL_BYTES" =~ ^[0-9]+$ ]]
    (( TAIL_BYTES > 0 && TAIL_BYTES <= USERDATA_BYTES ))
    (( USERDATA_BYTES % 4096 == 0 && TAIL_BYTES % 4096 == 0 ))
    OFFSET_BYTES=$((USERDATA_BYTES - TAIL_BYTES))
    SKIP_BLOCKS=$((OFFSET_BYTES / 4096))
    TAIL_BLOCKS=$((TAIL_BYTES / 4096))
    mkdir -p "$BACKUP_DIR"
    test ! -e "$BACKUP_DIR/userdata-tail.bin"
    adb -s "$ANDROID_SERIAL" exec-out "su -c 'dd if=/dev/block/by-name/userdata bs=4096 skip=$SKIP_BLOCKS count=$TAIL_BLOCKS 2>/dev/null'" > "$BACKUP_DIR/userdata-tail.bin"
    test "$(wc -c < "$BACKUP_DIR/userdata-tail.bin")" -eq "$TAIL_BYTES"
    printf '%s\n' "partition=userdata" "partition_bytes=$USERDATA_BYTES" "offset_bytes=$OFFSET_BYTES" "tail_bytes=$TAIL_BYTES" > "$BACKUP_DIR/userdata-tail-range.txt"
    shasum -a 256 "$BACKUP_DIR/userdata-tail.bin" > "$BACKUP_DIR/userdata-tail.sha256"
    cat "$BACKUP_DIR/userdata-tail-range.txt" "$BACKUP_DIR/userdata-tail.sha256"
    adb -s "$ANDROID_SERIAL" shell "su -c 'dd if=/dev/block/by-name/userdata bs=4096 skip=$SKIP_BLOCKS count=$TAIL_BLOCKS 2>/dev/null | sha256sum'"
)
```

比较最后的设备侧哈希与本地哈希。二者不同就停止后续写入，检查读取错误及 Android 是否仍在改变该范围，必要时在能读取该分区且停止文件系统写入的环境重新备份。尾部文件不能直接作为 `userdata` 的分区镜像刷入；恢复必须使用记录的偏移和长度，并核对同一设备、同一分区布局及备份后的写入情况。本项目早期尾部备份曾晚于首次写入，相关限制见[恢复记录](docs/analysis/2026-10-23-android-systemui-recovery.md#3-与-userdata-暂存操作的关系)。

原始镜像、分区清单和设备标识留在 Git 忽略的 `annibale-backup/` 或其他私有位置。备份方法与历史比较见 [docs/backup/](docs/backup/)，本地备份文件随各自工作区保存。

## 5. 如何启动 iOS

本机实测路径是向实验槽的 `boot` 写入驻留 loader，随后通过 USB 把 iOS 系统盘、内核和 root 镜像传入 RAM。Android 位于 B 槽、实验位于 A 槽是这台测试机的配置；新设备必须先验证自己的 Android 槽。`fastboot boot` 临时启动的适用镜像需要另行验证。

### 安装驻留 loader

先完成备份，并由 Agent 核对产物、目标设备和槽位。以下变量均由检查结果填写：`ANDROID_SLOT` 是已验证能正常启动 Android 的槽位，`TEST_SLOT` 是另一槽位，值为 `a` 或 `b`；`LOADER_IMG` 指向已核对的 K90 loader 启动镜像。

```sh
adb -s "${ANDROID_SERIAL:?}" reboot bootloader
fastboot -s "$ANDROID_SERIAL" getvar product
fastboot -s "$ANDROID_SERIAL" getvar current-slot
fastboot -s "$ANDROID_SERIAL" getvar unlocked
```

确认上述结果后，逐条执行写入和启动命令。`flash` 会覆盖目标 `boot` 分区，必须已有该分区的已校验备份。

```sh
: "${ANDROID_SERIAL:?}"
: "${ANDROID_SLOT:?请填写已验证的 Android 槽位}"
: "${TEST_SLOT:?请填写实验槽位}"
: "${LOADER_IMG:?请填写已核对的 K90 loader 镜像}"
if { [ "$ANDROID_SLOT:$TEST_SLOT" = b:a ] || [ "$ANDROID_SLOT:$TEST_SLOT" = a:b ]; } && [ -s "$LOADER_IMG" ]; then
    fastboot -s "$ANDROID_SERIAL" flash "boot_${TEST_SLOT}" "$LOADER_IMG"
else
    printf '%s\n' '槽位或镜像检查未通过，停止操作。'
fi
```

镜像检查与 `flash` 均成功后，再逐条切换槽位和重启；每条命令都检查退出码及输出中的 `FAILED`，失败就停止。

```sh
fastboot -s "$ANDROID_SERIAL" set_active "$TEST_SLOT"
fastboot -s "$ANDROID_SERIAL" reboot
fastboot -s xnuloader getvar product
fastboot -s xnuloader getvar screen
```

loader 的设备标识应为 `xnuloader`。当前面板配置实测为 `1156 2510 4624`，依次表示宽、高、每行字节数。每步同时检查退出码和输出中的 `FAILED`；出现失败就停止，重新确认设备状态。完整流程的恢复入口见下一节。

### 上传 RAM 镜像并运行

以下在 `hackios-xnu-kernel/` 中执行。`userland/system.apfs` 必须已生成且与本轮内核、root 镜像匹配；`KERNEL_IMG` 与 `ROOT_APFS` 填写该目录下可访问的已校验文件路径。

```sh
: "${KERNEL_IMG:?请填写本轮内核文件}"
: "${ROOT_APFS:?请填写本轮 root.apfs 文件}"
mkdir -p out
bash tools/stage-system.sh
python3 xnuloader/mkpayload.py -o out/first-run.bin "kernel=$KERNEL_IMG" "ramdisk=$ROOT_APFS" --cmdline "debug=0x10e serial=3 cpus=1 bootcpu=1 epoch=$(date +%s) -v"
fastboot -s xnuloader stage out/first-run.bin
fastboot -s xnuloader oem run
fastboot -s xnuloader getvar result
```

逐条确认成功后再继续；`result: running` 还需结合 SpringBoard 日志和实际画面验收。系统盘一次上传实测约 2.49 GB、62 秒，耗时随主机和 USB 状态变化。loader 持续运行期间可复用 RAM 系统盘，整机重启后重新上传。

上例先验收桌面，外设参数另行逐项验证。镜像中已经包含所需 Mesa 库后，才增加 `gl=1` 测试 OpenGL ES；`touchscreen=2`、电池及其他外设按相应实现和实测结果启用。交互体验不设置 `loader_return_after` 自动退出时限。系统盘继续使用 USB RAM 路径，不向 `userdata` 尾部暂存，不启用 `ufs_write=1` 或 `var_store`。

## 6. 如何回到 Android

loader 的普通 `reboot` 会按当前活动槽启动。完成实验后，先进入手机原厂 LK FASTBOOT，再选择此前验证过的 Android 槽。iOS／loader 无响应可使用电源键与音量下进入 FASTBOOT；主机能控制 loader 时可先用 `fastboot -s xnuloader oem stop` 停止内核、保存日志，再进入原厂 FASTBOOT。

确认 `fastboot devices` 中已出现 Android／LK 的目标序列号，读取 `product` 和当前槽位后执行：

```sh
fastboot -s "${ANDROID_SERIAL:?}" getvar product
fastboot -s "$ANDROID_SERIAL" getvar current-slot
fastboot -s "$ANDROID_SERIAL" set_active "${ANDROID_SLOT:?请填写备份时记录的可启动 Android 槽位}"
fastboot -s "$ANDROID_SERIAL" reboot
```

本项目测试机的 `ANDROID_SLOT=b`。切回后检查 Android 完成启动、通知栏／手势条、文件及重要应用数据。切换槽位只改变启动选择；已写入实验槽的 loader 会保留。

需要恢复实验槽的原 `boot` 时，先解压并校验首次实验前的对应镜像，再在原厂 FASTBOOT 中写回同名分区。例如，确认 `TEST_SLOT` 为实际实验槽、`ORIGINAL_BOOT_IMG` 为其原始备份后，使用 `fastboot -s "$ANDROID_SERIAL" flash "boot_${TEST_SLOT}" "$ORIGINAL_BOOT_IMG"`，随后选择已验证的 Android 槽重启。常规退出无需恢复其他固件、GPT、`metadata` 或 `userdata`。

若切回 Android 后界面异常，先读取崩溃日志；本项目曾定向修复 SystemUI／MIUIAod 编译缓存，见[修复记录](docs/analysis/2026-10-23-android-systemui-recovery.md)。该方法仅用于日志匹配的故障。恢复出厂设置、清除 `userdata`、锁定 bootloader，以及批量刷回旧分区镜像，都需要另行评估数据影响。

## 7. 发给 AI Agent 的提示词

复制下面这段即可；Agent 应先完成检查和备份，再给出适用于你设备的启动命令。

```text
请协助我体验 https://github.com/iola1999/hackios-k90-port。先阅读 README、AGENTS.md 和排查与协作手册，问清我的设备、电脑系统和数据保护要求，再只读核对真实机型、bootloader/root 权限、Android 槽位、OTA 状态及分区大小。按 README 备份重要分区与 userdata 尾部，先计算空间，记录尾部起始偏移和长度，再核对字节数与 SHA-256，并准备恢复方案。核对公开 commit 与最新调试结果的差异，准备匹配的 K90 构建产物；保留可启动的 Android 槽，系统盘只走 USB RAM。写分区或切换槽位前，列明设备、目标、文件哈希及恢复命令，等我确认。先验收 iOS 桌面，再单独验证触摸和性能；结束时帮我切回 Android 并检查数据。不要自动解锁／锁定 bootloader、清数据、修改 GPT，或使用 userdata 尾部暂存。
```

## 8. 工作区结构与版本

```text
hackios-k90-port/
├── docs/analysis/         调研、故障分析和检查记录
├── docs/backup/           备份方法与历史比较
├── docs/plan/             操作手册、计划与经验
├── docs/progress/         真机及 QEMU 运行记录
├── docker/               Linux 构建环境
├── tools/                主机辅助脚本
├── annibale-backup/       本机分区备份与校验清单，Git 忽略
├── hackios-xnu-kernel/    内核、loader、UEFI 子模块
└── hackios-xnu-userland/  用户态及镜像工具子模块
```

两个子模块的 `origin` 指向本项目的 fork，`upstream` 指向 OOSEX GANG 原仓库。本项目在 `k90-port` 维护移植修改，顶层仓库记录子模块的具体 commit。新克隆若尚未配置 `upstream`，可按第 1 节 URL 添加；更新上游前先检查本地修改并评估兼容性。

kernel 的 `common/setup.sh` 把 userland 检出到同一构建树，以 `.userland.git` 管理。它与顶层并列的 userland 子模块需要分别核对版本。首次建立构建树使用以下命令，之后比较 overlay 与顶层固定的 userland commit；分支已经前进时，由 Agent 在干净工作树中对齐到选定版本。

```sh
cd hackios-xnu-kernel
USERLAND_URL=https://github.com/iola1999/hackios-xnu-userland.git USERLAND_REF=k90-port common/setup.sh
common/ugit rev-parse HEAD
git -C ../hackios-xnu-userland rev-parse HEAD
```

已有构建树先检查状态。`common/setup.sh` 会尝试更新既有 overlay，保留其他任务的未提交修改；宿主缺失依赖按脚本输出补齐。进一步调试见[真机调试手册](docs/plan/device-test-playbook.md)，其中带具体日期和 `handoff-*` 文件名的内容按对应实验阅读。旧进度中的分区暂存路径已经停止使用，当前启动流程以本页的 USB RAM 路径为准。
