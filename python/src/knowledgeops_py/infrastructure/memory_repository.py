from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import MemoryRecord


@dataclass(slots=True)
class SqlAlchemyMemoryRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def create(
        self,
        tenant_id: str,
        principal: str,
        content: str,
        memory_type: str,
        session_id: str | None,
    ) -> dict[str, Any]:
        record = MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:16]}",
            tenant_id=tenant_id,
            principal=principal,
            session_id=session_id,
            type=memory_type,
            content=content,
            embedding=None,
        )
        async with self.sessions() as session:
            session.add(record)
            await session.commit()
            return to_public(record)

    async def list(self, tenant_id: str, principal: str, session_id: str | None = None) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            statement = (
                select(MemoryRecord)
                .where(MemoryRecord.tenant_id == tenant_id, MemoryRecord.principal == principal)
                .order_by(MemoryRecord.created_at.desc())
            )
            if session_id:
                statement = statement.where(MemoryRecord.session_id == session_id)
            records = (await session.scalars(statement)).all()
            return [to_public(record) for record in records]

    async def recall(self, tenant_id: str, principal: str, session_id: str, limit: int = 100) -> builtins.list[dict[str, Any]]:
        """Return only principal-owned global or current-session memories."""
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(MemoryRecord)
                    .where(
                        MemoryRecord.tenant_id == tenant_id,
                        MemoryRecord.principal == principal,
                        or_(MemoryRecord.session_id.is_(None), MemoryRecord.session_id == session_id),
                    )
                    .order_by(MemoryRecord.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [to_public(record) for record in records]

    async def create_if_absent(
        self,
        tenant_id: str,
        principal: str,
        content: str,
        memory_type: str,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        """Avoid recording the same explicit preference on request retries."""
        async with self.sessions() as session:
            session_filter = MemoryRecord.session_id.is_(None) if session_id is None else MemoryRecord.session_id == session_id
            existing = await session.scalar(
                select(MemoryRecord).where(
                    MemoryRecord.tenant_id == tenant_id,
                    MemoryRecord.principal == principal,
                    session_filter,
                    MemoryRecord.content == content,
                )
            )
            if existing is not None:
                return None
            record = MemoryRecord(
                memory_id=f"mem_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                principal=principal,
                session_id=session_id,
                type=memory_type,
                content=content,
                embedding=None,
            )
            session.add(record)
            await session.commit()
            return to_public(record)


def to_public(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memoryId": record.memory_id,
        "tenantId": record.tenant_id,
        "principal": record.principal,
        "sessionId": record.session_id,
        "type": record.type,
        "content": record.content,
        "createdAt": as_utc(record.created_at).isoformat(),
    }


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
