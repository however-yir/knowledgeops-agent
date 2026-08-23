package com.enterprise.iqk.ingestion.queue;

import java.time.Duration;
import java.util.List;

public interface IngestionQueue {
    void publishJob(String jobId, String traceId);

    void publishDlq(String jobId, String traceId, String reason);

    List<IngestionQueueMessage> readBatch(String consumerName, int batchSize, Duration block);

    void ack(String consumerName, String recordId);

    void ensureConsumerGroup();

    /**
     * Reclaims messages that were delivered to another consumer but never acked
     * (idle for at least {@code minIdle}). Returns an empty list when the backend
     * does not support reclaiming.
     */
    default List<IngestionQueueMessage> claimIdle(String consumerName, Duration minIdle, int maxCount) {
        return List.of();
    }
}
