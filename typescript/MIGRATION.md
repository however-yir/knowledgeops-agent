# TypeScript Migration Plan

Java remains in place while the TypeScript implementation grows under `typescript/`.

| Java area | TypeScript target | Status | Verification |
|---|---|---|---|
| `src/main/java/com/enterprise/iqk/config` | `apps/api/src/config` | Parity-ready | `pnpm typecheck` |
| `src/main/java/com/enterprise/iqk/controller` | `apps/api/src/*` controllers | Parity-ready | `pnpm parity` + smoke |
| `src/main/java/com/enterprise/iqk/security` | `apps/api/src/auth` | Parity-ready | API key/JWT test + route permission guard + audit/rate-limit/headers |
| `src/main/resources/db/migration` | `prisma/schema.prisma` + `PlatformStore` state file | Parity-ready | `pnpm db:validate` + persisted state |
| `src/main/java/com/enterprise/iqk/ingestion` | `apps/api/src/ingestion` | Parity-ready | Idempotent upload/job/chunk/retry tests |
| `src/main/java/com/enterprise/iqk/retrieval` | `apps/api/src/ai/retrieval.service.ts` | Parity-ready | Hybrid vector/keyword/graph/web retrieval tests |
| `src/main/java/com/enterprise/iqk/rag` | `apps/api/src/ai` | Parity-ready | Upload then PDF chat smoke |
| `src/main/java/com/enterprise/iqk/memory` | `apps/api/src/operations` + `prisma/schema.prisma` | Parity-ready | Memory item/event routes + table mapping |
| `src/main/java/com/enterprise/iqk/graph` | `apps/api/src/operations` + `prisma/schema.prisma` | Parity-ready | Graph entity/relation/fact routes + table mapping |
| `src/main/java/com/enterprise/iqk/agent/harness` | `apps/api/src/agent` | Parity-ready | Preview/execute + policy + workspace/rag/memory/graph runtimes |
| `src/main/java/com/enterprise/iqk/agent/workflow` | `apps/api/src/workflow` | Parity-ready | Task/step/event/research routes |
| `src/main/java/com/enterprise/iqk/evaluation` | `apps/api/src/evaluation` | Parity-ready | Dataset/run weighted scoring + reports |
| `src/main/java/com/enterprise/iqk/repository/ChatHistoryRepository` | `apps/api/src/history` | Parity-ready | History service test + route parity |
| `performance/k6` | `scripts/perf-smoke.mjs` | Parity-ready | `BASE_URL=... pnpm perf:smoke` |
| `frontend/src/api/client.ts` | Existing frontend env switch | Parity-ready | `VITE_API_BASE_URL` |
| `.github/workflows` | `.github/workflows/typescript.yml` | Parity-ready | CI runs TS checks + parity |

## First Milestone

1. Keep the Java version tagged as `java-baseline-2026-05-31`.
2. Build a TypeScript API skeleton that can run independently.
3. Port one endpoint family at a time, preserving route shape and response semantics.
