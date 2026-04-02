#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_case(case, answer: str):
    answer_lower = answer.lower()
    expected = case.get("expected_keywords", [])
    forbidden = case.get("forbidden_keywords", [])

    hit_expected = sum(1 for keyword in expected if keyword.lower() in answer_lower)
    forbidden_hit = [k for k in forbidden if k.lower() in answer_lower]

    expected_score = 1.0 if not expected else hit_expected / len(expected)
    hallucination_penalty = 1.0 if not forbidden_hit else 0.0
    final_score = expected_score * hallucination_penalty

    return {
        "id": case["id"],
        "category": case.get("category", "unknown"),
        "expected_hit": hit_expected,
        "expected_total": len(expected),
        "forbidden_hit": forbidden_hit,
        "score": round(final_score, 4),
        "pass": final_score >= 0.7,
    }


def render_markdown(report):
    lines = [
        "# Regression Report",
        "",
        f"- Generated At (UTC): {report['generated_at_utc']}",
        f"- Dataset Size: {report['summary']['total']}",
        f"- Pass Count: {report['summary']['passed']}",
        f"- Pass Rate: {report['summary']['pass_rate']:.2%}",
        f"- Avg Score: {report['summary']['avg_score']:.4f}",
        "",
        "| ID | Category | Score | Pass | Forbidden Hits |",
        "| --- | --- | ---: | :---: | --- |",
    ]
    for item in report["cases"]:
        lines.append(
            f"| {item['id']} | {item['category']} | {item['score']:.4f} | "
            f"{'Y' if item['pass'] else 'N'} | {', '.join(item['forbidden_hit']) if item['forbidden_hit'] else '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evaluation/dataset.json")
    parser.add_argument("--predictions", default="evaluation/predictions.sample.json")
    parser.add_argument("--report-dir", default="reports/regression")
    parser.add_argument("--threshold", type=float, default=0.70)
    args = parser.parse_args()

    dataset = load_json(Path(args.dataset))
    predictions = load_json(Path(args.predictions))
    pred_map = {item["id"]: item.get("answer", "") for item in predictions}

    case_reports = []
    for case in dataset:
        answer = pred_map.get(case["id"], "")
        case_reports.append(evaluate_case(case, answer))

    total = len(case_reports)
    passed = sum(1 for c in case_reports if c["pass"])
    avg_score = (sum(c["score"] for c in case_reports) / total) if total else 0.0
    pass_rate = (passed / total) if total else 0.0
    hallucination_hits = sum(1 for c in case_reports if c["forbidden_hit"])
    route_cases = [c for c in case_reports if c["category"] == "tool_routing"]
    route_pass = sum(1 for c in route_cases if c["pass"])
    route_acc = (route_pass / len(route_cases)) if route_cases else 0.0

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "pass_rate": pass_rate,
            "avg_score": avg_score,
            "threshold": args.threshold,
            "gate_passed": pass_rate >= args.threshold,
            "hallucination_rate": (hallucination_hits / total) if total else 0.0,
            "tool_route_accuracy": route_acc,
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
    if pass_rate < args.threshold:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
