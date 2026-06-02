from __future__ import annotations

import json

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app


AUTH_HEADERS = {"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "public"}


def main() -> None:
    client = TestClient(create_app())
    assert envelope(client.get("/actuator/health"))["status"] == "UP"

    upload = envelope(
        client.post(
            "/ai/pdf/upload/e2e-chat",
            headers=AUTH_HEADERS,
            files={"file": ("heat-safety-policy.txt", b"Heat safety requires shade, water, and rest breaks.", "text/plain")},
        )
    )
    assert upload["status"] == "COMPLETED"

    chat = envelope(client.post("/ai/chat", headers=AUTH_HEADERS, json={"chatId": "e2e-chat", "prompt": "heat safety", "modelProfile": "balanced"}))
    assert chat["answer"]

    stream = client.post("/ai/react/chat/stream", headers=AUTH_HEADERS, json={"chatId": "e2e-chat", "prompt": "heat safety stream", "modelProfile": "balanced"})
    assert "event: done" in stream.text
    done = json.loads([line for line in stream.text.splitlines() if line.startswith("data: ")][-1].removeprefix("data: "))
    assert done["ok"] == 1

    rag = envelope(client.post("/ai/pdf/chat", headers=AUTH_HEADERS, json={"chatId": "e2e-chat", "prompt": "heat safety", "modelProfile": "quality"}))
    assert rag["citations"]

    envelope(client.get("/ai/sessions/e2e-chat", headers=AUTH_HEADERS))
    envelope(client.post("/ai/feedback", headers=AUTH_HEADERS, json={"chatId": "e2e-chat", "rating": 1}))
    datasets = envelope(client.get("/ai/evaluation/datasets", headers=AUTH_HEADERS))
    envelope(client.post("/ai/evaluation/runs", headers=AUTH_HEADERS, json={"datasetId": datasets[0]["datasetId"], "modelProfile": "balanced"}))
    envelope(client.post("/cost/budget", headers=AUTH_HEADERS, json={"monthlyBudgetUsd": 40}))
    envelope(client.get("/audit/logs", headers=AUTH_HEADERS))
    print("python enterprise e2e smoke ok")


def envelope(response):
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["ok"] == 1, payload
    assert "data" in payload
    return payload["data"]


if __name__ == "__main__":
    main()
