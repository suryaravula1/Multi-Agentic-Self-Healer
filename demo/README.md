# Node.js Demo Stack

A **local Node.js API + Redis** stack you can spin up in Docker, manually break, and feed into the Multi-Agent Self Healer.

## What's included

| Service | Port | Role |
|---------|------|------|
| `node-api` | 3000 | Express API — depends on Redis |
| `redis` | 6379 | Cache/dependency — stop it to simulate cascade failure |

## Quick start

```bash
# 1. Start the demo stack
bash scripts/demo_stack.sh up

# 2. Verify it's healthy
curl http://localhost:3000/health

# 3. Break it (pick one)
bash scripts/demo_stack.sh break crash        # process crash + restart loop
bash scripts/demo_stack.sh break oom          # memory kill (256MB container limit)
bash scripts/demo_stack.sh break redis_down   # stop Redis → API goes unhealthy
bash scripts/demo_stack.sh break flood        # flood stderr logs

# 4. Capture logs and run self-healer
bash scripts/demo_stack.sh capture crash

# Start self-healer in another terminal first:
#   source .venv/bin/activate && self-healer

bash scripts/demo_stack.sh heal

# Or do everything in one command:
bash scripts/demo_stack.sh run crash
```

## Manual break (hands-on)

With the stack running (`bash scripts/demo_stack.sh up`):

```bash
# Crash the Node process (Docker restarts it)
curl -X POST http://localhost:3000/break/crash

# Trigger OOM inside the 256MB container
curl -X POST http://localhost:3000/break/oom

# Stop Redis dependency
docker compose -f demo/docker-compose.yml stop redis
curl http://localhost:3000/health   # → 503 unhealthy

# Flood logs
curl -X POST http://localhost:3000/break/flood-logs \
  -H "Content-Type: application/json" \
  -d '{"lines": 5000}'
```

Then capture and analyze:

```bash
bash scripts/demo_stack.sh capture redis_down
bash scripts/demo_stack.sh heal
```

Recover after testing:

```bash
bash scripts/demo_stack.sh recover
```

## How logs reach self-healer

Docker doesn't produce journald by default. The capture script:

1. Reads **container state** (exited, OOMKilled, restart loop)
2. Synthesizes **systemd/kernel-style lines** the heuristics understand
3. Appends raw **`docker compose logs`** output

Saved to: `fixtures/demo_captured/`

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (pings Redis) |
| GET | `/api/data` | Read counter from Redis |
| POST | `/api/increment` | Increment counter |
| POST | `/break/crash` | Exit process (lab only) |
| POST | `/break/oom` | Allocate until OOM |
| POST | `/break/flood-logs` | Flood stderr |

## Architecture

```
┌─────────────┐     depends on     ┌─────────────┐
│  node-api   │ ─────────────────► │    redis    │
│  :3000      │                    │   :6379     │
└──────┬──────┘                    └─────────────┘
       │ break / capture
       ▼
┌─────────────────────────────────────────────┐
│  fixtures/demo_captured/*.log               │
└──────────────────┬──────────────────────────┘
                   │ POST /analyze
                   ▼
┌─────────────────────────────────────────────┐
│  Multi-Agent Self Healer (:8080)            │
│  parse → diagnose → plan → safety           │
└─────────────────────────────────────────────┘
```

## Tear down

```bash
bash scripts/demo_stack.sh down
```
