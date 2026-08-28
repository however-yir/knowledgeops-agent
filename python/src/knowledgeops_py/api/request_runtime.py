"""Authentication context, trace, and rate-limit helpers for HTTP runtime."""

from __future__ import annotations

import ipaddress
import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

from knowledgeops_py.application.security import bearer_token
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.runtime import PlatformStore, RequestContext
from knowledgeops_py.infrastructure.rate_limit import RateLimitUnavailable, shared_token_bucket

TENANT_HEADER = "x-tenant-id"
API_KEY_HEADER = "x-api-key"
AUTH_HEADER = "authorization"

# Mirrors the Java RateLimitFilter hard cap on in-process buckets.
MAX_IN_MEMORY_RATE_LIMIT_KEYS = 50_000

ANONYMOUS_PRINCIPAL = "anonymous"
ANONYMOUS_TENANT = "public"


async def resolve_context(request: Request, auth_service: Any, allow_anonymous: bool) -> RequestContext:
    trace_id = ensure_trace_id(request)
    tenant_header = request.headers.get(TENANT_HEADER)
    tenant_id = str(tenant_header or ANONYMOUS_TENANT).strip().lower() or ANONYMOUS_TENANT
    identity = await auth_service.resolve_identity(
        bearer_token(request.headers.get(AUTH_HEADER)), request.headers.get(API_KEY_HEADER)
    )
    if identity:
        # The authenticated tenant is authoritative; the header may only echo
        # it (case-insensitively), never override it.
        if tenant_header and identity.tenant_id.lower() != tenant_id:
            raise HTTPException(status_code=403, detail="tenant mismatch")
        return RequestContext(trace_id, identity.tenant_id, identity.principal, identity.roles, identity.permissions, identity.auth_source)
    if not allow_anonymous:
        raise HTTPException(status_code=401, detail="authentication required")
    return RequestContext(trace_id, tenant_id, ANONYMOUS_PRINCIPAL, ["ANONYMOUS"], [], ANONYMOUS_PRINCIPAL)


def ensure_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    if not trace_id:
        trace_id = request.headers.get("x-request-id") or f"trace_{uuid4().hex}"
        request.state.trace_id = trace_id
    return trace_id


def _ip_is_internal(text: str) -> bool:
    """Best-effort textual classification. Parse failures (hostnames) count as
    external, mirroring the Java guard which never resolves DNS for XFF hops."""
    try:
        parsed = ipaddress.ip_address(text.strip())
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified or parsed.is_private


def _rightmost_public_hop(forwarded_for: str) -> str | None:
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _ip_is_internal(hop):
            return hop
    return None


def resolve_client_ip(request: Request) -> str:
    """Resolve the client IP for rate limiting, safe behind reverse proxies.

    Mirrors the Java fix (main a373082, bug 16): X-Forwarded-For is honored
    only when the direct peer is itself private/loopback (i.e. we actually sit
    behind a proxy), and the rightmost non-internal hop wins because proxies
    overwrite the values to their left, so a client cannot forge it.
    """
    peer = request.client.host if request.client else ""
    if peer and not _ip_is_internal(peer):
        return peer
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hop = _rightmost_public_hop(forwarded)
        if hop:
            return hop
    return peer or "unknown"


def _rate_limit_key(ctx: RequestContext, request: Request) -> str:
    if ctx.principal == ANONYMOUS_PRINCIPAL:
        # Anonymous buckets must not be steerable via the tenant header: the
        # resolved client IP is the only stable, client-chosen-free dimension.
        return f"anonymous:ip:{resolve_client_ip(request)}"
    return f"{ctx.tenant_id}:{ctx.principal}"


async def enforce_rate_limit(store: PlatformStore, settings: Settings, ctx: RequestContext, request: Request) -> None:
    key = _rate_limit_key(ctx, request)
    if settings.is_production:
        try:
            allowed = await shared_token_bucket(settings.redis_url, settings.rate_limit_per_minute).allow(key)
        except RateLimitUnavailable as exc:
            raise HTTPException(status_code=503, detail="rate limiter unavailable") from exc
        if not allowed:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        return
    if len(store.rate_limits) > MAX_IN_MEMORY_RATE_LIMIT_KEYS:
        store.rate_limits.clear()
    now = time.time()
    window = [timestamp for timestamp in store.rate_limits.get(key, []) if now - timestamp < 60]
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    store.rate_limits[key] = [*window, now]


def should_rate_limit(path: str) -> bool:
    return not path.startswith(("/actuator", "/health", "/metrics", "/v3/api-docs"))
