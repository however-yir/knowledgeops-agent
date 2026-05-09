package com.enterprise.iqk.retrieval;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IdentityRerankerTest {

    private final IdentityReranker reranker = new IdentityReranker();

    @Test
    void shouldReturnTopKResults() {
        List<ScoredDocument> docs = List.of(
                ScoredDocument.builder().docId("d1").retrievalScore(0.9).build(),
                ScoredDocument.builder().docId("d2").retrievalScore(0.8).build(),
                ScoredDocument.builder().docId("d3").retrievalScore(0.7).build()
        );

        List<ScoredDocument> result = reranker.rerank("query", docs, 2);

        assertEquals(2, result.size());
        assertEquals("d1", result.get(0).getDocId());
        assertEquals("d2", result.get(1).getDocId());
    }

    @Test
    void shouldReturnEmptyForEmptyInput() {
        List<ScoredDocument> result = reranker.rerank("query", List.of(), 5);

        assertTrue(result.isEmpty());
    }

    @Test
    void shouldReturnEmptyForTopKZero() {
        List<ScoredDocument> docs = List.of(
                ScoredDocument.builder().docId("d1").retrievalScore(0.9).build()
        );

        List<ScoredDocument> result = reranker.rerank("query", docs, 0);

        assertTrue(result.isEmpty());
    }

    @Test
    void shouldReturnAllWhenTopKExceedsSize() {
        List<ScoredDocument> docs = List.of(
                ScoredDocument.builder().docId("d1").retrievalScore(0.9).build(),
                ScoredDocument.builder().docId("d2").retrievalScore(0.8).build()
        );

        List<ScoredDocument> result = reranker.rerank("query", docs, 10);

        assertEquals(2, result.size());
        assertEquals("d1", result.get(0).getDocId());
        assertEquals("d2", result.get(1).getDocId());
    }

    @Test
    void shouldReturnIdentityName() {
        assertEquals("identity", reranker.getName());
    }
}
