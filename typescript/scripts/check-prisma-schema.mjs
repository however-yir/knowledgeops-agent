import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const schema = readFileSync(join(root, "prisma", "schema.prisma"), "utf8");
const requiredTables = [
  "course",
  "school",
  "course_reservation",
  "conversation",
  "users",
  "roles",
  "permissions",
  "user_roles",
  "role_permissions",
  "api_keys",
  "refresh_tokens",
  "audit_log",
  "ingestion_job",
  "agent_session_state",
  "answer_feedback",
  "tenant_budget",
  "tenant_usage_daily",
  "model_ab_exposure",
  "agent_task",
  "agent_step",
  "agent_event",
  "kg_entity",
  "kg_relation",
  "kg_fact",
  "memory_item",
  "memory_event",
  "eval_dataset",
  "eval_case",
  "eval_run",
  "eval_result"
];

const mappedTables = new Set([...schema.matchAll(/@@map\("([^"]+)"\)/g)].map((match) => match[1]));
const missing = requiredTables.filter((table) => !mappedTables.has(table));
if (missing.length > 0) {
  for (const table of missing) {
    console.error(`missing Prisma table mapping: ${table}`);
  }
  process.exit(1);
}

console.log(`prisma schema parity ok: ${requiredTables.length} Java tables mapped`);
