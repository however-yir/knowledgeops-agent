import { execFileSync, spawnSync } from "node:child_process";

const image = process.env.IMAGE_REF ?? "knowledgeops-agent-ts:ci";
const network = process.env.DOCKER_NETWORK ?? "knowledgeops-ci-security";
const mysqlContainer = process.env.MYSQL_CONTAINER ?? "knowledgeops-ci-security-mysql";
const appContainer = process.env.APP_CONTAINER ?? "knowledgeops-ci-security-app";
const hostPort = process.env.APP_HOST_PORT ?? "3013";
const apiKey = "ci-container-api-key";
const databaseUrl = `mysql://root:root@${mysqlContainer}:3306/knowledgeops_agent`;
const appEnv = [
  "-e", "NODE_ENV=production",
  "-e", "APP_SECURITY_ENABLED=true",
  "-e", "APP_PRISMA_ENABLED=true",
  "-e", `DATABASE_URL=${databaseUrl}`,
  "-e", "APP_JWT_SECRET=ci-container-security-secret-at-least-32-bytes",
  "-e", `APP_DEMO_API_KEY=${apiKey}`,
  "-e", "APP_LLM_ENABLED=false",
  "-e", "APP_INGESTION_QUEUE_BACKEND=in-memory",
  "-e", "APP_INGESTION_STORAGE_DIR=/tmp/uploads"
];

try {
  cleanup();
  docker("network", "create", network);
  docker("run", "-d", "--name", mysqlContainer, "--network", network,
    "-e", "MYSQL_DATABASE=knowledgeops_agent", "-e", "MYSQL_ROOT_PASSWORD=root", "mysql:8.4@sha256:c592c15aaf4a1961e15d82eb31ea5987dda862d1c4b1e93424438c0e91dc1f8d");
  await waitForMysql();

  docker("run", "--rm", "--network", network, ...appEnv, image, "pnpm", "db:migrate");
  docker("run", "--rm", "--network", network, ...appEnv, "-e", "APP_BOOTSTRAP_DEMO_KEY=true", image, "pnpm", "db:seed-demo");
  docker("run", "-d", "--name", appContainer, "--network", network,
    "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
    "--security-opt", "no-new-privileges=true", "--cap-drop", "ALL",
    "-p", `${hostPort}:3000`, ...appEnv, image);
  await waitForReadiness();

  const inspect = JSON.parse(execFileSync("docker", ["inspect", appContainer], { encoding: "utf8" }))[0];
  const user = inspect?.Config?.User ?? "";
  if (!user || user === "0" || user === "root") throw new Error(`runtime user is not non-root: ${JSON.stringify(user)}`);
  if (inspect?.HostConfig?.ReadonlyRootfs !== true) throw new Error("runtime root filesystem is not read-only");
  const securityOptions = inspect?.HostConfig?.SecurityOpt ?? [];
  if (!securityOptions.some((option) => option === "no-new-privileges=true" || option === "no-new-privileges:true")) {
    throw new Error(`no-new-privileges is not active: ${JSON.stringify(securityOptions)}`);
  }
  if (inspect?.HostConfig?.CapDrop?.includes("ALL") !== true) throw new Error("Linux capabilities were not dropped");

  const unauthorized = await fetch(`http://127.0.0.1:${hostPort}/ai/sessions`);
  if (unauthorized.status !== 401) throw new Error(`protected route returned ${unauthorized.status} without credentials`);
  const authorized = await fetch(`http://127.0.0.1:${hostPort}/ai/sessions`, { headers: { "x-api-key": apiKey } });
  if (!authorized.ok) throw new Error(`protected route rejected seeded API key: ${authorized.status} ${await authorized.text()}`);

  console.log(`container security smoke ok: non-root user ${user}, read-only rootfs, dropped capabilities, MySQL readiness, and auth enforced`);
} finally {
  cleanup();
}

async function waitForMysql() {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const result = spawnSync("docker", ["exec", mysqlContainer, "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-proot"], { stdio: "ignore" });
    if (result.status === 0) return;
    await delay(1000);
  }
  throw new Error("MySQL container did not become healthy");
}

async function waitForReadiness() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${hostPort}/actuator/health/readiness`, { headers: { "x-api-key": apiKey } });
      const json = await response.json();
      if (response.ok && json?.data?.components?.database === "UP" && json?.data?.components?.persistence === "UP") return;
    } catch {
      // Retry until the bounded deadline while the image initializes.
    }
    const running = spawnSync("docker", ["inspect", "-f", "{{.State.Running}}", appContainer], { encoding: "utf8" });
    if (running.status === 0 && running.stdout.trim() === "false") {
      docker("logs", appContainer);
      throw new Error("application container exited before readiness");
    }
    await delay(500);
  }
  docker("logs", appContainer);
  throw new Error("application container did not become database-ready");
}

function cleanup() {
  spawnSync("docker", ["rm", "-f", appContainer, mysqlContainer], { stdio: "ignore" });
  spawnSync("docker", ["network", "rm", network], { stdio: "ignore" });
}

function docker(...args) {
  execFileSync("docker", args, { stdio: "inherit" });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
