package com.enterprise.iqk.evaluation.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class EvalComparisonVO {
    private EvalDatasetVO dataset;
    private EvalRunVO baseline;
    private EvalRunVO current;
}
