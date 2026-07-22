from __future__ import annotations

import httpx

from knowledgeops_py.scripts.cross_runtime_contract import compare_case


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
