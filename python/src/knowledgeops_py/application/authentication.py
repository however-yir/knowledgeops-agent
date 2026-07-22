"""Authentication lifecycle service for API keys, refresh tokens and OIDC exchange."""

from __future__ import annotations

import hashlib
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from fastapi import HTTPException

from knowledgeops_py.application.oidc import (
    OidcFlowError,
)
from knowledgeops_py.application.oidc import (
    begin_oidc_login as begin_oidc_login_flow,
)
from knowledgeops_py.application.oidc import (
    complete_oidc_callback as complete_oidc_callback_flow,
)
from knowledgeops_py.application.oidc import (
    consume_oidc_exchange_code as consume_oidc_exchange_code_flow,
)
from knowledgeops_py.application.security import (
    ROLE_PERMISSIONS,
    Identity,
    normalize_tenant,
    permissions_for_roles,
    sign_payload,
    verify_access_token,
)
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.ports import OidcStateStore
from knowledgeops_py.dto import ApiKeyData, AuthTokenData
from knowledgeops_py.infrastructure.security_repository import (
    SecurityRepository,
    StoredIdentity,
)


class AuthenticationState(Protocol):
    api_keys: MutableMapping[str, dict[str, Any]]
    refresh_tokens: MutableMapping[str, dict[str, Any]]
    revoked_refresh_tokens: set[str]
    oidc_states: MutableMapping[str, dict[str, Any]]
    oidc_exchange_codes: MutableMapping[str, dict[str, Any]]


@dataclass(slots=True)
class AuthenticationError(Exception):
    code: str
    message: str


@dataclass(slots=True)
class AuthApplicationService:
    state: AuthenticationState
    settings: Settings
    security_repository: SecurityRepository | None
    oidc_state_store: OidcStateStore | None

    async def resolve_identity(self, bearer: str | None, api_key: str | None) -> Identity | None:
        return verify_access_token(self.settings, bearer) or await self.authenticate_api_key(api_key)

    async def issue_token(self, api_key: str | None, tenant_header: str | None) -> AuthTokenData:
        identity = await self.authenticate_api_key(api_key)
        if identity is None:
            raise AuthenticationError("AUTH_INVALID_API_KEY", "invalid api key")
        if tenant_header and normalize_tenant(tenant_header) != identity.tenant_id:
            raise AuthenticationError("AUTH_TENANT_MISMATCH", "tenant mismatch for api key")
        return await self.issue_tokens(identity)

    async def refresh(self, raw_token: str | None) -> AuthTokenData:
        if not raw_token:
            raise AuthenticationError("AUTH_INVALID_REFRESH_TOKEN", "invalid refresh token")
        if self.security_repository is not None:
            stored = await self.security_repository.consume_refresh_token(raw_token)
            if stored is None:
                raise AuthenticationError("AUTH_INVALID_REFRESH_TOKEN", "invalid refresh token")
            return await self.issue_tokens(_identity_from_stored(stored))

        token_hash = _hash(raw_token)
        if token_hash in self.state.revoked_refresh_tokens:
            raise AuthenticationError("AUTH_INVALID_REFRESH_TOKEN", "invalid refresh token")
        record = self.state.refresh_tokens.pop(token_hash, None)
        if not record or record["expiresAt"] <= _epoch_seconds():
            raise AuthenticationError("AUTH_INVALID_REFRESH_TOKEN", "invalid refresh token")
        self.state.revoked_refresh_tokens.add(token_hash)
        identity = Identity(
            record["principal"],
            record["tenantId"],
            record["roles"],
            permissions_for_roles(record["roles"]),
            "refresh",
        )
        return await self.issue_tokens(identity)

    async def issue_api_key(self, key_name: str, role: str, tenant_id: str) -> ApiKeyData:
        normalized_role = role.upper()
        if normalized_role not in ROLE_PERMISSIONS:
            raise HTTPException(status_code=422, detail="unsupported api key role")
        if self.security_repository is None:
            raw_key = f"koa_{uuid4().hex}{uuid4().hex[:16]}"
            expires_at = _future_iso(30)
            self.state.api_keys[_hash(raw_key)] = {
                "keyHash": _hash(raw_key),
                "keyName": key_name,
                "role": normalized_role,
                "tenantId": tenant_id,
                "enabled": True,
                "expiresAt": expires_at,
                "createdAt": _now_iso(),
                "updatedAt": _now_iso(),
            }
            return ApiKeyData(keyName=key_name, tenantId=tenant_id, role=normalized_role, rawApiKey=raw_key, expiresAt=expires_at)
        try:
            issued = await self.security_repository.issue_api_key(key_name, normalized_role, tenant_id, expires_in_days=30)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _api_key_data(issued.raw_key, issued.key_name, issued.tenant_id, issued.role, issued.expires_at)

    async def rotate_api_key(self, key_name: str, reason: str, tenant_id: str) -> ApiKeyData:
        if self.security_repository is not None:
            issued = await self.security_repository.rotate_api_key(key_name, tenant_id, reason, expires_in_days=30)
            if issued is None:
                raise HTTPException(status_code=404, detail="api key not found")
            return _api_key_data(issued.raw_key, issued.key_name, issued.tenant_id, issued.role, issued.expires_at)
        for record in self.state.api_keys.values():
            if record["keyName"] == key_name and record["tenantId"] == tenant_id and not record.get("revokedAt"):
                record["enabled"] = False
                record["revokedAt"] = _now_iso()
                record["revocationReason"] = reason
                return await self.issue_api_key(key_name, str(record["role"]), tenant_id)
        raise HTTPException(status_code=404, detail="api key not found")

    async def revoke_api_key(self, key_name: str, reason: str, tenant_id: str) -> None:
        if self.security_repository is not None:
            if not await self.security_repository.revoke_api_key(key_name, tenant_id, reason):
                raise HTTPException(status_code=404, detail="api key not found")
            return
        for record in self.state.api_keys.values():
            if record["keyName"] == key_name and record["tenantId"] == tenant_id and not record.get("revokedAt"):
                record["enabled"] = False
                record["revokedAt"] = _now_iso()
                record["revocationReason"] = reason
                return
        raise HTTPException(status_code=404, detail="api key not found")

    async def begin_oidc_login(self, return_to: str | None) -> dict[str, str]:
        try:
            return await begin_oidc_login_flow(self.state.oidc_states, self.settings, self.oidc_state_store, return_to)
        except OidcFlowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    async def complete_oidc_callback(self, authorization_code: str, state: str) -> dict[str, str]:
        try:
            return await complete_oidc_callback_flow(
                self.state.oidc_states,
                self.state.oidc_exchange_codes,
                self.settings,
                self.oidc_state_store,
                authorization_code,
                state,
            )
        except OidcFlowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    async def exchange_oidc_code(self, exchange_code: str) -> AuthTokenData:
        try:
            identity = await consume_oidc_exchange_code_flow(self.state.oidc_exchange_codes, self.oidc_state_store, exchange_code)
        except OidcFlowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if identity is None:
            raise AuthenticationError("OIDC_INVALID_EXCHANGE_CODE", "invalid or expired OIDC exchange code")
        return await self.issue_tokens(identity)

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        if self.security_repository is not None:
            await self.security_repository.revoke_refresh_token(raw_token)
            return
        token_hash = _hash(raw_token)
        self.state.refresh_tokens.pop(token_hash, None)
        self.state.revoked_refresh_tokens.add(token_hash)

    async def authenticate_api_key(self, raw_key: str | None) -> Identity | None:
        if self.security_repository is not None:
            stored = await self.security_repository.authenticate_api_key(raw_key)
            return _identity_from_stored(stored) if stored is not None else None
        if not raw_key:
            return None
        record = self.state.api_keys.get(_hash(raw_key.strip()))
        if not record or not record["enabled"] or record.get("revokedAt") or record.get("expiresAt", "9999") <= _now_iso():
            return None
        record["lastUsedAt"] = _now_iso()
        roles = [str(record["role"])]
        return Identity(str(record["keyName"]), str(record["tenantId"]), roles, permissions_for_roles(roles), "api_key")

    async def issue_tokens(self, identity: Identity) -> AuthTokenData:
        expires_at = _epoch_seconds() + self.settings.token_ttl_seconds
        token = sign_payload(
            self.settings,
            {
                "sub": identity.principal,
                "tenantId": identity.tenant_id,
                "roles": identity.roles,
                "permissions": identity.permissions,
                "exp": expires_at,
                "iat": _epoch_seconds(),
                "jti": f"jwt_{uuid4().hex[:16]}",
            },
        )
        if self.security_repository is None:
            refresh = f"refresh_{uuid4().hex[:16]}"
            self.state.refresh_tokens[_hash(refresh)] = {
                "principal": identity.principal,
                "tenantId": identity.tenant_id,
                "roles": identity.roles,
                "expiresAt": _epoch_seconds() + self.settings.refresh_token_ttl_days * 86400,
                "createdAt": _now_iso(),
            }
        else:
            refresh = await self.security_repository.issue_refresh_token(
                StoredIdentity(identity.principal, identity.tenant_id, tuple(identity.roles), identity.auth_source),
                self.settings.refresh_token_ttl_days,
            )
        return AuthTokenData(
            token=token,
            refreshToken=refresh,
            expiresInSeconds=self.settings.token_ttl_seconds,
            tenantId=identity.tenant_id,
            principal=identity.principal,
            roles=identity.roles,
            permissions=identity.permissions,
        )


def _identity_from_stored(stored: StoredIdentity) -> Identity:
    roles = list(stored.roles)
    return Identity(stored.principal, stored.tenant_id, roles, permissions_for_roles(roles), stored.source)


def _api_key_data(raw_key: str, key_name: str, tenant_id: str, role: str, expires_at: datetime) -> ApiKeyData:
    return ApiKeyData(
        keyName=key_name,
        tenantId=tenant_id,
        role=role,
        rawApiKey=raw_key,
        expiresAt=expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _epoch_seconds() -> int:
    return int(time.time())


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future_iso(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
