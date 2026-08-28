# KnowledgeOps Agent Python Rewrite

This directory is the Python rewrite track for KnowledgeOps Agent.

The Java implementation remains the production baseline, and the TypeScript implementation remains the current parity rewrite. The Python version starts as an isolated FastAPI runtime so endpoint families can be ported and verified one by one without disturbing either existing implementation.

## Local Commands

```bash
cd python
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
pytest
alembic upgrade head
knowledgeops-python-api
knowledgeops-python-worker
knowledgeops-python-contract
knowledgeops-python-security-gate
knowledgeops-python-maturity
knowledgeops-python-e2e-smoke
knowledgeops-python-perf-smoke
knowledgeops-python-parity-report
uvicorn knowledgeops_py.app:create_app --factory --host 0.0.0.0 --port 3001
```

The initial Python API exposes Java/TypeScript-compatible smoke endpoints:

```text
GET  http://localhost:3001/actuator/health
GET  http://localhost:3001/actuator/prometheus
POST http://localhost:3001/auth/token
GET  http://localhost:3001/ai/service?prompt=hello
POST http://localhost:3001/ai/service
```

The Python runtime is a FastAPI enterprise service track. It includes administrator-scoped API Key lifecycle, standard JWT refresh rotation, OIDC + PKCE, trusted tenant context, rate limiting, Chat/SSE, RAG ingestion, sessions, evaluation, workflows, research, memory, graph, Harness confirmation tokens, Alembic persistence, API/Worker deployment commands and contract gates.

All JSON responses use:

```json
{ "ok": 1, "msg": "ok", "data": {}, "traceId": "trace_..." }
```

Error responses use:

```json
{ "ok": 0, "msg": "error message", "code": "ERROR_CODE", "traceId": "trace_..." }
```

The local demo API key is development-only and defaults to:

```text
local-demo-api-key
```

Read [MIGRATION.md](MIGRATION.md) for production prerequisites, baseline generation, shadow validation and rollback.

## Java Alignment (baseline `a373082`, 2026-08-28)

This Python track is aligned against the Java `main` tree at commit
`a373082` ("fix(security): derive rate-limit IP from X-Forwarded-For behind
proxies"). The pinned manifest (`parity/java-baseline-manifest.json`) and the
generated report (`reports/python-parity-report.md`) are the evidence of
record.

Security parity in this alignment:

- SSRF guard (`infrastructure/url_guard.py`) for outbound tool base URLs —
  SearXNG web search is validated at construction; the harness `mcp_call`
  action stays fail-closed (no MCP HTTP adapter ships in Python).
- Rate limiting keys anonymous traffic by the proxy-safe client IP
  (`X-Forwarded-For` rightmost non-private hop behind trusted proxies only),
  so the client-controlled tenant header can no longer steer buckets.
- The committed demo ADMIN key is never seeded in production, Alembic `0007`
  revokes already-seeded rows, and e2e credentials are env-configured.
- Trusted-workspace `ls`/`rg` arguments must resolve inside the workspace root.
- Tenant headers are only honoured when they echo the authenticated tenant;
  rejected contexts fall back to the fixed `public` tenant for limiting/audit.

Feature parity in this alignment:

- Configurable per-source hybrid retrieval weights (`APP_HYBRID_WEIGHTS`),
  with a SearXNG web-search backend (`APP_WEB_SEARCH_BACKEND=searxng`).
- Externalized RAG system prompts and `APP_RAG_ANSWER_TEMPERATURE` (default 0.2).
- Durable workflow steps persist input/output token usage; abandoned
  non-terminal tasks are failed on startup; checkpoints row-lock transitions.
- Ingestion claims are tenant-scoped and workers pass the owner explicitly.
- Memories expire (`expiresAt`) and never surface in list/recall/RAG context.
- The feedback dataset is appended on disk with a size cap and rotation
  (`APP_FEEDBACK_DATASET_MAX_BYTES`, default 50 MiB).

Intentional differences (documented in the parity manifest/report):

- The removed Java GET variants (`GET /ai/chat`, `GET /ai/service`,
  `GET /ai/pdf/chat`) are absent here as well; `POST /ai/service` returns the
  text/html customer-service surface.
- Java's `agent_session_state.lock_version` optimistic locking is replaced by
  pessimistic row locks (`SELECT ... FOR UPDATE`) with equivalent semantics.
- The in-process simple vector store keeps no snapshot file (the pgvector
  projection is the durable path).
