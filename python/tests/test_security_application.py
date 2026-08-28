from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from knowledgeops_py.application.security import (
    Identity,
    bearer_token,
    permissions_for_roles,
    sign_payload,
    verify_access_token,
)
from knowledgeops_py.config import Settings


def test_security_application_signs_and_validates_jwt_identity() -> None:
    settings = Settings(jwt_secret="unit-test-secret-must-be-at-least-32-bytes")
    identity = Identity("alice", "tenant-a", ["USER"], permissions_for_roles(["USER"]), "api_key")
    token = sign_payload(
        settings,
        {
            "sub": identity.principal,
            "tenantId": identity.tenant_id,
            "roles": identity.roles,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "jti": "jwt-1",
        },
    )

    verified = verify_access_token(settings, token)
    assert verified == Identity("alice", "tenant-a", ["USER"], permissions_for_roles(["USER"]), "jwt")
    assert bearer_token(f"Bearer {token}") == token
    assert bearer_token(f"bearer {token}") is None
    assert "PERM_AUTH_KEY_MANAGE" in permissions_for_roles(["ADMIN"])
    assert verify_access_token(settings, jwt.encode({"sub": "alice"}, settings.jwt_secret, algorithm="HS256")) is None


def test_expired_jwt_falls_back_to_api_key_instead_of_erroring() -> None:
    """Java parity (a373082 M1): an expired/malformed JWT must degrade to the
    API-key path (401 when absent) instead of a 500."""
    import asyncio

    from knowledgeops_py.application.authentication import AuthApplicationService
    from knowledgeops_py.domain.runtime import PlatformStore

    settings = Settings(jwt_secret="unit-test-secret-must-be-at-least-32-bytes")
    service = AuthApplicationService(PlatformStore(), settings, None, None)
    issued = asyncio.run(service.issue_api_key("fallback", "ADMIN", "tenant-a"))

    expired = sign_payload(
        settings,
        {
            "sub": "alice",
            "tenantId": "tenant-a",
            "roles": ["USER"],
            "exp": datetime.now(UTC) - timedelta(minutes=1),
            "jti": "jwt-expired",
        },
    )

    identity = asyncio.run(service.resolve_identity(expired, issued.rawApiKey))
    assert identity is not None
    assert identity.auth_source == "api_key"
    assert identity.principal == "fallback"
    assert asyncio.run(service.resolve_identity(expired, None)) is None
