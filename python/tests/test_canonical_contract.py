from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from knowledgeops_py.app import PlatformStore, RequestContext, chat_response_with_provider, create_app
from knowledgeops_py.config import Settings
from knowledgeops_py.dto import ChatRequestDto

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
    assert {
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
    } <= set(cost.json())
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


def test_canonical_session_branches_match_java_compare_and_merge_contracts() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    state = {
        "title": "Branch session",
        "workspaceId": "team",
        "streaming": False,
        "activeBranchId": "target",
        "branches": [
            {
                "id": "source",
                "title": "Source",
                "messages": [
                    {"id": "source-common", "role": "user", "content": "common message"},
                    {"id": "source-only", "role": "assistant", "content": "source only"},
                ],
            },
            {
                "id": "target",
                "title": "Target",
                "messages": [
                    {"id": "target-common", "role": "user", "content": " common   message "},
                    {"id": "target-only", "role": "assistant", "content": "target only"},
                ],
            },
        ],
    }

    missing = client.get("/ai/sessions/missing", headers=AUTH_HEADERS)
    saved = client.put("/ai/sessions/branch-session", headers=AUTH_HEADERS, json=state)
    defaulted = client.put(
        "/ai/sessions/defaulted-session",
        headers=AUTH_HEADERS,
        json={"title": "   ", "workspaceId": " ", "activeBranchId": " ", "branches": [{"id": "fallback"}]},
    )
    comparison = client.post(
        "/ai/sessions/branch-session/branches/compare",
        headers=AUTH_HEADERS,
        json={"sourceBranchId": "source", "targetBranchId": "target"},
    )
    merged = client.post(
        "/ai/sessions/branch-session/branches/merge",
        headers=AUTH_HEADERS,
        json={"sourceBranchId": "source", "targetBranchId": "target", "title": "Merged"},
    )

    assert missing.status_code == 400
    assert missing.json()["msg"] == "session not found"
    assert set(saved.json()) == {
        "id",
        "title",
        "updatedAt",
        "modelProfile",
        "streaming",
        "pinned",
        "archived",
        "workspaceId",
        "activeBranchId",
        "branches",
    }
    assert saved.json()["workspaceId"] == "team"
    assert defaulted.json()["title"] == "新会话"
    assert defaulted.json()["workspaceId"] == "default"
    assert defaulted.json()["activeBranchId"] == "fallback"
    assert comparison.json() == {
        "sourceBranchId": "source",
        "targetBranchId": "target",
        "sourceMessageCount": 2,
        "targetMessageCount": 2,
        "commonMessageCount": 1,
        "sourceOnlyCount": 1,
        "targetOnlyCount": 1,
        "sourceOnlyPreview": ["source only"],
        "targetOnlyPreview": ["target only"],
    }
    assert set(merged.json()) == {"session", "mergedBranch", "mergedMessageCount"}
    assert merged.json()["mergedMessageCount"] == 3
    assert merged.json()["mergedBranch"]["title"] == "Merged"
    assert merged.json()["session"]["activeBranchId"] == merged.json()["mergedBranch"]["id"]


def test_canonical_evaluation_datasets_hide_cases_behind_java_summary_dto() -> None:
    response = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a"))).get(
        "/ai/evaluation/datasets", headers=AUTH_HEADERS
    )

    dataset = response.json()[0]
    assert {"datasetId", "tenantId", "name", "description", "baselineRunId", "caseCount", "createdAt", "updatedAt"} <= set(dataset)
    assert "cases" not in dataset


def test_canonical_ingestion_matches_java_job_lifecycle_and_admin_contract() -> None:
    client = TestClient(
        create_app(
            Settings(demo_api_key="test-key", demo_tenant_id="tenant-a", ingestion_queue_backend="db_polling")
        )
    )

    missing_chat = client.get("/ingestion/jobs", headers=AUTH_HEADERS)
    missing_file = client.post("/ingestion/upload/ingestion-contract", headers=AUTH_HEADERS, content=b"not multipart")
    assert missing_chat.status_code == 400 and missing_chat.json()["msg"] == "chatId is required"
    assert missing_file.status_code == 400 and missing_file.json()["msg"] == "file is required"

    upload_headers = AUTH_HEADERS | {"X-Idempotency-Key": "ingestion-contract-key"}
    first = client.post(
        "/ingestion/upload/ingestion-contract",
        headers=upload_headers,
        files={"file": ("policy.txt", b"Water and shade prevent heat injury.", "text/plain")},
    ).json()
    duplicate = client.post(
        "/ingestion/upload/ingestion-contract",
        headers=upload_headers,
        files={"file": ("policy.txt", b"different body is ignored by the client key", "text/plain")},
    ).json()
    job_id = first["job"]["jobId"]

    assert first["ok"] == duplicate["ok"] == 1
    assert duplicate["job"]["jobId"] == job_id
    assert first["job"]["status"] == "PENDING"
    assert first["job"]["startedAt"] is None and first["job"]["finishedAt"] is None

    jobs = client.get("/ingestion/jobs?chatId=ingestion-contract", headers=AUTH_HEADERS).json()
    assert len(jobs) == 1 and jobs[0]["jobId"] == job_id
    assert set(jobs[0]) == {
        "jobId", "chatId", "sourceName", "status", "attemptCount", "maxRetries", "errorMessage",
        "traceId", "queueBackend", "createdAt", "startedAt", "finishedAt",
    }
    assert not jobs[0]["createdAt"].endswith("Z")

    user_key = client.post("/auth/api-keys?keyName=ingestion-user&role=USER", headers=AUTH_HEADERS).json()["rawApiKey"]
    denied = client.post("/ingestion/jobs/process", headers={"X-API-Key": user_key})
    processed = client.post(f"/ingestion/jobs/process?jobId={job_id}", headers=AUTH_HEADERS)
    completed = client.get(f"/ingestion/jobs/{job_id}", headers=AUTH_HEADERS).json()
    requeued = client.post("/ingestion/jobs/process", headers=AUTH_HEADERS)

    assert denied.status_code == 403 and denied.json()["msg"] == "permission denied"
    assert processed.json() == {"ok": 1, "msg": "processed", "job": None}
    assert completed["status"] == "SUCCEEDED"
    assert completed["startedAt"] is not None and completed["finishedAt"] is not None
    assert requeued.json() == {"ok": 1, "msg": "requeue=0", "job": None}


def test_canonical_workflow_and_research_match_java_task_and_event_contracts() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    body = {"chatId": "workflow-contract", "prompt": "plan a heat safety response", "modelProfile": "quality"}

    legacy_workflow = client.post("/python/v1/ai/workflow/react/chat", headers=AUTH_HEADERS, json=body).json()["data"]
    task_id = legacy_workflow["taskId"]
    tasks = client.get("/ai/workflow/tasks?page=1&pageSize=20", headers=AUTH_HEADERS)
    task = client.get(f"/ai/workflow/tasks/{task_id}", headers=AUTH_HEADERS)
    events = client.get(f"/ai/workflow/tasks/{task_id}/events", headers=AUTH_HEADERS)
    missing_task = client.get("/ai/workflow/tasks/missing", headers=AUTH_HEADERS)
    missing_events = client.get("/ai/workflow/tasks/missing/events", headers=AUTH_HEADERS)

    task_fields = {
        "taskId", "tenantId", "type", "status", "userInput", "finalOutput", "modelProfile", "chatId",
        "sessionId", "createdAt", "updatedAt", "steps", "events",
    }
    event_fields = {"eventId", "taskId", "stepId", "eventType", "payload", "createdAt"}
    assert isinstance(tasks.json(), list) and tasks.json()[0]["taskId"] == task_id
    assert set(task.json()) == task_fields and task.json()["status"] == "DONE"
    assert set(events.json()[0]) == event_fields
    assert missing_task.status_code == 404 and missing_task.json() == {"ok": 0, "msg": "task not found"}
    assert missing_events.json() == []

    research = client.post("/ai/research/tasks", headers=AUTH_HEADERS, json={"topic": "Heat safety", "modelProfile": "quality"})
    research_id = research.json()["taskId"]
    research_task = client.get(f"/ai/research/tasks/{research_id}", headers=AUTH_HEADERS)
    research_events = client.get(f"/ai/research/tasks/{research_id}/events", headers=AUTH_HEADERS)
    report = client.get(f"/ai/research/tasks/{research_id}/report", headers=AUTH_HEADERS)

    assert set(research.json()) == {"taskId", "topic", "report", "status"}
    assert research.json()["status"] == "DONE"
    assert set(research_task.json()) == task_fields and research_task.json()["type"] == "DEEP_RESEARCH"
    assert isinstance(research_events.json(), list) and set(research_events.json()[0]) == event_fields
    assert report.json() == {"taskId": research_id, "report": research.json()["report"]}


def test_canonical_harness_matches_java_schema_token_and_workspace_policy(tmp_path) -> None:
    (tmp_path / "note.txt").write_text("tenant-scoped workspace note\n", encoding="utf-8")
    client = TestClient(
        create_app(
            Settings(
                demo_api_key="test-key",
                demo_tenant_id="tenant-a",
                trusted_runtime_enabled=True,
                workspace_root=str(tmp_path),
                trusted_runtime_tenant_allowed_actions={
                    "tenant-a": ("workspace_read_file", "workspace_propose_patch", "workspace_apply_patch")
                },
            )
        )
    )

    schemas = client.get("/ai/harness/actions", headers=AUTH_HEADERS)
    assert schemas.status_code == 200
    assert {schema["action"] for schema in schemas.json()} == {
        "query_school",
        "query_course",
        "add_course_reservation",
        "rag_search",
        "mcp_call",
        "workspace_list_files",
        "workspace_read_file",
        "workspace_search_text",
        "workspace_propose_patch",
        "workspace_apply_patch",
        "workspace_run_shell",
    }
    assert set(schemas.json()[0]) == {
        "action", "runtime", "requiredFields", "optionalFields", "sensitiveFields", "riskLevel", "trustedOnly"
    }
    assert client.post("/ai/harness/actions/preview", headers=AUTH_HEADERS, json={}).json()["msg"] == "action is required"

    read_preview = client.post(
        "/ai/harness/actions/preview",
        headers=AUTH_HEADERS,
        json={"action": "workspace_read_file", "actionInput": {"path": "note.txt"}},
    )
    assert set(read_preview.json()) == {"ok", "token", "action", "expiresAt", "preview"}
    assert read_preview.json()["preview"] == {
        "status": "pending_confirmation",
        "source": "workspace",
        "action": "workspace_read_file",
        "actionInput": {"path": "note.txt"},
    }
    read = client.post(f"/ai/harness/actions/execute/{read_preview.json()['token']}", headers=AUTH_HEADERS)
    assert read.json()["status"] == "success"
    assert read.json()["content"] == "tenant-scoped workspace note\n"
    assert client.post(f"/ai/harness/actions/execute/{read_preview.json()['token']}", headers=AUTH_HEADERS).json() == {
        "status": "error",
        "source": "trusted-action",
        "latencyMs": 0,
        "message": "trusted action token not found",
    }

    escaped = client.post(
        "/ai/harness/actions/preview",
        headers=AUTH_HEADERS,
        json={"action": "workspace_read_file", "actionInput": {"path": "../secret.txt"}},
    )
    escaped_result = client.post(f"/ai/harness/actions/execute/{escaped.json()['token']}", headers=AUTH_HEADERS)
    assert escaped_result.json()["source"] == "workspace"
    assert "path escapes workspace root" in escaped_result.json()["message"]

    patch_preview = client.post(
        "/ai/harness/actions/preview",
        headers=AUTH_HEADERS,
        json={"action": "workspace_apply_patch", "actionInput": {"path": "new.txt", "content": "draft"}},
    )
    assert patch_preview.json()["preview"]["applyAction"] == "workspace_apply_patch"
    denied_write = client.post(f"/ai/harness/actions/execute/{patch_preview.json()['token']}", headers=AUTH_HEADERS)
    assert denied_write.json()["message"] == "workspace writes are disabled"

    tenant_denied = client.post(
        "/ai/harness/actions/preview",
        headers=AUTH_HEADERS,
        json={"action": "workspace_list_files", "actionInput": {}},
    )
    denied = client.post(f"/ai/harness/actions/execute/{tenant_denied.json()['token']}", headers=AUTH_HEADERS)
    assert denied.json()["message"] == "action is not allowed for tenant: workspace_list_files"


def test_canonical_evaluation_comparison_and_report_match_java_contract() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    dataset_id = client.get("/ai/evaluation/datasets", headers=AUTH_HEADERS).json()[0]["datasetId"]
    run = client.post(
        "/ai/evaluation/runs", headers=AUTH_HEADERS, json={"datasetId": dataset_id, "modelProfile": "balanced"}
    ).json()
    client.post(f"/ai/evaluation/runs/{run['runId']}/baseline", headers=AUTH_HEADERS)

    comparison = client.get(f"/ai/evaluation/datasets/{dataset_id}/comparison", headers=AUTH_HEADERS)
    report = client.get(f"/ai/evaluation/runs/{run['runId']}/report", headers=AUTH_HEADERS)

    assert set(comparison.json()) == {"dataset", "baseline", "current"}
    assert "cases" not in comparison.json()["dataset"]
    assert comparison.json()["baseline"]["runId"] == run["runId"]
    assert comparison.json()["current"]["status"] == "SUCCESS"
    assert report.headers["content-disposition"] == f'attachment; filename="rag-evaluation-{run["runId"]}.md"'
    assert report.headers["content-type"].startswith("text/markdown")
    assert report.text.startswith("# RAG Evaluation Report\n")


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


@pytest.mark.parametrize("path", ["/ai/react/chat/stream", "/ai/workflow/react/chat/stream"])
def test_canonical_react_sse_returns_java_error_event_for_provider_failure(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    async def provider_failure(*args: object, **kwargs: object) -> None:
        raise HTTPException(status_code=502, detail="model provider request failed")

    monkeypatch.setattr("knowledgeops_py.app.chat_response_with_provider", provider_failure)
    response = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a"))).post(
        path,
        headers=AUTH_HEADERS,
        json={"chatId": "react-failure", "prompt": "hello", "modelProfile": "balanced"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert json.loads([line.removeprefix("data: ") for line in response.text.splitlines() if line.startswith("data: ")][0]) == {
        "message": "model provider request failed"
    }


@pytest.mark.parametrize("mode", ["react", "workflow"])
def test_production_react_provider_failure_uses_java_planner_fallback(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    class FailingProvider:
        async def complete(self, *args: object, **kwargs: object) -> dict[str, object]:
            request = httpx.Request("POST", "https://provider.example.test/chat/completions")
            raise httpx.HTTPStatusError("provider unavailable", request=request, response=httpx.Response(503, request=request))

    monkeypatch.setattr("knowledgeops_py.app.create_chat_provider", lambda _settings: FailingProvider())
    response = asyncio.run(
        chat_response_with_provider(
            PlatformStore(),
            RequestContext("trace", "tenant-a", "tester", ["USER"], [], "api_key"),
            ChatRequestDto(chatId="fallback", prompt="contract provider failure", modelProfile="balanced"),
            mode,
            False,
            Settings(environment="production"),
        )
    )

    assert response.answer == f"KnowledgeOps Python {mode} answer: contract provider failure"


def test_production_standard_chat_still_reports_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def complete(self, *args: object, **kwargs: object) -> dict[str, object]:
            request = httpx.Request("POST", "https://provider.example.test/chat/completions")
            raise httpx.HTTPStatusError("provider unavailable", request=request, response=httpx.Response(503, request=request))

    monkeypatch.setattr("knowledgeops_py.app.create_chat_provider", lambda _settings: FailingProvider())

    with pytest.raises(HTTPException, match="model provider request failed"):
        asyncio.run(
            chat_response_with_provider(
                PlatformStore(),
                RequestContext("trace", "tenant-a", "tester", ["USER"], [], "api_key"),
                ChatRequestDto(chatId="failure", prompt="provider failure", modelProfile="balanced"),
                "chat",
                False,
                Settings(environment="production"),
            )
        )


def test_canonical_chat_stream_is_raw_text_while_python_v1_keeps_named_events() -> None:
    client = TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))
    body = {"chatId": "chat-stream", "prompt": "hello", "modelProfile": "balanced"}

    canonical = client.post("/ai/chat/stream", headers=AUTH_HEADERS, json=body).text
    legacy = client.post("/python/v1/ai/chat/stream", headers=AUTH_HEADERS, json=body).text

    assert canonical.startswith("data: ")
    assert "event:" not in canonical
    assert "event: done" in legacy
