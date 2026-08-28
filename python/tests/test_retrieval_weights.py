"""Tests for configurable hybrid-retrieval weights (Java parity #115)."""

from __future__ import annotations

from typing import Any

import pytest

from knowledgeops_py.app import retrieve_chunks_with_semantics
from knowledgeops_py.application.retrieval_math import (
    BALANCED,
    DEFAULT,
    KEYWORD,
    SEMANTIC,
    HybridWeights,
)
from knowledgeops_py.domain.context import TenantContext


def test_weights_normalize_to_one() -> None:
    assert HybridWeights(2, 1, 1, 0).normalized() == HybridWeights(0.5, 0.25, 0.25, 0.0)
    assert HybridWeights(0.4, 0.25, 0.2, 0.15).normalized() == HybridWeights(0.4, 0.25, 0.2, 0.15)
    assert HybridWeights(0, 0, 0, 0).normalized() == BALANCED
    assert DEFAULT.normalized() == DEFAULT
    for preset in (SEMANTIC, KEYWORD, BALANCED):
        total = preset.vector + preset.keyword + preset.graph + preset.web
        assert abs(total - 1.0) < 1e-9


def test_weights_from_csv() -> None:
    assert HybridWeights.from_csv(None) == DEFAULT
    assert HybridWeights.from_csv("") == DEFAULT
    assert HybridWeights.from_csv("0.5, 0.3, 0.1, 0.1") == HybridWeights(0.5, 0.3, 0.1, 0.1)
    with pytest.raises(ValueError, match="four comma-separated"):
        HybridWeights.from_csv("0.5,0.5")
    with pytest.raises(ValueError, match="must be numbers"):
        HybridWeights.from_csv("a,b,c,d")
    with pytest.raises(ValueError, match="non-negative"):
        HybridWeights.from_csv("-1,0.5,0.3,0.2")


class FakeEmbedding:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding

    async def embed(self, context: Any, texts: list[str]) -> list[list[float]]:
        return [self.embedding for _ in texts]


def _chunk(chunk_id: str, content: str, *, embedding: list[float] | None = None, source: str | None = None) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "chunkId": chunk_id,
        "tenantId": "tenant-a",
        "chatId": "chat-1",
        "sourceName": "notes.txt",
        "title": "notes",
        "chunkIndex": 0,
        "content": content,
    }
    if embedding is not None:
        chunk["embedding"] = embedding
    if source is not None:
        chunk["_retrievalSource"] = source
    return chunk


def _context() -> TenantContext:
    return TenantContext("trace", "tenant-a", "retrieval", (), (), "retrieval")


async def _fuse(chunks: list[dict[str, Any]], weights: HybridWeights) -> list[str]:
    result = await retrieve_chunks_with_semantics(
        chunks,
        "heat safety",
        _context(),
        FakeEmbedding([1.0, 0.0]),
        None,
        False,
        weights=weights,
    )
    return [citation.chunkId for citation in result["citations"]]


def test_default_weights_preserve_semantic_first_ordering() -> None:
    semantic = _chunk("a", "heat safety rules", embedding=[1.0, 0.1])
    lexical = _chunk("b", "heat safety")

    import asyncio

    order = asyncio.run(_fuse([semantic, lexical], DEFAULT))
    assert order == ["a", "b"]


def test_keyword_preset_promotes_strong_lexical_hits() -> None:
    semantic = _chunk("a", "heat safety rules", embedding=[1.0, 0.1])
    lexical = _chunk("b", "heat safety")

    import asyncio

    order = asyncio.run(_fuse([semantic, lexical], KEYWORD))
    # lexical rank 1 (1.0 * 0.55) now outranks the semantic hit (0.995 * 0.15)
    assert order == ["b", "a"]


def test_graph_source_uses_graph_weight() -> None:
    graph = _chunk("g", "heat graph", source="graph")
    plain = _chunk("n", "heat normal rules")

    import asyncio

    default_order = asyncio.run(_fuse([graph, plain], DEFAULT))
    keyword_order = asyncio.run(_fuse([graph, plain], KEYWORD))
    # Under DEFAULT, graph and keyword weights are equal, so lexical rank wins.
    assert default_order == ["g", "n"]
    # Under KEYWORD the plain chunk's lexical weight beats the graph weight.
    assert keyword_order == ["n", "g"]


def test_semantic_hits_below_threshold_never_surface() -> None:
    weak = _chunk("w", "heat safety rules", embedding=[0.0, 1.0])

    import asyncio

    result = asyncio.run(
        retrieve_chunks_with_semantics(
            [weak], "heat safety", _context(), FakeEmbedding([1.0, 0.0]), None, False, weights=SEMANTIC
        )
    )
    # cosine(query, [0,1]) == 0 < 0.45 -> only the lexical path can surface it
    assert [citation.chunkId for citation in result["citations"]] == ["w"]
    assert result["retrievalStats"]["vectorMatches"] == 0
