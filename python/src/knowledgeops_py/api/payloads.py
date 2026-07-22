"""Shared API envelope and request-payload helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from knowledgeops_py.dto import ChatRequestDto


def ok(data: Any, msg: str = "ok", trace_id: str | None = None) -> dict[str, Any]:
    payload = data.model_dump() if hasattr(data, "model_dump") else data
    return {"ok": 1, "msg": msg, "data": payload, "traceId": trace_id}


def fail(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def error_payload(msg: str, code: str, trace_id: str) -> dict[str, Any]:
    return {"ok": 0, "msg": msg, "code": code, "traceId": trace_id}


def chat_request_payload(
    payload: ChatRequestDto | None, prompt: str | None, chat_id: str | None, model_profile: str | None
) -> ChatRequestDto:
    if payload is not None:
        return payload
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chatId is required")
    return ChatRequestDto(chatId=chat_id, prompt=prompt, modelProfile=model_profile or "balanced")
