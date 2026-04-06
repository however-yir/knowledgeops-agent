#!/usr/bin/env python3
"""
Generate a compact benchmark report from k6 summary-export JSON.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def metric_values(metrics: dict[str, Any], metric_name: str) -> dict[str, Any]:
    direct = metrics.get(metric_name, {})
    values = direct.get("values", {})
    if values:
        return values
    for key, payload in metrics.items():
        if key.startswith(metric_name):
            values = payload.get("values", {})
            if values:
                return values
    return {}


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_summary(summary_path: Path) -> dict[str, Any]:
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})

    duration_values = metric_values(metrics, "http_req_duration")
    failed_values = metric_values(metrics, "http_req_failed")
    request_values = metric_values(metrics, "http_reqs")
    check_values = metric_values(metrics, "checks")

    throughput = as_float(request_values.get("rate"))
    total_requests = int(as_float(request_values.get("count")))
    p95 = as_float(duration_values.get("p(95)"))
    p99 = as_float(duration_values.get("p(99)"))
    avg = as_float(duration_values.get("avg"))
    error_rate = as_float(failed_values.get("rate"))
    checks_rate = as_float(check_values.get("rate"), default=1.0)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summaryFile": str(summary_path),
        "throughputRps": throughput,
        "totalRequests": total_requests,
        "latencyMs": {
            "avg": avg,
            "p95": p95,
            "p99": p99,
        },
        "errorRate": error_rate,
        "checkPassRate": checks_rate,
    }


def markdown_report(report: dict[str, Any], p95_target: float, error_rate_target: float) -> str:
    p95_value = report["latencyMs"]["p95"]
    error_rate = report["errorRate"]
    p95_status = "PASS" if p95_value <= p95_target else "FAIL"
    error_status = "PASS" if error_rate <= error_rate_target else "FAIL"
    return "\n".join(
        [
            "# k6 Performance Report",
            "",
            f"- Generated At (UTC): `{report['generatedAt']}`",
            f"- Summary Source: `{report['summaryFile']}`",
            "",
            "## Key Metrics",
            "",
            "| Metric | Value | Target | Status |",
            "|---|---:|---:|---|",
            f"| Throughput (req/s) | {report['throughputRps']:.2f} | - | - |",
            f"| Total Requests | {report['totalRequests']} | - | - |",
            f"| Latency P95 (ms) | {p95_value:.2f} | <= {p95_target:.2f} | {p95_status} |",
            f"| Latency P99 (ms) | {report['latencyMs']['p99']:.2f} | - | - |",
            f"| Error Rate | {error_rate:.4f} | <= {error_rate_target:.4f} | {error_status} |",
            f"| Check Pass Rate | {report['checkPassRate']:.4f} | >= 0.9900 | {'PASS' if report['checkPassRate'] >= 0.99 else 'WARN'} |",
            "",
            "## Interpretation",
            "",
            f"- P95 latency target: **{p95_status}**",
            f"- Error rate target: **{error_status}**",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate k6 performance report from summary JSON")
    parser.add_argument(
        "--summary",
        default="reports/performance/distributed-k6-summary.json",
        help="k6 summary-export json path",
    )
    parser.add_argument(
        "--output-json",
        default="reports/performance/k6-report.json",
        help="json output path",
    )
    parser.add_argument(
        "--output-md",
        default="reports/performance/k6-report.md",
        help="markdown output path",
    )
    parser.add_argument("--p95-target", type=float, default=1500.0, help="P95 latency target in ms")
    parser.add_argument("--error-rate-target", type=float, default=0.02, help="error rate target")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)

    report = read_summary(summary_path)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(
        markdown_report(report, args.p95_target, args.error_rate_target),
        encoding="utf-8",
    )
    print(f"Generated: {output_json}")
    print(f"Generated: {output_md}")


if __name__ == "__main__":
    main()
