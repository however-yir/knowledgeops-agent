# KnowledgeOps Agent Python Parity Report

Python target: FastAPI enterprise service edition.

## Three Runtime Status

| Runtime | Status | Evidence |
|---|---|---|
| Java | Baseline | Spring Boot source and Maven/Baseline CI |
| TypeScript | Rewrite reference | TypeScript parity gates and contract cases |
| Python | Enterprise parity track | pytest, contract gate, e2e smoke, perf smoke, security gate, Docker build |

## Fixed API Surface

| Method | Path | Python status |
|---|---|---|
| POST | `/auth/token` | implemented |
| POST | `/auth/refresh` | implemented |
| POST | `/auth/api-keys` | implemented |
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
| GET | `/ai/sessions` | implemented |
| GET | `/ai/sessions/{sessionId}` | implemented |
| POST | `/ai/feedback` | implemented |
| GET | `/ai/evaluation/datasets` | implemented |
| POST | `/ai/evaluation/runs` | implemented |
| GET | `/audit/logs` | implemented |
| GET | `/cost/summary` | implemented |
| POST | `/cost/budget` | implemented |
| GET | `/ai/harness/actions` | implemented |

## Response Contract

- Success responses use `ok`, `msg`, `data`, `traceId`.
- Error responses use `ok=0`, `msg`, `code`, `traceId`.
- Chat data includes `answer`, `model`, `usage`, `traceId`.
- RAG data includes `answer`, `citations`, `evidence`, `retrievalStats`.
- Citation data includes `id`, `source`, `title`, `chunkId`, `snippet`.
- Agent trace includes `step`, `thoughtSummary`, `action`, `actionInput`, `observation`.

## Remaining Production Work

- Replace local simple queue/vector stores with managed Redis/pgvector in production configuration.
- Add live Java-vs-TS-vs-Python response diff once Python is deployed beside the other runtimes.
- Add provider-backed LLM integration after local contract gates stay stable.
