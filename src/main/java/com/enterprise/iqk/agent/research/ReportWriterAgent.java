package com.enterprise.iqk.agent.research;

import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.service.TenantCostService;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.stereotype.Component;

/**
 * Synthesizes research findings into a structured report.
 */
@Component
@RequiredArgsConstructor
public class ReportWriterAgent {

    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final TenantCostService tenantCostService;

    public String writeReport(String topic, String findings, String tenantId, String modelProfile) {
        String prompt = "Write a comprehensive research report based on the findings below.%nStructure: 1) Executive Summary 2) Key Findings 3) Detailed Analysis 4) Conclusions & Recommendations%n%nTopic: %s%n%nResearch Findings:%n%s%n".formatted(topic, findings);

        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(modelProfile, "research", tenantId, topic);
        long inputTokens = tenantCostService.estimateTokens(prompt);
        tenantCostService.assertBudget(tenantId, decision.costTier(), inputTokens, 2000);

        String report = chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build())
                .system("You are a research report writer. Produce well-structured, evidence-based reports in Chinese.")
                .user(prompt)
                .call()
                .content();

        long outputTokens = tenantCostService.estimateTokens(report);
        tenantCostService.recordUsage(tenantId, decision.costTier(), inputTokens, outputTokens, "research_writer");
        return report;
    }
}
