#!/usr/bin/env bash
# Spin up the Node.js demo stack, break it, capture logs, and run self-healer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="$ROOT/demo"
OUT="$ROOT/fixtures/demo_captured"
COMPOSE="docker compose -f $DEMO/docker-compose.yml"
HEALER_URL="${HEALER_URL:-http://localhost:8080}"

ts() { date "+%b %d %H:%M:%S"; }

up() {
  echo "Building and starting demo stack (Node.js + Redis)..."
  $COMPOSE up -d --build
  echo "Waiting for healthy services..."
  sleep 5
  curl -sf "http://localhost:3000/health" | head -c 200
  echo ""
  echo ""
  echo "Demo API:  http://localhost:3000"
  echo "Health:    http://localhost:3000/health"
  echo "Break endpoints (POST): /break/crash  /break/oom  /break/flood-logs"
}

down() {
  $COMPOSE down -v
  echo "Demo stack stopped."
}

status() {
  $COMPOSE ps
  echo ""
  curl -s "http://localhost:3000/health" 2>/dev/null || echo "node-api not responding"
}

break_scenario() {
  local scenario="${1:-crash}"
  echo "Injecting failure: $scenario"

  case "$scenario" in
    crash)
      curl -s -X POST "http://localhost:3000/break/crash" || true
      sleep 3
      ;;
    oom)
      curl -s -X POST "http://localhost:3000/break/oom" || true
      sleep 8
      ;;
    flood)
      curl -s -X POST "http://localhost:3000/break/flood-logs" \
        -H "Content-Type: application/json" \
        -d '{"lines": 8000}' || true
      sleep 2
      ;;
    redis_down)
      $COMPOSE stop redis
      sleep 3
      curl -s "http://localhost:3000/health" || true
      echo ""
      sleep 2
      ;;
    *)
      echo "Unknown scenario: $scenario"
      echo "Options: crash | oom | flood | redis_down"
      exit 1
      ;;
  esac

  echo "Failure injected."
}

capture() {
  local scenario="${1:-unknown}"
  mkdir -p "$OUT"
  local outfile="$OUT/$(date +%Y%m%d_%H%M%S)_${scenario}.log"

  local node_state redis_state node_exit
  node_state="$(docker inspect -f '{{.State.Status}}' demo-node-api 2>/dev/null || echo unknown)"
  redis_state="$(docker inspect -f '{{.State.Status}}' demo-redis 2>/dev/null || echo unknown)"
  node_exit="$(docker inspect -f '{{.State.ExitCode}}' demo-node-api 2>/dev/null || echo 0)"
  local oom_killed
  oom_killed="$(docker inspect -f '{{.State.OOMKilled}}' demo-node-api 2>/dev/null || echo false)"

  {
    echo "# Captured demo failure: $scenario @ $(ts)"
    echo ""

  # Synthesize systemd-style lines so self-healer heuristics can match them
    if [[ "$node_state" == "restarting" || "$node_state" == "exited" ]]; then
      echo "$(ts) prod-demo-01 systemd[1]: node-api.service: Main process exited, code=exited, status=${node_exit}/FAILURE"
      echo "$(ts) prod-demo-01 systemd[1]: node-api.service: Failed with result 'exit-code'."
      echo "$(ts) prod-demo-01 systemd[1]: Failed to start node-api.service - Demo Node API."
    fi

    if [[ "$oom_killed" == "true" ]]; then
      echo "$(ts) prod-demo-01 kernel: [$(date +%s)] Out of memory: Kill process 1 (node) score 900 or sacrifice child"
      echo "$(ts) prod-demo-01 kernel: [$(date +%s)] Killed process 1 (node) total-vm:268435456kB, anon-rss:256000kB"
      echo "$(ts) prod-demo-01 systemd[1]: node-api.service: Main process exited, code=killed, status=9/KILL"
    fi

    if [[ "$redis_state" != "running" ]]; then
      echo "$(ts) prod-demo-01 systemd[1]: redis.service: Failed with result 'exit-code'."
      echo "$(ts) prod-demo-01 systemd[1]: node-api.service: Dependency redis.service failed to start."
      echo "$(ts) prod-demo-01 node-api[1]: Error: connect ECONNREFUSED redis:6379"
    fi

    if [[ "$scenario" == "flood" ]]; then
      echo "$(ts) prod-demo-01 systemd[1]: systemd-journald.service: Failed to write entry (No space left on device)"
      echo "$(ts) prod-demo-01 node-api[1]: ENOSPC: no space left on device, write"
    fi

    echo ""
    echo "=== docker compose logs: node-api ==="
    $COMPOSE logs --no-color --tail=150 node-api 2>/dev/null || true
    echo ""
    echo "=== docker compose logs: redis ==="
    $COMPOSE logs --no-color --tail=50 redis 2>/dev/null || true
  } > "$outfile"

  echo "Captured -> $outfile"
  echo "$outfile"
}

heal() {
  local logfile="${1:-}"
  if [[ -z "$logfile" ]]; then
    logfile="$(ls -t "$OUT"/*.log 2>/dev/null | head -1)"
  fi
  if [[ -z "$logfile" || ! -f "$logfile" ]]; then
    echo "No captured log found. Run: $0 run <scenario> first"
    exit 1
  fi

  echo "Sending logs to self-healer ($HEALER_URL/analyze)..."
  if ! curl -sf "$HEALER_URL/health" >/dev/null 2>&1; then
    echo "Self-healer not running. Start it with: self-healer"
    exit 1
  fi

  curl -s -X POST "$HEALER_URL/analyze" \
    -H "Content-Type: application/json" \
    -d "{\"logs\": $(jq -Rs . "$logfile"), \"source_hint\": \"mixed\"}" | jq .
}

run_all() {
  local scenario="${1:-crash}"
  up
  break_scenario "$scenario"
  local logfile
  logfile="$(capture "$scenario")"
  echo ""
  heal "$logfile"
}

recover() {
  echo "Recovering demo stack..."
  $COMPOSE start redis 2>/dev/null || true
  $COMPOSE restart node-api
  sleep 5
  status
}

usage() {
  cat <<EOF
Node.js demo stack for self-healer testing

Usage: $0 <command> [scenario]

Commands:
  up                        Start Node.js + Redis (docker compose)
  down                      Stop and remove containers
  status                    Show service status
  break <scenario>          Inject failure (see scenarios below)
  capture [scenario]        Save logs to fixtures/demo_captured/
  heal [logfile]            POST captured logs to self-healer /analyze
  run <scenario>            up + break + capture + heal (full demo)
  recover                   Restart redis + node-api after a break

Scenarios:
  crash       POST /break/crash — process exit / restart loop
  oom         POST /break/oom — container OOM kill (256MB limit)
  flood       POST /break/flood-logs — massive stderr output
  redis_down  Stop Redis — dependency failure cascade

Examples:
  $0 up
  $0 break crash
  $0 capture crash
  $0 heal
  $0 run oom
EOF
}

cmd="${1:-}"
shift || true

case "$cmd" in
  up) up ;;
  down) down ;;
  status) status ;;
  break) break_scenario "${1:-crash}" ;;
  capture) capture "${1:-manual}" ;;
  heal) heal "${1:-}" ;;
  run) run_all "${1:-crash}" ;;
  recover) recover ;;
  *) usage; exit 1 ;;
esac
