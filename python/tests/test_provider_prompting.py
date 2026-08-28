"""Tests for the externalized RAG system prompt and configurable answer temperature.

Java parity (a373082): rag.temperature (default 0.2) and SystemConstants
prompts; the OpenAI-compatible payload must stay unchanged when no system
prompt or temperature is requested.
"""

from __future__ import annotations

from typing import Any

import pytest

from knowledgeops_py.application.system_prompts import HYBRID_RAG_ANSWER_SYSTEM
from knowledgeops_py.config import Settings
from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure import providers as provider_module
from knowledgeops_py.infrastructure.providers import (
    OllamaChatProvider,
    OpenAICompatibleChatProvider,
)

CONTEXT = TenantContext("trace", "tenant-a", "alice", (), (), "api_key")


class FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class FakeAsyncClient:
    sent: list[dict[str, Any]] = []

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str] | None = None) -> FakeResponse:
        FakeAsyncClient.sent.append({"url": url, "json": json})
        if url.endswith("/chat/completions"):
            body: dict[str, Any] = {
                "choices": [{"message": {"content": "ok"}}],
                "model": "stub-model",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        else:
            body = {"message": {"content": "ok"}, "model": "stub-model"}
        return FakeResponse(body)


@pytest.fixture(autouse=True)
def capture_http(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    FakeAsyncClient.sent = []
    monkeypatch.setattr(provider_module.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient.sent


def test_openai_payload_unchanged_without_system_or_temperature() -> None:
    provider = OpenAICompatibleChatProvider(base_url="http://model", api_key="k", model="m")

    import asyncio

    asyncio.run(provider.complete(CONTEXT, "hello", "balanced"))

    payload = FakeAsyncClient.sent[0]["json"]
    assert [message["role"] for message in payload["messages"]] == ["user"]
    assert "temperature" not in payload


def test_openai_payload_includes_system_and_temperature() -> None:
    provider = OpenAICompatibleChatProvider(base_url="http://model", api_key="k", model="m")

    import asyncio

    asyncio.run(provider.complete(CONTEXT, "hello", "balanced", system=HYBRID_RAG_ANSWER_SYSTEM, temperature=0.2))

    payload = FakeAsyncClient.sent[0]["json"]
    assert payload["messages"][0] == {"role": "system", "content": HYBRID_RAG_ANSWER_SYSTEM}
    assert payload["messages"][1] == {"role": "user", "content": "hello"}
    assert payload["temperature"] == 0.2


def test_ollama_temperature_override_and_profile_default() -> None:
    provider = OllamaChatProvider(base_url="http://ollama", model="qwen")

    import asyncio

    asyncio.run(provider.complete(CONTEXT, "hello", "balanced", temperature=0.2))
    assert FakeAsyncClient.sent[-1]["json"]["options"]["temperature"] == 0.2

    asyncio.run(provider.complete(CONTEXT, "hello", "quality"))
    assert FakeAsyncClient.sent[-1]["json"]["options"]["temperature"] == 0.8


def test_rag_answer_temperature_setting_defaults_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from knowledgeops_py.config import load_settings

    assert Settings().rag_answer_temperature == 0.2
    monkeypatch.setenv("APP_RAG_ANSWER_TEMPERATURE", "0.35")
    assert load_settings().rag_answer_temperature == 0.35
