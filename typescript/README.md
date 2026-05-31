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
pnpm parity
pnpm db:validate
pnpm build
pnpm --filter @knowledgeops/api dev
```

The initial API exposes a Java-compatible health endpoint:

```text
GET http://localhost:3000/actuator/health
```

The current contract surface also includes:

```text
POST /auth/token
POST /auth/refresh
POST /auth/api-keys
POST /ai/react/chat
POST /ai/react/chat/stream
GET  /ai/chat
GET  /ai/service
GET  /ai/pdf/chat
POST /ai/pdf/upload/:chatId
GET  /ai/pdf/file/:chatId
GET  /ai/history/:type
GET  /ai/history/:type/:chatId
POST /ingestion/upload/:chatId
GET  /ingestion/jobs
GET  /ingestion/jobs/:jobId
POST /ai/harness/actions/preview
POST /ai/harness/actions/execute/:token
GET  /ai/workflow/tasks
POST /ai/research/tasks
GET  /ai/evaluation/datasets
POST /ai/evaluation/datasets
GET  /cost/summary
GET  /audit/logs
GET  /actuator/prometheus
GET  /ai/memory/items
POST /ai/memory/items
GET  /ai/graph/entities
POST /ai/graph/entities
POST /ai/graph/relations
POST /ai/graph/facts
```

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

State is persisted locally through `APP_STATE_FILE` for CI and single-node deployments, while `prisma/schema.prisma` keeps the MySQL table model aligned with the Java Flyway schema. Docker enables `APP_SECURITY_ENABLED=true`, so protected routes require either:

```text
Authorization: Bearer <jwt>
X-API-Key: local-demo-api-key
```

When security is enabled, the TypeScript API applies the same route-level `PERM_*` authorization matrix used by the Java Spring Security configuration, writes non-actuator requests to the audit log store, applies token-bucket rate limiting, and exposes Prometheus text metrics at `/actuator/prometheus`.

The TypeScript runtime now includes Java-parity local implementations for:

- hybrid retrieval over vector-like hashed embeddings, keyword matches, graph facts/entities, and optional web-search configuration
- ingestion idempotency, file safety checks, retry metadata, and chunk indexing
- tenant cost governance, budget hard limits, model routing, and quality-vs-cost exposure logging
- memory items/events, graph entities/relations/facts, workflow task/step/event lifecycle, and trusted agent actions

With the API running, use the local performance smoke to guard the same p95/error-rate SLO shape as the Java k6 profile:

```bash
BASE_URL=http://localhost:3000 pnpm perf:smoke
```

## Migration Rule

The Java implementation remains in the repository as the baseline. TypeScript modules are considered parity-ready when their route contract, local behavior tests, database mapping, and CI checks pass.
