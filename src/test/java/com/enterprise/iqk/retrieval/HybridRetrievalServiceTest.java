package com.enterprise.iqk.retrieval;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
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
