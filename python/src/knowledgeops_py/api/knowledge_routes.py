"""Tenant-scoped memory and knowledge-graph routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request


def register_knowledge_routes(
    app: FastAPI,
    *,
    store: Any,
    memory_repository: Any,
    graph_repository: Any,
    require_permissions: Callable[..., Callable[..., Any]],
    ok: Callable[..., dict[str, Any]],
    new_id: Callable[[str], str],
    now_iso: Callable[[], str],
    bounded: Callable[[int, int, int], int],
    tokenize: Callable[[str], list[str]],
    optional_payload_text: Callable[[Any], str | None],
    parse_optional_date: Callable[[Any], date | None],
) -> None:
    """Register Java-compatible memory and graph persistence endpoints."""

    @app.post("/ai/memory/items")
    async def memory_create(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        payload = await request.json()
        content = str(payload.get("content", "")).strip()
        if not content:
            raise HTTPException(status_code=422, detail="memory content is required")
        raw_expires_at = payload.get("expiresAt")
        expires_at: datetime | None = None
        if raw_expires_at:
            try:
                expires_at = datetime.fromisoformat(str(raw_expires_at))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="expiresAt must be an ISO-8601 timestamp") from exc
        if memory_repository is not None:
            item = await memory_repository.create(
                ctx.tenant_id,
                ctx.principal,
                content,
                str(payload.get("type") or "fact"),
                payload.get("sessionId"),
                expires_at,
            )
            return ok(item, trace_id=ctx.trace_id)
        item = {
            "memoryId": new_id("mem"),
            "tenantId": ctx.tenant_id,
            "principal": ctx.principal,
            "sessionId": payload.get("sessionId"),
            "type": str(payload.get("type") or "fact"),
            "content": content,
            "expiresAt": expires_at.isoformat() if expires_at else None,
            "createdAt": now_iso(),
        }
        store.memories[item["memoryId"]] = item
        return ok(item, trace_id=ctx.trace_id)

    @app.get("/ai/memory/items")
    async def memory_list(
        sessionId: str | None = None,
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any]:
        if memory_repository is not None:
            return ok(await memory_repository.list(ctx.tenant_id, ctx.principal, sessionId), trace_id=ctx.trace_id)
        items = [
            item
            for item in store.memories.values()
            if item["tenantId"] == ctx.tenant_id
            and item["principal"] == ctx.principal
            and (not sessionId or item.get("sessionId") == sessionId)
        ]
        return ok(items, trace_id=ctx.trace_id)

    @app.get("/ai/memory/context")
    async def memory_context(
        prompt: str,
        sessionId: str | None = None,
        ctx: Any = Depends(require_permissions("PERM_CHAT_READ")),
    ) -> dict[str, Any]:
        tokens = set(tokenize(prompt))
        items = (
            await memory_repository.list(ctx.tenant_id, ctx.principal, sessionId)
            if memory_repository is not None
            else [
                item
                for item in store.memories.values()
                if item["tenantId"] == ctx.tenant_id
                and item["principal"] == ctx.principal
                and (not sessionId or item.get("sessionId") == sessionId)
            ]
        )
        matched = [item for item in items if tokens.intersection(tokenize(item["content"]))]
        return ok(matched[:10], trace_id=ctx.trace_id)

    @app.get("/ai/graph/entities")
    async def graph_entities(
        query: str = "",
        entityType: str | None = Query(default=None),
        limit: int = Query(default=100),
        ctx: Any = Depends(require_permissions("PERM_RAG_READ")),
    ) -> dict[str, Any]:
        if graph_repository is not None:
            return ok(
                await graph_repository.list_entities(ctx.tenant_id, query, entityType, bounded(limit, 1, 200)),
                trace_id=ctx.trace_id,
            )
        return ok([item for item in store.graph_entities.values() if item["tenantId"] == ctx.tenant_id], trace_id=ctx.trace_id)

    @app.post("/ai/graph/entities")
    async def graph_entity_create(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        payload = await request.json()
        name = str(payload.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=422, detail="entity name is required")
        if graph_repository is not None:
            aliases = payload.get("aliases")
            return ok(
                await graph_repository.create_entity(
                    ctx.tenant_id,
                    name,
                    str(payload.get("type") or "CONCEPT"),
                    [str(item) for item in aliases] if isinstance(aliases, list) else [],
                    optional_payload_text(payload.get("description")),
                    optional_payload_text(payload.get("sourceId")),
                    payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                ),
                trace_id=ctx.trace_id,
            )
        entity = {
            "entityId": new_id("entity"),
            "tenantId": ctx.tenant_id,
            "name": name,
            "type": str(payload.get("type") or "CONCEPT"),
            "createdAt": now_iso(),
        }
        store.graph_entities[entity["entityId"]] = entity
        return ok(entity, trace_id=ctx.trace_id)

    @app.post("/ai/graph/relations")
    async def graph_relation_create(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        payload = await request.json()
        source_entity_id = str(payload.get("sourceEntityId", "")).strip()
        target_entity_id = str(payload.get("targetEntityId", "")).strip()
        if not source_entity_id or not target_entity_id:
            raise HTTPException(status_code=422, detail="sourceEntityId and targetEntityId are required")
        if graph_repository is None:
            raise HTTPException(status_code=503, detail="graph persistence is unavailable")
        relation = await graph_repository.create_relation(
            ctx.tenant_id,
            source_entity_id,
            target_entity_id,
            str(payload.get("relationType") or "RELATED_TO"),
            optional_payload_text(payload.get("evidenceId")),
            float(payload.get("weight", 1.0)),
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        if relation is None:
            raise HTTPException(status_code=404, detail="graph entity not found")
        return ok(relation, trace_id=ctx.trace_id)

    @app.get("/ai/graph/entities/{entityId}/neighbors")
    async def graph_neighbors(
        entityId: str,
        ctx: Any = Depends(require_permissions("PERM_RAG_READ")),
    ) -> dict[str, Any]:
        if graph_repository is None:
            raise HTTPException(status_code=503, detail="graph persistence is unavailable")
        neighbors = await graph_repository.neighbors(ctx.tenant_id, entityId)
        if neighbors is None:
            raise HTTPException(status_code=404, detail="graph entity not found")
        return ok(neighbors, trace_id=ctx.trace_id)

    @app.post("/ai/graph/facts")
    async def graph_fact_create(
        request: Request,
        ctx: Any = Depends(require_permissions("PERM_CHAT_WRITE")),
    ) -> dict[str, Any]:
        payload = await request.json()
        subject = str(payload.get("subject", "")).strip()
        predicate = str(payload.get("predicate", "")).strip()
        object_value = str(payload.get("object", "")).strip()
        if not subject or not predicate or not object_value:
            raise HTTPException(status_code=422, detail="subject, predicate, and object are required")
        if graph_repository is None:
            raise HTTPException(status_code=503, detail="graph persistence is unavailable")
        return ok(
            await graph_repository.create_fact(
                ctx.tenant_id,
                subject,
                predicate,
                object_value,
                float(payload.get("confidence", 0.8)),
                optional_payload_text(payload.get("source")),
                parse_optional_date(payload.get("validFrom")),
                parse_optional_date(payload.get("validTo")),
                payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            ),
            trace_id=ctx.trace_id,
        )

    @app.get("/ai/graph/facts")
    async def graph_facts(
        query: str = "",
        limit: int = Query(default=100),
        ctx: Any = Depends(require_permissions("PERM_RAG_READ")),
    ) -> dict[str, Any]:
        if graph_repository is not None:
            return ok(
                await graph_repository.search_facts(ctx.tenant_id, query, bounded(limit, 1, 200)),
                trace_id=ctx.trace_id,
            )
        query_tokens = set(tokenize(query))
        facts = [
            fact
            for fact in store.graph_facts
            if fact["tenantId"] == ctx.tenant_id
            and (not query_tokens or query_tokens.intersection(tokenize(json.dumps(fact, ensure_ascii=False))))
        ]
        return ok(facts, trace_id=ctx.trace_id)
