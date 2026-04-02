package com.demo.ai.ingestion;

import com.demo.ai.config.properties.IngestionProperties;
import com.demo.ai.ingestion.queue.IngestionQueue;
import com.demo.ai.ingestion.queue.IngestionQueueMessage;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

@Slf4j
@Component
@RequiredArgsConstructor
public class IngestionWorker {

    private final IngestionService ingestionService;
    private final IngestionProperties ingestionProperties;
    private final IngestionQueue ingestionQueue;
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

    @PreDestroy
    public void shutdown() {
        running.set(false);
        if (workerPool != null) {
            workerPool.shutdownNow();
        }
    }
}
