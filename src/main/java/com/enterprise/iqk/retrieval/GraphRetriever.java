package com.enterprise.iqk.retrieval;

import com.enterprise.iqk.graph.GraphService;
import com.enterprise.iqk.graph.KgEntityRecord;
import com.enterprise.iqk.graph.KgFactRecord;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
@RequiredArgsConstructor
public class GraphRetriever {

    private final GraphService graphService;
    private final MeterRegistry meterRegistry;

    public List<ScoredDocument> retrieve(String query, String tenantId, int topK) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "error";
        try {
            List<ScoredDocument> results = new ArrayList<>();

            // Extract keywords from query for entity matching
            String keyword = extractMainKeyword(query);
            if (!StringUtils.hasText(keyword)) {
                outcome = "empty";
                return results;
            }

            // Search entities by keyword
            List<KgEntityRecord> entities = graphService.searchEntities(tenantId, keyword, topK);
            for (int i = 0; i < entities.size(); i++) {
                KgEntityRecord e = entities.get(i);
                // Get one-hop neighbors for richer context
                List<GraphService.GraphNeighbor> neighbors = graphService.getNeighbors(tenantId, e.getEntityId());
                String neighborContext = buildNeighborContext(neighbors);

                results.add(ScoredDocument.builder()
                        .docId("graph-entity-" + i)
                        .sourceType("graph")
                        .title(e.getName() + " (" + e.getType() + ")")
                        .chunkId(e.getEntityId())
                        .content(e.getName() + ": " + defaultText(e.getDescription(), "")
                                + (StringUtils.hasText(neighborContext) ? " | " + neighborContext : ""))
                        .retrievalScore(0.85)
                        .metadata(Map.of("entityType", e.getType(), "entityId", e.getEntityId()))
                        .build());
            }

            // Search facts by keyword
            List<KgFactRecord> facts = graphService.searchFacts(tenantId, keyword, topK);
            for (int i = 0; i < facts.size(); i++) {
                KgFactRecord f = facts.get(i);
                results.add(ScoredDocument.builder()
                        .docId("graph-fact-" + i)
                        .sourceType("graph")
                        .title(f.getSubject() + " " + f.getPredicate() + " " + f.getObject())
                        .chunkId(f.getFactId())
                        .content(f.getSubject() + " " + f.getPredicate() + " " + f.getObject())
                        .retrievalScore(f.getConfidence() != null ? f.getConfidence() : 0.7)
                        .metadata(Map.of("factId", f.getFactId()))
                        .build());
            }

            outcome = results.isEmpty() ? "empty" : "success";
            return results;
        } finally {
            sample.stop(Timer.builder("retrieval.graph.latency")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(meterRegistry));
        }
    }

    private String extractMainKeyword(String query) {
        if (!StringUtils.hasText(query)) return "";
        // Simple: take the longest token as keyword
        String longest = "";
        for (String token : query.split("[^\\p{L}\\p{Nd}]+")) {
            if (token.length() > longest.length()) {
                longest = token;
            }
        }
        return longest.length() >= 2 ? longest : query.trim();
    }

    private String buildNeighborContext(List<GraphService.GraphNeighbor> neighbors) {
        if (neighbors == null || neighbors.isEmpty()) return "";
        StringBuilder sb = new StringBuilder();
        for (GraphService.GraphNeighbor n : neighbors) {
            if (sb.length() > 0) sb.append("; ");
            sb.append(n.getRelationType()).append(" → ").append(n.getEntity().getName());
        }
        return sb.toString();
    }

    private String defaultText(String value, String fallback) {
        return StringUtils.hasText(value) ? value : fallback;
    }
}
