"""Deep Research task routes backed by the existing research application service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from knowledgeops_py.application.research import DeepResearchApplicationService, ResearchNotResumable


def register_research_routes(
    app: FastAPI,
    *,
    store: Any,
    research_service: DeepResearchApplicationService | None,
    workflow_repository: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    tenant_context: Callable[[Any], Any],
    create_research_task: Callable[..., dict[str, Any]],
    research_callbacks: Callable[[Any, str], tuple[Callable[..., Awaitable[Any]], ...]],
    require_research_task: Callable[..., dict[str, Any]],
    require_workflow_task: Callable[..., dict[str, Any]],
) -> None:
    """Register Java-compatible Deep Research task lifecycle endpoints."""

    @app.post("/ai/research/tasks")
    async def research_create(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
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
    async def research_resume(
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        if not is_legacy_request(request) or research_service is None or workflow_repository is None:
            raise HTTPException(status_code=404, detail="task not found")
        task = await workflow_repository.get(ctx.tenant_id, taskId)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        plan, retrieve_question, write_report = research_callbacks(ctx, str(task["modelProfile"]))
        try:
            result = await research_service.resume(tenant_context(ctx), taskId, plan, retrieve_question, write_report)
        except ResearchNotResumable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return ok(
            {"taskId": taskId, "topic": result.topic, "report": result.report, "status": result.task["status"]},
            trace_id=ctx.trace_id,
        )

    @app.post("/ai/research/tasks/{taskId}/cancel")
    async def research_cancel(
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
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
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any]:
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
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any]:
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

    @app.get("/ai/research/tasks/{taskId}/report", response_model=None)
    async def research_report(
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any] | PlainTextResponse:
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
