from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app, score_evaluation_case
from knowledgeops_py.config import Settings, load_settings
from knowledgeops_py.infrastructure.database import create_engine
from knowledgeops_py.infrastructure.models import Base

AUTH_HEADERS = {"X-API-Key": "test-key", "X-Tenant-ID": "tenant-a"}


class LegacyTestClient(TestClient):
    """Keep the existing Python-envelope tests on the explicitly versioned surface."""

    def request(self, method, url, *args, **kwargs):
        if isinstance(url, str) and url.startswith("/") and not url.startswith("/python/v1/"):
            url = f"/python/v1{url}"
        return super().request(method, url, *args, **kwargs)


def client() -> LegacyTestClient:
    return LegacyTestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))


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
    assert data["token"].count(".") == 2
    assert data["refreshToken"].startswith("refresh_")
    assert data["tenantId"] == "tenant-a"

    refreshed = test_client.post("/auth/refresh", headers={"X-Refresh-Token": data["refreshToken"]})
    assert refreshed.status_code == 200
    assert assert_envelope(refreshed.json())["token"].count(".") == 2


def test_database_backed_auth_survives_application_restart(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'security.db'}"

    async def initialise_schema() -> None:
        engine = create_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(initialise_schema())
    settings = Settings(
        database_url=database_url,
        demo_api_key="persistent-admin",
        demo_tenant_id="tenant-a",
        storage_path=str(tmp_path / "uploads"),
        ingestion_queue_backend="db_polling",
    )
    workflow_task_id = ""
    research_task_id = ""
    evaluation_dataset_id = ""
    evaluation_run_id = ""
    graph_source_id = ""
    graph_target_id = ""
    graph_fact_id = ""
    with LegacyTestClient(create_app(settings)) as first_app:
        token = assert_envelope(first_app.post("/auth/token", headers={"X-API-Key": "persistent-admin"}).json())
        issued = assert_envelope(first_app.post("/auth/api-keys?keyName=persisted&role=USER", headers=AUTH_HEADERS | {"X-API-Key": "persistent-admin"}).json())
        rotated = assert_envelope(first_app.post("/auth/api-keys/rotate?keyName=persisted", headers={"X-API-Key": "persistent-admin"}).json())
        assert first_app.post("/auth/token", headers={"X-API-Key": issued["rawApiKey"]}).json()["ok"] == 0
        assert_envelope(
            first_app.post(
                "/ai/chat",
                headers={"X-API-Key": "persistent-admin"},
                json={"chatId": "durable-chat", "prompt": "Persist this conversation.", "modelProfile": "balanced"},
            ).json()
        )
        evaluation_dataset_id = assert_envelope(
            first_app.post(
                "/ai/evaluation/datasets",
                headers={"X-API-Key": "persistent-admin"},
                json={
                    "name": "Durable evaluation",
                    "cases": [{"caseId": "durable-case", "question": "KnowledgeOps", "expectedKeywords": ["KnowledgeOps"]}],
                },
            ).json()
        )["datasetId"]
        evaluation_run_id = assert_envelope(
            first_app.post(
                f"/ai/evaluation/datasets/{evaluation_dataset_id}/runs",
                headers={"X-API-Key": "persistent-admin"},
                json={"modelProfile": "balanced"},
            ).json()
        )["runId"]
        graph_source_id = assert_envelope(
            first_app.post(
                "/ai/graph/entities",
                headers={"X-API-Key": "persistent-admin"},
                json={"name": "Heat safety course", "type": "COURSE", "aliases": ["heat"], "description": "Prevention guidance"},
            ).json()
        )["entityId"]
        graph_target_id = assert_envelope(
            first_app.post(
                "/ai/graph/entities",
                headers={"X-API-Key": "persistent-admin"},
                json={"name": "Heat safety", "type": "TOPIC"},
            ).json()
        )["entityId"]
        assert assert_envelope(
            first_app.post(
                "/ai/graph/relations",
                headers={"X-API-Key": "persistent-admin"},
                json={
                    "sourceEntityId": graph_source_id,
                    "targetEntityId": graph_target_id,
                    "relationType": "BELONGS_TO",
                    "weight": 0.9,
                },
            ).json()
        )["relationType"] == "BELONGS_TO"
        graph_fact_id = assert_envelope(
            first_app.post(
                "/ai/graph/facts",
                headers={"X-API-Key": "persistent-admin"},
                json={"subject": "Heat safety", "predicate": "REQUIRES", "object": "Water and shade", "confidence": 0.95},
            ).json()
        )["factId"]
        workflow_task_id = assert_envelope(
            first_app.post(
                "/ai/workflow/react/chat",
                headers={"X-API-Key": "persistent-admin"},
                json={"chatId": "durable-chat", "prompt": "Persist a workflow.", "modelProfile": "balanced"},
            ).json()
        )["taskId"]
        research_task_id = assert_envelope(
            first_app.post("/ai/research/tasks", headers={"X-API-Key": "persistent-admin"}, json={"topic": "heat safety"}).json()
        )["taskId"]
        assert_envelope(
            first_app.post(
                "/ai/memory/items",
                headers={"X-API-Key": "persistent-admin"},
                json={"sessionId": "durable-chat", "type": "fact", "content": "Water and shade are important."},
            ).json()
        )
        queued = assert_envelope(
            first_app.post(
                "/ingestion/upload/durable-chat",
                headers={"X-API-Key": "persistent-admin"},
                files={"file": ("policy.txt", b"Water and shade prevent heat injury.", "text/plain")},
            ).json()
        )
        assert queued["status"] == "QUEUED"
        assert assert_envelope(first_app.post("/ingestion/jobs/process", headers={"X-API-Key": "persistent-admin"}).json())["processed"] == 1
        assert assert_envelope(first_app.get(f"/ingestion/jobs/{queued['jobId']}", headers={"X-API-Key": "persistent-admin"}).json())["status"] == "COMPLETED"

    with LegacyTestClient(create_app(settings)) as second_app:
        new_key_token = assert_envelope(second_app.post("/auth/token", headers={"X-API-Key": rotated["rawApiKey"]}).json())
        assert new_key_token["tenantId"] == "tenant-a"
        durable_session = assert_envelope(second_app.get("/ai/sessions/durable-chat", headers={"X-API-Key": "persistent-admin"}).json())
        assert durable_session["messages"][0]["content"] == "Persist this conversation."
        pinned = assert_envelope(second_app.post("/ai/sessions/durable-chat/pin?value=true", headers={"X-API-Key": "persistent-admin"}).json())
        assert pinned["pinned"] is True
        workflow = assert_envelope(second_app.get(f"/ai/workflow/tasks/{workflow_task_id}", headers={"X-API-Key": "persistent-admin"}).json())
        assert workflow["status"] == "DONE" and workflow["steps"]
        assert assert_envelope(second_app.get(f"/ai/workflow/tasks/{workflow_task_id}/events", headers={"X-API-Key": "persistent-admin"}).json())
        research_report = second_app.get(f"/ai/research/tasks/{research_task_id}/report", headers={"X-API-Key": "persistent-admin"})
        assert research_report.status_code == 200 and "heat safety" in research_report.text
        memories = assert_envelope(second_app.get("/ai/memory/items?sessionId=durable-chat", headers={"X-API-Key": "persistent-admin"}).json())
        assert memories[0]["content"] == "Water and shade are important."
        evaluation = assert_envelope(
            second_app.get(f"/ai/evaluation/runs/{evaluation_run_id}", headers={"X-API-Key": "persistent-admin"}).json()
        )
        assert evaluation["datasetId"] == evaluation_dataset_id and evaluation["results"][0]["caseId"] == "durable-case"
        assert assert_envelope(
            second_app.post(
                f"/ai/evaluation/runs/{evaluation_run_id}/baseline",
                headers={"X-API-Key": "persistent-admin"},
            ).json()
        )["isBaseline"]
        comparison = assert_envelope(
            second_app.get(
                f"/ai/evaluation/datasets/{evaluation_dataset_id}/comparison",
                headers={"X-API-Key": "persistent-admin"},
            ).json()
        )
        assert comparison["runs"][0]["runId"] == evaluation_run_id
        graph_entities = assert_envelope(
            second_app.get("/ai/graph/entities?query=course", headers={"X-API-Key": "persistent-admin"}).json()
        )
        assert graph_entities[0]["entityId"] == graph_source_id
        graph_neighbors = assert_envelope(
            second_app.get(
                f"/ai/graph/entities/{graph_source_id}/neighbors", headers={"X-API-Key": "persistent-admin"}
            ).json()
        )
        assert graph_neighbors[0]["entity"]["entityId"] == graph_target_id
        graph_facts = assert_envelope(
            second_app.get("/ai/graph/facts?query=shade", headers={"X-API-Key": "persistent-admin"}).json()
        )
        assert graph_facts[0]["factId"] == graph_fact_id
        graph_preview = assert_envelope(
            second_app.post(
                "/ai/harness/actions/preview",
                headers={"X-API-Key": "persistent-admin"},
                json={"action": "graph_search", "actionInput": {"query": "course"}},
            ).json()
        )
        graph_action = assert_envelope(
            second_app.post(
                f"/ai/harness/actions/execute/{graph_preview['confirmationToken']}",
                headers={"X-API-Key": "persistent-admin"},
            ).json()
        )
        assert graph_action["result"][0]["entityId"] == graph_source_id
        graph_rag = assert_envelope(
            second_app.post(
                "/ai/pdf/chat",
                headers={"X-API-Key": "persistent-admin"},
                json={"chatId": "graph-only", "prompt": "shade", "modelProfile": "balanced"},
            ).json()
        )
        assert graph_rag["citations"][0]["source"] == "graph"
        assert "Water and shade" in graph_rag["evidence"][0]
        refreshed = assert_envelope(second_app.post("/auth/refresh", headers={"X-Refresh-Token": token["refreshToken"]}).json())
        assert refreshed["principal"] == "local-demo"
        assert second_app.post("/auth/refresh", headers={"X-Refresh-Token": token["refreshToken"]}).json()["ok"] == 0
        file_text = second_app.get("/ai/pdf/file/durable-chat", headers={"X-API-Key": "persistent-admin"})
        assert file_text.status_code == 200
        assert "Water and shade" in file_text.text
        rag = assert_envelope(
            second_app.post(
                "/ai/pdf/chat",
                headers={"X-API-Key": "persistent-admin"},
                json={"chatId": "durable-chat", "prompt": "What prevents heat injury?", "modelProfile": "balanced"},
            ).json()
        )
        assert "Water and shade" in rag["evidence"][0]


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


def test_evaluation_scoring_matches_java_keyword_citation_and_forbidden_rules() -> None:
    case = {
        "expectedKeywords": ["heat", "risk"],
        "expectedCitations": ["heat-policy"],
        "forbiddenKeywords": ["invented"],
    }
    perfect = score_evaluation_case(
        case,
        "Heat risk guidance is cited [1].",
        ["vector:heat-policy:chunk-1"],
        ["Heat risk includes dehydration."],
        False,
    )
    assert perfect == {
        "retrievalHit": 1.0,
        "citationCoverage": 1.0,
        "keywordScore": 1.0,
        "answerFaithfulness": 1.0,
        "score": 1.0,
    }
    forbidden = score_evaluation_case(
        {"expectedKeywords": ["heat"], "expectedCitations": [], "forbiddenKeywords": ["invented"]},
        "This invented heat claim is unsupported.",
        [],
        [],
        False,
    )
    assert forbidden["keywordScore"] == 0.0
    assert forbidden["answerFaithfulness"] <= 0.2
    assert forbidden["score"] < 0.7


def test_admin_key_lifecycle_and_tenant_write_boundaries() -> None:
    app = create_app(Settings(demo_api_key="admin-key", demo_tenant_id="tenant-a"))
    test_client = LegacyTestClient(app)
    headers = {"X-API-Key": "admin-key", "X-Tenant-ID": "tenant-a"}

    assert test_client.post("/auth/api-keys?keyName=blocked").status_code == 401
    issued = assert_envelope(test_client.post("/auth/api-keys?keyName=reporter&role=USER", headers=headers).json())
    assert issued["tenantId"] == "tenant-a"
    assert test_client.post("/auth/api-keys?keyName=wrong-role&role=NOPE", headers=headers).status_code == 422
    rotated = assert_envelope(test_client.post("/auth/api-keys/rotate?keyName=reporter", headers=headers).json())
    assert rotated["rawApiKey"] != issued["rawApiKey"]
    assert_envelope(test_client.post("/auth/api-keys/revoke?keyName=reporter", headers=headers).json())
    assert test_client.post("/auth/token", headers={"X-API-Key": rotated["rawApiKey"]}).json()["ok"] == 0

    budget = assert_envelope(
        test_client.post("/cost/budget", headers=headers, json={"tenantId": "other-tenant", "monthlyBudgetUsd": 39}).json()
    )
    assert budget["tenantId"] == "tenant-a"
    other_key = asyncio.run(app.state.auth_service.issue_api_key("other", "ADMIN", "tenant-b"))
    other_headers = {"X-API-Key": other_key.rawApiKey, "X-Tenant-ID": "tenant-b"}
    denied = test_client.get("/cost/summary", headers={"X-API-Key": other_key.rawApiKey, "X-Tenant-ID": "tenant-a"})
    assert denied.status_code == 403
    test_client.post("/ai/chat", headers=headers, json={"chatId": "tenant-a-session", "prompt": "private"})
    assert test_client.get("/ai/sessions/tenant-a-session", headers=other_headers).status_code == 404
    dataset = assert_envelope(test_client.post("/ai/evaluation/datasets", headers=headers, json={"name": "private", "cases": []}).json())
    assert test_client.post("/ai/evaluation/runs", headers=other_headers, json={"datasetId": dataset["datasetId"]}).status_code == 404


def test_harness_workflow_research_memory_graph_and_evaluations_are_tenant_scoped() -> None:
    test_client = client()
    headers = AUTH_HEADERS

    preview = assert_envelope(
        test_client.post(
            "/ai/harness/actions/preview",
            headers=headers,
            json={"action": "memory_save", "actionInput": {"content": "Tenant a preference", "type": "fact"}},
        ).json()
    )
    executed = assert_envelope(test_client.post(f"/ai/harness/actions/execute/{preview['confirmationToken']}", headers=headers).json())
    assert executed["status"] == "COMPLETED"
    assert test_client.post(f"/ai/harness/actions/execute/{preview['confirmationToken']}", headers=headers).status_code == 404

    memory = assert_envelope(test_client.get("/ai/memory/items", headers=headers).json())
    assert memory[0]["principal"] == "local-demo"
    context = assert_envelope(test_client.get("/ai/memory/context?prompt=preference", headers=headers).json())
    assert context[0]["content"] == "Tenant a preference"
    entity = assert_envelope(test_client.post("/ai/graph/entities", headers=headers, json={"name": "Tenant Entity", "type": "CONCEPT"}).json())
    assert entity["tenantId"] == "tenant-a"
    assert assert_envelope(test_client.get("/ai/graph/entities", headers=headers).json())[0]["name"] == "Tenant Entity"

    workflow = assert_envelope(test_client.post("/ai/workflow/react/chat", headers=headers, json={"chatId": "wf", "prompt": "workflow"}).json())
    assert assert_envelope(test_client.get(f"/ai/workflow/tasks/{workflow['taskId']}", headers=headers).json())["status"] == "COMPLETED"
    assert assert_envelope(test_client.get(f"/ai/workflow/tasks/{workflow['taskId']}/events", headers=headers).json())
    assert assert_envelope(test_client.get("/ai/workflow/tasks", headers=headers).json())["total"] == 1
    research = assert_envelope(test_client.post("/ai/research/tasks", headers=headers, json={"topic": "Heat safety"}).json())
    assert "# Heat safety" in test_client.get(f"/ai/research/tasks/{research['taskId']}/report", headers=headers).text

    dataset = assert_envelope(test_client.post("/ai/evaluation/datasets", headers=headers, json={"name": "d", "cases": [{"question": "KnowledgeOps"}]}).json())
    run = assert_envelope(test_client.post(f"/ai/evaluation/datasets/{dataset['datasetId']}/runs", headers=headers, json={}).json())
    assert assert_envelope(test_client.get(f"/ai/evaluation/runs/{run['runId']}", headers=headers).json())["runId"] == run["runId"]
    assert assert_envelope(test_client.post(f"/ai/evaluation/runs/{run['runId']}/baseline", headers=headers).json())["isBaseline"]
    assert assert_envelope(test_client.get(f"/ai/evaluation/datasets/{dataset['datasetId']}/comparison", headers=headers).json())["runs"]
    assert "# RAG Evaluation Report" in test_client.get(f"/ai/evaluation/runs/{run['runId']}/report", headers=headers).text


def test_extended_java_routes_file_safety_and_production_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    test_client = client()
    headers = AUTH_HEADERS
    assert test_client.get("/ai/chat?prompt=hello&chatId=html", headers=headers).headers["content-type"].startswith("text/html")
    assert test_client.get("/ai/pdf/file/missing", headers=headers).status_code == 404
    assert test_client.post("/ai/pdf/upload/doc", headers=headers, files={"file": ("bad.exe", b"no", "application/octet-stream")}).status_code == 415
    assert test_client.post("/ai/pdf/upload/doc", headers=headers, files={"file": ("bad.pdf", b"not-pdf", "application/pdf")}).status_code == 415
    assert assert_envelope(test_client.post("/ingestion/jobs/process", headers=headers).json())["processed"] == 0
    assert test_client.get("/auth/oidc/login").status_code == 503
    assert test_client.post("/auth/logout", headers={"X-Refresh-Token": "unused"}).status_code == 200

    with pytest.raises(ValueError, match="APP_JWT_SECRET"):
        Settings(environment="production", demo_api_key="real-key", database_url="sqlite+aiosqlite:///x", redis_url="redis://x", reranker_backend="remote").validate_startup()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("APP_DEMO_API_KEY", "not-a-default")
    monkeypatch.setenv("APP_DATABASE_URL", "sqlite+aiosqlite:///x")
    monkeypatch.setenv("APP_VECTOR_BACKEND", "pgvector")
    monkeypatch.setenv("APP_PGVECTOR_URL", "postgresql+asyncpg://postgres:secret@pgvector/knowledgeops")
    monkeypatch.setenv("APP_REDIS_URL", "redis://x")
    monkeypatch.setenv("APP_RERANKER_BACKEND", "remote")
    monkeypatch.setenv("APP_RERANKER_URL", "https://reranker.example.test")
    monkeypatch.setenv("APP_MODEL_BASE_URL", "https://model.example.test")
    monkeypatch.setenv("APP_MODEL_API_KEY", "test-model-key")
    assert load_settings().is_production
