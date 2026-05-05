package com.enterprise.iqk.retrieval;

import java.util.List;

/**
 * Pluggable reranker interface for retrieval result re-scoring.
 * Implementations can use LLM-as-reranker, cross-encoder, or rule-based scoring.
 */
public interface Reranker {

    /**
     * Rerank and filter the given documents based on relevance to the query.
     *
     * @param query     the user query
     * @param documents the initial retrieval results
     * @param topK      maximum number of results to return
     * @return reranked documents (potentially filtered and re-scored)
     */
    List<ScoredDocument> rerank(String query, List<ScoredDocument> documents, int topK);

    /**
     * Human-readable name for this reranker strategy.
     */
    String getName();
}
