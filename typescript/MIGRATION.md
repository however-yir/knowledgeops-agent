# TypeScript Migration Plan

Java remains in place while the TypeScript implementation grows under `typescript/`.

| Java area | TypeScript target | Status | Verification |
|---|---|---|---|
| `src/main/java/com/enterprise/iqk/config` | `apps/api/src/config` | Started | `pnpm typecheck` |
| `src/main/java/com/enterprise/iqk/controller` | `apps/api/src/*` controllers | Started | Health endpoint scaffold |
| `src/main/java/com/enterprise/iqk/security` | `apps/api/src/security` | Todo | Contract tests |
| `src/main/java/com/enterprise/iqk/ingestion` | `apps/api/src/ingestion` | Todo | Unit + API tests |
| `src/main/java/com/enterprise/iqk/retrieval` | `apps/api/src/retrieval` | Todo | Retrieval fixture tests |
| `src/main/java/com/enterprise/iqk/rag` | `apps/api/src/rag` | Todo | Java vs TS answer fixtures |
| `src/main/java/com/enterprise/iqk/memory` | `apps/api/src/memory` | Todo | Repository tests |
| `src/main/java/com/enterprise/iqk/graph` | `apps/api/src/graph` | Todo | Repository tests |
| `src/main/java/com/enterprise/iqk/agent/harness` | `apps/api/src/agent/harness` | Todo | Policy/runtime tests |
| `src/main/java/com/enterprise/iqk/agent/workflow` | `apps/api/src/agent/workflow` | Todo | State transition tests |
| `src/main/java/com/enterprise/iqk/evaluation` | `apps/api/src/evaluation` | Todo | Scoring tests |

## First Milestone

1. Keep the Java version tagged as `java-baseline-2026-05-31`.
2. Build a TypeScript API skeleton that can run independently.
3. Port one endpoint family at a time, preserving route shape and response semantics.
