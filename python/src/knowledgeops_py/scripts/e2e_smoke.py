from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from knowledgeops_py.app import create_app


def auth_headers() -> dict[str, str]:
    """Credentials for the in-process smoke run.

    Defaults to the local demo key so `make`-style local runs work out of the
    box; point APP_E2E_API_KEY / APP_E2E_TENANT_ID at explicit credentials when
    running against a configured stack (Java parity: e2e never assumes a
    repository-committed plaintext works anywhere but local development).
    """
    return {
        "X-API-Key": os.getenv("APP_E2E_API_KEY", "local-demo-api-key"),
        "X-Tenant-ID": os.getenv("APP_E2E_TENANT_ID", "public"),
    }


def main() -> None:
    client = TestClient(create_app())
    assert envelope(client.get("/python/v1/actuator/health"))["status"] == "UP"

    upload = envelope(
        client.post(
            "/python/v1/ai/pdf/upload/e2e-chat",
            headers=auth_headers(),
            files={"file": ("heat-safety-policy.txt", b"Heat safety requires shade, water, and rest breaks.", "text/plain")},
        )
    )
    assert upload["status"] == "COMPLETED"

    chat = envelope(client.post("/python/v1/ai/chat", headers=auth_headers(), json={"chatId": "e2e-chat", "prompt": "heat safety", "modelProfile": "balanced"}))
    assert chat["answer"]

    stream = client.post("/python/v1/ai/react/chat/stream", headers=auth_headers(), json={"chatId": "e2e-chat", "prompt": "heat safety stream", "modelProfile": "balanced"})
    assert "event: done" in stream.text
    done = json.loads([line for line in stream.text.splitlines() if line.startswith("data: ")][-1].removeprefix("data: "))
    assert done["ok"] == 1

    rag = envelope(client.post("/python/v1/ai/pdf/chat", headers=auth_headers(), json={"chatId": "e2e-chat", "prompt": "heat safety", "modelProfile": "quality"}))
    assert rag["citations"]

    envelope(client.get("/python/v1/ai/sessions/e2e-chat", headers=auth_headers()))
    envelope(client.post("/python/v1/ai/feedback", headers=auth_headers(), json={"chatId": "e2e-chat", "rating": 1}))
    datasets = envelope(client.get("/python/v1/ai/evaluation/datasets", headers=auth_headers()))
    envelope(client.post("/python/v1/ai/evaluation/runs", headers=auth_headers(), json={"datasetId": datasets[0]["datasetId"], "modelProfile": "balanced"}))
    envelope(client.post("/python/v1/cost/budget", headers=auth_headers(), json={"monthlyBudgetUsd": 40}))
    envelope(client.get("/python/v1/audit/logs", headers=auth_headers()))
    print("python enterprise e2e smoke ok")


def envelope(response: Response) -> Any:
    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["ok"] == 1, payload
    assert "data" in payload
    return payload["data"]


if __name__ == "__main__":
    main()
