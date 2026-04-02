package com.demo.ai.ingestion.queue;

import com.demo.ai.config.properties.IngestionProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.connection.stream.*;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Component
@ConditionalOnProperty(prefix = "app.ingestion", name = "queue-backend", havingValue = "redis_stream")
@RequiredArgsConstructor
public class RedisStreamIngestionQueue implements IngestionQueue {

    private final StringRedisTemplate redisTemplate;
    private final IngestionProperties ingestionProperties;

    @Override
    public void publishJob(String jobId, String traceId) {
        Map<String, String> body = new HashMap<>();
        body.put("jobId", jobId);
        body.put("traceId", traceId == null ? "" : traceId);
        body.put("publishedAt", String.valueOf(Instant.now().toEpochMilli()));
        redisTemplate.opsForStream().add(ingestionProperties.getRedis().getStreamKey(), body);
    }

    @Override
    public void publishDlq(String jobId, String traceId, String reason) {
        Map<String, String> body = new HashMap<>();
        body.put("jobId", jobId);
        body.put("traceId", traceId == null ? "" : traceId);
        body.put("reason", reason == null ? "" : reason);
        body.put("publishedAt", String.valueOf(Instant.now().toEpochMilli()));
        redisTemplate.opsForStream().add(ingestionProperties.getRedis().getDlqStreamKey(), body);
    }

    @Override
    public List<IngestionQueueMessage> readBatch(String consumerName, int batchSize, Duration block) {
        StreamReadOptions options = StreamReadOptions.empty()
                .count(Math.max(1, batchSize))
                .block(block == null ? Duration.ofSeconds(2) : block);
        List<MapRecord<String, Object, Object>> records = redisTemplate.opsForStream()
                .read(
                        Consumer.from(ingestionProperties.getRedis().getConsumerGroup(), consumerName),
                        options,
                        StreamOffset.create(ingestionProperties.getRedis().getStreamKey(), ReadOffset.lastConsumed())
                );
        if (records == null || records.isEmpty()) {
            return Collections.emptyList();
        }
        return records.stream().map(record -> IngestionQueueMessage.builder()
                .recordId(record.getId().getValue())
                .jobId(valueAsString(record.getValue().get("jobId")))
                .traceId(valueAsString(record.getValue().get("traceId")))
                .build()).toList();
    }

    @Override
    public void ack(String consumerName, String recordId) {
        if (!StringUtils.hasText(recordId)) {
            return;
        }
        redisTemplate.opsForStream().acknowledge(
                ingestionProperties.getRedis().getStreamKey(),
                ingestionProperties.getRedis().getConsumerGroup(),
                RecordId.of(recordId)
        );
    }

    @Override
    public void ensureConsumerGroup() {
        String streamKey = ingestionProperties.getRedis().getStreamKey();
        String group = ingestionProperties.getRedis().getConsumerGroup();
        try {
            // ensure stream exists
            redisTemplate.opsForStream().add(streamKey, Map.of("init", "1"));
            redisTemplate.opsForStream().createGroup(streamKey, ReadOffset.latest(), group);
            log.info("Created redis stream consumer group: {}", group);
        } catch (Exception e) {
            if (!e.getMessage().contains("BUSYGROUP")) {
                log.debug("Consumer group create skipped: {}", e.getMessage());
            }
        }
    }

    private String valueAsString(Object val) {
        return val == null ? "" : String.valueOf(val);
    }
}
