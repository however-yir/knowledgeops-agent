from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from knowledgeops_py.scripts.cross_runtime_contract import compare_case, request_contract_case


def response(status: int, *, body: str = "", json_data: object | None = None) -> httpx.Response:
    return httpx.Response(status, text=body) if json_data is None else httpx.Response(status, json=json_data)


def test_cross_runtime_contract_checks_expected_status_and_normalized_payload() -> None:
    case = {"label": "health", "expectStatus": 200}
    assert compare_case(case, response(200, json_data={"traceId": "java", "ok": True}), response(200, json_data={"traceId": "python", "ok": True})) == []
    assert compare_case(case, response(500, json_data={}), response(500, json_data={})) == [
        "health: Java status 500 != expected 200",
        "health: Python status 500 != expected 200",
    ]


def test_cross_runtime_contract_checks_sse_events_for_both_runtimes() -> None:
    case = {"label": "stream error", "expectStatus": 200, "sse": True, "sseEvents": ["error"]}
    assert compare_case(case, response(200, body="event: error\ndata: bad\n\n"), response(200, body="event: done\n\n")) == [
        "stream error: Python SSE missing error"
    ]


def test_cross_runtime_contract_checks_runtime_specific_fields_without_comparing_dynamic_values() -> None:
    case = {
        "label": "token",
        "expectStatus": 200,
        "javaFields": ["ok", "token"],
        "pythonFields": ["ok", "token", "usage.totalTokens"],
    }
    assert compare_case(
        case,
        response(200, json_data={"ok": 1, "token": "java-token"}),
        response(200, json_data={"ok": 1, "token": "python-token", "usage": {"totalTokens": 5}}),
    ) == []


class TruncatedSseStream(httpx.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __iter__(self) -> Iterator[bytes]:
        yield self.body
        raise httpx.RemoteProtocolError("incomplete chunked read")


def test_cross_runtime_contract_keeps_terminal_sse_events_after_baseline_transport_close() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=TruncatedSseStream(b"event: trace\n\nevent: done\n\n"), request=request)

    case = {"label": "stream", "method": "POST", "sse": True, "sseEvents": ["trace", "done"]}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = request_contract_case(client, case, "http://contract.test/stream", {"headers": {}})

    assert response.text == "event: trace\n\nevent: done\n\n"


def test_cross_runtime_contract_rejects_truncated_sse_without_a_terminal_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=TruncatedSseStream(b"event: trace\n\n"), request=request)

    case = {"label": "stream", "method": "POST", "sse": True, "sseEvents": ["trace", "done"]}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(httpx.RemoteProtocolError):
        request_contract_case(client, case, "http://contract.test/stream", {"headers": {}})


def test_cross_runtime_sse_cases_negotiate_event_streams() -> None:
    cases = json.loads((Path(__file__).parents[1] / "parity" / "cross-runtime-ci-cases.json").read_text(encoding="utf-8"))

    for case in cases:
        if case.get("sse"):
            assert case["headers"]["Accept"] == "text/event-stream"
            assert case["headers"]["Connection"] == "close"


def test_cross_runtime_provider_failure_matches_java_planner_fallback() -> None:
    cases = json.loads((Path(__file__).parents[1] / "parity" / "cross-runtime-ci-cases.json").read_text(encoding="utf-8"))
    provider_failure = next(case for case in cases if case["label"] == "react stream planner fallback")

    assert provider_failure["sseEvents"] == ["trace", "token", "done"]
