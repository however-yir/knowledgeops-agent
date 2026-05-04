package com.enterprise.iqk.agent.research;

import com.enterprise.iqk.agent.workflow.AgentWorkflowEngine;
import com.enterprise.iqk.agent.workflow.WorkflowState;
import com.enterprise.iqk.rag.HybridRagAnswerService;
import com.enterprise.iqk.retrieval.HybridRetrievalService;
import com.enterprise.iqk.retrieval.ScoredDocument;
import com.enterprise.iqk.security.TenantContext;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.Builder;
import lombok.Data;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeepResearchService {

    private final ResearchPlannerAgent plannerAgent;
    private final ReportWriterAgent writerAgent;
    private final HybridRetrievalService hybridRetrievalService;
    private final AgentWorkflowEngine workflowEngine;
    private final MeterRegistry meterRegistry;

    public DeepResearchResult executeResearch(ResearchTaskRequest request, String tenantId) {
        long startedNs = System.nanoTime();
        String normalizedTenant = TenantContext.normalize(tenantId);

        var task = workflowEngine.startTask(normalizedTenant, "DEEP_RESEARCH",
                request.getTopic(), request.getModelProfile(), null, null);

        try {
            // Step 1: Plan - decompose topic
            workflowEngine.transitionStatus(task.getTaskId(), WorkflowState.PLANNING, WorkflowState.SEARCHING);
            var planStep = workflowEngine.startStep(task.getTaskId(), "ResearchPlanner", 1,
                    Map.of("topic", request.getTopic()));
            ResearchPlannerAgent.ResearchPlan plan = plannerAgent.plan(
                    request.getTopic(), normalizedTenant, request.getModelProfile());
            workflowEngine.completeStep(planStep.getStepId(), "COMPLETED",
                    Map.of("subQuestions", plan.subQuestions(), "strategy", plan.strategy()),
                    plan, null, null, null, 0, 0,
                    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs), null);

            // Step 2: Search & Retrieve for each sub-question
            workflowEngine.transitionStatus(task.getTaskId(), WorkflowState.SEARCHING, WorkflowState.RETRIEVING);
            List<String> findings = new ArrayList<>();
            int stepNum = 2;
            for (String subQ : plan.subQuestions()) {
                var searchStep = workflowEngine.startStep(task.getTaskId(), "RagResearchAgent", stepNum,
                        Map.of("subQuestion", subQ));

                HybridRetrievalService.HybridRetrievalResult retrieval =
                        hybridRetrievalService.retrieve(subQ, normalizedTenant,
                                "research_" + task.getTaskId(), 5);

                StringBuilder finding = new StringBuilder("## " + subQ + "\n\n");
                for (ScoredDocument doc : retrieval.documents()) {
                    finding.append("- [").append(doc.getSourceType()).append("] ")
                            .append(doc.getTitle()).append(": ")
                            .append(doc.getContent().substring(0, Math.min(200, doc.getContent().length())))
                            .append("\n");
                }
                findings.add(finding.toString());

                workflowEngine.completeStep(searchStep.getStepId(), "COMPLETED",
                        Map.of("docsFound", retrieval.documents().size()),
                        Map.of("finding", finding.toString()),
                        null, null, null, 0, 0, 0, null);
                stepNum++;
            }

            // Step 3: Write report
            workflowEngine.transitionStatus(task.getTaskId(), WorkflowState.RETRIEVING, WorkflowState.WRITING);
            var writeStep = workflowEngine.startStep(task.getTaskId(), "ReportWriter", stepNum,
                    Map.of("topic", request.getTopic()));
            String report = writerAgent.writeReport(request.getTopic(),
                    String.join("\n\n", findings), normalizedTenant, request.getModelProfile());
            workflowEngine.completeStep(writeStep.getStepId(), "COMPLETED",
                    Map.of("reportLength", report.length()), report,
                    null, null, null, 0, 0, 0, null);

            workflowEngine.completeTask(task.getTaskId(), WorkflowState.DONE, report);
            workflowEngine.recordTaskMetrics("DEEP_RESEARCH", "DONE",
                    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs));

            return DeepResearchResult.builder()
                    .taskId(task.getTaskId())
                    .topic(request.getTopic())
                    .report(report)
                    .status("DONE")
                    .build();

        } catch (Exception e) {
            log.error("Deep research failed for task {}", task.getTaskId(), e);
            workflowEngine.failTask(task.getTaskId(), e.getMessage());
            workflowEngine.recordTaskMetrics("DEEP_RESEARCH", "FAILED",
                    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs));
            return DeepResearchResult.builder()
                    .taskId(task.getTaskId())
                    .topic(request.getTopic())
                    .report("Research failed: " + e.getMessage())
                    .status("FAILED")
                    .build();
        }
    }

    @Data
    @Builder
    public static class DeepResearchResult {
        private String taskId;
        private String topic;
        private String report;
        private String status;
    }
}
