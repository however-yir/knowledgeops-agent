package com.enterprise.iqk.evaluation;

import com.enterprise.iqk.evaluation.vo.EvalMetricSummaryVO;
import com.enterprise.iqk.evaluation.vo.EvalResultVO;
import com.enterprise.iqk.evaluation.vo.EvalRunVO;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

@Component
public class EvaluationReportRenderer {

    public String render(EvalRunVO run) {
        List<String> lines = new ArrayList<>();
        lines.add("# RAG Evaluation Report");
        lines.add("");
        lines.add("- Run ID: `" + run.getRunId() + "`");
        lines.add("- Dataset ID: `" + run.getDatasetId() + "`");
        lines.add("- Tenant: `" + run.getTenantId() + "`");
        lines.add("- Model Profile: `" + run.getModelProfile() + "`");
        lines.add("- Status: `" + run.getStatus() + "`");
        lines.add("- Generated At: " + LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        lines.add("");
        lines.add("## Metrics");
        lines.add("");
        lines.add("| Metric | Value |");
        lines.add("| --- | ---: |");
        EvalMetricSummaryVO m = run.getMetrics();
        lines.add("| Run Score | " + pct(m.getRunScore()) + " |");
        lines.add("| Retrieval Hit Rate | " + pct(m.getRetrievalHitRate()) + " |");
        lines.add("| Citation Coverage | " + pct(m.getCitationCoverageRate()) + " |");
        lines.add("| Answer Faithfulness | " + pct(m.getAnswerFaithfulnessScore()) + " |");
        lines.add("| Avg Latency | " + String.format(Locale.ROOT, "%.1f ms", m.getAvgLatencyMs()) + " |");
        lines.add("| Failure Rate | " + pct(m.getFailureRate()) + " |");
        lines.add("");
        lines.add("## Cases");
        lines.add("");
        lines.add("| Case | Status | Score | Retrieval | Citation | Faithfulness | Latency |");
        lines.add("| --- | --- | ---: | ---: | ---: | ---: | ---: |");
        for (EvalResultVO result : run.getResults()) {
            lines.add("| `" + result.getCaseId() + "` | " + result.getStatus()
                    + " | " + pct(result.getScore())
                    + " | " + pct(result.getRetrievalHit())
                    + " | " + pct(result.getCitationCoverage())
                    + " | " + pct(result.getAnswerFaithfulness())
                    + " | " + result.getLatencyMs() + " ms |");
        }
        lines.add("");
        return String.join("\n", lines);
    }

    private String pct(double value) {
        return String.format(Locale.ROOT, "%.2f%%", value * 100.0);
    }
}
