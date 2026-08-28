"""Pure tokenization and similarity functions used by retrieval pipelines."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


def tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if token]


def cosine_like(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / math.sqrt(len(left) * len(right))


def vector_cosine(query: list[float], document: Any) -> float:
    if not isinstance(document, list) or not query or len(query) != len(document):
        return 0.0
    try:
        values = [float(value) for value in document]
    except (TypeError, ValueError):
        return 0.0
    query_norm = math.sqrt(sum(value * value for value in query))
    document_norm = math.sqrt(sum(value * value for value in values))
    if not query_norm or not document_norm:
        return 0.0
    return sum(left * right for left, right in zip(query, values, strict=True)) / (query_norm * document_norm)


@dataclass(frozen=True, slots=True)
class HybridWeights:
    """Per-source weights for hybrid retrieval fusion (Java parity: HybridWeights).

    Python sources: ``vector`` (semantic/pgvector hits), ``keyword`` (lexical
    hits), ``graph`` (knowledge-graph expansions, scored on the lexical path)
    and ``web`` (reserved for the SearXNG backend). DEFAULT reproduces the
    pre-weights Python ordering exactly: every semantic hit outranks every
    lexical hit, and lexical/graph hits keep their rank order.
    """

    vector: float = 0.70
    keyword: float = 0.15
    graph: float = 0.15
    web: float = 0.0

    def normalized(self) -> HybridWeights:
        total = self.vector + self.keyword + self.graph + self.web
        if total <= 0:
            return BALANCED
        if abs(total - 1.0) < 1e-9:
            return self
        return HybridWeights(self.vector / total, self.keyword / total, self.graph / total, self.web / total)

    @classmethod
    def from_csv(cls, value: str | None) -> HybridWeights:
        """Parse ``vector,keyword,graph,web`` from APP_HYBRID_WEIGHTS."""
        if not value or not value.strip():
            return DEFAULT
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            raise ValueError("hybrid weights must be four comma-separated numbers: vector,keyword,graph,web")
        try:
            vector, keyword, graph, web = (float(part) for part in parts)
        except ValueError as exc:
            raise ValueError("hybrid weight entries must be numbers") from exc
        if min(vector, keyword, graph, web) < 0:
            raise ValueError("hybrid weight entries must be non-negative")
        return cls(vector, keyword, graph, web)


DEFAULT = HybridWeights()
SEMANTIC = HybridWeights(0.85, 0.10, 0.05, 0.0)
KEYWORD = HybridWeights(0.15, 0.55, 0.20, 0.10)
BALANCED = HybridWeights(0.25, 0.30, 0.25, 0.20)
