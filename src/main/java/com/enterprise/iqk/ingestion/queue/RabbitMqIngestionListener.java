package com.enterprise.iqk.ingestion.queue;

import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.ingestion.IngestionProcessResult;
import com.enterprise.iqk.ingestion.IngestionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(prefix = "app.ingestion", name = "queue-backend", havingValue = "rabbitmq")
public class RabbitMqIngestionListener {

    private final IngestionService ingestionService;
    private final IngestionProperties ingestionProperties;

    @RabbitListener(
            queues = "${app.ingestion.rabbit.queue}",
            concurrency = "${app.ingestion.worker-count:3}",
            autoStartup = "${app.ingestion.worker-enabled:true}"
    )
    public void consume(Map<String, Object> payload) {
        String jobId = payload == null ? "" : asString(payload.get("jobId"));
        String traceId = payload == null ? "" : asString(payload.get("traceId"));
        if (!StringUtils.hasText(jobId)) {
            log.warn("Skip rabbit ingestion message without jobId: {}", payload);
            return;
        }
        IngestionProcessResult result = ingestionService.processQueuedJob(jobId, traceId);
        if (result.getStatus() != null) {
            log.debug("Rabbit ingestion processed. backend={}, jobId={}, status={}",
                    ingestionProperties.getQueueBackend(), jobId, result.getStatus());
        }
    }

    private String asString(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
