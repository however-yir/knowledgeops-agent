"""Ingestion claim tenant-scoping tests (Java parity 0c64312)."""

from __future__ import annotations

import asyncio

from knowledgeops_py.infrastructure.database import create_engine, create_session_factory
from knowledgeops_py.infrastructure.ingestion_repository import SqlAlchemyIngestionRepository
from knowledgeops_py.infrastructure.models import Base, IngestionJobRecord


async def _repository() -> SqlAlchemyIngestionRepository:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return SqlAlchemyIngestionRepository(create_session_factory(engine))


def _record(job_id: str, tenant_id: str) -> IngestionJobRecord:
    return IngestionJobRecord(
        job_id=job_id,
        tenant_id=tenant_id,
        chat_id="chat-1",
        source_type="text",
        source_name="notes.txt",
        file_path="tenant-a/notes.txt",
        status="QUEUED",
        idempotency_key=f"idem-{job_id}",
        trace_id="trace-1",
    )


def test_claim_refuses_foreign_tenant_and_keeps_job_queued() -> None:
    async def exercise() -> None:
        repository = await _repository()
        await repository.create(_record("job-1", "tenant-a"))

        claimed = await repository.claim("job-1", "tenant-b")
        assert claimed is None

        job = await repository.get("tenant-a", "job-1")
        assert job is not None and job.status == "QUEUED"

        claimed = await repository.claim("job-1", "tenant-a")
        assert claimed is not None and claimed.status == "RUNNING"

    asyncio.run(exercise())


def test_claim_without_tenant_still_works_for_legacy_callers() -> None:
    async def exercise() -> None:
        repository = await _repository()
        await repository.create(_record("job-2", "tenant-a"))
        claimed = await repository.claim("job-2")
        assert claimed is not None and claimed.status == "RUNNING"

    asyncio.run(exercise())


def test_tenant_of_resolves_owner_for_worker_scoping() -> None:
    async def exercise() -> None:
        repository = await _repository()
        await repository.create(_record("job-3", "tenant-a"))
        assert await repository.tenant_of("job-3") == "tenant-a"
        assert await repository.tenant_of("missing") is None

    asyncio.run(exercise())
