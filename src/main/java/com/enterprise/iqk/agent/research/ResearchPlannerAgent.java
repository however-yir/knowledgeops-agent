package com.enterprise.iqk.agent.research;

import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.service.TenantCostService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;

/**
 * Decomposes a research topic into sub-questions for parallel or sequential investigation.
 */
@Component
@RequiredArgsConstructor
public class ResearchPlannerAgent {

    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final TenantCostService tenantCostService;
    private final ObjectMapper objectMapper;

    public ResearchPlan plan(String topic, String tenantId, String modelProfile) {
        String prompt = "Decompose the following research topic into 3-5 sub-questions.%nReturn JSON only:%n{%n  \"subQuestions\": [\"q1\", \"q2\", ...],%n  \"keywords\": [\"kw1\", \"kw2\", ...],%n  \"strategy\": \"breadth_first\"%n}%n%nTopic: %s%n".formatted(topic);

        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(modelProfile, "research", tenantId, topic);
        long inputTokens = tenantCostService.estimateTokens(prompt);
        tenantCostService.assertBudget(tenantId, decision.costTier(), inputTokens, 600);

        String raw = chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build())
                .system("You are a research planner. Decompose complex topics into sub-questions. Return JSON only.")
                .user(prompt)
                .call()
                .content();

        long outputTokens = tenantCostService.estimateTokens(raw);
        tenantCostService.recordUsage(tenantId, decision.costTier(), inputTokens, outputTokens, "research_planner");

        try {
            String json = extractJson(raw);
            Map<String, Object> parsed = objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
            @SuppressWarnings("unchecked")
            List<String> subQuestions = (List<String>) parsed.getOrDefault("subQuestions", List.of());
            @SuppressWarnings("unchecked")
            List<String> keywords = (List<String>) parsed.getOrDefault("keywords", List.of());
            String strategy = (String) parsed.getOrDefault("strategy", "breadth_first");
            return new ResearchPlan(subQuestions, keywords, strategy);
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            return new ResearchPlan(List.of(topic), List.of(), "direct");
        }
    }

    private String extractJson(String raw) {
        if (!StringUtils.hasText(raw)) return "{}";
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        return (start < 0 || end <= start) ? "{}" : raw.substring(start, end + 1);
    }

    public record ResearchPlan(List<String> subQuestions, List<String> keywords, String strategy) {}
}
