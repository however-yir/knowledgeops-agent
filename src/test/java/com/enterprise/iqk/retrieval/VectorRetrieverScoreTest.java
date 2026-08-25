package com.enterprise.iqk.retrieval;

import com.enterprise.iqk.config.properties.RagProperties;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class VectorRetrieverScoreTest {

    @Test
    void usesExplicitScoreFromMetadataWhenAvailable() {
        VectorStore vectorStore = mock(VectorStore.class);
        when(vectorStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(
                Document.builder()
                        .text("alpha")
                        .metadata("file_name", "a.txt")
                        .metadata("chunk_index", 0)
                        .metadata("score", 0.93)
                        .build()));
        VectorRetriever retriever = new VectorRetriever(vectorStore, new RagProperties(), new SimpleMeterRegistry());

        List<ScoredDocument> docs = retriever.retrieve("q", "tenant", "chat");

        assertThat(docs).singleElement().satisfies(d -> {
            assertThat(d.getRetrievalScore()).isEqualTo(0.93);
            assertThat(d.getSourceType()).isEqualTo("vector");
        });
    }

    @Test
    void convertsDistanceMetadataIntoScore() {
        VectorStore vectorStore = mock(VectorStore.class);
        when(vectorStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(
                Document.builder()
                        .text("beta")
                        .metadata("distance", 0.2)
                        .build()));
        VectorRetriever retriever = new VectorRetriever(vectorStore, new RagProperties(), new SimpleMeterRegistry());

        List<ScoredDocument> docs = retriever.retrieve("q", "tenant", "chat");

        assertThat(docs.get(0).getRetrievalScore()).isEqualTo(0.8);
    }

    @Test
    void fallsBackToRankBasedScoreWhenMetadataMissing() {
        VectorStore vectorStore = mock(VectorStore.class);
        when(vectorStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(
                Document.builder().text("a").metadata(Map.of()).build(),
                Document.builder().text("b").metadata(Map.of()).build()));
        VectorRetriever retriever = new VectorRetriever(vectorStore, new RagProperties(), new SimpleMeterRegistry());

        List<ScoredDocument> docs = retriever.retrieve("q", "tenant", "chat");

        // First doc still above the floor, second doc decays by 0.05.
        assertThat(docs.get(0).getRetrievalScore()).isBetween(0.99, 1.0);
        assertThat(docs.get(1).getRetrievalScore()).isBetween(0.9, 0.96);
    }
}
