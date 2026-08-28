package com.enterprise.iqk.retrieval;

import com.enterprise.iqk.config.properties.RagProperties;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

@Component
@RequiredArgsConstructor
public class VectorRetriever {

    private final VectorStore vectorStore;
    private final RagProperties ragProperties;
    private final MeterRegistry meterRegistry;

    public List<ScoredDocument> retrieve(String query, String tenantId, String chatId) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "error";
        try {
            String filter = "tenant_id == \"" + escapeFilter(tenantId)
                    + "\" && chat_id == \"" + escapeFilter(chatId) + "\"";
            SearchRequest request = SearchRequest.builder()
                    .query(query)
                    .topK(ragProperties.getRetrieveTopK())
                    .similarityThreshold(ragProperties.getSimilarityThreshold())
                    .filterExpression(filter)
                    .build();
            List<Document> docs = vectorStore.similaritySearch(request);
            outcome = docs.isEmpty() ? "empty" : "success";
            List<ScoredDocument> results = new ArrayList<>();
            for (int i = 0; i < docs.size(); i++) {
                Document d = docs.get(i);
                results.add(ScoredDocument.builder()
                        .docId("vec-" + i)
                        .sourceType("vector")
                        .title(metaStr(d, "file_name", "unknown"))
                        .chunkId("chunk-" + metaStr(d, "chunk_index", String.valueOf(i)))
                        .content(d.getFormattedContent())
                        .retrievalScore(extractScore(d, i))
                        .metadata(d.getMetadata())
                        .build());
            }
            return results;
        } finally {
            sample.stop(Timer.builder("retrieval.vector.latency")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(meterRegistry));
        }
    }

    private String metaStr(Document d, String key, String fallback) {
        Object v = d.getMetadata().get(key);
        return v == null ? fallback : v.toString();
    }

    // Real retrieval scores live in Spring AI's standard metadata keys
    // (distance / score). Falling back to rank-based decay keeps the pipeline
    // functional for stores that do not populate them.
    private double extractScore(Document d, int rank) {
        Double explicit = readDouble(d.getMetadata(), "score");
        if (explicit != null) {
            return clamp01(explicit);
        }
        Double distance = readDouble(d.getMetadata(), "distance");
        if (distance != null) {
            return clamp01(1.0 - distance);
        }
        double fallback = 1.0 - (rank * 0.05);
        return Math.max(0.1, fallback);
    }

    private Double readDouble(java.util.Map<String, Object> metadata, String key) {
        if (metadata == null) {
            return null;
        }
        Object v = metadata.get(key);
        if (v instanceof Number n) {
            return n.doubleValue();
        }
        if (v instanceof String s) {
            try {
                return Double.parseDouble(s.trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private double clamp01(double value) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            return 0.0;
        }
        if (value < 0.0) return 0.0;
        if (value > 1.0) return 1.0;
        return value;
    }

    // Escape values for double-quoted filter expressions. The previous
    // implementation only stripped single quotes, so an input containing a
    // double quote (or backslash) could break out of the filter and inject
    // an unintended predicate.
    private String escapeFilter(String v) {
        if (v == null) return "";
        return v.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
