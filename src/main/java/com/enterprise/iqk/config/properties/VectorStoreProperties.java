package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "app.vector-store")
public class VectorStoreProperties {
    private String backend = "pgvector";
    private boolean requirePgvector = true;
    private String simpleStorePath = "./data/vector-store/chat-pdf.json";
    private Pgvector pgvector = new Pgvector();

    @Data
    public static class Pgvector {
        private String url;
        private String username;
        private String password;
        private String schema = "public";
        private int dimensions = 1024;
        private String table = "ai_knowledge_chunks";
    }
}
