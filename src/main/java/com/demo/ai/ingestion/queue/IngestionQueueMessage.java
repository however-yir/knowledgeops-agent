package com.demo.ai.ingestion.queue;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class IngestionQueueMessage {
    private String recordId;
    private String jobId;
    private String traceId;
}
