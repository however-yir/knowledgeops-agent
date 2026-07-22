from __future__ import annotations

import base64
import hashlib
import secrets
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import InvalidTokenError

from knowledgeops_py.application.security import ROLE_PERMISSIONS, Identity, normalize_tenant, permissions_for_roles
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.ports import OidcStateStore, OidcStateUnavailable


@dataclass(frozen=True, slots=True)
class OidcFlowError(ValueError):
    status_code: int
    detail: str


async def begin_oidc_login(
    states: MutableMapping[str, dict[str, Any]],
    settings: Settings,
    state_store: OidcStateStore | None,
    return_to: str | None,
) -> dict[str, str]:
    metadata = await oidc_metadata(settings)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    pending = {"nonce": nonce, "verifier": verifier, "returnTo": return_to or "", "expiresAt": epoch_seconds() + 600}
    if state_store is None:
        states[state] = pending
    else:
        try:
            await state_store.put("state", sha256_hex(state), pending, ttl_seconds=600)
        except OidcStateUnavailable as exc:
            raise OidcFlowError(503, "OIDC state store is unavailable") from exc
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return {"authorizationUrl": f"{metadata['authorization_endpoint']}?{query}", "state": state}


async def complete_oidc_callback(
    states: MutableMapping[str, dict[str, Any]],
    exchange_codes: MutableMapping[str, dict[str, Any]],
    settings: Settings,
    state_store: OidcStateStore | None,
    authorization_code: str,
    state: str,
) -> dict[str, str]:
    if state_store is None:
        pending = states.pop(state, None)
    else:
        try:
            pending = await state_store.consume("state", sha256_hex(state))
        except OidcStateUnavailable as exc:
            raise OidcFlowError(503, "OIDC state store is unavailable") from exc
    if not pending or int(pending["expiresAt"]) <= epoch_seconds():
        raise OidcFlowError(400, "invalid or expired OIDC state")
    metadata = await oidc_metadata(settings)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                metadata["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": authorization_code,
                    "redirect_uri": settings.oidc_redirect_uri,
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret or "",
                    "code_verifier": pending["verifier"],
                },
            )
            token_response.raise_for_status()
            tokens = token_response.json()
        claims = verify_oidc_id_token(settings, metadata, str(tokens["id_token"]), str(pending["nonce"]))
    except (httpx.HTTPError, KeyError, InvalidTokenError, ValueError) as exc:
        raise OidcFlowError(502, "OIDC token exchange failed") from exc
    tenant_id = claims.get("tenant_id") or claims.get("tenantId") or claims.get("tid")
    if not tenant_id:
        raise OidcFlowError(403, "OIDC tenant claim is required")
    raw_roles = claims.get("roles") or claims.get("role") or ["USER"]
    roles = [str(raw_roles)] if isinstance(raw_roles, str) else [str(role) for role in raw_roles]
    roles = [role.upper() for role in roles if role.upper() in ROLE_PERMISSIONS] or ["USER"]
    identity = Identity(str(claims["sub"]), normalize_tenant(tenant_id), roles, permissions_for_roles(roles), "oidc")
    exchange_code = secrets.token_urlsafe(32)
    exchange_payload = {
        "identity": {"principal": identity.principal, "tenantId": identity.tenant_id, "roles": identity.roles},
        "expiresAt": epoch_seconds() + 60,
    }
    if state_store is None:
        exchange_codes[sha256_hex(exchange_code)] = {"identity": identity, "expiresAt": exchange_payload["expiresAt"]}
    else:
        try:
            await state_store.put("exchange", sha256_hex(exchange_code), exchange_payload, ttl_seconds=60)
        except OidcStateUnavailable as exc:
            raise OidcFlowError(503, "OIDC state store is unavailable") from exc
    return {"exchangeCode": exchange_code, "returnTo": str(pending["returnTo"])}


async def consume_oidc_exchange_code(
    exchange_codes: MutableMapping[str, dict[str, Any]], state_store: OidcStateStore | None, exchange_code: str
) -> Identity | None:
    if state_store is None:
        record = exchange_codes.pop(sha256_hex(exchange_code), None)
    else:
        try:
            record = await state_store.consume("exchange", sha256_hex(exchange_code))
        except OidcStateUnavailable as exc:
            raise OidcFlowError(503, "OIDC state store is unavailable") from exc
    if not record or int(record["expiresAt"]) <= epoch_seconds():
        return None
    identity = record["identity"]
    if isinstance(identity, Identity):
        return identity
    roles = [str(role) for role in identity.get("roles", ["USER"])]
    return Identity(
        str(identity["principal"]),
        normalize_tenant(identity.get("tenantId")),
        roles,
        permissions_for_roles(roles),
        "oidc",
    )


async def oidc_metadata(settings: Settings) -> dict[str, Any]:
    if not settings.oidc_issuer_url or not settings.oidc_client_id or not settings.oidc_redirect_uri:
        raise OidcFlowError(503, "OIDC is not configured")
    issuer = settings.oidc_issuer_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
            metadata = response.json()
    except httpx.HTTPError as exc:
        raise OidcFlowError(503, "OIDC discovery is unavailable") from exc
    for required_key in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
        if not metadata.get(required_key):
            raise OidcFlowError(503, "OIDC discovery response is incomplete")
    return metadata


def verify_oidc_id_token(settings: Settings, metadata: dict[str, Any], token: str, nonce: str) -> dict[str, Any]:
    key = jwt.PyJWKClient(metadata["jwks_uri"]).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=metadata.get("id_token_signing_alg_values_supported", ["RS256"]),
        audience=settings.oidc_client_id,
        issuer=metadata["issuer"],
        options={"require": ["exp", "sub", "nonce"]},
    )
    if claims.get("nonce") != nonce:
        raise InvalidTokenError("OIDC nonce mismatch")
    return claims


def epoch_seconds() -> int:
    return int(time.time())


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
