package com.enterprise.iqk.retrieval;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CitationItem {
    private int index;           // citation number in answer, e.g. [1]
    private String sourceType;
    private String title;
    private String url;
    private String chunkId;
    private double confidence;   // 0-1
    private String excerpt;      // quoted text from source

    public int getId() {
        return index;
    }

    public String getSource() {
        return sourceType;
    }

    public String getSnippet() {
        return excerpt;
    }
}
