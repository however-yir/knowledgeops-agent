"""Evaluate desensitized aggregate evidence from a Java/Python shadow run."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

STRUCTURE_DIFFERENCE_LIMIT = 0.005
ERROR_RATE_DELTA_LIMIT = 0.002
P95_MULTIPLIER_LIMIT = 1.2
REQUEST_TARGET = 10_000
CONTINUOUS_DAY_TARGET = 7


def evaluate_shadow_evidence(evidence: Mapping[str, object]) -> dict[str, object]:
    """Return a non-secret cutover decision for aggregate shadow measurements."""
    failures: list[str] = []
    request_count = _nonnegative_integer(evidence, "requestCount", failures)
    continuous_days = _nonnegative_integer(evidence, "continuousDays", failures)
    structure_difference = _rate(evidence, "structureDifferenceRate", failures)
    java_error_rate = _rate(evidence, "javaErrorRate", failures)
    python_error_rate = _rate(evidence, "pythonErrorRate", failures)
    java_p95 = _nonnegative_number(evidence, "javaP95Ms", failures)
    python_p95 = _nonnegative_number(evidence, "pythonP95Ms", failures)
    cross_tenant_errors = _nonnegative_integer(evidence, "crossTenantErrors", failures)

    if request_count is not None and continuous_days is not None and request_count < REQUEST_TARGET and continuous_days < CONTINUOUS_DAY_TARGET:
        failures.append(f"require at least {REQUEST_TARGET} requests or {CONTINUOUS_DAY_TARGET} continuous days")
    if structure_difference is not None and structure_difference >= STRUCTURE_DIFFERENCE_LIMIT:
        failures.append(f"structureDifferenceRate must be below {STRUCTURE_DIFFERENCE_LIMIT:.1%}")
    if cross_tenant_errors is not None and cross_tenant_errors != 0:
        failures.append("crossTenantErrors must be zero")
    if java_error_rate is not None and python_error_rate is not None and python_error_rate - java_error_rate > ERROR_RATE_DELTA_LIMIT:
        failures.append(f"Python error rate exceeds Java by more than {ERROR_RATE_DELTA_LIMIT:.1%}")
    if java_p95 is not None and python_p95 is not None and python_p95 > java_p95 * P95_MULTIPLIER_LIMIT:
        failures.append(f"Python p95 exceeds {P95_MULTIPLIER_LIMIT:.1f}x Java p95")

    return {
        "accepted": not failures,
        "failures": failures,
        "criteria": {
            "requestTarget": REQUEST_TARGET,
            "continuousDayTarget": CONTINUOUS_DAY_TARGET,
            "structureDifferenceRateExclusiveMax": STRUCTURE_DIFFERENCE_LIMIT,
            "errorRateDeltaInclusiveMax": ERROR_RATE_DELTA_LIMIT,
            "p95MultiplierInclusiveMax": P95_MULTIPLIER_LIMIT,
            "crossTenantErrorsRequired": 0,
        },
        "observed": {
            "requestCount": request_count,
            "continuousDays": continuous_days,
            "structureDifferenceRate": structure_difference,
            "javaErrorRate": java_error_rate,
            "pythonErrorRate": python_error_rate,
            "javaP95Ms": java_p95,
            "pythonP95Ms": python_p95,
            "crossTenantErrors": cross_tenant_errors,
        },
    }


def _nonnegative_integer(evidence: Mapping[str, object], name: str, failures: list[str]) -> int | None:
    value = evidence.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        failures.append(f"{name} must be a non-negative integer")
        return None
    return value


def _rate(evidence: Mapping[str, object], name: str, failures: list[str]) -> float | None:
    value = _nonnegative_number(evidence, name, failures)
    if value is not None and value > 1:
        failures.append(f"{name} must be between 0 and 1")
        return None
    return value


def _nonnegative_number(evidence: Mapping[str, object], name: str, failures: list[str]) -> float | None:
    value = evidence.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        failures.append(f"{name} must be a finite non-negative number")
        return None
    return float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path, help="path to desensitized aggregate shadow metrics JSON")
    arguments = parser.parse_args()
    try:
        parsed: Any = json.loads(arguments.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read shadow evidence: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("shadow evidence must be a JSON object")

    decision = evaluate_shadow_evidence(parsed)
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    if not decision["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
