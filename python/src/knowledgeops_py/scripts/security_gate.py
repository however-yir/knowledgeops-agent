from __future__ import annotations

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app
from knowledgeops_py.config import Settings

AUTH_HEADERS = {"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "public"}


def main() -> None:
    app = create_app(Settings(rate_limit_per_minute=2))
    client = TestClient(app)

    invalid = client.post("/auth/token", headers={"X-API-Key": "wrong", "X-Tenant-ID": "public"})
    assert invalid.status_code == 200
    assert invalid.json()["ok"] == 0
    assert invalid.json()["code"] == "AUTH_INVALID_API_KEY"

    unauth = client.post("/ai/chat", json={"chatId": "sec", "prompt": "hello", "modelProfile": "balanced"})
    assert unauth.status_code == 401
    assert {"ok", "msg", "code", "traceId"} <= set(unauth.json())

    tenant_mismatch = client.post("/auth/token", headers={"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "other"})
    assert tenant_mismatch.json()["ok"] == 0
    assert tenant_mismatch.json()["code"] == "AUTH_TENANT_MISMATCH"

    body = {"chatId": "sec", "prompt": "hello", "modelProfile": "balanced"}
    first = client.post("/ai/chat", headers=AUTH_HEADERS, json=body)
    second = client.post("/ai/chat", headers=AUTH_HEADERS, json=body)
    third = client.post("/ai/chat", headers=AUTH_HEADERS, json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["code"] == "RATE_LIMIT_EXCEEDED"
    print("python security gate ok")


if __name__ == "__main__":
    main()
