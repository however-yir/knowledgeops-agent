from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

VOLATILE_FIELDS = {"traceId", "createdAt", "updatedAt", "expiresAt", "token", "refreshToken", "rawApiKey"}


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items() if key not in VOLATILE_FIELDS}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def compare_case(case: dict[str, Any], java: httpx.Response, python: httpx.Response) -> list[str]:
    label = str(case["label"])
    expected_status = int(case["expectStatus"])
    failures: list[str] = []
    for runtime, response in (("Java", java), ("Python", python)):
        if response.status_code != expected_status:
            failures.append(f"{label}: {runtime} status {response.status_code} != expected {expected_status}")
    if java.status_code != python.status_code:
        failures.append(f"{label}: status {java.status_code} != {python.status_code}")
        return failures
    if case.get("sse"):
        events = [str(event) for event in case.get("sseEvents", ["trace", "token", "done"])]
        for runtime, response in (("Java", java), ("Python", python)):
            for event in events:
                if f"event: {event}" not in response.text:
                    failures.append(f"{label}: {runtime} SSE missing {event}")
        return failures
    try:
        if normalize(java.json()) != normalize(python.json()):
            failures.append(f"{label}: normalized JSON differs")
    except json.JSONDecodeError:
        if java.text != python.text:
            failures.append(f"{label}: text response differs")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Java and Python HTTP contracts against shared cases")
    parser.add_argument("--java-base-url", required=True)
    parser.add_argument("--python-base-url", required=True)
    parser.add_argument("--cases", type=Path, default=Path("../typescript/parity/contract-cases.json"))
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    headers = {"X-API-Key": args.api_key, "X-Tenant-ID": args.tenant_id}
    failures: list[str] = []
    with httpx.Client(timeout=30.0) as client:
        for case in cases:
            request_headers = headers | {str(key): str(value) for key, value in case.get("headers", {}).items()}
            request = {"headers": request_headers}
            if case.get("body"):
                request["json"] = case["body"]
            java = client.request(case["method"], args.java_base_url.rstrip("/") + case["path"], **request)
            python = client.request(case["method"], args.python_base_url.rstrip("/") + case["path"], **request)
            failures.extend(compare_case(case, java, python))
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"cross-runtime contract passed: {len(cases)} cases")


if __name__ == "__main__":
    main()
