"""RAG/PDF query and tenant-scoped source-file routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse

from knowledgeops_py.application.ingestion import IngestionApplicationService
from knowledgeops_py.dto import ChatRequestDto, RagEnvelope, RagResponseDto


def register_rag_routes(
    app: FastAPI,
    *,
    store: Any,
    settings: Any,
    ingestion_service: IngestionApplicationService | None,
    graph_repository: Any,
    session_repository: Any,
    vector_store: Any,
    memory_service: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    chat_request_payload: Callable[..., ChatRequestDto],
    rag_response_with_provider: Callable[..., Awaitable[RagResponseDto]],
) -> None:
    """Register Java-compatible evidence-grounded RAG and source-file endpoints."""

    @app.post("/ai/pdf/chat", response_model=RagEnvelope)
    async def pdf_chat(
        payload: ChatRequestDto | None = None,
        prompt: str | None = Query(default=None),
        chatId: str | None = Query(default=None),
        modelProfile: str | None = Query(default=None),
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        payload = chat_request_payload(payload, prompt, chatId, modelProfile)
        data = await rag_response_with_provider(
            store,
            ctx,
            payload,
            require_evidence=True,
            settings=settings,
            ingestion_repository=ingestion_service.repository if ingestion_service is not None else None,
            graph_repository=graph_repository,
            session_repository=session_repository,
            vector_store=vector_store,
            memory_service=memory_service,
        )
        return ok(data, trace_id=ctx.trace_id)

    # Java parity (a4f2565): the GET /ai/pdf/chat variant was removed and the
    # POST route is the single RAG answer surface gated by PERM_RAG_READ.

    @app.get("/ai/pdf/file/{chatId}")
    async def pdf_file(
        chatId: str,
        ctx: Any = Depends(require_permissions("PERM_RAG_READ")),
    ) -> PlainTextResponse:
        chunks = (
            await ingestion_service.repository.chunks(ctx.tenant_id, chatId)
            if ingestion_service is not None
            else [chunk for chunk in store.chunks if chunk["tenantId"] == ctx.tenant_id and chunk["chatId"] == chatId]
        )
        if not chunks:
            raise HTTPException(status_code=404, detail="file not found")
        return PlainTextResponse("\n".join(chunk["content"] for chunk in chunks), media_type="text/plain; charset=utf-8")
