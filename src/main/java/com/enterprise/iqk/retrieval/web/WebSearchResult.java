package com.enterprise.iqk.retrieval.web;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * A single web search result from an external search backend.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class WebSearchResult {
    private String title;
    private String url;
    private String snippet;
    private double score;
}
