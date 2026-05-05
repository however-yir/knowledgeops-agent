package com.enterprise.iqk.retrieval.web;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * SearXNG self-hosted search backend.
 * <p>
 * Requires a running SearXNG instance with JSON format enabled.
 * Docker quick-start:
 * <pre>
 * docker run -d --name searxng -p 8888:8080 \
 *   -e SEARXNG_BASE_URL=http://localhost:8888/ \
 *   searxng/searxng:latest
 * </pre>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SearXNGBackend implements WebSearchBackend {

    private final WebSearchProperties properties;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private RestTemplate restTemplate;

    private RestTemplate getRestTemplate() {
        if (restTemplate == null) {
            restTemplate = new RestTemplate();
        }
        return restTemplate;
    }

    @Override
    public List<WebSearchResult> search(String query, int maxResults) {
        if (!isAvailable()) {
            return Collections.emptyList();
        }
        try {
            String url = properties.getSearxngUrl() + "/search?q={query}&format=json&categories=general&pageno=1";
            Map<String, String> uriVars = Map.of("query", query);

            ResponseEntity<String> response = getRestTemplate().getForEntity(url, String.class, uriVars);
            if (response.getBody() == null) {
                return Collections.emptyList();
            }

            Map<String, Object> body = objectMapper.readValue(response.getBody(), new TypeReference<>() {});
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> results = (List<Map<String, Object>>) body.getOrDefault("results", Collections.emptyList());

            List<WebSearchResult> searchResults = new ArrayList<>();
            for (int i = 0; i < Math.min(results.size(), maxResults); i++) {
                Map<String, Object> r = results.get(i);
                searchResults.add(WebSearchResult.builder()
                        .title((String) r.getOrDefault("title", ""))
                        .url((String) r.getOrDefault("url", ""))
                        .snippet((String) r.getOrDefault("content", ""))
                        .score(1.0 - (i * 0.1)) // rank-based scoring
                        .build());
            }
            return searchResults;
        } catch (Exception e) {
            log.error("SearXNG search failed for query '{}': {}", query, e.getMessage());
            return Collections.emptyList();
        }
    }

    @Override
    public boolean isAvailable() {
        return "searxng".equalsIgnoreCase(properties.getBackend())
                && properties.getSearxngUrl() != null
                && !properties.getSearxngUrl().isBlank();
    }
}
