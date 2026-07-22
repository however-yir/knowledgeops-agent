"""SSE encoders for legacy envelopes and canonical Java-compatible events."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from knowledgeops_py.api.canonical import react_response_payload, react_trace_payload
from knowledgeops_py.dto import ChatResponseDto


def to_sse(
    data: ChatResponseDto,
    trace_id: str,
    legacy: bool,
    react: bool = False,
    *,
    ok: Callable[..., dict[str, Any]],
) -> str:
    events = []
    for trace in data.trace:
        payload = ok(trace, msg="trace", trace_id=trace_id) if legacy else react_trace_payload(trace)
        events.append(f"event: trace\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n")
    token = ok({"token": data.answer}, msg="token", trace_id=trace_id) if legacy else {"token": data.answer}
    events.append(f"event: token\ndata: {json.dumps(token, ensure_ascii=False)}\n\n")
    done = ok(data, trace_id=trace_id) if legacy else react_response_payload(data) if react else data.model_dump()
    events.append(f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n")
    return "".join(events)


def to_sse_error(
    exc: Exception, trace_id: str, legacy: bool, *, error_payload: Callable[[str, str, str], dict[str, Any]]
) -> str:
    message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
    payload = error_payload(message or "stream failed", "STREAM_FAILED", trace_id) if legacy else {"message": message or "stream failed"}
    return f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
