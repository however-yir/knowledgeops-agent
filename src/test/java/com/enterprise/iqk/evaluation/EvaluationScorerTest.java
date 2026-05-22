package com.enterprise.iqk.evaluation;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class EvaluationScorerTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final EvaluationScorer scorer = new EvaluationScorer(objectMapper);

    @Test
    void shouldScoreCitationAndKeywordCoverage() throws Exception {
        EvalCaseRecord evalCase = EvalCaseRecord.builder()
                .expectedKeywordsJson(objectMapper.writeValueAsString(List.of("高温", "风险")))
                .expectedCitationsJson(objectMapper.writeValueAsString(List.of("heat-policy")))
                .forbiddenKeywordsJson(objectMapper.writeValueAsString(List.of("编造")))
                .build();

        EvaluationScorer.CaseScores scores = scorer.scoreCase(
                evalCase,
                "高温风险处置建议见引用 [1]",
                List.of("vector:heat-policy:chunk-1"),
                List.of("高温风险包括中暑、脱水与慢病加重。"),
                false
        );

        assertThat(scores.retrievalHit()).isEqualTo(1.0);
        assertThat(scores.citationCoverage()).isEqualTo(1.0);
        assertThat(scores.keywordScore()).isEqualTo(1.0);
        assertThat(scores.answerFaithfulness()).isEqualTo(1.0);
        assertThat(scores.score()).isEqualTo(1.0);
    }

    @Test
    void shouldPenalizeForbiddenKeywords() throws Exception {
        EvalCaseRecord evalCase = EvalCaseRecord.builder()
                .expectedKeywordsJson(objectMapper.writeValueAsString(List.of("高温")))
                .expectedCitationsJson(objectMapper.writeValueAsString(List.of()))
                .forbiddenKeywordsJson(objectMapper.writeValueAsString(List.of("编造")))
                .build();

        EvaluationScorer.CaseScores scores = scorer.scoreCase(
                evalCase,
                "这里编造一个高温结论。",
                List.of(),
                List.of(),
                false
        );

        assertThat(scores.keywordScore()).isEqualTo(0.0);
        assertThat(scores.answerFaithfulness()).isLessThanOrEqualTo(0.2);
        assertThat(scores.score()).isLessThan(0.70);
    }
}
