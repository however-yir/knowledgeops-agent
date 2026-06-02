from __future__ import annotations

import json

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app
from knowledgeops_py.config import Settings


AUTH_HEADERS = {"X-API-Key": "test-key", "X-Tenant-ID": "tenant-a"}


def client() -> TestClient:
    return TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))


def assert_envelope(payload: dict) -> dict:
    assert payload["ok"] in (0, 1)
    assert "msg" in payload
    assert "data" in payload
    return payload["data"]


def test_health_and_metrics_use_enterprise_envelope() -> None:
    test_client = client()

    health = test_client.get("/actuator/health")
    metrics = test_client.get("/metrics", headers=AUTH_HEADERS)

    assert health.status_code == 200
    assert assert_envelope(health.json())["status"] == "UP"
    assert metrics.status_code == 200
    assert "knowledgeops_python_up 1" in assert_envelope(metrics.json())["prometheus"]


def test_auth_token_refresh_and_invalid_key_contract() -> None:
    test_client = client()

    invalid = test_client.post("/auth/token", headers={"X-API-Key": "wrong", "X-Tenant-ID": "tenant-a"})
    token = test_client.post("/auth/token", headers=AUTH_HEADERS)

    assert invalid.status_code == 200
    assert invalid.json()["ok"] == 0

    data = assert_envelope(token.json())
    assert data["token"].startswith("pyjwt.")
    assert data["refreshToken"].startswith("refresh_")
    assert data["tenantId"] == "tenant-a"

    refreshed = test_client.post("/auth/refresh", headers={"X-Refresh-Token": data["refreshToken"]})
    assert refreshed.status_code == 200
    assert assert_envelope(refreshed.json())["token"].startswith("pyjwt.")


def test_error_response_contains_code_and_trace_id() -> None:
    response = client().post("/ai/chat", json={"chatId": "c1", "prompt": "hello", "modelProfile": "balanced"})

    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] == 0
    assert payload["code"] == "AUTHENTICATION_REQUIRED"
    assert payload["traceId"]


def test_chat_and_sse_contract() -> None:
    test_client = client()
    chat = test_client.post(
        "/ai/chat",
        headers=AUTH_HEADERS,
        json={"chatId": "chat-1", "prompt": "hello", "modelProfile": "balanced"},
    )
    stream = test_client.post(
        "/ai/chat/stream",
        headers=AUTH_HEADERS,
        json={"chatId": "chat-1", "prompt": "hello stream", "modelProfile": "balanced"},
    )

    data = assert_envelope(chat.json())
    assert data["answer"]
    assert data["model"]
    assert data["usage"]["totalTokens"] >= 1
    assert data["traceId"]

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in stream.text
    done_line = [line for line in stream.text.splitlines() if line.startswith("data: ")][-1]
    assert json.loads(done_line.removeprefix("data: "))["data"]["traceId"]


def test_react_trace_and_rag_upload_chat_contract() -> None:
    test_client = client()
    upload = test_client.post(
        "/ai/pdf/upload/doc-1",
        headers=AUTH_HEADERS,
        files={"file": ("policy.txt", b"Heat safety requires water rest and shade.", "text/plain")},
    )
    react = test_client.post(
        "/ai/react/chat",
        headers=AUTH_HEADERS,
        json={"chatId": "doc-1", "prompt": "heat safety", "modelProfile": "quality"},
    )
    rag = test_client.post(
        "/ai/pdf/chat",
        headers=AUTH_HEADERS,
        json={"chatId": "doc-1", "prompt": "heat safety", "modelProfile": "quality"},
    )

    assert assert_envelope(upload.json())["status"] == "COMPLETED"

    trace = assert_envelope(react.json())["trace"]
    assert {"step", "thoughtSummary", "action", "actionInput", "observation"} <= set(trace[0])

    rag_data = assert_envelope(rag.json())
    assert rag_data["citations"][0]["source"] == "policy.txt"
    assert {"id", "source", "title", "chunkId", "snippet"} <= set(rag_data["citations"][0])
    assert rag_data["retrievalStats"]["evidenceAccepted"] >= 1


def test_no_evidence_rag_refuses() -> None:
    response = client().post(
        "/ai/pdf/chat",
        headers=AUTH_HEADERS,
        json={"chatId": "missing", "prompt": "unknown", "modelProfile": "balanced"},
    )

    data = assert_envelope(response.json())
    assert "未找到足够证据" in data["answer"]
    assert data["retrievalStats"]["refused"] is True


def test_sessions_feedback_evaluation_cost_and_audit_contract() -> None:
    test_client = client()

    test_client.post("/ai/chat", headers=AUTH_HEADERS, json={"chatId": "session-1", "prompt": "hello", "modelProfile": "balanced"})
    sessions = test_client.get("/ai/sessions", headers=AUTH_HEADERS)
    feedback = test_client.post("/ai/feedback", headers=AUTH_HEADERS, json={"chatId": "session-1", "rating": 1})
    dataset = test_client.post(
        "/ai/evaluation/datasets",
        headers=AUTH_HEADERS,
        json={"name": "contract", "cases": [{"question": "KnowledgeOps", "expectedKeywords": ["KnowledgeOps"]}]},
    )
    run = test_client.post(
        "/ai/evaluation/runs",
        headers=AUTH_HEADERS,
        json={"datasetId": assert_envelope(dataset.json())["datasetId"], "modelProfile": "balanced"},
    )
    budget = test_client.post("/cost/budget", headers=AUTH_HEADERS, json={"monthlyBudgetUsd": 50})
    cost = test_client.get("/cost/summary", headers=AUTH_HEADERS)
    audit = test_client.get("/audit/logs", headers=AUTH_HEADERS)

    assert assert_envelope(sessions.json())[0]["sessionId"] == "session-1"
    assert assert_envelope(feedback.json())["rating"] == 1
    assert assert_envelope(run.json())["status"] == "COMPLETED"
    assert assert_envelope(budget.json())["monthlyBudgetUsd"] == 50
    cost_data = assert_envelope(cost.json())
    assert {"tenantId", "monthCostUsd", "monthlyBudgetUsd", "budgetRemainingUsd"} <= set(cost_data)
    audit_item = assert_envelope(audit.json())[0]
    assert {"tenantId", "principal", "method", "path", "status", "createdAt"} <= set(audit_item)
