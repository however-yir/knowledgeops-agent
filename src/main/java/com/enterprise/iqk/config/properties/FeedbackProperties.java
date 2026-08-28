package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "app.feedback")
public class FeedbackProperties {
    private boolean enabled = true;
    private String datasetPath = "evaluation/feedback_dataset.jsonl";
    // Cap the on-disk dataset so a single tenant (or a tenant with a leaked
    // credential) cannot exhaust the disk by repeatedly submitting feedback.
    // When the file is at or above this size, the writer rotates to a
    // timestamped sibling instead of appending further.
    private long maxDatasetBytes = 50L * 1024L * 1024L; // 50 MiB
}
