"""Translate the legacy Python envelope into the fixed Java HTTP contract."""

from __future__ import annotations

import json
from collections.abc import AsyncIterable, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

LEGACY_PREFIX = "/python/v1"
AUTH_PATHS = {"/auth/token", "/auth/refresh"}
API_KEY_PATHS = {"/auth/api-keys", "/auth/api-keys/rotate", "/auth/api-keys/revoke"}
UPLOAD_PATHS = {"/ai/pdf/upload", "/ingestion/upload"}


def prepare_contract_path(request: Request) -> None:
    """Mark legacy calls and expose their original route to FastAPI."""
    path = request.scope["path"]
    is_legacy = path == LEGACY_PREFIX or path.startswith(f"{LEGACY_PREFIX}/")
    request.scope["knowledgeops.legacy_contract"] = is_legacy
    if is_legacy:
        request.scope["path"] = path.removeprefix(LEGACY_PREFIX) or "/"


def is_legacy_request(request: Request) -> bool:
    return bool(request.scope.get("knowledgeops.legacy_contract"))


async def canonicalize_response(request: Request, response: Response) -> Response:
    """Unwrap legacy JSON responses for the Java-compatible, unprefixed API."""
    if is_legacy_request(request) or "application/json" not in response.headers.get("content-type", ""):
        return response

    body_iterator = getattr(response, "body_iterator", None)
    body = await read_response_body(body_iterator) if body_iterator is not None else response.body
    try:
        payload = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return rebuild_response(response, body)
    if not isinstance(payload, dict) or payload.get("ok") not in (0, 1):
        return rebuild_response(response, body)

    path = request.scope["path"]
    if payload["ok"] == 0:
        canonical_payload: Any = failure_payload(path, str(payload.get("msg") or "request failed"))
    else:
        canonical_payload = success_payload(
            path,
            payload.get("data"),
            str(payload.get("msg") or "ok"),
            request.query_params,
        )

    if payload["ok"] == 1 and path in {"/ai/chat", "/ai/pdf/chat"} and isinstance(canonical_payload, dict):
        answer = str(canonical_payload.get("answer") or "")
        if path == "/ai/pdf/chat" and canonical_payload.get("citations"):
            answer += "\n\n引用来源:\n" + "\n".join(
                f"[{index}] {citation_label(citation)}"
                for index, citation in enumerate(canonical_payload["citations"], start=1)
            )
        return PlainTextResponse(answer, status_code=response.status_code, media_type="text/html; charset=utf-8")
    return json_response(response, canonical_payload)


async def read_response_body(body_iterator: AsyncIterable[bytes]) -> bytes:
    return b"".join([chunk async for chunk in body_iterator])


def rebuild_response(response: Response, body: bytes) -> Response:
    rebuilt = Response(content=body, status_code=response.status_code, media_type=response.media_type)
    copy_headers(response, rebuilt)
    return rebuilt


def json_response(response: Response, payload: Any) -> JSONResponse:
    rebuilt = JSONResponse(content=payload, status_code=response.status_code)
    copy_headers(response, rebuilt)
    return rebuilt


def copy_headers(source: Response, target: Response) -> None:
    preserved = [(key, value) for key, value in source.raw_headers if key.lower() not in {b"content-length", b"content-type"}]
    target.raw_headers.extend(preserved)


def success_payload(path: str, data: Any, message: str, query: Mapping[str, str]) -> Any:
    if path in AUTH_PATHS:
        return auth_token_payload(data, 1, message)
    if path in API_KEY_PATHS:
        return api_key_payload(data, 1, message)
    if any(path.startswith(prefix) for prefix in UPLOAD_PATHS):
        return {"ok": 1, "msg": message, "job": ingestion_job_payload(data)}
    if path in {"/ai/react/chat", "/ai/workflow/react/chat"}:
        return react_response_payload(data)
    if path == "/ai/evaluation/datasets":
        if isinstance(data, list):
            return [evaluation_dataset_payload(item) for item in data]
        return evaluation_dataset_payload(data)
    if path.startswith("/ai/evaluation/datasets/") and path.endswith("/comparison"):
        return evaluation_comparison_payload(data)
    if is_evaluation_run_path(path):
        return evaluation_run_payload(data)
    if path == "/ai/sessions":
        return paged_session_payload(data, query)
    if is_session_branch_compare_path(path):
        return session_branch_compare_payload(data)
    if is_session_branch_merge_path(path):
        return session_branch_merge_payload(data)
    if is_session_state_path(path):
        return session_state_payload(data)
    if path == "/ai/feedback":
        return result_payload(1, "ok")
    return data


def failure_payload(path: str, message: str) -> dict[str, Any]:
    if path in AUTH_PATHS:
        return auth_token_payload({}, 0, message)
    if path in API_KEY_PATHS:
        return api_key_payload({}, 0, message)
    return result_payload(0, message, code="REQUEST_FAILED")


def auth_token_payload(data: Any, ok: int, message: str) -> dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    return {
        "ok": ok,
        "msg": message,
        "token": source.get("token"),
        "refreshToken": source.get("refreshToken"),
        "tenantId": source.get("tenantId"),
        "expiresInSeconds": source.get("expiresInSeconds"),
        "refreshExpiresAt": source.get("refreshExpiresAt"),
        "refreshWillExpireSoon": source.get("refreshWillExpireSoon"),
    }


def api_key_payload(data: Any, ok: int, message: str) -> dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    return {
        "ok": ok,
        "msg": message,
        "keyName": source.get("keyName"),
        "tenantId": source.get("tenantId"),
        "rawApiKey": source.get("rawApiKey"),
        "expiresAt": source.get("expiresAt"),
    }


def ingestion_job_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    return {
        "jobId": data.get("jobId"),
        "chatId": data.get("chatId"),
        "sourceName": data.get("sourceName"),
        "status": data.get("status"),
        "attemptCount": data.get("attemptCount"),
        "maxRetries": data.get("maxRetries"),
        "errorMessage": data.get("errorMessage"),
        "traceId": data.get("traceId"),
        "queueBackend": data.get("queueBackend"),
        "createdAt": data.get("createdAt"),
        "startedAt": data.get("startedAt"),
        "finishedAt": data.get("finishedAt"),
    }


def react_response_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    model = str(source.get("model") or "")
    profile = model.rsplit("-", maxsplit=1)[-1] if "-" in model else model
    return {
        "ok": 1,
        "msg": "ok",
        "chatId": source.get("chatId"),
        "answer": source.get("answer"),
        "citations": source.get("citations") or [],
        "evidence": source.get("evidence") or [],
        "routeProfile": profile,
        "routeReason": "python profile routing",
        "routeCostTier": profile,
        "experimentKey": "",
        "experimentVariant": "",
        "experimentBucket": None,
        "trace": [react_trace_payload(trace) for trace in source.get("trace") or []],
    }


def react_trace_payload(trace: Any) -> dict[str, Any]:
    source = model_data(trace)
    thought = source.get("thought") or source.get("thoughtSummary") or ""
    return {
        "step": source.get("step"),
        "thought": thought,
        "thoughtSummary": thought,
        "action": source.get("action"),
        "actionInput": source.get("actionInput") or {},
        "observation": source.get("observation"),
    }


def model_data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def evaluation_dataset_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    cases = source.get("cases")
    return {
        "datasetId": source.get("datasetId"),
        "tenantId": source.get("tenantId"),
        "name": source.get("name"),
        "description": source.get("description"),
        "baselineRunId": source.get("baselineRunId"),
        "caseCount": source.get("caseCount") if source.get("caseCount") is not None else len(cases or []),
        "createdAt": source.get("createdAt"),
        "updatedAt": source.get("updatedAt"),
    }


def evaluation_comparison_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    return {
        "dataset": evaluation_dataset_payload(source.get("dataset")),
        "baseline": evaluation_run_payload(source.get("baseline")) if source.get("baseline") is not None else None,
        "current": evaluation_run_payload(source.get("current")) if source.get("current") is not None else None,
    }


def is_evaluation_run_path(path: str) -> bool:
    return path == "/ai/evaluation/runs" or (
        path.startswith("/ai/evaluation/runs/") and not path.endswith("/report")
    ) or (path.startswith("/ai/evaluation/datasets/") and path.endswith("/runs"))


def evaluation_run_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    metrics = model_data(source.get("metrics"))
    return {
        "runId": source.get("runId"),
        "datasetId": source.get("datasetId"),
        "tenantId": source.get("tenantId"),
        "status": "SUCCESS" if source.get("status") == "COMPLETED" else source.get("status"),
        "modelProfile": source.get("modelProfile"),
        "metrics": {
            "totalCases": metrics.get("totalCases", 0),
            "passedCases": metrics.get("passedCases", 0),
            "runScore": metrics.get("runScore", 0.0),
            "retrievalHitRate": metrics.get("retrievalHitRate", 0.0),
            "citationCoverageRate": metrics.get("citationCoverageRate", 0.0),
            "answerFaithfulnessScore": metrics.get("answerFaithfulnessScore", 0.0),
            "avgLatencyMs": metrics.get("avgLatencyMs", 0.0),
            "failureRate": metrics.get("failureRate", 0.0),
        },
        "results": [evaluation_result_payload(item) for item in source.get("results") or []],
        "errorMessage": source.get("errorMessage"),
        "startedAt": source.get("startedAt") or "",
        "finishedAt": source.get("finishedAt") or "",
        "createdAt": source.get("createdAt") or "",
    }


def evaluation_result_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    return {
        "resultId": source.get("resultId"),
        "caseId": source.get("caseId"),
        "status": source.get("status"),
        "question": source.get("question"),
        "answer": source.get("answer") or "",
        "citations": source.get("citations") or [],
        "evidence": source.get("evidence") or [],
        "retrievalHit": source.get("retrievalHit", 0.0),
        "citationCoverage": source.get("citationCoverage", 0.0),
        "keywordScore": source.get("keywordScore", 0.0),
        "answerFaithfulness": source.get("answerFaithfulness", 0.0),
        "score": source.get("score", 0.0),
        "latencyMs": source.get("latencyMs", 0),
        "errorMessage": source.get("errorMessage"),
    }


def paged_session_payload(data: Any, query: Mapping[str, str]) -> dict[str, Any]:
    items = [item for item in (data if isinstance(data, list) else []) if session_matches(item, query)]
    page = positive_int(query.get("page"), default=1)
    page_size = positive_int(query.get("pageSize"), default=20)
    start = (page - 1) * page_size
    return {
        "items": [session_state_payload(item) for item in items[start : start + page_size]],
        "total": len(items),
        "page": page,
        "pageSize": page_size,
    }


def session_matches(session: Any, query: Mapping[str, str]) -> bool:
    source = model_data(session)
    if query.get("includeArchived", "false").lower() != "true" and source.get("archived"):
        return False
    search = query.get("search", "").strip().lower()
    if search and search not in str(source.get("title") or "").lower():
        return False
    workspace = query.get("workspace")
    return not workspace or workspace == (source.get("workspaceId") or source.get("workspace") or "default")


def session_state_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    return {
        "id": source.get("id") or source.get("sessionId"),
        "title": source.get("title"),
        "updatedAt": epoch_millis(source.get("updatedAt")),
        "modelProfile": source.get("modelProfile") or "balanced",
        "streaming": bool(source.get("streaming", True)),
        "pinned": bool(source.get("pinned", False)),
        "archived": bool(source.get("archived", False)),
        "workspaceId": source.get("workspaceId") or source.get("workspace") or "default",
        "activeBranchId": source.get("activeBranchId"),
        "branches": [branch_state_payload(branch) for branch in source.get("branches") or []],
    }


def branch_state_payload(branch: Any) -> dict[str, Any]:
    source = model_data(branch)
    return {
        "id": source.get("id") or source.get("branchId"),
        "title": source.get("title"),
        "parentBranchId": source.get("parentBranchId"),
        "parentMessageId": source.get("parentMessageId"),
        "updatedAt": epoch_millis_or_none(source.get("updatedAt")),
        "messages": [session_message_payload(item) for item in source["messages"]]
        if isinstance(source.get("messages"), list)
        else None,
        "traceSteps": source.get("traceSteps"),
    }


def is_session_state_path(path: str) -> bool:
    parts = path.split("/")
    return path.startswith("/ai/sessions/") and (len(parts) == 4 or parts[-1] in {"pin", "archive"})


def is_session_branch_compare_path(path: str) -> bool:
    return path.startswith("/ai/sessions/") and path.endswith("/branches/compare")


def is_session_branch_merge_path(path: str) -> bool:
    return path.startswith("/ai/sessions/") and path.endswith("/branches/merge")


def session_branch_compare_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    return {
        "sourceBranchId": source.get("sourceBranchId"),
        "targetBranchId": source.get("targetBranchId"),
        "sourceMessageCount": source.get("sourceMessageCount", 0),
        "targetMessageCount": source.get("targetMessageCount", 0),
        "commonMessageCount": source.get("commonMessageCount", 0),
        "sourceOnlyCount": source.get("sourceOnlyCount", 0),
        "targetOnlyCount": source.get("targetOnlyCount", 0),
        "sourceOnlyPreview": source.get("sourceOnlyPreview") or [],
        "targetOnlyPreview": source.get("targetOnlyPreview") or [],
    }


def session_branch_merge_payload(data: Any) -> dict[str, Any]:
    source = model_data(data)
    return {
        "session": session_state_payload(source.get("session")),
        "mergedBranch": branch_state_payload(source.get("mergedBranch")),
        "mergedMessageCount": source.get("mergedMessageCount", 0),
    }


def session_message_payload(message: Any) -> dict[str, Any]:
    source = model_data(message)
    return {
        "id": source.get("id"),
        "role": source.get("role"),
        "content": source.get("content"),
        "createdAt": epoch_millis_or_none(source.get("createdAt")),
        "state": source.get("state"),
        "citations": source.get("citations"),
        "evidence": source.get("evidence"),
        "taskId": source.get("taskId"),
        "traceId": source.get("traceId"),
        "memorySnapshot": source.get("memorySnapshot"),
        "workflowState": source.get("workflowState"),
    }


def positive_int(value: str | None, default: int) -> int:
    try:
        return max(1, int(value)) if value is not None else default
    except ValueError:
        return default


def epoch_millis(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            pass
    return int(datetime.now(UTC).timestamp() * 1000)


def epoch_millis_or_none(value: Any) -> int | None:
    return epoch_millis(value) if value is not None else None


def result_payload(ok: int, message: str, code: str | None = None) -> dict[str, Any]:
    return {"ok": ok, "msg": message, "code": code, "traceId": None, "data": None}


def citation_label(citation: Any) -> str:
    if isinstance(citation, dict):
        return str(citation.get("title") or citation.get("source") or "source")
    return str(citation)
