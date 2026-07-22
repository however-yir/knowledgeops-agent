"""Authentication routes backed by the authentication application service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, Query, Request

from knowledgeops_py.application.authentication import AuthApplicationService, AuthenticationError


def register_auth_routes(
    app: FastAPI,
    *,
    auth_service: AuthApplicationService,
    ensure_trace_id: Callable[[Request], str],
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    fail: Callable[[str, str, str], dict[str, Any]],
) -> None:
    """Register Java-compatible authentication endpoints."""

    @app.post("/auth/token")
    async def auth_token(
        request: Request,
        x_api_key: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            data = await auth_service.issue_token(x_api_key, x_tenant_id)
        except AuthenticationError as exc:
            return fail(exc.message, exc.code, ensure_trace_id(request))
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/refresh")
    async def auth_refresh(request: Request, x_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
        try:
            data = await auth_service.refresh(x_refresh_token)
        except AuthenticationError as exc:
            return fail(exc.message, exc.code, ensure_trace_id(request))
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys")
    async def auth_api_keys(
        request: Request,
        keyName: str = Query(..., min_length=1, max_length=120),
        role: str = Query(default="USER"),
        ctx: Any = Depends(require_permissions("PERM_AUTH_KEY_MANAGE")),
    ) -> dict[str, Any]:
        return ok(await auth_service.issue_api_key(keyName, role, ctx.tenant_id), trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys/rotate")
    async def auth_api_key_rotate(
        request: Request,
        keyName: str = Query(..., min_length=1, max_length=120),
        reason: str = Query(default="rotation", max_length=240),
        ctx: Any = Depends(require_permissions("PERM_AUTH_KEY_MANAGE")),
    ) -> dict[str, Any]:
        return ok(await auth_service.rotate_api_key(keyName, reason, ctx.tenant_id), msg="rotated", trace_id=ensure_trace_id(request))

    @app.post("/auth/api-keys/revoke")
    async def auth_api_key_revoke(
        request: Request,
        keyName: str = Query(..., min_length=1, max_length=120),
        reason: str = Query(default="manual revoke", max_length=240),
        ctx: Any = Depends(require_permissions("PERM_AUTH_KEY_MANAGE")),
    ) -> dict[str, Any]:
        await auth_service.revoke_api_key(keyName, reason, ctx.tenant_id)
        return ok({"keyName": keyName, "tenantId": ctx.tenant_id}, msg="revoked", trace_id=ensure_trace_id(request))

    @app.get("/auth/oidc/login")
    async def oidc_login(request: Request, returnTo: str | None = Query(default=None, max_length=2048)) -> dict[str, Any]:
        return ok(await auth_service.begin_oidc_login(returnTo), trace_id=ensure_trace_id(request))

    @app.get("/auth/oidc/callback")
    async def oidc_callback(
        request: Request,
        code: str = Query(..., min_length=1),
        state: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        return ok(await auth_service.complete_oidc_callback(code, state), trace_id=ensure_trace_id(request))

    @app.post("/auth/oidc/exchange")
    async def oidc_exchange(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            data = await auth_service.exchange_oidc_code(str(payload.get("exchangeCode", "")))
        except AuthenticationError as exc:
            return fail(exc.message, exc.code, ensure_trace_id(request))
        return ok(data, trace_id=ensure_trace_id(request))

    @app.post("/auth/logout")
    async def logout(request: Request, x_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
        await auth_service.logout(x_refresh_token)
        return ok({"loggedOut": True}, trace_id=ensure_trace_id(request))
