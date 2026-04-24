package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.enterprise.iqk.domain.enums.IngestionJobStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("ingestion_job")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class IngestionJob {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String jobId;
    private String tenantId;
    private String chatId;
    private String sourceType;
    private String sourceName;
    private String filePath;
    private String idempotencyKey;
    private IngestionJobStatus status;
    private String traceId;
    private Integer attemptCount;
    private Integer maxRetries;
    private String errorMessage;
    private LocalDateTime nextRetryAt;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
