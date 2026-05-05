package com.enterprise.iqk.retrieval.web;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Configuration for external web search backend (SearXNG or Bing API).
 * Web search is disabled by default; a search backend must be explicitly configured.
 */
@Data
@Component
@ConfigurationProperties(prefix = "app.web-search")
public class WebSearchProperties {

    /**
     * Whether web search is enabled. Defaults to false.
     * Must be explicitly set to true AND a backend URL configured for web retrieval to work.
     */
    private boolean enabled = false;

    /**
     * Backend type: "searxng" (default) or "bing".
     */
    private String backend = "searxng";

    /**
     * SearXNG instance base URL (e.g., http://localhost:8888).
     */
    private String searxngUrl = "";

    /**
     * Bing Search API v7 subscription key.
     */
    private String bingApiKey = "";

    /**
     * Bing Search API v7 endpoint (e.g., https://api.bing.microsoft.com/v7.0).
     */
    private String bingEndpoint = "https://api.bing.microsoft.com/v7.0";

    /**
     * Connection timeout in milliseconds.
     */
    private int connectTimeoutMs = 3000;

    /**
     * Read timeout in milliseconds.
     */
    private int readTimeoutMs = 8000;

    /**
     * Maximum number of search results to request from the backend.
     */
    private int maxResults = 5;
}
