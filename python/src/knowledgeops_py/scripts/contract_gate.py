from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from httpx import URL, Response

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
    ("POST", "/ingestion/jobs/process"),
    ("POST", "/ai/pdf/chat"),
    ("GET", "/ai/pdf/chat"),
    ("GET", "/ai/pdf/file/{chatId}"),
    ("GET", "/ai/history/{kind}"),
    ("GET", "/ai/history/{kind}/{chatId}"),
    ("GET", "/ai/sessions"),
    ("GET", "/ai/sessions/{sessionId}"),
    ("PUT", "/ai/sessions/{sessionId}"),
    ("POST", "/ai/sessions/{sessionId}/pin"),
    ("POST", "/ai/sessions/{sessionId}/archive"),
    ("POST", "/ai/sessions/{sessionId}/branches/compare"),
    ("POST", "/ai/sessions/{sessionId}/branches/merge"),
    ("POST", "/ai/feedback"),
    ("GET", "/ai/evaluation/datasets"),
    ("POST", "/ai/evaluation/runs"),
    ("GET", "/ai/evaluation/datasets/{datasetId}/comparison"),
    ("GET", "/ai/evaluation/runs/{runId}/report"),
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
    ("GET", "/ai/workflow/tasks/{taskId}/events"),
    ("POST", "/ai/research/tasks"),
    ("GET", "/ai/research/tasks/{taskId}"),
    ("GET", "/ai/research/tasks/{taskId}/events"),
    ("GET", "/ai/research/tasks/{taskId}/report"),
    ("POST", "/ai/memory/items"),
    ("GET", "/ai/memory/items"),
    ("POST", "/ai/graph/entities"),
    ("GET", "/ai/graph/entities"),
    ("POST", "/ai/graph/relations"),
    ("GET", "/ai/graph/entities/{entityId}/neighbors"),
    ("POST", "/ai/graph/facts"),
    ("GET", "/ai/graph/facts"),
]


class LegacyTestClient(TestClient):
    """Exercise the explicitly versioned Python-envelope compatibility surface."""

    def request(self, method: str, url: str | URL, *args: Any, **kwargs: Any) -> Response:
        if isinstance(url, str) and url.startswith("/") and not url.startswith("/python/v1/"):
            url = f"/python/v1{url}"
        return super().request(method, url, *args, **kwargs)


def main() -> None:
    app = create_app()
    client = TestClient(app)
    legacy_client = LegacyTestClient(app)
    failures: list[str] = []
    failures.extend(check_openapi(client))
    failures.extend(check_runtime_contract(client, legacy_client))
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"python enterprise contract gate ok: {len(REQUIRED_OPENAPI_ENDPOINTS)} OpenAPI endpoints plus canonical and legacy checks")


def check_openapi(client: TestClient) -> list[str]:
    response = client.get("/v3/api-docs")
    data = response.json()
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


def check_runtime_contract(client: TestClient, legacy_client: LegacyTestClient) -> list[str]:
    failures: list[str] = []
    token_response = client.post("/auth/token", headers=AUTH_HEADERS)
    token = token_response.json()
    if not token.get("token") or not token.get("refreshToken"):
        failures.append("auth token response missing token/refreshToken")
    if "data" in token or token.get("ok") != 1:
        failures.append("canonical auth token response retained the Python envelope")
    refresh = client.post("/auth/refresh", headers={"X-Refresh-Token": token["refreshToken"]}).json()
    if not refresh.get("token"):
        failures.append("refresh response missing token")
    api_key = client.post("/auth/api-keys?keyName=contract-user&role=USER", headers=AUTH_HEADERS).json()
    if "data" in api_key or not api_key.get("rawApiKey"):
        failures.append("canonical api key response did not match ApiKeyIssueVO")
    health = client.get("/actuator/health").json()
    if health.get("status") != "UP" or "data" in health:
        failures.append("canonical health response retained the Python envelope")
    prometheus = client.get("/actuator/prometheus", headers=AUTH_HEADERS)
    if prometheus.status_code != 200 or "knowledgeops_python_up 1" not in prometheus.text:
        failures.append("canonical Prometheus endpoint did not return native metrics")
    metrics = client.get("/metrics", headers=AUTH_HEADERS).json()
    if "data" in metrics or "prometheus" not in metrics:
        failures.append("canonical metrics response retained the Python envelope")

    chat_body = {"chatId": "contract-chat", "prompt": "contract smoke", "modelProfile": "balanced"}
    chat = client.post("/ai/chat", headers=AUTH_HEADERS, json=chat_body)
    if chat.status_code != 200 or not chat.text:
        failures.append("canonical chat response did not return Java text output")
    query_chat = client.post("/ai/chat?prompt=query-contract&chatId=query-chat&modelProfile=quality", headers=AUTH_HEADERS)
    if query_chat.status_code != 200 or not query_chat.text:
        failures.append("canonical chat did not accept Java query parameters")
    legacy_chat = envelope_data(legacy_client.post("/ai/chat", headers=AUTH_HEADERS, json=chat_body))
    if not legacy_chat.get("answer"):
        failures.append("legacy /python/v1 chat adapter returned no answer")
    assert_raw_chat_sse(failures, "canonical chat stream", client.post("/ai/chat/stream", headers=AUTH_HEADERS, json=chat_body).text)
    assert_sse(failures, "legacy chat stream", legacy_client.post("/ai/chat/stream", headers=AUTH_HEADERS, json=chat_body).text)
    react = client.post("/ai/react/chat", headers=AUTH_HEADERS, json=chat_body).json()
    if "data" in react:
        failures.append("canonical react response retained the Python envelope")
    assert_keys(failures, "react trace", react["trace"][0], ["step", "thoughtSummary", "action", "actionInput", "observation"])
    assert_react_sse(failures, "canonical react stream", client.post("/ai/react/chat/stream", headers=AUTH_HEADERS, json=chat_body).text)
    assert_sse(failures, "legacy react stream", legacy_client.post("/ai/react/chat/stream", headers=AUTH_HEADERS, json=chat_body).text)
    assert_react_sse(
        failures,
        "canonical workflow react stream",
        client.post("/ai/workflow/react/chat/stream", headers=AUTH_HEADERS, json=chat_body).text,
    )

    upload = client.post(
        "/ai/pdf/upload/contract-rag",
        headers=AUTH_HEADERS,
        files={"file": ("contract.txt", b"Contract evidence includes citations and heat safety.", "text/plain")},
    ).json()
    if upload.get("ok") != 1 or not upload.get("job"):
        failures.append("canonical upload response did not match IngestionSubmitVO")
    job_id = upload["job"]["jobId"]
    client.post(
        "/ingestion/upload/contract-rag-2",
        headers=AUTH_HEADERS,
        files={"file": ("second.txt", b"second document", "text/plain")},
    )
    jobs = client.get("/ingestion/jobs?chatId=contract-rag", headers=AUTH_HEADERS).json()
    if not isinstance(jobs, list):
        failures.append("canonical ingestion jobs response retained the Python envelope")
    job = client.get(f"/ingestion/jobs/{job_id}", headers=AUTH_HEADERS).json()
    if set(job) != {
        "jobId", "chatId", "sourceName", "status", "attemptCount", "maxRetries", "errorMessage",
        "traceId", "queueBackend", "createdAt", "startedAt", "finishedAt",
    } or job.get("jobId") != job_id or job.get("status") not in {"PENDING", "SUCCEEDED"}:
        failures.append("canonical ingestion job response did not return IngestionJobVO")

    rag = envelope_data(legacy_client.post("/ai/pdf/chat", headers=AUTH_HEADERS, json={"chatId": "contract-rag", "prompt": "citations heat", "modelProfile": "quality"}))
    assert_keys(failures, "rag", rag, ["answer", "citations", "evidence", "retrievalStats"])
    assert_keys(failures, "citation", rag["citations"][0], ["id", "source", "title", "chunkId", "snippet"])
    query_rag = client.post("/ai/pdf/chat?prompt=citations%20heat&chatId=contract-rag", headers=AUTH_HEADERS)
    if query_rag.status_code != 200 or not query_rag.text:
        failures.append("canonical PDF chat did not accept Java query parameters")

    sessions = client.get("/ai/sessions", headers=AUTH_HEADERS).json()
    if "data" in sessions or not {"items", "total", "page", "pageSize"} <= set(sessions):
        failures.append("canonical sessions response did not match PagedResult")
    branch_state = client.put(
        "/ai/sessions/contract-branches",
        headers=AUTH_HEADERS,
        json={
            "title": "Contract branches",
            "branches": [
                {"id": "source", "messages": [{"role": "user", "content": "shared"}, {"role": "assistant", "content": "source"}]},
                {"id": "target", "messages": [{"role": "user", "content": " shared "}, {"role": "assistant", "content": "target"}]},
            ],
            "activeBranchId": "target",
        },
    ).json()
    if "data" in branch_state or branch_state.get("id") != "contract-branches":
        failures.append("canonical session upsert did not match AgentSessionStateVO")
    branch_compare = client.post(
        "/ai/sessions/contract-branches/branches/compare",
        headers=AUTH_HEADERS,
        json={"sourceBranchId": "source", "targetBranchId": "target"},
    ).json()
    if branch_compare.get("commonMessageCount") != 1 or branch_compare.get("sourceOnlyPreview") != ["source"]:
        failures.append("canonical branch comparison did not match BranchCompareResultVO")
    branch_merge = client.post(
        "/ai/sessions/contract-branches/branches/merge",
        headers=AUTH_HEADERS,
        json={"sourceBranchId": "source", "targetBranchId": "target"},
    ).json()
    if set(branch_merge) != {"session", "mergedBranch", "mergedMessageCount"} or branch_merge.get("mergedMessageCount") != 3:
        failures.append("canonical branch merge did not match BranchMergeResultVO")
    feedback = client.post("/ai/feedback", headers=AUTH_HEADERS, json={"chatId": "contract-chat", "rating": 1}).json()
    if feedback.get("ok") != 1 or feedback.get("data") is not None:
        failures.append("canonical feedback response did not match Result")
    datasets = client.get("/ai/evaluation/datasets", headers=AUTH_HEADERS).json()
    if not datasets or "cases" in datasets[0] or "caseCount" not in datasets[0]:
        failures.append("canonical evaluation dataset response did not match EvalDatasetVO")
    run = client.post("/ai/evaluation/runs", headers=AUTH_HEADERS, json={"datasetId": datasets[0]["datasetId"], "modelProfile": "balanced"}).json()
    if run.get("status") != "SUCCESS":
        failures.append("evaluation run did not complete")
    client.post(f"/ai/evaluation/runs/{run['runId']}/baseline", headers=AUTH_HEADERS)
    comparison = client.get(f"/ai/evaluation/datasets/{datasets[0]['datasetId']}/comparison", headers=AUTH_HEADERS).json()
    if set(comparison) != {"dataset", "baseline", "current"} or "cases" in comparison["dataset"]:
        failures.append("canonical evaluation comparison did not match EvalComparisonVO")
    report = client.get(f"/ai/evaluation/runs/{run['runId']}/report", headers=AUTH_HEADERS)
    if report.headers.get("content-disposition") != f'attachment; filename="rag-evaluation-{run["runId"]}.md"':
        failures.append("canonical evaluation report did not match Java download contract")
    cost = client.get("/cost/summary", headers=AUTH_HEADERS).json()
    assert_keys(
        failures,
        "cost",
        cost,
        [
            "tenantId",
            "month",
            "monthlyBudgetUsd",
            "hardLimitEnabled",
            "monthCostUsd",
            "monthRequestCount",
            "monthInputTokens",
            "monthOutputTokens",
            "todayCostUsd",
            "todayRequestCount",
            "budgetRemainingUsd",
            "budgetExceeded",
        ],
    )
    client.post("/cost/budget", headers=AUTH_HEADERS, json={"monthlyBudgetUsd": 30})
    audit = client.get("/audit/logs", headers=AUTH_HEADERS).json()
    if audit:
        assert_keys(failures, "audit", audit[0], ["tenantId", "principal", "method", "path", "status", "createdAt"])
    harness = client.get("/ai/harness/actions", headers=AUTH_HEADERS).json()
    expected_harness_fields = {"action", "runtime", "requiredFields", "optionalFields", "sensitiveFields", "riskLevel", "trustedOnly"}
    if not isinstance(harness, list) or "data" in harness or len(harness) != 11:
        failures.append("canonical harness response did not return the Java schema list")
    elif any(set(schema) != expected_harness_fields for schema in harness):
        failures.append("canonical harness schema fields do not match ActionSchema")
    preview = client.post(
        "/ai/harness/actions/preview",
        headers=AUTH_HEADERS,
        json={"action": "workspace_run_shell", "actionInput": {"command": "pwd"}},
    ).json()
    if set(preview) != {"ok", "token", "action", "expiresAt", "preview"} or preview.get("ok") != 1:
        failures.append("canonical harness preview did not return TrustedActionPreviewResponse")
    elif preview.get("preview", {}).get("actionInput", {}).get("command") != "[REDACTED]":
        failures.append("canonical harness preview did not redact sensitive command input")
    else:
        observation = client.post(f"/ai/harness/actions/execute/{preview['token']}", headers=AUTH_HEADERS).json()
        if observation != {
            "status": "error",
            "source": "policy",
            "latencyMs": 0,
            "message": "trusted runtime is disabled",
        }:
            failures.append("canonical harness execution did not return the Java policy observation")
    return failures


def envelope_data(response: Response) -> Any:
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


def assert_raw_chat_sse(failures: list[str], label: str, text: str) -> None:
    if not text.startswith("data: ") or "event:" in text:
        failures.append(f"{label} did not return Java raw text SSE")


def assert_react_sse(failures: list[str], label: str, text: str) -> None:
    events = [line.removeprefix("event: ") for line in text.splitlines() if line.startswith("event: ")]
    payloads = [json.loads(line.removeprefix("data: ")) for line in text.splitlines() if line.startswith("data: ")]
    if not {"trace", "token", "done"} <= set(events):
        failures.append(f"{label} missing trace/token/done events")
        return
    done = payloads[-1]
    if done.get("ok") != 1 or "data" in done or not done.get("chatId"):
        failures.append(f"{label} done event did not match ReactChatResponseVO")


if __name__ == "__main__":
    main()
