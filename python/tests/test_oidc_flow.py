from __future__ import annotations

import asyncio
import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException
from jwt import InvalidTokenError

import knowledgeops_py.app as app_module
import knowledgeops_py.application.oidc as oidc_module
from knowledgeops_py.application.authentication import AuthApplicationService, AuthenticationError
from knowledgeops_py.config import Settings


class FakeOidcClient:
    async def __aenter__(self) -> FakeOidcClient:
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    async def post(self, url: str, data: dict[str, Any]) -> httpx.Response:
        assert url == "https://idp.example.test/token"
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "authorization-code"
        assert data["code_verifier"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"id_token": "signed-id-token"},
        )


def test_oidc_authorization_code_pkce_flow_is_one_time(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        oidc_issuer_url="https://idp.example.test",
        oidc_client_id="knowledgeops",
        oidc_client_secret="client-secret",
        oidc_redirect_uri="https://app.example.test/auth/callback",
    )
    store = app_module.PlatformStore()
    auth_service = AuthApplicationService(store, settings, None, None)
    metadata = {
        "authorization_endpoint": "https://idp.example.test/authorize",
        "token_endpoint": "https://idp.example.test/token",
        "jwks_uri": "https://idp.example.test/keys",
        "issuer": "https://idp.example.test",
    }
    observed_nonce: list[str] = []

    async def fake_metadata(_: Settings) -> dict[str, Any]:
        return metadata

    def fake_verify(_: Settings, received_metadata: dict[str, Any], token: str, nonce: str) -> dict[str, Any]:
        assert received_metadata == metadata and token == "signed-id-token"
        observed_nonce.append(nonce)
        return {"sub": "alice", "tenant_id": "tenant-a", "roles": ["ADMIN"], "nonce": nonce}

    monkeypatch.setattr(oidc_module, "oidc_metadata", fake_metadata)
    monkeypatch.setattr(oidc_module, "verify_oidc_id_token", fake_verify)
    monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda **_: FakeOidcClient())

    async def exercise() -> None:
        login = await auth_service.begin_oidc_login("/console")
        params = parse_qs(urlparse(login["authorizationUrl"]).query)
        state = login["state"]
        pending = store.oidc_states[state]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode("ascii")).digest()).decode().rstrip("=")
        assert params == {
            "response_type": ["code"],
            "client_id": ["knowledgeops"],
            "redirect_uri": ["https://app.example.test/auth/callback"],
            "scope": ["openid profile email"],
            "state": [state],
            "nonce": [pending["nonce"]],
            "code_challenge": [challenge],
            "code_challenge_method": ["S256"],
        }

        callback = await auth_service.complete_oidc_callback("authorization-code", state)
        assert callback["returnTo"] == "/console"
        assert observed_nonce == [pending["nonce"]]
        token = await auth_service.exchange_oidc_code(callback["exchangeCode"])
        assert token.principal == "alice" and token.tenantId == "tenant-a"
        with pytest.raises(HTTPException, match="invalid or expired OIDC state"):
            await auth_service.complete_oidc_callback("authorization-code", state)
        with pytest.raises(AuthenticationError, match="invalid or expired OIDC exchange code"):
            await auth_service.exchange_oidc_code(callback["exchangeCode"])

    asyncio.run(exercise())


def test_oidc_id_token_verification_requires_jwks_issuer_audience_and_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeJwkClient:
        def __init__(self, url: str) -> None:
            assert url == "https://idp.example.test/keys"

        def get_signing_key_from_jwt(self, token: str) -> object:
            assert token == "signed-id-token"
            return type("SigningKey", (), {"key": "public-key"})()

    def fake_decode(token: str, key: str, **kwargs: Any) -> dict[str, Any]:
        assert token == "signed-id-token" and key == "public-key"
        assert kwargs["audience"] == "knowledgeops"
        assert kwargs["issuer"] == "https://idp.example.test"
        assert kwargs["options"] == {"require": ["exp", "sub", "nonce"]}
        return {"sub": "alice", "nonce": "expected"}

    monkeypatch.setattr(oidc_module.jwt, "PyJWKClient", FakeJwkClient)
    monkeypatch.setattr(oidc_module.jwt, "decode", fake_decode)
    settings = Settings(oidc_client_id="knowledgeops")
    metadata = {
        "jwks_uri": "https://idp.example.test/keys",
        "issuer": "https://idp.example.test",
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    assert oidc_module.verify_oidc_id_token(settings, metadata, "signed-id-token", "expected")["sub"] == "alice"
    monkeypatch.setattr(oidc_module.jwt, "decode", lambda *_args, **_kwargs: {"sub": "alice", "nonce": "other"})
    with pytest.raises(InvalidTokenError, match="OIDC nonce mismatch"):
        oidc_module.verify_oidc_id_token(settings, metadata, "signed-id-token", "expected")
