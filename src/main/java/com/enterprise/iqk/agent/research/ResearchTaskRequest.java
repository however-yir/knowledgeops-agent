package com.enterprise.iqk.agent.research;

import lombok.Data;

@Data
public class ResearchTaskRequest {
    private String topic;
    private String modelProfile;
    private int maxSearchRounds = 3;
    /**
     * Whether to enable web search in the research workflow.
     * Defaults to false — requires a configured search backend (SearXNG or Bing API)
     * and explicit opt-in via app.web-search.enabled=true.
     */
    private boolean enableWebSearch = false;
    private boolean enableRagSearch = true;
    private boolean enableGraphSearch = true;
}
