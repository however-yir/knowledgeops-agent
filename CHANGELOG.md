# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

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

### Changed
- PDF ingestion switched from DB polling loop to queue-driven worker model.
- API key rotation now rotates by stable `keyName` (active key semantics) instead of generating ad-hoc names.
- Vector store backend defaults tuned toward pgvector production path.
- Project naming and runtime identifiers aligned to enterprise platform terminology (`knowledgeops-agent`).
- README and docs upgraded to enterprise deployment/architecture focused documentation set.
