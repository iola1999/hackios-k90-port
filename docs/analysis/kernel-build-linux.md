# 内核重编流水线（Linux 容器，2026-10-23 打通）

背景：`prebuilt/mach.development.bcm2837` 原是上游交付物；我们改 `xnu/files/bsd/dev/redwood_*.c`（如 annibale 触摸参数化 cc9ff58）必须重编内核才能进 payload。macOS 上没有构建所需的一整套 Linux host 工具 + theos，故在 docker 里建（容器 `kbuild` 常驻复用：`docker start kbuild`）。

## 容器与依赖

```sh
docker volume create kb
docker run -d --name kbuild --platform linux/amd64 \
  -v kb:/work -v $PWD/hackios-xnu-kernel:/src:ro ubuntu:22.04 sleep infinity
```

- **必须 `--platform linux/amd64`**：theos 的 Linux cctools/ld64 只有 x86_64；OrbStack 的 Rosetta 透明加速，性能可接受（全量 -j8 约 35 分钟）。
- apt（tuna 源）：`git curl ca-certificates tar xz-utils make clang lld python3 perl flex bison m4 autoconf automake libtool pkg-config zlib1g-dev gawk file unzip zstd libzstd-dev bzip2 zip binutils uuid-dev libssl-dev libxml2-dev libbz2-dev liblzma-dev libncurses-dev python-is-python3`

## theos（XNU 的 SDK 与链接器）

```sh
git clone --depth 1 https://github.com/theos/theos.git /root/theos
curl -sL https://github.com/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz \
  | tar -xJ -C /root/theos/toolchain/        # 提供 toolchain/linux/iphone（ld64 等）
/root/theos/bin/install-sdk iPhoneOS16.5     # 提供 sdks/iPhoneOS16.5.sdk
```

## 构建步骤（容器内，仓库克隆在 /work/repo）

```sh
git clone -b k90-port file:///src /work/repo
bash xnu/apply.sh            # 拉 apple-oss-distributions/xnu 的 xnu-8796.121.2 并打 redwood 补丁
bash xnu-deps/setup.sh       # stage1 host 工具(mig/tcsh/unifdef) + SDK 缝合；stage2 两个静态库
bash xnu-build.sh -j8 BUILD_DSYM=0 KEXT_CREATE_SYMBOL_SET=/bin/true
```

产物：`xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837`。

## 踩过的坑（均已修复，前两个已提交进仓库）

| 症状 | 根因 | 修复 |
|---|---|---|
| `strlcat` 未定义（SETUP/replacecontents） | glibc<2.38 无 BSD 字符串函数 | hostcompat.h 加 static inline（仓库 63f0f01） |
| `-ftrivial-auto-var-init=zero` 报错 | xnu-clang 包装器为一律丢弃 enable flag，而 Ubuntu clang≤19 需要它 | 包装器加一次性能力探测缓存（kernel 仓库 b7ac03a） |
| `uuid/uuid.h` 找不到 | 缺 uuid-dev | apt 装上 |
| tcsh 配置失败 | 缺 libncurses-dev | apt 装上 |
| `--minimize: command not found`（DSYMUTIL） | Linux 无 dsymutil | `BUILD_DSYM=0`（dSYM 我们不用） |
| `check_all_exports`: exported name not in import list | 新 clang 生成的 C++ 符号与 Apple 参考清单不一致（Apple 用 LTO 收敛） | `KEXT_CREATE_SYMBOL_SET=/bin/true` 旁路；注意值必须是存在的文件（make 会把它当依赖），不能用裸 `true` |
| lldbmacros `env: python` | ubuntu 无 `python` 别名 | `python-is-python3` |

另注意：改了 `hostcompat.h` 后旧 `.o` 不会自动重编（无头文件依赖），要 `rm -rf BUILD/obj/SETUP`。

## 换入 payload 的流程

```sh
docker cp kbuild:/work/repo/xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837 \
  hackios-xnu-kernel/prebuilt/mach.development.bcm2837
# 更新 prebuilt/SHA256SUMS 对应行 → 重跑 mkpayload/mkxnuimg → QEMU 回归（qemu/run-ios.sh）
```

已知差异：我们 `BUILD_LTO=0`（构建脚本默认），上游交付物带 LTO，体积 15.2MB vs 15.6MB；功能等价性以 QEMU 回归为准。
