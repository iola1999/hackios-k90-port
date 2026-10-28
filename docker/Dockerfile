# HackiOS build + QEMU run environment (linux/arm64; QEMU is TCG either way).
FROM ubuntu:noble

ENV DEBIAN_FRONTEND=noninteractive
# 中国内网：apt 换 USTC 源（noble 用 deb822 格式）
RUN sed -i 's|http://ports.ubuntu.com/ubuntu-ports|http://mirrors.ustc.edu.cn/ubuntu-ports|g' /etc/apt/sources.list.d/ubuntu.sources \
 && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git less vim procps \
    python3 python3-pip \
    clang lld llvm gcc make cmake pkg-config \
    binutils device-tree-compiler \
    p7zip-full lz4 unzip xz-utils cpio file bsdextrautils \
    qemu-system-arm qemu-efi-aarch64 \
    nasm acpica-tools uuid-dev python3-ply \
    bison flex patch gawk autoconf automake libtool-bin m4 perl \
    libzstd-dev zlib1g-dev python3-venv \
    ninja-build \
 && rm -rf /var/lib/apt/lists/*

# 7z: scripts call `7z`; p7zip-full provides 7z. Fine.
# stuart (edk2-pytool) for Mu-Silicium builds -- tuna mirror (CN)
RUN pip3 install --break-system-packages -q \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    edk2-pytool-extensions edk2-pytool-library pillow regex coloredlogs

# iOS 交叉构建（tools/mk-mesa.sh / userland/build.sh 的 dylib 线）：theos 的 Linux iPhone 工具链
# （cctools 的 ld64/install_name_tool）只有 x86_64（与 kbuild 容器同一份，见
# docs/analysis/kernel-build-linux.md），故加 amd64 multiarch 由 OrbStack 的 Rosetta 执行
# （实测：arm64 容器跑 x86_64 ELF 报 "Dynamic loader not found"，装 libc6:amd64 即通）。
# meson 用 mk-mesa.sh 自己 venv 里的钉版（26.x 要求 >= 1.4，noble apt 只有 1.3）。
# theos 钉 commit，iOSToolchain 与 SDK 钉产物 sha256（ld64 / install_name_tool / SDKSettings.plist），
# 上游变化就让镜像构建失败；产物不会悄悄变化。
RUN dpkg --add-architecture amd64 \
 && sed -i '/^URIs: http:\/\/mirrors.ustc.edu.cn\/ubuntu-ports\/$/a Architectures: arm64' /etc/apt/sources.list.d/ubuntu.sources \
 && printf 'Types: deb\nURIs: http://mirrors.ustc.edu.cn/ubuntu\nSuites: noble noble-updates\nComponents: main\nArchitectures: amd64\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' \
      > /etc/apt/sources.list.d/amd64.sources \
 && apt-get update && apt-get install -y --no-install-recommends libc6:amd64 libuuid1:amd64 libstdc++6:amd64 libtinfo6:amd64 \
 && rm -rf /var/lib/apt/lists/*

# libz.so.1（x86_64）也是 ld64 的依赖，但 apt 装不上：zlib1g 是 Multi-Arch: same，ports 上 arm64 还停在
# 1:1.3.dfsg-3.1ubuntu2.2，主档案 amd64 已到 ...ubuntu2.3，两架构必须同版本，apt 直接判 not installable。
# 于是绕开 dpkg 数据库直接解包官方 deb（kbuild 那台是靠 jammy 自带的 amd64 zlib1g 混过去的），URL 钉死 + sha256 校验。
RUN curl -sL --fail -o /tmp/z.deb http://mirrors.ustc.edu.cn/ubuntu/pool/main/z/zlib/zlib1g_1.3.dfsg-3.1ubuntu2.3_amd64.deb \
 && echo "376249c8de139568221dbb242318cc8cb8f02299e3a62b7432948e1754fbddf9  /tmp/z.deb" | sha256sum -c - \
 && dpkg-deb -x /tmp/z.deb / && rm /tmp/z.deb && ldconfig

ENV THEOS=/root/theos
RUN git clone --depth 1 https://github.com/theos/theos.git /root/theos \
 && git -C /root/theos fetch --depth 1 origin 304e0799973e8145f32e4ca2de6c747a84b758ce \
 && git -C /root/theos checkout -q FETCH_HEAD \
 && mkdir -p /root/theos/toolchain \
 && curl -sL --fail https://github.com/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz \
      | tar -xJ -C /root/theos/toolchain/ \
 && echo "b61576c013b8639646ae600f7b4b171fb8f2748d99c55f84b0e3be51335fdec2  /root/theos/toolchain/linux/iphone/bin/ld" | sha256sum -c - \
 && echo "15f0355059d75836977c21f77dc672dd604869ae7f511779e3049db80af560d6  /root/theos/toolchain/linux/iphone/bin/install_name_tool" | sha256sum -c - \
 && /root/theos/bin/install-sdk iPhoneOS16.5 \
 && echo "e402d200c37290c9bb7c92d8f4b2dbb00374fa9b73bddd16f613fafa92f625a4  /root/theos/sdks/iPhoneOS16.5.sdk/SDKSettings.plist" | sha256sum -c -

WORKDIR /work
CMD ["bash"]
