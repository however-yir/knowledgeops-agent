from __future__ import annotations

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app


def main() -> None:
    client = TestClient(create_app())
    health = client.get("/actuator/health")
    assert health.json() == {"status": "UP"}

    upload = client.post(
        "/ai/pdf/upload/e2e-chat",
        files={"file": ("heat-safety-policy.txt", b"Heat safety requires shade, water, and rest breaks.", "text/plain")},
    )
    assert upload.status_code == 200, upload.text

    chat = client.post("/ai/react/chat", json={"prompt": "heat safety", "chatId": "e2e-chat"})
    assert chat.json()["ok"] == 1

    stream = client.post("/ai/react/chat/stream", json={"prompt": "heat safety stream", "chatId": "e2e-chat"})
    assert "event: done" in stream.text

    memory = client.post("/ai/memory/items", json={"userId": "anonymous", "content": "E2E memory item", "type": "fact"})
    assert memory.status_code == 200

    entity = client.post("/ai/graph/entities", json={"name": "E2E Entity", "type": "CONCEPT"})
    assert entity.status_code == 200
    neighbors = client.get(f"/ai/graph/entities/{entity.json()['entityId']}/neighbors")
    assert "relations" in neighbors.json()

    dataset = client.post(
        "/ai/evaluation/datasets",
        json={"name": "e2e", "cases": [{"question": "heat safety", "expectedKeywords": ["heat"]}]},
    )
    run = client.post(f"/ai/evaluation/datasets/{dataset.json()['datasetId']}/runs", json={"modelProfile": "balanced"})
    assert run.json()["status"] == "COMPLETED"
    assert client.get("/cost/summary").json()["tenantId"] == "public"
    print("python e2e smoke ok")


if __name__ == "__main__":
    main()
