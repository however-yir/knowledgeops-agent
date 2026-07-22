import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const cases = JSON.parse(readFileSync(join(root, "parity", "contract-cases.json"), "utf8"));
const manifest = JSON.parse(readFileSync(join(root, "parity", "manifest.json"), "utf8"));
const labels = new Set(manifest.requiredRoutes.map((route) => route.label.toLowerCase()));
const requiredTags = [
  "health", "auth", "chat", "sse", "rag", "ingestion", "history", "sessions",
  "harness", "workflow", "evaluation", "cost", "audit", "metrics", "memory", "graph", "negative"
];
const missing = cases.filter((testCase) => ![...labels].some((label) => {
  const prefix = testCase.path.split("?")[0].replace(/^\//, "").split("/").slice(0, 2).join("/");
  return label.includes(prefix);
}));
const tags = new Set(cases.flatMap((testCase) => testCase.tags ?? []));
const missingTags = requiredTags.filter((tag) => !tags.has(tag));
const invalidCases = cases.filter((testCase) =>
  typeof testCase.label !== "string"
  || typeof testCase.method !== "string"
  || typeof testCase.path !== "string"
  || !testCase.path.startsWith("/")
);

if (missing.length > 0 || missingTags.length > 0 || invalidCases.length > 0) {
  for (const testCase of missing) {
    console.error(`contract case is not represented in manifest: ${testCase.label}`);
  }
  for (const tag of missingTags) {
    console.error(`contract inventory is missing tag: ${tag}`);
  }
  for (const testCase of invalidCases) {
    console.error(`contract inventory has an invalid case: ${JSON.stringify(testCase)}`);
  }
  process.exit(1);
}

console.log(`contract inventory ok: ${cases.length} cases and ${requiredTags.length} tags are represented; this does not establish runtime parity`);
