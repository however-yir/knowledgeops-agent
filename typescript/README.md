# KnowledgeOps Agent TypeScript Rewrite

This directory contains the TypeScript rewrite alongside the existing Java/Spring Boot implementation.

## Layout

```text
apps/api/           NestJS API runtime
apps/web/           Reserved for a future TypeScript web app, if needed
packages/shared/    Shared DTOs and response helpers
prisma/             TypeScript-side database model mapping
```

## Local Commands

```bash
cd typescript
pnpm install --frozen-lockfile
pnpm db:generate
pnpm db:schema:validate
pnpm typecheck
pnpm test:coverage
pnpm build
pnpm inventory:all
pnpm security:audit
pnpm e2e:smoke
pnpm perf:smoke
LOAD_VUS=50 LOAD_DURATION_SECONDS=180 pnpm load:gate
pnpm --filter @knowledgeops/api dev
```

The `inventory:*` commands check that expected files, route fragments, table mappings, frontend path strings, rollout topics, and declared deployment settings remain represented. `inventory:java-baseline` additionally pins the 2026-07-21 Java baseline's 15 controller sources, 48 route declarations, 31 public DTOs, 15 core service responsibilities, 26 Mapper-to-Prisma-model pairs, and 13 Flyway-to-Prisma migrations to explicit TypeScript anchors. It checks all 31 baseline DTOs and 217 key fields, with the `thought` to `thoughtSummary` rename and time-value representations documented explicitly. A change to one of those Java baseline sets requires an intentional TypeScript mapping update. These are deliberately static checks: they do not start Java, compare DTO optionality, nested shape, or service behavior, apply a migration, execute CI, or prove runtime equivalence.

`e2e:smoke` runs the local fallback path without an external model, vector database, or search backend. In addition to the core upload/chat/session/evaluation journey, it executes all 37 declared contract cases against the TypeScript runtime. This proves the declared TypeScript demo surface is locally executable; it is not a Java-vs-TypeScript comparison.

Database integration requires a fresh migrated MySQL database and explicitly enabled Prisma:

```bash
DATABASE_URL=mysql://root:root@127.0.0.1:3307/knowledgeops_agent APP_PRISMA_ENABLED=true pnpm db:migrate
APP_BOOTSTRAP_DEMO_KEY=true APP_DEMO_API_KEY=ci-database-integration-key DATABASE_URL=mysql://root:root@127.0.0.1:3307/knowledgeops_agent pnpm db:seed-demo
DATABASE_URL=mysql://root:root@127.0.0.1:3307/knowledgeops_agent APP_PRISMA_ENABLED=true APP_DEMO_API_KEY=ci-database-integration-key pnpm db:integration
```

The initial API exposes a Java-compatible health endpoint:

```text
GET http://localhost:3000/actuator/health
GET http://localhost:3000/health
```

All JSON API responses use the enterprise envelope:

```json
{ "ok": 1, "msg": "ok", "data": {} }
```

JSON error responses use:

```json
{ "ok": 0, "msg": "error message", "code": "ERROR_CODE", "traceId": "trace_..." }
```

Protocol endpoints keep their protocol payloads: `/actuator/prometheus` and `/metrics` return Prometheus text, `/v3/api-docs` returns OpenAPI JSON, and `*/stream` endpoints return SSE events whose final `done` event contains the same response envelope.

The enterprise contract surface includes:

```text
POST /auth/token
POST /auth/refresh
POST /auth/api-keys
GET  /actuator/health
GET  /health
GET  /actuator/prometheus
GET  /metrics
POST /ai/chat
POST /ai/chat/stream
POST /ai/react/chat
POST /ai/react/chat/stream
GET  /ai/service
POST /ai/pdf/chat
POST /ai/pdf/upload/{chatId}
POST /ingestion/upload/{chatId}
GET  /ingestion/jobs
GET  /ingestion/jobs/{jobId}
GET  /ai/pdf/file/:chatId
GET  /ai/history/:type
GET  /ai/history/:type/:chatId
GET  /ai/sessions
GET  /ai/sessions/{sessionId}
POST /ai/feedback
POST /ai/harness/actions/preview
POST /ai/harness/actions/execute/:token
GET  /ai/workflow/tasks
POST /ai/research/tasks
GET  /ai/evaluation/datasets
POST /ai/evaluation/datasets
POST /ai/evaluation/runs
GET  /cost/summary
POST /cost/budget
GET  /audit/logs
GET  /ai/memory/items
POST /ai/memory/items
GET  /ai/memory/context
POST /ai/memory/cleanup
GET  /ai/graph/entities
POST /ai/graph/entities
GET  /ai/graph/entities/:entityId/neighbors
GET  /ai/graph/facts
POST /ai/graph/relations
POST /ai/graph/facts
```

Fixed request headers:

```text
Authorization: Bearer <jwt-or-refresh-token>
X-API-Key: <api-key>
X-Tenant-ID: <tenant-id>
```

Fixed response payload fields:

- Chat: `answer`, `model`, `usage`, `traceId`
- RAG: `answer`, `citations`, `evidence`, `retrievalStats`
- Citation: `id`, `source`, `title`, `chunkId`, `snippet`
- Agent trace: `step`, `thoughtSummary`, `action`, `actionInput`, `observation`
- Cost summary: `tenantId`, `monthCostUsd`, `monthlyBudgetUsd`, `budgetRemainingUsd`
- Audit log: `tenantId`, `principal`, `method`, `path`, `status`, `createdAt`

To point the existing Vue frontend at the TypeScript API:

```bash
cd ../frontend
cp .env.typescript.example .env.local
npm run dev
```

The local TypeScript demo API key defaults to:

```text
local-demo-api-key
```

State is persisted locally through `APP_STATE_FILE` for CI and single-node deployments. For production, set `APP_PRISMA_ENABLED=true` and `DATABASE_URL=mysql://...`; the Prisma persistence bridge writes auth, API key, refresh token hash, audit, ingestion, sessions, chunks, workflow, memory, graph, evaluation, cost, exposure, and harness-event state into MySQL with transaction/upsert semantics. Docker enables `APP_SECURITY_ENABLED=true`, so protected routes require either:

```text
Authorization: Bearer <jwt>
X-API-Key: local-demo-api-key
```

When security is enabled, the TypeScript API applies the same route-level `PERM_*` authorization matrix used by the Java Spring Security configuration, writes non-actuator requests to the audit log store, applies token-bucket rate limiting, and exposes Prometheus text metrics at `/actuator/prometheus`.

The TypeScript runtime now includes Java-parity local implementations for:

- OpenAI-compatible LLM generation and provider SSE streaming with model routing, timeout/retry, usage capture, and deterministic fallback
- hybrid retrieval over local vectors or pgvector endpoint, embedding model calls, BM25/keyword matches, graph facts/entities, optional web-search backend, reranker endpoint, evidence judge endpoint, citations, and retrieval stats
- ingestion idempotency, file safety checks, MIME/size limits, retry delay, DLQ status, background worker mode, Redis Stream or RabbitMQ queue mode, and chunk indexing
- tenant cost governance, budget hard limits, model routing, and quality-vs-cost exposure logging
- memory items/events/context snapshots/cleanup, graph entities/relations/facts/neighbors, workflow task/step/event lifecycle with optional async worker and LLM planner/writer, distributed rate-limit option, audit retention worker, Java-parity education tools, and trusted agent actions including workspace list/read/search/diff/apply/shell plus MCP HTTP adapter

Production feature flags:

```bash
APP_LLM_ENABLED=true
OPENAI_API_KEY=...
APP_PRISMA_ENABLED=true
DATABASE_URL=mysql://user:pass@host:3306/knowledgeops_agent
APP_INGESTION_WORKER_ENABLED=true
APP_INGESTION_QUEUE_BACKEND=redis_stream
APP_REDIS_URL=redis://redis:6379
APP_RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672
APP_WORKFLOW_ASYNC_ENABLED=true
APP_VECTOR_BACKEND=pgvector
APP_PGVECTOR_ENDPOINT=https://vector.example.com
APP_EMBEDDING_ENABLED=true
APP_WEB_SEARCH_ENABLED=true
APP_WEB_SEARCH_BACKEND=searxng
APP_WEB_SEARCH_SEARXNG_URL=https://search.example.com
# or:
# APP_WEB_SEARCH_BACKEND=bing
# APP_WEB_SEARCH_BING_API_KEY=...
RAG_RERANK_ENDPOINT=https://reranker.example.com/rerank
RAG_EVIDENCE_JUDGE_ENDPOINT=https://judge.example.com/judge
APP_DISTRIBUTED_RATE_LIMIT_ENABLED=true
APP_AUDIT_RETENTION_WORKER_ENABLED=true
APP_MCP_HTTP_ALLOWLIST=https://mcp.example.com/
```

Before enabling Prisma in a production image or host, generate the Prisma client for the checked-in schema:

```bash
pnpm db:generate
```

With the API running, use the local performance smoke to guard the same p95/error-rate SLO shape as the Java k6 profile:

```bash
BASE_URL=http://localhost:3000 pnpm perf:smoke
```

For local Docker deployment:

```bash
docker compose --profile enterprise up --build
```

The compose profile starts the API, MySQL, Redis, and RabbitMQ. Redis Stream is the default production ingestion queue in the profile; RabbitMQ remains available as a compatible queue backend.

To run a live Java-vs-TS contract comparison, start both services and set:

```bash
APP_JAVA_BASE_URL=http://localhost:8080 APP_TS_BASE_URL=http://localhost:3000 pnpm contract:diff:live
```

`contract:diff:live` fails when either URL is absent, unreachable, or produces a contract mismatch. The regular workflow does not start Java and does not run this comparator, so it makes no automatic live-parity claim. Run it only against externally started, equivalently seeded services; set `APP_CONTRACT_API_KEY` when protected routes use a shared key.

The Java oracle currently returns 500 for `/v3/api-docs` because springdoc calls an incompatible Spring method and raises `NoSuchMethodError`. That endpoint is excluded from the shared live diff as an oracle defect, not counted as a TypeScript parity pass. TypeScript `/v3/api-docs`, `/health`, and `/metrics` remain executable TypeScript extension checks in `e2e:smoke`.

## CI Evidence

The TypeScript workflow separates quality, MySQL integration, runtime smoke/load, dependency/SBOM, Docker/Compose/image, and Helm verification. Its static inventory gate includes the Java-baseline map (15 controller sources, 48 route declarations, 31 DTOs, 15 core services, 26 Mapper/Prisma pairs, 13 migration pairs, and 217 key DTO fields), implementation surface, contract cases, Prisma tables, frontend paths, cutover topics, and deployment settings. Runtime smoke runs performance and load against fresh MySQL state before it executes all 37 declared local contract cases. Coverage includes all `src/**/*.ts` files, not only modules imported by tests. The shared package enforces 90% lines/statements/functions and 85% branches. The API currently ratchets at 40% lines, 39% statements, 32% functions, and 24% branches from the measured 2026-07-22 baseline of 40.00%, 39.02%, 32.50%, and 24.06%. Raise those thresholds as tests are added; the target remains 90% lines/statements/functions and 85% branches.

CI generates the CycloneDX JSON SBOM with pinned Syft, validates it with a checksum-verified CycloneDX CLI, and uploads it. The checked-in hand-written `CycloneDX-lite` generator has been removed.

## Migration Rule

The read-only Java oracle baseline used for this evidence is commit `ac62bb3a83239b1b3a8701fcdcad7d337c2c400a` (2026-07-21). Static TypeScript inventories are not Java parity evidence. Runtime parity requires the explicit live diff plus environment-specific behavioral, migration, security, and operational acceptance evidence.
