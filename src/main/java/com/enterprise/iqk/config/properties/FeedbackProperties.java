package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "app.feedback")
public class FeedbackProperties {
    private boolean enabled = true;
    private String datasetPath = "evaluation/feedback_dataset.jsonl";
}
