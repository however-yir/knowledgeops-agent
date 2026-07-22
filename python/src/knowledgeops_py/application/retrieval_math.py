"""Pure tokenization and similarity functions used by retrieval pipelines."""

from __future__ import annotations

import math
import re
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
