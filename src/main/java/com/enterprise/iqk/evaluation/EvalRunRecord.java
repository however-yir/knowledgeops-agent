package com.enterprise.iqk.evaluation;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("eval_run")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EvalRunRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String runId;
    private String datasetId;
    private String tenantId;
    private String status;
    private String modelProfile;
    private Integer totalCases;
    private Integer passedCases;
    private Double runScore;
    private Double retrievalHitRate;
    private Double citationCoverageRate;
    private Double answerFaithfulnessScore;
    private Double avgLatencyMs;
    private Double failureRate;
    private String errorMessage;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
