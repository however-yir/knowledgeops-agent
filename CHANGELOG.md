# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Fixed
- Workspace shell commands no longer leak the child `Process` when `waitFor` is interrupted: the process is now always destroyed in a `finally` block (PMD `CloseResource` also flagged this, which was failing the build).
- PMD `CloseResource` rule now recognizes `destroy()`/`destroyForcibly()` as closing a `Process`, so the `workspace_run_shell` action no longer trips the check.
- Streaming ReAct requests (`/ai/react/chat/stream`) now mark the workflow task `FAILED` when the stream errors, instead of leaving orphaned task records stuck in non-terminal states.
- Per-step `input_tokens` are now persisted by `AgentStepMapper.completeStep` instead of being silently dropped (column existed in the schema but was never written).
- `WorkspaceRuntimeTest.runsOnlyAllowedCommandFamilies` now asserts on the workspace directory name instead of the full absolute path, fixing a Windows/Git-Bash failure where `pwd` returns an MSYS-style path.
- `IngestionService.processQueuedJob` now requires the owning tenant to claim a job, closing a cross-tenant hijack path where any caller could pass another tenant's `jobId` to `POST /ingestion/jobs/process` and trigger the job. The new `processQueuedJob(jobId, tenantId, traceId)` overload also lets the Redis/RabbitMQ/db-polling workers pass the job's own tenant (their threads have no MDC). `IngestionJobMapper.claimForRun` SQL now filters on `tenant_id`.
- SQL `LIKE` keyword injection in graph and session search: `GraphService.searchEntities / searchFacts` and `AgentSessionService.list` now route the user-supplied keyword through a new `SqlLikeUtils.escapeForLike` so `%`, `_`, and `\` no longer widen the search. Without this, a search for `%` would match every row in the tenant's `kg_entity` / `kg_fact` / `agent_session_state` tables, turning any of those endpoints into a one-request DoS / data-exhaustion vector.
- Frontend reverse-tabnabbing hardening: `App.vue` `renderMarkdown` now (a) explicitly forbids `style`/`onload`/`onclick`/`onerror`/`onmouseover` attributes and `style`/`iframe`/`object`/`embed`/`form`/`input` tags, and (b) installs a module-level DOMPurify `afterSanitizeAttributes` hook that forces `rel="noopener noreferrer"` on every link with `target="_blank"`. This closes the reverse-tabnabbing vector that arises when prompt-injected LLM output is rendered with `v-html`.
- Web search backends no longer race on first-call lazy init: `BingSearchBackend` and `SearXNGBackend` now use a `volatile` field with double-checked locking so concurrent first-callers cannot end up with a half-configured `RestTemplate` (mismatched connect/read timeouts) or silently drop one of the two constructed instances. The two backends also share the Spring-managed `ObjectMapper` bean instead of constructing a new default `ObjectMapper` per backend instance, so the search JSON parsing uses the same configuration (including any registered modules) as the rest of the application.
- `ChatController.multiModalChat` no longer 500s on a multipart upload without an explicit `Content-Type` header: it now falls back to `application/octet-stream` instead of letting `Objects.requireNonNull(getContentType())` raise a NullPointerException, so the failure is a clean 4xx from the model layer rather than an unhandled NPE.

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
