from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from knowledgeops_py.domain.context import TenantContext


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
class RemoteHttpReranker:
    url: str

    async def rank(self, context: TenantContext, query: str, documents: list[str]) -> list[float]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.url, json={"query": query, "documents": documents, "tenantId": context.tenant_id})
            response.raise_for_status()
            body = response.json()
        return [float(score) for score in body["scores"]]
