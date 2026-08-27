package com.enterprise.iqk.ingestion.queue;

import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.ingestion.IngestionProcessResult;
import com.enterprise.iqk.ingestion.IngestionService;
import com.enterprise.iqk.mapper.IngestionJobMapper;
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
    private final IngestionJobMapper ingestionJobMapper;

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
        // Read tenant from the job itself; threads here have no MDC and the SQL
        // now requires the owning tenant to claim the row.
        IngestionJob job = ingestionJobMapper.findByJobId(jobId);
        String ownerTenant = job == null ? null : job.getTenantId();
        IngestionProcessResult result = ingestionService.processQueuedJob(jobId, ownerTenant, traceId);
        if (result.getStatus() != null) {
            log.debug("Rabbit ingestion processed. backend={}, jobId={}, status={}",
                    ingestionProperties.getQueueBackend(), jobId, result.getStatus());
        }
    }

    private String asString(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
