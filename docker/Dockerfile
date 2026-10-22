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
 && rm -rf /var/lib/apt/lists/*

# 7z: scripts call `7z`; p7zip-full provides 7z. Fine.
# stuart (edk2-pytool) for Mu-Silicium builds -- tuna mirror (CN)
RUN pip3 install --break-system-packages -q \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    edk2-pytool-extensions edk2-pytool-library pillow regex

WORKDIR /work
CMD ["bash"]
