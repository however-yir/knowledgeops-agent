"""Audit and cost routes backed by the existing operations services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Query

from knowledgeops_py.dto import AuditLogDto, AuditLogsEnvelope, BudgetUpdateDto, CostEnvelope


def register_operations_routes(
    app: FastAPI,
    *,
    store: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    bounded: Callable[[int, int, int], int],
    now_iso: Callable[[], str],
    select_audit_fields: Callable[[dict[str, Any]], dict[str, Any]],
    cost_summary_data: Callable[[Any, str], dict[str, Any]],
) -> None:
    """Register Java-compatible tenant-scoped audit and cost endpoints."""

    @app.get("/audit/logs", response_model=AuditLogsEnvelope)
    def audit_logs(ctx: Any = Depends(require_permissions("PERM_AUDIT_READ")), limit: int = Query(default=50)) -> dict[str, Any]:
        logs = [AuditLogDto(**select_audit_fields(log)).model_dump() for log in store.audit_logs if log["tenantId"] == ctx.tenant_id]
        return ok(list(reversed(logs[-bounded(limit, 1, 200) :])), trace_id=ctx.trace_id)

    @app.get("/cost/summary", response_model=CostEnvelope)
    def cost_summary(ctx: Any = Depends(require_permissions("PERM_COST_READ"))) -> dict[str, Any]:
        return ok(cost_summary_data(store, ctx.tenant_id), trace_id=ctx.trace_id)

    @app.post("/cost/budget", response_model=CostEnvelope)
    def cost_budget(
        payload: BudgetUpdateDto,
        ctx: Any = Depends(require_permissions("PERM_COST_WRITE")),
    ) -> dict[str, Any]:
        previous = store.budgets.get(ctx.tenant_id, {})
        store.budgets[ctx.tenant_id] = {
            "tenantId": ctx.tenant_id,
            "monthlyBudgetUsd": payload.monthlyBudgetUsd,
            "hardLimitEnabled": payload.hardLimitEnabled if payload.hardLimitEnabled is not None else bool(previous.get("hardLimitEnabled", False)),
            "updatedAt": now_iso(),
        }
        return ok(cost_summary_data(store, ctx.tenant_id), msg="updated", trace_id=ctx.trace_id)
