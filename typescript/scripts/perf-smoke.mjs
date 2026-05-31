import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3000";
const iterations = Number(process.env.ITERATIONS ?? "40");
const concurrency = Number(process.env.CONCURRENCY ?? "8");
const p95LimitMs = Number(process.env.P95_MS ?? "1500");
const demoFile = process.env.DEMO_FILE ?? join(scriptDir, "..", "..", "demo-data", "heat-safety-policy.txt");
const chatId = `perf-smoke-${Date.now()}`;
const server = await ensureServer();

await seedRagDocument();

const latencies = [];
let failures = 0;
let cursor = 0;
await Promise.all(Array.from({ length: concurrency }, async () => {
  while (cursor < iterations) {
    const index = cursor;
    cursor += 1;
    const endpoint = index % 2 === 0
      ? `/ai/chat?prompt=${encodeURIComponent("hello")}&chatId=${chatId}-${index}`
      : `/ai/pdf/chat?prompt=${encodeURIComponent("heat safety requirements")}&chatId=${chatId}`;
    const started = performance.now();
    try {
      const response = await fetch(`${baseUrl}${endpoint}`);
      await response.text();
      if (!response.ok) {
        failures += 1;
      }
    } catch {
      failures += 1;
    } finally {
      latencies.push(performance.now() - started);
    }
  }
}));

latencies.sort((a, b) => a - b);
const p95 = latencies[Math.max(0, Math.ceil(latencies.length * 0.95) - 1)] ?? 0;
const failureRate = failures / Math.max(1, iterations);
const summary = {
  baseUrl,
  iterations,
  concurrency,
  p95Ms: Number(p95.toFixed(1)),
  failureRate: Number(failureRate.toFixed(4)),
  p95LimitMs
};

console.log(JSON.stringify(summary, null, 2));
if (p95 > p95LimitMs || failureRate >= 0.02) {
  await stopServer(server);
  process.exit(1);
}
await stopServer(server);

async function ensureServer() {
  if (await healthOk()) {
    return undefined;
  }
  const apiDist = join(scriptDir, "..", "apps", "api", "dist", "main.js");
  if (!existsSync(apiDist)) {
    const build = spawnSync("pnpm", ["build"], {
      cwd: join(scriptDir, ".."),
      stdio: "inherit",
      env: process.env
    });
    if (build.status !== 0) {
      throw new Error("failed to build API before perf smoke");
    }
  }
  const child = spawn("pnpm", ["--filter", "@knowledgeops/api", "start"], {
    cwd: join(scriptDir, ".."),
    env: {
      ...process.env,
      NODE_ENV: "development",
      APP_SECURITY_ENABLED: "false",
      APP_LLM_ENABLED: "false",
      APP_WORKFLOW_ASYNC_ENABLED: "false",
      APP_INGESTION_WORKER_ENABLED: "false",
      PORT: new URL(baseUrl).port || "3000"
    },
    stdio: ["ignore", "ignore", "inherit"]
  });
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await healthOk()) {
      return child;
    }
    await delay(250);
  }
  child.kill("SIGTERM");
  throw new Error(`server did not become healthy at ${baseUrl}`);
}

async function healthOk() {
  try {
    const response = await fetch(`${baseUrl}/actuator/health`);
    return response.ok;
  } catch {
    return false;
  }
}

async function stopServer(child) {
  if (!child) {
    return;
  }
  child.kill("SIGTERM");
  await delay(250);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function seedRagDocument() {
  const content = await readFile(demoFile);
  const form = new FormData();
  form.set("file", new Blob([content], { type: "text/plain" }), "heat-safety-policy.txt");
  const response = await fetch(`${baseUrl}/ai/pdf/upload/${chatId}`, {
    method: "POST",
    body: form
  });
  if (!response.ok) {
    throw new Error(`failed to seed RAG document: ${response.status} ${await response.text()}`);
  }
}
