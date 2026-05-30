# TypeScript Migration Plan

Java remains in place while the TypeScript implementation grows under `typescript/`.

| Java area | TypeScript target | Status | Verification |
|---|---|---|---|
| `src/main/java/com/enterprise/iqk/config` | `apps/api/src/config` | Contract scaffold | `pnpm typecheck` |
| `src/main/java/com/enterprise/iqk/controller` | `apps/api/src/*` controllers | Contract scaffold | Health + route smoke |
| `src/main/java/com/enterprise/iqk/security` | `apps/api/src/auth` | Contract scaffold | API key exchange test |
| `src/main/resources/db/migration` | `prisma/schema.prisma` | Model mapping scaffold | Schema review |
| `src/main/java/com/enterprise/iqk/ingestion` | `apps/api/src/ingestion` | Contract scaffold | Upload/job routes |
| `src/main/java/com/enterprise/iqk/retrieval` | `apps/api/src/ai` | Placeholder retrieval | Java vs TS fixtures pending |
| `src/main/java/com/enterprise/iqk/rag` | `apps/api/src/ai` | Contract scaffold | PDF chat route |
| `src/main/java/com/enterprise/iqk/memory` | `apps/api/src/operations` | Contract scaffold | Memory item routes |
| `src/main/java/com/enterprise/iqk/graph` | `apps/api/src/operations` | Contract scaffold | Graph entity routes |
| `src/main/java/com/enterprise/iqk/agent/harness` | `apps/api/src/agent` | Contract scaffold | Preview/execute routes |
| `src/main/java/com/enterprise/iqk/agent/workflow` | `apps/api/src/workflow` | Contract scaffold | Task/event routes |
| `src/main/java/com/enterprise/iqk/evaluation` | `apps/api/src/evaluation` | Contract scaffold | Dataset/run routes |
| `frontend/src/api/client.ts` | Existing frontend env switch | Started | `VITE_API_BASE_URL` |
| `.github/workflows` | `.github/workflows/typescript.yml` | Started | CI runs TS checks |

## First Milestone

1. Keep the Java version tagged as `java-baseline-2026-05-31`.
2. Build a TypeScript API skeleton that can run independently.
3. Port one endpoint family at a time, preserving route shape and response semantics.
