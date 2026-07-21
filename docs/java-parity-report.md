# Java Parity Report

This report records the Java edition readiness against the shared
KnowledgeOps Agent parity target for Java, TypeScript, and Python.

## Scope

The Java edition is the feature baseline and production-oriented prototype. It keeps the
existing Spring Boot, Spring Security, Spring AI, MyBatis-Plus, Flyway,
Docker, and observability stack, while exposing compatibility endpoints and
tests for the shared three-language contract.

## Capability Matrix

| Capability | Java status | Evidence |
|---|---:|---|
| Auth and tenant isolation | Done | API key, JWT, refresh token, RBAC, identity-derived tenant context |
| Chat | Done | `/ai/chat` |
| SSE streaming | Done | `/ai/chat/stream`, `/ai/react/chat/stream` |
| ReAct Agent | Done | `/ai/react/chat`, trace payloads |
| RAG ingestion and Q&A | Done | `/ai/pdf/upload/{chatId}`, `/ingestion/upload/{chatId}`, `/ai/pdf/chat` |
| Hybrid retrieval | Done | vector, keyword, graph, web retrieval service |
| Citations and evidence | Done | `CitationItem`, `EvidenceItem`, RAG responses |
| Session history | Done | `/ai/sessions`, branch compare and merge |
| Feedback and evaluation | Done | `/ai/feedback`, `/ai/evaluation/datasets`, `/ai/evaluation/runs` |
| Cost governance | Done | `/cost/summary`, `/cost/budget` |
| Audit logs | Done | `/audit/logs`, audit filter |
| Rate limiting | Single instance | Bucket4j in-memory filter; shared Redis backend is not implemented |
| Health and metrics | Done | `/actuator/health`, `/actuator/prometheus` |
| Docker local deployment | Done | `Dockerfile`, `docker-compose.yml` |
| Helm deployment | Done | `helm/knowledgeops-agent` |
| API contract tests | Done | `JavaApiContractTest` |
| E2E smoke | Done | `scripts/e2e_chat_flow.py` |
| Performance smoke | Done | `performance/k6/chat_ingestion_load.js` |
| Security defaults check | Done | `AppStartupValidator`, `SecurityDefaultsTest` |
| README and operations docs | Done | README, operations docs, this report |

## Shared Endpoint Contract

The Java edition exposes the shared endpoint names expected by the three
language tracks:

- `POST /auth/token`
- `POST /auth/refresh`
- `POST /auth/api-keys`
- `GET /actuator/health`
- `GET /actuator/prometheus`
- `POST /ai/chat`
- `POST /ai/chat/stream`
- `POST /ai/react/chat`
- `POST /ai/react/chat/stream`
- `POST /ai/pdf/upload/{chatId}`
- `POST /ingestion/upload/{chatId}`
- `GET /ingestion/jobs`
- `GET /ingestion/jobs/{jobId}`
- `POST /ai/pdf/chat`
- `GET /ai/sessions`
- `GET /ai/sessions/{sessionId}`
- `POST /ai/feedback`
- `GET /ai/evaluation/datasets`
- `POST /ai/evaluation/runs`
- `GET /audit/logs`
- `GET /cost/summary`
- `POST /cost/budget`

## Compatibility Notes

- Existing Java endpoints remain available. New shared endpoints were added as
  aliases where needed instead of removing existing routes.
- JSON responses keep the current Java response shapes for frontend and smoke
  compatibility. Compatibility getters expose shared names such as
  `thoughtSummary`, `source`, `snippet`, `principal`, and `status`.
- Global response envelope migration to strict `ok/msg/data` for every endpoint
  is intentionally left as a future coordinated change because it would affect
  the current frontend and E2E smoke payload expectations.

## Local Java Gates

Run these before pushing Java main:

```bash
mvn -q test
mvn -q -DskipTests package
```

Optional deployment checks:

```bash
helm lint helm/knowledgeops-agent
docker compose config
```
