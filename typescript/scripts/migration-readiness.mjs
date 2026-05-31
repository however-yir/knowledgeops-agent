import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const schema = readFileSync(join(root, "prisma", "schema.prisma"), "utf8");
const migration = readFileSync(join(root, "MIGRATION.md"), "utf8");

const requiredRuntimeTables = [
  "course",
  "school",
  "course_reservation",
  "api_keys",
  "refresh_tokens",
  "audit_log",
  "ingestion_job",
  "knowledge_chunk",
  "agent_session_state",
  "agent_task",
  "agent_step",
  "agent_event",
  "memory_item",
  "memory_event",
  "kg_entity",
  "kg_relation",
  "kg_fact",
  "eval_dataset",
  "eval_case",
  "eval_run",
  "eval_result",
  "tenant_budget",
  "tenant_usage_daily",
  "model_ab_exposure",
  "harness_event"
];

const mapped = new Set([...schema.matchAll(/@@map\("([^"]+)"\)/g)].map((match) => match[1]));
const missingTables = requiredRuntimeTables.filter((table) => !mapped.has(table));
const requiredDocPhrases = ["Cutover And Rollback", "shadow read traffic", "rollback", "dual-write"];
const missingDocs = requiredDocPhrases.filter((phrase) => !migration.includes(phrase));

if (missingTables.length || missingDocs.length) {
  for (const table of missingTables) {
    console.error(`migration readiness missing table: ${table}`);
  }
  for (const phrase of missingDocs) {
    console.error(`migration readiness missing doc phrase: ${phrase}`);
  }
  process.exit(1);
}

console.log(`migration readiness ok: ${requiredRuntimeTables.length} runtime tables and rollback plan covered`);
