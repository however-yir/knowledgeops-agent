"""Workflow task query routes backed by the existing workflow repository."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request


def register_workflow_task_routes(
    app: FastAPI,
    *,
    store: Any,
    workflow_repository: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    bounded: Callable[[int, int, int], int],
    page_data: Callable[[list[dict[str, Any]], int, int], dict[str, Any]],
) -> None:
    """Register Java-compatible workflow task list, detail, and event routes."""

    @app.get("/ai/workflow/tasks")
    async def workflow_list(
        request: Request,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=20, ge=1, le=200),
        ctx: Any = Depends(require_permissions("PERM_SESSION_READ")),
    ) -> dict[str, Any]:
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
    async def workflow_task(
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_SESSION_READ")),
    ) -> dict[str, Any]:
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
        request: Request,
        taskId: str,
        ctx: Any = Depends(require_permissions("PERM_SESSION_READ")),
    ) -> dict[str, Any]:
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
