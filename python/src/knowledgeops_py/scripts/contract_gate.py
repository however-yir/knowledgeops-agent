from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from knowledgeops_py.app import create_app


def main() -> None:
    client = TestClient(create_app())
    cases = json.loads(_contract_path().read_text(encoding="utf-8"))
    failures: list[str] = []
    for case in cases:
        response = _call(client, case)
        expected = int(case.get("expectStatus", 200))
        if response.status_code != expected:
            failures.append(f"{case['label']}: expected {expected}, got {response.status_code}: {response.text[:160]}")
            continue
        if case.get("sse") and "event: done" not in response.text:
            failures.append(f"{case['label']}: expected SSE done event")
    if failures:
        raise SystemExit("\n".join(failures))
    tag_count = len({tag for case in cases for tag in case.get("tags", [])})
    print(f"python contract gate ok: {len(cases)} cases, {tag_count} tags")


def _call(client: TestClient, case: dict[str, Any]):
    method = str(case.get("method", "GET")).upper()
    path = str(case["path"])
    headers = dict(case.get("headers") or {})
    body = case.get("body")
    if method == "GET":
        return client.get(path, headers=headers)
    if method == "POST":
        return client.post(path, headers=headers, json=body if body is not None else {})
    if method == "PUT":
        return client.put(path, headers=headers, json=body if body is not None else {})
    if method == "DELETE":
        return client.delete(path, headers=headers)
    raise AssertionError(f"unsupported method: {method}")


def _contract_path() -> Path:
    return Path(__file__).resolve().parents[4] / "typescript" / "parity" / "contract-cases.json"


if __name__ == "__main__":
    main()
