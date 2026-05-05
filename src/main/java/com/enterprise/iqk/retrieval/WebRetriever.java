package com.enterprise.iqk.retrieval;

import com.enterprise.iqk.retrieval.web.WebSearchBackend;
import com.enterprise.iqk.retrieval.web.WebSearchProperties;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * Web search retriever that delegates to a configured search backend (SearXNG or Bing API).
 * <p>
 * Web search is disabled by default. To enable it:
 * <ol>
 *   <li>Set {@code app.web-search.enabled=true}</li>
 *   <li>Configure a search backend:
 *     <ul>
 *       <li>SearXNG: set {@code app.web-search.searxng-url} to your SearXNG instance</li>
 *       <li>Bing: set {@code app.web-search.bing-api-key} and optionally {@code app.web-search.bing-endpoint}</li>
 *     </ul>
 *   </li>
 * </ol>
 * If no backend is configured or enabled, this retriever returns an empty list with a log warning.
 */
@Slf4j
@Component
public class WebRetriever {

    private final List<WebSearchBackend> backends;
    private final WebSearchProperties webSearchProperties;
    private final MeterRegistry meterRegistry;

    public WebRetriever(List<WebSearchBackend> backends,
                        WebSearchProperties webSearchProperties,
                        MeterRegistry meterRegistry) {
        this.backends = backends;
        this.webSearchProperties = webSearchProperties;
        this.meterRegistry = meterRegistry;
    }

    public List<ScoredDocument> retrieve(String query, int topK) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "disabled";
        try {
            if (!webSearchProperties.isEnabled()) {
                log.debug("Web search is disabled (app.web-search.enabled=false). Skipping web retrieval.");
                return Collections.emptyList();
            }

            // Find the first available backend
            WebSearchBackend activeBackend = backends.stream()
                    .filter(WebSearchBackend::isAvailable)
                    .findFirst()
                    .orElse(null);

            if (activeBackend == null) {
                log.warn("Web search is enabled but no search backend is configured. " +
                        "Set app.web-search.searxng-url or app.web-search.bing-api-key to enable web retrieval.");
                outcome = "no-backend";
                return Collections.emptyList();
            }

            var results = activeBackend.search(query, topK);
            if (results.isEmpty()) {
                outcome = "empty";
                return Collections.emptyList();
            }

            List<ScoredDocument> docs = results.stream()
                    .map(r -> ScoredDocument.builder()
                            .docId("web-" + UUID.randomUUID().toString().substring(0, 8))
                            .sourceType("web")
                            .title(r.getTitle())
                            .url(r.getUrl())
                            .content(r.getSnippet())
                            .retrievalScore(r.getScore())
                            .finalScore(r.getScore())
                            .build())
                    .toList();

            outcome = "success";
            log.debug("Web retrieval returned {} results for query '{}'", docs.size(), query);
            return docs;
        } finally {
            sample.stop(Timer.builder("retrieval.web.latency")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(meterRegistry));
        }
    }
}
