package com.enterprise.iqk.ingestion.queue;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.List;

@Component
@ConditionalOnMissingBean(IngestionQueue.class)
public class NoopIngestionQueue implements IngestionQueue {
    @Override
    public void publishJob(String jobId, String traceId) {
        // noop
    }

    @Override
    public void publishDlq(String jobId, String traceId, String reason) {
        // noop
    }

    @Override
    public List<IngestionQueueMessage> readBatch(String consumerName, int batchSize, Duration block) {
        return List.of();
    }

    @Override
    public void ack(String consumerName, String recordId) {
        // noop
    }

    @Override
    public void ensureConsumerGroup() {
        // noop
    }
}
