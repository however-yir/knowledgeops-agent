from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from jwt import InvalidTokenError

from .config import Settings, load_settings
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
from .infrastructure.providers import OpenAICompatibleChatProvider
from .infrastructure.rate_limit import RateLimitUnavailable, RedisTokenBucket
from .observability.setup import configure_observability

TENANT_HEADER = "x-tenant-id"
API_KEY_HEADER = "x-api-key"
AUTH_HEADER = "authorization"

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "ADMIN": [
        "ROLE_ADMIN",
        "PERM_AUTH_KEY_MANAGE",
        "PERM_CHAT_READ",
        "PERM_CHAT_WRITE",
        "PERM_INGESTION_READ",
        "PERM_INGESTION_WRITE",
        "PERM_RAG_READ",
        "PERM_METRICS_READ",
        "PERM_AUDIT_READ",
        "PERM_SESSION_READ",
        "PERM_SESSION_WRITE",
        "PERM_FEEDBACK_WRITE",
        "PERM_COST_READ",
        "PERM_COST_WRITE",
        "PERM_AGENT_TRUSTED",
        "PERM_EVAL_READ",
        "PERM_EVAL_WRITE",
    ],
    "USER": [
        "ROLE_USER",
        "PERM_CHAT_READ",
        "PERM_CHAT_WRITE",
        "PERM_INGESTION_READ",
        "PERM_INGESTION_WRITE",
        "PERM_RAG_READ",
        "PERM_SESSION_READ",
        "PERM_SESSION_WRITE",
        "PERM_FEEDBACK_WRITE",
        "PERM_COST_READ",
        "PERM_EVAL_READ",
        "PERM_EVAL_WRITE",
    ],
    "OPS": [
        "ROLE_OPS",
        "PERM_INGESTION_READ",
        "PERM_METRICS_READ",
        "PERM_AUDIT_READ",
        "PERM_SESSION_READ",
        "PERM_COST_READ",
        "PERM_EVAL_READ",
    ],
}


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

    app = FastAPI(
        title="KnowledgeOps Agent Python Enterprise API",
        version="0.2.0",
        docs_url="/swagger-ui/index.html",
        redoc_url=None,
    )
    app.state.settings = active_settings
    app.state.store = store
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
        if request.scope["path"].startswith("/python/v1/"):
            request.scope["path"] = request.scope["path"].removeprefix("/python/v1")
        trace_id = request.headers.get("x-request-id") or new_id("trace")
        request.state.trace_id = trace_id
        try:
            ctx = resolve_context(request, store, active_settings, allow_anonymous=True)
        except HTTPException:
            ctx = RequestContext(trace_id, normalize_tenant(request.headers.get(TENANT_HEADER)), "anonymous", ["ANONYMOUS"], [], "anonymous")
        request.state.context = ctx
        if should_rate_limit(request.url.path):
            try:
                await enforce_rate_limit(store, active_settings, ctx)
            except HTTPException as exc:
                code = "RATE_LIMIT_UNAVAILABLE" if exc.status_code == 503 else "RATE_LIMIT_EXCEEDED"
                return JSONResponse(status_code=exc.status_code, content=error_payload(str(exc.detail), code, trace_id))
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
        return response

    async def optional_ctx(request: Request) -> RequestContext:
        return resolve_context(request, store, active_settings, allow_anonymous=True)

    def require_permissions(*required: str) -> Callable[[Request], RequestContext]:
        async def dependency(request: Request) -> RequestContext:
            ctx = resolve_context(request, store, active_settings, allow_anonymous=False)
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
    def auth_token(request: Request, x_api_key: str | None = Header(default=None), x_tenant_id: str | None = Header(default=None)):
        identity = authenticate_api_key(store, x_api_key)
        if not identity:
            return fail("invalid api key", "AUTH_INVALID_API_KEY", ensure_trace_id(request))
        if x_tenant_id and normalize_tenant(x_tenant_id) != identity.tenant_id:
            return fail("tenant mismatch for api key", "AUTH_TENANT_MISMATCH", ensure_trace_id(request))
        data = issue_tokens(store, active_settings, identity)
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/refresh")
    def auth_refresh(request: Request, x_refresh_token: str | None = Header(default=None)):
        if not x_refresh_token:
            return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
        token_hash = sha256_hex(x_refresh_token)
        if token_hash in store.revoked_refresh_tokens:
            return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
        record = store.refresh_tokens.pop(token_hash, None)
        if not record or record["expiresAt"] <= epoch_seconds():
            return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
        store.revoked_refresh_tokens.add(token_hash)
        ctx = RequestContext(ensure_trace_id(request), record["tenantId"], record["principal"], record["roles"], permissions_for_roles(record["roles"]), "refresh")
        return ok(issue_tokens(store, active_settings, ctx), trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys")
    def auth_api_keys(request: Request, keyName: str = Query(..., min_length=1, max_length=120), role: str = Query(default="USER"), ctx: RequestContext = Depends(require_permissions("PERM_AUTH_KEY_MANAGE"))):
        data = create_api_key(store, keyName, role, ctx.tenant_id)
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys/rotate")
    def auth_api_key_rotate(request: Request, keyName: str = Query(..., min_length=1, max_length=120), reason: str = Query(default="rotation", max_length=240), ctx: RequestContext = Depends(require_permissions("PERM_AUTH_KEY_MANAGE"))):
        data = rotate_api_key(store, keyName, reason, ctx.tenant_id)
        return ok(data, msg="rotated", trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys/revoke")
    def auth_api_key_revoke(request: Request, keyName: str = Query(..., min_length=1, max_length=120), reason: str = Query(default="manual revoke", max_length=240), ctx: RequestContext = Depends(require_permissions("PERM_AUTH_KEY_MANAGE"))):
        revoke_api_key(store, keyName, reason, ctx.tenant_id)
        return ok({"keyName": keyName, "tenantId": ctx.tenant_id}, msg="revoked", trace_id=ensure_trace_id(request))

    @app.get("/auth/oidc/login")
    def oidc_login(request: Request, returnTo: str | None = Query(default=None, max_length=2048)):
        return ok(begin_oidc_login(store, active_settings, returnTo), trace_id=ensure_trace_id(request))

    @app.get("/auth/oidc/callback")
    def oidc_callback(request: Request, code: str = Query(..., min_length=1), state: str = Query(..., min_length=1)):
        return ok(complete_oidc_callback(store, active_settings, code, state), trace_id=ensure_trace_id(request))

    @app.post("/auth/oidc/exchange")
    async def oidc_exchange(request: Request):
        payload = await request.json()
        exchange_code = str(payload.get("exchangeCode", ""))
        identity = consume_oidc_exchange_code(store, exchange_code)
        if not identity:
            return fail("invalid or expired OIDC exchange code", "OIDC_INVALID_EXCHANGE_CODE", ensure_trace_id(request))
        return ok(issue_tokens(store, active_settings, identity), trace_id=ensure_trace_id(request))

    @app.post("/auth/logout")
    def logout(request: Request, x_refresh_token: str | None = Header(default=None)):
        if x_refresh_token:
            token_hash = sha256_hex(x_refresh_token)
            store.refresh_tokens.pop(token_hash, None)
            store.revoked_refresh_tokens.add(token_hash)
        return ok({"loggedOut": True}, trace_id=ensure_trace_id(request))

    @app.post("/ai/chat", response_model=ChatEnvelope)
    async def ai_chat(request: Request, payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = await chat_response_with_provider(store, ctx, payload, mode="chat", require_evidence=False, settings=active_settings)
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/chat/stream")
    async def ai_chat_stream(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = await chat_response_with_provider(store, ctx, payload, mode="chat", require_evidence=False, settings=active_settings)
        return PlainTextResponse(to_sse(data, ctx.trace_id), media_type="text/event-stream")

    @app.post("/ai/react/chat", response_model=ChatEnvelope)
    async def react_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = await chat_response_with_provider(store, ctx, payload, mode="react", require_evidence=False, settings=active_settings)
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/react/chat/stream")
    async def react_chat_stream(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = await chat_response_with_provider(store, ctx, payload, mode="react", require_evidence=False, settings=active_settings)
        return PlainTextResponse(to_sse(data, ctx.trace_id), media_type="text/event-stream")

    @app.post("/ai/pdf/chat", response_model=RagEnvelope)
    async def pdf_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = await rag_response_with_provider(store, ctx, payload, require_evidence=True, settings=active_settings)
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/pdf/upload/{chatId}")
    @app.post("/ingestion/upload/{chatId}")
    async def upload(chatId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_WRITE"))):
        source_name, content = await request_file(request, active_settings)
        job = create_ingestion_job(store, active_settings, ctx, chatId, source_name, content)
        enqueue_and_process(store, active_settings, job["jobId"])
        return ok(IngestionJobDto(**public_job(store.jobs[job["jobId"]])), msg="accepted", trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs")
    def ingestion_jobs(ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_READ")), chatId: str | None = Query(default=None), limit: int = Query(default=50)):
        jobs = [
            IngestionJobDto(**job).model_dump()
            for job in store.jobs.values()
            if job["tenantId"] == ctx.tenant_id and (not chatId or job["chatId"] == chatId)
        ]
        return ok(jobs[: bounded(limit, 1, 200)], trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs/{jobId}")
    def ingestion_job(jobId: str, ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_READ"))):
        job = store.jobs.get(jobId)
        if not job or job["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="job not found")
        return ok(IngestionJobDto(**job), trace_id=ctx.trace_id)

    @app.get("/ai/sessions")
    def sessions(ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        data = [SessionDto(**session).model_dump() for session in store.sessions.values() if session["tenantId"] == ctx.tenant_id]
        return ok(data, trace_id=ctx.trace_id)

    @app.get("/ai/sessions/{sessionId}")
    def session(sessionId: str, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        data = get_or_create_session(store, ctx, sessionId, chat_id=sessionId)
        return ok(SessionDto(**data), trace_id=ctx.trace_id)

    @app.post("/ai/feedback")
    def feedback(payload: FeedbackRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_FEEDBACK_WRITE"))):
        record = payload.model_dump() | {"tenantId": ctx.tenant_id, "principal": ctx.principal, "createdAt": now_iso()}
        store.feedback.append(record)
        return ok(record, msg="saved", trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/datasets")
    def evaluation_datasets(ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        data = [dataset for dataset in store.eval_datasets.values() if dataset["tenantId"] == ctx.tenant_id]
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/datasets")
    def evaluation_dataset_create(payload: EvaluationDatasetCreateDto, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_WRITE"))):
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
    def evaluation_run(payload: EvaluationRunRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        run = create_eval_run(store, ctx, payload)
        return ok(run, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/datasets/{datasetId}/runs")
    def evaluation_dataset_run(datasetId: str, payload: EvaluationRunRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        dataset = store.eval_datasets.get(datasetId)
        if not dataset or dataset["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        run = create_eval_run(store, ctx, EvaluationRunRequestDto(datasetId=datasetId, modelProfile=payload.modelProfile))
        return ok(run, trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/runs/{runId}")
    def evaluation_run_get(runId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        run = require_eval_run(store, ctx, runId)
        return ok(run, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/runs/{runId}/baseline")
    def evaluation_run_baseline(runId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_WRITE"))):
        run = require_eval_run(store, ctx, runId)
        run["isBaseline"] = True
        return ok(run, trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/datasets/{datasetId}/comparison")
    def evaluation_comparison(datasetId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        dataset = store.eval_datasets.get(datasetId)
        if not dataset or dataset["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        runs = [run for run in store.eval_runs.values() if run["tenantId"] == ctx.tenant_id and run["datasetId"] == datasetId]
        return ok({"datasetId": datasetId, "runs": runs}, trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/runs/{runId}/report")
    def evaluation_report(runId: str, ctx: RequestContext = Depends(require_permissions("PERM_EVAL_READ"))):
        run = require_eval_run(store, ctx, runId)
        return PlainTextResponse(f"# Evaluation {runId}\n\nScore: {run['metrics']['runScore']}\n", media_type="text/markdown; charset=utf-8")

    @app.get("/audit/logs", response_model=AuditLogsEnvelope)
    def audit_logs(ctx: RequestContext = Depends(require_permissions("PERM_AUDIT_READ")), limit: int = Query(default=50)):
        logs = [AuditLogDto(**select_audit_fields(log)).model_dump() for log in store.audit_logs if log["tenantId"] == ctx.tenant_id]
        return ok(list(reversed(logs[-bounded(limit, 1, 200) :])), trace_id=ctx.trace_id)

    @app.get("/cost/summary", response_model=CostEnvelope)
    def cost_summary(ctx: RequestContext = Depends(require_permissions("PERM_COST_READ"))):
        return ok(cost_summary_data(store, ctx.tenant_id), trace_id=ctx.trace_id)

    @app.post("/cost/budget", response_model=CostEnvelope)
    def cost_budget(payload: BudgetUpdateDto, ctx: RequestContext = Depends(require_permissions("PERM_COST_WRITE"))):
        store.budgets[ctx.tenant_id] = {"tenantId": ctx.tenant_id, "monthlyBudgetUsd": payload.monthlyBudgetUsd, "updatedAt": now_iso()}
        return ok(cost_summary_data(store, ctx.tenant_id), msg="updated", trace_id=ctx.trace_id)

    @app.get("/ai/harness/actions")
    def action_schema(ctx: RequestContext = Depends(require_permissions("PERM_AGENT_TRUSTED"))):
        return ok(store.action_schemas, trace_id=ctx.trace_id)

    @app.post("/ai/harness/actions/preview")
    async def action_preview(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_AGENT_TRUSTED"))):
        payload = await request.json()
        action = str(payload.get("action", ""))
        schema = next((item for item in store.action_schemas if item["action"] == action), None)
        if not schema:
            raise HTTPException(status_code=404, detail="action not found")
        action_input = payload.get("actionInput") or {}
        missing = [key for key in schema["requiredKeys"] if key not in action_input]
        if missing:
            raise HTTPException(status_code=422, detail=f"missing action input: {', '.join(missing)}")
        token = secrets.token_urlsafe(32)
        store.action_confirmations[sha256_hex(token)] = {
            "tenantId": ctx.tenant_id,
            "principal": ctx.principal,
            "action": action,
            "actionInput": action_input,
            "expiresAt": epoch_seconds() + 300,
            "used": False,
        }
        return ok({"confirmationToken": token, "action": action, "riskLevel": schema["riskLevel"], "expiresInSeconds": 300}, trace_id=ctx.trace_id)

    @app.post("/ai/harness/actions/execute/{token}")
    def action_execute(token: str, ctx: RequestContext = Depends(require_permissions("PERM_AGENT_TRUSTED"))):
        confirmation = store.action_confirmations.get(sha256_hex(token))
        if not confirmation or confirmation["tenantId"] != ctx.tenant_id or confirmation["used"] or confirmation["expiresAt"] <= epoch_seconds():
            raise HTTPException(status_code=404, detail="confirmation token not found")
        confirmation["used"] = True
        observation = execute_trusted_action(store, ctx, confirmation["action"], confirmation["actionInput"])
        return ok(observation, trace_id=ctx.trace_id)

    @app.get("/ai/chat")
    @app.get("/ai/service")
    async def html_chat(prompt: str = Query(..., min_length=1), chatId: str = Query(default="default"), ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        response = await chat_response_with_provider(store, ctx, ChatRequestDto(chatId=chatId, prompt=prompt), mode="chat", require_evidence=False, settings=active_settings)
        return PlainTextResponse(response.answer, media_type="text/html; charset=utf-8")

    @app.get("/ai/pdf/chat")
    async def pdf_chat_get(prompt: str = Query(..., min_length=1), chatId: str = Query(..., min_length=1), ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        data = await rag_response_with_provider(store, ctx, ChatRequestDto(chatId=chatId, prompt=prompt), require_evidence=True, settings=active_settings)
        return ok(data, trace_id=ctx.trace_id)

    @app.get("/ai/pdf/file/{chatId}")
    def pdf_file(chatId: str, ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        chunks = [chunk for chunk in store.chunks if chunk["tenantId"] == ctx.tenant_id and chunk["chatId"] == chatId]
        if not chunks:
            raise HTTPException(status_code=404, detail="file not found")
        return PlainTextResponse("\n".join(chunk["content"] for chunk in chunks), media_type="text/plain; charset=utf-8")

    @app.post("/ingestion/jobs/process")
    def ingestion_process(ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_WRITE"))):
        processed = process_pending_jobs(store, active_settings, ctx.tenant_id)
        return ok({"processed": processed}, trace_id=ctx.trace_id)

    @app.get("/ai/history/{kind}")
    def history_list(kind: str, page: int = Query(default=1, ge=1), pageSize: int = Query(default=20, ge=1, le=200), ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        sessions_for_tenant = [item for item in store.sessions.values() if item["tenantId"] == ctx.tenant_id]
        return ok(page_data(sessions_for_tenant, page, pageSize), trace_id=ctx.trace_id)

    @app.get("/ai/history/{kind}/{chatId}")
    def history_messages(kind: str, chatId: str, page: int = Query(default=1, ge=1), pageSize: int = Query(default=50, ge=1, le=200), ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        session_data = store.sessions.get(chatId)
        messages = session_data["messages"] if session_data and session_data["tenantId"] == ctx.tenant_id else []
        return ok(page_data(messages, page, pageSize), trace_id=ctx.trace_id)

    @app.put("/ai/sessions/{sessionId}")
    async def session_upsert(sessionId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE"))):
        payload = await request.json()
        existing = get_or_create_session(store, ctx, sessionId, str(payload.get("chatId") or sessionId))
        for attribute in ("title", "chatId", "modelProfile", "workspace", "pinned", "archived"):
            if attribute in payload:
                existing[attribute] = payload[attribute]
        existing["updatedAt"] = now_iso()
        return ok(existing, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/pin")
    def session_pin(sessionId: str, value: bool = Query(...), ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE"))):
        session_data = require_session(store, ctx, sessionId)
        session_data["pinned"] = value
        session_data["updatedAt"] = now_iso()
        return ok(session_data, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/archive")
    def session_archive(sessionId: str, value: bool = Query(...), ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE"))):
        session_data = require_session(store, ctx, sessionId)
        session_data["archived"] = value
        session_data["updatedAt"] = now_iso()
        return ok(session_data, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/branches/compare")
    async def session_compare(sessionId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        session_data = require_session(store, ctx, sessionId)
        payload = await request.json()
        return ok({"sessionId": session_data["sessionId"], "sourceBranchId": payload.get("sourceBranchId"), "targetBranchId": payload.get("targetBranchId"), "differences": []}, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/branches/merge")
    async def session_merge(sessionId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_WRITE"))):
        session_data = require_session(store, ctx, sessionId)
        payload = await request.json()
        branch_id = new_id("branch")
        return ok({"sessionId": session_data["sessionId"], "mergedBranchId": branch_id, "title": payload.get("title") or "Merged branch"}, trace_id=ctx.trace_id)

    @app.post("/ai/workflow/react/chat")
    async def workflow_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        response = await chat_response_with_provider(store, ctx, payload, mode="workflow", require_evidence=False, settings=active_settings)
        task = create_workflow_task(store, ctx, payload, response)
        result = response.model_dump() | {"taskId": task["taskId"], "status": task["status"]}
        return ok(result, trace_id=ctx.trace_id)

    @app.post("/ai/workflow/react/chat/stream")
    async def workflow_stream(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        response = await chat_response_with_provider(store, ctx, payload, mode="workflow", require_evidence=False, settings=active_settings)
        create_workflow_task(store, ctx, payload, response)
        return PlainTextResponse(to_sse(response, ctx.trace_id), media_type="text/event-stream")

    @app.get("/ai/workflow/tasks")
    def workflow_list(page: int = Query(default=1, ge=1), pageSize: int = Query(default=20, ge=1, le=200), ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        tasks = [task for task in store.workflow_tasks.values() if task["tenantId"] == ctx.tenant_id]
        return ok(page_data(tasks, page, pageSize), trace_id=ctx.trace_id)

    @app.get("/ai/workflow/tasks/{taskId}")
    def workflow_task(taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        task = store.workflow_tasks.get(taskId)
        if not task or task["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/workflow/tasks/{taskId}/events")
    def workflow_events(taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
        task = store.workflow_tasks.get(taskId)
        if not task or task["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task["events"], trace_id=ctx.trace_id)

    @app.post("/ai/research/tasks")
    async def research_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        topic = str(payload.get("topic", "")).strip()
        if not topic:
            raise HTTPException(status_code=422, detail="topic is required")
        task = create_research_task(store, ctx, topic)
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/research/tasks/{taskId}")
    def research_task(taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        task = require_research_task(store, ctx, taskId)
        return ok(task, trace_id=ctx.trace_id)

    @app.get("/ai/research/tasks/{taskId}/events")
    def research_events(taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        return ok(require_research_task(store, ctx, taskId)["events"], trace_id=ctx.trace_id)

    @app.get("/ai/research/tasks/{taskId}/report")
    def research_report(taskId: str, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        return PlainTextResponse(require_research_task(store, ctx, taskId)["report"], media_type="text/markdown; charset=utf-8")

    @app.post("/ai/memory/items")
    async def memory_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        content = str(payload.get("content", "")).strip()
        if not content:
            raise HTTPException(status_code=422, detail="memory content is required")
        item = {"memoryId": new_id("mem"), "tenantId": ctx.tenant_id, "principal": ctx.principal, "sessionId": payload.get("sessionId"), "type": str(payload.get("type") or "fact"), "content": content, "createdAt": now_iso()}
        store.memories[item["memoryId"]] = item
        return ok(item, trace_id=ctx.trace_id)

    @app.get("/ai/memory/items")
    def memory_list(sessionId: str | None = None, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        items = [item for item in store.memories.values() if item["tenantId"] == ctx.tenant_id and item["principal"] == ctx.principal and (not sessionId or item.get("sessionId") == sessionId)]
        return ok(items, trace_id=ctx.trace_id)

    @app.get("/ai/memory/context")
    def memory_context(prompt: str, sessionId: str | None = None, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_READ"))):
        tokens = set(tokenize(prompt))
        items = [item for item in store.memories.values() if item["tenantId"] == ctx.tenant_id and item["principal"] == ctx.principal and (not sessionId or item.get("sessionId") == sessionId)]
        matched = [item for item in items if tokens.intersection(tokenize(item["content"]))]
        return ok(matched[:10], trace_id=ctx.trace_id)

    @app.get("/ai/graph/entities")
    def graph_entities(ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        return ok([item for item in store.graph_entities.values() if item["tenantId"] == ctx.tenant_id], trace_id=ctx.trace_id)

    @app.post("/ai/graph/entities")
    async def graph_entity_create(request: Request, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        payload = await request.json()
        name = str(payload.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=422, detail="entity name is required")
        entity = {"entityId": new_id("entity"), "tenantId": ctx.tenant_id, "name": name, "type": str(payload.get("type") or "CONCEPT"), "createdAt": now_iso()}
        store.graph_entities[entity["entityId"]] = entity
        return ok(entity, trace_id=ctx.trace_id)

    @app.get("/ai/graph/facts")
    def graph_facts(query: str = "", ctx: RequestContext = Depends(require_permissions("PERM_RAG_READ"))):
        query_tokens = set(tokenize(query))
        facts = [fact for fact in store.graph_facts if fact["tenantId"] == ctx.tenant_id and (not query_tokens or query_tokens.intersection(tokenize(json.dumps(fact, ensure_ascii=False))))]
        return ok(facts, trace_id=ctx.trace_id)

    return app


def page_data(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    start = (page - 1) * page_size
    return {"items": items[start : start + page_size], "page": page, "pageSize": page_size, "total": len(items)}


def require_session(store: PlatformStore, ctx: RequestContext, session_id: str) -> dict[str, Any]:
    session_data = store.sessions.get(session_id)
    if not session_data or session_data["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="session not found")
    return session_data


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
        "chatId": request.chatId,
        "status": "COMPLETED",
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
    task = {
        "taskId": new_id("research"),
        "tenantId": ctx.tenant_id,
        "topic": topic,
        "status": "COMPLETED",
        "createdAt": now_iso(),
        "events": [
            {"type": "PLANNED", "createdAt": now_iso()},
            {"type": "EVIDENCE_JUDGED", "createdAt": now_iso(), "evidenceCount": 0},
            {"type": "REPORT_WRITTEN", "createdAt": now_iso()},
        ],
        "report": f"# {topic}\n\nNo tenant-scoped evidence has been ingested yet. Add sources before relying on this report.\n",
    }
    store.research_tasks[task["taskId"]] = task
    return task


def require_eval_run(store: PlatformStore, ctx: RequestContext, run_id: str) -> dict[str, Any]:
    run = store.eval_runs.get(run_id)
    if not run or run["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return run


def require_research_task(store: PlatformStore, ctx: RequestContext, task_id: str) -> dict[str, Any]:
    task = store.research_tasks.get(task_id)
    if not task or task["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="research task not found")
    return task


def ok(data: Any, msg: str = "ok", trace_id: str | None = None) -> dict[str, Any]:
    payload = data.model_dump() if hasattr(data, "model_dump") else data
    return {"ok": 1, "msg": msg, "data": payload, "traceId": trace_id}


def fail(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def error_payload(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def resolve_context(request: Request, store: PlatformStore, settings: Settings, allow_anonymous: bool) -> RequestContext:
    trace_id = ensure_trace_id(request)
    tenant_header = request.headers.get(TENANT_HEADER)
    tenant_id = normalize_tenant(tenant_header)
    bearer = bearer_token(request.headers.get(AUTH_HEADER))
    jwt_identity = verify_access_token(settings, bearer) if bearer else None
    api_identity = authenticate_api_key(store, request.headers.get(API_KEY_HEADER))
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


@dataclass
class Identity:
    principal: str
    tenant_id: str
    roles: list[str]
    permissions: list[str]
    auth_source: str


def authenticate_api_key(store: PlatformStore, api_key: str | None) -> Identity | None:
    if not api_key:
        return None
    record = store.api_keys.get(sha256_hex(api_key.strip()))
    if not record or not record["enabled"] or record.get("revokedAt") or record.get("expiresAt", "9999") <= now_iso():
        return None
    record["lastUsedAt"] = now_iso()
    roles = [record["role"]]
    return Identity(record["keyName"], record["tenantId"], roles, permissions_for_roles(roles), "api_key")


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


def rotate_api_key(store: PlatformStore, key_name: str, reason: str, tenant_id: str) -> ApiKeyData:
    for record in store.api_keys.values():
        if record["keyName"] == key_name and record["tenantId"] == tenant_id and not record.get("revokedAt"):
            record["enabled"] = False
            record["revokedAt"] = now_iso()
            record["revocationReason"] = reason
            return create_api_key(store, key_name, record["role"], tenant_id)
    raise HTTPException(status_code=404, detail="api key not found")


def revoke_api_key(store: PlatformStore, key_name: str, reason: str, tenant_id: str) -> None:
    for record in store.api_keys.values():
        if record["keyName"] == key_name and record["tenantId"] == tenant_id and not record.get("revokedAt"):
            record["enabled"] = False
            record["revokedAt"] = now_iso()
            record["revocationReason"] = reason
            return
    raise HTTPException(status_code=404, detail="api key not found")


def begin_oidc_login(store: PlatformStore, settings: Settings, return_to: str | None) -> dict[str, str]:
    metadata = oidc_metadata(settings)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    store.oidc_states[state] = {
        "nonce": nonce,
        "verifier": verifier,
        "returnTo": return_to or "",
        "expiresAt": epoch_seconds() + 600,
    }
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return {"authorizationUrl": f"{metadata['authorization_endpoint']}?{query}", "state": state}


def complete_oidc_callback(store: PlatformStore, settings: Settings, authorization_code: str, state: str) -> dict[str, str]:
    pending = store.oidc_states.pop(state, None)
    if not pending or int(pending["expiresAt"]) <= epoch_seconds():
        raise HTTPException(status_code=400, detail="invalid or expired OIDC state")
    metadata = oidc_metadata(settings)
    token_response = httpx.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret or "",
            "code_verifier": pending["verifier"],
        },
        timeout=10.0,
    )
    try:
        token_response.raise_for_status()
        tokens = token_response.json()
        claims = verify_oidc_id_token(settings, metadata, str(tokens["id_token"]), str(pending["nonce"]))
    except (httpx.HTTPError, KeyError, InvalidTokenError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="OIDC token exchange failed") from exc
    tenant_id = claims.get("tenant_id") or claims.get("tenantId") or claims.get("tid")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="OIDC tenant claim is required")
    raw_roles = claims.get("roles") or claims.get("role") or ["USER"]
    roles = [str(raw_roles)] if isinstance(raw_roles, str) else [str(role) for role in raw_roles]
    roles = [role.upper() for role in roles if role.upper() in ROLE_PERMISSIONS] or ["USER"]
    identity = Identity(str(claims["sub"]), normalize_tenant(tenant_id), roles, permissions_for_roles(roles), "oidc")
    exchange_code = secrets.token_urlsafe(32)
    store.oidc_exchange_codes[sha256_hex(exchange_code)] = {
        "identity": identity,
        "expiresAt": epoch_seconds() + 60,
    }
    return {"exchangeCode": exchange_code, "returnTo": str(pending["returnTo"])}


def consume_oidc_exchange_code(store: PlatformStore, exchange_code: str) -> Identity | None:
    record = store.oidc_exchange_codes.pop(sha256_hex(exchange_code), None)
    if not record or int(record["expiresAt"]) <= epoch_seconds():
        return None
    return record["identity"]


def oidc_metadata(settings: Settings) -> dict[str, Any]:
    if not settings.oidc_issuer_url or not settings.oidc_client_id or not settings.oidc_redirect_uri:
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    issuer = settings.oidc_issuer_url.rstrip("/")
    try:
        response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10.0)
        response.raise_for_status()
        metadata = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="OIDC discovery is unavailable") from exc
    for required_key in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
        if not metadata.get(required_key):
            raise HTTPException(status_code=503, detail="OIDC discovery response is incomplete")
    return metadata


def verify_oidc_id_token(settings: Settings, metadata: dict[str, Any], token: str, nonce: str) -> dict[str, Any]:
    key = jwt.PyJWKClient(metadata["jwks_uri"]).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=metadata.get("id_token_signing_alg_values_supported", ["RS256"]),
        audience=settings.oidc_client_id,
        issuer=metadata["issuer"],
        options={"require": ["exp", "sub", "nonce"]},
    )
    if claims.get("nonce") != nonce:
        raise InvalidTokenError("OIDC nonce mismatch")
    return claims


def issue_tokens(store: PlatformStore, settings: Settings, identity: RequestContext | Identity) -> AuthTokenData:
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
    refresh = new_id("refresh")
    store.refresh_tokens[sha256_hex(refresh)] = {
        "principal": identity.principal,
        "tenantId": identity.tenant_id,
        "roles": identity.roles,
        "expiresAt": epoch_seconds() + 7 * 86400,
        "createdAt": now_iso(),
    }
    return AuthTokenData(
        token=token,
        refreshToken=refresh,
        expiresInSeconds=settings.token_ttl_seconds,
        tenantId=identity.tenant_id,
        principal=identity.principal,
        roles=identity.roles,
        permissions=identity.permissions,
    )


def sign_payload(settings: Settings, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_access_token(settings: Settings, token: str | None) -> Identity | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "jti"]})
    except InvalidTokenError:
        return None
    roles = [str(role) for role in payload.get("roles", ["USER"])]
    return Identity(str(payload["sub"]), normalize_tenant(payload.get("tenantId")), roles, permissions_for_roles(roles), "jwt")


def bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    prefix = "Bearer "
    return header[len(prefix) :].strip() if header.startswith(prefix) else None


def permissions_for_roles(roles: list[str]) -> list[str]:
    return sorted({permission for role in roles for permission in ROLE_PERMISSIONS.get(role, [])})


def chat_response(store: PlatformStore, ctx: RequestContext, request: ChatRequestDto, mode: str, require_evidence: bool) -> ChatResponseDto:
    rag = retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    model = route_model(request.modelProfile, mode)
    answer = (
        refusal_answer(request.prompt)
        if require_evidence and not rag["evidence"]
        else compose_answer(request.prompt, rag["evidence"], mode)
    )
    trace = react_trace(request, rag, mode)
    usage = usage_for(store, ctx.tenant_id, request.prompt, answer)
    session = get_or_create_session(store, ctx, request.chatId, request.chatId)
    session["messages"].extend(
        [
            {"role": "user", "content": request.prompt, "createdAt": now_iso()},
            {"role": "assistant", "content": answer, "createdAt": now_iso()},
        ]
    )
    return ChatResponseDto(answer=answer, model=model, usage=usage, traceId=ctx.trace_id, trace=trace)


async def chat_response_with_provider(
    store: PlatformStore,
    ctx: RequestContext,
    request: ChatRequestDto,
    mode: str,
    require_evidence: bool,
    settings: Settings,
) -> ChatResponseDto:
    response = chat_response(store, ctx, request, mode, require_evidence)
    if not settings.model_base_url or not settings.model_api_key:
        return response
    rag = retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    if require_evidence and not rag["evidence"]:
        return response
    grounded_prompt = request.prompt
    if rag["evidence"]:
        grounded_prompt = f"{request.prompt}\n\nEvidence:\n" + "\n".join(rag["evidence"][:5])
    provider = OpenAICompatibleChatProvider(settings.model_base_url, settings.model_api_key, settings.model_name)
    try:
        completion = await provider.complete(ctx, grounded_prompt, request.modelProfile)
    except httpx.HTTPError as exc:
        if settings.is_production:
            raise HTTPException(status_code=502, detail="model provider request failed") from exc
        return response
    response.answer = str(completion["answer"])
    response.model = str(completion["model"])
    provider_usage = completion["usage"]
    input_tokens = int(provider_usage.get("prompt_tokens", response.usage.inputTokens))
    output_tokens = int(provider_usage.get("completion_tokens", response.usage.outputTokens))
    response.usage = record_provider_usage(store, ctx.tenant_id, input_tokens, output_tokens)
    return response


def rag_response(store: PlatformStore, ctx: RequestContext, request: ChatRequestDto, require_evidence: bool) -> RagResponseDto:
    rag = retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    base = chat_response(store, ctx, request, "rag", require_evidence=require_evidence)
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
) -> RagResponseDto:
    rag = retrieve(store, ctx.tenant_id, request.chatId, request.prompt)
    base = await chat_response_with_provider(store, ctx, request, "rag", require_evidence, settings)
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
    tokens = set(tokenize(prompt))
    keyword_hits = []
    vector_hits = []
    for chunk in store.chunks:
        if chunk["tenantId"] != tenant_id or chunk["chatId"] != chat_id:
            continue
        overlap = len(tokens.intersection(chunk["tokens"]))
        if overlap:
            keyword_hits.append((overlap, chunk))
            vector_hits.append((cosine_like(tokens, chunk["tokens"]), chunk))
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


def create_ingestion_job(store: PlatformStore, settings: Settings, ctx: RequestContext, chat_id: str, source_name: str, content: bytes) -> dict[str, Any]:
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
        "content": content,
        "createdAt": now,
        "updatedAt": now,
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
    job["updatedAt"] = now_iso()


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"tenantId", "content"}}


async def request_file(request: Request, settings: Settings) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if hasattr(uploaded, "read"):
            name = getattr(uploaded, "filename", "document.txt") or "document.txt"
            content = await uploaded.read()
            validate_upload(name, content, getattr(uploaded, "content_type", None), settings)
            return name, content
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
    results = []
    for index, case in enumerate(cases):
        request = ChatRequestDto(chatId=f"eval-{index}", prompt=str(case["question"]), modelProfile=payload.modelProfile)
        answer = chat_response(store, ctx, request, "eval", require_evidence=False)
        expected = [str(item).lower() for item in case.get("expectedKeywords", [])]
        pool = answer.answer.lower()
        keyword_score = 1.0 if not expected else len([keyword for keyword in expected if keyword in pool]) / len(expected)
        results.append({"caseId": case.get("caseId", f"case-{index + 1}"), "score": round4(keyword_score), "answer": answer.answer})
    score = round4(sum(result["score"] for result in results) / max(1, len(results)))
    run = {
        "runId": new_id("run"),
        "tenantId": ctx.tenant_id,
        "datasetId": payload.datasetId or "default",
        "status": "COMPLETED",
        "modelProfile": payload.modelProfile,
        "metrics": {"runScore": score, "totalCases": len(results), "passedCases": len([r for r in results if r["score"] >= 0.7])},
        "results": results,
        "createdAt": now_iso(),
    }
    store.eval_runs[run["runId"]] = run
    return run


def cost_summary_data(store: PlatformStore, tenant_id: str) -> CostSummaryDto:
    usage = store.usage.get(tenant_id, {"monthCostUsd": 0.0})
    budget = store.budgets.get(tenant_id, {"monthlyBudgetUsd": 25.0})
    month_cost = float(usage.get("monthCostUsd", 0.0))
    monthly_budget = float(budget.get("monthlyBudgetUsd", 25.0))
    return CostSummaryDto(
        tenantId=tenant_id,
        monthCostUsd=round4(month_cost),
        monthlyBudgetUsd=round4(monthly_budget),
        budgetRemainingUsd=round4(monthly_budget - month_cost),
    )


def usage_for(store: PlatformStore, tenant_id: str, prompt: str, answer: str) -> UsageDto:
    return record_provider_usage(store, tenant_id, estimate_tokens(prompt), estimate_tokens(answer))


def record_provider_usage(store: PlatformStore, tenant_id: str, input_tokens: int, output_tokens: int) -> UsageDto:
    cost = round4(input_tokens * 0.000001 + output_tokens * 0.000002)
    usage = store.usage.setdefault(tenant_id, {"monthCostUsd": 0.0, "requestCount": 0})
    usage["monthCostUsd"] = round4(float(usage["monthCostUsd"]) + cost)
    usage["requestCount"] += 1
    return UsageDto(inputTokens=input_tokens, outputTokens=output_tokens, totalTokens=input_tokens + output_tokens, estimatedCostUsd=cost)


def select_audit_fields(log: dict[str, Any]) -> dict[str, Any]:
    return {key: log[key] for key in ["tenantId", "principal", "method", "path", "status", "createdAt"]}


def to_sse(data: ChatResponseDto, trace_id: str) -> str:
    events = []
    for trace in data.trace:
        events.append(f"event: trace\ndata: {json.dumps(ok(trace, msg='trace', trace_id=trace_id), ensure_ascii=False)}\n\n")
    events.append(f"event: token\ndata: {json.dumps(ok({'token': data.answer}, msg='token', trace_id=trace_id), ensure_ascii=False)}\n\n")
    events.append(f"event: done\ndata: {json.dumps(ok(data, trace_id=trace_id), ensure_ascii=False)}\n\n")
    return "".join(events)


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
    store.budgets[settings.demo_tenant_id] = {"tenantId": settings.demo_tenant_id, "monthlyBudgetUsd": 25.0, "updatedAt": now_iso()}
    store.action_schemas = [
        {"action": "rag_search", "requiredKeys": ["query"], "optionalKeys": ["chatId"], "riskLevel": "read"},
        {"action": "memory_save", "requiredKeys": ["content"], "optionalKeys": ["userId", "type"], "riskLevel": "write"},
        {"action": "graph_search", "requiredKeys": ["query"], "optionalKeys": ["limit"], "riskLevel": "read"},
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


def normalize_tenant(value: Any = None) -> str:
    return str(value or "public").strip() or "public"


def sha256_hex(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def epoch_seconds() -> int:
    return int(time.time())


def future_iso(days: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + days * 86400))


def bounded(value: int, lower: int, upper: int) -> int:
    return max(lower, min(int(value), upper))


def round4(value: float) -> float:
    return round(float(value), 4)
