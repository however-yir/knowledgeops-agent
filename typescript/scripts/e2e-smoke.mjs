import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { spawn, spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = join(scriptDir, "..");
const baseUrl = process.env.BASE_URL ?? "http://localhost:3000";
const chatId = `e2e-${Date.now()}`;
const server = await ensureServer();

try {
  await expectRawJson("health", "/actuator/health", { status: "UP" });
  await expectRawJson("TypeScript health alias", "/health", { status: "UP" });
  await expectOpenApi();
  await upload();
  assertFields("chat", await expectOk("chat", "/ai/react/chat", { prompt: "heat safety", chatId }), ["answer", "model", "usage", "traceId"]);
  await expectSse("stream", "/ai/react/chat/stream", { prompt: "heat safety stream", chatId });
  await expectJson("sessions", "/ai/sessions", { items: "array" }, "GET");
  await expectJson("memory create", "/ai/memory/items", { userId: "anonymous", content: "E2E memory item", type: "fact" });
  await expectJson("memory list", "/ai/memory/items?userId=anonymous", "array", "GET");
  const entity = await expectJson("graph entity", "/ai/graph/entities", { name: "E2E Entity", type: "CONCEPT" });
  await expectJson("graph neighbors", `/ai/graph/entities/${encodeURIComponent(entity.entityId)}/neighbors`, { relations: "array" }, "GET");
  await expectJson("graph fact", "/ai/graph/facts", { subject: "E2E", predicate: "checks", object: "graph" });
  const dataset = await expectJson("eval dataset", "/ai/evaluation/datasets", {
    name: `e2e-${Date.now()}`,
    cases: [{ question: "heat safety", expectedKeywords: ["heat"] }]
  });
  await expectJson("eval run", "/ai/evaluation/runs", { datasetId: dataset.datasetId, modelProfile: "balanced" });
  await expectJson("cost", "/cost/summary", { tenantId: "public" }, "GET");
  await expectPrometheusAlias();
  console.log("e2e smoke ok");
} finally {
  await stopServer(server);
}

async function expectOpenApi() {
  const response = await fetch(`${baseUrl}/v3/api-docs`);
  const json = await response.json();
  if (!response.ok || json?.openapi !== "3.0.3" || !json?.paths?.["/actuator/health"]) {
    throw new Error(`TypeScript OpenAPI extension failed: ${response.status} ${JSON.stringify(json)}`);
  }
}

async function expectPrometheusAlias() {
  const response = await fetch(`${baseUrl}/metrics`);
  const body = await response.text();
  if (!response.ok || !/^http_requests_total(?:\{|\s)/m.test(body) || !/^http_request_duration_ms_(?:bucket|count|sum)(?:\{|\s)/m.test(body)) {
    throw new Error(`TypeScript metrics alias failed: ${response.status} ${body.slice(0, 500)}`);
  }
}

async function expectRawJson(label, path, shape) {
  const response = await fetch(`${baseUrl}${path}`);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${label} failed: ${response.status} ${text}`);
  }
  const json = text ? JSON.parse(text) : null;
  assertShape(label, json, shape);
  return json;
}

async function upload() {
  const content = await readFile(join(root, "..", "demo-data", "heat-safety-policy.txt"));
  const form = new FormData();
  form.set("file", new Blob([content], { type: "text/plain" }), "heat-safety-policy.txt");
  const response = await fetch(`${baseUrl}/ai/pdf/upload/${chatId}`, { method: "POST", body: form });
  if (!response.ok) {
    throw new Error(`upload failed: ${response.status} ${await response.text()}`);
  }
  const json = await response.json();
  if (json?.ok !== 1 || json?.msg !== "accepted" || typeof json?.job?.jobId !== "string") {
    throw new Error(`upload expected accepted job response: ${JSON.stringify(json)}`);
  }
}

async function expectOk(label, path, body) {
  return expectJson(label, path, body);
}

async function expectJson(label, path, bodyOrShape, method = "POST") {
  const hasBody = method !== "GET";
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: hasBody ? { "content-type": "application/json" } : undefined,
    body: hasBody ? JSON.stringify(bodyOrShape) : undefined
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${label} failed: ${response.status} ${text}`);
  }
  const json = text ? JSON.parse(text) : null;
  assertShape(label, json, hasBody ? undefined : bodyOrShape);
  return json;
}

async function expectSse(label, path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  const text = await response.text();
  if (!response.ok || !text.includes("event: done")) {
    throw new Error(`${label} SSE failed`);
  }
  const done = text.match(/event: done\ndata: (.+)\n/)?.[1];
  assertEnvelope(label, done ? JSON.parse(done) : null);
}

function assertEnvelope(label, json) {
  if (json?.ok !== 1 || typeof json.msg !== "string" || !("data" in json)) {
    throw new Error(`${label} expected { ok, msg, data } envelope`);
  }
  return json.data;
}

function assertFields(label, json, fields) {
  for (const field of fields) {
    if (!(field in (json ?? {}))) {
      throw new Error(`${label} expected field ${field}`);
    }
  }
}

function assertShape(label, json, shape) {
  if (shape === "array") {
    if (!Array.isArray(json)) {
      throw new Error(`${label} expected array`);
    }
    return;
  }
  if (!shape || typeof shape !== "object") {
    return;
  }
  for (const [key, expected] of Object.entries(shape)) {
    if (expected === "array" && !Array.isArray(json?.[key])) {
      throw new Error(`${label} expected ${key} array`);
    }
    if (typeof expected === "string" && expected !== "array" && json?.[key] !== expected) {
      throw new Error(`${label} expected ${key}=${expected}`);
    }
  }
}

async function ensureServer() {
  if (await healthOk()) {
    return undefined;
  }
  if (!existsSync(join(root, "apps", "api", "dist", "main.js"))) {
    const build = spawnSync("pnpm", ["build"], { cwd: root, stdio: "inherit", env: process.env });
    if (build.status !== 0) {
      throw new Error("failed to build API before e2e smoke");
    }
  }
  const child = spawn("pnpm", ["--filter", "@knowledgeops/api", "start"], {
    cwd: root,
    env: { ...process.env, NODE_ENV: "development", APP_SECURITY_ENABLED: "false", APP_LLM_ENABLED: "false", PORT: new URL(baseUrl).port || "3000" },
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
