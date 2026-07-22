"""Evaluation routes backed by the existing evaluation application services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from knowledgeops_py.dto import EvaluationDatasetCreateDto, EvaluationRunRequestDto


def register_evaluation_routes(
    app: FastAPI,
    *,
    store: Any,
    evaluation_repository: Any,
    settings: Any,
    ingestion_repository: Any,
    graph_repository: Any,
    vector_store: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    new_id: Callable[[str], str],
    now_iso: Callable[[], str],
    is_legacy_request: Callable[[Request], bool],
    create_persisted_eval_run: Callable[..., Awaitable[dict[str, Any]]],
    create_eval_run: Callable[..., dict[str, Any]],
    require_eval_run: Callable[..., dict[str, Any]],
    evaluation_comparison_data: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    evaluation_report_response: Callable[[dict[str, Any]], PlainTextResponse],
) -> None:
    """Register Java-compatible tenant-scoped dataset, run, comparison, and report endpoints."""

    @app.get("/ai/evaluation/datasets")
    async def evaluation_datasets(ctx: Any = Depends(require_permissions("PERM_EVAL_READ"))) -> dict[str, Any]:
        if evaluation_repository is not None:
            return ok(await evaluation_repository.list_datasets(ctx.tenant_id), trace_id=ctx.trace_id)
        data = [dataset for dataset in store.eval_datasets.values() if dataset["tenantId"] == ctx.tenant_id]
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/datasets")
    async def evaluation_dataset_create(
        payload: EvaluationDatasetCreateDto,
        ctx: Any = Depends(require_permissions("PERM_EVAL_WRITE")),
    ) -> dict[str, Any]:
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
    async def evaluation_run(
        payload: EvaluationRunRequestDto,
        ctx: Any = Depends(require_permissions("PERM_EVAL_READ")),
    ) -> dict[str, Any]:
        if evaluation_repository is not None:
            run = await create_persisted_eval_run(
                evaluation_repository,
                store,
                ctx,
                payload,
                settings,
                ingestion_repository,
                graph_repository,
                vector_store,
            )
            return ok(run, trace_id=ctx.trace_id)
        return ok(create_eval_run(store, ctx, payload), trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/datasets/{datasetId}/runs")
    async def evaluation_dataset_run(
        datasetId: str,
        payload: EvaluationRunRequestDto,
        ctx: Any = Depends(require_permissions("PERM_EVAL_READ")),
    ) -> dict[str, Any]:
        request_payload = EvaluationRunRequestDto(datasetId=datasetId, modelProfile=payload.modelProfile)
        if evaluation_repository is not None:
            run = await create_persisted_eval_run(
                evaluation_repository,
                store,
                ctx,
                request_payload,
                settings,
                ingestion_repository,
                graph_repository,
                vector_store,
            )
            return ok(run, trace_id=ctx.trace_id)
        dataset = store.eval_datasets.get(datasetId)
        if not dataset or dataset["tenantId"] != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="dataset not found")
        return ok(create_eval_run(store, ctx, request_payload), trace_id=ctx.trace_id)

    @app.get("/ai/evaluation/runs/{runId}")
    async def evaluation_run_get(runId: str, ctx: Any = Depends(require_permissions("PERM_EVAL_READ"))) -> dict[str, Any]:
        if evaluation_repository is not None:
            run = await evaluation_repository.get_run(ctx.tenant_id, runId)
            if run is None:
                raise HTTPException(status_code=404, detail="evaluation run not found")
            return ok(run, trace_id=ctx.trace_id)
        return ok(require_eval_run(store, ctx, runId), trace_id=ctx.trace_id)

    @app.post("/ai/evaluation/runs/{runId}/baseline")
    async def evaluation_run_baseline(
        runId: str,
        ctx: Any = Depends(require_permissions("PERM_EVAL_WRITE")),
    ) -> dict[str, Any]:
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
        ctx: Any = Depends(require_permissions("PERM_EVAL_READ")),
    ) -> dict[str, Any]:
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
    async def evaluation_report(
        runId: str,
        ctx: Any = Depends(require_permissions("PERM_EVAL_READ")),
    ) -> PlainTextResponse:
        if evaluation_repository is not None:
            run = await evaluation_repository.get_run(ctx.tenant_id, runId)
            if run is None:
                raise HTTPException(status_code=404, detail="evaluation run not found")
            return evaluation_report_response(run)
        return evaluation_report_response(require_eval_run(store, ctx, runId))
