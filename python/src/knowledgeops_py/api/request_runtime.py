"""Authentication context, trace, and rate-limit helpers for HTTP runtime."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

from knowledgeops_py.application.security import bearer_token
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.runtime import PlatformStore, RequestContext
from knowledgeops_py.infrastructure.rate_limit import RateLimitUnavailable, RedisTokenBucket

TENANT_HEADER = "x-tenant-id"
API_KEY_HEADER = "x-api-key"
AUTH_HEADER = "authorization"


async def resolve_context(request: Request, auth_service: Any, allow_anonymous: bool) -> RequestContext:
    trace_id = ensure_trace_id(request)
    tenant_header = request.headers.get(TENANT_HEADER)
    tenant_id = str(tenant_header or "public").strip().lower() or "public"
    identity = await auth_service.resolve_identity(
        bearer_token(request.headers.get(AUTH_HEADER)), request.headers.get(API_KEY_HEADER)
    )
    if identity:
        if tenant_header and identity.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")
        return RequestContext(trace_id, identity.tenant_id, identity.principal, identity.roles, identity.permissions, identity.auth_source)
    if not allow_anonymous:
        raise HTTPException(status_code=401, detail="authentication required")
    return RequestContext(trace_id, tenant_id, "anonymous", ["ANONYMOUS"], [], "anonymous")


def ensure_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = request.headers.get("x-request-id") or f"trace_{uuid4().hex}"
        request.state.trace_id = trace_id
    return trace_id


async def enforce_rate_limit(store: PlatformStore, settings: Settings, ctx: RequestContext) -> None:
    key = f"{ctx.tenant_id}:{ctx.principal}"
    if settings.is_production:
        try:
            allowed = await RedisTokenBucket(settings.redis_url, settings.rate_limit_per_minute).allow(key)
        except RateLimitUnavailable as exc:
            raise HTTPException(status_code=503, detail="rate limiter unavailable") from exc
        if not allowed:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        return
    now = time.time()
    window = [timestamp for timestamp in store.rate_limits.get(key, []) if now - timestamp < 60]
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    store.rate_limits[key] = [*window, now]


def should_rate_limit(path: str) -> bool:
    return not path.startswith(("/actuator", "/health", "/metrics", "/v3/api-docs"))
