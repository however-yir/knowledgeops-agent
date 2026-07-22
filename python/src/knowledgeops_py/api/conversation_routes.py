"""Chat, ReAct, streaming, and HTML compatibility routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import PlainTextResponse

from knowledgeops_py.dto import ChatEnvelope, ChatRequestDto, ChatResponseDto


def register_conversation_routes(
    app: FastAPI,
    *,
    store: Any,
    settings: Any,
    session_repository: Any,
    memory_service: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    is_legacy_request: Callable[[Request], bool],
    chat_request_payload: Callable[..., ChatRequestDto],
    chat_response_with_provider: Callable[..., Awaitable[ChatResponseDto]],
    to_sse: Callable[..., str],
    to_sse_error: Callable[..., str],
) -> None:
    """Register Java-compatible chat and ReAct HTTP/SSE endpoints."""

    @app.post("/ai/chat", response_model=ChatEnvelope)
    async def ai_chat(
        request: Request,
        payload: ChatRequestDto | None = None,
        prompt: str | None = Query(default=None),
        chatId: str | None = Query(default=None),
        modelProfile: str | None = Query(default=None),
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        payload = chat_request_payload(payload, prompt, chatId, modelProfile)
        data = await chat_response_with_provider(
            store,
            ctx,
            payload,
            mode="chat",
            require_evidence=False,
            settings=settings,
            session_repository=session_repository,
            memory_service=memory_service,
        )
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/chat/stream")
    async def ai_chat_stream(
        request: Request,
        payload: ChatRequestDto | None = None,
        prompt: str | None = Query(default=None),
        chatId: str | None = Query(default=None),
        modelProfile: str | None = Query(default=None),
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ):
        payload = chat_request_payload(payload, prompt, chatId, modelProfile)
        data = await chat_response_with_provider(
            store,
            ctx,
            payload,
            mode="chat",
            require_evidence=False,
            settings=settings,
            session_repository=session_repository,
            memory_service=memory_service,
        )
        if not is_legacy_request(request):
            return PlainTextResponse(f"data: {data.answer}\n\n", media_type="text/event-stream")
        return PlainTextResponse(to_sse(data, ctx.trace_id, legacy=True), media_type="text/event-stream")

    @app.post("/ai/react/chat", response_model=ChatEnvelope)
    async def react_chat(
        payload: ChatRequestDto,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        data = await chat_response_with_provider(
            store,
            ctx,
            payload,
            mode="react",
            require_evidence=False,
            settings=settings,
            session_repository=session_repository,
            memory_service=memory_service,
        )
        return ok(data, trace_id=ctx.trace_id)

    @app.post("/ai/react/chat/stream")
    async def react_chat_stream(
        request: Request,
        payload: ChatRequestDto,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ):
        legacy = is_legacy_request(request)
        try:
            data = await chat_response_with_provider(
                store,
                ctx,
                payload,
                mode="react",
                require_evidence=False,
                settings=settings,
                session_repository=session_repository,
                memory_service=memory_service,
            )
        except Exception as exc:
            return PlainTextResponse(to_sse_error(exc, ctx.trace_id, legacy), media_type="text/event-stream")
        return PlainTextResponse(
            to_sse(data, ctx.trace_id, legacy=legacy, react=True), media_type="text/event-stream"
        )

    @app.get("/ai/chat")
    @app.get("/ai/service")
    async def html_chat(
        prompt: str = Query(..., min_length=1),
        chatId: str = Query(default="default"),
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ):
        response = await chat_response_with_provider(
            store,
            ctx,
            ChatRequestDto(chatId=chatId, prompt=prompt),
            mode="chat",
            require_evidence=False,
            settings=settings,
            session_repository=session_repository,
            memory_service=memory_service,
        )
        return PlainTextResponse(response.answer, media_type="text/html; charset=utf-8")
