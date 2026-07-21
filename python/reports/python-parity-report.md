# KnowledgeOps Agent Python Parity Report

Python target: FastAPI enterprise service edition.

## Three Runtime Status

| Runtime | Status | Evidence |
|---|---|---|
| Java | Baseline | Spring Boot source and Maven/Baseline CI |
| TypeScript | Rewrite reference | TypeScript parity gates and contract cases |
| Python | Enterprise rewrite | unit/integration tests, contract gate, security gate, Alembic, SBOM and container CI |

## Fixed API Surface

| Method | Path | Python status |
|---|---|---|
| POST | `/auth/token` | implemented |
| POST | `/auth/refresh` | implemented |
| POST | `/auth/api-keys` | implemented |
| POST | `/auth/api-keys/rotate` | implemented |
| POST | `/auth/api-keys/revoke` | implemented |
| GET | `/auth/oidc/login` | implemented |
| GET | `/auth/oidc/callback` | implemented |
| POST | `/auth/oidc/exchange` | implemented |
| POST | `/auth/logout` | implemented |
| GET | `/actuator/health` | implemented |
| GET | `/health` | implemented |
| GET | `/actuator/prometheus` | implemented |
| GET | `/metrics` | implemented |
| POST | `/ai/chat` | implemented |
| POST | `/ai/chat/stream` | implemented |
| POST | `/ai/react/chat` | implemented |
| POST | `/ai/react/chat/stream` | implemented |
| POST | `/ai/pdf/upload/{chatId}` | implemented |
| POST | `/ingestion/upload/{chatId}` | implemented |
| GET | `/ingestion/jobs` | implemented |
| GET | `/ingestion/jobs/{jobId}` | implemented |
| POST | `/ai/pdf/chat` | implemented |
| GET | `/ai/pdf/chat` | implemented |
| GET | `/ai/pdf/file/{chatId}` | implemented |
| GET | `/ai/history/{kind}` | implemented |
| GET | `/ai/history/{kind}/{chatId}` | implemented |
| GET | `/ai/sessions` | implemented |
| GET | `/ai/sessions/{sessionId}` | implemented |
| POST | `/ai/feedback` | implemented |
| GET | `/ai/evaluation/datasets` | implemented |
| POST | `/ai/evaluation/runs` | implemented |
| GET | `/audit/logs` | implemented |
| GET | `/cost/summary` | implemented |
| POST | `/cost/budget` | implemented |
| GET | `/ai/harness/actions` | implemented |
| POST | `/ai/harness/actions/preview` | implemented |
| POST | `/ai/harness/actions/execute/{token}` | implemented |
| POST | `/ai/workflow/react/chat` | implemented |
| POST | `/ai/workflow/react/chat/stream` | implemented |
| GET | `/ai/workflow/tasks` | implemented |
| GET | `/ai/workflow/tasks/{taskId}` | implemented |
| GET | `/ai/research/tasks/{taskId}` | implemented |
| POST | `/ai/memory/items` | implemented |
| GET | `/ai/memory/items` | implemented |
| POST | `/ai/graph/entities` | implemented |
| GET | `/ai/graph/entities` | implemented |

## Response Contract

- Success responses use `ok`, `msg`, `data`, `traceId`.
- Error responses use `ok=0`, `msg`, `code`, `traceId`.
- Chat data includes `answer`, `model`, `usage`, `traceId`.
- RAG data includes `answer`, `citations`, `evidence`, `retrievalStats`.
- Citation data includes `id`, `source`, `title`, `chunkId`, `snippet`.
- Agent trace includes `step`, `thoughtSummary`, `action`, `actionInput`, `observation`.

## Deployment Evidence Required

- Real model, Redis, pgvector, RabbitMQ and OIDC settings are mandatory in production; CI uses deterministic local adapters.
- Run the Java/Python black-box runner against a deployed isolated stack before any routing change.
- Shadow evidence remains external: 10,000 requests or seven days, zero tenant isolation failures, and agreed error/latency limits.
