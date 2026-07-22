from __future__ import annotations

from knowledgeops_py.scripts.shadow_evidence import evaluate_shadow_evidence


def accepted_evidence() -> dict[str, object]:
    return {
        "requestCount": 10_000,
        "continuousDays": 0,
        "structureDifferenceRate": 0.004,
        "javaErrorRate": 0.01,
        "pythonErrorRate": 0.012,
        "javaP95Ms": 500,
        "pythonP95Ms": 600,
        "crossTenantErrors": 0,
    }


def test_shadow_evidence_accepts_exactly_the_documented_thresholds() -> None:
    decision = evaluate_shadow_evidence(accepted_evidence())

    assert decision["accepted"] is True
    assert decision["failures"] == []
    assert decision["criteria"] == {
        "requestTarget": 10_000,
        "continuousDayTarget": 7,
        "structureDifferenceRateExclusiveMax": 0.005,
        "errorRateDeltaInclusiveMax": 0.002,
        "p95MultiplierInclusiveMax": 1.2,
        "crossTenantErrorsRequired": 0,
    }


def test_shadow_evidence_accepts_the_seven_day_alternative() -> None:
    evidence = accepted_evidence()
    evidence["requestCount"] = 1
    evidence["continuousDays"] = 7

    assert evaluate_shadow_evidence(evidence)["accepted"] is True


def test_shadow_evidence_rejects_each_cutover_breach() -> None:
    evidence = accepted_evidence()
    evidence.update(
        {
            "requestCount": 9_999,
            "structureDifferenceRate": 0.005,
            "pythonErrorRate": 0.0121,
            "pythonP95Ms": 601,
            "crossTenantErrors": 1,
        }
    )

    decision = evaluate_shadow_evidence(evidence)

    assert decision["accepted"] is False
    assert decision["failures"] == [
        "require at least 10000 requests or 7 continuous days",
        "structureDifferenceRate must be below 0.5%",
        "crossTenantErrors must be zero",
        "Python error rate exceeds Java by more than 0.2%",
        "Python p95 exceeds 1.2x Java p95",
    ]


def test_shadow_evidence_rejects_missing_or_invalid_measurements() -> None:
    decision = evaluate_shadow_evidence({"requestCount": True})

    assert decision["accepted"] is False
    assert "requestCount must be a non-negative integer" in decision["failures"]
    assert "structureDifferenceRate must be a finite non-negative number" in decision["failures"]
