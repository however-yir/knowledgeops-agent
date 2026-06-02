package com.enterprise.iqk.evaluation.vo;

import lombok.Data;

@Data
public class EvalRunRequestVO {
    private String datasetId;
    private String modelProfile;
    private String chatIdPrefix;
}
