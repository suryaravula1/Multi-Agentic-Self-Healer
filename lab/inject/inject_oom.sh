#!/bin/bash
# Allocate memory until the kernel OOM killer activates (use with --memory limit)
set -euo pipefail

LIMIT_MB="${1:-200}"
echo "[lab] Allocating ~${LIMIT_MB}MB to trigger memory pressure..."

python3 - <<PY
import sys
chunks = []
target = int("${LIMIT_MB}") * 1024 * 1024
used = 0
block = 10 * 1024 * 1024
while used < target:
    try:
        chunks.append(bytearray(block))
        used += block
    except MemoryError:
        break
print(f"[lab] Allocated ~{used // (1024*1024)}MB, holding for 60s...")
import time
time.sleep(60)
PY

logger -t lab-inject "OOM injection script completed"
