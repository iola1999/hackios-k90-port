# 功能全景扫描：红杉家底 × annibale 可行性 × 上游近况（2026-10-23 离线轮）

结论先行：**按键、电池、手电三项建议加入本期真机测试排期**（都吃已建成的 SPMI v7 主端，边际成本低）；Wi-Fi 固件的"必须真机 dump"前提作废（linux-firmware 已有）；音频维持不碰（结构全变，月级）。

## 1. 红杉真机驱动全家底（`xnu/files/bsd/dev/redwood_*.c`）与 K90 对照

| 驱动 | 红杉做法 | annibale 判定 |
|---|---|---|
| goodix（触摸） | SPI SE2 + TLMM，参数表化 | **已完成**：`touchscreen=2`（kernel cc9ff58） |
| haptic_hv（震动） | 新写，PMIC hv-haptics + SPMI v7 主端 | **已完成**：`hv_haptic=1..4`（kernel 2006f81） |
| buttons（按键） | PON KPDPWR/RESIN + PM7325 GPIO6，纯读，SPMI v5 | **可做，推荐加入本期**：annibale 设备树实证音量上=**TLMM GPIO6**（phandle 0x68f，/tmp/hw_check.dts #L9164，比红杉的 PMIC GPIO 还简单）；电源/音量下走 PMK8550 PON 块（`pmic-pon-log` #L9264 佐证 PON 在用）；SPMI 层直接换用 hv 驱动里那套 v7 通道（obsrvr 读不抢占属主）。上游 `drivers/input/power/qpnp-power-on.c` 可作 PON 寄存器对照 |
| battery（电池） | **loader 从常驻 UEFI 拿 charger 上下文轮询**，XNU 只读共享页（`battery_shared_pa`） | **可做，推荐加入本期，但换路线**：annibale 的 EDK2（annibalePkg）没有现成 charger 驱动，照抄 loader 缓存路线要写 EDK2 驱动，不划算；改走**内核经 SPMI v7 直读 PMIH010X FG**（DT `qcom,battery-charger` #L21713 证实是同族 qcom charger、非 PMIC-GLINK；ADC5-gen3/gen4 #L19682 起可做电池温度，上游驱动 `drivers/iio/adc/qcom-spmi-adc5-gen3.c` 已在库）。vendor 内核 qcom-fg 驱动 gh 可拉作寄存器对照 |
| torch（手电/闪光灯） | PMIC 闪光灯块，`torch=1`、`torch_secs/torch_max_s` | **可捎带**：DT `qcom,camera-flash/1/2`（#L771/L781，flash-source 0x6b3 / torch-source 0x6b7）指到 PMI 闪光灯外设，同样吃 SPMI v7；相机 L1b 也依赖它 |
| audio/sound/speaker/mic + adsp | bolero 编解码直怼 + APR/Q6 | **本期不碰**：SM8750 换 ADSP + SoundWire WCD9395 + WSA smart-amp，结构全变，月级；锁屏/桌面不需要 |
| adreno（GPU） | 22 步上电 + Mesa 桩 | 规划 + 固件已备齐（gpu-plan.md），L1a 离线可开工 |
| wifi/wlfw/qmi/net/apple80211 | WPSS-PIL + GLINK/QMI + ath11k(ahb) | WCN7850 = PCIe RC0 + MHI，月级（wcn7850-plan.md），固件前提已消除（§3） |
| camera | cam=1..5 + mediaserverd 注入 + 软 ISP | 规划完成（camera-plan.md），CAMSS 基址已入 hw-map §12 |
| ufs/ufshc | 内核 UFS | 不需要（rdfile 路线，loader 侧 ufs=1 勘察足够） |
| cpufreq | CPU 调频 | 本期不做（perf 税已知） |
| apfs_check/sparse/image/sta/guard/lx/input | root 与输入基础设施 | 随 rdfile 变体 C 自然复用 |
| virtio_blk/input/net/sound | QEMU 专用 | QEMU 回归已依赖，保持 |

## 2. 真机测试排期建议（写进 playbook 的终点清单）

一次开机带全旗标：`touchscreen=2 hv_haptic=3 buttons=1 torch=1`（battery 走内核直读则同带 `battery=1`；名字以最终实现为准）。观察顺序：看屏 → 搓屏 → 手感震动 → 音量键行为 → 手电（`torch_secs=3` 盲测）→ 电量图标。收尾纯拷贝 `adb pull /vendor/lib64/camera`（相机前置资源）。全程零持久化，2.4G 暂存仍单独经用户确认。

## 3. linux-firmware 实捞（GitLab 镜像 main 分支）

- **WCN7850 Wi-Fi 固件在库**：`ath12k/WCN7850/hw2.0/{amss.bin, m3.bin, board-2.bin}`（另有 ncm865 变体目录）。wcn7850-plan.md 的硬前提"先 dump vendor 分区拿固件"**作废**——Wi-Fi 的 PCIe/MHI/QMI 全链路 100% 可离线盲写；板级 BDF 对不上再回 vendor。
- GPU gen80200 三件套（gmu/sqe/aqe）已入库（userland 仓 firmware-gen8/，SHA256 钉死）。
- `qcom/` 下无 wcn/kiwi 命名的 BT 固件——BT HCI 载体仍待真机定（MHI vs SE14 UART，wcn7850-plan 原判断不变）。

## 4. hackios 上游（oosexgang/hackios-xnu-kernel、hackios-xnu-userland）同步扫描

两仓 `main` 自我们建 k90-port 后**零新提交**（kernel merge-base=8e61187、userland=906425b，均等于上游 HEAD）。未合并 PR 三个（replydev，2026-10-22）：kernel PR4 `common/build.sh` 构建失败传播（`|| die`）、kernel PR5 `qemu/run.sh` 用 `timeout --foreground` 防 SIGTTIN 停住 QEMU、userland PR3 老 prebuilt 镜像构建修复（pipefail + drawable_test 可选 + timedatectl 兜底）。**决定：PR 未合入前不摘取**；我们本地 userland/build.sh 已是上游 PR3 意图的超集（循环判存拷贝 + BSD sed 兼容 + readlink 时区兜底），PR5 场景我们用 run-ios.sh 独立路径不受影响；上游合入后再同步。
