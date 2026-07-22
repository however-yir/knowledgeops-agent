from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt import InvalidTokenError

from knowledgeops_py.config import Settings

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "ADMIN": [
        "ROLE_ADMIN",
        "PERM_AUTH_KEY_MANAGE",
        "PERM_CHAT_READ",
        "PERM_CHAT_WRITE",
        "PERM_INGESTION_READ",
        "PERM_INGESTION_WRITE",
        "PERM_RAG_READ",
        "PERM_METRICS_READ",
        "PERM_AUDIT_READ",
        "PERM_SESSION_READ",
        "PERM_SESSION_WRITE",
        "PERM_FEEDBACK_WRITE",
        "PERM_COST_READ",
        "PERM_COST_WRITE",
        "PERM_AGENT_TRUSTED",
        "PERM_EVAL_READ",
        "PERM_EVAL_WRITE",
    ],
    "USER": [
        "ROLE_USER",
        "PERM_CHAT_READ",
        "PERM_CHAT_WRITE",
        "PERM_INGESTION_READ",
        "PERM_INGESTION_WRITE",
        "PERM_RAG_READ",
        "PERM_SESSION_READ",
        "PERM_SESSION_WRITE",
        "PERM_FEEDBACK_WRITE",
        "PERM_COST_READ",
        "PERM_EVAL_READ",
        "PERM_EVAL_WRITE",
    ],
    "OPS": [
        "ROLE_OPS",
        "PERM_INGESTION_READ",
        "PERM_METRICS_READ",
        "PERM_AUDIT_READ",
        "PERM_SESSION_READ",
        "PERM_COST_READ",
        "PERM_EVAL_READ",
    ],
}


@dataclass
class Identity:
    principal: str
    tenant_id: str
    roles: list[str]
    permissions: list[str]
    auth_source: str


def sign_payload(settings: Settings, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_access_token(settings: Settings, token: str | None) -> Identity | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "jti"]})
    except InvalidTokenError:
        return None
    roles = [str(role) for role in payload.get("roles", ["USER"])]
    return Identity(str(payload["sub"]), normalize_tenant(payload.get("tenantId")), roles, permissions_for_roles(roles), "jwt")


def bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    prefix = "Bearer "
    return header[len(prefix) :].strip() if header.startswith(prefix) else None


def permissions_for_roles(roles: list[str]) -> list[str]:
    return sorted({permission for role in roles for permission in ROLE_PERMISSIONS.get(role, [])})


def normalize_tenant(value: Any = None) -> str:
    return str(value or "public").strip() or "public"
