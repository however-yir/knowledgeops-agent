package com.enterprise.iqk.retrieval;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import java.util.stream.Stream;

@Slf4j
@Service
@RequiredArgsConstructor
public class HybridRetrievalService {

    private final VectorRetriever vectorRetriever;
    private final KeywordRetriever keywordRetriever;
    private final GraphRetriever graphRetriever;
    private final WebRetriever webRetriever;
    private final MeterRegistry meterRegistry;

    private static final double VECTOR_WEIGHT = 0.40;
    private static final double KEYWORD_WEIGHT = 0.25;
    private static final double GRAPH_WEIGHT = 0.20;
    private static final double WEB_WEIGHT = 0.15;
    private static final long SOURCE_TIMEOUT_SECONDS = 3;

    public HybridRetrievalResult retrieve(String query, String tenantId, String chatId, int topK) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "error";
        try {
            CompletableFuture<List<ScoredDocument>> vectorFuture = retrieveAsync("vector",
                    () -> vectorRetriever.retrieve(query, tenantId, chatId), VECTOR_WEIGHT);
            CompletableFuture<List<ScoredDocument>> keywordFuture = retrieveAsync("keyword",
                    () -> keywordRetriever.retrieve(query, tenantId, chatId, topK), KEYWORD_WEIGHT);
            CompletableFuture<List<ScoredDocument>> graphFuture = retrieveAsync("graph",
                    () -> graphRetriever.retrieve(query, tenantId, topK), GRAPH_WEIGHT);
            CompletableFuture<List<ScoredDocument>> webFuture = retrieveAsync("web",
                    () -> webRetriever.retrieve(query, topK), WEB_WEIGHT);

            List<ScoredDocument> allDocs = Stream.of(vectorFuture, keywordFuture, graphFuture, webFuture)
                    .flatMap(future -> future.join().stream())
                    .toList();

            // Deduplicate by content fingerprint
            List<ScoredDocument> deduped = deduplicate(allDocs);

            // Sort by weighted score descending
            deduped.sort(Comparator.comparingDouble(ScoredDocument::getFinalScore).reversed());

            List<ScoredDocument> top = deduped.stream().limit(topK).toList();

            outcome = top.isEmpty() ? "empty" : "success";
            return new HybridRetrievalResult(top, allDocs.size(), deduped.size());
        } finally {
            sample.stop(Timer.builder("retrieval.hybrid.latency")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(meterRegistry));
        }
    }

    private List<ScoredDocument> applyWeight(List<ScoredDocument> docs, double weight) {
        for (ScoredDocument d : docs) {
            d.setFinalScore(d.getRetrievalScore() * weight);
        }
        return docs;
    }

    private CompletableFuture<List<ScoredDocument>> retrieveAsync(String source,
                                                                  Supplier<List<ScoredDocument>> retrieval,
                                                                  double weight) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return applyWeight(retrieval.get(), weight);
            } catch (RuntimeException ex) {
                log.warn("hybrid retrieval source failed: source={}, reason={}", source, ex.toString());
                return List.<ScoredDocument>of();
            }
        }).completeOnTimeout(List.of(), SOURCE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
    }

    private List<ScoredDocument> deduplicate(List<ScoredDocument> docs) {
        Map<String, ScoredDocument> seen = new LinkedHashMap<>();
        for (ScoredDocument d : docs) {
            String fingerprint = fingerprint(d);
            ScoredDocument existing = seen.get(fingerprint);
            if (existing == null || d.getFinalScore() > existing.getFinalScore()) {
                seen.put(fingerprint, d);
            }
        }
        return new ArrayList<>(seen.values());
    }

    private String fingerprint(ScoredDocument d) {
        String content = d.getContent() != null ? d.getContent() : "";
        // Use first 200 chars as dedup key
        String normalized = content.replaceAll("\\s+", " ").trim();
        return normalized.length() <= 200 ? normalized : normalized.substring(0, 200);
    }

    public record HybridRetrievalResult(List<ScoredDocument> documents, int totalBeforeDedup,
                                         int totalAfterDedup) {}
}
