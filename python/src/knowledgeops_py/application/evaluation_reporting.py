"""Pure presentation rules for Java-compatible evaluation results."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def evaluation_comparison_data(dataset: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    recent = sorted(runs, key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    current = recent[0] if recent else None
    baseline_id = dataset.get("baselineRunId")
    baseline = next((run for run in recent if run.get("runId") == baseline_id), None)
    if baseline is None and len(recent) > 1:
        baseline = recent[1]
    return {"dataset": dataset, "baseline": baseline, "current": current}


def evaluation_report_markdown(run: dict[str, Any]) -> str:
    metrics = run["metrics"]
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Run ID: `{run['runId']}`",
        f"- Dataset ID: `{run['datasetId']}`",
        f"- Tenant: `{run['tenantId']}`",
        f"- Model Profile: `{run['modelProfile']}`",
        f"- Status: `{java_evaluation_status(run['status'])}`",
        f"- Generated At: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Run Score | {percent(metrics.get('runScore', 0.0))} |",
        f"| Retrieval Hit Rate | {percent(metrics.get('retrievalHitRate', 0.0))} |",
        f"| Citation Coverage | {percent(metrics.get('citationCoverageRate', 0.0))} |",
        f"| Answer Faithfulness | {percent(metrics.get('answerFaithfulnessScore', 0.0))} |",
        f"| Avg Latency | {float(metrics.get('avgLatencyMs', 0.0)):.1f} ms |",
        f"| Failure Rate | {percent(metrics.get('failureRate', 0.0))} |",
        "",
        "## Cases",
        "",
        "| Case | Status | Score | Retrieval | Citation | Faithfulness | Latency |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        "| `{caseId}` | {status} | {score} | {retrieval} | {citation} | {faithfulness} | {latency} ms |".format(
            caseId=result["caseId"],
            status=result["status"],
            score=percent(result["score"]),
            retrieval=percent(result["retrievalHit"]),
            citation=percent(result["citationCoverage"]),
            faithfulness=percent(result["answerFaithfulness"]),
            latency=result["latencyMs"],
        )
        for result in run["results"]
    )
    return "\n".join([*lines, ""])


def percent(value: float) -> str:
    return f"{float(value) * 100:.2f}%"


def java_evaluation_status(value: str) -> str:
    return "SUCCESS" if value == "COMPLETED" else value
