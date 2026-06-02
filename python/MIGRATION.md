# Python Migration Plan

Java remains the baseline while the Python implementation grows under `python/`.

| Existing area | Python target | Status | Verification |
|---|---|---|---|
| `src/main/java/com/enterprise/iqk/config` | `src/knowledgeops_py/config.py` | Started | `pytest` |
| `src/main/java/com/enterprise/iqk/controller` and `typescript/apps/api/src/*` controllers | FastAPI route modules | Started | health/auth/service smoke tests |
| `src/main/java/com/enterprise/iqk/security` and `typescript/apps/api/src/auth` | Python auth module | Started | demo API key exchange test |
| `src/main/java/com/enterprise/iqk/rag` and `typescript/apps/api/src/ai` | Python AI/RAG services | Not started | future contract diff |
| `src/main/resources/db/migration` and `typescript/prisma/schema.prisma` | SQLAlchemy or repository adapters | Not started | future persistence tests |
| `src/main/java/com/enterprise/iqk/ingestion` | Python ingestion workers | Not started | future queue/job tests |
| `src/main/java/com/enterprise/iqk/agent` | Python agent harness/workflow modules | Not started | future policy/runtime tests |
| `.github/workflows` | Python CI workflow | Not started | future GitHub Actions gate |

## Maturity Equivalence Gate

The Python rewrite is considered Java-maturity-equivalent only when these evidence gates pass together:

| Gate | Evidence |
|---|---|
| API contract | `knowledgeops-python-contract` validates the fixed FastAPI enterprise paths, OpenAPI schemas, response envelopes, SSE envelopes, Chat/RAG/Cost/Audit field contracts, and runtime flows. |
| security and tenant boundary | `knowledgeops-python-security-gate` verifies invalid API keys, JWT/refresh behavior, auth-required errors, tenant mismatch, and rate limiting defaults. |
| data persistence | Python currently uses a local parity store with Redis queue and simple-vector extension points; SQLAlchemy/MySQL and managed Redis/pgvector adapters must replace it before production cutover. |
| frontend cutover | Existing client calls must use the fixed Python enterprise paths and `ok/msg/data` response envelope. |
| observability and performance | Python CI runs health, metrics, e2e smoke, perf smoke, security defaults, parity report generation, Docker build, and local tests. |
| rollback | Java remains the schema-compatible fallback until Python has database-backed parity, shadow traffic evidence, and stable operational SLOs. |

## First Milestone

1. Keep Java and TypeScript unchanged.
2. Add a Python runtime that can run independently on port `3001`.
3. Port endpoint families in this order: health/auth, chat/RAG, ingestion/history, operations, harness/workflow/evaluation.
4. Extend contract cases only after each endpoint family has local tests.
5. Replace local parity storage with MySQL/Redis/RabbitMQ/LLM adapters only after contract gates are stable.

## Cutover Notes

The Python rewrite should remain branch-isolated until it can run side by side with Java and TypeScript. Rollback is simple while Python is read-compatible and writes only through mapped persistence adapters.
