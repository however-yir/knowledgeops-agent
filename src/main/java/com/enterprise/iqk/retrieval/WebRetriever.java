package com.enterprise.iqk.retrieval;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.List;

/**
 * Placeholder for external web search retrieval.
 * Will be wired to a real search API (e.g., Bing/SearXNG) in DeepResearch module (Task #5).
 */
@Component
@RequiredArgsConstructor
public class WebRetriever {

    private final MeterRegistry meterRegistry;

    public List<ScoredDocument> retrieve(String query, int topK) {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            // TODO: Wire to external search API in DeepResearch module
            return Collections.emptyList();
        } finally {
            sample.stop(Timer.builder("retrieval.web.latency")
                    .tag("outcome", "empty")
                    .publishPercentileHistogram()
                    .register(meterRegistry));
        }
    }
}
