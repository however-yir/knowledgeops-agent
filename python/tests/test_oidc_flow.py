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
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode("ascii")).digest()).decode().rstrip("=")
        )
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


def test_oidc_replay_protection_store_failures_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = oidc_settings()
    monkeypatch.setattr(oidc_module, "oidc_metadata", fake_oidc_metadata)

    class UnavailableStore:
        async def put(self, *_: object, **__: object) -> None:
            raise oidc_module.OidcStateUnavailable("redis is offline")

        async def consume(self, *_: object) -> dict[str, Any] | None:
            raise oidc_module.OidcStateUnavailable("redis is offline")

    async def exercise() -> None:
        store = UnavailableStore()
        with pytest.raises(oidc_module.OidcFlowError, match="state store is unavailable"):
            await oidc_module.begin_oidc_login({}, settings, store, None)
        with pytest.raises(oidc_module.OidcFlowError, match="state store is unavailable"):
            await oidc_module.complete_oidc_callback({}, {}, settings, store, "authorization-code", "state")
        with pytest.raises(oidc_module.OidcFlowError, match="state store is unavailable"):
            await oidc_module.consume_oidc_exchange_code({}, store, "exchange-code")

    asyncio.run(exercise())


def test_oidc_callback_rejects_provider_claim_and_exchange_store_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = oidc_settings()
    pending = {
        "nonce": "expected",
        "verifier": "verifier",
        "returnTo": "/console",
        "expiresAt": oidc_module.epoch_seconds() + 60,
    }
    monkeypatch.setattr(oidc_module, "oidc_metadata", fake_oidc_metadata)

    class OfflineTokenClient:
        async def __aenter__(self) -> OfflineTokenClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def post(self, *_: object, **__: object) -> httpx.Response:
            raise httpx.ConnectError("idp is offline")

    async def exercise() -> None:
        monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda **_: OfflineTokenClient())
        with pytest.raises(oidc_module.OidcFlowError, match="OIDC token exchange failed"):
            await oidc_module.complete_oidc_callback(
                {"state": pending.copy()}, {}, settings, None, "authorization-code", "state"
            )

        monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda **_: FakeOidcClient())
        monkeypatch.setattr(oidc_module, "verify_oidc_id_token", lambda *_: {"sub": "alice", "nonce": "expected"})
        with pytest.raises(oidc_module.OidcFlowError, match="tenant claim is required"):
            await oidc_module.complete_oidc_callback(
                {"state": pending.copy()}, {}, settings, None, "authorization-code", "state"
            )

        class PutUnavailableStore:
            async def consume(self, *_: object) -> dict[str, Any]:
                return pending

            async def put(self, *_: object, **__: object) -> None:
                raise oidc_module.OidcStateUnavailable("redis is offline")

        monkeypatch.setattr(
            oidc_module,
            "verify_oidc_id_token",
            lambda *_: {"sub": "alice", "tenant_id": "tenant-a", "nonce": "expected"},
        )
        with pytest.raises(oidc_module.OidcFlowError, match="state store is unavailable"):
            await oidc_module.complete_oidc_callback(
                {}, {}, settings, PutUnavailableStore(), "authorization-code", "state"
            )

        class SerializedIdentityStore:
            async def consume(self, *_: object) -> dict[str, Any]:
                return {
                    "identity": {"principal": "alice", "tenantId": "tenant-a", "roles": ["ADMIN"]},
                    "expiresAt": oidc_module.epoch_seconds() + 60,
                }

            async def put(self, *_: object, **__: object) -> None:
                return None

        identity = await oidc_module.consume_oidc_exchange_code({}, SerializedIdentityStore(), "exchange-code")
        assert identity is not None and identity.principal == "alice" and identity.roles == ["ADMIN"]

    asyncio.run(exercise())


def test_oidc_discovery_requires_configuration_and_complete_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class DiscoveryClient:
        def __init__(self, response: httpx.Response) -> None:
            self.response = response

        async def __aenter__(self) -> DiscoveryClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, *_: object) -> httpx.Response:
            return self.response

    async def exercise() -> None:
        with pytest.raises(oidc_module.OidcFlowError, match="OIDC is not configured"):
            await oidc_module.oidc_metadata(Settings())

        error_response = httpx.Response(
            503, request=httpx.Request("GET", "https://idp.example.test/.well-known/openid-configuration")
        )
        monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda **_: DiscoveryClient(error_response))
        with pytest.raises(oidc_module.OidcFlowError, match="OIDC discovery is unavailable"):
            await oidc_module.oidc_metadata(oidc_settings())

        request = httpx.Request("GET", "https://idp.example.test/.well-known/openid-configuration")
        for payload in ([], {"authorization_endpoint": "https://idp.example.test/authorize"}):
            monkeypatch.setattr(
                oidc_module.httpx,
                "AsyncClient",
                lambda payload=payload, **_: DiscoveryClient(httpx.Response(200, request=request, json=payload)),
            )
            with pytest.raises(oidc_module.OidcFlowError, match="OIDC discovery response is incomplete"):
                await oidc_module.oidc_metadata(oidc_settings())

    asyncio.run(exercise())


def oidc_settings() -> Settings:
    return Settings(
        oidc_issuer_url="https://idp.example.test",
        oidc_client_id="knowledgeops",
        oidc_client_secret="client-secret",
        oidc_redirect_uri="https://app.example.test/auth/callback",
    )


def oidc_metadata() -> dict[str, str]:
    return {
        "authorization_endpoint": "https://idp.example.test/authorize",
        "token_endpoint": "https://idp.example.test/token",
        "jwks_uri": "https://idp.example.test/keys",
        "issuer": "https://idp.example.test",
    }


async def fake_oidc_metadata(_: Settings) -> dict[str, str]:
    return oidc_metadata()
