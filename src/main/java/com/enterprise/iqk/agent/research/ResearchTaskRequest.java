package com.enterprise.iqk.agent.research;

import lombok.Data;

@Data
public class ResearchTaskRequest {
    private String topic;
    private String modelProfile;
    private int maxSearchRounds = 3;
    private boolean enableWebSearch = true;
    private boolean enableRagSearch = true;
    private boolean enableGraphSearch = true;
}
