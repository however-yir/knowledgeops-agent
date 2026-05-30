# TypeScript Migration Plan

Java remains in place while the TypeScript implementation grows under `typescript/`.

| Java area | TypeScript target | Status | Verification |
|---|---|---|---|
| `src/main/java/com/enterprise/iqk/config` | `apps/api/src/config` | Contract scaffold | `pnpm typecheck` |
| `src/main/java/com/enterprise/iqk/controller` | `apps/api/src/*` controllers | Local implementation | `pnpm parity` + smoke |
| `src/main/java/com/enterprise/iqk/security` | `apps/api/src/auth` | Local implementation | API key/JWT test + optional guard |
| `src/main/resources/db/migration` | `prisma/schema.prisma` + `PlatformStore` state file | Local implementation | Schema review + persisted state |
| `src/main/java/com/enterprise/iqk/ingestion` | `apps/api/src/ingestion` | Local implementation | Idempotent upload/job/chunk tests |
| `src/main/java/com/enterprise/iqk/retrieval` | `apps/api/src/ai/retrieval.service.ts` | Local implementation | Token-overlap retrieval tests |
| `src/main/java/com/enterprise/iqk/rag` | `apps/api/src/ai` | Local implementation | Upload then PDF chat smoke |
| `src/main/java/com/enterprise/iqk/memory` | `apps/api/src/operations` | Contract scaffold | Memory item routes |
| `src/main/java/com/enterprise/iqk/graph` | `apps/api/src/operations` | Contract scaffold | Graph entity routes |
| `src/main/java/com/enterprise/iqk/agent/harness` | `apps/api/src/agent` | Local implementation | Preview/execute + rag_query runtime |
| `src/main/java/com/enterprise/iqk/agent/workflow` | `apps/api/src/workflow` | Local implementation | Task/event/research routes |
| `src/main/java/com/enterprise/iqk/evaluation` | `apps/api/src/evaluation` | Local implementation | Dataset/run scoring |
| `src/main/java/com/enterprise/iqk/repository/ChatHistoryRepository` | `apps/api/src/history` | Local implementation | History service test + route parity |
| `performance/k6` | `scripts/perf-smoke.mjs` | Local implementation | `BASE_URL=... pnpm perf:smoke` |
| `frontend/src/api/client.ts` | Existing frontend env switch | Local implementation | `VITE_API_BASE_URL` |
| `.github/workflows` | `.github/workflows/typescript.yml` | Local implementation | CI runs TS checks + parity |

## First Milestone

1. Keep the Java version tagged as `java-baseline-2026-05-31`.
2. Build a TypeScript API skeleton that can run independently.
3. Port one endpoint family at a time, preserving route shape and response semantics.
