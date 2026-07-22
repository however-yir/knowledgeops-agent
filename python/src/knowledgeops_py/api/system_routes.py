"""System and observability routes registered with explicit application dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import PlainTextResponse


def register_system_routes(
    app: FastAPI,
    *,
    store: Any,
    ensure_trace_id: Callable[[Request], str],
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    prometheus_text: Callable[[Any], str],
) -> None:
    """Register Java-compatible health, metrics and OpenAPI endpoints."""

    @app.get("/actuator/health")
    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        return ok({"status": "UP", "service": "knowledgeops-agent-python"}, trace_id=ensure_trace_id(request))

    @app.get("/metrics")
    def metrics(request: Request, _ctx: object = Depends(require_permissions("PERM_METRICS_READ"))) -> dict[str, Any]:
        text = prometheus_text(store)
        return ok({"prometheus": text, "counters": store.metrics}, trace_id=ensure_trace_id(request))

    @app.get("/actuator/prometheus")
    def prometheus(_ctx: object = Depends(require_permissions("PERM_METRICS_READ"))) -> PlainTextResponse:
        return PlainTextResponse(prometheus_text(store), media_type="text/plain; version=0.0.4")

    @app.get("/v3/api-docs")
    def openapi_docs(request: Request) -> dict[str, Any]:
        return ok(app.openapi(), trace_id=ensure_trace_id(request))
