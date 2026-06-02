import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dockerfile = readFileSync(join(root, "Dockerfile"), "utf8");
const compose = readFileSync(join(root, "docker-compose.yml"), "utf8");

const requiredChecks = [
  ["Docker runtime runs as non-root app user", dockerfile.includes("USER app")],
  ["Dockerfile has a container healthcheck", dockerfile.includes("HEALTHCHECK")],
  ["Compose enables production auth", compose.includes('APP_SECURITY_ENABLED: "true"')],
  ["Compose enables rate limiting", compose.includes('APP_RATE_LIMIT_ENABLED: "true"')],
  ["Compose uses Redis Stream as the primary ingestion queue", compose.includes("APP_INGESTION_QUEUE_BACKEND: redis_stream")],
  ["Compose mounts app container read-only", compose.includes("read_only: true")],
  ["Compose blocks privilege escalation", compose.includes("no-new-privileges:true")],
  ["Compose provides enterprise profile", compose.includes('profiles: ["typescript", "enterprise"]')]
];

const failures = requiredChecks.filter(([, passed]) => !passed);
if (failures.length > 0) {
  for (const [label] of failures) {
    console.error(`security default missing: ${label}`);
  }
  process.exit(1);
}

console.log(`security defaults ok: ${requiredChecks.length} checks`);
