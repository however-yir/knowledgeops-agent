from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

from knowledgeops_py.config import Settings
from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.domain.ports import ChatProvider, EmbeddingProvider, Reranker


@dataclass(slots=True)
class OpenAICompatibleChatProvider:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0

    async def complete(self, context: TenantContext, prompt: str, model_profile: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "metadata": {"tenantId": context.tenant_id, "modelProfile": model_profile},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        choice = body["choices"][0]["message"]["content"]
        return {"answer": str(choice), "model": str(body.get("model") or self.model), "usage": body.get("usage") or {}}


@dataclass(slots=True)
class OpenAICompatibleEmbeddingProvider:
    base_url: str
    api_key: str
    model: str

    async def embed(self, context: TenantContext, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            response = await client.post("/embeddings", json={"model": self.model, "input": texts}, headers=headers)
            response.raise_for_status()
            body = response.json()
        return [list(item["embedding"]) for item in body["data"]]


@dataclass(slots=True)
class OllamaChatProvider:
    base_url: str
    model: str
    timeout_seconds: float = 30.0

    async def complete(self, context: TenantContext, prompt: str, model_profile: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": ollama_temperature(model_profile)},
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
        message = body.get("message") or {}
        answer = message.get("content")
        if not isinstance(answer, str):
            raise ValueError("Ollama response did not include message.content")
        return {
            "answer": answer,
            "model": str(body.get("model") or self.model),
            "usage": {
                "prompt_tokens": int(body.get("prompt_eval_count") or 0),
                "completion_tokens": int(body.get("eval_count") or 0),
            },
        }


@dataclass(slots=True)
class OllamaEmbeddingProvider:
    base_url: str
    model: str
    timeout_seconds: float = 30.0

    async def embed(self, context: TenantContext, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = await client.post("/api/embed", json={"model": self.model, "input": texts})
            response.raise_for_status()
            body = response.json()
        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list):
            raise ValueError("Ollama response did not include embeddings")
        return [[float(value) for value in embedding] for embedding in embeddings]


@dataclass(slots=True)
class RemoteHttpReranker:
    url: str

    async def rank(self, context: TenantContext, query: str, documents: list[str]) -> list[float]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.url, json={"query": query, "documents": documents, "tenantId": context.tenant_id})
            response.raise_for_status()
            body = response.json()
        return [float(score) for score in body["scores"]]


@dataclass(slots=True)
class LocalCrossEncoderReranker:
    model_name: str

    async def rank(self, context: TenantContext, query: str, documents: list[str]) -> list[float]:
        return await asyncio.to_thread(local_cross_encoder_scores, self.model_name, query, documents)


def create_chat_provider(settings: Settings) -> ChatProvider | None:
    if settings.model_backend == "ollama":
        return OllamaChatProvider(settings.ollama_base_url, settings.ollama_chat_model)
    if settings.model_base_url and settings.model_api_key:
        return OpenAICompatibleChatProvider(settings.model_base_url, settings.model_api_key, settings.model_name)
    return None


def create_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    if settings.model_backend == "ollama":
        return OllamaEmbeddingProvider(settings.ollama_base_url, settings.ollama_embedding_model)
    if settings.model_base_url and settings.model_api_key:
        return OpenAICompatibleEmbeddingProvider(settings.model_base_url, settings.model_api_key, settings.embedding_model)
    return None


def create_reranker(settings: Settings) -> Reranker | None:
    if settings.reranker_backend == "remote" and settings.reranker_url:
        return RemoteHttpReranker(settings.reranker_url)
    if settings.reranker_backend == "local":
        return LocalCrossEncoderReranker(settings.reranker_model)
    return None


def ollama_temperature(model_profile: str) -> float:
    return {"cheap": 0.2, "balanced": 0.5, "quality": 0.8}.get(model_profile, 0.5)


def local_cross_encoder_scores(model_name: str, query: str, documents: list[str]) -> list[float]:
    try:
        model = cross_encoder(model_name)
    except ModuleNotFoundError as exc:
        raise RerankerUnavailable("local reranker requires the local-reranker dependency") from exc
    scores = model.predict([(query, document) for document in documents])
    return [float(score) for score in scores]


@lru_cache(maxsize=2)
def cross_encoder(model_name: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


class RerankerUnavailable(RuntimeError):
    """The configured local reranker cannot be used by this runtime."""
