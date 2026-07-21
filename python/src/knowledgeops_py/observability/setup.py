from __future__ import annotations

import logging

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def configure_observability(service_name: str) -> trace.Tracer:
    """Install a resource-scoped tracer once and return the service tracer."""
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        trace.set_tracer_provider(TracerProvider(resource=Resource.create({"service.name": service_name})))
    structlog.configure(
        processors=[structlog.processors.add_log_level, structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.getLogger("uvicorn.access").handlers.clear()
    return trace.get_tracer(service_name)
