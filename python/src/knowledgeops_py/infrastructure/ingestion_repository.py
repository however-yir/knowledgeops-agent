from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import IngestionChunkRecord, IngestionJobRecord


@dataclass(frozen=True, slots=True)
class PersistedIngestionJob:
    job_id: str
    tenant_id: str
    chat_id: str
    source_name: str
    source_type: str
    file_path: str | None
    status: str
    attempt_count: int
    max_retries: int
    queue_backend: str
    trace_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class SqlAlchemyIngestionRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def find_by_idempotency(self, tenant_id: str, idempotency_key: str) -> PersistedIngestionJob | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(IngestionJobRecord).where(
                    IngestionJobRecord.tenant_id == tenant_id,
                    IngestionJobRecord.idempotency_key == idempotency_key,
                )
            )
            return to_job(record)

    async def create(self, record: IngestionJobRecord) -> PersistedIngestionJob:
        async with self.sessions() as session:
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(IngestionJobRecord).where(
                        IngestionJobRecord.tenant_id == record.tenant_id,
                        IngestionJobRecord.idempotency_key == record.idempotency_key,
                    )
                )
                existing_job = to_job(existing)
                if existing_job is not None:
                    return existing_job
                raise
            return to_job(record) or raise_missing_job()

    async def get(self, tenant_id: str, job_id: str) -> PersistedIngestionJob | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(IngestionJobRecord).where(IngestionJobRecord.tenant_id == tenant_id, IngestionJobRecord.job_id == job_id)
            )
            return to_job(record)

    async def list_jobs(self, tenant_id: str, chat_id: str | None, limit: int) -> list[PersistedIngestionJob]:
        async with self.sessions() as session:
            statement = select(IngestionJobRecord).where(IngestionJobRecord.tenant_id == tenant_id).order_by(IngestionJobRecord.created_at.desc())
            if chat_id:
                statement = statement.where(IngestionJobRecord.chat_id == chat_id)
            records = (await session.scalars(statement.limit(limit))).all()
            return [job for record in records if (job := to_job(record)) is not None]

    async def ready_job_ids(self, tenant_id: str | None, limit: int) -> list[str]:
        return [job.job_id for job in await self.ready_jobs(tenant_id, limit)]

    async def ready_jobs(
        self,
        tenant_id: str | None,
        limit: int,
        statuses: tuple[str, ...] = ("QUEUED", "RETRY"),
    ) -> list[PersistedIngestionJob]:
        now = utc_now()
        async with self.sessions() as session:
            statement = (
                select(IngestionJobRecord)
                .where(
                    IngestionJobRecord.status.in_(statuses),
                    (IngestionJobRecord.next_retry_at.is_(None)) | (IngestionJobRecord.next_retry_at <= now),
                )
                .order_by(IngestionJobRecord.created_at)
                .limit(limit)
            )
            if tenant_id:
                statement = statement.where(IngestionJobRecord.tenant_id == tenant_id)
            return [job for record in (await session.scalars(statement)).all() if (job := to_job(record)) is not None]

    async def claim(self, job_id: str) -> PersistedIngestionJob | None:
        now = utc_now()
        async with self.sessions() as session:
            result = await session.execute(
                update(IngestionJobRecord)
                .where(
                    IngestionJobRecord.job_id == job_id,
                    IngestionJobRecord.status.in_(("QUEUED", "RETRY")),
                    (IngestionJobRecord.next_retry_at.is_(None)) | (IngestionJobRecord.next_retry_at <= now),
                )
                .values(status="RUNNING", attempt_count=IngestionJobRecord.attempt_count + 1, started_at=now, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            if changed_rows(result) != 1:
                await session.rollback()
                return None
            record = await session.scalar(select(IngestionJobRecord).where(IngestionJobRecord.job_id == job_id))
            await session.commit()
            return to_job(record)

    async def claim_next(self, tenant_id: str | None = None) -> PersistedIngestionJob | None:
        """Claim one ready job using the database's row lock as the worker lease."""
        now = utc_now()
        async with self.sessions() as session:
            statement = (
                select(IngestionJobRecord)
                .where(
                    IngestionJobRecord.status.in_(("QUEUED", "RETRY")),
                    (IngestionJobRecord.next_retry_at.is_(None)) | (IngestionJobRecord.next_retry_at <= now),
                )
                .order_by(IngestionJobRecord.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if tenant_id:
                statement = statement.where(IngestionJobRecord.tenant_id == tenant_id)
            record = (await session.scalars(statement)).first()
            if record is None:
                await session.rollback()
                return None
            record.status = "RUNNING"
            record.attempt_count += 1
            record.started_at = now
            record.updated_at = now
            await session.commit()
            return to_job(record)

    async def recover_abandoned(self, lease_seconds: int, tenant_id: str | None = None) -> int:
        """Return jobs whose worker lease expired to RETRY, or terminal FAILED."""
        now = utc_now()
        cutoff = now - timedelta(seconds=max(0, lease_seconds))
        async with self.sessions() as session:
            statement = (
                select(IngestionJobRecord)
                .where(
                    IngestionJobRecord.status == "RUNNING",
                    (IngestionJobRecord.started_at.is_(None)) | (IngestionJobRecord.started_at <= cutoff),
                )
                .with_for_update(skip_locked=True)
            )
            if tenant_id:
                statement = statement.where(IngestionJobRecord.tenant_id == tenant_id)
            records = (await session.scalars(statement)).all()
            for record in records:
                retry = record.attempt_count < record.max_retries
                record.status = "RETRY" if retry else "FAILED"
                record.error_message = "worker lease expired"
                record.next_retry_at = now if retry else None
                record.finished_at = now if not retry else None
                record.updated_at = now
            await session.commit()
            return len(records)

    async def complete(self, job_id: str, chunks: list[dict[str, Any]]) -> None:
        now = utc_now()
        async with self.sessions() as session:
            for chunk in chunks:
                session.add(IngestionChunkRecord(**chunk))
            await session.execute(
                update(IngestionJobRecord)
                .where(IngestionJobRecord.job_id == job_id, IngestionJobRecord.status == "RUNNING")
                .values(status="COMPLETED", finished_at=now, error_message=None, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            await session.commit()

    async def fail(self, job_id: str, message: str, base_delay_seconds: int) -> PersistedIngestionJob | None:
        now = utc_now()
        async with self.sessions() as session:
            record = await session.scalar(select(IngestionJobRecord).where(IngestionJobRecord.job_id == job_id).with_for_update())
            job = record
            if job is None or job.status != "RUNNING":
                await session.rollback()
                return None
            retry = job.attempt_count < job.max_retries
            job.status = "RETRY" if retry else "FAILED"
            job.error_message = message[:1024]
            job.next_retry_at = now + timedelta(seconds=max(1, base_delay_seconds) * max(1, job.attempt_count)) if retry else None
            job.finished_at = now if not retry else None
            job.updated_at = now
            await session.commit()
            return to_job(job)

    async def chunks(self, tenant_id: str, chat_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(IngestionChunkRecord)
                    .where(IngestionChunkRecord.tenant_id == tenant_id, IngestionChunkRecord.chat_id == chat_id)
                    .order_by(IngestionChunkRecord.created_at, IngestionChunkRecord.chunk_index)
                )
            ).all()
            return [
                {
                    "chunkId": item.chunk_id,
                    "tenantId": item.tenant_id,
                    "chatId": item.chat_id,
                    "sourceName": item.source_name,
                    "title": item.source_name,
                    "chunkIndex": item.chunk_index,
                    "content": item.content,
                }
                for item in records
            ]


def to_job(record: IngestionJobRecord | None) -> PersistedIngestionJob | None:
    if record is None:
        return None
    return PersistedIngestionJob(
        job_id=record.job_id,
        tenant_id=record.tenant_id,
        chat_id=record.chat_id,
        source_name=record.source_name,
        source_type=record.source_type,
        file_path=record.file_path,
        status=record.status,
        attempt_count=record.attempt_count,
        max_retries=record.max_retries,
        queue_backend=record.queue_backend,
        trace_id=record.trace_id,
        error_message=record.error_message,
        created_at=as_utc(record.created_at),
        updated_at=as_utc(record.updated_at),
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def changed_rows(result: object) -> int:
    rowcount = getattr(result, "rowcount", 0)
    return rowcount if isinstance(rowcount, int) else 0


def raise_missing_job() -> PersistedIngestionJob:
    raise RuntimeError("ingestion job disappeared after insert")
