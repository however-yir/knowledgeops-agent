"""Pure scoring rules for RAG evaluation cases."""

from __future__ import annotations

from typing import Any


def score_evaluation_case(
    case: dict[str, Any], answer: str, citations: list[str], evidence: list[str], failed: bool
) -> dict[str, float]:
    answer_pool = (answer + "\n" + "\n".join(evidence)).lower()
    expected_keywords = [str(item).lower() for item in case.get("expectedKeywords", [])]
    expected_citations = [str(item).lower() for item in case.get("expectedCitations", [])]
    forbidden_keywords = [str(item).lower() for item in case.get("forbiddenKeywords", [])]
    keyword_score = hit_rate(expected_keywords, answer_pool) if expected_keywords else float(bool(answer))
    citation_coverage = hit_rate(expected_citations, "\n".join(citations).lower()) if expected_citations else 1.0
    retrieval_hit = (
        float(bool(citations) or bool(evidence) or keyword_score > 0)
        if not expected_citations
        else float(citation_coverage > 0)
    )
    if failed or not answer:
        answer_faithfulness = 0.0
    elif not citations:
        answer_faithfulness = 0.5
    else:
        answer_faithfulness = min(
            1.0,
            sum(f"[{index}]" in answer for index in range(1, len(citations) + 1)) / len(citations),
        )
    if any(keyword and keyword in answer_pool for keyword in forbidden_keywords):
        keyword_score = 0.0
        answer_faithfulness = min(answer_faithfulness, 0.2)
    return {
        "retrievalHit": _round4(retrieval_hit),
        "citationCoverage": _round4(citation_coverage),
        "keywordScore": _round4(keyword_score),
        "answerFaithfulness": _round4(answer_faithfulness),
        "score": _round4(
            0.30 * retrieval_hit
            + 0.25 * citation_coverage
            + 0.25 * keyword_score
            + 0.20 * answer_faithfulness
        ),
    }


def hit_rate(expected: list[str], actual: str) -> float:
    return sum(item in actual for item in expected) / len(expected) if expected else 1.0


def _round4(value: float) -> float:
    return round(value, 4)
