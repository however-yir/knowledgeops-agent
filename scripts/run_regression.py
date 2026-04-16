#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


SUCCESS_STATUSES = {"ok", "success", "done"}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def to_lower_set(values):
    result = set()
    for value in values or []:
        if value is None:
            continue
        text = str(value).strip().lower()
        if text:
            result.add(text)
    return result


def percentile(values, p):
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * weight)


def normalize_prediction(raw):
    item = raw or {}
    status = str(item.get("status", "ok")).strip().lower() or "ok"
    answer = str(item.get("answer", "") or "")
    citations = item.get("citations")
    if not isinstance(citations, list):
        citations = []

    first_token_latency_ms = item.get("first_token_latency_ms")
    total_latency_ms = item.get("total_latency_ms")

    def as_float(value):
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "id": item.get("id"),
        "answer": answer,
        "citations": [str(c).strip() for c in citations if str(c).strip()],
        "status": status,
        "error": str(item.get("error", "") or "").strip(),
        "first_token_latency_ms": as_float(first_token_latency_ms),
        "total_latency_ms": as_float(total_latency_ms),
    }


def evaluate_case(case, prediction, per_case_threshold):
    answer = prediction["answer"]
    answer_lower = answer.lower()
    expected = case.get("expected_keywords", [])
    forbidden = case.get("forbidden_keywords", [])
    expected_citations = case.get("expected_citations", [])

    expected_hit = [k for k in expected if str(k).lower() in answer_lower]
    forbidden_hit = [k for k in forbidden if str(k).lower() in answer_lower]

    expected_score = 1.0 if not expected else len(expected_hit) / len(expected)
    hallucination_penalty = 0.0 if forbidden_hit else 1.0
    score = round(expected_score * hallucination_penalty, 4)

    citation_pool = "\n".join(prediction["citations"]).lower()
    citation_required = bool(case.get("citation_required", False) or expected_citations or str(case.get("category", "")).startswith("rag"))
    citation_hit = True
    if citation_required:
        if expected_citations:
            expected_cite_tokens = to_lower_set(expected_citations)
            citation_hit = bool(expected_cite_tokens) and all(token in citation_pool for token in expected_cite_tokens)
        else:
            citation_hit = len(prediction["citations"]) > 0

    status_ok = prediction["status"] in SUCCESS_STATUSES
    has_answer = bool(answer.strip())
    failed = (not status_ok) or (not has_answer)

    score_pass = score >= per_case_threshold
    passed = score_pass and citation_hit and (not failed)

    return {
        "id": case.get("id", ""),
        "category": case.get("category", "unknown"),
        "expected_hit": len(expected_hit),
        "expected_total": len(expected),
        "forbidden_hit": forbidden_hit,
        "score": score,
        "score_pass": score_pass,
        "citation_required": citation_required,
        "citation_hit": citation_hit,
        "citation_count": len(prediction["citations"]),
        "first_token_latency_ms": prediction["first_token_latency_ms"],
        "total_latency_ms": prediction["total_latency_ms"],
        "status": prediction["status"],
        "error": prediction["error"],
        "failed": failed,
        "pass": passed,
    }


def summarize(cases, args):
    total = len(cases)
    if total == 0:
        return {
            "total": 0,
            "passed": 0,
            "pass_rate": 0.0,
            "correctness_rate": 0.0,
            "citation_hit_rate": 0.0,
            "citation_required_cases": 0,
            "hallucination_rate": 0.0,
            "failure_rate": 0.0,
            "avg_score": 0.0,
            "first_token_latency_avg_ms": None,
            "first_token_latency_p95_ms": None,
            "total_latency_avg_ms": None,
            "gate_passed": False,
            "gate_checks": {},
        }

    passed = sum(1 for item in cases if item["pass"])
    correctness = sum(1 for item in cases if item["score_pass"])
    hallucination_hits = sum(1 for item in cases if item["forbidden_hit"])
    failed = sum(1 for item in cases if item["failed"])

    citation_cases = [item for item in cases if item["citation_required"]]
    citation_hits = sum(1 for item in citation_cases if item["citation_hit"])

    first_token_samples = [item["first_token_latency_ms"] for item in cases if item["first_token_latency_ms"] is not None]
    total_latency_samples = [item["total_latency_ms"] for item in cases if item["total_latency_ms"] is not None]

    pass_rate = passed / total
    correctness_rate = correctness / total
    hallucination_rate = hallucination_hits / total
    failure_rate = failed / total
    citation_hit_rate = (citation_hits / len(citation_cases)) if citation_cases else 1.0

    first_token_avg = mean(first_token_samples) if first_token_samples else None
    first_token_p95 = percentile(first_token_samples, 95) if first_token_samples else None
    total_latency_avg = mean(total_latency_samples) if total_latency_samples else None

    checks = {
        "correctness_rate": correctness_rate >= args.correctness_threshold,
        "citation_hit_rate": citation_hit_rate >= args.citation_hit_threshold,
        "hallucination_rate": hallucination_rate <= args.hallucination_max_rate,
        "failure_rate": failure_rate <= args.failure_max_rate,
    }

    if args.require_latency:
        checks["first_token_latency_p95_ms"] = (
            first_token_p95 is not None and first_token_p95 <= args.first_token_max_ms
        )
    elif first_token_p95 is not None:
        checks["first_token_latency_p95_ms"] = first_token_p95 <= args.first_token_max_ms
    else:
        checks["first_token_latency_p95_ms"] = True

    gate_passed = all(checks.values())

    return {
        "total": total,
        "passed": passed,
        "pass_rate": pass_rate,
        "correctness_rate": correctness_rate,
        "citation_hit_rate": citation_hit_rate,
        "citation_required_cases": len(citation_cases),
        "hallucination_rate": hallucination_rate,
        "failure_rate": failure_rate,
        "avg_score": mean(item["score"] for item in cases),
        "first_token_latency_avg_ms": first_token_avg,
        "first_token_latency_p95_ms": first_token_p95,
        "total_latency_avg_ms": total_latency_avg,
        "gate_passed": gate_passed,
        "gate_checks": checks,
    }


def render_markdown(report):
    summary = report["summary"]

    def fmt_ms(value):
        return "-" if value is None else f"{value:.2f}"

    lines = [
        "# Regression Report",
        "",
        f"- Generated At (UTC): {report['generated_at_utc']}",
        f"- Dataset Size: {summary['total']}",
        f"- Pass Count: {summary['passed']}",
        f"- Gate Passed: {'YES' if summary['gate_passed'] else 'NO'}",
        "",
        "## Core Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Pass Rate | {summary['pass_rate']:.2%} |",
        f"| Correctness Rate | {summary['correctness_rate']:.2%} |",
        f"| Citation Hit Rate | {summary['citation_hit_rate']:.2%} |",
        f"| Hallucination Rate | {summary['hallucination_rate']:.2%} |",
        f"| Failure Rate | {summary['failure_rate']:.2%} |",
        f"| Avg Score | {summary['avg_score']:.4f} |",
        f"| First Token Avg (ms) | {fmt_ms(summary['first_token_latency_avg_ms'])} |",
        f"| First Token P95 (ms) | {fmt_ms(summary['first_token_latency_p95_ms'])} |",
        f"| Total Latency Avg (ms) | {fmt_ms(summary['total_latency_avg_ms'])} |",
        "",
        "## Gate Checks",
        "",
    ]

    for key, value in summary["gate_checks"].items():
        lines.append(f"- `{key}`: {'PASS' if value else 'FAIL'}")

    lines.extend([
        "",
        "## Case Details",
        "",
        "| ID | Category | Score | Citation | Status | Failed | Pass |",
        "| --- | --- | ---: | :---: | --- | :---: | :---: |",
    ])

    for item in report["cases"]:
        lines.append(
            f"| {item['id']} | {item['category']} | {item['score']:.4f} | "
            f"{'Y' if item['citation_hit'] else 'N'} | {item['status']} | "
            f"{'Y' if item['failed'] else 'N'} | {'Y' if item['pass'] else 'N'} |"
        )

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/dataset.json")
    parser.add_argument("--predictions", default="evaluation/predictions.sample.json")
    parser.add_argument("--report-dir", default="reports/regression")

    # Keep backward compatibility with existing usage (--threshold)
    parser.add_argument("--threshold", type=float, default=0.70, help="Per-case correctness threshold (legacy alias)")
    parser.add_argument("--correctness-threshold", type=float, default=0.75)
    parser.add_argument("--citation-hit-threshold", type=float, default=0.80)
    parser.add_argument("--hallucination-max-rate", type=float, default=0.15)
    parser.add_argument("--first-token-max-ms", type=float, default=4000)
    parser.add_argument("--failure-max-rate", type=float, default=0.10)
    parser.add_argument("--require-latency", action="store_true", default=False)
    args = parser.parse_args()

    dataset = load_json(Path(args.dataset))
    raw_predictions = load_json(Path(args.predictions))

    if isinstance(raw_predictions, dict):
        pred_map = {key: normalize_prediction(value) for key, value in raw_predictions.items()}
    else:
        pred_map = {}
        for item in raw_predictions:
            normalized = normalize_prediction(item)
            pred_map[str(normalized.get("id", ""))] = normalized

    case_reports = []
    for case in dataset:
        case_id = str(case.get("id", ""))
        prediction = pred_map.get(case_id, normalize_prediction({"id": case_id, "status": "missing", "answer": ""}))
        case_reports.append(evaluate_case(case, prediction, per_case_threshold=args.threshold))

    summary = summarize(case_reports, args)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "thresholds": {
            "per_case_score_threshold": args.threshold,
            "correctness_threshold": args.correctness_threshold,
            "citation_hit_threshold": args.citation_hit_threshold,
            "hallucination_max_rate": args.hallucination_max_rate,
            "first_token_max_ms": args.first_token_max_ms,
            "failure_max_rate": args.failure_max_rate,
            "require_latency": args.require_latency,
        },
        "cases": case_reports,
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_json = report_dir / "latest.json"
    latest_md = report_dir / "latest.md"

    latest_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")

    print(f"written: {latest_json}")
    print(f"written: {latest_md}")

    if not summary["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
