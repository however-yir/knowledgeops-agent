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

## First Milestone

1. Keep Java and TypeScript unchanged.
2. Add a Python runtime that can run independently on port `3001`.
3. Port endpoint families in this order: health/auth, chat/RAG, ingestion/history, operations, harness/workflow/evaluation.
4. Extend contract cases only after each endpoint family has local tests.

## Cutover Notes

The Python rewrite should remain branch-isolated until it can run side by side with Java and TypeScript. Rollback is simple while Python is read-compatible and writes only through mapped persistence adapters.
