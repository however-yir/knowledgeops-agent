package com.enterprise.iqk.retrieval;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ScoredDocument {
    private String docId;
    private String sourceType;   // vector | keyword | graph | web
    private String title;
    private String url;
    private String chunkId;
    private String content;
    private double retrievalScore; // raw score from retriever (0-1)
    private double finalScore;     // after fusion + evidence judging (0-1)
    private Map<String, Object> metadata;
}
