# KnowledgeOps Agent TypeScript Rewrite

This directory contains the TypeScript rewrite alongside the existing Java/Spring Boot implementation.

## Layout

```text
apps/api/           NestJS API scaffold
apps/web/           Reserved for a future TypeScript web app, if needed
packages/shared/    Shared DTOs and response helpers
prisma/             TypeScript-side database model mapping
```

## Local Commands

```bash
cd typescript
pnpm install
pnpm typecheck
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
GET  /ai/pdf/chat
POST /ai/pdf/upload/:chatId
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
GET  /ai/memory/items
GET  /ai/graph/entities
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

State is persisted locally through `APP_STATE_FILE` so the TypeScript API can run without MySQL while the Prisma mapping is being completed. Docker enables `APP_SECURITY_ENABLED=true`, so protected routes require either:

```text
Authorization: Bearer <jwt>
X-API-Key: local-demo-api-key
```

## Migration Rule

The Java implementation remains the source of truth until a TypeScript module has matching API contract tests and is marked complete in `MIGRATION.md`.
