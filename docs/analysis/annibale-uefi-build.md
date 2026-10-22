# annibale UEFI 构建配方（M2 实录）

> 2026-10-23 起。基于 [uefi-sm8750.md](uefi-sm8750.md) 的调研结论执行。
> 仓库：私有镜像 `iola1999/hackios-mu-silicium`（upstream = Project-Silicium/Mu-Silicium）。
> 本地位置 `hackios-xnu-kernel/Mu-Silicium/`（上游 .gitignore 忽略，与 hackios 同款处理）。

## 分支模型

- `main` = 上游快照（squash 导入，浅克隆历史剥离；跟进上游 = 上游新快照对比合并，或
  需要完整历史时 `git fetch upstream --unshallow`）
- `k90-port` = 我们的工作分支（首个提交：annibalePkg 骨架）

## 已完成

| 步骤 | 产物 |
|---|---|
| Mu-Silicium 浅克隆 + 镜像仓库 | `hackios-mu-silicium`（main/k90-port 已推） |
| SM8750 基座确认 | 主线 `dodgePkg`（OnePlus 13R 系）/`paganiPkg`，**同一 SoC**，包很小：dsc/fdf/dec + `FdtBlob` + `MemoryMapLib` + `ConfigurationMapLib` + `DeviceBuild.py`（stuart） |
| annibalePkg 骨架 | `Platforms/Xiaomi/annibalePkg`：全量改名、SMBIOS=Xiaomi/annibale、构建路径指向 Xiaomi/ |
| **真机 DTB** | 从**我们自己备份的 `dtbo_a` 分区**提取（`/tmp/annibale-dtbo-1.dtb`，498KB，含 `annibale` 节点），已放进 `FdtBlob/sm8750-xiaomi-annibale.dtb` 并入库。注意：vendor_boot 里那 8 个是 Sun 公版 thermal 变体，**不是**设备树正主 |

## 原厂 UEFI 镜像格式（2026-10-23 IDA 实测，uefi_a 备份）

- `uefi_a` **不是裸 FV/FD，是 AArch64 ELF**：`e_type=ET_EXEC`，entry `0xa7000000`，
  单 LOAD 段 RWX `0x2b3000`（file off 0x1000）；分区 5MiB。XBL 按 ELF 加载并跳 entry。
- **明文里没有 FV 头（HIVE 全镜像 0 命中）**：FV 压缩存放，运行期解出——
  ELF 里有 `Error: DecompressFvHobInit Failed - %r`（DXE 核早期，紧邻
  `EnableMultiThreading`/`KernelInterfaceInit`，即这就是完整 PI/DXE 镜像，非 stub）。
- 推论：
  1. 我们 profile 的 `FD_BASE=0x9FD00000`（redwood 默认）与原厂布局无关——它是
     **BootShim 把 Mu-Silicium UEFI 搬到哪**，由 annibalePkg 的 MemoryMapLib 定，构建后回填。
  2. 走 gbl-chainload/自载路径时，若让 XBL 直接加载我们的镜像，需保持同款 ELF 外壳
     （或改喂裸 FD 给自写的二级加载器）。
  3. 想看原厂 GOP/显示初始化：这个 ELF 已用 idalib 打开过（imagebase 0xa7000000，
     符号未 stripped 的字符串 1535 条），后续 IDA 会话可直接从 `DecompressFv` 顺藤。

## ✅ 2026-10-23 首次 FD 编译成功（冒烟）

`Build/annibalePkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd`（3MiB）产出，30 核容器约 4 分钟。
冒烟路线用 **dodge（同 SM8750）固件转储软链** `Binaries/annibale -> dodge` 顶包。要点：

- 真入口是 **`python3 build_uefi.py -d annibale`**（stuart_build 直调时须手传
  `FD_BASE/FD_SIZE/FD_BLOCKS/ENABLE_SECUREBOOT/DEVICE_MODEL`，来自 `Resources/Configs/annibale.toml`）
- 工具链 = **CLANGPDB**（Mu tools_def 无 GCC5 定义；容器 clang18+lld 原生可用）
- nasm：删 Mu_Basecore 的 nuget extdep 描述、用容器 apt nasm（`tools/fixup-mu-nasm.sh`，幂等）
- FD 地址定档 `0xA7100000/0x300000`（SM8750 家族布局；与 IDA 实测原厂 ELF@0xa7000000 同族），
  已回填 `annibale.conf`（kernel k90-port `b1ca05e`）
- 冒烟 .fd 归档 `hackios-xnu-kernel/prebuilt/uefi/annibale-smoke-dodgefv.fd`

## 构建前置（还欠的）

1. **子模块拉取**（`DeviceBuild.py GetRequiredSubmodules`）：`Binaries`(Project-Silicium/Device-Binaries)、
   `Common/Mu`、`Common/Mu_OEM_Sample`、`Mu_Basecore`、`Silicium-ACPI`、openssl。构建时在 docker 内浅拉。
2. **Binaries/annibale 固件转储**：设备上跑 [UEFIReader](https://github.com/WOA-Project/UEFIReader)
   （root）dump 运行中 UEFI 全镜像；离线兜底用我们备份的 `xbl_a.img`/`uefi_a.img`。
   dodge 的转储在 Device-Binaries 仓（子模块）里按设备目录组织。
3. **面板bring-up**：`ConfigurationMapLib` 改 annibale 屏（1200×2608，DOT 由转储的 panel 驱动决定；
   先跑通 GOP 再精调，dodge 默认值可作起点）。
4. **内存图核对**：`MemoryMapLib` 暂用 dodge 版；对照 `docs/analysis/data/annibale.iomem` 与
   我们 profile 的 `FD_BASE=0x9FD00000 / PAYLOAD_BASE=0xF0000000` 核一遍可用性。
5. **hackios 双补丁**：`hackios-xnu-kernel/uefi/mu-silicium.patch` ——①BootShim.S 增加 "XNUP"
   容器搬运到 `PAYLOAD_BASE`；②BootManagerLib 直接起 XNU loader。用 `uefi/apply.sh` 流程应用
   （它面向 redwood 树，改名后需手工过一遍冲突）。
6. **交叉工具链**：stuart（pip `edk2-pytool-extensions`）+ `gcc-aarch64-linux-gnu`
   （hackios-dev 镜像已带 gcc-aarch64；补 pip 即可）。

## 快速验证旁路（可先于完整 pkg）

`gbl-chainload-myron`（NullCode1337）：不编 UEFI，从 Android 引导链（EFISP/ABL）把自建 UEFI
镜像直接 chainload 进内存——姊妹机 myron（K90 Pro Max，同 sun 平台）已验证。适合最早验证
`fastboot boot` 不可用时的 loader+GOP 通路。

## 已验证的兼容性/流水线事实（2026-10-23 实测）

- **`uefi/mu-silicium.patch` 对今天的上游 main `git apply --check` 干净通过**
  （hackios 锁的 BASE 提交是 `e51cd877`，无漂移冲突）。
- 出货镜像装配线 = 根目录 `mkxnuimg.py`：
  `gzip(BootShim.bin + UEFI FD + XNUP容器(kernel+images)) + DTB`；
  检测 `Mu-Silicium/BootShim` 存在时**自动用我们的地址重编 BootShim**（FD_BASE/PAYLOAD_BASE 生效点）。
- `uefi/apply.sh` 是 redwood 流程（clone+checkout BASE+cp files/），我们的 annibale 路线
  **不复用它**：直接在 k90-port 上 `git apply mu-silicium.patch` 即可（已验证可过），
  第一支纯 Mu UEFI 冒烟 .fd 可以不套补丁（先验 UEFI 本体起壳）。
- 构建容器化：`hackios-dev:latest` 已含 stuart（edk2-pytool + regex + pillow，tuna 源）；
  日志 `hackios-xnu-kernel/logs-mu-{setup,update,compile}.log`（容器写、宿主读，均 gitignore）。
  坑：宿主机一次性 `docker run --rm` 里 pip install 不会留存（无头容器）——已烙进镜像层。

## 构建命令（备齐子模块后）

```sh
# docker 内（hackios-dev 镜像 + pip install edk2-pytool-extensions edk2-pytool-library）
cd Mu-Silicium
stuart_build -c Platforms/Xiaomi/annibalePkg/DeviceBuild.py \
  TARGET=RELEASE TOOLCHAIN=GCC5
# 产物 Build/annibalePkg/RELEASE_GCC5/AARCH64/... .fd → 填 annibale.conf UEFI_FD
```

## 风险与备注

- 浅历史镜像与上游合并时若遇到 rename 冲突，以 upstream 为基底重新落我们的 `k90-port` diff
  （骨架是纯新增目录，冲突面小）。
- dodge 的 APRIORI/DXE/RAW include 列表是 OnePlus 固件布局，annibale 转储后驱动 GUID 列表要对表。

## 真机首boot:全链路 EDK2 → BDS → XnuLoader 走通(2026-10-23 凌晨)

fastboot boot 实测(xnu-annibale.img,带合并 DTB 的 FD):
1. **LK 状态玄学**:`fastboot boot` 偶发 `Load Error`(与镜像无关,reboot 重进 LK fastboot 即好)。
   注意 `fastboot reboot fastboot` 在 K90 进的是 **fastbootd**(Android userspace),
   fastbootd 拒绝未签名 boot(也是 Load Error);回 LK 用 `fastboot reboot bootloader` 或 `adb reboot bootloader`。
2. **DTB 修复确认必要**:dtbo 里是 overlay(fragment 结构),Mu 的 IortDtDxe 等需要完整 DT。
   正确做法:vendor_boot 里的 8 个 base DT 之一(qcom,sun,`/tmp/vb/v3.dtb`)+ 自家 dtbo overlay
   `fdtoverlay` 合并(956KB)→ `annibalePkg/FdtBlob/sm8750-xiaomi-annibale.dtb`。
3. **行为轨迹**:OKAY 后设备黑屏运行 ~40s(全量 DXE 驱动),loader 打印 no payload/或 USB 协议失败 →
   BootManager UnableToBoot → XnuLoaderMain 返回 → 原流程 Stall 10s → **Shutdown**(USB 完全消失)。
   = BootShim/FD/DTB/EDK2 核心/QcomPkg 大部分驱动全部健康,一直跑到 BDS 之后!
4. **USB 驻留没成**:loader 的 usb_start 依赖 QCOM_USB_DEVICE 协议(UsbDeviceDxe 在 apriori,
   但 locate 失败/start_ex 失败,无串口无法分辨)。K90 无 redwood 的 `logdump` 分区,loader 日志无处落盘。
5. 屏幕黑:DisplayDxe 用 dodge 面板 XML 与 K90 面板(1200x2608)不符,初始化失败,属预期;M3 主攻。

### 下一步(M2 收尾)
- **RAM 留痕日志桥**:loader 在固定物理地址留 magic+log_buf,无 payload 时改走 EfiResetWarm
  (Qcom warm reset 保 DDR),第二次 boot 由 XnuLoaderMain 读出 → 经 GOP 屏显或下轮 USB 拉走。
- USB 协议没找到的两种成因(驱动没起 vs start_ex 失败)用日志区分,再对症。

## 设备离线备货轮(2026-10-23 清晨,设备关机等人开机)

结论与产物(验证流程/决策树见 docs/plan/device-test-playbook.md):

1. **loader 平台进仓**:kernel 子模块 feb3c55 —— `platform_annibale`
   (GIC 0x16000000/0x16080000、8 核 shift 8、small 0x3f,全部来自合并 DT 实证)、
   `-DDIRECT_PHONE_PLAT`(GOP fb_base 未知时直接选中 annibale)、日志分区
   `logdump`→`boot_a` 回退。手机版:`EXTRA_CFLAGS=-DDIRECT_PHONE_PLAT bash build.sh`。
2. **面板 XML 生成器** `tools/dts2panelxml.py`:自家 DTS `dsi_p11_42_0d_0a_p10_dsc_cmd`
   → DisplayDxe XML:1156x2510 时序(注意:K90 标称 1200x2608 为 DSC 后显示区,
   DSI 时序以 DTS 为准)、DSC1.2 slice 578x10、clk 1205000000、4 lane、cmd mode、
   339 条 DCS 初始化命令(6 字节头流→XML 行式转换)。已挂 RAW.inc(新 GUID
   1A395579-…,FFS 14KB 进 FVMAIN 已验证)。**悬念**:DisplayDxe 按 DDIC ID 匹配
   PanelName,首boot 若仍黑屏,从 loader/DisplayDxe 日志找自报 ID 改 `<PanelName>` 再试
   (备选:换 dsc_ver/slice/ProfileID 参数组)。
3. **DTB 回退陷阱**:02:00 对比实验把 `FdtBlob/sm8750-xiaomi-annibale.dtb` 落回了 505KB
   纯 overlay,02:56 那次 FD 其实带的是 overlay。已用 `/tmp/vb/merged.dtb`(956243B)恢复
   并重建;Mu-Silicium k90-port 87416d2 固化 merged DTB + Source.txt,不再依赖 /tmp。
4. **变体镜像**(均在 hackios-xnu-kernel/,同一最新 FD):
   - `xnu-annibale-log.img`(1.26MB,变体 A):payload=loader(--usb)+cmdline,驻留等 USB;
     打包 `DTB=empty.dtb`(DT 槽占位,LK 收到的 DTB 无人消费,真 DT 在 FD FREEFORM 内),稳低于 LK ~2MB 上限;
     `fastboot boot` 直测(LK 容量内)。
   - `xnu-annibale-auto.img`(~7.5MB,变体 B):payload=loader+kernel(mach.development.bcm2837
     同款),无 --usb 自动 run_kernel 盲跑;走 `flash boot_a + --set-active=a`。
   - 变体 C(面板)已并入 A/B 的 FD。
5. **一键回归** `tools/device-test.sh`:LK 重试 → 变体 A → getvar xnuloader 探测 →
   boot_a 日志 fetch → 摘要。人肉流程+决策树在 playbook。
