package com.enterprise.iqk.retrieval.web;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Bing Search API v7 backend.
 * <p>
 * Requires a Bing Search API subscription key from Azure.
 */
@Slf4j
@Component
public class BingSearchBackend implements WebSearchBackend {

    private final WebSearchProperties properties;
    private final ObjectMapper objectMapper;
    // volatile + double-checked initialization: concurrent first-callers
    // would otherwise see partially constructed factories with mismatched
    // timeouts, or one of the two RestTemplate instances would be silently
    // dropped while both threads raced through the `if (restTemplate == null)`
    // branch.
    private volatile RestTemplate restTemplate;

    public BingSearchBackend(WebSearchProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    private RestTemplate getRestTemplate() {
        RestTemplate local = restTemplate;
        if (local == null) {
            synchronized (this) {
                local = restTemplate;
                if (local == null) {
                    SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
                    factory.setConnectTimeout(properties.getConnectTimeoutMs());
                    factory.setReadTimeout(properties.getReadTimeoutMs());
                    local = new RestTemplate(factory);
                    restTemplate = local;
                }
            }
        }
        return local;
    }

    @Override
    public List<WebSearchResult> search(String query, int maxResults) {
        if (!isAvailable()) {
            return Collections.emptyList();
        }
        try {
            String url = properties.getBingEndpoint() + "/search?q={query}&count={count}&responseFilter=Webpages";
            Map<String, String> uriVars = Map.of("query", query, "count", String.valueOf(maxResults));

            HttpHeaders headers = new HttpHeaders();
            headers.set("Ocp-Apim-Subscription-Key", properties.getBingApiKey());

            ResponseEntity<String> response = getRestTemplate().exchange(
                    url, HttpMethod.GET, new HttpEntity<>(headers), String.class, uriVars);
            if (response.getBody() == null) {
                return Collections.emptyList();
            }

            Map<String, Object> body = objectMapper.readValue(response.getBody(), new TypeReference<>() {});
            @SuppressWarnings("unchecked")
            Map<String, Object> webPages = (Map<String, Object>) body.getOrDefault("webPages", Map.of());
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> values = (List<Map<String, Object>>) webPages.getOrDefault("value", Collections.emptyList());

            List<WebSearchResult> searchResults = new ArrayList<>();
            for (int i = 0; i < Math.min(values.size(), maxResults); i++) {
                Map<String, Object> r = values.get(i);
                searchResults.add(WebSearchResult.builder()
                        .title((String) r.getOrDefault("name", ""))
                        .url((String) r.getOrDefault("url", ""))
                        .snippet((String) r.getOrDefault("snippet", ""))
                        .score(1.0 - (i * 0.1))
                        .build());
            }
            return searchResults;
        } catch (Exception e) {
            log.error("Bing search failed for query '{}': {}", query, e.getMessage());
            return Collections.emptyList();
        }
    }

    @Override
    public boolean isAvailable() {
        return "bing".equalsIgnoreCase(properties.getBackend())
                && properties.getBingApiKey() != null
                && !properties.getBingApiKey().isBlank();
    }
}

