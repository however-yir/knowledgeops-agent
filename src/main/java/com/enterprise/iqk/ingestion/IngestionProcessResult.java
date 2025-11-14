package com.enterprise.iqk.ingestion;

import com.enterprise.iqk.domain.enums.IngestionJobStatus;
import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class IngestionProcessResult {
    private String jobId;
    private IngestionJobStatus status;
    private boolean picked;
    private String traceId;
    private String errorMessage;
}
