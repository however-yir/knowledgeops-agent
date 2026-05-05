package com.enterprise.iqk.retrieval;

import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Default no-op reranker that passes through documents unchanged.
 * Used when no LLM reranker is configured or available.
 */
@Component
public class IdentityReranker implements Reranker {

    @Override
    public List<ScoredDocument> rerank(String query, List<ScoredDocument> documents, int topK) {
        return documents.stream().limit(topK).toList();
    }

    @Override
    public String getName() {
        return "identity";
    }
}
