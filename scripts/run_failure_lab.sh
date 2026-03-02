#!/usr/bin/env bash
# Run the local failure-injection lab and export logs for self-healer testing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAB_IMAGE="self-healer-lab:latest"
CONTAINER="self-healer-lab"
OUT="$ROOT/fixtures/lab_captured"

build() {
  echo "Building lab image..."
  docker build -f "$ROOT/lab/Dockerfile" -t "$LAB_IMAGE" "$ROOT"
}

start() {
  docker rm -f "$CONTAINER" 2>/dev/null || true
  echo "Starting lab container (privileged — required for systemd)..."
  docker run -d \
    --name "$CONTAINER" \
    --privileged \
    --tmpfs /run \
    --tmpfs /run/lock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    --memory=512m \
    --memory-swap=512m \
    "$LAB_IMAGE"
  echo "Waiting for systemd..."
  sleep 8
}

inject() {
  local scenario="${1:-service_failure}"
  case "$scenario" in
    service_failure)
      docker exec "$CONTAINER" /opt/lab/inject/inject_service_failure.sh demo-app.service
      ;;
    disk_full)
      docker exec "$CONTAINER" /opt/lab/inject/inject_disk_full.sh
      ;;
    oom)
      docker exec "$CONTAINER" /opt/lab/inject/inject_oom.sh 400
      ;;
    *)
      echo "Unknown scenario: $scenario"
      echo "Options: service_failure | disk_full | oom"
      exit 1
      ;;
  esac
}

capture() {
  mkdir -p "$OUT"
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  local outfile="$OUT/${ts}_lab.log"

  {
    echo "=== journalctl (demo-app) ==="
    docker exec "$CONTAINER" journalctl -u demo-app.service -n 200 --no-pager 2>/dev/null || true
    echo ""
    echo "=== journalctl (system) ==="
    docker exec "$CONTAINER" journalctl -p err..alert -n 100 --no-pager 2>/dev/null || true
    echo ""
    echo "=== dmesg (OOM / kernel) ==="
    docker exec "$CONTAINER" dmesg 2>/dev/null | tail -50 || true
  } > "$outfile"

  echo "Captured logs -> $outfile"
  echo ""
  echo "Test against self-healer:"
  echo "  curl -s -X POST http://localhost:8080/analyze -H 'Content-Type: application/json' \\"
  echo "    -d \"{\\\"logs\\\": \$(jq -Rs . '$outfile')}\""
}

stop() {
  docker rm -f "$CONTAINER" 2>/dev/null || true
  echo "Lab stopped."
}

usage() {
  cat <<EOF
Usage: $0 <command> [scenario]

Commands:
  build                     Build the lab Docker image
  start                     Start the lab container
  inject <scenario>         Inject failure (service_failure|disk_full|oom)
  capture                   Export journald/dmesg logs to fixtures/lab_captured/
  run <scenario>            build + start + inject + capture (all-in-one)
  stop                      Remove lab container

Examples:
  $0 run service_failure
  $0 run disk_full
EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  build) build ;;
  start) start ;;
  inject) inject "${1:-service_failure}" ;;
  capture) capture ;;
  run)
    build
    start
    inject "${1:-service_failure}"
    sleep 3
    capture
    ;;
  stop) stop ;;
  *) usage; exit 1 ;;
esac
