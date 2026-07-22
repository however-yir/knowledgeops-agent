from __future__ import annotations

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app
from knowledgeops_py.config import Settings

AUTH_HEADERS = {"X-API-Key": "test-key", "X-Tenant-ID": "tenant-a"}


def test_unprefixed_auth_and_business_routes_use_java_response_shapes() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))

    token = client.post("/auth/token", headers=AUTH_HEADERS)
    assert token.status_code == 200
    assert {"ok", "msg", "token", "refreshToken", "tenantId", "expiresInSeconds"} <= set(token.json())
    assert "data" not in token.json()

    api_key = client.post("/auth/api-keys?keyName=canonical&role=USER", headers=AUTH_HEADERS)
    assert api_key.status_code == 200
    assert {"ok", "msg", "keyName", "rawApiKey", "expiresAt"} <= set(api_key.json())
    assert "data" not in api_key.json()

    feedback = client.post("/ai/feedback", headers=AUTH_HEADERS, json={"chatId": "canonical", "rating": 1})
    assert feedback.json() == {"ok": 1, "msg": "ok", "code": None, "traceId": None, "data": None}

    cost = client.get("/cost/summary", headers=AUTH_HEADERS)
    assert cost.status_code == 200
    assert {"tenantId", "monthCostUsd", "monthlyBudgetUsd", "budgetRemainingUsd"} <= set(cost.json())
    assert "data" not in cost.json()


def test_python_v1_keeps_legacy_envelope_and_java_errors_return_result() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))

    legacy = client.post("/python/v1/auth/token", headers=AUTH_HEADERS)
    assert legacy.json()["ok"] == 1
    assert "data" in legacy.json()

    missing = client.get("/ingestion/jobs/not-found", headers=AUTH_HEADERS)
    assert missing.status_code == 404
    assert missing.json() == {
        "ok": 0,
        "msg": "job not found",
        "code": "REQUEST_FAILED",
        "traceId": None,
        "data": None,
    }


def test_canonical_rate_limit_returns_java_result_instead_of_a_stream_error() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a", rate_limit_per_minute=1)))
    body = {"chatId": "rate", "prompt": "hello", "modelProfile": "balanced"}

    assert client.post("/ai/chat", headers=AUTH_HEADERS, json=body).status_code == 200
    limited = client.post("/ai/chat", headers=AUTH_HEADERS, json=body)

    assert limited.status_code == 429
    assert limited.json() == {
        "ok": 0,
        "msg": "rate limit exceeded",
        "code": "REQUEST_FAILED",
        "traceId": None,
        "data": None,
    }
