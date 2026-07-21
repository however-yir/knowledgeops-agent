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
            request = {"headers": headers}
            if case.get("body"):
                request["json"] = case["body"]
            java = client.request(case["method"], args.java_base_url.rstrip("/") + case["path"], **request)
            python = client.request(case["method"], args.python_base_url.rstrip("/") + case["path"], **request)
            if java.status_code != python.status_code:
                failures.append(f"{case['label']}: status {java.status_code} != {python.status_code}")
                continue
            if case.get("sse"):
                for event in ("trace", "token", "done"):
                    if f"event: {event}" not in python.text:
                        failures.append(f"{case['label']}: Python SSE missing {event}")
                continue
            try:
                if normalize(java.json()) != normalize(python.json()):
                    failures.append(f"{case['label']}: normalized JSON differs")
            except json.JSONDecodeError:
                if java.text != python.text:
                    failures.append(f"{case['label']}: text response differs")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"cross-runtime contract passed: {len(cases)} cases")


if __name__ == "__main__":
    main()
