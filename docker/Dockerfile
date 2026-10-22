# HackiOS build + QEMU run environment (linux/arm64; QEMU is TCG either way).
FROM ubuntu:noble

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git less vim procps \
    python3 python3-pip \
    clang lld llvm gcc make cmake pkg-config \
    binutils device-tree-compiler \
    p7zip-full lz4 unzip xz-utils cpio file bsdextrautils \
    qemu-system-arm edk2-aarch64 \
    nasm acpica-tools uuid-dev python3-ply \
 && rm -rf /var/lib/apt/lists/*

# 7z: scripts call `7z`; p7zip-full provides 7z. Fine.
WORKDIR /work
CMD ["bash"]
