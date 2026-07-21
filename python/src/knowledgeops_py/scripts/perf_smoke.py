from __future__ import annotations

import os
import time

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app

AUTH_HEADERS = {"X-API-Key": "local-demo-api-key", "X-Tenant-ID": "public"}


def main() -> None:
    iterations = int(os.getenv("ITERATIONS", "40"))
    p95_limit_ms = float(os.getenv("P95_MS", "1500"))
    client = TestClient(create_app())
    client.post(
        "/ai/pdf/upload/perf-chat",
        headers=AUTH_HEADERS,
        files={"file": ("policy.txt", b"Heat safety requires shade water rest and supervisor review.", "text/plain")},
    )
    latencies: list[float] = []
    failures = 0
    for index in range(iterations):
        endpoint = "/ai/chat" if index % 2 == 0 else "/ai/pdf/chat"
        body = {"chatId": "perf-chat", "prompt": "heat safety requirements", "modelProfile": "balanced"}
        started = time.perf_counter()
        response = client.post(endpoint, headers=AUTH_HEADERS, json=body)
        latencies.append((time.perf_counter() - started) * 1000)
        if response.status_code >= 400 or response.json().get("ok") != 1:
            failures += 1
    latencies.sort()
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
    failure_rate = failures / max(1, iterations)
    print({"iterations": iterations, "p95Ms": round(p95, 1), "failureRate": round(failure_rate, 4), "p95LimitMs": p95_limit_ms})
    if p95 > p95_limit_ms or failure_rate >= 0.02:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
