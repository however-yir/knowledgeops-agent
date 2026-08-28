"""Web-search backend tests (Java parity: SearXNG web source + SSRF guard)."""

from __future__ import annotations

import asyncio
import hashlib
import socket
from typing import Any

import pytest

from knowledgeops_py.app import retrieve_hybrid
from knowledgeops_py.domain.context import TenantContext
from knowledgeops_py.domain.runtime import PlatformStore
from knowledgeops_py.infrastructure import web_search as web_search_module
from knowledgeops_py.infrastructure.url_guard import UnsafeBaseUrlError
from knowledgeops_py.infrastructure.web_search import SearxngWebSearchBackend, create_web_search_backend


class FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class FakeAsyncClient:
    requests: list[dict[str, Any]] = []

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, params: dict[str, str] | None = None, headers: Any = None) -> FakeResponse:
        FakeAsyncClient.requests.append({"url": url, "params": params})
        return FakeResponse(
            {
                "results": [
                    {"title": "Heat safety", "content": "Provide shade and water.", "url": "https://gov.example/heat"},
                    {"title": "Empty", "content": "", "url": "https://skip.example/x"},
                ]
            }
        )


@pytest.fixture(autouse=True)
def _resolve_test_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    """searx.example has no real DNS record; pin it to a public address so the
    SSRF guard's live resolution succeeds (its fail-closed behaviour is what
    the internal-address tests assert)."""

    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host: str, port: Any, **kwargs: Any):
        if host == "searx.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
        return real_getaddrinfo(host, port, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_construction_rejects_internal_base_urls() -> None:
    for url in ("http://127.0.0.1:8080", "http://169.254.169.254", "http://10.0.0.9/search", "file:///tmp"):
        with pytest.raises(UnsafeBaseUrlError):
            SearxngWebSearchBackend(url)


def test_search_maps_results_to_web_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr(web_search_module.httpx, "AsyncClient", FakeAsyncClient)
    backend = SearxngWebSearchBackend("https://searx.example")
    context = TenantContext("trace", "tenant-a", "retrieval", (), (), "retrieval")

    chunks = asyncio.run(backend.search(context, "heat safety", 5))

    assert FakeAsyncClient.requests[0]["params"]["q"] == "heat safety"
    assert [chunk["chunkId"] for chunk in chunks] == ["web_" + hashlib.sha256(b"https://gov.example/heat").hexdigest()[:16]]
    chunk = chunks[0]
    assert chunk["sourceName"] == "web"
    assert chunk["_retrievalSource"] == "web"
    assert "heat" in chunk["content"]


def test_search_wraps_http_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingClient(FakeAsyncClient):
        async def get(self, url: str, params: dict[str, str] | None = None, headers: Any = None) -> FakeResponse:
            import httpx

            raise httpx.ConnectTimeout("backend down")

    FakeAsyncClient.requests = []
    monkeypatch.setattr(web_search_module.httpx, "AsyncClient", FailingClient)
    backend = SearxngWebSearchBackend("https://searx.example")

    with pytest.raises(web_search_module.WebSearchUnavailable):
        asyncio.run(backend.search(TenantContext("t", "tenant-a", "r", (), (), "retrieval"), "query", 5))


def test_factory_requires_backend_configuration() -> None:
    assert create_web_search_backend(type("S", (), {"web_search_backend": "none"})()) is None

    class Settings:
        web_search_backend = "searxng"
        web_search_base_url = None
        web_search_api_key = None
        web_search_timeout_seconds = 3.0

    with pytest.raises(ValueError, match="APP_WEB_SEARCH_BASE_URL"):
        create_web_search_backend(Settings())


def test_retrieve_hybrid_surfaces_web_results_with_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.requests = []
    monkeypatch.setattr(web_search_module.httpx, "AsyncClient", FakeAsyncClient)
    store = PlatformStore()
    backend = SearxngWebSearchBackend("https://searx.example")

    result = asyncio.run(
        retrieve_hybrid(
            store,
            "tenant-a",
            "chat-web",
            "heat safety",
            None,
            None,
            None,
            None,
            False,
            None,
            None,
            backend,
        )
    )

    sources = [citation.source for citation in result["citations"]]
    assert "web" in sources


def test_retrieve_hybrid_degrades_when_web_backend_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingBackend:
        async def search(self, context: Any, query: str, top_k: int) -> list[dict[str, Any]]:
            raise web_search_module.WebSearchUnavailable("down")

    store = PlatformStore()
    result = asyncio.run(
        retrieve_hybrid(
            store,
            "tenant-a",
            "chat-web",
            "heat safety",
            None,
            None,
            None,
            None,
            False,
            None,
            None,
            FailingBackend(),
        )
    )
    assert "retrievalStats" in result
