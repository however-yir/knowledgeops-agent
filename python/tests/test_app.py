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
    assert payload["token"].startswith("py-access-")
    assert payload["refreshToken"].startswith("py-refresh-")


def test_auth_token_rejects_invalid_api_key() -> None:
    response = client().post("/auth/token", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401


def test_ai_service_matches_plain_text_contract() -> None:
    response = client().get("/ai/service", params={"prompt": "hello", "chatId": "c1", "modelProfile": "cheap"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "[python:cheap] hello chatId=c1"
