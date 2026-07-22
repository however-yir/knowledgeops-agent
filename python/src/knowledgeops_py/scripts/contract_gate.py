from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app

AUTH_HEADERS = {"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "public"}

REQUIRED_OPENAPI_ENDPOINTS = [
    ("POST", "/auth/token"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/api-keys"),
    ("POST", "/auth/api-keys/rotate"),
    ("POST", "/auth/api-keys/revoke"),
    ("GET", "/auth/oidc/login"),
    ("GET", "/auth/oidc/callback"),
    ("POST", "/auth/oidc/exchange"),
    ("POST", "/auth/logout"),
    ("GET", "/actuator/health"),
    ("GET", "/health"),
    ("GET", "/actuator/prometheus"),
    ("GET", "/metrics"),
    ("POST", "/ai/chat"),
    ("POST", "/ai/chat/stream"),
    ("POST", "/ai/react/chat"),
    ("POST", "/ai/react/chat/stream"),
    ("POST", "/ai/pdf/upload/{chatId}"),
    ("POST", "/ingestion/upload/{chatId}"),
    ("GET", "/ingestion/jobs"),
    ("GET", "/ingestion/jobs/{jobId}"),
    ("POST", "/ai/pdf/chat"),
    ("GET", "/ai/pdf/chat"),
    ("GET", "/ai/pdf/file/{chatId}"),
    ("GET", "/ai/history/{kind}"),
    ("GET", "/ai/history/{kind}/{chatId}"),
    ("GET", "/ai/sessions"),
    ("GET", "/ai/sessions/{sessionId}"),
    ("POST", "/ai/feedback"),
    ("GET", "/ai/evaluation/datasets"),
    ("POST", "/ai/evaluation/runs"),
    ("GET", "/audit/logs"),
    ("GET", "/cost/summary"),
    ("POST", "/cost/budget"),
    ("GET", "/ai/harness/actions"),
    ("POST", "/ai/harness/actions/preview"),
    ("POST", "/ai/harness/actions/execute/{token}"),
    ("POST", "/ai/workflow/react/chat"),
    ("POST", "/ai/workflow/react/chat/stream"),
    ("GET", "/ai/workflow/tasks"),
    ("GET", "/ai/workflow/tasks/{taskId}"),
    ("GET", "/ai/research/tasks/{taskId}"),
    ("POST", "/ai/memory/items"),
    ("GET", "/ai/memory/items"),
    ("POST", "/ai/graph/entities"),
    ("GET", "/ai/graph/entities"),
    ("POST", "/ai/graph/relations"),
    ("GET", "/ai/graph/entities/{entityId}/neighbors"),
    ("POST", "/ai/graph/facts"),
    ("GET", "/ai/graph/facts"),
]


def main() -> None:
    client = TestClient(create_app())
    failures: list[str] = []
    failures.extend(check_openapi(client))
    failures.extend(check_runtime_contract(client))
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"python enterprise contract gate ok: {len(REQUIRED_OPENAPI_ENDPOINTS)} OpenAPI endpoints plus runtime envelope checks")


def check_openapi(client: TestClient) -> list[str]:
    response = client.get("/v3/api-docs")
    data = envelope_data(response)
    paths = data["paths"]
    failures = []
    for method, path in REQUIRED_OPENAPI_ENDPOINTS:
        methods = paths.get(path)
        if not methods or method.lower() not in methods:
            failures.append(f"OpenAPI missing {method} {path}")
    schemas = data.get("components", {}).get("schemas", {})
    for schema in ["ChatRequestDto", "ChatResponseDto", "RagResponseDto", "CitationDto", "AgentTraceDto", "CostSummaryDto", "AuditLogDto"]:
        if schema not in schemas:
            failures.append(f"OpenAPI missing schema {schema}")
    return failures


def check_runtime_contract(client: TestClient) -> list[str]:
    failures: list[str] = []
    token = envelope_data(client.post("/auth/token", headers=AUTH_HEADERS))
    if not token.get("token") or not token.get("refreshToken"):
        failures.append("auth token response missing token/refreshToken")
    refresh = envelope_data(client.post("/auth/refresh", headers={"X-Refresh-Token": token["refreshToken"]}))
    if not refresh.get("token"):
        failures.append("refresh response missing token")
    envelope_data(client.post("/auth/api-keys?keyName=contract-user&role=USER", headers=AUTH_HEADERS))
    envelope_data(client.get("/actuator/health"))
    prometheus = client.get("/actuator/prometheus", headers=AUTH_HEADERS)
    if prometheus.status_code != 200 or "knowledgeops_python_up 1" not in prometheus.text:
        failures.append("canonical Prometheus endpoint did not return native metrics")
    envelope_data(client.get("/metrics", headers=AUTH_HEADERS))

    chat_body = {"chatId": "contract-chat", "prompt": "contract smoke", "modelProfile": "balanced"}
    chat = envelope_data(client.post("/ai/chat", headers=AUTH_HEADERS, json=chat_body))
    legacy_chat = envelope_data(client.post("/python/v1/ai/chat", headers=AUTH_HEADERS, json=chat_body))
    if not legacy_chat.get("answer"):
        failures.append("legacy /python/v1 chat adapter returned no answer")
    assert_keys(failures, "chat", chat, ["answer", "model", "usage", "traceId"])
    assert_sse(failures, "chat stream", client.post("/ai/chat/stream", headers=AUTH_HEADERS, json=chat_body).text)
    react = envelope_data(client.post("/ai/react/chat", headers=AUTH_HEADERS, json=chat_body))
    assert_keys(failures, "react trace", react["trace"][0], ["step", "thoughtSummary", "action", "actionInput", "observation"])
    assert_sse(failures, "react stream", client.post("/ai/react/chat/stream", headers=AUTH_HEADERS, json=chat_body).text)

    upload = envelope_data(
        client.post(
            "/ai/pdf/upload/contract-rag",
            headers=AUTH_HEADERS,
            files={"file": ("contract.txt", b"Contract evidence includes citations and heat safety.", "text/plain")},
        )
    )
    job_id = upload["jobId"]
    envelope_data(client.post("/ingestion/upload/contract-rag-2", headers=AUTH_HEADERS, content=b"second document"))
    envelope_data(client.get("/ingestion/jobs", headers=AUTH_HEADERS))
    envelope_data(client.get(f"/ingestion/jobs/{job_id}", headers=AUTH_HEADERS))

    rag = envelope_data(client.post("/ai/pdf/chat", headers=AUTH_HEADERS, json={"chatId": "contract-rag", "prompt": "citations heat", "modelProfile": "quality"}))
    assert_keys(failures, "rag", rag, ["answer", "citations", "evidence", "retrievalStats"])
    assert_keys(failures, "citation", rag["citations"][0], ["id", "source", "title", "chunkId", "snippet"])

    envelope_data(client.get("/ai/sessions", headers=AUTH_HEADERS))
    envelope_data(client.get("/ai/sessions/contract-chat", headers=AUTH_HEADERS))
    envelope_data(client.post("/ai/feedback", headers=AUTH_HEADERS, json={"chatId": "contract-chat", "rating": 1}))
    datasets = envelope_data(client.get("/ai/evaluation/datasets", headers=AUTH_HEADERS))
    run = envelope_data(client.post("/ai/evaluation/runs", headers=AUTH_HEADERS, json={"datasetId": datasets[0]["datasetId"], "modelProfile": "balanced"}))
    if run.get("status") != "COMPLETED":
        failures.append("evaluation run did not complete")
    cost = envelope_data(client.get("/cost/summary", headers=AUTH_HEADERS))
    assert_keys(failures, "cost", cost, ["tenantId", "monthCostUsd", "monthlyBudgetUsd", "budgetRemainingUsd"])
    envelope_data(client.post("/cost/budget", headers=AUTH_HEADERS, json={"monthlyBudgetUsd": 30}))
    audit = envelope_data(client.get("/audit/logs", headers=AUTH_HEADERS))
    if audit:
        assert_keys(failures, "audit", audit[0], ["tenantId", "principal", "method", "path", "status", "createdAt"])
    envelope_data(client.get("/ai/harness/actions", headers=AUTH_HEADERS))
    return failures


def envelope_data(response) -> Any:
    payload = response.json()
    if response.status_code >= 400 or payload.get("ok") != 1 or "data" not in payload or "msg" not in payload:
        raise AssertionError(f"invalid envelope: {response.status_code} {payload}")
    return payload["data"]


def assert_keys(failures: list[str], label: str, value: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        failures.append(f"{label} missing keys: {', '.join(missing)}")


def assert_sse(failures: list[str], label: str, text: str) -> None:
    if "event: done" not in text:
        failures.append(f"{label} missing done event")
        return
    done = [line for line in text.splitlines() if line.startswith("data: ")][-1].removeprefix("data: ")
    payload = json.loads(done)
    if payload.get("ok") != 1 or "data" not in payload:
        failures.append(f"{label} done event is not an envelope")


if __name__ == "__main__":
    main()
