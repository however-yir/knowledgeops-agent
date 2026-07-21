from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from .context import TenantContext


class ChatProvider(Protocol):
    async def complete(self, context: TenantContext, prompt: str, model_profile: str) -> dict[str, Any]: ...


class EmbeddingProvider(Protocol):
    async def embed(self, context: TenantContext, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    async def rank(self, context: TenantContext, query: str, documents: list[str]) -> list[float]: ...


class VectorStore(Protocol):
    async def search(self, context: TenantContext, chat_id: str, query: str, limit: int) -> list[dict[str, Any]]: ...


class IngestionQueue(Protocol):
    async def publish(self, context: TenantContext, job_id: str) -> None: ...

    async def publish_dead_letter(self, context: TenantContext, job_id: str, reason: str) -> None: ...

    async def consume(self) -> AsyncIterator[str]: ...


class ToolRuntime(Protocol):
    async def preview(self, context: TenantContext, action: str, action_input: dict[str, Any]) -> dict[str, Any]: ...

    async def execute(self, context: TenantContext, token: str) -> dict[str, Any]: ...
