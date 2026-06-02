from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app
from knowledgeops_py.config import Settings


def client() -> TestClient:
    return TestClient(create_app(Settings(demo_api_key="test-key", demo_tenant_id="tenant-a")))


def test_health_is_java_compatible() -> None:
    response = client().get("/actuator/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_prometheus_smoke_metric() -> None:
    response = client().get("/actuator/prometheus")

    assert response.status_code == 200
    assert "knowledgeops_python_up 1" in response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_auth_token_exchanges_demo_api_key() -> None:
    response = client().post("/auth/token", headers={"X-API-Key": "test-key"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] == 1
    assert payload["msg"] == "ok"
    assert payload["tenantId"] == "tenant-a"
    assert payload["token"].startswith("pyjwt.")
    assert payload["refreshToken"].startswith("refresh_")


def test_auth_token_rejects_invalid_api_key() -> None:
    response = client().post("/auth/token", headers={"X-API-Key": "wrong"})

    assert response.status_code == 200
    assert response.json()["ok"] == 0


def test_ai_service_matches_plain_text_contract() -> None:
    response = client().get("/ai/service", params={"prompt": "hello", "chatId": "c1", "modelProfile": "cheap"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "hello" in response.text


def test_react_stream_contract_contains_done_event() -> None:
    response = client().post("/ai/react/chat/stream", json={"prompt": "hello", "chatId": "stream-1"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in response.text


def test_upload_and_pdf_chat_returns_citation() -> None:
    test_client = client()
    upload = test_client.post(
        "/ai/pdf/upload/doc-1",
        files={"file": ("policy.txt", b"Heat safety requires water rest and shade.", "text/plain")},
    )

    assert upload.status_code == 200
    assert upload.json()["job"]["status"] == "COMPLETED"

    chat = test_client.get("/ai/pdf/chat", params={"prompt": "heat safety", "chatId": "doc-1"})

    assert chat.status_code == 200
    assert "policy.txt" in chat.text


def test_memory_graph_evaluation_workflow_surfaces() -> None:
    test_client = client()
    memory = test_client.post("/ai/memory/items", json={"userId": "anonymous", "type": "fact", "content": "contract memory"})
    entity = test_client.post("/ai/graph/entities", json={"name": "Contract Entity", "type": "CONCEPT"})
    dataset = test_client.post(
        "/ai/evaluation/datasets",
        json={"name": "contract", "cases": [{"question": "contract memory", "expectedKeywords": ["contract"]}]},
    )
    run = test_client.post(f"/ai/evaluation/datasets/{dataset.json()['datasetId']}/runs", json={"modelProfile": "balanced"})
    workflow = test_client.post("/ai/research/tasks", json={"topic": "contract research"})

    assert memory.status_code == 200
    assert entity.status_code == 200
    assert run.json()["status"] == "COMPLETED"
    assert workflow.json()["ok"] == 1
