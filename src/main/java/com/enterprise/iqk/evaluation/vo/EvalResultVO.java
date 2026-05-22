package com.enterprise.iqk.evaluation.vo;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class EvalResultVO {
    private String resultId;
    private String caseId;
    private String status;
    private String question;
    private String answer;
    private List<String> citations;
    private List<String> evidence;
    private double retrievalHit;
    private double citationCoverage;
    private double keywordScore;
    private double answerFaithfulness;
    private double score;
    private long latencyMs;
    private String errorMessage;
}
