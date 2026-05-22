#!/usr/bin/env python3
"""Generate evaluation report from demo paths dataset and predictions JSON.

Usage:
    python3 scripts/generate_eval_report.py \
        --dataset evaluation/demo-paths-dataset.json \
        --predictions evaluation/predictions.demo-paths.json \
        --output evaluation/reports/latest-evaluation-report.md
"""

import json
import argparse
import os
from datetime import datetime, timezone


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_sample_predictions(dataset):
    """Generate a sample predictions file for demo purposes."""
    preds = {"generated_at": datetime.now(timezone.utc).isoformat(), "results": {}}
    for path_key, path_data in dataset.get("paths", {}).items():
        for case in path_data.get("cases", []):
            preds["results"][case["id"]] = {
                "status": "pending",
                "note": "Placeholder — run actual evaluation to populate",
            }
    return preds


def evaluate(dataset, predictions):
    metrics = {}
    for path_key, path_data in dataset.get("paths", {}).items():
        total = len(path_data.get("cases", []))
        passed = 0
        failed = 0
        pending = 0
        details = []

        for case in path_data.get("cases", []):
            pid = case["id"]
            pred = predictions.get("results", {}).get(pid, {})
            pred_status = pred.get("status", "pending")

            if pred_status == "pending":
                pending += 1
                details.append({"id": pid, "result": "pending"})
            elif pred_status == "pass":
                passed += 1
                details.append({"id": pid, "result": "pass"})
            else:
                failed += 1
                details.append({"id": pid, "result": "fail", "note": pred.get("note", "")})

        metrics[path_key] = {
            "name": path_data.get("name", path_key),
            "total": total,
            "passed": passed,
            "failed": failed,
            "pending": pending,
            "pass_rate": round(passed / max(total, 1), 3),
            "details": details,
        }

    # Compute overall
    total_all = sum(m["total"] for m in metrics.values())
    passed_all = sum(m["passed"] for m in metrics.values())
    failed_all = sum(m["failed"] for m in metrics.values())
    pending_all = sum(m["pending"] for m in metrics.values())

    metrics["overall"] = {
        "name": "Overall",
        "total": total_all,
        "passed": passed_all,
        "failed": failed_all,
        "pending": pending_all,
        "pass_rate": round(passed_all / max(total_all, 1), 3),
    }
    return metrics


def render_markdown(metrics, threshold=0.60):
    lines = []
    lines.append("# Evaluation Report — Demo Paths")
    lines.append(f"")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Pass threshold: {threshold * 100:.0f}%")
    lines.append("")

    for key, m in metrics.items():
        if key == "overall":
            continue
        status_icon = "✅" if m["pass_rate"] >= threshold else "⚠️"
        lines.append(f"## {status_icon} {m['name']}")
        lines.append(f"")
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Total | {m['total']} |")
        lines.append(f"| Passed | {m['passed']} |")
        lines.append(f"| Failed | {m['failed']} |")
        lines.append(f"| Pending | {m['pending']} |")
        lines.append(f"| Pass Rate | {m['pass_rate'] * 100:.1f}% |")
        lines.append("")

        if m["details"]:
            lines.append("| Case ID | Result | Note |")
            lines.append("|---|---|---|")
            for d in m["details"]:
                note = d.get("note", "-")
                icon = "✅" if d["result"] == "pass" else ("❌" if d["result"] == "fail" else "⏳")
                lines.append(f"| {d['id']} | {icon} {d['result']} | {note} |")
            lines.append("")

    # Overall summary
    overall = metrics.get("overall", {})
    lines.append(f"## 📊 Overall")
    lines.append(f"")
    all_green = overall.get("pass_rate", 0) >= threshold
    lines.append(f"**Status: {'✅ ALL PASS' if all_green else '⚠️ BELOW THRESHOLD'}**")
    lines.append(f"")
    lines.append(f"- Total cases: {overall.get('total', 0)}")
    lines.append(f"- Passed: {overall.get('passed', 0)}")
    lines.append(f"- Failed: {overall.get('failed', 0)}")
    lines.append(f"- Pending (not yet evaluated): {overall.get('pending', 0)}")
    lines.append(f"- Overall pass rate: {overall.get('pass_rate', 0) * 100:.1f}%")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation report for demo paths")
    parser.add_argument("--dataset", required=True, help="Path to dataset JSON")
    parser.add_argument("--predictions", required=True, help="Path to predictions JSON")
    parser.add_argument("--output", default="evaluation/reports/latest-evaluation-report.md", help="Output markdown path")
    parser.add_argument("--threshold", type=float, default=0.60, help="Pass rate threshold")
    parser.add_argument("--init", action="store_true", help="Initialize a sample predictions file")
    args = parser.parse_args()

    dataset = load_json(args.dataset)

    if args.init:
        preds = create_sample_predictions(dataset)
        os.makedirs(os.path.dirname(args.predictions), exist_ok=True)
        with open(args.predictions, "w", encoding="utf-8") as f:
            json.dump(preds, f, indent=2, ensure_ascii=False)
        print(f"Sample predictions written to {args.predictions}")
        print("Fill in actual results, then re-run without --init.")
        return

    predictions = load_json(args.predictions)
    metrics = evaluate(dataset, predictions)
    report = render_markdown(metrics, args.threshold)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written to {args.output}")

    overall = metrics.get("overall", {})
    if overall.get("pass_rate", 0) >= args.threshold:
        print("PASS")
    else:
        print("FAIL")
        exit(1)


if __name__ == "__main__":
    main()
