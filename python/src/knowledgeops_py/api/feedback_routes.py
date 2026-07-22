"""Tenant-scoped feedback recording route."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI

from knowledgeops_py.dto import FeedbackRequestDto


def register_feedback_routes(
    app: FastAPI,
    *,
    store: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    now_iso: Callable[[], str],
) -> None:
    """Register the Java-compatible tenant-scoped feedback endpoint."""

    @app.post("/ai/feedback")
    def feedback(
        payload: FeedbackRequestDto,
        ctx: Any = Depends(require_permissions("PERM_FEEDBACK_WRITE")),
    ) -> dict[str, Any]:
        record = payload.model_dump() | {
            "tenantId": ctx.tenant_id,
            "principal": ctx.principal,
            "createdAt": now_iso(),
        }
        store.feedback.append(record)
        return ok(record, msg="saved", trace_id=ctx.trace_id)
