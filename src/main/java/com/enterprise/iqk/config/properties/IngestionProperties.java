package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "app.ingestion")
public class IngestionProperties {
    private String queueBackend = "redis_stream";
    private boolean workerEnabled = true;
    private long pollIntervalMs = 2000;
    private int maxRetries = 3;
    private int baseDelaySeconds = 10;
    private String storageDir = "./data/uploads";
    private int workerCount = 3;
    private Redis redis = new Redis();
    private Rabbit rabbit = new Rabbit();

    @Data
    public static class Redis {
        private String streamKey = "ingestion:jobs";
        private String dlqStreamKey = "ingestion:dlq";
        private String consumerGroup = "ingestion_group";
        private String consumerPrefix = "worker";
        private int readBatchSize = 10;
        private long claimIdleMs = 30000;
    }

    @Data
    public static class Rabbit {
        private String exchange = "ingestion.exchange";
        private String routingKey = "ingestion.jobs";
        private String queue = "ingestion.jobs.queue";
        private String dlqExchange = "ingestion.dlx";
        private String dlqRoutingKey = "ingestion.jobs.dlq";
        private String dlqQueue = "ingestion.jobs.dlq.queue";
    }
}
