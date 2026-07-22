"""Translate the legacy Python envelope into the fixed Java HTTP contract."""

from __future__ import annotations

import json
from collections.abc import AsyncIterable
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
        canonical_payload = success_payload(path, payload.get("data"), str(payload.get("msg") or "ok"))

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


def success_payload(path: str, data: Any, message: str) -> Any:
    if path in AUTH_PATHS:
        return auth_token_payload(data, 1, message)
    if path in API_KEY_PATHS:
        return api_key_payload(data, 1, message)
    if any(path.startswith(prefix) for prefix in UPLOAD_PATHS):
        return {"ok": 1, "msg": message, "job": ingestion_job_payload(data)}
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


def result_payload(ok: int, message: str, code: str | None = None) -> dict[str, Any]:
    return {"ok": ok, "msg": message, "code": code, "traceId": None, "data": None}


def citation_label(citation: Any) -> str:
    if isinstance(citation, dict):
        return str(citation.get("title") or citation.get("source") or "source")
    return str(citation)
