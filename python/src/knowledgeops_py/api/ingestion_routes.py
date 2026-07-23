"""Ingestion upload, task query, and worker-control routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from knowledgeops_py.application.ingestion import IngestionApplicationService
from knowledgeops_py.dto import IngestionJobDto


def register_ingestion_routes(
    app: FastAPI,
    *,
    store: Any,
    settings: Any,
    ingestion_service: IngestionApplicationService | None,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    tenant_context: Callable[[Any], Any],
    bounded: Callable[[int, int, int], int],
    request_file: Callable[..., Awaitable[tuple[str, bytes]]],
    persisted_public_job: Callable[[Any], dict[str, Any]],
    public_job: Callable[[dict[str, Any]], dict[str, Any]],
    create_ingestion_job: Callable[..., dict[str, Any]],
    enqueue_and_process: Callable[..., None],
    process_pending_jobs: Callable[..., int],
    process_ingestion_job: Callable[..., None],
) -> None:
    """Register Java-compatible ingestion endpoints for persistent and demo backends."""

    @app.post("/ai/pdf/upload/{chatId}")
    @app.post("/ingestion/upload/{chatId}")
    async def upload(
        chatId: str,
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_INGESTION_WRITE")),
    ) -> dict[str, Any]:
        legacy = is_legacy_request(request)
        if not legacy and not chatId.strip():
            raise HTTPException(status_code=400, detail="chatId is required")
        source_name, content = await request_file(request, settings, require_file=not legacy)
        idempotency_key = request.headers.get("x-idempotency-key")
        if ingestion_service is not None:
            persisted_job = await ingestion_service.submit(tenant_context(ctx), chatId, source_name, content, idempotency_key)
            return ok(IngestionJobDto(**persisted_public_job(persisted_job)), msg="accepted", trace_id=ctx.trace_id)
        memory_job = create_ingestion_job(store, settings, ctx, chatId, source_name, content, idempotency_key)
        enqueue_and_process(store, settings, memory_job["jobId"])
        return ok(IngestionJobDto(**public_job(store.jobs[memory_job["jobId"]])), msg="accepted", trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs")
    async def ingestion_jobs(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_INGESTION_READ")),
        chatId: str | None = Query(default=None),
        limit: int | None = Query(default=None),
    ) -> dict[str, Any]:
        legacy = is_legacy_request(request)
        if not legacy and chatId is None:
            raise HTTPException(status_code=400, detail="chatId is required")
        selected_limit = 50 if legacy else 20
        if limit is not None:
            selected_limit = limit
        selected_limit = bounded(selected_limit, 1, 200 if legacy else 100)
        if ingestion_service is not None:
            persisted_jobs = await ingestion_service.repository.list_jobs(ctx.tenant_id, chatId, selected_limit)
            return ok(
                [IngestionJobDto(**persisted_public_job(job)).model_dump() for job in persisted_jobs],
                trace_id=ctx.trace_id,
            )
        memory_jobs = [
            IngestionJobDto(**job).model_dump()
            for job in store.jobs.values()
            if job["tenantId"] == ctx.tenant_id and (not chatId or job["chatId"] == chatId)
        ]
        return ok(memory_jobs[:selected_limit], trace_id=ctx.trace_id)

    @app.get("/ingestion/jobs/{jobId}")
    async def ingestion_job(
        jobId: str,
        ctx: Any = Depends(require_permissions("PERM_INGESTION_READ")),
    ) -> dict[str, Any]:
        if ingestion_service is not None:
            job = await ingestion_service.repository.get(ctx.tenant_id, jobId)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            return ok(IngestionJobDto(**persisted_public_job(job)), trace_id=ctx.trace_id)
        job = store.jobs.get(jobId)
        if not job or job["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="job not found")
        return ok(IngestionJobDto(**job), trace_id=ctx.trace_id)

    @app.post("/ingestion/jobs/process")
    async def ingestion_process(
        request: Request,
        jobId: str | None = Query(default=None),
        ctx: Any = Depends(require_permissions("PERM_INGESTION_WRITE")),
    ) -> dict[str, Any]:
        if is_legacy_request(request):
            if ingestion_service is not None:
                processed = await ingestion_service.process_ready(ctx.tenant_id)
                return ok({"processed": processed}, trace_id=ctx.trace_id)
            processed = process_pending_jobs(store, settings, ctx.tenant_id)
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
            processed_job = await ingestion_service.process(job.job_id)
            return ok(None, msg="processed" if processed_job is not None else "empty", trace_id=ctx.trace_id)
        job = store.jobs.get(jobId)
        if not job or job["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="job not found")
        picked = job["status"] in {"QUEUED", "RETRY"}
        if picked:
            process_ingestion_job(store, jobId)
        return ok(None, msg="processed" if picked else "empty", trace_id=ctx.trace_id)
