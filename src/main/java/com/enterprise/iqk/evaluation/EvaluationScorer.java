package com.enterprise.iqk.evaluation;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Locale;

@Component
@RequiredArgsConstructor
public class EvaluationScorer {
    private final ObjectMapper objectMapper;

    public CaseScores scoreCase(EvalCaseRecord evalCase,
                                String answer,
                                List<String> citations,
                                List<String> evidence,
                                boolean failed) {
        List<String> expectedKeywords = readJsonList(evalCase.getExpectedKeywordsJson());
        List<String> expectedCitations = readJsonList(evalCase.getExpectedCitationsJson());
        List<String> forbiddenKeywords = readJsonList(evalCase.getForbiddenKeywordsJson());
        String answerPool = (emptyIfBlank(answer) + "\n" + String.join("\n", evidence)).toLowerCase(Locale.ROOT);
        String citationPool = String.join("\n", citations).toLowerCase(Locale.ROOT);

        double keywordScore = expectedKeywords.isEmpty()
                ? (StringUtils.hasText(answer) ? 1.0 : 0.0)
                : hitRate(expectedKeywords, answerPool);
        double citationCoverage = expectedCitations.isEmpty()
                ? 1.0
                : hitRate(expectedCitations, citationPool);
        boolean forbiddenHit = forbiddenKeywords.stream()
                .filter(StringUtils::hasText)
                .anyMatch(keyword -> answerPool.contains(keyword.toLowerCase(Locale.ROOT)));
        double retrievalHit = expectedCitations.isEmpty()
                ? (!citations.isEmpty() || !evidence.isEmpty() || keywordScore > 0 ? 1.0 : 0.0)
                : (citationCoverage > 0 ? 1.0 : 0.0);
        double faithfulness = failed ? 0.0 : scoreFaithfulness(answer, citations);
        if (forbiddenHit) {
            keywordScore = 0.0;
            faithfulness = Math.min(faithfulness, 0.2);
        }

        double score = round(0.30 * retrievalHit
                + 0.25 * citationCoverage
                + 0.25 * keywordScore
                + 0.20 * faithfulness);
        return new CaseScores(round(retrievalHit), round(citationCoverage), round(keywordScore), round(faithfulness), score);
    }

    private double hitRate(List<String> expected, String actualLower) {
        if (expected == null || expected.isEmpty()) {
            return 1.0;
        }
        long hits = expected.stream()
                .filter(StringUtils::hasText)
                .filter(item -> actualLower.contains(item.toLowerCase(Locale.ROOT)))
                .count();
        return round(hits / (double) expected.size());
    }

    private double scoreFaithfulness(String answer, List<String> citations) {
        if (!StringUtils.hasText(answer)) {
            return 0.0;
        }
        if (citations == null || citations.isEmpty()) {
            return 0.5;
        }
        int markers = 0;
        for (int i = 1; i <= citations.size(); i++) {
            if (answer.contains("[" + i + "]")) {
                markers++;
            }
        }
        return round(Math.min(1.0, markers / (double) citations.size()));
    }

    private List<String> readJsonList(String json) {
        if (!StringUtils.hasText(json)) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {
            });
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private double round(double value) {
        return Math.round(value * 10000.0) / 10000.0;
    }

    private String emptyIfBlank(String value) {
        return StringUtils.hasText(value) ? value : "";
    }

    public record CaseScores(double retrievalHit,
                             double citationCoverage,
                             double keywordScore,
                             double answerFaithfulness,
                             double score) {
    }
}
