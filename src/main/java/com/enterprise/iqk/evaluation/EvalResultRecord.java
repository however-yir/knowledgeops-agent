package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("eval_result")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EvalResultRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String resultId;
    private String runId;
    private String datasetId;
    private String caseId;
    private String tenantId;
    private String status;
    private String questionText;
    private String answerText;
    private String citationsJson;
    private String evidenceJson;
    private Double retrievalHit;
    private Double citationCoverage;
    private Double keywordScore;
    private Double answerFaithfulness;
    private Double score;
    private Long latencyMs;
    private String errorMessage;
    private LocalDateTime createdAt;
}
