"""Memory expiry tests (Java parity d91405b: expires_at filtering)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from knowledgeops_py.infrastructure.database import create_engine, create_session_factory
from knowledgeops_py.infrastructure.memory_repository import SqlAlchemyMemoryRepository
from knowledgeops_py.infrastructure.models import Base


async def _repository() -> SqlAlchemyMemoryRepository:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return SqlAlchemyMemoryRepository(create_session_factory(engine))


def test_expired_memories_never_surface_in_list_or_recall() -> None:
    async def exercise() -> None:
        repository = await _repository()
        now = datetime.now(UTC)

        await repository.create("tenant-a", "alice", "expired fact", "fact", None, now - timedelta(minutes=5))
        await repository.create("tenant-a", "alice", "live fact", "fact", None, now + timedelta(days=7))
        await repository.create("tenant-a", "alice", "eternal fact", "fact", None, None)

        listed = await repository.list("tenant-a", "alice")
        contents = sorted(item["content"] for item in listed)
        assert contents == ["eternal fact", "live fact"]

        recalled = await repository.recall("tenant-a", "alice", "chat-1")
        assert sorted(item["content"] for item in recalled) == ["eternal fact", "live fact"]

        live = next(item for item in listed if item["content"] == "live fact")
        assert live["expiresAt"] is not None

    asyncio.run(exercise())
