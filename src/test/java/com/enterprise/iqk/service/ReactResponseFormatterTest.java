package com.enterprise.iqk.service;

import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.domain.vo.ReactTraceStepVO;
import com.enterprise.iqk.llm.ModelRouter;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class ReactResponseFormatterTest {
    private final ReactResponseFormatter formatter = new ReactResponseFormatter(new ObjectMapper());

    @Test
    void collectsUniqueEvidenceAndAppendsCitationFooter() {
        List<ReactTraceStepVO> trace = List.of(
                ReactTraceStepVO.builder().step(1).observation(Map.of(
                        "citations", List.of("doc-1", "doc-1"),
                        "evidence", List.of("first evidence")
                )).build(),
                ReactTraceStepVO.builder().step(2).observation(Map.of(
                        "citations", List.of("doc-2"),
                        "evidence", List.of("second evidence")
                )).build()
        );

        ReactChatResponseVO response = formatter.success("chat-1", "answer", trace, null, false);

        assertThat(response.getCitations()).containsExactly("doc-1", "doc-2");
        assertThat(response.getEvidence()).containsExactly("first evidence", "second evidence");
        assertThat(response.getFallback()).isFalse();
        assertThat(response.getAnswer()).contains("answer", "引用来源", "[1] doc-1", "[2] doc-2");
    }

    @Test
    void emitsWellFormedSseAndPreservesContextHistory() {
        String sse = formatter.formatSse("token", formatter.toJson(Map.of("token", "你好")));
        String context = formatter.appendContext("first", "rag_search", Map.of("count", 1));

        assertThat(sse).isEqualTo("event: token\ndata: {\"token\":\"你好\"}\n\n");
        assertThat(context).contains("first", "action=rag_search", "\"count\":1");
    }

    @Test
    void preservesRoutingForMissingOrSparseTraceData() {
        ModelRouter.ModelRouteDecision route = new ModelRouter.ModelRouteDecision(
                "quality", "model-a", "premium", false, "profile_match", "quality_vs_cost", "quality", 42
        );

        ReactChatResponseVO noTrace = formatter.success("chat-2", "已有引用来源", null, route, true);
        ReactChatResponseVO sparseTrace = formatter.success("chat-3", "answer", Arrays.asList(
                null,
                ReactTraceStepVO.builder().step(1).observation("not-a-map").build()
        ), route, false);

        assertThat(noTrace.getAnswer()).isEqualTo("已有引用来源");
        assertThat(noTrace.getCitations()).isEmpty();
        assertThat(noTrace.getFallback()).isTrue();
        assertThat(noTrace.getRouteProfile()).isEqualTo("quality");
        assertThat(noTrace.getRouteReason()).isEqualTo("profile_match");
        assertThat(noTrace.getRouteCostTier()).isEqualTo("premium");
        assertThat(noTrace.getExperimentKey()).isEqualTo("quality_vs_cost");
        assertThat(noTrace.getExperimentVariant()).isEqualTo("quality");
        assertThat(noTrace.getExperimentBucket()).isEqualTo(42);
        assertThat(sparseTrace.getCitations()).isEmpty();
        assertThat(sparseTrace.getEvidence()).isEmpty();
    }
}
