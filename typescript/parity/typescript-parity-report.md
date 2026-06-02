# TypeScript Parity Report

Date: 2026-06-03

## Decision

The TypeScript target is implemented as a Node enterprise service using NestJS on the Fastify adapter. It is not limited to frontend code or scripts.

## Contract Status

- Response envelope: JSON responses return `ok`, `msg`, and `data`.
- Error envelope: JSON errors return `ok: 0`, `msg`, `code`, and `traceId`.
- Fixed request headers: `Authorization`, `X-API-Key`, `X-Tenant-ID`.
- Chat request fields: `chatId`, `prompt`, `modelProfile`.
- Chat response fields: `answer`, `model`, `usage`, `traceId`.
- RAG response fields: `answer`, `citations`, `evidence`, `retrievalStats`.
- Citation fields: `id`, `source`, `title`, `chunkId`, `snippet`.
- Agent trace fields: `step`, `thoughtSummary`, `action`, `actionInput`, `observation`.
- Cost summary fields: `tenantId`, `monthCostUsd`, `monthlyBudgetUsd`, `budgetRemainingUsd`.
- Audit log fields: `tenantId`, `principal`, `method`, `path`, `status`, `createdAt`.

Protocol exceptions are intentional: `/actuator/prometheus` and `/metrics` return Prometheus text, `/v3/api-docs` returns raw OpenAPI JSON, file download endpoints return binary streams, and SSE endpoints return event streams whose final `done` event contains the response envelope.

## Required Enterprise Surface

Implemented routes include:

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
POST /ai/pdf/upload/{chatId}
POST /ingestion/upload/{chatId}
GET  /ingestion/jobs
GET  /ingestion/jobs/{jobId}
POST /ai/pdf/chat
GET  /ai/sessions
GET  /ai/sessions/{sessionId}
POST /ai/feedback
GET  /ai/evaluation/datasets
POST /ai/evaluation/runs
GET  /audit/logs
GET  /cost/summary
POST /cost/budget
```

Additional parity surfaces remain available for history, harness actions, workflow/research tasks, memory, and graph APIs.

## Capability Coverage

- Auth and tenant isolation: API key, JWT, refresh token, RBAC guard, `X-Tenant-ID` context.
- Chat and streaming: standard Chat, ReAct Chat, and SSE streaming endpoints.
- Agent: ReAct response trace plus trusted tool action schemas and harness execution surfaces.
- RAG: upload, ingestion job lifecycle, chunking, local vector fallback, pgvector-compatible endpoint abstraction, keyword/BM25 retrieval, hybrid retrieval, citation builder, evidence judge, and no-evidence refusal.
- Operations: sessions, feedback, evaluation datasets/runs, cost summary/budget update, audit logs, rate limit, health, metrics.
- Deployment: Dockerfile, compose `enterprise`/`typescript` profile, Redis Stream priority queue backend, MySQL/Redis/RabbitMQ local services.
- Quality gates: API contract diff, vitest unit tests, e2e smoke, perf smoke, maturity gate, migration readiness, Prisma schema validation, frontend contract smoke, security defaults check.

## Verification

Last successful gate run:

```text
pnpm prod:gate
```

Results:

```text
parity ok: 26 files, 71 routes
prisma schema parity ok: 32 Java tables mapped
contract diff static ok: 40 cases
frontend contract smoke ok: 10 client calls mapped to TS backend
migration readiness ok: 25 runtime tables and rollback plan covered
maturity gate ok: 40 contract cases, 9 spec surfaces, 18 tags
security defaults ok: 8 checks
e2e smoke ok
perf smoke: 40 iterations, concurrency 8, p95 205.5ms, failureRate 0
```
