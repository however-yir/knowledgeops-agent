from __future__ import annotations

import hashlib
import io
import json
import math
import re
import secrets
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .api.canonical import (
    canonicalize_response,
    is_legacy_request,
    prepare_contract_path,
    react_response_payload,
    react_trace_payload,
)
from .application.harness import CanonicalHarnessApplicationService, harness_error
from .application.ingestion import IngestionApplicationService, normalize_idempotency_key
from .application.memory import MemoryApplicationService, memory_context
from .application.oidc import OidcFlowError
from .application.oidc import begin_oidc_login as begin_oidc_login_flow
from .application.oidc import complete_oidc_callback as complete_oidc_callback_flow
from .application.oidc import consume_oidc_exchange_code as consume_oidc_exchange_code_flow
from .application.research import DeepResearchApplicationService, ResearchNotResumable
from .application.security import (
    ROLE_PERMISSIONS,
    Identity,
    bearer_token,
    permissions_for_roles,
    sign_payload,
    verify_access_token,
)
from .application.sessions import (
    SessionBranchValidationError,
    compare_session_branches,
    java_session_payload,
    merge_session_branches,
)
from .application.workflow import ReactWorkflowApplicationService, WorkflowNotResumable
from .config import Settings, load_settings
from .domain.context import TenantContext
from .domain.ports import EmbeddingProvider, OidcStateStore, Reranker, VectorStore
from .dto import (
    AgentTraceDto,
    ApiKeyData,
    AuditLogDto,
    AuditLogsEnvelope,
    AuthTokenData,
    BudgetUpdateDto,
    ChatEnvelope,
    ChatRequestDto,
    ChatResponseDto,
    CitationDto,
    CostEnvelope,
    CostSummaryDto,
    EvaluationDatasetCreateDto,
    EvaluationRunRequestDto,
    FeedbackRequestDto,
    IngestionJobDto,
    RagEnvelope,
    RagResponseDto,
    RetrievalStatsDto,
    SessionDto,
    UsageDto,
)
from .infrastructure.database import create_engine, create_session_factory
from .infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from .infrastructure.file_store import LocalFileStore
from .infrastructure.graph_repository import SqlAlchemyGraphRepository
from .infrastructure.ingestion_repository import PersistedIngestionJob, SqlAlchemyIngestionRepository
from .infrastructure.memory_repository import SqlAlchemyMemoryRepository
from .infrastructure.oidc_state import RedisOidcStateStore
from .infrastructure.pgvector_store import PgVectorProjection, VectorStoreUnavailable
from .infrastructure.providers import (
    RerankerUnavailable,
    create_chat_provider,
    create_embedding_provider,
    create_reranker,
)
from .infrastructure.queue_factory import close_ingestion_queue, create_ingestion_queue
from .infrastructure.rate_limit import RateLimitUnavailable, RedisTokenBucket
from .infrastructure.security_repository import SecurityRepository, SqlAlchemySecurityRepository, StoredIdentity
from .infrastructure.session_repository import SqlAlchemySessionRepository
from .infrastructure.workflow_repository import SqlAlchemyWorkflowRepository
from .infrastructure.workspace_runtime import WorkspaceRuntime
from .observability.setup import configure_observability

TENANT_HEADER = "x-tenant-id"
API_KEY_HEADER = "x-api-key"
AUTH_HEADER = "authorization"

@dataclass
class RequestContext:
    trace_id: str
    tenant_id: str
    principal: str
    roles: list[str]
    permissions: list[str]
    auth_source: str


@dataclass
class PlatformStore:
    api_keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    refresh_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    rate_limits: dict[str, list[float]] = field(default_factory=dict)
    audit_logs: list[dict[str, Any]] = field(default_factory=list)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    queue: list[str] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    eval_datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    eval_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    budgets: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    action_schemas: list[dict[str, Any]] = field(default_factory=list)
    oidc_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    oidc_exchange_codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    revoked_refresh_tokens: set[str] = field(default_factory=set)
    workflow_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    research_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    memories: dict[str, dict[str, Any]] = field(default_factory=dict)
    graph_entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    graph_facts: list[dict[str, Any]] = field(default_factory=list)
    action_confirmations: dict[str, dict[str, Any]] = field(default_factory=dict)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    active_settings.validate_startup()
    store = PlatformStore()
    seed_store(store, active_settings)
    tracer = configure_observability(active_settings.app_name)
    engine = create_engine(active_settings.database_url) if active_settings.database_url else None
    session_factory = create_session_factory(engine) if engine is not None else None
    security_repository: SecurityRepository | None = (
        SqlAlchemySecurityRepository(session_factory) if session_factory is not None else None
    )
    session_repository = SqlAlchemySessionRepository(session_factory) if session_factory is not None else None
    workflow_repository = SqlAlchemyWorkflowRepository(session_factory) if session_factory is not None else None
    workflow_service = ReactWorkflowApplicationService(workflow_repository) if workflow_repository is not None else None
    research_service = DeepResearchApplicationService(workflow_repository) if workflow_repository is not None else None
    memory_repository = SqlAlchemyMemoryRepository(session_factory) if session_factory is not None else None
    memory_service = MemoryApplicationService(memory_repository) if memory_repository is not None else None
    evaluation_repository = SqlAlchemyEvaluationRepository(session_factory) if session_factory is not None else None
    graph_repository = SqlAlchemyGraphRepository(session_factory) if session_factory is not None else None
    workspace_runtime = WorkspaceRuntime(
        root=Path(active_settings.workspace_root),
        write_enabled=active_settings.allow_workspace_write,
        shell_enabled=active_settings.allow_workspace_shell,
        command_timeout_seconds=active_settings.workspace_command_timeout_seconds,
        max_command_output_bytes=active_settings.workspace_max_command_output_bytes,
        max_file_bytes=active_settings.workspace_max_file_bytes,
        max_search_files=active_settings.workspace_max_search_files,
        allowed_commands=active_settings.workspace_allowed_commands,
        allowed_git_subcommands=active_settings.workspace_allowed_git_subcommands,
    )
    harness_service = CanonicalHarnessApplicationService(workspace_runtime, active_settings)
    ingestion_queue = create_ingestion_queue(active_settings, "api") if session_factory is not None else None
    embedding_provider = create_embedding_provider(active_settings)
    vector_store = (
        PgVectorProjection(active_settings.pgvector_url, active_settings.pgvector_dimensions)
        if active_settings.vector_backend == "pgvector" and active_settings.pgvector_url
        else None
    )
    ingestion_service = (
        IngestionApplicationService(
            SqlAlchemyIngestionRepository(session_factory),
            LocalFileStore(Path(active_settings.storage_path)),
            active_settings.ingestion_queue_backend,
            ingestion_queue,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
        if session_factory is not None
        else None
    )
    oidc_state_store: OidcStateStore | None = RedisOidcStateStore(active_settings.redis_url) if active_settings.is_production else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if isinstance(security_repository, SqlAlchemySecurityRepository):
            await security_repository.bootstrap_api_key(
                active_settings.demo_api_key,
                "local-demo",
                active_settings.demo_tenant_id,
                "ADMIN",
            )
        if evaluation_repository is not None:
            default_dataset = store.eval_datasets["default"]
            await evaluation_repository.ensure_default_dataset(
                active_settings.demo_tenant_id,
                default_dataset["name"],
                default_dataset["cases"],
            )
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()
            await close_ingestion_queue(ingestion_queue)

    app = FastAPI(
        title="KnowledgeOps Agent Python Enterprise API",
        version="0.2.0",
        docs_url="/swagger-ui/index.html",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.store = store
    app.state.security_repository = security_repository
    app.state.session_repository = session_repository
    app.state.workflow_repository = workflow_repository
    app.state.workflow_service = workflow_service
    app.state.research_service = research_service
    app.state.memory_repository = memory_repository
    app.state.memory_service = memory_service
    app.state.evaluation_repository = evaluation_repository
    app.state.graph_repository = graph_repository
    app.state.oidc_state_store = oidc_state_store
    app.state.ingestion_service = ingestion_service
    app.state.vector_store = vector_store
    app.state.embedding_provider = embedding_provider
    app.state.tracer = tracer

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "X-API-Key", "X-Tenant-ID", "Content-Type", "X-Request-ID"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        trace_id = ensure_trace_id(request)
        code = str(exc.detail if isinstance(exc.detail, str) else "http_error").upper().replace(" ", "_")
        return JSONResponse(status_code=exc.status_code, content=error_payload(str(exc.detail), code, trace_id))

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = ensure_trace_id(request)
        message = "internal server error" if active_settings.is_production else str(exc)
        return JSONResponse(status_code=500, content=error_payload(message, "INTERNAL_ERROR", trace_id))

    @app.middleware("http")
    async def context_audit_rate_limit(request: Request, call_next):
        prepare_contract_path(request)
        trace_id = request.headers.get("x-request-id") or new_id("trace")
        request.state.trace_id = trace_id
        try:
            ctx = await resolve_context(request, store, active_settings, security_repository, allow_anonymous=True)
        except HTTPException:
            ctx = RequestContext(trace_id, normalize_tenant(request.headers.get(TENANT_HEADER)), "anonymous", ["ANONYMOUS"], [], "anonymous")
        request.state.context = ctx
        if should_rate_limit(request.url.path):
            try:
                await enforce_rate_limit(store, active_settings, ctx)
            except HTTPException as exc:
                code = "RATE_LIMIT_UNAVAILABLE" if exc.status_code == 503 else "RATE_LIMIT_EXCEEDED"
                return await canonicalize_response(
                    request,
                    JSONResponse(status_code=exc.status_code, content=error_payload(str(exc.detail), code, trace_id)),
                )
        started = time.perf_counter()
        with tracer.start_as_current_span("http.request") as span:
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("url.path", request.url.path)
            span.set_attribute("knowledgeops.trace_id", trace_id)
            span.set_attribute("knowledgeops.tenant_id", ctx.tenant_id)
            response = await call_next(request)
            span.set_attribute("http.response.status_code", response.status_code)
        response.headers["X-Trace-ID"] = trace_id
        if not request.url.path.startswith(("/actuator", "/health", "/metrics")):
            store.audit_logs.append(
                AuditLogDto(
                    tenantId=ctx.tenant_id,
                    principal=ctx.principal,
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    createdAt=now_iso(),
                ).model_dump()
                | {"latencyMs": round((time.perf_counter() - started) * 1000, 2)}
            )
        metric_inc(store, "http_requests_total")
        return await canonicalize_response(request, response)

    async def optional_ctx(request: Request) -> RequestContext:
        return await resolve_context(request, store, active_settings, security_repository, allow_anonymous=True)

    def require_permissions(*required: str) -> Callable[[Request], RequestContext]:
        async def dependency(request: Request) -> RequestContext:
            ctx = await resolve_context(request, store, active_settings, security_repository, allow_anonymous=False)
            missing = [permission for permission in required if permission not in ctx.permissions]
            if missing:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
            request.state.context = ctx
            return ctx

        return dependency

    @app.get("/actuator/health")
    @app.get("/health")
    def health(request: Request):
        return ok({"status": "UP", "service": "knowledgeops-agent-python"}, trace_id=ensure_trace_id(request))

    @app.get("/metrics")
    def metrics(request: Request, _ctx: RequestContext = Depends(require_permissions("PERM_METRICS_READ"))):
        text = prometheus_text(store)
        return ok({"prometheus": text, "counters": store.metrics}, trace_id=ensure_trace_id(request))

    @app.get("/actuator/prometheus")
    def prometheus(_ctx: RequestContext = Depends(require_permissions("PERM_METRICS_READ"))):
        return PlainTextResponse(prometheus_text(store), media_type="text/plain; version=0.0.4")

    @app.get("/v3/api-docs")
    def openapi_docs(request: Request):
        return ok(app.openapi(), trace_id=ensure_trace_id(request))

    @app.post("/auth/token")
    async def auth_token(request: Request, x_api_key: str | None = Header(default=None), x_tenant_id: str | None = Header(default=None)):
        identity = await resolve_api_key_identity(store, security_repository, x_api_key)
        if not identity:
            return fail("invalid api key", "AUTH_INVALID_API_KEY", ensure_trace_id(request))
        if x_tenant_id and normalize_tenant(x_tenant_id) != identity.tenant_id:
            return fail("tenant mismatch for api key", "AUTH_TENANT_MISMATCH", ensure_trace_id(request))
        data = await issue_tokens(store, active_settings, identity, security_repository)
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/refresh")
    async def auth_refresh(request: Request, x_refresh_token: str | None = Header(default=None)):
        if not x_refresh_token:
            return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
        if security_repository is not None:
            stored = await security_repository.consume_refresh_token(x_refresh_token)
            if stored is None:
                return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
            identity = identity_from_stored(stored)
        else:
            token_hash = sha256_hex(x_refresh_token)
            if token_hash in store.revoked_refresh_tokens:
                return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
            record = store.refresh_tokens.pop(token_hash, None)
            if not record or record["expiresAt"] <= epoch_seconds():
                return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
            store.revoked_refresh_tokens.add(token_hash)
            identity = Identity(record["principal"], record["tenantId"], record["roles"], permissions_for_roles(record["roles"]), "refresh")
        return ok(await issue_tokens(store, active_settings, identity, security_repository), trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys")
    async def auth_api_keys(request: Request, keyName: str = Query(..., min_length=1, max_length=120), role: str = Query(default="USER"), ctx: RequestContext = Depends(require_permissions("PERM_AUTH_KEY_MANAGE"))):
        data = await issue_api_key(store, security_repository, keyName, role, ctx.tenant_id)
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys/rotate")
    async def auth_api_key_rotate(request: Request, keyName: str = Query(..., min_length=1, max_length=120), reason: str = Query(default="rotation", max_length=240), ctx: RequestContext = Depends(require_permissions("PERM_AUTH_KEY_MANAGE"))):
        data = await rotate_persistent_api_key(store, security_repository, keyName, reason, ctx.tenant_id)
        return ok(data, msg="rotated", trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys/revoke")
    async def auth_api_key_revoke(request: Request, keyName: str = Query(..., min_length=1, max_length=120), reason: str = Query(default="manual revoke", max_length=240), ctx: RequestContext = Depends(require_permissions("PERM_AUTH_KEY_MANAGE"))):
        await revoke_persistent_api_key(store, security_repository, keyName, reason, ctx.tenant_id)
        return ok({"keyName": keyName, "tenantId": ctx.tenant_id}, msg="revoked", trace_id=ensure_trace_id(request))

    @app.get("/auth/oidc/login")
    async def oidc_login(request: Request, returnTo: str | None = Query(default=None, max_length=2048)):
        return ok(await begin_oidc_login(store, active_settings, oidc_state_store, returnTo), trace_id=ensure_trace_id(request))

    @app.get("/auth/oidc/callback")
    async def oidc_callback(request: Request, code: str = Query(..., min_length=1), state: str = Query(..., min_length=1)):
        return ok(await complete_oidc_callback(store, active_settings, oidc_state_store, code, state), trace_id=ensure_trace_id(request))

    @app.post("/auth/oidc/exchange")
    async def oidc_exchange(request: Request):
        payload = await request.json()
        exchange_code = str(payload.get("exchangeCode", ""))
        identity = await consume_oidc_exchange_code(store, oidc_state_store, exchange_code)
        if not identity:
            return fail("invalid or expired OIDC exchange code", "OIDC_INVALID_EXCHANGE_CODE", ensure_trace_id(request))
        return ok(await issue_tokens(store, active_settings, identity, security_repository), trace_id=ensure_trace_id(request))

    @app.post("/auth/logout")
    async def logout(request: Request, x_refresh_token: str | None = Header(default=None)):
        if x_refresh_token:
            if security_repository is not None:
                await security_repository.revoke_refresh_token(x_refresh_token)
            else:
                token_hash = sha256_hex(x_refresh_token)
                store.refresh_tokens.pop(token_hash, None)
                store.revoked_refresh_tokens.add(token_hash)
        return ok({"loggedOut": True}, trace_id=ensure_trace_id(request))

    @app.post("/ai/chat", response_model=ChatEnvelope)
    async def ai_chat(
        request: Request,
        payload: ChatRequestDto | None = None,
        prompt: str | None = Query(default=None),
        chatId: str | None = Query(default=None),
        modelProfile: str | None = Query(default=None),
        ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE")),
    ):
        payload = chat_request_payload(payload, prompt, chatId, modelProfile)
        data = await chat_response_with_provider(
            store, ctx, payload, mode="chat", require_evidence=False, settings=active_settings,
            session_repository=session_repository, memory_service=memory_service
        )
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/chat/stream")
    async def ai_chat_stream(
        request: Request,
        payload: ChatRequestDto | None = None,
        prompt: str | None = Query(default=None),
        chatId: str | None = Query(default=None),
        modelProfile: str | None = Query(default=None),
        ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE")),
    ):
        payload = chat_request_payload(payload, prompt, chatId, modelProfile)
        data = await chat_response_with_provider(
            store, ctx, payload, mode="chat", require_evidence=False, settings=active_settings,
            session_repository=session_repository, memory_service=memory_service
        )
        if not is_legacy_request(request):
            return PlainTextResponse(f"data: {data.answer}\n\n", media_type="text/event-stream")
        return PlainTextResponse(to_sse(data, ctx.trace_id, legacy=True), media_type="text/event-stream")

    @app.post("/ai/react/chat", response_model=ChatEnvelope)
    async def react_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = await chat_response_with_provider(
            store, ctx, payload, mode="react", require_evidence=False, settings=active_settings,
            session_repository=session_repository, memory_service=memory_service
        )
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/react/chat/stream")
    async def react_chat_stream(request: Request, payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        legacy = is_legacy_request(request)
        try:
            data = await chat_response_with_provider(
                store, ctx, payload, mode="react", require_evidence=False, settings=active_settings,
                session_repository=session_repository, memory_service=memory_service
            )
        except Exception as exc:
            return PlainTextResponse(to_sse_error(exc, ctx.trace_id, legacy), media_type="text/event-stream")
        return PlainTextResponse(
            to_sse(data, ctx.trace_id, legacy=legacy, react=True), media_type="text/event-stream"
        )

    @app.post("/ai/pdf/chat", response_model=RagEnvelope)
    async def pdf_chat(
        payload: ChatRequestDto | None = None,
        prompt: str | None = Query(default=None),
        chatId: str | None = Query(default=None),
        modelProfile: str | None = Query(default=None),
        ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE")),
    ):
        payload = chat_request_payload(payload, prompt, chatId, modelProfile)
        data = await rag_response_with_provider(
            store,
            ctx,
            payload,
            require_evidence=True,
            settings=active_settings,
            ingestion_repository=ingestion_service.repository if ingestion_service is not None else None,
            graph_repository=graph_repository,
            session_repository=session_repository,
            vector_store=vector_store,
            memory_service=memory_service,
        )
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/pdf/upload/{chatId}")
    @app.post("/ingestion/upload/{chatId}")
    async def upload(chatId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_WRITE"))):
        legacy = is_legacy_request(request)
        if not legacy and not chatId.strip():
            raise HTTPException(status_code=400, detail="chatId is required")
        source_name, content = await request_file(request, active_settings, require_file=not legacy)
        idempotency_key = request.headers.get("x-idempotency-key")
        if ingestion_service is not None:
            job = await ingestion_service.submit(tenant_context(ctx), chatId, source_name, content, idempotency_key)
            return ok(IngestionJobDto(**persisted_public_job(job)), msg="accepted", trace_id=ctx.trace_id)
        job = create_ingestion_job(store, active_settings, ctx, chatId, source_name, content, idempotency_key)
        enqueue_and_process(store, active_settings, job["jobId"])
        return ok(IngestionJobDto(**public_job(store.jobs[job["jobId"]])), msg="accepted", trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs")
    async def ingestion_jobs(
        request: Request,
        ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_READ")),
        chatId: str | None = Query(default=None),
        limit: int | None = Query(default=None),
    ):
        legacy = is_legacy_request(request)
        if not legacy and chatId is None:
            raise HTTPException(status_code=400, detail="chatId is required")
        selected_limit = 50 if legacy else 20
        if limit is not None:
            selected_limit = limit
        selected_limit = bounded(selected_limit, 1, 200 if legacy else 100)
        if ingestion_service is not None:
            jobs = await ingestion_service.repository.list_jobs(ctx.tenant_id, chatId, selected_limit)
            return ok([IngestionJobDto(**persisted_public_job(job)).model_dump() for job in jobs], trace_id=ctx.trace_id)
        jobs = [
            IngestionJobDto(**job).model_dump()
            for job in store.jobs.values()
            if job["tenantId"] == ctx.tenant_id and (not chatId or job["chatId"] == chatId)
        ]
        return ok(jobs[:selected_limit], trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs/{jobId}")
    async def ingestion_job(jobId: str, ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_READ"))):
        if ingestion_service is not None:
            job = await ingestion_service.repository.get(ctx.tenant_id, jobId)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            return ok(IngestionJobDto(**persisted_public_job(job)), trace_id=ctx.trace_id)
        job = store.jobs.get(jobId)
        if not job or job["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="job not found")
        return ok(IngestionJobDto(**job), trace_id=ctx.trace_id)

    @app.get("/ai/sessions")
    async def sessions(ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        if session_repository is not None:
            return ok(await session_repository.list(ctx.tenant_id), trace_id=ctx.trace_id)
        data = [SessionDto(**session).model_dump() for session in store.sessions.values() if session["tenantId"] == ctx.tenant_id]
        return ok(data, trace_id=ctx.trace_id)

    @app.get("/ai/sessions/{sessionId}")
    async def session(
        sessionId: str,
        request: Request,
        ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ")),
    ):
        if session_repository is not None:
            data = await session_repository.get(ctx.tenant_id, sessionId)
            if data is None:
                raise session_not_found(request)
            return ok(data, trace_id=ctx.trace_id)
        data = (
            get_or_create_session(store, ctx, sessionId, chat_id=sessionId)
            if is_legacy_request(request)
            else require_session(store, ctx, sessionId, session_not_found_status(request))
        )
        return ok(SessionDto(**data), trace_id=ctx.trace_id)

    @app.post("/ai/feedback")
    def feedback(payload: FeedbackRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_FEEDBACK_WRITE"))):
        record = payload.model_dump() | {"tenantId": ctx.tenant_id, "principal": ctx.principal, "createdAt": now_iso()}
        store.feedback.append(record)
        return ok(record, msg="saved", trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/datasets")
    async def evaluation_datasets(ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        if evaluation_repository is not None:
            return ok(await evaluation_repository.list_datasets(ctx.tenant_id), trace_id=ctx.trace_id)
        data = [dataset for dataset in store.eval_datasets.values() if dataset["tenantId"] == ctx.tenant_id]
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/datasets")
    async def evaluation_dataset_create(
        payload: EvaluationDatasetCreateDto, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_WRITE"))
    ):
        if evaluation_repository is not None:
            dataset = await evaluation_repository.create_dataset(
                ctx.tenant_id,
                new_id("ds"),
                payload.name,
                payload.description,
                payload.cases,
            )
            return ok(dataset, trace_id=ctx.trace_id)
        dataset = {
            "datasetId": new_id("ds"),
            "tenantId": ctx.tenant_id,
            "name": payload.name,
            "description": payload.description,
            "cases": payload.cases,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
        store.eval_datasets[dataset["datasetId"]] = dataset
        return ok(dataset, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/runs")
    async def evaluation_run(payload: EvaluationRunRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        if evaluation_repository is not None:
            return ok(
                await create_persisted_eval_run(
                    evaluation_repository,
                    store,
                    ctx,
                    payload,
                    active_settings,
                    ingestion_service.repository if ingestion_service is not None else None,
                    graph_repository,
                    vector_store,
                ),
                trace_id=ctx.trace_id,
            )
        run = create_eval_run(store, ctx, payload)
        return ok(run, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/datasets/{datasetId}/runs")
    async def evaluation_dataset_run(
        datasetId: str, payload: EvaluationRunRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))
    ):
        if evaluation_repository is not None:
            return ok(
                await create_persisted_eval_run(
                    evaluation_repository,
                    store,
                    ctx,
                    EvaluationRunRequestDto(datasetId=datasetId, modelProfile=payload.modelProfile),
                    active_settings,
                    ingestion_service.repository if ingestion_service is not None else None,
                    graph_repository,
                    vector_store,
                ),
                trace_id=ctx.trace_id,
            )
        dataset = store.eval_datasets.get(datasetId)
        if not dataset or dataset["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        run = create_eval_run(store, ctx, EvaluationRunRequestDto(datasetId=datasetId, modelProfile=payload.modelProfile))
        return ok(run, trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/runs/{runId}")
    async def evaluation_run_get(runId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        if evaluation_repository is not None:
            run = await evaluation_repository.get_run(ctx.tenant_id, runId)
            if run is None:
                raise HTTPException(status_code=404, detail="evaluation run not found")
            return ok(run, trace_id=ctx.trace_id)
        run = require_eval_run(store, ctx, runId)
        return ok(run, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/runs/{runId}/baseline")
    async def evaluation_run_baseline(runId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_WRITE"))):
        if evaluation_repository is not None:
            run = await evaluation_repository.mark_baseline(ctx.tenant_id, runId)
            if run is None:
                raise HTTPException(status_code=404, detail="evaluation run not found")
            return ok(run, trace_id=ctx.trace_id)
        run = require_eval_run(store, ctx, runId)
        run["isBaseline"] = True
        dataset = store.eval_datasets.get(run["datasetId"])
        if dataset is not None:
            dataset["baselineRunId"] = runId
            dataset["updatedAt"] = now_iso()
        return ok(run, trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/datasets/{datasetId}/comparison")
    async def evaluation_comparison(
        datasetId: str,
        request: Request,
        ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ")),
    ):
        if evaluation_repository is not None:
            dataset = await evaluation_repository.get_dataset(ctx.tenant_id, datasetId)
            if dataset is None:
                raise HTTPException(status_code=404, detail="dataset not found")
            runs = await evaluation_repository.list_runs(ctx.tenant_id, datasetId)
            data = {"datasetId": datasetId, "runs": runs} if is_legacy_request(request) else evaluation_comparison_data(dataset, runs)
            return ok(data, trace_id=ctx.trace_id)
        dataset = store.eval_datasets.get(datasetId)
        if not dataset or dataset["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        runs = [run for run in store.eval_runs.values() if run["tenantId"] == ctx.tenant_id and run["datasetId"] == datasetId]
        data = {"datasetId": datasetId, "runs": runs} if is_legacy_request(request) else evaluation_comparison_data(dataset, runs)
        return ok(data, trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/runs/{runId}/report")
    async def evaluation_report(runId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        if evaluation_repository is not None:
            run = await evaluation_repository.get_run(ctx.tenant_id, runId)
            if run is None:
                raise HTTPException(status_code=404, detail="evaluation run not found")
            return evaluation_report_response(run)
        run = require_eval_run(store, ctx, runId)
        return evaluation_report_response(run)

    @app.get("/audit/logs", response_model=AuditLogsEnvelope)
    def audit_logs(ctx: RequestContext = Depends(require_permissions("PERM_AUDIT_READ")), limit: int = Query(default=50)):
        logs = [AuditLogDto(**select_audit_fields(log)).model_dump() for log in store.audit_logs if log["tenantId"] == ctx.tenant_id]
        return ok(list(reversed(logs[-bounded(limit, 1, 200) :])), trace_id=ctx.trace_id)

    @app.get("/cost/summary", response_model=CostEnvelope)
    def cost_summary(ctx: RequestContext = Depends(require_permissions("PERM_COST_READ"))):
        return ok(cost_summary_data(store, ctx.tenant_id), trace_id=ctx.trace_id)

    @app.post("/cost/budget", response_model=CostEnvelope)
    def cost_budget(payload: BudgetUpdateDto, ctx: RequestContext = Depends(require_permissions("PERM_COST_WRITE"))):
        previous = store.budgets.get(ctx.tenant_id, {})
        store.budgets[ctx.tenant_id] = {
            "tenantId": ctx.tenant_id,
            "monthlyBudgetUsd": payload.monthlyBudgetUsd,
            "hardLimitEnabled": payload.hardLimitEnabled if payload.hardLimitEnabled is not None else bool(previous.get("hardLimitEnabled", False)),
            "updatedAt": now_iso(),
        }
        return ok(cost_summary_data(store, ctx.tenant_id), msg="updated", trace_id=ctx.trace_id)

    @app.get("/ai/harness/actions")
    def action_schema(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_AGENT_TRUSTED"))):
        schemas = [
            schema
            for schema in store.action_schemas
            if schema.get("contract") == ("legacy" if is_legacy_request(request) else "canonical")
        ]
        if is_legacy_request(request):
            schemas = [{key: value for key, value in schema.items() if key != "contract"} for schema in schemas]
        return ok(schemas, trace_id=ctx.trace_id)

    @app.post("/ai/harness/actions/preview")
    async def action_preview(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_AGENT_TRUSTED"))):
        payload = await request.json()
        action = str(payload.get("action", ""))
        legacy = is_legacy_request(request)
        if not legacy and not action.strip():
            raise HTTPException(status_code=400, detail="action is required")
        schema = next(
            (
                item
                for item in store.action_schemas
                if item["action"] == action and item.get("contract") == ("legacy" if legacy else "canonical")
            ),
            None,
        )
        if not schema:
            if legacy:
                raise HTTPException(status_code=404, detail="action not found")
            raise HTTPException(status_code=400, detail=f"unsupported action: {action}")
        action_input = payload.get("actionInput") or {}
        if not isinstance(action_input, dict):
            raise HTTPException(status_code=400, detail="actionInput must be an object")
        if legacy:
            missing = [key for key in schema["requiredKeys"] if key not in action_input]
            if missing:
                raise HTTPException(status_code=422, detail=f"missing action input: {', '.join(missing)}")
            token = secrets.token_urlsafe(32)
            expires_at = epoch_seconds() + 300
        else:
            if not schema["trustedOnly"]:
                raise HTTPException(status_code=400, detail=f"action does not require trusted runtime: {action}")
            token = f"ta-{secrets.token_hex(16)}"
            expires_at = epoch_seconds() + 600
        store.action_confirmations[sha256_hex(token)] = {
            "tenantId": ctx.tenant_id,
            "principal": ctx.principal,
            "action": action,
            "actionInput": action_input,
            "expiresAt": expires_at,
            "used": False,
            "legacy": legacy,
            "schema": schema,
        }
        if legacy:
            return ok(
                {"confirmationToken": token, "action": action, "riskLevel": schema["riskLevel"], "expiresInSeconds": 300},
                trace_id=ctx.trace_id,
            )
        preview = harness_service.preview(ctx.tenant_id, action, action_input, schema)
        return ok(
            {"token": token, "action": action, "expiresAt": iso_at_epoch(expires_at), "preview": preview},
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/harness/actions/execute/{token}")
    async def action_execute(token: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_AGENT_TRUSTED"))):
        legacy = is_legacy_request(request)
        confirmation = store.action_confirmations.get(sha256_hex(token))
        if not confirmation or confirmation["tenantId"] != ctx.tenant_id or confirmation["used"] or confirmation.get("legacy") != legacy:
            if legacy:
                raise HTTPException(status_code=404, detail="confirmation token not found")
            return ok(harness_error("trusted-action", "trusted action token not found"), trace_id=ctx.trace_id)
        if confirmation["expiresAt"] <= epoch_seconds():
            confirmation["used"] = True
            if legacy:
                raise HTTPException(status_code=404, detail="confirmation token not found")
            return ok(harness_error("trusted-action", "trusted action token expired"), trace_id=ctx.trace_id)
        confirmation["used"] = True
        if not legacy:
            return ok(
                harness_service.execute(
                    ctx.tenant_id,
                    confirmation["action"],
                    confirmation["actionInput"],
                    confirmation["schema"],
                ),
                trace_id=ctx.trace_id,
            )
        if memory_repository is not None and confirmation["action"] == "memory_save":
            action_input = confirmation["actionInput"]
            item = await memory_repository.create(
                ctx.tenant_id,
                ctx.principal,
                str(action_input["content"]),
                str(action_input.get("type") or "fact"),
                action_input.get("sessionId"),
            )
            observation = {"action": "memory_save", "status": "COMPLETED", "result": item}
        elif graph_repository is not None and confirmation["action"] == "graph_search":
            action_input = confirmation["actionInput"]
            observation = {
                "action": "graph_search",
                "status": "COMPLETED",
                "result": await graph_repository.list_entities(
                    ctx.tenant_id,
                    str(action_input["query"]),
                    limit=bounded(int(action_input.get("limit", 20)), 1, 100),
                ),
            }
        else:
            observation = execute_trusted_action(store, ctx, confirmation["action"], confirmation["actionInput"])
        return ok(observation, trace_id=ctx.trace_id)

    @app.get("/ai/chat")
    @app.get("/ai/service")
    async def html_chat(prompt: str = Query(..., min_length=1), chatId: str = Query(default="default"), ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        response = await chat_response_with_provider(
            store,
            ctx,
            ChatRequestDto(chatId=chatId, prompt=prompt),
            mode="chat",
            require_evidence=False,
            settings=active_settings,
            session_repository=session_repository,
            memory_service=memory_service,
        )
        return PlainTextResponse(response.answer, media_type="text/html; charset=utf-8")

    @app.get("/ai/pdf/chat")
    async def pdf_chat_get(prompt: str = Query(..., min_length=1), chatId: str = Query(..., min_length=1), ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        data = await rag_response_with_provider(
            store,
            ctx,
            ChatRequestDto(chatId=chatId, prompt=prompt),
            require_evidence=True,
            settings=active_settings,
            ingestion_repository=ingestion_service.repository if ingestion_service is not None else None,
            graph_repository=graph_repository,
            session_repository=session_repository,
            vector_store=vector_store,
            memory_service=memory_service,
        )
        return ok(data, trace_id=ctx.trace_id)

    @app.get("/ai/pdf/file/{chatId}")
    async def pdf_file(chatId: str, ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        chunks = (
            await ingestion_service.repository.chunks(ctx.tenant_id, chatId)
            if ingestion_service is not None
            else [chunk for chunk in store.chunks if chunk["tenantId"] == ctx.tenant_id and chunk["chatId"] == chatId]
        )
        if not chunks:
            raise HTTPException(status_code=404, detail="file not found")
        return PlainTextResponse("\n".join(chunk["content"] for chunk in chunks), media_type="text/plain; charset=utf-8")

    @app.post("/ingestion/jobs/process")
    async def ingestion_process(
        request: Request,
        jobId: str | None = Query(default=None),
        ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_WRITE")),
    ):
        if is_legacy_request(request):
            if ingestion_service is not None:
                processed = await ingestion_service.process_ready(ctx.tenant_id)
                return ok({"processed": processed}, trace_id=ctx.trace_id)
            processed = process_pending_jobs(store, active_settings, ctx.tenant_id)
            return ok({"processed": processed}, trace_id=ctx.trace_id)
        if "ROLE_ADMIN" not in ctx.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        if jobId is None or not jobId.strip():
            requeued = await ingestion_service.publish_ready(limit=20) if ingestion_service is not None else 0
            return ok(None, msg=f"requeue={requeued}", trace_id=ctx.trace_id)
        if ingestion_service is not None:
            job = await ingestion_service.repository.get(ctx.tenant_id, jobId)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            processed = await ingestion_service.process(job.job_id)
            return ok(None, msg="processed" if processed is not None else "empty", trace_id=ctx.trace_id)
        job = store.jobs.get(jobId)
        if not job or job["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="job not found")
        picked = job["status"] in {"QUEUED", "RETRY"}
        if picked:
            process_ingestion_job(store, jobId)
        return ok(None, msg="processed" if picked else "empty", trace_id=ctx.trace_id)

    @app.get("/ai/history/{kind}")
    async def history_list(kind: str, page: int = Query(default=1, ge=1), pageSize: int = Query(default=20, ge=1, le=200), ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        if session_repository is not None:
            return ok(page_data(await session_repository.list(ctx.tenant_id), page, pageSize), trace_id=ctx.trace_id)
        sessions_for_tenant = [item for item in store.sessions.values() if item["tenantId"] == ctx.tenant_id]
        return ok(page_data(sessions_for_tenant, page, pageSize), trace_id=ctx.trace_id)

    @app.get("/ai/history/{kind}/{chatId}")
    async def history_messages(kind: str, chatId: str, page: int = Query(default=1, ge=1), pageSize: int = Query(default=50, ge=1, le=200), ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        if session_repository is not None:
            session_data = await session_repository.get(ctx.tenant_id, chatId)
            return ok(page_data(session_data["messages"] if session_data else [], page, pageSize), trace_id=ctx.trace_id)
        session_data = store.sessions.get(chatId)
        messages = session_data["messages"] if session_data and session_data["tenantId"] == ctx.tenant_id else []
        return ok(page_data(messages, page, pageSize), trace_id=ctx.trace_id)

    @app.put("/ai/sessions/{sessionId}")
    async def session_upsert(sessionId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE"))):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="session payload is required")
        legacy = is_legacy_request(request)
        if not legacy:
            payload = java_session_payload(sessionId, payload)
        if session_repository is not None:
            saved = await session_repository.upsert(ctx.tenant_id, sessionId, payload)
            if saved is None:
                raise session_not_found(request)
            return ok(saved, trace_id=ctx.trace_id)
        existing = get_or_create_session(store, ctx, sessionId, str(payload.get("chatId") or sessionId))
        if legacy:
            for attribute in ("title", "chatId", "modelProfile", "workspace", "pinned", "archived"):
                if attribute in payload:
                    existing[attribute] = payload[attribute]
        else:
            existing.update(payload)
        existing["updatedAt"] = now_iso()
        return ok(existing, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/pin")
    async def session_pin(
        sessionId: str,
        request: Request,
        value: bool = Query(...),
        ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE")),
    ):
        if session_repository is not None:
            saved = await session_repository.set_flag(ctx.tenant_id, sessionId, "pinned", value)
            if saved is None:
                raise session_not_found(request)
            return ok(saved, trace_id=ctx.trace_id)
        session_data = require_session(store, ctx, sessionId, session_not_found_status(request))
        session_data["pinned"] = value
        session_data["updatedAt"] = now_iso()
        return ok(session_data, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/archive")
    async def session_archive(
        sessionId: str,
        request: Request,
        value: bool = Query(...),
        ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE")),
    ):
        if session_repository is not None:
            saved = await session_repository.set_flag(ctx.tenant_id, sessionId, "archived", value)
            if saved is None:
                raise session_not_found(request)
            return ok(saved, trace_id=ctx.trace_id)
        session_data = require_session(store, ctx, sessionId, session_not_found_status(request))
        session_data["archived"] = value
        session_data["updatedAt"] = now_iso()
        return ok(session_data, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/branches/compare")
    async def session_compare(sessionId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        session_data = (
            await session_repository.get(ctx.tenant_id, sessionId)
            if session_repository is not None
            else require_session(store, ctx, sessionId, session_not_found_status(request))
        )
        if session_data is None:
            raise session_not_found(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="compare request is required")
        try:
            comparison = compare_session_branches(session_data, payload.get("sourceBranchId"), payload.get("targetBranchId"))
        except SessionBranchValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ok(comparison, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/branches/merge")
    async def session_merge(sessionId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE"))):
        session_data = (
            await session_repository.get(ctx.tenant_id, sessionId)
            if session_repository is not None
            else require_session(store, ctx, sessionId, session_not_found_status(request))
        )
        if session_data is None:
            raise session_not_found(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="merge request is required")
        try:
            merged_session, merged_branch = merge_session_branches(
                session_data,
                payload.get("sourceBranchId"),
                payload.get("targetBranchId"),
                payload.get("title"),
            )
        except SessionBranchValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if session_repository is not None:
            saved = await session_repository.upsert(
                ctx.tenant_id,
                sessionId,
                merged_session,
            )
            if saved is None:
                raise session_not_found(request)
        else:
            store.sessions[sessionId] = merged_session
            saved = merged_session
        return ok(
            {
                "session": saved,
                "mergedBranch": merged_branch,
                "mergedMessageCount": len(merged_branch["messages"]),
            },
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/workflow/react/chat")
    async def workflow_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        if workflow_service is not None:
            async def respond() -> dict[str, Any]:
                response = await chat_response_with_provider(
                    store,
                    ctx,
                    payload,
                    mode="workflow",
                    require_evidence=False,
                    settings=active_settings,
                    session_repository=session_repository,
                    memory_service=memory_service,
                )
                return response.model_dump()

            workflow = await workflow_service.run(tenant_context(ctx), payload.prompt, payload.modelProfile, payload.chatId, respond)
            response = ChatResponseDto.model_validate(workflow.response)
            task = workflow.task
        else:
            response = await chat_response_with_provider(
                store, ctx, payload, mode="workflow", require_evidence=False, settings=active_settings,
                session_repository=session_repository, memory_service=memory_service
            )
            task = create_workflow_task(store, ctx, payload, response)
        result = response.model_dump() | {"taskId": task["taskId"], "status": task["status"]}
        return ok(result, trace_id=ctx.trace_id)

    @app.post("/ai/workflow/react/chat/stream")
    async def workflow_stream(request: Request, payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        legacy = is_legacy_request(request)
        try:
            if workflow_service is not None:
                async def respond() -> dict[str, Any]:
                    response = await chat_response_with_provider(
                        store,
                        ctx,
                        payload,
                        mode="workflow",
                        require_evidence=False,
                        settings=active_settings,
                        session_repository=session_repository,
                        memory_service=memory_service,
                    )
                    return response.model_dump()

                workflow = await workflow_service.run(tenant_context(ctx), payload.prompt, payload.modelProfile, payload.chatId, respond)
                response = ChatResponseDto.model_validate(workflow.response)
            else:
                response = await chat_response_with_provider(
                    store, ctx, payload, mode="workflow", require_evidence=False, settings=active_settings,
                    session_repository=session_repository, memory_service=memory_service
                )
                create_workflow_task(store, ctx, payload, response)
        except Exception as exc:
            return PlainTextResponse(to_sse_error(exc, ctx.trace_id, legacy), media_type="text/event-stream")
        return PlainTextResponse(
            to_sse(response, ctx.trace_id, legacy=legacy, react=True), media_type="text/event-stream"
        )

    @app.post("/ai/workflow/tasks/{taskId}/resume")
    async def workflow_resume(request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        if not is_legacy_request(request) or workflow_service is None or workflow_repository is None:
            raise HTTPException(status_code=404, detail="task not found")
        task = await workflow_repository.get(ctx.tenant_id, taskId)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        payload = ChatRequestDto(
            chatId=str(task["chatId"]),
            prompt=str(task["userInput"]),
            modelProfile=str(task["modelProfile"]),
        )

        async def respond() -> dict[str, Any]:
            response = await chat_response_with_provider(
                store,
                ctx,
                payload,
                mode="workflow",
                require_evidence=False,
                settings=active_settings,
                session_repository=session_repository,
                memory_service=memory_service,
            )
            return response.model_dump()

        try:
            workflow = await workflow_service.resume(tenant_context(ctx), taskId, respond)
        except WorkflowNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response = ChatResponseDto.model_validate(workflow.response)
        return ok(response.model_dump() | {"taskId": taskId, "status": workflow.task["status"]}, trace_id=ctx.trace_id)

    @app.post("/ai/workflow/tasks/{taskId}/cancel")
    async def workflow_cancel(request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        if not is_legacy_request(request) or workflow_service is None:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            task = await workflow_service.cancel(tenant_context(ctx), taskId)
        except WorkflowNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/workflow/tasks")
    async def workflow_list(
        request: Request,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=20, ge=1, le=200),
        ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ")),
    ):
        if not is_legacy_request(request):
            limit = bounded(page * pageSize, 1, 2000)
            tasks = (
                await workflow_repository.list_tasks(ctx.tenant_id, limit)
                if workflow_repository is not None
                else [task for task in store.workflow_tasks.values() if task["tenantId"] == ctx.tenant_id]
            )
            start = (page - 1) * pageSize
            return ok(tasks[start : start + pageSize], trace_id=ctx.trace_id)
        if workflow_repository is not None:
            tasks = await workflow_repository.list_tasks(ctx.tenant_id, bounded(page * pageSize, 1, 2000))
            return ok(page_data(tasks, page, pageSize), trace_id=ctx.trace_id)
        tasks = [task for task in store.workflow_tasks.values() if task["tenantId"] == ctx.tenant_id]
        return ok(page_data(tasks, page, pageSize), trace_id=ctx.trace_id)

    @app.get("/ai/workflow/tasks/{taskId}")
    async def workflow_task(taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        if workflow_repository is not None:
            task = await workflow_repository.get(ctx.tenant_id, taskId)
            if task is None:
                raise HTTPException(status_code=404, detail="task not found")
            return ok(task, trace_id=ctx.trace_id)
        task = store.workflow_tasks.get(taskId)
        if not task or task["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/workflow/tasks/{taskId}/events")
    async def workflow_events(
        request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))
    ):
        if workflow_repository is not None:
            events = await workflow_repository.events(ctx.tenant_id, taskId)
            if events is None:
                if is_legacy_request(request):
                    raise HTTPException(status_code=404, detail="task not found")
                return ok([], trace_id=ctx.trace_id)
            return ok(events, trace_id=ctx.trace_id)
        task = store.workflow_tasks.get(taskId)
        if not task or task["tenantId"] != ctx.tenant_id:
            if is_legacy_request(request):
                raise HTTPException(status_code=404, detail="task not found")
            return ok([], trace_id=ctx.trace_id)
        return ok(task["events"], trace_id=ctx.trace_id)

    def research_callbacks(ctx: RequestContext, model_profile: str):
        async def plan(research_topic: str) -> list[str]:
            return await research_plan_with_provider(store, tenant_context(ctx), active_settings, research_topic, model_profile)

        async def retrieve_question(question: str, task_id: str) -> dict[str, Any]:
            rag = await retrieve_hybrid(
                store,
                ctx.tenant_id,
                f"research_{task_id}",
                question,
                ingestion_service.repository if ingestion_service is not None else None,
                graph_repository,
                create_embedding_provider(active_settings),
                create_reranker(active_settings),
                active_settings.is_production,
                vector_store,
            )
            return {
                "evidence": rag["evidence"],
                "citations": [citation.model_dump() for citation in rag["citations"]],
                "retrievalStats": rag["retrievalStats"],
            }

        async def write_report(research_topic: str, findings: list[dict[str, Any]]) -> str:
            return await research_report_with_provider(
                store,
                tenant_context(ctx),
                active_settings,
                research_topic,
                model_profile,
                findings,
            )

        return plan, retrieve_question, write_report

    @app.post("/ai/research/tasks")
    async def research_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        topic = str(payload.get("topic", "")).strip()
        if not topic:
            raise HTTPException(status_code=422, detail="topic is required")
        model_profile = str(payload.get("modelProfile") or "quality")
        if research_service is None:
            return ok(create_research_task(store, ctx, topic), trace_id=ctx.trace_id)

        plan, retrieve_question, write_report = research_callbacks(ctx, model_profile)
        result = await research_service.run(tenant_context(ctx), topic, model_profile, plan, retrieve_question, write_report)
        return ok(
            {"taskId": result.task["taskId"], "topic": result.topic, "report": result.report, "status": result.task["status"]},
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/research/tasks/{taskId}/resume")
    async def research_resume(request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        if not is_legacy_request(request) or research_service is None or workflow_repository is None:
            raise HTTPException(status_code=404, detail="task not found")
        task = await workflow_repository.get(ctx.tenant_id, taskId)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        plan, retrieve_question, write_report = research_callbacks(ctx, str(task["modelProfile"]))
        try:
            result = await research_service.resume(
                tenant_context(ctx), taskId, plan, retrieve_question, write_report
            )
        except ResearchNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ok(
            {"taskId": taskId, "topic": result.topic, "report": result.report, "status": result.task["status"]},
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/research/tasks/{taskId}/cancel")
    async def research_cancel(request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        if not is_legacy_request(request) or research_service is None:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            task = await research_service.cancel(tenant_context(ctx), taskId)
        except ResearchNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/research/tasks/{taskId}")
    async def research_task(
        request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))
    ):
        legacy = is_legacy_request(request)
        if workflow_repository is not None:
            task = await workflow_repository.get(ctx.tenant_id, taskId)
            if task is None or (legacy and task["type"] not in {"RESEARCH", "DEEP_RESEARCH"}):
                raise HTTPException(status_code=404, detail="task not found")
            return ok(task, trace_id=ctx.trace_id)
        task = require_research_task(store, ctx, taskId) if legacy else require_workflow_task(store, ctx, taskId)
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/research/tasks/{taskId}/events")
    async def research_events(
        request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))
    ):
        legacy = is_legacy_request(request)
        if workflow_repository is not None:
            task = await workflow_repository.get(ctx.tenant_id, taskId)
            events = await workflow_repository.events(ctx.tenant_id, taskId)
            if not legacy and (task is None or events is None):
                return ok([], trace_id=ctx.trace_id)
            if task is None or task["type"] not in {"RESEARCH", "DEEP_RESEARCH"} or events is None:
                raise HTTPException(status_code=404, detail="task not found")
            return ok(events, trace_id=ctx.trace_id)
        if legacy:
            return ok(require_research_task(store, ctx, taskId)["events"], trace_id=ctx.trace_id)
        task = store.workflow_tasks.get(taskId)
        return ok(task["events"] if task and task["tenantId"] == ctx.tenant_id else [], trace_id=ctx.trace_id)

    @app.get("/ai/research/tasks/{taskId}/report")
    async def research_report(request: Request, taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        legacy = is_legacy_request(request)
        if workflow_repository is not None:
            task = await workflow_repository.get(ctx.tenant_id, taskId)
            if task is None or (legacy and task["type"] not in {"RESEARCH", "DEEP_RESEARCH"}):
                raise HTTPException(status_code=404, detail="task not found")
            report = str(task["finalOutput"] or "")
        else:
            task = require_research_task(store, ctx, taskId) if legacy else require_workflow_task(store, ctx, taskId)
            report = str(task.get("report") or task.get("finalOutput") or "")
        if not legacy:
            return ok({"taskId": task["taskId"], "report": report}, trace_id=ctx.trace_id)
        return PlainTextResponse(report, media_type="text/markdown; charset=utf-8")

    @app.post("/ai/memory/items")
    async def memory_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        content = str(payload.get("content", "")).strip()
        if not content:
            raise HTTPException(status_code=422, detail="memory content is required")
        if memory_repository is not None:
            item = await memory_repository.create(
                ctx.tenant_id,
                ctx.principal,
                content,
                str(payload.get("type") or "fact"),
                payload.get("sessionId"),
            )
            return ok(item, trace_id=ctx.trace_id)
        item = {"memoryId": new_id("mem"), "tenantId": ctx.tenant_id, "principal": ctx.principal, "sessionId": payload.get("sessionId"), "type": str(payload.get("type") or "fact"), "content": content, "createdAt": now_iso()}
        store.memories[item["memoryId"]] = item
        return ok(item, trace_id=ctx.trace_id)

    @app.get("/ai/memory/items")
    async def memory_list(sessionId: str | None = None, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        if memory_repository is not None:
            return ok(await memory_repository.list(ctx.tenant_id, ctx.principal, sessionId), trace_id=ctx.trace_id)
        items = [item for item in store.memories.values() if item["tenantId"] == ctx.tenant_id and item["principal"] == ctx.principal and (not sessionId or item.get("sessionId") == sessionId)]
        return ok(items, trace_id=ctx.trace_id)

    @app.get("/ai/memory/context")
    async def memory_context(prompt: str, sessionId: str | None = None, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        tokens = set(tokenize(prompt))
        items = (
            await memory_repository.list(ctx.tenant_id, ctx.principal, sessionId)
            if memory_repository is not None
            else [item for item in store.memories.values() if item["tenantId"] == ctx.tenant_id and item["principal"] == ctx.principal and (not sessionId or item.get("sessionId") == sessionId)]
        )
        matched = [item for item in items if tokens.intersection(tokenize(item["content"]))]
        return ok(matched[:10], trace_id=ctx.trace_id)

    @app.get("/ai/graph/entities")
    async def graph_entities(
        query: str = "",
        entityType: str | None = Query(default=None),
        limit: int = Query(default=100),
        ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ")),
    ):
        if graph_repository is not None:
            return ok(
                await graph_repository.list_entities(ctx.tenant_id, query, entityType, bounded(limit, 1, 200)),
                trace_id=ctx.trace_id,
            )
        return ok([item for item in store.graph_entities.values() if item["tenantId"] == ctx.tenant_id], trace_id=ctx.trace_id)

    @app.post("/ai/graph/entities")
    async def graph_entity_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        name = str(payload.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=422, detail="entity name is required")
        if graph_repository is not None:
            aliases = payload.get("aliases")
            return ok(
                await graph_repository.create_entity(
                    ctx.tenant_id,
                    name,
                    str(payload.get("type") or "CONCEPT"),
                    [str(item) for item in aliases] if isinstance(aliases, list) else [],
                    optional_payload_text(payload.get("description")),
                    optional_payload_text(payload.get("sourceId")),
                    payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                ),
                trace_id=ctx.trace_id,
            )
        entity = {"entityId": new_id("entity"), "tenantId": ctx.tenant_id, "name": name, "type": str(payload.get("type") or "CONCEPT"), "createdAt": now_iso()}
        store.graph_entities[entity["entityId"]] = entity
        return ok(entity, trace_id=ctx.trace_id)

    @app.post("/ai/graph/relations")
    async def graph_relation_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        source_entity_id = str(payload.get("sourceEntityId", "")).strip()
        target_entity_id = str(payload.get("targetEntityId", "")).strip()
        if not source_entity_id or not target_entity_id:
            raise HTTPException(status_code=422, detail="sourceEntityId and targetEntityId are required")
        if graph_repository is None:
            raise HTTPException(status_code=503, detail="graph persistence is unavailable")
        relation = await graph_repository.create_relation(
            ctx.tenant_id,
            source_entity_id,
            target_entity_id,
            str(payload.get("relationType") or "RELATED_TO"),
            optional_payload_text(payload.get("evidenceId")),
            float(payload.get("weight", 1.0)),
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        if relation is None:
            raise HTTPException(status_code=404, detail="graph entity not found")
        return ok(relation, trace_id=ctx.trace_id)

    @app.get("/ai/graph/entities/{entityId}/neighbors")
    async def graph_neighbors(entityId: str, ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        if graph_repository is None:
            raise HTTPException(status_code=503, detail="graph persistence is unavailable")
        neighbors = await graph_repository.neighbors(ctx.tenant_id, entityId)
        if neighbors is None:
            raise HTTPException(status_code=404, detail="graph entity not found")
        return ok(neighbors, trace_id=ctx.trace_id)

    @app.post("/ai/graph/facts")
    async def graph_fact_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        subject = str(payload.get("subject", "")).strip()
        predicate = str(payload.get("predicate", "")).strip()
        object_value = str(payload.get("object", "")).strip()
        if not subject or not predicate or not object_value:
            raise HTTPException(status_code=422, detail="subject, predicate, and object are required")
        if graph_repository is None:
            raise HTTPException(status_code=503, detail="graph persistence is unavailable")
        return ok(
            await graph_repository.create_fact(
                ctx.tenant_id,
                subject,
                predicate,
                object_value,
                float(payload.get("confidence", 0.8)),
                optional_payload_text(payload.get("source")),
                parse_optional_date(payload.get("validFrom")),
                parse_optional_date(payload.get("validTo")),
                payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            ),
            trace_id=ctx.trace_id,
        )

    @app.get("/ai/graph/facts")
    async def graph_facts(query: str = "", limit: int = Query(default=100), ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        if graph_repository is not None:
            return ok(
                await graph_repository.search_facts(ctx.tenant_id, query, bounded(limit, 1, 200)),
                trace_id=ctx.trace_id,
            )
        query_tokens = set(tokenize(query))
        facts = [fact for fact in store.graph_facts if fact["tenantId"] == ctx.tenant_id and (not query_tokens or query_tokens.intersection(tokenize(json.dumps(fact, ensure_ascii=False))))]
        return ok(facts, trace_id=ctx.trace_id)

    return app


def page_data(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    start = (page - 1) * page_size
    return {"items": items[start : start + page_size], "page": page, "pageSize": page_size, "total": len(items)}


def require_session(store: PlatformStore, ctx: RequestContext, session_id: str, error_status: int = 404) -> dict[str, Any]:
    session_data = store.sessions.get(session_id)
    if not session_data or session_data["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=error_status, detail="session not found")
    return session_data


def session_not_found_status(request: Request) -> int:
    return 404 if is_legacy_request(request) else 400


def session_not_found(request: Request) -> HTTPException:
    return HTTPException(status_code=session_not_found_status(request), detail="session not found")


def process_pending_jobs(store: PlatformStore, settings: Settings, tenant_id: str | None = None) -> int:
    processed = 0
    for job in list(store.jobs.values()):
        if job["status"] != "QUEUED" or (tenant_id and job["tenantId"] != tenant_id):
            continue
        process_ingestion_job(store, job["jobId"])
        processed += 1
    return processed


def execute_trusted_action(store: PlatformStore, ctx: RequestContext, action: str, action_input: dict[str, Any]) -> dict[str, Any]:
    if action == "rag_search":
        result = retrieve(store, ctx.tenant_id, str(action_input.get("chatId") or ""), str(action_input["query"]))
        return {"action": action, "status": "COMPLETED", "result": {"citations": result["citations"], "evidence": result["evidence"]}}
    if action == "memory_save":
        item = {"memoryId": new_id("mem"), "tenantId": ctx.tenant_id, "principal": ctx.principal, "sessionId": action_input.get("sessionId"), "type": str(action_input.get("type") or "fact"), "content": str(action_input["content"]), "createdAt": now_iso()}
        store.memories[item["memoryId"]] = item
        return {"action": action, "status": "COMPLETED", "result": item}
    if action == "graph_search":
        query_tokens = set(tokenize(str(action_input["query"])))
        matches = [entity for entity in store.graph_entities.values() if entity["tenantId"] == ctx.tenant_id and query_tokens.intersection(tokenize(entity["name"]))]
        return {"action": action, "status": "COMPLETED", "result": matches[: int(action_input.get("limit", 20))]}
    raise HTTPException(status_code=403, detail="action is not executable")


def create_workflow_task(store: PlatformStore, ctx: RequestContext, request: ChatRequestDto, response: ChatResponseDto) -> dict[str, Any]:
    task = {
        "taskId": new_id("task"),
        "tenantId": ctx.tenant_id,
        "type": "REACT",
        "chatId": request.chatId,
        "status": "COMPLETED",
        "userInput": request.prompt,
        "finalOutput": response.answer,
        "modelProfile": request.modelProfile,
        "sessionId": request.chatId,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "steps": response.trace,
        "events": [
            {"type": "TASK_CREATED", "createdAt": now_iso()},
            {"type": "TASK_COMPLETED", "createdAt": now_iso(), "answer": response.answer},
        ],
    }
    store.workflow_tasks[task["taskId"]] = task
    return task


def create_research_task(store: PlatformStore, ctx: RequestContext, topic: str) -> dict[str, Any]:
    report = f"# {topic}\n\nNo tenant-scoped evidence has been ingested yet. Add sources before relying on this report.\n"
    task = {
        "taskId": new_id("research"),
        "tenantId": ctx.tenant_id,
        "topic": topic,
        "type": "DEEP_RESEARCH",
        "chatId": "",
        "status": "COMPLETED",
        "userInput": topic,
        "finalOutput": report,
        "modelProfile": "quality",
        "sessionId": None,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "steps": [],
        "events": [
            {"type": "PLANNED", "createdAt": now_iso()},
            {"type": "EVIDENCE_JUDGED", "createdAt": now_iso(), "evidenceCount": 0},
            {"type": "REPORT_WRITTEN", "createdAt": now_iso()},
        ],
        "report": report,
    }
    store.workflow_tasks[task["taskId"]] = task
    store.research_tasks[task["taskId"]] = task
    return task


async def research_plan_with_provider(
    store: PlatformStore,
    context: TenantContext,
    settings: Settings,
    topic: str,
    model_profile: str,
) -> list[str]:
    provider = create_chat_provider(settings)
    if provider is None:
        return [topic]
    prompt = (
        "Break this research topic into at most four precise sub-questions. "
        "Return one question per line, without commentary.\n\nTopic: "
        f"{topic}"
    )
    try:
        completion = await provider.complete(context, prompt, model_profile)
    except (httpx.HTTPError, ValueError) as exc:
        if settings.is_production:
            raise HTTPException(status_code=502, detail="research planner request failed") from exc
        return [topic]
    usage = completion.get("usage") or {}
    record_provider_usage(
        store,
        context.tenant_id,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )
    return parse_research_questions(str(completion.get("answer") or ""), topic)


async def research_report_with_provider(
    store: PlatformStore,
    context: TenantContext,
    settings: Settings,
    topic: str,
    model_profile: str,
    findings: list[dict[str, Any]],
) -> str:
    evidence = research_evidence_text(findings)
    if not evidence:
        return f"# {topic}\n\nNo tenant-scoped evidence has been ingested yet. Add sources before relying on this report.\n"
    provider = create_chat_provider(settings)
    if provider is None:
        return fallback_research_report(topic, findings)
    prompt = (
        "Write a concise Markdown research report using only the evidence below. "
        "State uncertainty where evidence is incomplete and cite evidence with [n] markers.\n\n"
        f"Topic: {topic}\n\nEvidence:\n{evidence}"
    )
    try:
        completion = await provider.complete(context, prompt, model_profile)
    except (httpx.HTTPError, ValueError) as exc:
        if settings.is_production:
            raise HTTPException(status_code=502, detail="research writer request failed") from exc
        return fallback_research_report(topic, findings)
    usage = completion.get("usage") or {}
    record_provider_usage(
        store,
        context.tenant_id,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )
    answer = str(completion.get("answer") or "").strip()
    return answer if answer else fallback_research_report(topic, findings)


def parse_research_questions(answer: str, topic: str) -> list[str]:
    questions: list[str] = []
    for line in answer.splitlines():
        question = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if question and question not in questions:
            questions.append(question[:500])
    return questions[:4] or [topic]


def research_evidence_text(findings: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for index, finding in enumerate(findings, start=1):
        evidence = [str(item) for item in finding.get("evidence", []) if str(item).strip()]
        if evidence:
            sections.append(f"[{index}] {finding.get('question', '')}: {evidence[0][:800]}")
    return "\n".join(sections)


def fallback_research_report(topic: str, findings: list[dict[str, Any]]) -> str:
    sections = [f"# {topic}", "", "## Findings"]
    for index, finding in enumerate(findings, start=1):
        evidence = [str(item) for item in finding.get("evidence", []) if str(item).strip()]
        if evidence:
            sections.extend([f"### {finding.get('question', topic)}", evidence[0][:800], f"[{index}]"])
    return "\n\n".join(sections) + "\n"


def require_eval_run(store: PlatformStore, ctx: RequestContext, run_id: str) -> dict[str, Any]:
    run = store.eval_runs.get(run_id)
    if not run or run["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return run


def evaluation_comparison_data(dataset: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    recent = sorted(runs, key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    current = recent[0] if recent else None
    baseline_id = dataset.get("baselineRunId")
    baseline = next((run for run in recent if run.get("runId") == baseline_id), None)
    if baseline is None and len(recent) > 1:
        baseline = recent[1]
    return {"dataset": dataset, "baseline": baseline, "current": current}


def evaluation_report_response(run: dict[str, Any]) -> PlainTextResponse:
    return PlainTextResponse(
        evaluation_report_markdown(run),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rag-evaluation-{run["runId"]}.md"'},
    )


def evaluation_report_markdown(run: dict[str, Any]) -> str:
    metrics = run["metrics"]
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Run ID: `{run['runId']}`",
        f"- Dataset ID: `{run['datasetId']}`",
        f"- Tenant: `{run['tenantId']}`",
        f"- Model Profile: `{run['modelProfile']}`",
        f"- Status: `{java_evaluation_status(run['status'])}`",
        f"- Generated At: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Run Score | {percent(metrics.get('runScore', 0.0))} |",
        f"| Retrieval Hit Rate | {percent(metrics.get('retrievalHitRate', 0.0))} |",
        f"| Citation Coverage | {percent(metrics.get('citationCoverageRate', 0.0))} |",
        f"| Answer Faithfulness | {percent(metrics.get('answerFaithfulnessScore', 0.0))} |",
        f"| Avg Latency | {float(metrics.get('avgLatencyMs', 0.0)):.1f} ms |",
        f"| Failure Rate | {percent(metrics.get('failureRate', 0.0))} |",
        "",
        "## Cases",
        "",
        "| Case | Status | Score | Retrieval | Citation | Faithfulness | Latency |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        "| `{caseId}` | {status} | {score} | {retrieval} | {citation} | {faithfulness} | {latency} ms |".format(
            caseId=result["caseId"],
            status=result["status"],
            score=percent(result["score"]),
            retrieval=percent(result["retrievalHit"]),
            citation=percent(result["citationCoverage"]),
            faithfulness=percent(result["answerFaithfulness"]),
            latency=result["latencyMs"],
        )
        for result in run["results"]
    )
    return "\n".join([*lines, ""])


def percent(value: float) -> str:
    return f"{float(value) * 100:.2f}%"


def java_evaluation_status(value: str) -> str:
    return "SUCCESS" if value == "COMPLETED" else value


def require_research_task(store: PlatformStore, ctx: RequestContext, task_id: str) -> dict[str, Any]:
    task = store.research_tasks.get(task_id)
    if not task or task["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="research task not found")
    return task


def require_workflow_task(store: PlatformStore, ctx: RequestContext, task_id: str) -> dict[str, Any]:
    task = store.workflow_tasks.get(task_id)
    if not task or task["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="task not found")
    return task


def ok(data: Any, msg: str = "ok", trace_id: str | None = None) -> dict[str, Any]:
    payload = data.model_dump() if hasattr(data, "model_dump") else data
    return {"ok": 1, "msg": msg, "data": payload, "traceId": trace_id}


def fail(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def error_payload(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def chat_request_payload(
    payload: ChatRequestDto | None,
    prompt: str | None,
    chat_id: str | None,
    model_profile: str | None,
) -> ChatRequestDto:
    if payload is not None:
        return payload
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chatId is required")
    return ChatRequestDto(chatId=chat_id, prompt=prompt, modelProfile=model_profile or "balanced")


async def resolve_context(
    request: Request,
    store: PlatformStore,
    settings: Settings,
    security_repository: SecurityRepository | None,
    allow_anonymous: bool,
) -> RequestContext:
    trace_id = ensure_trace_id(request)
    tenant_header = request.headers.get(TENANT_HEADER)
    tenant_id = normalize_tenant(tenant_header)
    bearer = bearer_token(request.headers.get(AUTH_HEADER))
    jwt_identity = verify_access_token(settings, bearer) if bearer else None
    api_identity = await resolve_api_key_identity(store, security_repository, request.headers.get(API_KEY_HEADER))
    identity = jwt_identity or api_identity
    if identity:
        if tenant_header and identity.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")
        return RequestContext(trace_id, identity.tenant_id, identity.principal, identity.roles, identity.permissions, identity.auth_source)
    if not allow_anonymous:
        raise HTTPException(status_code=401, detail="authentication required")
    return RequestContext(trace_id, tenant_id, "anonymous", ["ANONYMOUS"], [], "anonymous")


def ensure_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = request.headers.get("x-request-id") or new_id("trace")
        request.state.trace_id = trace_id
    return trace_id


async def enforce_rate_limit(store: PlatformStore, settings: Settings, ctx: RequestContext) -> None:
    key = f"{ctx.tenant_id}:{ctx.principal}"
    if settings.is_production:
        try:
            allowed = await RedisTokenBucket(settings.redis_url, settings.rate_limit_per_minute).allow(key)
        except RateLimitUnavailable as exc:
            raise HTTPException(status_code=503, detail="rate limiter unavailable") from exc
        if not allowed:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        return
    now = time.time()
    window = [timestamp for timestamp in store.rate_limits.get(key, []) if now - timestamp < 60]
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    window.append(now)
    store.rate_limits[key] = window


def should_rate_limit(path: str) -> bool:
    return not path.startswith(("/actuator", "/health", "/metrics", "/v3/api-docs"))


def authenticate_api_key(store: PlatformStore, api_key: str | None) -> Identity | None:
    if not api_key:
        return None
    record = store.api_keys.get(sha256_hex(api_key.strip()))
    if not record or not record["enabled"] or record.get("revokedAt") or record.get("expiresAt", "9999") <= now_iso():
        return None
    record["lastUsedAt"] = now_iso()
    roles = [record["role"]]
    return Identity(record["keyName"], record["tenantId"], roles, permissions_for_roles(roles), "api_key")


async def resolve_api_key_identity(
    store: PlatformStore, security_repository: SecurityRepository | None, api_key: str | None
) -> Identity | None:
    if security_repository is None:
        return authenticate_api_key(store, api_key)
    stored = await security_repository.authenticate_api_key(api_key)
    return identity_from_stored(stored) if stored is not None else None


def identity_from_stored(stored: StoredIdentity) -> Identity:
    roles = list(stored.roles)
    return Identity(stored.principal, stored.tenant_id, roles, permissions_for_roles(roles), stored.source)


def create_api_key(store: PlatformStore, key_name: str, role: str, tenant_id: str) -> ApiKeyData:
    normalized_role = role.upper()
    if normalized_role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=422, detail="unsupported api key role")
    raw = "koa_" + uuid4().hex + uuid4().hex[:16]
    store.api_keys[sha256_hex(raw)] = {
        "keyHash": sha256_hex(raw),
        "keyName": key_name,
        "role": normalized_role,
        "tenantId": tenant_id,
        "enabled": True,
        "expiresAt": future_iso(days=30),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    return ApiKeyData(keyName=key_name, tenantId=tenant_id, role=normalized_role, rawApiKey=raw, expiresAt=future_iso(days=30))


async def issue_api_key(
    store: PlatformStore,
    security_repository: SecurityRepository | None,
    key_name: str,
    role: str,
    tenant_id: str,
) -> ApiKeyData:
    normalized_role = role.upper()
    if normalized_role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=422, detail="unsupported api key role")
    if security_repository is None:
        return create_api_key(store, key_name, normalized_role, tenant_id)
    try:
        issued = await security_repository.issue_api_key(key_name, normalized_role, tenant_id, expires_in_days=30)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ApiKeyData(
        keyName=issued.key_name,
        tenantId=issued.tenant_id,
        role=issued.role,
        rawApiKey=issued.raw_key,
        expiresAt=issued.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def rotate_api_key(store: PlatformStore, key_name: str, reason: str, tenant_id: str) -> ApiKeyData:
    for record in store.api_keys.values():
        if record["keyName"] == key_name and record["tenantId"] == tenant_id and not record.get("revokedAt"):
            record["enabled"] = False
            record["revokedAt"] = now_iso()
            record["revocationReason"] = reason
            return create_api_key(store, key_name, record["role"], tenant_id)
    raise HTTPException(status_code=404, detail="api key not found")


async def rotate_persistent_api_key(
    store: PlatformStore,
    security_repository: SecurityRepository | None,
    key_name: str,
    reason: str,
    tenant_id: str,
) -> ApiKeyData:
    if security_repository is None:
        return rotate_api_key(store, key_name, reason, tenant_id)
    issued = await security_repository.rotate_api_key(key_name, tenant_id, reason, expires_in_days=30)
    if issued is None:
        raise HTTPException(status_code=404, detail="api key not found")
    return ApiKeyData(
        keyName=issued.key_name,
        tenantId=issued.tenant_id,
        role=issued.role,
        rawApiKey=issued.raw_key,
        expiresAt=issued.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def revoke_api_key(store: PlatformStore, key_name: str, reason: str, tenant_id: str) -> None:
    for record in store.api_keys.values():
        if record["keyName"] == key_name and record["tenantId"] == tenant_id and not record.get("revokedAt"):
            record["enabled"] = False
            record["revokedAt"] = now_iso()
            record["revocationReason"] = reason
            return
    raise HTTPException(status_code=404, detail="api key not found")


async def revoke_persistent_api_key(
    store: PlatformStore,
    security_repository: SecurityRepository | None,
    key_name: str,
    reason: str,
    tenant_id: str,
) -> None:
    if security_repository is None:
        revoke_api_key(store, key_name, reason, tenant_id)
        return
    if not await security_repository.revoke_api_key(key_name, tenant_id, reason):
        raise HTTPException(status_code=404, detail="api key not found")


async def begin_oidc_login(
    store: PlatformStore, settings: Settings, oidc_state_store: OidcStateStore | None, return_to: str | None
) -> dict[str, str]:
    try:
        return await begin_oidc_login_flow(store.oidc_states, settings, oidc_state_store, return_to)
    except OidcFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def complete_oidc_callback(
    store: PlatformStore,
    settings: Settings,
    oidc_state_store: OidcStateStore | None,
    authorization_code: str,
    state: str,
) -> dict[str, str]:
    try:
        return await complete_oidc_callback_flow(
            store.oidc_states,
            store.oidc_exchange_codes,
            settings,
            oidc_state_store,
            authorization_code,
            state,
        )
    except OidcFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def consume_oidc_exchange_code(
    store: PlatformStore, oidc_state_store: OidcStateStore | None, exchange_code: str
) -> Identity | None:
    try:
        return await consume_oidc_exchange_code_flow(store.oidc_exchange_codes, oidc_state_store, exchange_code)
    except OidcFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


async def issue_tokens(
    store: PlatformStore,
    settings: Settings,
    identity: RequestContext | Identity,
    security_repository: SecurityRepository | None,
) -> AuthTokenData:
    expires_at = epoch_seconds() + settings.token_ttl_seconds
    payload = {
        "sub": identity.principal,
        "tenantId": identity.tenant_id,
        "roles": identity.roles,
        "permissions": identity.permissions,
        "exp": expires_at,
        "iat": epoch_seconds(),
        "jti": new_id("jwt"),
    }
    token = sign_payload(settings, payload)
    if security_repository is None:
        refresh = new_id("refresh")
        store.refresh_tokens[sha256_hex(refresh)] = {
            "principal": identity.principal,
            "tenantId": identity.tenant_id,
            "roles": identity.roles,
            "expiresAt": epoch_seconds() + settings.refresh_token_ttl_days * 86400,
            "createdAt": now_iso(),
        }
    else:
        refresh = await security_repository.issue_refresh_token(
            StoredIdentity(identity.principal, identity.tenant_id, tuple(identity.roles), identity.auth_source),
            settings.refresh_token_ttl_days,
        )
    return AuthTokenData(
        token=token,
        refreshToken=refresh,
        expiresInSeconds=settings.token_ttl_seconds,
        tenantId=identity.tenant_id,
        principal=identity.principal,
        roles=identity.roles,
        permissions=identity.permissions,
    )


def chat_response(
    store: PlatformStore,
    ctx: RequestContext,
    request: ChatRequestDto,
    mode: str,
    require_evidence: bool,
    rag: dict[str, Any] | None = None,
    record_session: bool = True,
) -> ChatResponseDto:
    rag = rag or retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    model = route_model(request.modelProfile, mode)
    answer = (
        refusal_answer(request.prompt)
        if require_evidence and not rag["evidence"]
        else compose_answer(request.prompt, rag["evidence"], mode)
    )
    trace = react_trace(request, rag, mode)
    usage = usage_for(store, ctx.tenant_id, request.prompt, answer)
    if record_session:
        session = get_or_create_session(store, ctx, request.chatId, request.chatId)
        session["messages"].extend(
            [
                {"role": "user", "content": request.prompt, "createdAt": now_iso()},
                {"role": "assistant", "content": answer, "createdAt": now_iso()},
            ]
        )
    return ChatResponseDto(chatId=request.chatId, answer=answer, model=model, usage=usage, traceId=ctx.trace_id, trace=trace)


async def chat_response_with_provider(
    store: PlatformStore,
    ctx: RequestContext,
    request: ChatRequestDto,
    mode: str,
    require_evidence: bool,
    settings: Settings,
    rag: dict[str, Any] | None = None,
    session_repository: SqlAlchemySessionRepository | None = None,
    record_session: bool = True,
    memory_service: MemoryApplicationService | None = None,
) -> ChatResponseDto:
    rag = rag or retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    response = chat_response(
        store,
        ctx,
        request,
        mode,
        require_evidence,
        rag,
        record_session=record_session and session_repository is None,
    )
    provider = create_chat_provider(settings)
    if provider is not None and (not require_evidence or rag["evidence"]):
        grounded_prompt = request.prompt
        if rag["evidence"]:
            grounded_prompt = f"{request.prompt}\n\nEvidence:\n" + "\n".join(rag["evidence"][:5])
        if memory_service is not None:
            grounded_prompt += memory_context(
                await memory_service.recall(tenant_context(ctx), request.chatId, request.prompt)
            )
        try:
            completion = await provider.complete(tenant_context(ctx), grounded_prompt, request.modelProfile)
        except (httpx.HTTPError, ValueError) as exc:
            if settings.is_production:
                raise HTTPException(status_code=502, detail="model provider request failed") from exc
        else:
            response.answer = str(completion["answer"])
            response.model = str(completion["model"])
            provider_usage = completion["usage"]
            input_tokens = int(provider_usage.get("prompt_tokens", response.usage.inputTokens))
            output_tokens = int(provider_usage.get("completion_tokens", response.usage.outputTokens))
            response.usage = record_provider_usage(store, ctx.tenant_id, input_tokens, output_tokens)
    if session_repository is not None:
        saved = await session_repository.append_turn(
            ctx.tenant_id,
            request.chatId,
            request.chatId,
            request.prompt,
            response.answer,
            request.modelProfile,
        )
        if saved is None:
            raise HTTPException(status_code=404, detail="session not found")
    if memory_service is not None:
        await memory_service.capture_explicit(tenant_context(ctx), request.chatId, request.prompt)
    return response


def rag_response(
    store: PlatformStore,
    ctx: RequestContext,
    request: ChatRequestDto,
    require_evidence: bool,
    rag: dict[str, Any] | None = None,
) -> RagResponseDto:
    rag = rag or retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    base = chat_response(store, ctx, request, "rag", require_evidence=require_evidence, rag=rag)
    stats = RetrievalStatsDto(**rag["retrievalStats"])
    return RagResponseDto(
        answer=base.answer,
        model=base.model,
        usage=base.usage,
        traceId=base.traceId,
        trace=base.trace,
        citations=rag["citations"],
        evidence=rag["evidence"],
        retrievalStats=stats,
    )


async def rag_response_with_provider(
    store: PlatformStore,
    ctx: RequestContext,
    request: ChatRequestDto,
    require_evidence: bool,
    settings: Settings,
    ingestion_repository: SqlAlchemyIngestionRepository | None = None,
    graph_repository: SqlAlchemyGraphRepository | None = None,
    session_repository: SqlAlchemySessionRepository | None = None,
    record_session: bool = True,
    vector_store: VectorStore | None = None,
    memory_service: MemoryApplicationService | None = None,
) -> RagResponseDto:
    rag = await retrieve_hybrid(
        store,
        ctx.tenant_id,
        request.chatId,
        request.prompt,
        ingestion_repository,
        graph_repository,
        create_embedding_provider(settings),
        create_reranker(settings),
        settings.is_production,
        vector_store,
    )
    base = await chat_response_with_provider(
        store, ctx, request, "rag", require_evidence, settings, rag, session_repository, record_session, memory_service
    )
    return RagResponseDto(
        answer=base.answer,
        model=base.model,
        usage=base.usage,
        traceId=base.traceId,
        trace=base.trace,
        citations=rag["citations"],
        evidence=rag["evidence"],
        retrievalStats=RetrievalStatsDto(**rag["retrievalStats"]),
    )


def react_trace(request: ChatRequestDto, rag: dict[str, Any], mode: str) -> list[AgentTraceDto]:
    return [
        AgentTraceDto(
            step=1,
            thoughtSummary="Route model profile and prepare retrieval context.",
            action="model_route",
            actionInput={"chatId": request.chatId, "modelProfile": request.modelProfile, "mode": mode},
            observation={"model": route_model(request.modelProfile, mode)},
        ),
        AgentTraceDto(
            step=2,
            thoughtSummary="Run hybrid retrieval and evidence judging.",
            action="hybrid_retrieval",
            actionInput={"prompt": request.prompt, "chatId": request.chatId},
            observation=rag["retrievalStats"],
        ),
        AgentTraceDto(
            step=3,
            thoughtSummary="Compose grounded local response with refusal when evidence is absent.",
            action="answer",
            actionInput={},
            observation={"citations": len(rag["citations"]), "evidence": len(rag["evidence"])},
        ),
    ]


def route_model(model_profile: str, mode: str) -> str:
    profile = model_profile if model_profile in {"cheap", "balanced", "quality"} else "balanced"
    return f"local-{mode}-{profile}"


def compose_answer(prompt: str, evidence: list[str], mode: str) -> str:
    if evidence:
        markers = " ".join(f"[{index + 1}]" for index in range(len(evidence)))
        return f"基于证据回答：{evidence[0][:240]} {markers}"
    return f"KnowledgeOps Python {mode} answer: {prompt}"


def refusal_answer(prompt: str) -> str:
    return f"未找到足够证据回答“{prompt}”，请先上传相关资料或补充检索范围。"


def retrieve(store: PlatformStore, tenant_id: str, chat_id: str, prompt: str) -> dict[str, Any]:
    chunks = [chunk for chunk in store.chunks if chunk["tenantId"] == tenant_id and chunk["chatId"] == chat_id]
    return retrieve_chunks(chunks, prompt)


async def retrieve_persisted(
    repository: SqlAlchemyIngestionRepository,
    tenant_id: str,
    chat_id: str,
    prompt: str,
) -> dict[str, Any]:
    return retrieve_chunks(await repository.chunks(tenant_id, chat_id), prompt)


async def retrieve_hybrid(
    store: PlatformStore,
    tenant_id: str,
    chat_id: str,
    prompt: str,
    ingestion_repository: SqlAlchemyIngestionRepository | None,
    graph_repository: SqlAlchemyGraphRepository | None,
    embedding_provider: EmbeddingProvider | None = None,
    reranker: Reranker | None = None,
    require_provider_success: bool = False,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    chunks = (
        await ingestion_repository.chunks(tenant_id, chat_id)
        if ingestion_repository is not None
        else [chunk for chunk in store.chunks if chunk["tenantId"] == tenant_id and chunk["chatId"] == chat_id]
    )
    if graph_repository is not None:
        chunks.extend(await graph_chunks(graph_repository, tenant_id, prompt))
    return await retrieve_chunks_with_semantics(
        chunks,
        prompt,
        TenantContext("", tenant_id, "retrieval", (), (), "retrieval"),
        embedding_provider,
        reranker,
        require_provider_success,
        vector_store=vector_store,
        chat_id=chat_id,
    )


async def retrieve_chunks_with_semantics(
    chunks: list[dict[str, Any]],
    prompt: str,
    context: TenantContext,
    embedding_provider: EmbeddingProvider | None,
    reranker: Reranker | None,
    require_provider_success: bool,
    vector_store: VectorStore | None = None,
    chat_id: str = "",
) -> dict[str, Any]:
    lexical = retrieve_chunks(chunks, prompt)
    if embedding_provider is None:
        return lexical
    try:
        embeddings = await embedding_provider.embed(context, [prompt])
        query_embedding = embeddings[0] if embeddings else []
        semantic_hits = [
            (vector_cosine(query_embedding, chunk.get("embedding")), chunk)
            for chunk in chunks
            if isinstance(chunk.get("embedding"), list)
        ]
        if vector_store is not None and query_embedding:
            records = await vector_store.search(context, chat_id, query_embedding, limit=5)
            semantic_hits.extend(
                (float(record["score"]), vector_record_to_chunk(record))
                for record in records
                if record.get("tenant_id") == context.tenant_id
                and record.get("chat_id") == chat_id
                and isinstance(record.get("score"), (float, int))
            )
    except (httpx.HTTPError, ValueError, TypeError, VectorStoreUnavailable, RerankerUnavailable) as exc:
        if require_provider_success:
            raise HTTPException(status_code=502, detail="embedding provider request failed") from exc
        return lexical
    semantic_hits = [(score, chunk) for score, chunk in semantic_hits if score >= 0.45]
    semantic_hits.sort(key=lambda item: item[0], reverse=True)
    chunk_by_id = {str(chunk["chunkId"]): chunk for chunk in chunks}
    candidates = [chunk for _, chunk in semantic_hits]
    candidates.extend(chunk_by_id[str(citation.chunkId)] for citation in lexical["citations"] if str(citation.chunkId) in chunk_by_id)
    unique: dict[str, dict[str, Any]] = {}
    for chunk in candidates:
        unique.setdefault(str(chunk["chunkId"]), chunk)
    selected = list(unique.values())[:5]
    if reranker is not None and selected:
        try:
            scores = await reranker.rank(context, prompt, [str(chunk["content"]) for chunk in selected])
            if len(scores) != len(selected):
                raise ValueError("reranker returned an invalid score set")
            selected = [chunk for _, chunk in sorted(zip(scores, selected, strict=True), key=lambda item: item[0], reverse=True)]
        except (httpx.HTTPError, ValueError, TypeError, RerankerUnavailable) as exc:
            if require_provider_success:
                raise HTTPException(status_code=502, detail="reranker provider request failed") from exc
    return {
        "citations": [build_citation(index, chunk) for index, chunk in enumerate(selected, start=1)],
        "evidence": [chunk["content"] for chunk in selected],
        "retrievalStats": {
            **lexical["retrievalStats"],
            "vectorMatches": len({str(chunk["chunkId"]) for _, chunk in semantic_hits}),
            "hybridMatches": len(unique),
            "evidenceAccepted": len(selected),
            "refused": len(selected) == 0,
        },
    }


def vector_record_to_chunk(record: dict[str, Any]) -> dict[str, Any]:
    source_name = str(record["source_name"])
    return {
        "chunkId": str(record["chunk_id"]),
        "tenantId": str(record["tenant_id"]),
        "chatId": str(record["chat_id"]),
        "sourceName": source_name,
        "title": source_name,
        "chunkIndex": int(record["chunk_index"]),
        "content": str(record["content"]),
    }


async def graph_chunks(repository: SqlAlchemyGraphRepository, tenant_id: str, prompt: str) -> list[dict[str, Any]]:
    keyword = graph_keyword(prompt)
    if not keyword:
        return []
    entities = await repository.list_entities(tenant_id, keyword, limit=5)
    chunks: list[dict[str, Any]] = []
    for entity in entities:
        neighbors = await repository.neighbors(tenant_id, entity["entityId"])
        neighbor_context = "; ".join(
            f"{item['relationType']} → {item['entity']['name']}" for item in (neighbors or [])
        )
        content = f"{entity['name']}: {entity.get('description') or ''}".strip()
        if neighbor_context:
            content = f"{content} | {neighbor_context}"
        chunks.append(
            {
                "chunkId": entity["entityId"],
                "sourceName": "graph",
                "title": f"{entity['name']} ({entity['type']})",
                "content": content,
                "tokens": set(tokenize(content)),
            }
        )
    for fact in await repository.search_facts(tenant_id, keyword, limit=5):
        content = f"{fact['subject']} {fact['predicate']} {fact['object']}"
        chunks.append(
            {
                "chunkId": fact["factId"],
                "sourceName": "graph",
                "title": content,
                "content": content,
                "tokens": set(tokenize(content)),
            }
        )
    return chunks


def graph_keyword(prompt: str) -> str:
    tokens = tokenize(prompt)
    return max(tokens, key=len) if tokens else prompt.strip()


def retrieve_chunks(chunks: list[dict[str, Any]], prompt: str) -> dict[str, Any]:
    tokens = set(tokenize(prompt))
    keyword_hits = []
    vector_hits = []
    for chunk in chunks:
        chunk_tokens = set(chunk.get("tokens", tokenize(chunk["content"])))
        overlap = len(tokens.intersection(chunk_tokens))
        if overlap:
            keyword_hits.append((overlap, chunk))
            vector_hits.append((cosine_like(tokens, chunk_tokens), chunk))
    candidates: dict[str, tuple[float, dict[str, Any]]] = {}
    for score, chunk in keyword_hits:
        candidates[chunk["chunkId"]] = (float(score), chunk)
    for score, chunk in vector_hits:
        current = candidates.get(chunk["chunkId"], (0.0, chunk))[0]
        candidates[chunk["chunkId"]] = (current + score, chunk)
    ranked = sorted(candidates.values(), key=lambda item: item[0], reverse=True)
    accepted = [chunk for score, chunk in ranked if evidence_accepts(score)][:5]
    citations = [build_citation(index, chunk) for index, chunk in enumerate(accepted, start=1)]
    evidence = [chunk["content"] for chunk in accepted]
    return {
        "citations": citations,
        "evidence": evidence,
        "retrievalStats": {
            "keywordMatches": len(keyword_hits),
            "vectorMatches": len(vector_hits),
            "hybridMatches": len(ranked),
            "evidenceAccepted": len(accepted),
            "refused": len(accepted) == 0,
        },
    }


def build_citation(index: int, chunk: dict[str, Any]) -> CitationDto:
    return CitationDto(
        id=f"c{index}",
        source=chunk["sourceName"],
        title=chunk["title"],
        chunkId=chunk["chunkId"],
        snippet=chunk["content"][:220],
    )


def evidence_accepts(score: float) -> bool:
    return score > 0


def create_ingestion_job(
    store: PlatformStore,
    settings: Settings,
    ctx: RequestContext,
    chat_id: str,
    source_name: str,
    content: bytes,
    provided_idempotency_key: str | None = None,
) -> dict[str, Any]:
    idempotency_key = normalize_idempotency_key(ctx.tenant_id, chat_id, content, provided_idempotency_key)
    for existing in store.jobs.values():
        if existing["tenantId"] == ctx.tenant_id and existing.get("idempotencyKey") == idempotency_key:
            return public_job(existing)
    now = now_iso()
    job = {
        "jobId": new_id("job"),
        "tenantId": ctx.tenant_id,
        "chatId": chat_id,
        "sourceName": source_name,
        "status": "QUEUED",
        "attemptCount": 0,
        "maxRetries": 3,
        "queueBackend": settings.ingestion_queue_backend,
        "traceId": ctx.trace_id,
        "errorMessage": None,
        "content": content,
        "idempotencyKey": idempotency_key,
        "createdAt": now,
        "updatedAt": now,
        "startedAt": None,
        "finishedAt": None,
    }
    store.jobs[job["jobId"]] = job
    return public_job(job)


def enqueue_and_process(store: PlatformStore, settings: Settings, job_id: str) -> None:
    store.queue.append(job_id)
    # The in-memory backend exists solely for deterministic local tests. Production
    # backends are consumed by the dedicated worker command after durable enqueue.
    if settings.ingestion_queue_backend == "memory":
        while store.queue:
            process_ingestion_job(store, store.queue.pop(0))


def process_ingestion_job(store: PlatformStore, job_id: str) -> None:
    job = store.jobs[job_id]
    if job["status"] not in {"QUEUED", "RETRY"}:
        return
    job["status"] = "RUNNING"
    job["attemptCount"] += 1
    job["startedAt"] = now_iso()
    text = safe_decode(job.pop("content"))
    for index, content in enumerate(chunk_text(text)):
        chunk_id = new_id("chunk")
        store.chunks.append(
            {
                "chunkId": chunk_id,
                "tenantId": job["tenantId"],
                "chatId": job["chatId"],
                "sourceName": job["sourceName"],
                "title": job["sourceName"],
                "chunkIndex": index,
                "content": content,
                "tokens": set(tokenize(content)),
                "createdAt": now_iso(),
            }
        )
    job["status"] = "COMPLETED"
    job["finishedAt"] = now_iso()
    job["updatedAt"] = job["finishedAt"]


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"tenantId", "content", "idempotencyKey"}}


def persisted_public_job(job: PersistedIngestionJob) -> dict[str, Any]:
    return {
        "jobId": job.job_id,
        "chatId": job.chat_id,
        "sourceName": job.source_name,
        "status": job.status,
        "attemptCount": job.attempt_count,
        "maxRetries": job.max_retries,
        "errorMessage": job.error_message,
        "queueBackend": job.queue_backend,
        "traceId": job.trace_id or "",
        "createdAt": job.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updatedAt": job.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "startedAt": job.started_at.strftime("%Y-%m-%dT%H:%M:%SZ") if job.started_at else None,
        "finishedAt": job.finished_at.strftime("%Y-%m-%dT%H:%M:%SZ") if job.finished_at else None,
    }


def tenant_context(ctx: RequestContext) -> TenantContext:
    return TenantContext(ctx.trace_id, ctx.tenant_id, ctx.principal, tuple(ctx.roles), tuple(ctx.permissions), ctx.auth_source)


async def request_file(request: Request, settings: Settings, require_file: bool = False) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if hasattr(uploaded, "read"):
            name = getattr(uploaded, "filename", "document.txt") or "document.txt"
            content = await uploaded.read()
            if require_file and not content:
                raise HTTPException(status_code=400, detail="file is required")
            validate_upload(name, content, getattr(uploaded, "content_type", None), settings)
            return name, content
    if require_file:
        raise HTTPException(status_code=400, detail="file is required")
    content = await request.body()
    validate_upload("document.txt", content, request.headers.get("content-type"), settings)
    return "document.txt", content


def validate_upload(name: str, content: bytes, content_type: str | None, settings: Settings) -> None:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    allowed = {"txt", "md", "csv", "pdf"}
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="unsupported file type")
    if not content or len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file exceeds configured size limit")
    if suffix == "pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="invalid PDF signature")
    if suffix != "pdf" and b"\x00" in content:
        raise HTTPException(status_code=415, detail="binary uploads are not supported")
    if content_type and suffix == "pdf" and "pdf" not in content_type.lower():
        raise HTTPException(status_code=415, detail="PDF content type is required")


def get_or_create_session(store: PlatformStore, ctx: RequestContext, session_id: str, chat_id: str) -> dict[str, Any]:
    existing = store.sessions.get(session_id)
    if existing and existing["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="session not found")
    if not existing:
        store.sessions[session_id] = {
            "sessionId": session_id,
            "tenantId": ctx.tenant_id,
            "title": f"Session {session_id}",
            "chatId": chat_id,
            "modelProfile": "balanced",
            "updatedAt": now_iso(),
            "messages": [],
        }
    store.sessions[session_id]["updatedAt"] = now_iso()
    return store.sessions[session_id]


def create_eval_run(store: PlatformStore, ctx: RequestContext, payload: EvaluationRunRequestDto) -> dict[str, Any]:
    dataset = store.eval_datasets.get(payload.datasetId or "default")
    if dataset and dataset["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="dataset not found")
    cases = dataset["cases"] if dataset else [{"question": "default evaluation", "expectedKeywords": ["KnowledgeOps"]}]
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        started = time.perf_counter()
        request = ChatRequestDto(chatId=f"eval-{index}", prompt=str(case["question"]), modelProfile=payload.modelProfile)
        answer = chat_response(store, ctx, request, "eval", require_evidence=False)
        expected = [str(item).lower() for item in case.get("expectedKeywords", [])]
        pool = answer.answer.lower()
        keyword_score = 1.0 if not expected else len([keyword for keyword in expected if keyword in pool]) / len(expected)
        citations: list[str] = []
        evidence: list[str] = []
        retrieval_hit = 1.0 if evidence else 0.0
        citation_coverage = 1.0 if citations else 0.0
        score = round4(0.30 * retrieval_hit + 0.25 * citation_coverage + 0.25 * keyword_score + 0.20 * keyword_score)
        results.append(
            {
                "resultId": new_id("eval-result"),
                "caseId": case.get("caseId", f"case-{index + 1}"),
                "status": "SUCCESS",
                "question": str(case["question"]),
                "answer": answer.answer,
                "citations": citations,
                "evidence": evidence,
                "retrievalHit": retrieval_hit,
                "citationCoverage": citation_coverage,
                "keywordScore": round4(keyword_score),
                "answerFaithfulness": round4(keyword_score),
                "score": score,
                "latencyMs": round((time.perf_counter() - started) * 1000),
                "errorMessage": None,
            }
        )
    metrics = {
        "runScore": average_metric(results, "score"),
        "totalCases": len(results),
        "passedCases": sum(result["score"] >= 0.7 for result in results),
        "retrievalHitRate": average_metric(results, "retrievalHit"),
        "citationCoverageRate": average_metric(results, "citationCoverage"),
        "answerFaithfulnessScore": average_metric(results, "answerFaithfulness"),
        "avgLatencyMs": average_metric(results, "latencyMs"),
        "failureRate": 0.0,
    }
    now = now_iso()
    run = {
        "runId": new_id("run"),
        "tenantId": ctx.tenant_id,
        "datasetId": payload.datasetId or "default",
        "status": "COMPLETED",
        "modelProfile": payload.modelProfile,
        "metrics": metrics,
        "results": results,
        "errorMessage": None,
        "startedAt": now,
        "finishedAt": now,
        "createdAt": now,
    }
    store.eval_runs[run["runId"]] = run
    return run


def average_metric(items: list[dict[str, Any]], key: str) -> float:
    return round4(sum(float(item[key]) for item in items) / len(items)) if items else 0.0


async def create_persisted_eval_run(
    repository: SqlAlchemyEvaluationRepository,
    store: PlatformStore,
    ctx: RequestContext,
    payload: EvaluationRunRequestDto,
    settings: Settings,
    ingestion_repository: SqlAlchemyIngestionRepository | None,
    graph_repository: SqlAlchemyGraphRepository | None,
    vector_store: VectorStore | None = None,
) -> dict[str, Any]:
    dataset_id = payload.datasetId or "default"
    dataset = await repository.get_dataset(ctx.tenant_id, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    results: list[dict[str, Any]] = []
    for index, case in enumerate(dataset["cases"]):
        started = time.perf_counter()
        answer = ""
        status_value = "SUCCESS"
        error_message: str | None = None
        try:
            response = await rag_response_with_provider(
                store,
                ctx,
                ChatRequestDto(
                    chatId=str(case.get("chatId") or f"eval-{index}"),
                    prompt=str(case["question"]),
                    modelProfile=payload.modelProfile,
                ),
                require_evidence=False,
                settings=settings,
                ingestion_repository=ingestion_repository,
                graph_repository=graph_repository,
                record_session=False,
                vector_store=vector_store,
            )
            answer = response.answer
            if not answer:
                status_value = "FAILED"
                error_message = "empty answer"
        except Exception as exc:  # Evaluation stores per-case failure instead of losing the complete run.
            status_value = "FAILED"
            error_message = str(exc)
        citations = [f"{item.source}:{item.title}:{item.chunkId}" for item in response.citations] if answer else []
        evidence = response.evidence if answer else []
        scores = score_evaluation_case(case, answer, citations, evidence, status_value == "FAILED")
        results.append(
            {
                "resultId": new_id("result"),
                "caseId": str(case.get("caseId") or f"case-{index + 1}"),
                "status": status_value,
                "question": str(case["question"]),
                "answer": answer,
                "citations": citations,
                "evidence": evidence,
                "retrievalHit": scores["retrievalHit"],
                "citationCoverage": scores["citationCoverage"],
                "keywordScore": scores["keywordScore"],
                "answerFaithfulness": scores["answerFaithfulness"],
                "score": scores["score"],
                "latencyMs": round((time.perf_counter() - started) * 1000),
                "errorMessage": error_message,
            }
        )
    return await repository.create_completed_run(ctx.tenant_id, dataset_id, payload.modelProfile, results)


def score_evaluation_case(
    case: dict[str, Any], answer: str, citations: list[str], evidence: list[str], failed: bool
) -> dict[str, float]:
    answer_pool = (answer + "\n" + "\n".join(evidence)).lower()
    expected_keywords = [str(item).lower() for item in case.get("expectedKeywords", [])]
    expected_citations = [str(item).lower() for item in case.get("expectedCitations", [])]
    forbidden_keywords = [str(item).lower() for item in case.get("forbiddenKeywords", [])]
    keyword_score = hit_rate(expected_keywords, answer_pool) if expected_keywords else float(bool(answer))
    citation_coverage = hit_rate(expected_citations, "\n".join(citations).lower()) if expected_citations else 1.0
    retrieval_hit = (
        float(bool(citations) or bool(evidence) or keyword_score > 0)
        if not expected_citations
        else float(citation_coverage > 0)
    )
    if failed or not answer:
        answer_faithfulness = 0.0
    elif not citations:
        answer_faithfulness = 0.5
    else:
        answer_faithfulness = min(
            1.0,
            sum(f"[{index}]" in answer for index in range(1, len(citations) + 1)) / len(citations),
        )
    if any(keyword and keyword in answer_pool for keyword in forbidden_keywords):
        keyword_score = 0.0
        answer_faithfulness = min(answer_faithfulness, 0.2)
    return {
        "retrievalHit": round4(retrieval_hit),
        "citationCoverage": round4(citation_coverage),
        "keywordScore": round4(keyword_score),
        "answerFaithfulness": round4(answer_faithfulness),
        "score": round4(
            0.30 * retrieval_hit
            + 0.25 * citation_coverage
            + 0.25 * keyword_score
            + 0.20 * answer_faithfulness
        ),
    }


def hit_rate(expected: list[str], actual: str) -> float:
    return sum(item in actual for item in expected) / len(expected) if expected else 1.0


def optional_payload_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def parse_optional_date(value: Any) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must use ISO-8601 YYYY-MM-DD") from exc


def cost_summary_data(store: PlatformStore, tenant_id: str) -> CostSummaryDto:
    usage = store.usage.get(tenant_id, {"monthCostUsd": 0.0, "requestCount": 0, "inputTokens": 0, "outputTokens": 0})
    budget = store.budgets.get(tenant_id, {"monthlyBudgetUsd": 25.0, "hardLimitEnabled": False})
    month_cost = float(usage.get("monthCostUsd", 0.0))
    monthly_budget = float(budget.get("monthlyBudgetUsd", 25.0))
    request_count = int(usage.get("requestCount", 0))
    input_tokens = int(usage.get("inputTokens", 0))
    output_tokens = int(usage.get("outputTokens", 0))
    return CostSummaryDto(
        tenantId=tenant_id,
        month=date.today().strftime("%Y-%m"),
        monthCostUsd=round4(month_cost),
        monthlyBudgetUsd=round4(monthly_budget),
        hardLimitEnabled=bool(budget.get("hardLimitEnabled", False)),
        monthRequestCount=request_count,
        monthInputTokens=input_tokens,
        monthOutputTokens=output_tokens,
        todayCostUsd=round4(month_cost),
        todayRequestCount=request_count,
        budgetRemainingUsd=round4(max(0.0, monthly_budget - month_cost)),
        budgetExceeded=month_cost > monthly_budget,
    )


def usage_for(store: PlatformStore, tenant_id: str, prompt: str, answer: str) -> UsageDto:
    return record_provider_usage(store, tenant_id, estimate_tokens(prompt), estimate_tokens(answer))


def record_provider_usage(store: PlatformStore, tenant_id: str, input_tokens: int, output_tokens: int) -> UsageDto:
    cost = round4(input_tokens * 0.000001 + output_tokens * 0.000002)
    usage = store.usage.setdefault(tenant_id, {"monthCostUsd": 0.0, "requestCount": 0, "inputTokens": 0, "outputTokens": 0})
    usage["monthCostUsd"] = round4(float(usage["monthCostUsd"]) + cost)
    usage["requestCount"] += 1
    usage["inputTokens"] = int(usage.get("inputTokens", 0)) + input_tokens
    usage["outputTokens"] = int(usage.get("outputTokens", 0)) + output_tokens
    return UsageDto(inputTokens=input_tokens, outputTokens=output_tokens, totalTokens=input_tokens + output_tokens, estimatedCostUsd=cost)


def select_audit_fields(log: dict[str, Any]) -> dict[str, Any]:
    return {key: log[key] for key in ["tenantId", "principal", "method", "path", "status", "createdAt"]}


def to_sse(data: ChatResponseDto, trace_id: str, legacy: bool, react: bool = False) -> str:
    events = []
    for trace in data.trace:
        payload = ok(trace, msg="trace", trace_id=trace_id) if legacy else react_trace_payload(trace)
        events.append(f"event: trace\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n")
    token = ok({"token": data.answer}, msg="token", trace_id=trace_id) if legacy else {"token": data.answer}
    events.append(f"event: token\ndata: {json.dumps(token, ensure_ascii=False)}\n\n")
    done = ok(data, trace_id=trace_id) if legacy else react_response_payload(data) if react else data.model_dump()
    events.append(f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n")
    return "".join(events)


def to_sse_error(exc: Exception, trace_id: str, legacy: bool) -> str:
    message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
    payload = error_payload(message or "stream failed", "STREAM_FAILED", trace_id) if legacy else {"message": message or "stream failed"}
    return f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def seed_store(store: PlatformStore, settings: Settings) -> None:
    store.api_keys[sha256_hex(settings.demo_api_key)] = {
        "keyHash": sha256_hex(settings.demo_api_key),
        "keyName": "local-demo",
        "role": "ADMIN",
        "tenantId": settings.demo_tenant_id,
        "enabled": True,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    store.eval_datasets["default"] = {
        "datasetId": "default",
        "tenantId": settings.demo_tenant_id,
        "name": "Default Python parity dataset",
        "cases": [{"caseId": "case-1", "question": "KnowledgeOps parity", "expectedKeywords": ["KnowledgeOps"]}],
        "createdAt": now_iso(),
    }
    store.budgets[settings.demo_tenant_id] = {
        "tenantId": settings.demo_tenant_id,
        "monthlyBudgetUsd": 25.0,
        "hardLimitEnabled": False,
        "updatedAt": now_iso(),
    }
    store.action_schemas = [*java_harness_schemas(), *legacy_harness_schemas()]


def java_harness_schemas() -> list[dict[str, Any]]:
    return [
        harness_schema("query_school", "builtin", (), (), (), "read", False),
        harness_schema("query_course", "builtin", (), ("type", "edu", "sorts"), (), "read", False),
        harness_schema(
            "add_course_reservation",
            "builtin",
            ("course", "studentName", "contactInfo", "school"),
            ("remark",),
            ("contactInfo",),
            "write",
            False,
        ),
        harness_schema("rag_search", "builtin", (), ("query",), (), "read", False),
        harness_schema("mcp_call", "mcp", ("server", "tool", "arguments"), (), ("arguments",), "external", True),
        harness_schema("workspace_list_files", "workspace", (), ("path", "maxDepth"), (), "read", True),
        harness_schema("workspace_read_file", "workspace", ("path",), ("maxBytes",), (), "read", True),
        harness_schema("workspace_search_text", "workspace", ("query",), ("path", "maxMatches"), (), "read", True),
        harness_schema(
            "workspace_propose_patch",
            "workspace",
            ("path",),
            ("content", "patch", "summary"),
            ("content", "patch"),
            "write_preview",
            True,
        ),
        harness_schema(
            "workspace_apply_patch",
            "workspace",
            ("path",),
            ("content", "patch", "summary"),
            ("content", "patch"),
            "write",
            True,
        ),
        harness_schema("workspace_run_shell", "workspace", ("command",), ("timeoutSeconds",), ("command",), "shell", True),
    ]


def harness_schema(
    action: str,
    runtime: str,
    required_fields: tuple[str, ...],
    optional_fields: tuple[str, ...],
    sensitive_fields: tuple[str, ...],
    risk_level: str,
    trusted_only: bool,
) -> dict[str, Any]:
    return {
        "contract": "canonical",
        "action": action,
        "runtime": runtime,
        "requiredFields": list(required_fields),
        "optionalFields": list(optional_fields),
        "sensitiveFields": list(sensitive_fields),
        "riskLevel": risk_level,
        "trustedOnly": trusted_only,
    }


def legacy_harness_schemas() -> list[dict[str, Any]]:
    return [
        {"contract": "legacy", "action": "rag_search", "requiredKeys": ["query"], "optionalKeys": ["chatId"], "riskLevel": "read"},
        {"contract": "legacy", "action": "memory_save", "requiredKeys": ["content"], "optionalKeys": ["userId", "type"], "riskLevel": "write"},
        {"contract": "legacy", "action": "graph_search", "requiredKeys": ["query"], "optionalKeys": ["limit"], "riskLevel": "read"},
    ]


def prometheus_text(store: PlatformStore) -> str:
    lines = ["# HELP knowledgeops_python_up Python service liveness", "# TYPE knowledgeops_python_up gauge", "knowledgeops_python_up 1"]
    for name, value in sorted(store.metrics.items()):
        lines.extend([f"# TYPE {name} counter", f"{name} {value:g}"])
    return "\n".join(lines) + "\n"


def metric_inc(store: PlatformStore, name: str, amount: float = 1.0) -> None:
    store.metrics[name] = store.metrics.get(name, 0.0) + amount


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def chunk_text(text: str, size: int = 700) -> list[str]:
    clean = text.strip() or "empty document"
    return [clean[index : index + size] for index in range(0, len(clean), size)]


def safe_decode(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        try:
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="unable to extract PDF text") from exc
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="ignore")


def tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if token]


def cosine_like(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / math.sqrt(len(left) * len(right))


def vector_cosine(query: list[float], document: Any) -> float:
    if not isinstance(document, list) or not query or len(query) != len(document):
        return 0.0
    try:
        values = [float(value) for value in document]
    except (TypeError, ValueError):
        return 0.0
    query_norm = math.sqrt(sum(value * value for value in query))
    document_norm = math.sqrt(sum(value * value for value in values))
    if not query_norm or not document_norm:
        return 0.0
    return sum(left * right for left, right in zip(query, values, strict=True)) / (query_norm * document_norm)


def normalize_tenant(value: Any = None) -> str:
    return str(value or "public").strip() or "public"


def sha256_hex(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def iso_at_epoch(seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def current_epoch_millis() -> int:
    return int(time.time() * 1000)


def epoch_seconds() -> int:
    return int(time.time())


def future_iso(days: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + days * 86400))


def bounded(value: int, lower: int, upper: int) -> int:
    return max(lower, min(int(value), upper))


def round4(value: float) -> float:
    return round(float(value), 4)
