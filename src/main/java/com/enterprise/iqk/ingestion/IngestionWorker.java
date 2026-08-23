package com.enterprise.iqk.ingestion;

import com.enterprise.iqk.config.properties.IngestionProperties;
import com.enterprise.iqk.domain.IngestionJob;
import com.enterprise.iqk.ingestion.queue.IngestionQueue;
import com.enterprise.iqk.ingestion.queue.IngestionQueueMessage;
import com.enterprise.iqk.mapper.IngestionJobMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

@Slf4j
@Component
@RequiredArgsConstructor
public class IngestionWorker {

    private static final int DB_POLL_BATCH = 20;

    private final IngestionService ingestionService;
    private final IngestionProperties ingestionProperties;
    private final IngestionQueue ingestionQueue;
    private final IngestionJobMapper ingestionJobMapper;
    private final AtomicBoolean running = new AtomicBoolean(true);
    private ExecutorService workerPool;

    @PostConstruct
    public void start() {
        if (!ingestionProperties.isWorkerEnabled()) {
            return;
        }
        if (!"redis_stream".equalsIgnoreCase(ingestionProperties.getQueueBackend())) {
            return;
        }
        ingestionQueue.ensureConsumerGroup();
        int workers = Math.max(1, ingestionProperties.getWorkerCount());
        workerPool = Executors.newFixedThreadPool(workers);
        for (int i = 0; i < workers; i++) {
            final String consumerName = ingestionProperties.getRedis().getConsumerPrefix() + "-" + i + "-" + UUID.randomUUID();
            workerPool.submit(() -> loopConsume(consumerName));
        }
        log.info("Started redis stream ingestion workers: {}", workers);
    }

    private void loopConsume(String consumerName) {
        while (running.get()) {
            try {
                List<IngestionQueueMessage> records = ingestionQueue.readBatch(
                        consumerName,
                        ingestionProperties.getRedis().getReadBatchSize(),
                        Duration.ofMillis(Math.max(500, ingestionProperties.getPollIntervalMs()))
                );
                if (records.isEmpty()) {
                    // Reclaim messages left pending by crashed/slow workers so jobs do
                    // not stay RUNNING forever; guarded by app.ingestion.redis.claim-idle-ms.
                    records = ingestionQueue.claimIdle(
                            consumerName,
                            Duration.ofMillis(ingestionProperties.getRedis().getClaimIdleMs()),
                            ingestionProperties.getRedis().getReadBatchSize()
                    );
                }
                if (records.isEmpty()) {
                    continue;
                }
                for (IngestionQueueMessage msg : records) {
                    ingestionService.processQueuedJob(msg.getJobId(), msg.getTraceId());
                    ingestionQueue.ack(consumerName, msg.getRecordId());
                }
            } catch (Exception ex) {
                log.error("Redis ingestion worker failed for consumer {}", consumerName, ex);
            }
        }
    }

    @Scheduled(fixedDelayString = "${app.ingestion.poll-interval-ms:2000}")
    public void enqueueRetryJobs() {
        if (!ingestionProperties.isWorkerEnabled()) {
            return;
        }
        if ("db_polling".equalsIgnoreCase(ingestionProperties.getQueueBackend())) {
            return;
        }
        int enqueued = ingestionService.enqueueReadyRetries(50);
        if (enqueued > 0) {
            log.info("Re-enqueued retry jobs: {}", enqueued);
        }
    }

    /**
     * Consumer for the db_polling backend: without it, submitted jobs would stay
     * PENDING forever unless an admin manually called POST /ingestion/jobs/process.
     */
    @Scheduled(fixedDelayString = "${app.ingestion.poll-interval-ms:2000}")
    public void pollDatabaseJobs() {
        if (!ingestionProperties.isWorkerEnabled()) {
            return;
        }
        if (!"db_polling".equalsIgnoreCase(ingestionProperties.getQueueBackend())) {
            return;
        }
        int processed = 0;
        while (processed < DB_POLL_BATCH) {
            IngestionJob job = ingestionJobMapper.findNextReadyJob(LocalDateTime.now());
            if (job == null) {
                break;
            }
            try {
                if (!ingestionService.processQueuedJob(job.getJobId(), job.getTraceId()).isPicked()) {
                    break;
                }
            } catch (Exception ex) {
                log.error("db_polling ingestion failed for job {}", job.getJobId(), ex);
                break;
            }
            processed++;
        }
        if (processed > 0) {
            log.info("Processed db_polling ingestion jobs: {}", processed);
        }
    }

    @PreDestroy
    public void shutdown() {
        running.set(false);
        if (workerPool != null) {
            workerPool.shutdownNow();
        }
    }
}
