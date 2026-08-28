package com.enterprise.iqk.retrieval;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class HybridRetrievalServiceTest {

    @Test
    void degradesWhenOneRetrievalSourceFails() {
        VectorRetriever vectorRetriever = mock(VectorRetriever.class);
        KeywordRetriever keywordRetriever = mock(KeywordRetriever.class);
        GraphRetriever graphRetriever = mock(GraphRetriever.class);
        WebRetriever webRetriever = mock(WebRetriever.class);
        HybridRetrievalService service = new HybridRetrievalService(
                vectorRetriever,
                keywordRetriever,
                graphRetriever,
                webRetriever,
                new SimpleMeterRegistry()
        );

        when(vectorRetriever.retrieve("spring ai", "tenant", "chat")).thenThrow(new IllegalStateException("down"));
        when(keywordRetriever.retrieve("spring ai", "tenant", "chat", 3))
                .thenReturn(List.of(doc("kw-1", "keyword", "same content", 0.4)));
        when(graphRetriever.retrieve("spring ai", "tenant", 3))
                .thenReturn(List.of(doc("graph-1", "graph", "same content", 0.9)));
        when(webRetriever.retrieve("spring ai", 3)).thenReturn(List.of(doc("web-1", "web", "web content", 0.7)));

        HybridRetrievalService.HybridRetrievalResult result = service.retrieve("spring ai", "tenant", "chat", 3);

        assertThat(result.documents()).extracting(ScoredDocument::getDocId)
                .containsExactly("graph-1", "web-1");
        assertThat(result.totalBeforeDedup()).isEqualTo(3);
        assertThat(result.totalAfterDedup()).isEqualTo(2);
    }

    @Test
    void deduplicatesByContentFingerprintAndSortsByFinalScore() {
        VectorRetriever vectorRetriever = mock(VectorRetriever.class);
        KeywordRetriever keywordRetriever = mock(KeywordRetriever.class);
        GraphRetriever graphRetriever = mock(GraphRetriever.class);
        WebRetriever webRetriever = mock(WebRetriever.class);
        HybridRetrievalService service = new HybridRetrievalService(
                vectorRetriever,
                keywordRetriever,
                graphRetriever,
                webRetriever,
                new SimpleMeterRegistry()
        );

        when(vectorRetriever.retrieve("q", "tenant", "chat"))
                .thenReturn(List.of(doc("vec-1", "vector", "spring ai tutorial basics", 0.9)));
        when(keywordRetriever.retrieve(eq("q"), eq("tenant"), eq("chat"), eq(5)))
                .thenReturn(List.of(doc("kw-1", "keyword", "spring ai tutorial basics", 0.5),
                        doc("kw-2", "keyword", "another unique chunk", 0.4)));
        when(graphRetriever.retrieve(eq("q"), eq("tenant"), eq(5)))
                .thenReturn(List.of());
        when(webRetriever.retrieve(eq("q"), eq(5))).thenReturn(List.of());

        HybridRetrievalService.HybridRetrievalResult result = service.retrieve("q", "tenant", "chat", 5);

        // 3 raw docs, 2 unique fingerprints after dedup
        assertThat(result.totalBeforeDedup()).isEqualTo(3);
        assertThat(result.totalAfterDedup()).isEqualTo(2);
        // vector 0.9 * 0.40 = 0.36 wins over keyword 0.5 * 0.25 = 0.125 for the
        // shared content
        assertThat(result.documents()).extracting(ScoredDocument::getDocId)
                .containsExactly("vec-1", "kw-2");
        assertThat(result.documents().get(0).getFinalScore()).isGreaterThan(
                result.documents().get(1).getFinalScore());
    }

    @Test
    void allSourcesFailingReturnsEmptyResult() {
        VectorRetriever vectorRetriever = mock(VectorRetriever.class);
        KeywordRetriever keywordRetriever = mock(KeywordRetriever.class);
        GraphRetriever graphRetriever = mock(GraphRetriever.class);
        WebRetriever webRetriever = mock(WebRetriever.class);
        HybridRetrievalService service = new HybridRetrievalService(
                vectorRetriever,
                keywordRetriever,
                graphRetriever,
                webRetriever,
                new SimpleMeterRegistry()
        );

        when(vectorRetriever.retrieve("q", "tenant", "chat")).thenThrow(new RuntimeException("a"));
        when(keywordRetriever.retrieve(any(), any(), any(), anyInt())).thenThrow(new RuntimeException("b"));
        when(graphRetriever.retrieve(any(), any(), anyInt())).thenThrow(new RuntimeException("c"));
        when(webRetriever.retrieve(any(), anyInt())).thenThrow(new RuntimeException("d"));

        HybridRetrievalService.HybridRetrievalResult result = service.retrieve("q", "tenant", "chat", 3);

        assertThat(result.documents()).isEmpty();
        assertThat(result.totalBeforeDedup()).isZero();
        assertThat(result.totalAfterDedup()).isZero();
    }

    private ScoredDocument doc(String id, String sourceType, String content, double score) {
        return ScoredDocument.builder()
                .docId(id)
                .sourceType(sourceType)
                .title(id)
                .content(content)
                .retrievalScore(score)
                .metadata(Map.of())
                .build();
    }
}
