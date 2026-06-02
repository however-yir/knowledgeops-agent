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

The current Python runtime is the FastAPI enterprise service track. It includes API Key auth, JWT/refresh token issue, RBAC dependencies, `X-Tenant-ID` context, rate limiting, Chat/SSE, ReAct trace, RAG upload/chat, ingestion jobs, simple-vector hybrid retrieval, citations/evidence/refusal, sessions, feedback, evaluation runs, cost governance, audit logs, health/metrics, OpenAPI contract validation, e2e/perf/security gates, Docker, and a Python parity report.

All JSON responses use:

```json
{ "ok": 1, "msg": "ok", "data": {}, "traceId": "trace_..." }
```

Error responses use:

```json
{ "ok": 0, "msg": "error message", "code": "ERROR_CODE", "traceId": "trace_..." }
```

The local demo API key defaults to:

```text
local-demo-api-key
```

## Migration Rule

Python modules are parity-ready only when their route contract, local behavior tests, persistence mapping, and cross-runtime contract checks match the Java baseline and the TypeScript rewrite evidence.
