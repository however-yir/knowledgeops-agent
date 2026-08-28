"""Native pgvector projection used by the Python RAG path."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from knowledgeops_py.domain.context import TenantContext


@dataclass(frozen=True, slots=True)
class PgVectorProjection:
    database_url: str
    dimensions: int = 1024
    _pool: Any = field(default=None, compare=False, repr=False)
    _pool_lock: Any = field(default_factory=asyncio.Lock, compare=False, repr=False)

    async def _connection_pool(self) -> Any:
        # Java parity (a373082): replace per-operation connections with a
        # bounded pool so retrieval does not open a fresh TCP connection on
        # every search.
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    object.__setattr__(
                        self,
                        "_pool",
                        await asyncpg.create_pool(asyncpg_url(self.database_url), min_size=1, max_size=4),
                    )
        return self._pool

    async def upsert(self, chunks: list[dict[str, Any]]) -> None:
        rows = [
            (
                str(chunk["chunk_id"]),
                str(chunk["tenant_id"]),
                str(chunk["chat_id"]),
                str(chunk["source_name"]),
                int(chunk["chunk_index"]),
                str(chunk["content"]),
                vector_literal(chunk["embedding"], self.dimensions),
            )
            for chunk in chunks
            if chunk.get("embedding")
        ]
        if not rows:
            return
        try:
            pool = await self._connection_pool()
            async with pool.acquire() as connection:
                await connection.executemany(
                    """
                    INSERT INTO py_pgvector_chunks
                        (chunk_id, tenant_id, chat_id, source_name, chunk_index, content, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        chat_id = EXCLUDED.chat_id,
                        source_name = EXCLUDED.source_name,
                        chunk_index = EXCLUDED.chunk_index,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                    """,
                    rows,
                )
        except (OSError, asyncpg.PostgresError) as exc:
            raise VectorStoreUnavailable("pgvector upsert failed") from exc

    async def search(self, context: TenantContext, chat_id: str, embedding: list[float], limit: int) -> list[dict[str, Any]]:
        try:
            pool = await self._connection_pool()
            async with pool.acquire() as connection:
                records = await connection.fetch(
                    """
                    SELECT chunk_id, tenant_id, chat_id, source_name, chunk_index, content,
                           1 - (embedding <=> $3::vector) AS score
                    FROM py_pgvector_chunks
                    WHERE tenant_id = $1 AND chat_id = $2
                    ORDER BY embedding <=> $3::vector
                    LIMIT $4
                    """,
                    context.tenant_id,
                    chat_id,
                    vector_literal(embedding, self.dimensions),
                    max(1, limit),
                )
                return [dict(record) for record in records]
        except (OSError, asyncpg.PostgresError) as exc:
            raise VectorStoreUnavailable("pgvector search failed") from exc


def asyncpg_url(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def vector_literal(values: Any, dimensions: int | None = None) -> str:
    if not isinstance(values, list) or not values:
        raise ValueError("pgvector embedding must be a non-empty list")
    if dimensions is not None and len(values) != dimensions:
        raise ValueError(f"pgvector embedding must have {dimensions} dimensions")
    return "[" + ",".join(str(float(value)) for value in values) + "]"


class VectorStoreUnavailable(RuntimeError):
    """The configured vector database could not complete an operation."""
