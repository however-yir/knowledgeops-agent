from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

VOLATILE_FIELDS = {"traceId", "createdAt", "updatedAt", "expiresAt", "token", "refreshToken", "rawApiKey"}
TERMINAL_SSE_EVENTS = {"done", "error"}
TEMPLATE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
ROUTE_PARAMETER = re.compile(r"\{\{[^{}]+\}\}|\{[^{}]+\}")


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items() if key not in VOLATILE_FIELDS}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def compare_case(case: dict[str, Any], java: httpx.Response | None, python: httpx.Response) -> list[str]:
    label = str(case["label"])
    expected_status = int(case["expectStatus"])
    failures: list[str] = []
    if java is not None and java.status_code != expected_status:
        failures.append(f"{label}: Java status {java.status_code} != expected {expected_status}")
    if python.status_code != expected_status:
        failures.append(f"{label}: Python status {python.status_code} != expected {expected_status}")
    if java is None:
        # javaKnownDefect case: the pinned Java baseline cannot serve this
        # request at all (documented oracle defect), so only Python is
        # validated.
        return failures
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
    if case.get("comparison") == "status":
        return failures
    fields_by_runtime = {
        "Java": [] if java is None else [str(field) for field in case.get("javaFields", case.get("fields", []))],
        "Python": [str(field) for field in case.get("pythonFields", case.get("fields", []))],
    }
    if any(fields_by_runtime.values()):
        for runtime, response in (("Java", java), ("Python", python)):
            try:
                payload = response.json()
            except json.JSONDecodeError:
                failures.append(f"{label}: {runtime} response is not JSON")
                continue
            for field in fields_by_runtime[runtime]:
                if not has_json_field(payload, field):
                    failures.append(f"{label}: {runtime} JSON missing {field}")
        return failures
    try:
        if normalize(java.json()) != normalize(python.json()):
            failures.append(f"{label}: normalized JSON differs")
    except json.JSONDecodeError:
        if java.text != python.text:
            failures.append(f"{label}: text response differs")
    return failures


def has_json_field(payload: Any, field: str) -> bool:
    _, found = json_path_value(payload, field)
    return found


def json_path_value(payload: Any, path: str) -> tuple[Any, bool]:
    value = payload
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None, False
    return value, True


def render_value(value: Any, variables: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in variables:
                raise ValueError(f"missing captured value: {name}")
            return str(variables[name])

        return TEMPLATE.sub(replace, value)
    if isinstance(value, list):
        return [render_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {str(key): render_value(item, variables) for key, item in value.items()}
    return value


def request_data(case: dict[str, Any], headers: Mapping[str, str], variables: Mapping[str, Any]) -> dict[str, Any]:
    case_headers = render_value(case.get("headers", {}), variables)
    request: dict[str, Any] = {"headers": dict(headers) | {str(key): str(value) for key, value in case_headers.items()}}
    if "body" in case:
        request["json"] = render_value(case["body"], variables)
    if "multipart" in case:
        multipart = render_value(case["multipart"], variables)
        field = str(multipart["field"])
        request["files"] = {
            field: (
                str(multipart["filename"]),
                str(multipart["content"]).encode(),
                str(multipart.get("contentType", "application/octet-stream")),
            )
        }
    return request


def capture_response(case: dict[str, Any], runtime: str, response: httpx.Response, variables: dict[str, Any]) -> list[str]:
    captures = case.get("captures", {})
    if not captures:
        return []
    label = str(case["label"])
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return [f"{label}: {runtime} response is not JSON; unable to capture values"]
    failures: list[str] = []
    for name, path in captures.items():
        value, found = json_path_value(payload, str(path))
        if not found:
            failures.append(f"{label}: {runtime} JSON missing capture {name} at {path}")
        else:
            variables[str(name)] = value
    return failures


def routes_match(case_path: str, manifest_path: str) -> bool:
    case_segments = case_path.split("?", maxsplit=1)[0].strip("/").split("/")
    manifest_segments = manifest_path.strip("/").split("/")
    return len(case_segments) == len(manifest_segments) and all(
        case_segment == manifest_segment
        or ROUTE_PARAMETER.fullmatch(case_segment)
        or ROUTE_PARAMETER.fullmatch(manifest_segment)
        for case_segment, manifest_segment in zip(case_segments, manifest_segments, strict=True)
    )


def missing_manifest_routes(cases: list[dict[str, Any]], manifest: dict[str, Any]) -> list[str]:
    return [
        f"{str(route['method']).upper()} {route['path']}"
        for route in manifest["routes"]
        if not any(
            str(case["method"]).upper() == str(route["method"]).upper()
            and routes_match(str(case["path"]), str(route["path"]))
            for case in cases
        )
    ]


def request_contract_case(
    client: httpx.Client, case: dict[str, Any], url: str, request: dict[str, Any]
) -> httpx.Response:
    if not case.get("sse"):
        return client.request(case["method"], url, **request)

    expected_events = [str(event) for event in case.get("sseEvents", [])]
    with client.stream(case["method"], url, **request) as response:
        chunks: list[bytes] = []
        try:
            for chunk in response.iter_bytes():
                chunks.append(chunk)
        except httpx.RemoteProtocolError:
            body = b"".join(chunks)
            terminal_events = set(expected_events) & TERMINAL_SSE_EVENTS
            if not terminal_events or not any(f"event: {event}".encode() in body for event in terminal_events):
                raise
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=b"".join(chunks),
            request=response.request,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Java and Python HTTP contracts against shared cases")
    parser.add_argument("--java-base-url", required=True)
    parser.add_argument("--python-base-url", required=True)
    parser.add_argument("--cases", type=Path, default=Path("../typescript/parity/contract-cases.json"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    manifest_path = args.manifest or args.cases.with_name("java-baseline-manifest.json")
    missing_routes = missing_manifest_routes(cases, json.loads(manifest_path.read_text(encoding="utf-8")))
    if missing_routes:
        raise SystemExit("cross-runtime cases missing baseline routes:\n" + "\n".join(missing_routes))
    headers = {"X-API-Key": args.api_key, "X-Tenant-ID": args.tenant_id}
    failures: list[str] = []
    java_variables: dict[str, Any] = {}
    python_variables: dict[str, Any] = {}
    with httpx.Client(timeout=30.0) as client:
        for case in cases:
            java: httpx.Response | None = None
            if not case.get("javaKnownDefect"):
                try:
                    java_url = args.java_base_url.rstrip("/") + str(render_value(case["path"], java_variables))
                    java = request_contract_case(client, case, java_url, request_data(case, headers, java_variables))
                    failures.extend(capture_response(case, "Java", java, java_variables))
                except ValueError as exc:
                    failures.append(f"{case['label']}: Java {exc}")
                    continue
            try:
                python_url = args.python_base_url.rstrip("/") + str(render_value(case["path"], python_variables))
                python = request_contract_case(client, case, python_url, request_data(case, headers, python_variables))
                failures.extend(capture_response(case, "Python", python, python_variables))
            except ValueError as exc:
                failures.append(f"{case['label']}: Python {exc}")
                continue
            failures.extend(compare_case(case, java, python))
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"cross-runtime contract passed: {len(cases)} cases")


if __name__ == "__main__":
    main()
