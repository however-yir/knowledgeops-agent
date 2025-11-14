package com.enterprise.iqk.ingestion.queue;

import com.enterprise.iqk.config.properties.IngestionProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(prefix = "app.ingestion", name = "queue-backend", havingValue = "rabbitmq")
public class RabbitMqIngestionQueue implements IngestionQueue {

    private final RabbitTemplate rabbitTemplate;
    private final IngestionProperties ingestionProperties;

    @Override
    public void publishJob(String jobId, String traceId) {
        Map<String, Object> body = new HashMap<>();
        body.put("jobId", jobId);
        body.put("traceId", traceId == null ? "" : traceId);
        body.put("publishedAt", Instant.now().toEpochMilli());
        rabbitTemplate.convertAndSend(
                ingestionProperties.getRabbit().getExchange(),
                ingestionProperties.getRabbit().getRoutingKey(),
                body
        );
    }

    @Override
    public void publishDlq(String jobId, String traceId, String reason) {
        Map<String, Object> body = new HashMap<>();
        body.put("jobId", jobId);
        body.put("traceId", traceId == null ? "" : traceId);
        body.put("reason", reason == null ? "" : reason);
        body.put("publishedAt", Instant.now().toEpochMilli());
        rabbitTemplate.convertAndSend(
                ingestionProperties.getRabbit().getDlqExchange(),
                ingestionProperties.getRabbit().getDlqRoutingKey(),
                body
        );
    }

    @Override
    public List<IngestionQueueMessage> readBatch(String consumerName, int batchSize, Duration block) {
        return List.of();
    }

    @Override
    public void ack(String consumerName, String recordId) {
        // RabbitMQ listener handles ack automatically.
    }

    @Override
    public void ensureConsumerGroup() {
        // no-op for RabbitMQ
    }
}
