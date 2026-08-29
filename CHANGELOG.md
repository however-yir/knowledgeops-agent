# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Python rewrite (parity with Java `a373082`, 2026-08-28)

- security: SSRF guard for outbound tool base URLs; rate-limit anonymous buckets keyed by the proxy-safe client IP; tenant headers are never trusted over the authenticated tenant; production no longer seeds the committed demo ADMIN key (Alembic 0007 revokes existing rows); workspace ls/rg arguments are confined to the workspace root; expired harness confirmation records are swept; pip-audit reports no known vulnerabilities.
- features: configurable per-source hybrid retrieval weights (APP_HYBRID_WEIGHTS) with a SearXNG web-search backend; externalized RAG system prompts with APP_RAG_ANSWER_TEMPERATURE; durable workflow steps persist token usage and abandoned tasks are recovered on startup; ingestion claims are tenant-scoped; memories expire out of list/recall/RAG context; the feedback dataset is capped and rotated on disk.
- removed: the Java-parity GET variants `GET /ai/chat`, `GET /ai/service` and `GET /ai/pdf/chat`; `POST /ai/service` is the text/html customer-service surface.
- alignment: baseline manifest re-pinned to `a1b1287` with 15 Java migrations and the parity report regenerated (61 fixed endpoints); the research `javaKnownDefect` marker is removed because the Java baseline now provisions conversationId, and the contract stack uses APP_BOOTSTRAP_API_KEY instead of the temporary java-seed service.

## [1.0.0] - 2026-04-28

### Added
- Redis Stream ingestion queue with DLQ, retry re-enqueue, and multi-worker concurrency.
- RabbitMQ ingestion queue backend with dedicated queue/DLX/DLQ declarations and concurrent listeners.
- pgvector formal migration and rollback script.
- API key lifecycle (issue/rotate/revoke/expiry) and JWT refresh token flow.
- Permission-granular security routing and audit log retention scheduler.
- RAG chunking, reranking, multi-document fusion, and answer citations.
- Observability stack templates (Prometheus, Loki, Tempo, Alertmanager, Promtail).
- OpenAPI integration, load testing scripts, large nightly evaluation pipeline.
- ReAct agent endpoints (`/ai/react/chat`, `/ai/react/chat/stream`) with trace payload and SSE events.
- Vue3 + TypeScript + Element Plus frontend console with Markdown rendering, dark mode, responsive layout, and ReAct trace view.
- Nginx reverse-proxy web service in Docker Compose for one-command full-stack startup.
- Development demo admin API key seed (`dev-admin-key-2026`) for local authentication walkthrough.
- Fast Maven test lane plus separate `integration-test` profile for container-backed smoke tests.
- Stream-based SHA-256 hashing utility and PDF safety scanner tests.
- Flyway migration `V9` for tenant isolation on `conversation` and `ingestion_job`.
- PostgreSQL pgvector tenant-aware metadata indexes (`tenant_id`, `tenant_id + chat_id`).

### Changed
- PDF ingestion switched from DB polling loop to queue-driven worker model.
- API key rotation now rotates by stable `keyName` (active key semantics) instead of generating ad-hoc names.
- Vector store backend defaults tuned toward pgvector production path.
- Project naming and runtime identifiers aligned to enterprise platform terminology (`knowledgeops-agent`).
- README and docs upgraded to enterprise deployment/architecture focused documentation set.
- Application security now defaults to enabled outside the development profile.
- Automatic ingestion idempotency keys now use file content hash instead of filename and size.
- PDF safety scanning now reads only the file header and validates PDF magic bytes before ingestion.
- Frontend production build now separates Vue, Element Plus, and Markdown/highlight dependencies into vendor chunks.
- Chat history, chat memory, ingestion job APIs, and PDF download/list operations are now tenant-scoped (`tenant_id`) to prevent cross-tenant data bleed.
- RAG retrieval filter is now tenant-aware (`tenant_id && chat_id`) and ingestion metadata includes `tenant_id`.
- ReAct stream endpoint now emits true model token streaming instead of synthetic answer chunk splitting.
- Cost budget update endpoint now falls back to request tenant header when `tenantId` is omitted in payload.
- Ingestion operational metrics now include tenant tags for submitted/finished/duration series.
