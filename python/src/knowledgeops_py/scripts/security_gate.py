from __future__ import annotations

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app
from knowledgeops_py.config import Settings

AUTH_HEADERS = {"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "public"}


def main() -> None:
    # Per-minute budget of 3: the three pre-chat probes (invalid key, tenant
    # mismatch, unauthenticated) now share ONE anonymous IP bucket after the
    # rate-limit hardening (anonymous buckets are keyed by client IP, not by
    # the client-controlled tenant header), so the old budget of 2 would trip
    # a 429 on the tenant-mismatch probe.
    app = create_app(Settings(rate_limit_per_minute=3))
    client = TestClient(app)

    invalid = client.post("/python/v1/auth/token", headers={"X-API-Key": "wrong", "X-Tenant-ID": "public"})
    assert invalid.status_code == 200
    assert invalid.json()["ok"] == 0
    assert invalid.json()["code"] == "AUTH_INVALID_API_KEY"

    unauth = client.post("/python/v1/ai/chat", json={"chatId": "sec", "prompt": "hello", "modelProfile": "balanced"})
    assert unauth.status_code == 401
    assert {"ok", "msg", "code", "traceId"} <= set(unauth.json())

    tenant_mismatch = client.post("/python/v1/auth/token", headers={"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "other"})
    assert tenant_mismatch.json()["ok"] == 0
    assert tenant_mismatch.json()["code"] == "AUTH_TENANT_MISMATCH"

    body = {"chatId": "sec", "prompt": "hello", "modelProfile": "balanced"}
    chats = [client.post("/python/v1/ai/chat", headers=AUTH_HEADERS, json=body) for _ in range(4)]
    assert [chat.status_code for chat in chats[:3]] == [200, 200, 200]
    assert chats[3].status_code == 429
    assert chats[3].json()["code"] == "RATE_LIMIT_EXCEEDED"
    print("python security gate ok")


if __name__ == "__main__":
    main()
