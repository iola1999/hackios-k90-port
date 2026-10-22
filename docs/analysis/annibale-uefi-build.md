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
