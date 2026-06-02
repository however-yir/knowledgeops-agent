import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const repoRoot = join(root, "..");
const packageJson = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const contractCases = JSON.parse(readFileSync(join(root, "parity", "contract-cases.json"), "utf8"));
const migration = readFileSync(join(root, "MIGRATION.md"), "utf8");
const workflow = readFileSync(join(repoRoot, ".github", "workflows", "typescript.yml"), "utf8");

const requiredContractTags = [
  "health",
  "openapi",
  "auth",
  "chat",
  "sse",
  "rag",
  "ingestion",
  "history",
  "sessions",
  "harness",
  "workflow",
  "evaluation",
  "cost",
  "audit",
  "metrics",
  "memory",
  "graph",
  "negative"
];

const requiredSpecs = [
  "apps/api/src/auth/auth.service.spec.ts",
  "apps/api/src/auth/auth.guard.spec.ts",
  "apps/api/src/ingestion/ingestion.service.spec.ts",
  "apps/api/src/ai/retrieval.service.spec.ts",
  "apps/api/src/agent/harness.controller.spec.ts",
  "apps/api/src/workflow/workflow.service.spec.ts",
  "apps/api/src/evaluation/evaluation.controller.spec.ts",
  "apps/api/src/history/history.service.spec.ts",
  "apps/api/src/platform/tenant-cost.service.spec.ts"
];

const requiredMigrationPhrases = [
  "Maturity Equivalence Gate",
  "API contract",
  "security and tenant boundary",
  "data persistence",
  "frontend cutover",
  "observability and performance",
  "rollback"
];

const failures = [];
const tagSet = new Set(contractCases.flatMap((testCase) => testCase.tags ?? []));
for (const tag of requiredContractTags) {
  if (!tagSet.has(tag)) {
    failures.push(`contract cases missing maturity tag: ${tag}`);
  }
}

if (contractCases.length < 24) {
  failures.push(`contract case count ${contractCases.length} is below maturity floor 24`);
}

for (const spec of requiredSpecs) {
  if (!existsSync(join(root, spec))) {
    failures.push(`required maturity spec missing: ${spec}`);
  }
}

for (const phrase of requiredMigrationPhrases) {
  if (!migration.includes(phrase)) {
    failures.push(`migration maturity standard missing phrase: ${phrase}`);
  }
}

if (!packageJson.scripts?.["prod:gate"]?.includes("maturity:gate")) {
  failures.push("prod:gate does not include maturity:gate");
}

if (!packageJson.scripts?.["prod:gate"]?.includes("security:defaults")) {
  failures.push("prod:gate does not include security:defaults");
}

if (!workflow.includes("pnpm maturity:gate")) {
  failures.push("TypeScript CI does not run maturity:gate");
}

if (failures.length) {
  for (const failure of failures) {
    console.error(failure);
  }
  process.exit(1);
}

console.log(`maturity gate ok: ${contractCases.length} contract cases, ${requiredSpecs.length} spec surfaces, ${requiredContractTags.length} tags`);
