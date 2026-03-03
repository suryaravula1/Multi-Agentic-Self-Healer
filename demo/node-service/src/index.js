const express = require("express");
const redis = require("redis");

const PORT = Number(process.env.PORT || 3000);
const REDIS_URL = process.env.REDIS_URL || "redis://redis:6379";
const SERVICE_NAME = process.env.SERVICE_NAME || "node-api.service";

const app = express();
app.use(express.json());

let client = null;
let redisReady = false;

function log(level, message, extra = "") {
  const ts = new Date().toISOString();
  const suffix = extra ? ` ${extra}` : "";
  console.log(`${ts} [${level}] ${message}${suffix}`);
}

async function connectRedis() {
  client = redis.createClient({ url: REDIS_URL });
  client.on("error", (err) => {
    redisReady = false;
    console.error(`${new Date().toISOString()} [error] Redis client error: ${err.message}`);
  });
  client.on("connect", () => log("info", "Connected to Redis"));
  await client.connect();
  redisReady = true;
}

app.get("/", (_req, res) => {
  res.json({
    service: "demo-node-api",
    hint: "Try GET /health, POST /break/crash, POST /break/oom, POST /break/flood-logs",
  });
});

app.get("/health", async (_req, res) => {
  try {
    if (!client || !redisReady) throw new Error("Redis client not ready");
    const pong = await client.ping();
    res.json({ status: "ok", redis: pong, service: SERVICE_NAME });
  } catch (err) {
    console.error(`${new Date().toISOString()} [error] Health check failed: ${err.message}`);
    res.status(503).json({ status: "unhealthy", error: err.message });
  }
});

app.get("/api/data", async (_req, res) => {
  try {
    const value = await client.get("demo:counter");
    res.json({ counter: Number(value || 0) });
  } catch (err) {
    console.error(`${new Date().toISOString()} [error] API failure: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/increment", async (_req, res) => {
  try {
    const next = await client.incr("demo:counter");
    res.json({ counter: next });
  } catch (err) {
    console.error(`${new Date().toISOString()} [error] Increment failed: ${err.message}`);
    res.status(500).json({ error: err.message });
  }
});

// --- Break scenarios (lab only — do not expose in production) ---

app.post("/break/crash", (_req, res) => {
  console.error(`${new Date().toISOString()} [fatal] Manual crash injection requested`);
  res.json({ message: "Crashing in 500ms..." });
  setTimeout(() => process.exit(1), 500);
});

app.post("/break/oom", (_req, res) => {
  console.error(`${new Date().toISOString()} [fatal] OOM injection started — allocating memory`);
  res.json({ message: "Allocating memory until container limit..." });
  setImmediate(() => {
    const leak = [];
    try {
      while (true) {
        leak.push(Buffer.alloc(20 * 1024 * 1024));
      }
    } catch (err) {
      console.error(`${new Date().toISOString()} [error] Allocation stopped: ${err.message}`);
    }
  });
});

app.post("/break/flood-logs", (req, res) => {
  const lines = Number(req.body?.lines || 5000);
  console.error(`${new Date().toISOString()} [warn] Flooding ${lines} log lines`);
  for (let i = 0; i < lines; i += 1) {
    console.error(`${new Date().toISOString()} [error] synthetic flood line ${i}`);
  }
  res.json({ flooded: lines });
});

async function start() {
  log("info", `Starting ${SERVICE_NAME} on port ${PORT}`);
  try {
    await connectRedis();
    log("info", "Redis dependency satisfied");
  } catch (err) {
    console.error(`${new Date().toISOString()} [error] Failed to connect Redis: ${err.message}`);
    console.error(`${new Date().toISOString()} [error] Service will start but remain unhealthy`);
  }

  app.listen(PORT, () => log("info", `Listening on :${PORT}`));
}

start().catch((err) => {
  console.error(`${new Date().toISOString()} [fatal] Startup failed: ${err.message}`);
  process.exit(1);
});
