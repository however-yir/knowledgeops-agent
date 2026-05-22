package com.enterprise.iqk.evaluation.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class EvalDatasetVO {
    private String datasetId;
    private String tenantId;
    private String name;
    private String description;
    private String baselineRunId;
    private int caseCount;
    private String createdAt;
    private String updatedAt;
}
