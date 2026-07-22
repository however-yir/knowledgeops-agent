import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const baseUrl = process.env.BASE_URL ?? "http://127.0.0.1:3011";
const databaseUrl = process.env.DATABASE_URL?.trim();
const apiKey = process.env.APP_DEMO_API_KEY ?? "ci-database-integration-key";
const concurrency = Number(process.env.DB_TEST_CONCURRENCY ?? "12");
const sessionPrefix = `db-ci-${Date.now()}`;

if (!databaseUrl) {
  throw new Error("DATABASE_URL is required for database integration");
}
if (!Number.isInteger(concurrency) || concurrency < 2) {
  throw new Error("DB_TEST_CONCURRENCY must be an integer of at least 2");
}

await verifyMigrationHistory();
let server;
try {
  server = await startServer();
  const sessionIds = Array.from({ length: concurrency }, (_, index) => `${sessionPrefix}-${index}`);
  await Promise.all(sessionIds.map((sessionId, index) => putSession(sessionId, index)));
  await assertSessions(sessionIds, "before restart");

  await stopServer(server);
  server = await startServer();
  await assertSessions(sessionIds, "after restart");
  await verifyRows(sessionIds);
  console.log(`database integration ok: fresh migration history, ${concurrency} concurrent writes, and restart hydration verified`);
} finally {
  await stopServer(server);
}

async function startServer() {
  const child = spawn(process.execPath, [join(root, "apps", "api", "dist", "main.js")], {
    cwd: root,
    env: {
      ...process.env,
      NODE_ENV: "production",
      PORT: new URL(baseUrl).port || "3011",
      APP_SECURITY_ENABLED: "true",
      APP_PRISMA_ENABLED: "true",
      APP_JWT_SECRET: "ci-database-integration-secret-at-least-32-bytes",
      APP_DEMO_API_KEY: apiKey,
      APP_LLM_ENABLED: "false",
      APP_INGESTION_QUEUE_BACKEND: "in-memory",
      APP_INGESTION_WORKER_ENABLED: "false",
      APP_WORKFLOW_ASYNC_ENABLED: "false",
      APP_AUDIT_RETENTION_WORKER_ENABLED: "false"
    },
    stdio: ["ignore", "ignore", "inherit"]
  });
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`database-backed API exited before readiness with code ${child.exitCode}`);
    }
    if (await readinessOk()) {
      return child;
    }
    await delay(250);
  }
  child.kill("SIGTERM");
  throw new Error(`database-backed API did not become ready at ${baseUrl}`);
}

async function putSession(sessionId, index) {
  const response = await fetch(`${baseUrl}/ai/sessions/${sessionId}`, {
    method: "PUT",
    headers: requestHeaders(),
    body: JSON.stringify({
      id: sessionId,
      title: `Concurrent session ${index}`,
      updatedAt: Date.now(),
      modelProfile: "balanced",
      streaming: false,
      pinned: index % 2 === 0,
      archived: false,
      workspaceId: "ci",
      activeBranchId: "main",
      branches: [{
        id: "main",
        title: "Main",
        parentBranchId: null,
        parentMessageId: null,
        updatedAt: Date.now(),
        messages: [],
        traceSteps: []
      }]
    })
  });
  const body = await response.text();
  if (!response.ok) {
    throw new Error(`concurrent session write failed for ${sessionId}: ${response.status} ${body}`);
  }
}

async function assertSessions(sessionIds, phase) {
  const response = await fetch(`${baseUrl}/ai/sessions?page=1&pageSize=${sessionIds.length + 5}&workspace=ci`, {
    headers: requestHeaders(false)
  });
  const json = await response.json();
  if (!response.ok || json?.ok !== 1 || !Array.isArray(json?.data?.items)) {
    throw new Error(`session list ${phase} failed: ${response.status} ${JSON.stringify(json)}`);
  }
  const observed = new Set(json.data.items.map((item) => item.id));
  const missing = sessionIds.filter((sessionId) => !observed.has(sessionId));
  if (missing.length > 0) {
    throw new Error(`session list ${phase} missing ${missing.join(", ")}`);
  }
}

async function readinessOk() {
  try {
    const response = await fetch(`${baseUrl}/actuator/health/readiness`, { headers: requestHeaders(false) });
    const json = await response.json();
    return response.ok
      && json?.status === "UP"
      && json?.components?.enabled === true
      && json?.components?.database === "UP"
      && json?.components?.persistence === "UP";
  } catch {
    return false;
  }
}

async function verifyMigrationHistory() {
  const prisma = await prismaClient();
  try {
    const rows = await prisma.$queryRawUnsafe(`
      SELECT COUNT(*) AS count_value
      FROM _prisma_migrations
      WHERE finished_at IS NOT NULL AND rolled_back_at IS NULL
    `);
    const count = Number(rows[0]?.count_value ?? 0);
    if (count < 14) {
      throw new Error(`expected at least 14 applied Prisma migrations, found ${count}`);
    }
  } finally {
    await prisma.$disconnect();
  }
}

async function verifyRows(sessionIds) {
  const prisma = await prismaClient();
  try {
    const count = await prisma.agentSessionState.count({ where: { sessionId: { in: sessionIds } } });
    if (count !== sessionIds.length) {
      throw new Error(`expected ${sessionIds.length} persisted session rows, found ${count}`);
    }
  } finally {
    await prisma.$disconnect();
  }
}

async function prismaClient() {
  const requireFromApi = createRequire(join(root, "apps", "api", "package.json"));
  const { PrismaClient } = requireFromApi("@prisma/client");
  const prisma = new PrismaClient();
  await prisma.$connect();
  return prisma;
}

function requestHeaders(json = true) {
  return {
    "x-api-key": apiKey,
    "x-tenant-id": "public",
    ...(json ? { "content-type": "application/json" } : {})
  };
}

async function stopServer(child) {
  if (!child || child.exitCode !== null) {
    return;
  }
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    delay(5000).then(() => child.kill("SIGKILL"))
  ]);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
