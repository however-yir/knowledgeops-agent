package com.enterprise.iqk.evaluation.vo;

import lombok.Data;

import java.util.List;

@Data
public class EvalDatasetCreateVO {
    private String name;
    private String description;
    private List<EvalCaseCreateVO> cases;
}
