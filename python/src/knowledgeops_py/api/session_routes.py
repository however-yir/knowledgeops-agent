"""Session, history, and branch routes backed by the existing session services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from knowledgeops_py.application.sessions import (
    SessionBranchValidationError,
    compare_session_branches,
    java_session_payload,
    merge_session_branches,
)
from knowledgeops_py.dto import SessionDto


def register_session_routes(
    app: FastAPI,
    *,
    store: Any,
    session_repository: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    get_or_create_session: Callable[..., dict[str, Any]],
    require_session: Callable[..., dict[str, Any]],
    session_not_found_status: Callable[[Request], int],
    session_not_found: Callable[[Request], HTTPException],
    now_iso: Callable[[], str],
    page_data: Callable[[list[dict[str, Any]], int, int], dict[str, Any]],
) -> None:
    """Register Java-compatible tenant-scoped session and history endpoints."""

    @app.get("/ai/sessions")
    async def sessions(ctx: Any = Depends(require_permissions("PERM_SESSION_READ"))) -> dict[str, Any]:
        if session_repository is not None:
            return ok(await session_repository.list(ctx.tenant_id), trace_id=ctx.trace_id)
        data = [SessionDto(**session).model_dump() for session in store.sessions.values() if session["tenantId"] == ctx.tenant_id]
        return ok(data, trace_id=ctx.trace_id)

    @app.get("/ai/sessions/{sessionId}")
    async def session(
        sessionId: str,
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_SESSION_READ")),
    ) -> dict[str, Any]:
        if session_repository is not None:
            data = await session_repository.get(ctx.tenant_id, sessionId)
            if data is None:
                raise session_not_found(request)
            return ok(data, trace_id=ctx.trace_id)
        data = (
            get_or_create_session(store, ctx, sessionId, chat_id=sessionId)
            if is_legacy_request(request)
            else require_session(store, ctx, sessionId, session_not_found_status(request))
        )
        return ok(SessionDto(**data), trace_id=ctx.trace_id)

    @app.get("/ai/history/{kind}")
    async def history_list(
        kind: str,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=20, ge=1, le=200),
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any]:
        if session_repository is not None:
            return ok(page_data(await session_repository.list(ctx.tenant_id), page, pageSize), trace_id=ctx.trace_id)
        sessions_for_tenant = [item for item in store.sessions.values() if item["tenantId"] == ctx.tenant_id]
        return ok(page_data(sessions_for_tenant, page, pageSize), trace_id=ctx.trace_id)

    @app.get("/ai/history/{kind}/{chatId}")
    async def history_messages(
        kind: str,
        chatId: str,
        page: int = Query(default=1, ge=1),
        pageSize: int = Query(default=50, ge=1, le=200),
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any]:
        if session_repository is not None:
            session_data = await session_repository.get(ctx.tenant_id, chatId)
            return ok(page_data(session_data["messages"] if session_data else [], page, pageSize), trace_id=ctx.trace_id)
        session_data = store.sessions.get(chatId)
        messages = session_data["messages"] if session_data and session_data["tenantId"] == ctx.tenant_id else []
        return ok(page_data(messages, page, pageSize), trace_id=ctx.trace_id)

    @app.put("/ai/sessions/{sessionId}")
    async def session_upsert(
        sessionId: str,
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_SESSION_WRITE")),
    ) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="session payload is required")
        legacy = is_legacy_request(request)
        if not legacy:
            payload = java_session_payload(sessionId, payload)
        if session_repository is not None:
            saved = await session_repository.upsert(ctx.tenant_id, sessionId, payload)
            if saved is None:
                raise session_not_found(request)
            return ok(saved, trace_id=ctx.trace_id)
        existing = get_or_create_session(store, ctx, sessionId, str(payload.get("chatId") or sessionId))
        if legacy:
            for attribute in ("title", "chatId", "modelProfile", "workspace", "pinned", "archived"):
                if attribute in payload:
                    existing[attribute] = payload[attribute]
        else:
            existing.update(payload)
        existing["updatedAt"] = now_iso()
        return ok(existing, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/pin")
    async def session_pin(
        sessionId: str,
        request: Request,
        value: bool = Query(...),
        ctx: Any = Depends(require_permissions("PERM_SESSION_WRITE")),
    ) -> dict[str, Any]:
        if session_repository is not None:
            saved = await session_repository.set_flag(ctx.tenant_id, sessionId, "pinned", value)
            if saved is None:
                raise session_not_found(request)
            return ok(saved, trace_id=ctx.trace_id)
        session_data = require_session(store, ctx, sessionId, session_not_found_status(request))
        session_data["pinned"] = value
        session_data["updatedAt"] = now_iso()
        return ok(session_data, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/archive")
    async def session_archive(
        sessionId: str,
        request: Request,
        value: bool = Query(...),
        ctx: Any = Depends(require_permissions("PERM_SESSION_WRITE")),
    ) -> dict[str, Any]:
        if session_repository is not None:
            saved = await session_repository.set_flag(ctx.tenant_id, sessionId, "archived", value)
            if saved is None:
                raise session_not_found(request)
            return ok(saved, trace_id=ctx.trace_id)
        session_data = require_session(store, ctx, sessionId, session_not_found_status(request))
        session_data["archived"] = value
        session_data["updatedAt"] = now_iso()
        return ok(session_data, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/branches/compare")
    async def session_compare(
        sessionId: str,
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_SESSION_READ")),
    ) -> dict[str, Any]:
        session_data = (
            await session_repository.get(ctx.tenant_id, sessionId)
            if session_repository is not None
            else require_session(store, ctx, sessionId, session_not_found_status(request))
        )
        if session_data is None:
            raise session_not_found(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="compare request is required")
        try:
            comparison = compare_session_branches(session_data, payload.get("sourceBranchId"), payload.get("targetBranchId"))
        except SessionBranchValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ok(comparison, trace_id=ctx.trace_id)

    @app.post("/ai/sessions/{sessionId}/branches/merge")
    async def session_merge(
        sessionId: str,
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_SESSION_WRITE")),
    ) -> dict[str, Any]:
        session_data = (
            await session_repository.get(ctx.tenant_id, sessionId)
            if session_repository is not None
            else require_session(store, ctx, sessionId, session_not_found_status(request))
        )
        if session_data is None:
            raise session_not_found(request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="merge request is required")
        try:
            merged_session, merged_branch = merge_session_branches(
                session_data,
                payload.get("sourceBranchId"),
                payload.get("targetBranchId"),
                payload.get("title"),
            )
        except SessionBranchValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if session_repository is not None:
            saved = await session_repository.upsert(ctx.tenant_id, sessionId, merged_session)
            if saved is None:
                raise session_not_found(request)
        else:
            store.sessions[sessionId] = merged_session
            saved = merged_session
        return ok(
            {
                "session": saved,
                "mergedBranch": merged_branch,
                "mergedMessageCount": len(merged_branch["messages"]),
            },
            trace_id=ctx.trace_id,
        )
