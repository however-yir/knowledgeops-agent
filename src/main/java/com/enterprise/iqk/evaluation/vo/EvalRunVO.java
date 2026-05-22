package com.enterprise.iqk.evaluation.vo;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class EvalRunVO {
    private String runId;
    private String datasetId;
    private String tenantId;
    private String status;
    private String modelProfile;
    private EvalMetricSummaryVO metrics;
    private List<EvalResultVO> results;
    private String errorMessage;
    private String startedAt;
    private String finishedAt;
    private String createdAt;
}
