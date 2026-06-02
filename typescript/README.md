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
pnpm install
pnpm typecheck
pnpm test
pnpm parity
pnpm db:validate
pnpm contract:diff
pnpm frontend:contract
pnpm migration:readiness
pnpm maturity:gate
pnpm e2e:smoke
pnpm perf:smoke
LOAD_VUS=50 LOAD_DURATION_SECONDS=180 pnpm load:gate
pnpm sbom
pnpm build
pnpm --filter @knowledgeops/api dev
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
APP_JAVA_BASE_URL=http://localhost:8080 APP_TS_BASE_URL=http://localhost:3000 pnpm contract:diff
```

## Migration Rule

The Java implementation remains in the repository as the baseline. TypeScript modules are considered parity-ready when their route contract, local behavior tests, database mapping, and CI checks pass.
