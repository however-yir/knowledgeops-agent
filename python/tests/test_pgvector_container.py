from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from docker.errors import DockerException
from testcontainers.postgres import PostgresContainer

from alembic import command


def test_pgvector_alembic_migration_creates_projection_extension_and_indexes(monkeypatch) -> None:
    monkeypatch.setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
    try:
        with PostgresContainer("pgvector/pgvector:pg16", username="postgres", password="postgres", dbname="knowledgeops") as container:
            database_url = container.get_connection_url(driver="asyncpg")
            monkeypatch.setenv("APP_DATABASE_URL", database_url)
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            command.upgrade(config, "head")

            async def verify() -> None:
                connection = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
                try:
                    assert await connection.fetchval("SELECT extname FROM pg_extension WHERE extname = 'vector'") == "vector"
                    assert await connection.fetchval("SELECT to_regclass('public.py_pgvector_chunks')") == "py_pgvector_chunks"
                    indexes = {
                        record["indexname"]
                        for record in await connection.fetch(
                            "SELECT indexname FROM pg_indexes WHERE tablename = 'py_pgvector_chunks'"
                        )
                    }
                    assert {"ix_py_pgvector_chunks_tenant_chat", "ix_py_pgvector_chunks_embedding_hnsw"} <= indexes
                finally:
                    await connection.close()

            asyncio.run(verify())
    except DockerException as exc:
        detail = str(exc)
        if not os.getenv("CI") and (
            "registry-1.docker.io" in detail or "No such image: pgvector/pgvector:pg16" in detail
        ):
            pytest.skip("Docker Hub is unavailable for the local pgvector Testcontainer")
        raise
