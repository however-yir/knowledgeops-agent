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
import java.util.concurrent.TimeUnit;

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
            String filter = "tenant_id == '" + sanitize(tenantId) + "' && chat_id == '" + sanitize(chatId) + "'";
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
                double score = 1.0 - (i * 0.05); // approximate; real score from metadata if available
                results.add(ScoredDocument.builder()
                        .docId("vec-" + i)
                        .sourceType("vector")
                        .title(metaStr(d, "file_name", "unknown"))
                        .chunkId("chunk-" + metaStr(d, "chunk_index", String.valueOf(i)))
                        .content(d.getFormattedContent())
                        .retrievalScore(Math.max(0.1, score))
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

    private String sanitize(String v) {
        return (v == null ? "" : v).replace("'", "");
    }
}
