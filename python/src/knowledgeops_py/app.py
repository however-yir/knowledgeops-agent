from __future__ import annotations

import hashlib
import io
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.datastructures import UploadFile

from .api.auth_routes import register_auth_routes
from .api.canonical import (
    canonicalize_response,
    is_legacy_request,
    prepare_contract_path,
)
from .api.conversation_routes import register_conversation_routes
from .api.evaluation_routes import register_evaluation_routes
from .api.feedback_routes import register_feedback_routes
from .api.harness_routes import register_harness_routes
from .api.ingestion_routes import register_ingestion_routes
from .api.knowledge_routes import register_knowledge_routes
from .api.operations_routes import register_operations_routes
from .api.payloads import chat_request_payload, error_payload, fail, ok
from .api.rag_routes import register_rag_routes
from .api.request_runtime import (
    enforce_rate_limit,
    ensure_trace_id,
    resolve_context,
    should_rate_limit,
)
from .api.research_routes import register_research_routes
from .api.session_routes import register_session_routes
from .api.sse import to_sse as encode_sse
from .api.sse import to_sse_error as encode_sse_error
from .api.system_routes import register_system_routes
from .api.workflow_execution_routes import register_workflow_execution_routes
from .api.workflow_task_routes import register_workflow_task_routes
from .application.authentication import AuthApplicationService
from .application.costs import cost_summary_data, record_provider_usage
from .application.evaluation_reporting import evaluation_comparison_data, evaluation_report_markdown
from .application.evaluation_scoring import score_evaluation_case
from .application.harness import CanonicalHarnessApplicationService, harness_error
from .application.ingestion import IngestionApplicationService, normalize_idempotency_key
from .application.memory import MemoryApplicationService, memory_context
from .application.research import (
    DeepResearchApplicationService,
    fallback_research_report,
    parse_research_questions,
    research_evidence_text,
)
from .application.retrieval_math import HybridWeights, cosine_like, tokenize, vector_cosine
from .application.system_prompts import HYBRID_RAG_ANSWER_SYSTEM
from .application.workflow import ReactWorkflowApplicationService
from .config import Settings, load_settings
from .domain.context import TenantContext
from .domain.ports import EmbeddingProvider, OidcStateStore, Reranker, VectorStore
from .domain.runtime import PlatformStore, RequestContext
from .dto import (
    AgentTraceDto,
    AuditLogDto,
    ChatRequestDto,
    ChatResponseDto,
    CitationDto,
    EvaluationRunRequestDto,
    RagResponseDto,
    RetrievalStatsDto,
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
from .infrastructure.security_repository import SecurityRepository, SqlAlchemySecurityRepository
from .infrastructure.session_repository import SqlAlchemySessionRepository
from .infrastructure.workflow_repository import SqlAlchemyWorkflowRepository
from .infrastructure.workspace_runtime import WorkspaceRuntime
from .observability.metrics import metric_inc, prometheus_text
from .observability.setup import configure_observability


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
    auth_service = AuthApplicationService(store, active_settings, security_repository, oidc_state_store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if active_settings.seed_demo_credentials and isinstance(security_repository, SqlAlchemySecurityRepository):
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
        if workflow_repository is not None:
            # Java parity (60a69da): a crashed worker must not leave tasks
            # RUNNING forever; fail everything past the grace period on boot.
            await workflow_repository.recover_abandoned()
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
    app.state.auth_service = auth_service
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
    async def context_audit_rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        prepare_contract_path(request)
        trace_id = request.headers.get("x-request-id") or new_id("trace")
        request.state.trace_id = trace_id
        try:
            ctx = await resolve_context(request, auth_service, allow_anonymous=True)
        except HTTPException:
            # Never launder a rejected context into an attacker-chosen tenant:
            # the anonymous fallback always buckets and audits under the fixed
            # public tenant, and the route-level dependency still rejects the
            # request (401/403) with the canonical envelope.
            ctx = RequestContext(trace_id, "public", "anonymous", ["ANONYMOUS"], [], "anonymous")
        request.state.context = ctx
        if should_rate_limit(request.url.path):
            try:
                await enforce_rate_limit(store, active_settings, ctx, request)
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
        return await resolve_context(request, auth_service, allow_anonymous=True)

    def require_permissions(*required: str) -> Callable[[Request], Awaitable[RequestContext]]:
        async def dependency(request: Request) -> RequestContext:
            ctx = await resolve_context(request, auth_service, allow_anonymous=False)
            missing = [permission for permission in required if permission not in ctx.permissions]
            if missing:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
            request.state.context = ctx
            return ctx

        return dependency

    register_system_routes(
        app,
        store=store,
        ensure_trace_id=ensure_trace_id,
        require_permissions=require_permissions,
        ok=ok,
        prometheus_text=prometheus_text,
    )
    register_auth_routes(
        app,
        auth_service=auth_service,
        ensure_trace_id=ensure_trace_id,
        require_permissions=require_permissions,
        ok=ok,
        fail=fail,
    )
    register_operations_routes(
        app,
        store=store,
        require_permissions=require_permissions,
        ok=ok,
        bounded=bounded,
        now_iso=now_iso,
        select_audit_fields=select_audit_fields,
        cost_summary_data=cost_summary_data,
    )
    register_session_routes(
        app,
        store=store,
        session_repository=session_repository,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        get_or_create_session=get_or_create_session,
        require_session=require_session,
        session_not_found_status=session_not_found_status,
        session_not_found=session_not_found,
        now_iso=now_iso,
        page_data=page_data,
    )
    register_evaluation_routes(
        app,
        store=store,
        evaluation_repository=evaluation_repository,
        settings=active_settings,
        ingestion_repository=ingestion_service.repository if ingestion_service is not None else None,
        graph_repository=graph_repository,
        vector_store=vector_store,
        require_permissions=require_permissions,
        ok=ok,
        new_id=new_id,
        now_iso=now_iso,
        is_legacy_request=is_legacy_request,
        create_persisted_eval_run=create_persisted_eval_run,
        create_eval_run=create_eval_run,
        require_eval_run=require_eval_run,
        evaluation_comparison_data=evaluation_comparison_data,
        evaluation_report_response=evaluation_report_response,
    )
    register_harness_routes(
        app,
        store=store,
        harness_service=harness_service,
        memory_repository=memory_repository,
        graph_repository=graph_repository,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        sha256_hex=sha256_hex,
        epoch_seconds=epoch_seconds,
        iso_at_epoch=iso_at_epoch,
        bounded=bounded,
        execute_trusted_action=execute_trusted_action,
        harness_error=harness_error,
    )
    register_knowledge_routes(
        app,
        store=store,
        memory_repository=memory_repository,
        graph_repository=graph_repository,
        require_permissions=require_permissions,
        ok=ok,
        new_id=new_id,
        now_iso=now_iso,
        bounded=bounded,
        tokenize=tokenize,
        optional_payload_text=optional_payload_text,
        parse_optional_date=parse_optional_date,
    )
    register_workflow_task_routes(
        app,
        store=store,
        workflow_repository=workflow_repository,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        bounded=bounded,
        page_data=page_data,
    )
    register_workflow_execution_routes(
        app,
        store=store,
        workflow_service=workflow_service,
        workflow_repository=workflow_repository,
        settings=active_settings,
        session_repository=session_repository,
        memory_service=memory_service,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        tenant_context=tenant_context,
        chat_response_with_provider=chat_response_with_provider,
        create_workflow_task=create_workflow_task,
        to_sse=lambda data, trace_id, legacy, react=False: encode_sse(data, trace_id, legacy, react, ok=ok),
        to_sse_error=lambda exc, trace_id, legacy: encode_sse_error(exc, trace_id, legacy, error_payload=error_payload),
    )
    register_ingestion_routes(
        app,
        store=store,
        settings=active_settings,
        ingestion_service=ingestion_service,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        tenant_context=tenant_context,
        bounded=bounded,
        request_file=request_file,
        persisted_public_job=persisted_public_job,
        public_job=public_job,
        create_ingestion_job=create_ingestion_job,
        enqueue_and_process=enqueue_and_process,
        process_pending_jobs=process_pending_jobs,
        process_ingestion_job=process_ingestion_job,
    )
    register_conversation_routes(
        app,
        store=store,
        settings=active_settings,
        session_repository=session_repository,
        memory_service=memory_service,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        chat_request_payload=chat_request_payload,
        chat_response_with_provider=chat_response_with_provider,
        to_sse=lambda data, trace_id, legacy, react=False: encode_sse(data, trace_id, legacy, react, ok=ok),
        to_sse_error=lambda exc, trace_id, legacy: encode_sse_error(exc, trace_id, legacy, error_payload=error_payload),
    )
    register_rag_routes(
        app,
        store=store,
        settings=active_settings,
        ingestion_service=ingestion_service,
        graph_repository=graph_repository,
        session_repository=session_repository,
        vector_store=vector_store,
        memory_service=memory_service,
        require_permissions=require_permissions,
        ok=ok,
        chat_request_payload=chat_request_payload,
        rag_response_with_provider=rag_response_with_provider,
    )
    register_feedback_routes(
        app,
        store=store,
        require_permissions=require_permissions,
        ok=ok,
        now_iso=now_iso,
    )

    def research_callbacks(
        ctx: RequestContext, model_profile: str
    ) -> tuple[Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]]:
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
                HybridWeights.from_csv(active_settings.hybrid_weights),
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

    register_research_routes(
        app,
        store=store,
        research_service=research_service,
        workflow_repository=workflow_repository,
        require_permissions=require_permissions,
        ok=ok,
        is_legacy_request=is_legacy_request,
        tenant_context=tenant_context,
        create_research_task=create_research_task,
        research_callbacks=research_callbacks,
        require_research_task=require_research_task,
        require_workflow_task=require_workflow_task,
    )

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
        item: dict[str, Any] = {
            "memoryId": new_id("mem"),
            "tenantId": ctx.tenant_id,
            "principal": ctx.principal,
            "sessionId": action_input.get("sessionId"),
            "type": str(action_input.get("type") or "fact"),
            "content": str(action_input["content"]),
            "createdAt": now_iso(),
        }
        store.memories[item["memoryId"]] = item
        return {"action": action, "status": "COMPLETED", "result": item}
    if action == "graph_search":
        query_tokens = set(tokenize(str(action_input["query"])))
        matches = [entity for entity in store.graph_entities.values() if entity["tenantId"] == ctx.tenant_id and query_tokens.intersection(tokenize(entity["name"]))]
        return {"action": action, "status": "COMPLETED", "result": matches[: int(action_input.get("limit", 20))]}
    raise HTTPException(status_code=403, detail="action is not executable")


def create_workflow_task(store: PlatformStore, ctx: RequestContext, request: ChatRequestDto, response: ChatResponseDto) -> dict[str, Any]:
    task: dict[str, Any] = {
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
    task: dict[str, Any] = {
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


def require_eval_run(store: PlatformStore, ctx: RequestContext, run_id: str) -> dict[str, Any]:
    run = store.eval_runs.get(run_id)
    if not run or run["tenantId"] != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return run


def evaluation_report_response(run: dict[str, Any]) -> PlainTextResponse:
    return PlainTextResponse(
        evaluation_report_markdown(run),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rag-evaluation-{run["runId"]}.md"'},
    )


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
            # Java parity (a373082): RAG answers run with the externalized
            # enterprise system prompt and their own temperature (default 0.2)
            # instead of inheriting the chat profile temperature.
            rag_mode = mode == "rag"
            completion = await provider.complete(
                tenant_context(ctx),
                grounded_prompt,
                request.modelProfile,
                system=HYBRID_RAG_ANSWER_SYSTEM if rag_mode else None,
                temperature=settings.rag_answer_temperature if rag_mode else None,
            )
        except (httpx.HTTPError, ValueError) as exc:
            if settings.is_production and mode not in {"react", "workflow"}:
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
        HybridWeights.from_csv(settings.hybrid_weights),
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
    weights: HybridWeights | None = None,
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
        weights=weights,
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
    weights: HybridWeights | None = None,
) -> dict[str, Any]:
    effective = weights.normalized() if weights is not None else HybridWeights()
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

    # Weighted per-source fusion (Java parity #115): each source contributes
    # its score scaled by its normalized weight; a chunk seen in several
    # sources keeps its strongest weighted score. With the DEFAULT weights this
    # reproduces the previous ordering exactly (all semantic hits outrank all
    # lexical/graph hits, which keep their rank order).
    scored: dict[str, tuple[float, dict[str, Any]]] = {}

    def offer(chunk: dict[str, Any], score: float) -> None:
        key = str(chunk["chunkId"])
        best = scored.get(key)
        if best is None or score > best[0]:
            scored[key] = (score, chunk)

    for score, chunk in semantic_hits:
        offer(chunk, score * effective.vector)
    for rank, (_, chunk) in enumerate(lexical_ranked(chunks, prompt)):
        source_weight = effective.graph if chunk.get("_retrievalSource") == "graph" else effective.keyword
        offer(chunk, (1.0 / (rank + 1)) * source_weight)
    ordered = [chunk for _, chunk in sorted(scored.values(), key=lambda item: item[0], reverse=True)]
    selected = ordered[:5]
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
            "hybridMatches": len(scored),
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
                "_retrievalSource": "graph",
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


def lexical_ranked(chunks: list[dict[str, Any]], prompt: str) -> list[tuple[float, dict[str, Any]]]:
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
    for keyword_score, chunk in keyword_hits:
        candidates[chunk["chunkId"]] = (float(keyword_score), chunk)
    for vector_score, chunk in vector_hits:
        current = candidates.get(chunk["chunkId"], (0.0, chunk))[0]
        candidates[chunk["chunkId"]] = (current + vector_score, chunk)
    return sorted(candidates.values(), key=lambda item: item[0], reverse=True)


def retrieve_chunks(chunks: list[dict[str, Any]], prompt: str) -> dict[str, Any]:
    ranked = lexical_ranked(chunks, prompt)
    accepted = [chunk for score, chunk in ranked if evidence_accepts(score)][:5]
    citations = [build_citation(index, chunk) for index, chunk in enumerate(accepted, start=1)]
    evidence = [chunk["content"] for chunk in accepted]
    return {
        "citations": citations,
        "evidence": evidence,
        "retrievalStats": {
            # lexical_ranked only keeps chunks with token overlap, so the
            # keyword and vector match counts are identical by construction.
            "keywordMatches": len(ranked),
            "vectorMatches": len(ranked),
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
    job: dict[str, Any] = {
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
        if isinstance(uploaded, UploadFile):
            name = uploaded.filename or "document.txt"
            content = await uploaded.read()
            if require_file and not content:
                raise HTTPException(status_code=400, detail="file is required")
            validate_upload(name, content, uploaded.content_type, settings)
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
    run: dict[str, Any] = {
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


def usage_for(store: PlatformStore, tenant_id: str, prompt: str, answer: str) -> UsageDto:
    return record_provider_usage(store, tenant_id, estimate_tokens(prompt), estimate_tokens(answer))


def select_audit_fields(log: dict[str, Any]) -> dict[str, Any]:
    return {key: log[key] for key in ["tenantId", "principal", "method", "path", "status", "createdAt"]}


def seed_store(store: PlatformStore, settings: Settings) -> None:
    if settings.seed_demo_credentials:
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
