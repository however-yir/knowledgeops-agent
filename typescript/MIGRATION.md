# TypeScript Migration Plan

Java remains in place while the TypeScript implementation grows under `typescript/`.

| Java area | TypeScript target | Status | Verification |
|---|---|---|---|
| `src/main/java/com/enterprise/iqk/config` | `apps/api/src/config` | Parity-ready | `pnpm typecheck` |
| `src/main/java/com/enterprise/iqk/controller` | `apps/api/src/*` controllers | Parity-ready | `pnpm parity` + smoke |
| `src/main/java/com/enterprise/iqk/security` | `apps/api/src/auth` | Parity-ready | API key/JWT test + route permission guard + audit/rate-limit/headers |
| `src/main/resources/db/migration` | `prisma/schema.prisma` + `PrismaPersistenceService` + `PlatformStore` fallback | Parity-ready | `pnpm db:validate` + persisted state + MySQL bridge |
| `src/main/java/com/enterprise/iqk/ingestion` | `apps/api/src/ingestion` | Parity-ready | Idempotent upload/job/chunk/retry/DLQ worker tests + Redis Stream mode |
| `src/main/java/com/enterprise/iqk/retrieval` | `apps/api/src/ai/retrieval.service.ts` | Parity-ready | Hybrid local/pgvector/BM25/graph/web/rerank/evidence tests |
| `src/main/java/com/enterprise/iqk/rag` | `apps/api/src/ai` | Parity-ready | Upload then PDF chat smoke + contract diff |
| `src/main/java/com/enterprise/iqk/memory` | `apps/api/src/operations` + `prisma/schema.prisma` | Parity-ready | Memory item/event routes + table mapping |
| `src/main/java/com/enterprise/iqk/graph` | `apps/api/src/operations` + `prisma/schema.prisma` | Parity-ready | Graph entity/relation/fact routes + table mapping |
| `src/main/java/com/enterprise/iqk/agent/harness` | `apps/api/src/agent` | Parity-ready | Preview/execute + policy + workspace/rag/memory/graph runtimes |
| `src/main/java/com/enterprise/iqk/agent/workflow` | `apps/api/src/workflow` | Parity-ready | Task/step/event/research routes + async worker + LLM planner/writer |
| `src/main/java/com/enterprise/iqk/evaluation` | `apps/api/src/evaluation` | Parity-ready | Dataset/run weighted scoring + reports |
| `src/main/java/com/enterprise/iqk/repository/ChatHistoryRepository` | `apps/api/src/history` | Parity-ready | History service test + route parity |
| `performance/k6` | `scripts/perf-smoke.mjs` + `scripts/load-gate.mjs` | Parity-ready | auto-start compiled API + p95/p99/failure gate |
| `frontend/src/api/client.ts` | Existing frontend env switch + TS backend helpers | Parity-ready | `pnpm frontend:contract` + frontend build |
| `.github/workflows` | `.github/workflows/typescript.yml` | Parity-ready | CI runs TS checks, MySQL/Redis services, contract, perf, Docker |

## First Milestone

1. Keep the Java version tagged as `java-baseline-2026-05-31`.
2. Build a TypeScript API skeleton that can run independently.
3. Port one endpoint family at a time, preserving route shape and response semantics.

## Cutover And Rollback

1. Run Java and TypeScript together against a staging copy of MySQL.
2. Keep `APP_PRISMA_ENABLED=false` for the first TS smoke, then enable it and run `pnpm db:validate`.
3. Run live diff with `APP_JAVA_BASE_URL=http://java-host APP_TS_BASE_URL=http://ts-host pnpm contract:diff`.
4. Send shadow read traffic to TS and compare status, content type, JSON schema, SSE events, auth decisions, and pagination.
5. For rollback, keep Java schema-compatible Flyway migrations as the source of truth. TS writes only mapped tables and can be disabled by setting `APP_PRISMA_ENABLED=false`; traffic can be moved back to Java without data shape conversion.
6. For high-risk rollout, run dual-write only for append-safe audit/evaluation/harness tables first, then enable authoritative TS writes for ingestion, memory, graph, sessions, and cost after the contract diff stays clean.

## Maturity Equivalence Gate

The TypeScript rewrite is considered Java-maturity-equivalent only when these evidence gates pass together:

| Gate | Evidence |
|---|---|
| API contract | `pnpm parity` and `pnpm contract:diff` cover health, OpenAPI, auth, chat, SSE, RAG, ingestion, history, sessions, harness, workflow, evaluation, cost, audit, metrics, memory, graph, and negative cases. |
| security and tenant boundary | Auth service, auth guard, retrieval, workflow, and cost tests verify invalid credentials, tenant mismatch, role authorization, and tenant-scoped state. |
| data persistence | `pnpm db:validate` and `pnpm migration:readiness` verify Prisma mappings for the Java Flyway runtime tables and the rollout/rollback plan. |
| frontend cutover | `pnpm frontend:contract` verifies that the existing Vue client calls are present in the TypeScript backend contract. |
| observability and performance | `pnpm e2e:smoke`, `pnpm perf:smoke`, `pnpm load:gate`, Prometheus contract cases, and SBOM generation run in CI. |
| rollback | Keep Java as the schema-compatible fallback until shadow traffic, contract diff, and operational SLOs stay clean on TypeScript. |

`pnpm maturity:gate` enforces that these evidence categories remain present in the repository and CI before the branch can be treated as cutover-ready.
