package com.enterprise.iqk.evaluation.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class EvalMetricSummaryVO {
    private int totalCases;
    private int passedCases;
    private double runScore;
    private double retrievalHitRate;
    private double citationCoverageRate;
    private double answerFaithfulnessScore;
    private double avgLatencyMs;
    private double failureRate;
}
