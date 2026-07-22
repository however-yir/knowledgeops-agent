import { Injectable } from "@nestjs/common";

import type { EvaluationRunView } from "./evaluation.service.js";

@Injectable()
export class EvaluationReportRenderer {
  render(run: EvaluationRunView): string {
    const lines = [
      "# RAG Evaluation Report",
      "",
      `- Run ID: \`${run.runId}\``,
      `- Dataset ID: \`${run.datasetId}\``,
      `- Tenant: \`${run.tenantId}\``,
      `- Model Profile: \`${run.modelProfile}\``,
      `- Status: \`${run.status}\``,
      `- Generated At: ${localDateTime()}`,
      "",
      "## Metrics",
      "",
      "| Metric | Value |",
      "| --- | ---: |",
      `| Run Score | ${pct(run.metrics.runScore)} |`,
      `| Retrieval Hit Rate | ${pct(run.metrics.retrievalHitRate)} |`,
      `| Citation Coverage | ${pct(run.metrics.citationCoverageRate)} |`,
      `| Answer Faithfulness | ${pct(run.metrics.answerFaithfulnessScore)} |`,
      `| Avg Latency | ${run.metrics.avgLatencyMs.toFixed(1)} ms |`,
      `| Failure Rate | ${pct(run.metrics.failureRate)} |`,
      "",
      "## Cases",
      "",
      "| Case | Status | Score | Retrieval | Citation | Faithfulness | Latency |",
      "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
      ...run.results.map((result) => [
        `| \`${result.caseId}\` | ${result.status}`,
        pct(result.score),
        pct(result.retrievalHit),
        pct(result.citationCoverage),
        pct(result.answerFaithfulness),
        `${result.latencyMs} ms |`
      ].join(" | ")),
      ""
    ];
    return lines.join("\n");
  }
}

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function localDateTime(date = new Date()): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().replace(/Z$/, "");
}
