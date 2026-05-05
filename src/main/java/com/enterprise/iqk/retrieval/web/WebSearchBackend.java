package com.enterprise.iqk.retrieval.web;

import java.util.List;

/**
 * Abstraction for web search backends (SearXNG, Bing, etc.).
 */
public interface WebSearchBackend {

    /**
     * Search the web for the given query and return results.
     *
     * @param query      the search query
     * @param maxResults maximum number of results to return
     * @return list of search results, never null
     */
    List<WebSearchResult> search(String query, int maxResults);

    /**
     * Check if this backend is configured and available.
     */
    boolean isAvailable();
}
