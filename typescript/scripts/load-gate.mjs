import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = join(scriptDir, "..");
const baseUrl = process.env.BASE_URL ?? "http://localhost:3000";
const vus = Number(process.env.LOAD_VUS ?? "50");
const durationSeconds = Number(process.env.LOAD_DURATION_SECONDS ?? "180");
const p99LimitMs = Number(process.env.LOAD_P99_MS ?? "2500");
const server = await ensureServer();
const latencies = [];
let failures = 0;
const deadline = Date.now() + durationSeconds * 1000;

try {
  await Promise.all(Array.from({ length: vus }, async (_, vu) => {
    let index = 0;
    while (Date.now() < deadline) {
      const started = performance.now();
      try {
        const path = index % 3 === 0
          ? `/ai/chat?prompt=${encodeURIComponent(`load ${vu} ${index}`)}&chatId=load-${vu}`
          : index % 3 === 1
            ? `/ai/pdf/chat?prompt=${encodeURIComponent("heat safety")}&chatId=load-${vu}`
            : "/actuator/health";
        const response = await fetch(`${baseUrl}${path}`);
        await response.text();
        if (!response.ok) {
          failures += 1;
        }
      } catch {
        failures += 1;
      } finally {
        latencies.push(performance.now() - started);
        index += 1;
      }
    }
  }));
  latencies.sort((a, b) => a - b);
  const p99 = latencies[Math.max(0, Math.ceil(latencies.length * 0.99) - 1)] ?? 0;
  const failureRate = failures / Math.max(1, latencies.length);
  const summary = { baseUrl, vus, durationSeconds, requests: latencies.length, p99Ms: Number(p99.toFixed(1)), failureRate: Number(failureRate.toFixed(4)), p99LimitMs };
  console.log(JSON.stringify(summary, null, 2));
  if (p99 > p99LimitMs || failureRate >= 0.02) {
    process.exitCode = 1;
  }
} finally {
  await stopServer(server);
}

async function ensureServer() {
  if (await healthOk()) {
    return undefined;
  }
  if (!existsSync(join(root, "apps", "api", "dist", "main.js"))) {
    const build = spawnSync("pnpm", ["build"], { cwd: root, stdio: "inherit", env: process.env });
    if (build.status !== 0) {
      throw new Error("failed to build API before load gate");
    }
  }
  const child = spawn("pnpm", ["--filter", "@knowledgeops/api", "start"], {
    cwd: root,
    env: { ...process.env, NODE_ENV: "development", APP_SECURITY_ENABLED: "false", APP_RATE_LIMIT_ENABLED: "false", APP_LLM_ENABLED: "false", PORT: new URL(baseUrl).port || "3000" },
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
    return (await fetch(`${baseUrl}/actuator/health`)).ok;
  } catch {
    return false;
  }
}

async function stopServer(child) {
  if (child) {
    child.kill("SIGTERM");
    await delay(250);
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
