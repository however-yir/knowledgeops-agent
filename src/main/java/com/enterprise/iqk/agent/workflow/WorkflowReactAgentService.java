package com.enterprise.iqk.agent.workflow;

import com.enterprise.iqk.agent.harness.AgentAction;
import com.enterprise.iqk.agent.harness.AgentHarnessService;
import com.enterprise.iqk.domain.vo.ReactChatRequestVO;
import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.domain.vo.ReactTraceStepVO;
import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.TenantCostService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

@Service
@RequiredArgsConstructor
public class WorkflowReactAgentService {

    private static final int MAX_STEPS = 6;

    private final AgentWorkflowEngine workflowEngine;
    private final AgentHarnessService agentHarnessService;
    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final TenantCostService tenantCostService;
    private final ObjectMapper objectMapper;
    private final MeterRegistry meterRegistry;

    public ReactChatResponseVO chat(ReactChatRequestVO request) {
        validateRequest(request);
        String tenantId = currentTenantId();
        long startedNs = System.nanoTime();

        AgentTaskRecord task = workflowEngine.startTask(
                tenantId, "REACT", request.getPrompt(),
                request.getModelProfile(), request.getChatId(), null);

        ModelRouter.ModelRouteDecision routeDecision = resolveRouteDecision(
                request.getModelProfile(), "react", request.getChatId(), tenantId);

        List<ReactTraceStepVO> trace = new ArrayList<>();
        String rollingContext = "";

        try {
            for (int stepNum = 1; stepNum <= MAX_STEPS; stepNum++) {
                AgentStepRecord stepRecord = workflowEngine.startStep(
                        task.getTaskId(), "planner", stepNum,
                        Map.of("prompt", request.getPrompt(), "rollingContext", rollingContext));

                long stepStartNs = System.nanoTime();
                ReasonDecision decision = reason(request, rollingContext, trace, routeDecision, tenantId);

                if ("finish".equals(decision.action())) {
                    String answer = StringUtils.hasText(decision.answer())
                            ? decision.answer()
                            : summarizeAnswer(request, trace, rollingContext, routeDecision, tenantId);
                    Map<String, Object> obs = new LinkedHashMap<>();
                    obs.put("status", "completed");
                    obs.put("citations", decision.citations() != null ? decision.citations() : List.of());
                    obs.put("evidence", decision.evidence() != null ? decision.evidence() : List.of());

                    trace.add(buildTraceStep(stepNum, decision, obs));
                    workflowEngine.completeStep(stepRecord.getStepId(), "COMPLETED",
                            Map.of("answer", answer), obs,
                            decision.thought(), "finish", decision.actionInput(),
                            0, 0, elapsedMs(stepStartNs), null);
                    workflowEngine.completeTask(task.getTaskId(), WorkflowState.DONE, answer);
                    workflowEngine.recordTaskMetrics("REACT", "DONE", elapsedMs(startedNs));
                    return success(request.getChatId(), answer, trace, routeDecision, task.getTaskId());
                }

                workflowEngine.transitionStatus(task.getTaskId(),
                        mapToWorkflowState(stepNum), mapToWorkflowState(stepNum + 1));

                Object observation = executeAction(request, decision.action(), decision.actionInput(), tenantId,
                        task.getTaskId(), stepRecord.getStepId());
                trace.add(buildTraceStep(stepNum, decision, observation));
                workflowEngine.completeStep(stepRecord.getStepId(), "COMPLETED",
                        null, observation,
                        decision.thought(), decision.action(), decision.actionInput(),
                        0, 0, elapsedMs(stepStartNs), null);

                rollingContext = appendContext(rollingContext, decision.action(), observation);
            }

            String answer = summarizeAnswer(request, trace, rollingContext, routeDecision, tenantId);
            workflowEngine.completeTask(task.getTaskId(), WorkflowState.DONE, answer);
            workflowEngine.recordTaskMetrics("REACT", "DONE", elapsedMs(startedNs));
            return success(request.getChatId(), answer, trace, routeDecision, task.getTaskId());

        } catch (RuntimeException e) {
            workflowEngine.failTask(task.getTaskId(), e.getMessage());
            workflowEngine.recordTaskMetrics("REACT", "FAILED", elapsedMs(startedNs));
            throw e;
        }
    }

    public Flux<String> stream(ReactChatRequestVO request) {
        long startedNs = System.nanoTime();
        AtomicReference<Long> firstTokenMs = new AtomicReference<>(null);
        AtomicReference<String> outcomeRef = new AtomicReference<>("error");

        return Flux.defer(() -> {
            validateRequest(request);
            String tenantId = currentTenantId();

            AgentTaskRecord task = workflowEngine.startTask(
                    tenantId, "REACT_STREAM", request.getPrompt(),
                    request.getModelProfile(), request.getChatId(), null);

            ModelRouter.ModelRouteDecision routeDecision = resolveRouteDecision(
                    request.getModelProfile(), "react", request.getChatId(), tenantId);

            List<ReactTraceStepVO> trace = new ArrayList<>();
            String rollingContext = "";
            String directAnswer = "";

            for (int stepNum = 1; stepNum <= MAX_STEPS; stepNum++) {
                AgentStepRecord stepRecord = workflowEngine.startStep(
                        task.getTaskId(), "planner", stepNum,
                        Map.of("prompt", request.getPrompt()));

                long stepStartNs = System.nanoTime();
                ReasonDecision decision = reason(request, rollingContext, trace, routeDecision, tenantId);

                if ("finish".equals(decision.action())) {
                    Map<String, Object> obs = new LinkedHashMap<>();
                    obs.put("status", "completed");
                    trace.add(buildTraceStep(stepNum, decision, obs));
                    directAnswer = emptyIfBlank(decision.answer());
                    workflowEngine.completeStep(stepRecord.getStepId(), "COMPLETED",
                            Map.of("answer", directAnswer), obs,
                            decision.thought(), "finish", decision.actionInput(),
                            0, 0, elapsedMs(stepStartNs), null);
                    break;
                }

                Object observation = executeAction(request, decision.action(), decision.actionInput(), tenantId,
                        task.getTaskId(), stepRecord.getStepId());
                trace.add(buildTraceStep(stepNum, decision, observation));
                workflowEngine.completeStep(stepRecord.getStepId(), "COMPLETED",
                        null, observation,
                        decision.thought(), decision.action(), decision.actionInput(),
                        0, 0, elapsedMs(stepStartNs), null);
                rollingContext = appendContext(rollingContext, decision.action(), observation);
            }

            Flux<String> traceFlux = Flux.fromIterable(trace)
                    .map(step -> formatSse("trace", toJson(step)));

            StringBuilder answerBuilder = new StringBuilder();
            Flux<String> answerFlux = StringUtils.hasText(directAnswer)
                    ? Flux.just(directAnswer)
                    : callModelStream(
                    "你是企业级AI助手，请结合轨迹和观察信息给出最终答案。",
                    buildFinalPrompt(request, trace, rollingContext),
                    routeDecision, tenantId, "react_final");

            Flux<String> tokenFlux = answerFlux
                    .map(token -> {
                        if (firstTokenMs.get() == null) {
                            firstTokenMs.set(elapsedMs(startedNs));
                        }
                        answerBuilder.append(token);
                        return formatSse("token", toJson(Map.of("token", token)));
                    });

            String finalTaskId = task.getTaskId();
            return Flux.concat(traceFlux, tokenFlux)
                    .concatWith(Flux.defer(() -> {
                        if (firstTokenMs.get() == null) {
                            firstTokenMs.set(elapsedMs(startedNs));
                        }
                        String answer = answerBuilder.toString();
                        ReactChatResponseVO response = success(
                                request.getChatId(), answer, trace, routeDecision, finalTaskId);
                        workflowEngine.completeTask(finalTaskId, WorkflowState.DONE, answer);
                        outcomeRef.set("success");
                        return Flux.just(formatSse("done", toJson(response)));
                    }));
        })
                .onErrorResume(ex -> {
                    String message = StringUtils.hasText(ex.getMessage())
                            ? ex.getMessage() : "stream failed";
                    return Flux.just(formatSse("error", toJson(Map.of("message", message))));
                })
                .doFinally(signal -> recordStreamMetrics(startedNs, firstTokenMs.get(), outcomeRef.get()));
    }

    // ── Reason / Action / Summarize (same logic, now with engine) ──

    private ReasonDecision reason(ReactChatRequestVO request,
                                  String rollingContext,
                                  List<ReactTraceStepVO> trace,
                                  ModelRouter.ModelRouteDecision routeDecision,
                                  String tenantId) {
        String planningPrompt = "You are a ReAct planner for an education assistant.%nYou must choose exactly one action for the next step.%n%nAllowed actions:%n- query_school%n- query_course%n- add_course_reservation%n- rag_search%n- finish%n%nReturn JSON only:%n{%n  \"thought\": \"short reasoning\",%n  \"action\": \"one action from list\",%n  \"action_input\": {\"key\":\"value\"},%n  \"answer\": \"only provide when action is finish\"%n}%n%nUser question:%n%s%n%nRolling context:%n%s%n%nExisting trace:%n%s%n".formatted(request.getPrompt(), emptyIfBlank(rollingContext), toJson(trace));

        try {
            String raw = callModel("You are strict JSON ReAct planner. Return valid JSON only.",
                    planningPrompt, routeDecision, tenantId, "react_planner");
            return parseDecision(raw);
        } catch (RuntimeException ex) {
            return fallbackDecision(request.getPrompt());
        }
    }

    private Map<String, Object> executeAction(ReactChatRequestVO request,
                                              String action,
                                              Map<String, Object> actionInput,
                                              String tenantId,
                                              String taskId,
                                              String stepId) {
        return agentHarnessService.execute(new AgentAction(
                action,
                actionInput,
                request.getPrompt(),
                tenantId,
                request.getChatId(),
                request.getModelProfile(),
                taskId,
                stepId
        )).toMap();
    }

    private String summarizeAnswer(ReactChatRequestVO request, List<ReactTraceStepVO> trace,
                                    String rollingContext, ModelRouter.ModelRouteDecision routeDecision,
                                    String tenantId) {
        String finalPrompt = buildFinalPrompt(request, trace, rollingContext);
        try {
            String answer = callModel("你是企业级AI助手，请结合轨迹和观察信息给出最终答案。",
                    finalPrompt, routeDecision, tenantId, "react_final");
            if (StringUtils.hasText(answer)) return answer;
        } catch (RuntimeException ignored) {}
        return "当前未能生成最终答案，请稍后重试。";
    }

    private String buildFinalPrompt(ReactChatRequestVO request,
                                     List<ReactTraceStepVO> trace, String rollingContext) {
        return "用户问题:%n%s%n%nReAct轨迹:%n%s%n%n观察上下文:%n%s%n%n请输出最终中文答案，要求简洁、可执行、结构清晰。%n".formatted(request.getPrompt(), toJson(trace), emptyIfBlank(rollingContext));
    }

    // ── Helpers (delegated from original ReactAgentService) ──────

    private ReactTraceStepVO buildTraceStep(int step, ReasonDecision d, Object obs) {
        return ReactTraceStepVO.builder()
                .step(step).thought(d.thought()).action(d.action())
                .actionInput(d.actionInput()).observation(obs).build();
    }

    private ReactChatResponseVO success(String chatId, String answer,
                                         List<ReactTraceStepVO> trace,
                                         ModelRouter.ModelRouteDecision routeDecision,
                                         String taskId) {
        List<String> citations = extractTraceStrings(trace, "citations");
        List<String> evidence = extractTraceStrings(trace, "evidence");
        return ReactChatResponseVO.builder()
                .ok(1).msg("ok").chatId(chatId)
                .answer(attachCitationFooter(answer, citations))
                .citations(citations).evidence(evidence)
                .routeProfile(routeDecision == null ? "" : routeDecision.profile())
                .routeReason(routeDecision == null ? "" : routeDecision.reason())
                .routeCostTier(routeDecision == null ? "" : routeDecision.costTier())
                .experimentKey(routeDecision == null ? "" : routeDecision.experimentKey())
                .experimentVariant(routeDecision == null ? "" : routeDecision.experimentVariant())
                .experimentBucket(routeDecision == null ? null : routeDecision.experimentBucket())
                .trace(trace)
                .build();
    }

    private ModelRouter.ModelRouteDecision resolveRouteDecision(String profile, String endpoint,
                                                                 String subjectKey, String tenantId) {
        return modelRouter.resolve(profile, endpoint, tenantId, subjectKey);
    }

    private String callModel(String system, String user, ModelRouter.ModelRouteDecision decision,
                              String tenantId, String endpointTag) {
        long inputTokens = tenantCostService.estimateTokens(system)
                + tenantCostService.estimateTokens(user);
        tenantCostService.assertBudget(tenantId, decision.costTier(), inputTokens, 600);
        String output = chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build())
                .system(system).user(user).call().content();
        long outputTokens = tenantCostService.estimateTokens(output);
        tenantCostService.recordUsage(tenantId, decision.costTier(), inputTokens, outputTokens, endpointTag);
        return output;
    }

    private Flux<String> callModelStream(String system, String user,
                                          ModelRouter.ModelRouteDecision decision,
                                          String tenantId, String endpointTag) {
        long inputTokens = tenantCostService.estimateTokens(system)
                + tenantCostService.estimateTokens(user);
        tenantCostService.assertBudget(tenantId, decision.costTier(), inputTokens, 600);
        StringBuilder collector = new StringBuilder();
        AtomicBoolean recorded = new AtomicBoolean(false);
        return chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build())
                .system(system).user(user).stream().content()
                .doOnNext(collector::append)
                .doFinally(sig -> {
                    if (!recorded.compareAndSet(false, true)) return;
                    long out = tenantCostService.estimateTokens(collector.toString());
                    tenantCostService.recordUsage(tenantId, decision.costTier(), inputTokens, out, endpointTag);
                });
    }

    private WorkflowState mapToWorkflowState(int step) {
        return switch (step) {
            case 1 -> WorkflowState.SEARCHING;
            case 2 -> WorkflowState.RETRIEVING;
            case 3 -> WorkflowState.JUDGING;
            case 4 -> WorkflowState.REFLECTING;
            default -> WorkflowState.WRITING;
        };
    }

    // ── Delegated helpers (same as original ReactAgentService) ───

    private ReasonDecision parseDecision(String raw) {
        String json = extractJson(raw);
        if (!StringUtils.hasText(json)) {
            return new ReasonDecision("Fallback to finish.", "finish",
                    Collections.emptyMap(), emptyIfBlank(raw), List.of(), List.of());
        }
        try {
            JsonNode node = objectMapper.readTree(json);
            String action = normalizeAction(node.path("action").asText("finish"));
            Map<String, Object> input = objectMapper.convertValue(
                    node.path("action_input"), new TypeReference<Map<String, Object>>() {});
            if (input == null) input = Collections.emptyMap();
            if (!List.of("query_school", "query_course", "add_course_reservation", "rag_search", "finish")
                    .contains(action)) action = "finish";
            return new ReasonDecision(node.path("thought").asText(""),
                    action, input, node.path("answer").asText(""), List.of(), List.of());
        } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
            return new ReasonDecision("Parse failed.", "finish",
                    Collections.emptyMap(), emptyIfBlank(raw), List.of(), List.of());
        }
    }

    private ReasonDecision fallbackDecision(String prompt) {
        String safe = emptyIfBlank(prompt).toLowerCase(Locale.ROOT);
        if (!StringUtils.hasText(safe)) {
            return new ReasonDecision("Empty prompt.", "finish", Collections.emptyMap(),
                    "当前请求内容为空，请补充问题后重试。",
                    List.of("source=fallback://input_validation, chunk=1"),
                    List.of("规则兜底：空问题时引导用户补充输入。"));
        }
        if (containsAny(safe, "校区", "campus")) {
            return new ReasonDecision("Fallback school query.", "finish", Collections.emptyMap(),
                    "已识别为校区查询请求：可以返回校区列表，并按城市或课程类型做进一步筛选。",
                    List.of("source=fallback://school_query_flow, chunk=1"),
                    List.of("校区查询流程：先列出校区，再按城市/课程类型筛选。"));
        }
        if (containsAny(safe, "课程预约", "预约字段", "预约需要", "联系方式", "姓名")) {
            return new ReasonDecision("Fallback reservation.", "finish", Collections.emptyMap(),
                    "课程预约建议至少包含：课程、姓名、联系方式、校区。",
                    List.of("source=fallback://course_reservation_schema, chunk=1"),
                    List.of("预约字段模板。"));
        }
        if (containsAny(safe, "知识库", "引用", "来源", "pdf", "文档", "source")) {
            return new ReasonDecision("Fallback rag.", "rag_search",
                    Map.of("query", prompt), "", List.of(), List.of());
        }
        return new ReasonDecision("Generic fallback.", "finish", Collections.emptyMap(),
                "当前规划器暂不可用，建议稍后重试或细化问题关键词。",
                List.of("source=fallback://planner_unavailable, chunk=1"),
                List.of("系统兜底。"));
    }

    private String extractJson(String raw) {
        if (!StringUtils.hasText(raw)) return "";
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        return (start < 0 || end <= start) ? "" : raw.substring(start, end + 1);
    }

    private List<String> extractTraceStrings(List<ReactTraceStepVO> trace, String key) {
        if (trace == null || trace.isEmpty()) return List.of();
        Set<String> values = new LinkedHashSet<>();
        for (ReactTraceStepVO step : trace) {
            if (!(step.getObservation() instanceof Map<?, ?> obs)) continue;
            Object raw = obs.get(key);
            if (raw instanceof List<?> list) {
                for (Object item : list) {
                    String s = emptyIfBlank(String.valueOf(item));
                    if (StringUtils.hasText(s)) values.add(s);
                }
            }
        }
        return List.copyOf(values);
    }

    private String attachCitationFooter(String answer, List<String> citations) {
        if (citations == null || citations.isEmpty()) return emptyIfBlank(answer);
        if (emptyIfBlank(answer).contains("引用来源")) return answer;
        StringBuilder sb = new StringBuilder(emptyIfBlank(answer).trim());
        if (sb.length() > 0) sb.append("\n\n");
        sb.append("引用来源:\n");
        for (int i = 0; i < citations.size(); i++) {
            sb.append("[").append(i + 1).append("] ").append(citations.get(i)).append("\n");
        }
        return sb.toString().trim();
    }

    private String formatSse(String event, String data) {
        return "event: " + event + "\ndata: " + data + "\n\n";
    }

    private String toJson(Object value) {
        try { return objectMapper.writeValueAsString(value); }
        catch (Exception e) { return "{\"message\":\"serialization_failed\"}"; }
    }

    private String appendContext(String origin, String action, Object observation) {
        StringBuilder sb = new StringBuilder(emptyIfBlank(origin));
        if (sb.length() > 0) sb.append("\n");
        sb.append("action=").append(action).append(", observation=").append(toJson(observation));
        return sb.toString();
    }

    private void recordStreamMetrics(long startedNs, Long firstTokenMs, String outcome) {
        long total = elapsedMs(startedNs);
        Timer.builder("react.stream.total.latency").tag("outcome", outcome)
                .publishPercentileHistogram().register(meterRegistry)
                .record(total, TimeUnit.MILLISECONDS);
        if (firstTokenMs != null) {
            Timer.builder("react.stream.first_token.latency").tag("outcome", outcome)
                    .publishPercentileHistogram().register(meterRegistry)
                    .record(firstTokenMs, TimeUnit.MILLISECONDS);
        }
        Counter.builder("react.stream.requests").tag("outcome", outcome)
                .register(meterRegistry).increment();
    }

    // ── Trivial delegates ──────────────────────────────────────────

    private String normalizeAction(String a) {
        return (!StringUtils.hasText(a)) ? "finish" : a.trim().toLowerCase(Locale.ROOT);
    }
    private long elapsedMs(long startedNs) { return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs); }
    private String emptyIfBlank(String v) { return StringUtils.hasText(v) ? v : ""; }
    private boolean containsAny(String text, String... keywords) {
        if (!StringUtils.hasText(text) || keywords == null) return false;
        for (String kw : keywords) {
            if (StringUtils.hasText(kw) && text.contains(kw.toLowerCase(Locale.ROOT))) return true;
        }
        return false;
    }
    private String currentTenantId() { return TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE)); }
    private void validateRequest(ReactChatRequestVO r) {
        if (r == null || !StringUtils.hasText(r.getPrompt())) throw new IllegalArgumentException("prompt is required");
        if (!StringUtils.hasText(r.getChatId())) throw new IllegalArgumentException("chatId is required");
    }

    private record ReasonDecision(String thought, String action,
                                   Map<String, Object> actionInput, String answer,
                                   List<String> citations, List<String> evidence) {}
}
