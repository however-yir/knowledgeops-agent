package com.enterprise.iqk.rag;

import com.enterprise.iqk.config.properties.RagProperties;
import com.enterprise.iqk.constants.SystemConstants;
import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.retrieval.CitationItem;
import com.enterprise.iqk.retrieval.CitationService;
import com.enterprise.iqk.retrieval.EvidenceItem;
import com.enterprise.iqk.retrieval.EvidenceJudgeService;
import com.enterprise.iqk.retrieval.HybridRetrievalService;
import com.enterprise.iqk.retrieval.ScoredDocument;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.TenantCostService;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.Builder;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.UUID;

import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY;

@Slf4j
@Service
@RequiredArgsConstructor
public class HybridRagAnswerService {

    private final HybridRetrievalService hybridRetrievalService;
    private final EvidenceJudgeService evidenceJudgeService;
    private final CitationService citationService;
    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final RagProperties ragProperties;
    private final MeterRegistry meterRegistry;
    private final TenantCostService tenantCostService;

    public HybridRagResult answer(String prompt, String tenantId, String chatId,
                                   String conversationId, String modelProfile) {
        Timer.Sample pipelineSample = Timer.start(meterRegistry);
        String traceId = "trace-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        String pipelineOutcome = "error";

        try {
            String normalizedTenantId = TenantContext.normalize(tenantId);

            // Step 1: Hybrid retrieval (vector + keyword + graph + web)
            HybridRetrievalService.HybridRetrievalResult retrievalResult =
                    hybridRetrievalService.retrieve(prompt, normalizedTenantId, chatId,
                            ragProperties.getRetrieveTopK());

            List<ScoredDocument> retrievedDocs = retrievalResult.documents();
            if (retrievedDocs.isEmpty()) {
                pipelineOutcome = "empty";
                return HybridRagResult.builder()
                        .answer("没有在当前知识库中检索到可用内容。")
                        .citations(List.of())
                        .evidence(List.of())
                        .traceId(traceId)
                        .memoryUsed(List.of())
                        .build();
            }

            // Step 2: Evidence judging
            List<EvidenceItem> evidence = evidenceJudgeService.judge(retrievedDocs, prompt);

            // Step 3: Build citations
            List<CitationItem> citations = citationService.buildCitations(evidence);

            // Step 4: Build context from top evidence
            String context = buildContext(retrievedDocs);

            // Step 5: Generate answer via LLM
            ModelRouter.ModelRouteDecision decision = modelRouter.resolve(
                    modelProfile, "rag_hybrid", normalizedTenantId, chatId);
            long inputTokens = tenantCostService.estimateTokens(prompt + "\n" + context);
            tenantCostService.assertBudget(normalizedTenantId, decision.costTier(), inputTokens, 600);

            String answer = chatClient.prompt()
                    .options(ChatOptions.builder().model(decision.model())
                            .temperature(ragProperties.getTemperature()).build())
                    .system(SystemConstants.HYBRID_RAG_ANSWER_SYSTEM)
                    .user("用户问题:%n%s%n%n上下文:%n%s%n".formatted(prompt, context))
                    .advisors(a -> a.param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId))
                    .call()
                    .content();

            long outputTokens = tenantCostService.estimateTokens(answer);
            tenantCostService.recordUsage(normalizedTenantId, decision.costTier(),
                    inputTokens, outputTokens, "rag_hybrid");

            // Step 6: Append citation footer
            String answerWithCitations = answer + citationService.formatCitationFooter(citations);

            pipelineOutcome = "success";
            return HybridRagResult.builder()
                    .answer(answerWithCitations)
                    .citations(citations)
                    .evidence(evidence)
                    .traceId(traceId)
                    .memoryUsed(List.of())
                    .retrievalStats(HybridRagResult.RetrievalStats.builder()
                            .totalRetrieved(retrievalResult.totalBeforeDedup())
                            .afterDedup(retrievalResult.totalAfterDedup())
                            .finalCount(retrievedDocs.size())
                            .build())
                    .build();

        } finally {
            pipelineSample.stop(Timer.builder("rag.hybrid.pipeline.latency")
                    .description("Overall latency for hybrid RAG pipeline")
                    .tag("outcome", pipelineOutcome)
                    .publishPercentileHistogram()
                    .register(meterRegistry));
            Counter.builder("rag.hybrid.pipeline.requests")
                    .description("Total hybrid RAG pipeline requests")
                    .tag("outcome", pipelineOutcome)
                    .register(meterRegistry)
                    .increment();
        }
    }

    private String buildContext(List<ScoredDocument> docs) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < docs.size(); i++) {
            ScoredDocument d = docs.get(i);
            sb.append("[").append(i + 1).append("] ")
                    .append("source=").append(d.getSourceType())
                    .append(", title=").append(d.getTitle())
                    .append(", chunk=").append(d.getChunkId())
                    .append("\n")
                    .append(d.getContent())
                    .append("\n\n");
        }
        return sb.toString();
    }

    @Data
    @Builder
    public static class HybridRagResult {
        private String answer;
        private List<CitationItem> citations;
        private List<EvidenceItem> evidence;
        private String traceId;
        private List<String> memoryUsed;
        private RetrievalStats retrievalStats;

        @Data
        @Builder
        public static class RetrievalStats {
            private int totalRetrieved;
            private int afterDedup;
            private int finalCount;
        }
    }
}
