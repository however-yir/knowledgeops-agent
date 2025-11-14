package com.enterprise.iqk.domain.vo;

import com.enterprise.iqk.domain.enums.IngestionJobStatus;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class IngestionJobVO {
    private String jobId;
    private String chatId;
    private String sourceName;
    private IngestionJobStatus status;
    private Integer attemptCount;
    private Integer maxRetries;
    private String errorMessage;
    private String traceId;
    private String queueBackend;
    private LocalDateTime createdAt;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;
}
