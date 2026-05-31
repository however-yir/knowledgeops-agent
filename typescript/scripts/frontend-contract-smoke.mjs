import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");
const client = readFileSync(join(repoRoot, "frontend", "src", "api", "client.ts"), "utf8");
const manifest = JSON.parse(readFileSync(join(repoRoot, "typescript", "parity", "manifest.json"), "utf8"));
const sourceRoutes = new Set(manifest.requiredRoutes.map((route) => route.label));

const requiredClientCalls = [
  "/auth/token",
  "/auth/refresh",
  "/ai/react/chat",
  "/ai/react/chat/stream",
  "/ai/pdf/upload/",
  "/ai/sessions",
  "/ai/evaluation/datasets",
  "/cost/summary",
  "/ai/memory/items",
  "/ai/graph/entities"
];

const missingClientCalls = requiredClientCalls.filter((path) => !client.includes(path));
if (missingClientCalls.length > 0) {
  for (const path of missingClientCalls) {
    console.error(`frontend client missing TS backend call: ${path}`);
  }
  process.exit(1);
}

const missingBackendCoverage = ["/ai/react/chat", "/ai/react/chat/stream", "/cost/summary", "/ai/memory/items", "/ai/graph/entities"]
  .filter((path) => ![...sourceRoutes].some((label) => label.includes(path)));
if (missingBackendCoverage.length > 0) {
  for (const path of missingBackendCoverage) {
    console.error(`parity manifest missing frontend route: ${path}`);
  }
  process.exit(1);
}

console.log(`frontend contract smoke ok: ${requiredClientCalls.length} client calls mapped to TS backend`);
