package com.demo.ai.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "rag")
public class RagProperties {
    private int retrieveTopK = 12;
    private int rerankTopK = 6;
    private double similarityThreshold = 0.45;
    private Split split = new Split();

    @Data
    public static class Split {
        private int chunkSize = 800;
        private int minChunkSize = 120;
        private int maxNumChunks = 100;
    }
}
