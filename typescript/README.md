# KnowledgeOps Agent TypeScript Rewrite

This directory contains the TypeScript rewrite alongside the existing Java/Spring Boot implementation.

## Layout

```text
apps/api/           NestJS API scaffold
apps/web/           Reserved for a future TypeScript web app, if needed
packages/shared/    Shared DTOs and response helpers
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

## Migration Rule

The Java implementation remains the source of truth until a TypeScript module has matching API contract tests and is marked complete in `MIGRATION.md`.
