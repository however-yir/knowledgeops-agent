"""Native pgvector projection used by the Python RAG path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from knowledgeops_py.domain.context import TenantContext


@dataclass(frozen=True, slots=True)
class PgVectorProjection:
    database_url: str

    async def upsert(self, chunks: list[dict[str, Any]]) -> None:
        rows = [
            (
                str(chunk["chunk_id"]),
                str(chunk["tenant_id"]),
                str(chunk["chat_id"]),
                str(chunk["source_name"]),
                int(chunk["chunk_index"]),
                str(chunk["content"]),
                vector_literal(chunk["embedding"]),
            )
            for chunk in chunks
            if chunk.get("embedding")
        ]
        if not rows:
            return
        connection = await asyncpg.connect(asyncpg_url(self.database_url))
        try:
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
        finally:
            await connection.close()

    async def search(self, context: TenantContext, chat_id: str, embedding: list[float], limit: int) -> list[dict[str, Any]]:
        connection = await asyncpg.connect(asyncpg_url(self.database_url))
        try:
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
                vector_literal(embedding),
                max(1, limit),
            )
            return [dict(record) for record in records]
        finally:
            await connection.close()


def asyncpg_url(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def vector_literal(values: Any) -> str:
    if not isinstance(values, list) or not values:
        raise ValueError("pgvector embedding must be a non-empty list")
    return "[" + ",".join(str(float(value)) for value in values) + "]"
