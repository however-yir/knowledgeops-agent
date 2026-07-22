from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import GraphEntityRecord, GraphFactRecord, GraphRelationRecord


@dataclass(slots=True)
class SqlAlchemyGraphRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def create_entity(
        self,
        tenant_id: str,
        name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        description: str | None = None,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        record = GraphEntityRecord(
            entity_id=f"entity_{uuid4().hex[:16]}",
            tenant_id=tenant_id,
            name=name,
            type=entity_type,
            aliases=aliases or [],
            description=description,
            source_id=source_id,
            attributes=metadata or {},
            created_at=now,
            updated_at=now,
        )
        async with self.sessions() as session:
            session.add(record)
            await session.commit()
        return to_entity(record)

    async def list_entities(
        self, tenant_id: str, query: str = "", entity_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            statement = select(GraphEntityRecord).where(GraphEntityRecord.tenant_id == tenant_id)
            if entity_type:
                statement = statement.where(GraphEntityRecord.type == entity_type)
            records = (await session.scalars(statement.order_by(GraphEntityRecord.name).limit(limit))).all()
            return [to_entity(record) for record in records if entity_matches(record, query)]

    async def get_entity(self, tenant_id: str, entity_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(GraphEntityRecord).where(
                    GraphEntityRecord.tenant_id == tenant_id, GraphEntityRecord.entity_id == entity_id
                )
            )
            return to_entity(record) if record is not None else None

    async def create_relation(
        self,
        tenant_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        evidence_id: str | None = None,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        now = utc_now()
        async with self.sessions() as session:
            entities = (
                await session.scalars(
                    select(GraphEntityRecord).where(
                        GraphEntityRecord.tenant_id == tenant_id,
                        GraphEntityRecord.entity_id.in_((source_entity_id, target_entity_id)),
                    )
                )
            ).all()
            if {item.entity_id for item in entities} != {source_entity_id, target_entity_id}:
                return None
            record = GraphRelationRecord(
                relation_id=f"relation_{uuid4().hex[:16]}",
                tenant_id=tenant_id,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
                evidence_id=evidence_id,
                weight=weight,
                metadata_json=metadata or {},
                created_at=now,
            )
            session.add(record)
            await session.commit()
            return to_relation(record)

    async def neighbors(self, tenant_id: str, entity_id: str) -> list[dict[str, Any]] | None:
        async with self.sessions() as session:
            exists = await session.scalar(
                select(GraphEntityRecord.entity_id).where(
                    GraphEntityRecord.tenant_id == tenant_id, GraphEntityRecord.entity_id == entity_id
                )
            )
            if exists is None:
                return None
            relations = (
                await session.scalars(
                    select(GraphRelationRecord)
                    .where(
                        GraphRelationRecord.tenant_id == tenant_id,
                        or_(
                            GraphRelationRecord.source_entity_id == entity_id,
                            GraphRelationRecord.target_entity_id == entity_id,
                        ),
                    )
                    .order_by(GraphRelationRecord.created_at)
                )
            ).all()
            neighbor_ids = {
                item.target_entity_id if item.source_entity_id == entity_id else item.source_entity_id for item in relations
            }
            entities = (
                await session.scalars(
                    select(GraphEntityRecord).where(
                        GraphEntityRecord.tenant_id == tenant_id, GraphEntityRecord.entity_id.in_(neighbor_ids)
                    )
                )
            ).all()
            by_id = {item.entity_id: item for item in entities}
            return [
                {
                    "entity": to_entity(by_id[relation.target_entity_id if relation.source_entity_id == entity_id else relation.source_entity_id]),
                    "relationType": relation.relation_type,
                    "direction": "OUT" if relation.source_entity_id == entity_id else "IN",
                    "weight": relation.weight,
                }
                for relation in relations
                if (relation.target_entity_id if relation.source_entity_id == entity_id else relation.source_entity_id) in by_id
            ]

    async def create_fact(
        self,
        tenant_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float = 0.8,
        source: str | None = None,
        valid_from: date | None = None,
        valid_to: date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        record = GraphFactRecord(
            fact_id=f"fact_{uuid4().hex[:16]}",
            tenant_id=tenant_id,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            valid_from=valid_from,
            valid_to=valid_to,
            confidence=confidence,
            source=source,
            metadata_json=metadata or {},
            created_at=now,
            updated_at=now,
        )
        async with self.sessions() as session:
            session.add(record)
            await session.commit()
        return to_fact(record)

    async def search_facts(self, tenant_id: str, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(GraphFactRecord)
                    .where(GraphFactRecord.tenant_id == tenant_id)
                    .order_by(GraphFactRecord.confidence.desc(), GraphFactRecord.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [to_fact(record) for record in records if fact_matches(record, query)]


def entity_matches(record: GraphEntityRecord, query: str) -> bool:
    if not query.strip():
        return True
    needle = query.casefold().strip()
    values = [record.name, record.description or "", *(record.aliases or [])]
    return any(needle in value.casefold() for value in values)


def fact_matches(record: GraphFactRecord, query: str) -> bool:
    if not query.strip():
        return True
    needle = query.casefold().strip()
    return needle in record.subject.casefold() or needle in record.object_value.casefold()


def to_entity(record: GraphEntityRecord) -> dict[str, Any]:
    return {
        "entityId": record.entity_id,
        "tenantId": record.tenant_id,
        "name": record.name,
        "type": record.type,
        "aliases": record.aliases or [],
        "description": record.description,
        "sourceId": record.source_id,
        "metadata": record.attributes or {},
        "createdAt": as_utc(record.created_at).isoformat(),
        "updatedAt": as_utc(record.updated_at).isoformat(),
    }


def to_relation(record: GraphRelationRecord) -> dict[str, Any]:
    return {
        "relationId": record.relation_id,
        "tenantId": record.tenant_id,
        "sourceEntityId": record.source_entity_id,
        "targetEntityId": record.target_entity_id,
        "relationType": record.relation_type,
        "evidenceId": record.evidence_id,
        "weight": record.weight,
        "metadata": record.metadata_json or {},
        "createdAt": as_utc(record.created_at).isoformat(),
    }


def to_fact(record: GraphFactRecord) -> dict[str, Any]:
    return {
        "factId": record.fact_id,
        "tenantId": record.tenant_id,
        "subject": record.subject,
        "predicate": record.predicate,
        "object": record.object_value,
        "validFrom": record.valid_from.isoformat() if record.valid_from else None,
        "validTo": record.valid_to.isoformat() if record.valid_to else None,
        "confidence": record.confidence,
        "source": record.source,
        "metadata": record.metadata_json or {},
        "createdAt": as_utc(record.created_at).isoformat(),
        "updatedAt": as_utc(record.updated_at).isoformat(),
    }


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
