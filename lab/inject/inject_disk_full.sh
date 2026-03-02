#!/bin/bash
# Fill a small tmpfs-backed dir to trigger 'No space left on device' writes
set -euo pipefail

TARGET="${1:-/var/log/lab}"
FILL_FILE="$TARGET/diskfill.bin"

mkdir -p "$TARGET"
echo "[lab] Filling $TARGET until writes fail..."
dd if=/dev/zero of="$FILL_FILE" bs=1M 2>/dev/null || true

logger -t lab-inject "Injected disk-full condition at $TARGET"
echo "[lab] Disk pressure injected. Check with: df -h $TARGET"
