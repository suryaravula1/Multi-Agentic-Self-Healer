#!/bin/bash
# Inject a systemd service crash loop (start-limit-hit scenario)
set -euo pipefail

SERVICE="${1:-demo-app.service}"

echo "[lab] Stopping $SERVICE to simulate crash..."
systemctl stop "$SERVICE" || true

# Write a marker so journal has a clear failure trail
logger -t lab-inject "Injected service failure for $SERVICE"
systemctl status "$SERVICE" --no-pager || true

echo "[lab] Failure injected. Collect logs with:"
echo "  docker exec self-healer-lab journalctl -u $SERVICE -n 100 --no-pager"
