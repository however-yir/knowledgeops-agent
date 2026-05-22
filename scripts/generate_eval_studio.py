#!/usr/bin/env python3
"""Generate a compact RAG evaluation studio report.

The regression gate already scores every case. This script turns the latest
regression JSON into a reviewer-friendly quality dashboard that can be attached
to releases, evidence packs, or portfolio pages.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


QUALITY_BANDS = [
    (0.90, "excellent"),
    (0.75, "healthy"),
    (0.60, "watch"),
    (0.00, "needs_attention"),
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def band_for(value: float) -> str:
    for threshold, label in QUALITY_BANDS:
        if value >= threshold:
            return label
    return "unknown"


def metric_delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(current - baseline, 4)


def get_summary(report: dict) -> dict:
    return report.get("summary", {})


def build_studio_report(current: dict, baseline: dict | None) -> dict:
    current_summary = get_summary(current)
    baseline_summary = get_summary(baseline or {})

    metrics = {}
    for key in [
        "pass_rate",
        "correctness_rate",
        "citation_hit_rate",
        "hallucination_rate",
        "failure_rate",
        "avg_score",
        "first_token_latency_p95_ms",
        "total_latency_avg_ms",
    ]:
        current_value = current_summary.get(key)
        baseline_value = baseline_summary.get(key)
        metrics[key] = {
            "current": current_value,
            "baseline": baseline_value,
            "delta": metric_delta(current_value, baseline_value),
        }

    failed_cases = [
        case
        for case in current.get("cases", [])
        if not case.get("pass", False) or case.get("failed", False)
    ]
    citation_misses = [
        case
        for case in current.get("cases", [])
        if case.get("citation_required") and not case.get("citation_hit")
    ]
    hallucination_cases = [
        case for case in current.get("cases", []) if case.get("forbidden_hit")
    ]

    score = float(current_summary.get("pass_rate", 0.0) or 0.0)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if current_summary.get("gate_passed") else "fail",
        "quality_band": band_for(score),
        "metrics": metrics,
        "risk_queues": {
            "failed_cases": failed_cases,
            "citation_misses": citation_misses,
            "hallucination_cases": hallucination_cases,
        },
        "gate_checks": current_summary.get("gate_checks", {}),
    }


def fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(report: dict) -> str:
    lines = [
        "# RAG Evaluation Studio",
        "",
        f"- Generated At (UTC): {report['generated_at_utc']}",
        f"- Status: {report['status'].upper()}",
        f"- Quality Band: {report['quality_band']}",
        "",
        "## Scorecard",
        "",
        "| Metric | Current | Baseline | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]

    for key, values in report["metrics"].items():
        lines.append(
            f"| `{key}` | {fmt(values['current'])} | "
            f"{fmt(values['baseline'])} | {fmt(values['delta'])} |"
        )

    lines.extend(["", "## Gate Checks", ""])
    for key, passed in report["gate_checks"].items():
        lines.append(f"- `{key}`: {'PASS' if passed else 'FAIL'}")

    lines.extend(["", "## Risk Queues", ""])
    for queue_name, cases in report["risk_queues"].items():
        lines.append(f"### {queue_name}")
        if not cases:
            lines.append("")
            lines.append("No cases.")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Case | Category | Score | Status |")
        lines.append("| --- | --- | ---: | --- |")
        for case in cases:
            lines.append(
                f"| {case.get('id', '-')} | {case.get('category', '-')} | "
                f"{fmt(case.get('score'))} | {case.get('status', '-')} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--current",
        default="reports/regression/latest.json",
        help="Current regression report JSON",
    )
    parser.add_argument("--baseline", default=None, help="Optional baseline report JSON")
    parser.add_argument(
        "--output-json",
        default="evaluation/reports/studio-summary.json",
        help="Output studio summary JSON",
    )
    parser.add_argument(
        "--output-md",
        default="evaluation/reports/studio-summary.md",
        help="Output studio summary markdown",
    )
    args = parser.parse_args()

    current = load_json(Path(args.current))
    baseline = load_json(Path(args.baseline)) if args.baseline else None
    report = build_studio_report(current, baseline)

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(report), encoding="utf-8")

    print(f"written: {output_json}")
    print(f"written: {output_md}")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
