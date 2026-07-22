from __future__ import annotations

import json

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


def test_canonical_chat_and_pdf_post_accept_java_query_contract() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))

    chat = client.post("/ai/chat?prompt=query-contract&chatId=query-chat&modelProfile=quality", headers=AUTH_HEADERS)
    stream = client.post("/ai/chat/stream?prompt=query-contract&chatId=query-chat", headers=AUTH_HEADERS)
    rag = client.post("/ai/pdf/chat?prompt=query-contract&chatId=query-chat", headers=AUTH_HEADERS)

    assert chat.status_code == 200 and chat.headers["content-type"].startswith("text/html")
    assert stream.status_code == 200 and stream.text.startswith("data: ")
    assert rag.status_code == 200 and rag.headers["content-type"].startswith("text/html")


def test_canonical_chat_query_validation_uses_java_result() -> None:
    response = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a"))).post(
        "/ai/chat?chatId=query-chat", headers=AUTH_HEADERS
    )

    assert response.status_code == 400
    assert response.json() == {
        "ok": 0,
        "msg": "prompt is required",
        "code": "REQUEST_FAILED",
        "traceId": None,
        "data": None,
    }


def test_canonical_sessions_use_java_paged_result_and_state_shape() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    client.post("/ai/chat", headers=AUTH_HEADERS, json={"chatId": "session-shape", "prompt": "hello"})

    page = client.get("/ai/sessions?page=1&pageSize=1&search=Session", headers=AUTH_HEADERS)
    state = client.get("/ai/sessions/session-shape", headers=AUTH_HEADERS)

    assert page.status_code == 200
    assert set(page.json()) == {"items", "total", "page", "pageSize"}
    assert page.json()["total"] == 1
    assert {"id", "title", "updatedAt", "modelProfile", "streaming", "pinned", "archived", "workspaceId", "activeBranchId", "branches"} <= set(page.json()["items"][0])
    assert state.json()["id"] == "session-shape"
    assert isinstance(state.json()["updatedAt"], int)


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


def test_canonical_react_sse_uses_java_event_payloads_while_python_v1_keeps_envelopes() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    body = {"chatId": "react-stream", "prompt": "hello", "modelProfile": "balanced"}

    canonical = client.post("/ai/react/chat/stream", headers=AUTH_HEADERS, json=body).text
    legacy = client.post("/python/v1/ai/react/chat/stream", headers=AUTH_HEADERS, json=body).text
    canonical_data = [line.removeprefix("data: ") for line in canonical.splitlines() if line.startswith("data: ")]
    canonical_done = json.loads(canonical_data[-1])
    legacy_done = json.loads([line.removeprefix("data: ") for line in legacy.splitlines() if line.startswith("data: ")][-1])

    assert {"event: trace", "event: token", "event: done"} <= set(canonical.splitlines())
    assert {"ok", "msg", "chatId", "answer", "routeProfile", "trace"} <= set(canonical_done)
    assert "data" not in canonical_done
    assert canonical_done["trace"][0]["thought"] == canonical_done["trace"][0]["thoughtSummary"]
    assert legacy_done["ok"] == 1 and "data" in legacy_done


def test_canonical_chat_stream_is_raw_text_while_python_v1_keeps_named_events() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    body = {"chatId": "chat-stream", "prompt": "hello", "modelProfile": "balanced"}

    canonical = client.post("/ai/chat/stream", headers=AUTH_HEADERS, json=body).text
    legacy = client.post("/python/v1/ai/chat/stream", headers=AUTH_HEADERS, json=body).text

    assert canonical.startswith("data: ")
    assert "event:" not in canonical
    assert "event: done" in legacy
