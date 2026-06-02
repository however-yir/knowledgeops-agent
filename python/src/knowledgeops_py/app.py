from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import Settings, load_settings
from .dto import (
    AgentTraceDto,
    ApiKeyData,
    ApiEnvelope,
    AuditLogDto,
    AuditLogsEnvelope,
    AuthTokenData,
    BudgetUpdateDto,
    ChatRequestDto,
    ChatResponseDto,
    ChatEnvelope,
    CostEnvelope,
    CitationDto,
    CostSummaryDto,
    EvaluationRunRequestDto,
    EvaluationDatasetCreateDto,
    FeedbackRequestDto,
    IngestionJobDto,
    RagResponseDto,
    RagEnvelope,
    RetrievalStatsDto,
    SessionDto,
    UsageDto,
)

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


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or load_settings()
    store = PlatformStore()
    seed_store(store, active_settings)

    app = FastAPI(
        title="KnowledgeOps Agent Python Enterprise API",
        version="0.2.0",
        docs_url="/swagger-ui/index.html",
        redoc_url=None,
    )
    app.state.settings = active_settings
    app.state.store = store

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
        return JSONResponse(status_code=500, content=error_payload(str(exc), "INTERNAL_ERROR", trace_id))

    @app.middleware("http")
    async def context_audit_rate_limit(request: Request, call_next):
        trace_id = request.headers.get("x-request-id") or new_id("trace")
        request.state.trace_id = trace_id
        try:
            ctx = resolve_context(request, store, active_settings, allow_anonymous=True)
        except HTTPException:
            ctx = RequestContext(trace_id, normalize_tenant(request.headers.get(TENANT_HEADER)), "anonymous", ["ANONYMOUS"], [], "anonymous")
        request.state.context = ctx
        if should_rate_limit(request.url.path):
            try:
                enforce_rate_limit(store, active_settings, ctx)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content=error_payload(str(exc.detail), "RATE_LIMIT_EXCEEDED", trace_id))
        started = time.perf_counter()
        response = await call_next(request)
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

    @app.get("/actuator/prometheus")
    @app.get("/metrics")
    def metrics(request: Request, _ctx: RequestContext = Depends(require_permissions("PERM_METRICS_READ"))):
        text = prometheus_text(store)
        return ok({"prometheus": text, "counters": store.metrics}, trace_id=ensure_trace_id(request))

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
        record = store.refresh_tokens.pop(sha256_hex(x_refresh_token), None)
        if not record or record["expiresAt"] <= epoch_seconds():
            return fail("invalid refresh token", "AUTH_INVALID_REFRESH_TOKEN", ensure_trace_id(request))
        ctx = RequestContext(ensure_trace_id(request), record["tenantId"], record["principal"], record["roles"], permissions_for_roles(record["roles"]), "refresh")
        return ok(issue_tokens(store, active_settings, ctx), trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys")
    def auth_api_keys(request: Request, keyName: str = Query(default="py-issued-key"), role: str = Query(default="USER"), tenantId: str | None = Query(default=None)):
        tenant_id = normalize_tenant(tenantId)
        data = create_api_key(store, keyName, role, tenant_id)
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/ai/chat", response_model=ChatEnvelope)
    def ai_chat(request: Request, payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = chat_response(store, ctx, payload, mode="chat", require_evidence=False)
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/chat/stream")
    def ai_chat_stream(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = chat_response(store, ctx, payload, mode="chat", require_evidence=False)
        return PlainTextResponse(to_sse(data, ctx.trace_id), media_type="text/event-stream")

    @app.post("/ai/react/chat", response_model=ChatEnvelope)
    def react_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = chat_response(store, ctx, payload, mode="react", require_evidence=False)
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/react/chat/stream")
    def react_chat_stream(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = chat_response(store, ctx, payload, mode="react", require_evidence=False)
        return PlainTextResponse(to_sse(data, ctx.trace_id), media_type="text/event-stream")

    @app.post("/ai/pdf/chat", response_model=RagEnvelope)
    def pdf_chat(payload: ChatRequestDto, ctx: RequestContext = Depends(require_permissions("PERM_CHAT_WRITE"))):
        data = rag_response(store, ctx, payload, require_evidence=True)
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/pdf/upload/{chatId}")
    @app.post("/ingestion/upload/{chatId}")
    async def upload(chatId: str, request: Request, ctx: RequestContext = Depends(require_permissions("PERM_INGESTION_WRITE"))):
        source_name, content = await request_file(request)
        job = create_ingestion_job(store, active_settings, ctx, chatId, source_name, content)
        enqueue_and_process(store, active_settings, job["jobId"])
        return ok(IngestionJobDto(**public_job(store.jobs[job["jobId"]])), msg="accepted", trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs")
    def ingestion_jobs(ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ")), chatId: str | None = Query(default=None), limit: int = Query(default=50)):
        jobs = [
            IngestionJobDto(**job).model_dump()
            for job in store.jobs.values()
            if job["tenantId"] == ctx.tenant_id and (not chatId or job["chatId"] == chatId)
        ]
        return ok(jobs[: bounded(limit, 1, 200)], trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs/{jobId}")
    def ingestion_job(jobId: str, ctx: RequestContext = Depends(require_permissions("PERM_SESSION_READ"))):
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

    @app.get("/audit/logs", response_model=AuditLogsEnvelope)
    def audit_logs(ctx: RequestContext = Depends(require_permissions("PERM_AUDIT_READ")), limit: int = Query(default=50)):
        logs = [AuditLogDto(**select_audit_fields(log)).model_dump() for log in store.audit_logs if log["tenantId"] == ctx.tenant_id]
        return ok(list(reversed(logs[-bounded(limit, 1, 200) :])), trace_id=ctx.trace_id)

    @app.get("/cost/summary", response_model=CostEnvelope)
    def cost_summary(ctx: RequestContext = Depends(require_permissions("PERM_COST_READ"))):
        return ok(cost_summary_data(store, ctx.tenant_id), trace_id=ctx.trace_id)

    @app.post("/cost/budget", response_model=CostEnvelope)
    def cost_budget(payload: BudgetUpdateDto, ctx: RequestContext = Depends(require_permissions("PERM_COST_WRITE"))):
        tenant_id = normalize_tenant(payload.tenantId or ctx.tenant_id)
        store.budgets[tenant_id] = {"tenantId": tenant_id, "monthlyBudgetUsd": payload.monthlyBudgetUsd, "updatedAt": now_iso()}
        return ok(cost_summary_data(store, tenant_id), msg="updated", trace_id=ctx.trace_id)

    @app.get("/ai/harness/actions")
    def action_schema(ctx: RequestContext = Depends(optional_ctx)):
        return ok(store.action_schemas, trace_id=ctx.trace_id)

    return app


def ok(data: Any, msg: str = "ok", trace_id: str | None = None) -> dict[str, Any]:
    payload = data.model_dump() if hasattr(data, "model_dump") else data
    return {"ok": 1, "msg": msg, "data": payload, "traceId": trace_id}


def fail(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def error_payload(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def resolve_context(request: Request, store: PlatformStore, settings: Settings, allow_anonymous: bool) -> RequestContext:
    trace_id = ensure_trace_id(request)
    tenant_id = normalize_tenant(request.headers.get(TENANT_HEADER))
    bearer = bearer_token(request.headers.get(AUTH_HEADER))
    jwt_identity = verify_access_token(settings, bearer) if bearer else None
    api_identity = authenticate_api_key(store, request.headers.get(API_KEY_HEADER))
    identity = jwt_identity or api_identity
    if identity:
        if tenant_id != "public" and identity.tenant_id != tenant_id:
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


def enforce_rate_limit(store: PlatformStore, settings: Settings, ctx: RequestContext) -> None:
    key = f"{ctx.tenant_id}:{ctx.principal}"
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
    if not record or not record["enabled"] or record.get("revokedAt"):
        return None
    record["lastUsedAt"] = now_iso()
    roles = [record["role"]]
    return Identity(record["keyName"], record["tenantId"], roles, permissions_for_roles(roles), "api_key")


def create_api_key(store: PlatformStore, key_name: str, role: str, tenant_id: str) -> ApiKeyData:
    raw = "koa_" + uuid4().hex + uuid4().hex[:16]
    store.api_keys[sha256_hex(raw)] = {
        "keyHash": sha256_hex(raw),
        "keyName": key_name,
        "role": role or "USER",
        "tenantId": tenant_id,
        "enabled": True,
        "expiresAt": future_iso(days=30),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    return ApiKeyData(keyName=key_name, tenantId=tenant_id, role=role or "USER", rawApiKey=raw, expiresAt=future_iso(days=30))


def issue_tokens(store: PlatformStore, settings: Settings, identity: RequestContext | Identity) -> AuthTokenData:
    expires_at = epoch_seconds() + settings.token_ttl_seconds
    payload = {
        "sub": identity.principal,
        "tenantId": identity.tenant_id,
        "roles": identity.roles,
        "permissions": identity.permissions,
        "exp": expires_at,
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
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"pyjwt.{encoded}.{signature}"


def verify_access_token(settings: Settings, token: str | None) -> Identity | None:
    if not token or not token.startswith("pyjwt."):
        return None
    try:
        _, encoded, signature = token.split(".", 2)
        expected = hmac.new(settings.jwt_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except Exception:
        return None
    if int(payload.get("exp", 0)) <= epoch_seconds():
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
    if settings.ingestion_queue_backend == "redis":
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.lpush("knowledgeops:ingestion", job_id)
            queued_id = client.rpop("knowledgeops:ingestion")
            if queued_id:
                store.queue.append(str(queued_id))
        except Exception:
            store.queue.append(job_id)
    else:
        store.queue.append(job_id)
    while store.queue:
        process_ingestion_job(store, store.queue.pop(0))


def process_ingestion_job(store: PlatformStore, job_id: str) -> None:
    job = store.jobs[job_id]
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


async def request_file(request: Request) -> tuple[str, bytes]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded = form.get("file")
        if hasattr(uploaded, "read"):
            return getattr(uploaded, "filename", "document.txt") or "document.txt", await uploaded.read()
    return "document.txt", await request.body()


def get_or_create_session(store: PlatformStore, ctx: RequestContext, session_id: str, chat_id: str) -> dict[str, Any]:
    if session_id not in store.sessions:
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
    input_tokens = estimate_tokens(prompt)
    output_tokens = estimate_tokens(answer)
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
