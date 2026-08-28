"""Tests for client-IP resolution, tenant trust boundaries, and rate-limit keys.

Parity of the Java rate-limit IP fix (main a373082, bug 16) plus the Python
tenant-header trust-boundary hardening.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from knowledgeops_py.api.request_runtime import (
    _ip_is_internal,
    _rate_limit_key,
    _rightmost_public_hop,
    enforce_rate_limit,
    resolve_client_ip,
)
from knowledgeops_py.app import create_app
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.runtime import PlatformStore, RequestContext


def _request(client: tuple[str, int] | None = None, headers: dict[str, str] | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
    }
    if client is not None:
        scope["client"] = client
    return Request(scope)


def _ctx(tenant_id: str = "tenant-a", principal: str = "anonymous") -> RequestContext:
    return RequestContext("trace", tenant_id, principal, ["ANONYMOUS"], [], principal)


def test_ip_classification() -> None:
    internal = ["127.0.0.1", "10.0.0.5", "172.16.0.9", "192.168.0.1", "169.254.1.1", "::1", "::ffff:127.0.0.1", "0.0.0.0"]
    external = ["93.184.216.34", "8.8.8.8"]
    for address in internal:
        assert _ip_is_internal(address) is True, address
    for address in external:
        assert _ip_is_internal(address) is False, address
    assert _ip_is_internal("attacker.example") is False


def test_rightmost_public_hop_wins() -> None:
    assert _rightmost_public_hop("1.2.3.4, 10.0.0.1, 192.168.0.5") == "1.2.3.4"
    assert _rightmost_public_hop("10.0.0.1, 192.168.0.5") is None
    # A proxy appends the real client IP to the right; a forged left value loses.
    assert _rightmost_public_hop("attacker.example, 8.8.8.8") == "8.8.8.8"


def test_public_direct_peer_ignores_forwarded_for() -> None:
    request = _request(client=("8.8.8.8", 80), headers={"X-Forwarded-For": "1.2.3.4"})
    assert resolve_client_ip(request) == "8.8.8.8"


def test_private_peer_uses_rightmost_public_hop() -> None:
    request = _request(client=("10.0.0.9", 1234), headers={"X-Forwarded-For": "attacker.example, 93.184.216.34"})
    assert resolve_client_ip(request) == "93.184.216.34"


def test_private_peer_without_public_hop_falls_back_to_peer() -> None:
    request = _request(client=("10.0.0.9", 1234), headers={"X-Forwarded-For": "10.0.0.1, 192.168.0.5"})
    assert resolve_client_ip(request) == "10.0.0.9"


def test_missing_peer_falls_back_to_unknown() -> None:
    assert resolve_client_ip(_request()) == "unknown"


def test_anonymous_rate_limit_key_ignores_tenant_header() -> None:
    request = _request(client=("8.8.8.8", 80))
    first = _rate_limit_key(_ctx("tenant-a"), request)
    second = _rate_limit_key(_ctx("tenant-b"), request)
    assert first == second == "anonymous:ip:8.8.8.8"


def test_authenticated_rate_limit_key_keeps_tenant_and_principal() -> None:
    request = _request(client=("8.8.8.8", 80))
    assert _rate_limit_key(_ctx("tenant-a", "alice"), request) == "tenant-a:alice"


def test_anonymous_bucket_is_shared_across_tenant_headers() -> None:
    store: PlatformStore = PlatformStore()
    settings = Settings(demo_api_key="k", demo_tenant_id="tenant-a", rate_limit_per_minute=1)
    request = _request(client=("8.8.8.8", 80))

    asyncio.run(enforce_rate_limit(store, settings, _ctx("tenant-a"), request))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(enforce_rate_limit(store, settings, _ctx("tenant-b"), request))
    assert exc_info.value.status_code == 429


def test_tenant_mismatch_with_valid_identity_is_rejected() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    response = client.get(
        "/python/v1/cost/summary",
        headers={"X-API-Key": "test-key", "X-Tenant-ID": "tenant-b"},
    )
    assert response.status_code == 403


def test_tenant_header_case_difference_is_accepted() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="Tenant-A")))
    response = client.get(
        "/python/v1/cost/summary",
        headers={"X-API-Key": "test-key", "X-Tenant-ID": "tenant-a"},
    )
    assert response.status_code == 200


def test_anonymous_requests_share_one_ip_bucket_regardless_of_header() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a", rate_limit_per_minute=1)))
    first = client.get("/python/v1/cost/summary", headers={"X-Tenant-ID": "tenant-x"})
    second = client.get("/python/v1/cost/summary", headers={"X-Tenant-ID": "tenant-y"})

    assert first.status_code == 401
    # The second anonymous request hits the same IP bucket even though the
    # tenant header rotated: 429 from the middleware, not a fresh 401.
    assert second.status_code == 429
