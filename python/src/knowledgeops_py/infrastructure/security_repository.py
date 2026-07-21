from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowledgeops_py.infrastructure.models import ApiKeyRecord, RefreshTokenRecord


@dataclass(frozen=True, slots=True)
class StoredIdentity:
    """Authentication facts restored from a durable credential record."""

    principal: str
    tenant_id: str
    roles: tuple[str, ...]
    source: str


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    raw_key: str
    key_name: str
    tenant_id: str
    role: str
    expires_at: datetime


class SecurityRepository(Protocol):
    async def authenticate_api_key(self, raw_key: str | None) -> StoredIdentity | None: ...

    async def issue_api_key(self, key_name: str, role: str, tenant_id: str, expires_in_days: int) -> IssuedApiKey: ...

    async def rotate_api_key(self, key_name: str, tenant_id: str, reason: str, expires_in_days: int) -> IssuedApiKey | None: ...

    async def revoke_api_key(self, key_name: str, tenant_id: str, reason: str) -> bool: ...

    async def issue_refresh_token(self, identity: StoredIdentity, expires_in_days: int) -> str: ...

    async def consume_refresh_token(self, raw_token: str | None) -> StoredIdentity | None: ...

    async def revoke_refresh_token(self, raw_token: str | None) -> None: ...


@dataclass(slots=True)
class SqlAlchemySecurityRepository:
    """Durable credential lifecycle with conditional refresh-token rotation."""

    sessions: async_sessionmaker[AsyncSession]

    async def bootstrap_api_key(self, raw_key: str, key_name: str, tenant_id: str, role: str) -> None:
        key_hash = hash_secret(raw_key)
        async with self.sessions() as session:
            existing = await session.get(ApiKeyRecord, key_hash)
            if existing is None:
                session.add(
                    ApiKeyRecord(
                        key_hash=key_hash,
                        key_name=key_name,
                        tenant_id=tenant_id,
                        role=role,
                        enabled=True,
                        expires_at=None,
                    )
                )
                await session.commit()

    async def authenticate_api_key(self, raw_key: str | None) -> StoredIdentity | None:
        if not raw_key:
            return None
        key_hash = hash_secret(raw_key.strip())
        now = utc_now()
        async with self.sessions() as session:
            record = await session.scalar(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.key_hash == key_hash,
                    ApiKeyRecord.enabled.is_(True),
                    ApiKeyRecord.revoked_at.is_(None),
                )
            )
            if record is None or (record.expires_at is not None and as_utc(record.expires_at) <= now):
                return None
            record.last_used_at = now
            await session.commit()
            return StoredIdentity(record.key_name, record.tenant_id, (record.role,), "api_key")

    async def issue_api_key(self, key_name: str, role: str, tenant_id: str, expires_in_days: int) -> IssuedApiKey:
        raw_key = new_api_key()
        expires_at = utc_now() + timedelta(days=max(1, expires_in_days))
        async with self.sessions() as session:
            active = await self._active_by_name(session, key_name, tenant_id, lock=True)
            if active is not None:
                raise ValueError("active api key already exists for keyName")
            session.add(
                ApiKeyRecord(
                    key_hash=hash_secret(raw_key),
                    key_name=key_name,
                    tenant_id=tenant_id,
                    role=role,
                    enabled=True,
                    expires_at=expires_at,
                )
            )
            await session.commit()
        return IssuedApiKey(raw_key, key_name, tenant_id, role, expires_at)

    async def rotate_api_key(self, key_name: str, tenant_id: str, reason: str, expires_in_days: int) -> IssuedApiKey | None:
        raw_key = new_api_key()
        expires_at = utc_now() + timedelta(days=max(1, expires_in_days))
        now = utc_now()
        async with self.sessions() as session:
            previous = await self._active_by_name(session, key_name, tenant_id, lock=True)
            if previous is None:
                return None
            previous.enabled = False
            previous.revoked_at = now
            previous.revoked_reason = reason
            session.add(
                ApiKeyRecord(
                    key_hash=hash_secret(raw_key),
                    key_name=key_name,
                    tenant_id=tenant_id,
                    role=previous.role,
                    enabled=True,
                    expires_at=expires_at,
                    rotated_from_key_hash=previous.key_hash,
                )
            )
            await session.commit()
            return IssuedApiKey(raw_key, key_name, tenant_id, previous.role, expires_at)

    async def revoke_api_key(self, key_name: str, tenant_id: str, reason: str) -> bool:
        now = utc_now()
        async with self.sessions() as session:
            result = await session.execute(
                update(ApiKeyRecord)
                .where(
                    ApiKeyRecord.key_name == key_name,
                    ApiKeyRecord.tenant_id == tenant_id,
                    ApiKeyRecord.enabled.is_(True),
                    ApiKeyRecord.revoked_at.is_(None),
                )
                .values(enabled=False, revoked_at=now, revoked_reason=reason, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            return bool(result.rowcount)

    async def issue_refresh_token(self, identity: StoredIdentity, expires_in_days: int) -> str:
        raw_token = new_refresh_token()
        async with self.sessions() as session:
            session.add(
                RefreshTokenRecord(
                    token_hash=hash_secret(raw_token),
                    principal=identity.principal,
                    tenant_id=identity.tenant_id,
                    roles=list(identity.roles),
                    expires_at=utc_now() + timedelta(days=max(1, expires_in_days)),
                )
            )
            await session.commit()
        return raw_token

    async def consume_refresh_token(self, raw_token: str | None) -> StoredIdentity | None:
        if not raw_token:
            return None
        token_hash = hash_secret(raw_token)
        now = utc_now()
        async with self.sessions() as session:
            record = await session.get(RefreshTokenRecord, token_hash)
            if record is None or record.revoked_at is not None or as_utc(record.expires_at) <= now:
                return None
            result = await session.execute(
                update(RefreshTokenRecord)
                .where(
                    RefreshTokenRecord.token_hash == token_hash,
                    RefreshTokenRecord.revoked_at.is_(None),
                    RefreshTokenRecord.expires_at > now,
                )
                .values(revoked_at=now)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
            return StoredIdentity(record.principal, record.tenant_id, tuple(record.roles), "refresh_token")

    async def revoke_refresh_token(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        async with self.sessions() as session:
            await session.execute(
                update(RefreshTokenRecord)
                .where(RefreshTokenRecord.token_hash == hash_secret(raw_token), RefreshTokenRecord.revoked_at.is_(None))
                .values(revoked_at=utc_now())
                .execution_options(synchronize_session=False)
            )
            await session.commit()

    async def _active_by_name(
        self, session: AsyncSession, key_name: str, tenant_id: str, lock: bool
    ) -> ApiKeyRecord | None:
        now = utc_now()
        statement = select(ApiKeyRecord).where(
            ApiKeyRecord.key_name == key_name,
            ApiKeyRecord.tenant_id == tenant_id,
            ApiKeyRecord.enabled.is_(True),
            ApiKeyRecord.revoked_at.is_(None),
            (ApiKeyRecord.expires_at.is_(None)) | (ApiKeyRecord.expires_at > now),
        )
        if lock:
            statement = statement.with_for_update()
        return cast(ApiKeyRecord | None, await session.scalar(statement))


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_api_key() -> str:
    from secrets import token_urlsafe

    return f"koa_{token_urlsafe(48)}"


def new_refresh_token() -> str:
    from secrets import token_urlsafe

    return f"refresh_{token_urlsafe(48)}"


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
