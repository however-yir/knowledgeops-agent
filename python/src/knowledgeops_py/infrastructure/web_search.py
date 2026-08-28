"""Web-search retrieval backends for the hybrid pipeline.

Java parity: retrieval/web/SearXNGBackend. The configured base URL is
validated by the SSRF guard (infrastructure/url_guard) at construction time —
fail-closed, so a misconfigured internal address can never be fetched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.infrastructure.url_guard import require_safe_base_url


class WebSearchUnavailable(RuntimeError):
    """The web-search backend could not complete a request."""


@dataclass(slots=True)
class SearxngWebSearchBackend:
    """Self-hosted SearXNG JSON API backend."""

    base_url: str
    api_key: str | None = None
    timeout_seconds: float = 3.0
    max_results: int = 5

    def __post_init__(self) -> None:
        require_safe_base_url(self.base_url, setting="APP_WEB_SEARCH_BASE_URL")

    async def search(self, context: TenantContext, query: str, top_k: int) -> list[dict[str, Any]]:
        params = {"q": query, "format": "json"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = await client.get("/search", params=params, headers=headers)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WebSearchUnavailable("web search backend is unavailable") from exc
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise WebSearchUnavailable("web search backend returned an unexpected payload")
        chunks: list[dict[str, Any]] = []
        for index, item in enumerate(results[: max(1, top_k)]):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            title = str(item.get("title") or "web result")
            content = str(item.get("content") or "")
            if not url or not content:
                continue
            chunks.append(
                {
                    "chunkId": f"web_{hashlib.sha256(url.encode()).hexdigest()[:16]}",
                    "tenantId": context.tenant_id,
                    "chatId": "",
                    "sourceName": "web",
                    "title": title,
                    "chunkIndex": index,
                    "content": f"{title}: {content} (source: {url})",
                    "_retrievalSource": "web",
                }
            )
        return chunks


def create_web_search_backend(settings: Any) -> SearxngWebSearchBackend | None:
    """Factory honouring APP_WEB_SEARCH_BACKEND (none | searxng)."""
    backend = getattr(settings, "web_search_backend", "none")
    if backend != "searxng":
        return None
    if not settings.web_search_base_url:
        raise ValueError("APP_WEB_SEARCH_BASE_URL is required when APP_WEB_SEARCH_BACKEND=searxng")
    return SearxngWebSearchBackend(
        settings.web_search_base_url,
        settings.web_search_api_key,
        settings.web_search_timeout_seconds,
    )
