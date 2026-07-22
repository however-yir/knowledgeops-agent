from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import SessionRecord


@dataclass(slots=True)
class SqlAlchemySessionRepository:
    sessions: async_sessionmaker[AsyncSession]

    async def list(self, tenant_id: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(SessionRecord)
                    .where(SessionRecord.tenant_id == tenant_id)
                    .order_by(SessionRecord.updated_at.desc())
                )
            ).all()
            return [to_public(record) for record in records]

    async def get(self, tenant_id: str, session_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(SessionRecord).where(SessionRecord.tenant_id == tenant_id, SessionRecord.session_id == session_id)
            )
            return to_public(record) if record is not None else None

    async def upsert(self, tenant_id: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(SessionRecord)
                .where(SessionRecord.tenant_id == tenant_id, SessionRecord.session_id == session_id)
                .with_for_update()
            )
            if record is None:
                record = SessionRecord(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    title=str(payload.get("title") or f"Session {session_id}"),
                    chat_id=str(payload.get("chatId") or session_id),
                    state=state_from_payload(payload),
                    pinned=bool(payload.get("pinned", False)),
                    archived=bool(payload.get("archived", False)),
                    updated_at=utc_now(),
                )
                session.add(record)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return None
                return to_public(record)
            apply_payload(record, payload)
            await session.commit()
            return to_public(record)

    async def append_turn(
        self,
        tenant_id: str,
        session_id: str,
        chat_id: str,
        prompt: str,
        answer: str,
        model_profile: str,
    ) -> dict[str, Any] | None:
        payload = {
            "chatId": chat_id,
            "modelProfile": model_profile,
            "messages": [
                {"role": "user", "content": prompt, "createdAt": utc_now().isoformat()},
                {"role": "assistant", "content": answer, "createdAt": utc_now().isoformat()},
            ],
        }
        async with self.sessions() as session:
            record = await session.scalar(
                select(SessionRecord)
                .where(SessionRecord.tenant_id == tenant_id, SessionRecord.session_id == session_id)
                .with_for_update()
            )
            if record is None:
                record = SessionRecord(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    title=f"Session {session_id}",
                    chat_id=chat_id,
                    state=state_from_payload(payload),
                    pinned=False,
                    archived=False,
                    updated_at=utc_now(),
                )
                session.add(record)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return None
                return to_public(record)
            messages = list(record.state.get("messages", []))
            messages.extend(payload["messages"])
            record.chat_id = chat_id
            record.state = record.state | {"modelProfile": model_profile, "messages": messages}
            record.updated_at = utc_now()
            await session.commit()
            return to_public(record)

    async def set_flag(self, tenant_id: str, session_id: str, flag: str, value: bool) -> dict[str, Any] | None:
        if flag not in {"pinned", "archived"}:
            raise ValueError(f"unsupported session flag: {flag}")
        async with self.sessions() as session:
            record = await session.scalar(
                select(SessionRecord)
                .where(SessionRecord.tenant_id == tenant_id, SessionRecord.session_id == session_id)
                .with_for_update()
            )
            if record is None:
                return None
            setattr(record, flag, value)
            record.updated_at = utc_now()
            await session.commit()
            return to_public(record)


def apply_payload(record: SessionRecord, payload: dict[str, Any]) -> None:
    state = record.state | state_from_payload(payload, existing=record.state)
    record.title = str(payload.get("title") or record.title)
    record.chat_id = str(payload.get("chatId") or record.chat_id)
    record.state = state
    if "pinned" in payload:
        record.pinned = bool(payload["pinned"])
    if "archived" in payload:
        record.archived = bool(payload["archived"])
    record.updated_at = utc_now()


def state_from_payload(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    state = dict(existing or {})
    for key in ("modelProfile", "workspace", "messages", "branches", "activeBranchId", "streaming"):
        if key in payload:
            state[key] = payload[key]
    state.setdefault("modelProfile", "balanced")
    state.setdefault("messages", [])
    return state


def to_public(record: SessionRecord) -> dict[str, Any]:
    state = record.state or {}
    return {
        "sessionId": record.session_id,
        "tenantId": record.tenant_id,
        "title": record.title,
        "chatId": record.chat_id,
        "modelProfile": str(state.get("modelProfile") or "balanced"),
        "workspace": state.get("workspace"),
        "messages": list(state.get("messages", [])),
        "branches": list(state.get("branches", [])),
        "activeBranchId": state.get("activeBranchId"),
        "streaming": state.get("streaming", True),
        "pinned": record.pinned,
        "archived": record.archived,
        "updatedAt": as_utc(record.updated_at).isoformat(),
    }


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
