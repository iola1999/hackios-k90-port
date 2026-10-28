#!/usr/bin/env bash
# Build the linux/arm64 dev image.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t hackios-dev:latest .
