package com.enterprise.iqk.retrieval;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EvidenceItem {
    private String sourceType;   // vector | keyword | graph | web
    private String title;
    private String url;
    private String chunkId;
    private double score;        // 0-1 composite score
    private String reason;       // human-readable reason for the score
    private double relevanceScore;
    private double authorityScore;
    private double timelinessScore;
    private String snippet;      // short preview text
}
