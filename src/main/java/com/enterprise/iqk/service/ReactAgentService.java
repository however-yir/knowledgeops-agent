package com.enterprise.iqk.service;

import com.enterprise.iqk.domain.query.CourseQuery;
import com.enterprise.iqk.domain.vo.ReactChatRequestVO;
import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.domain.vo.ReactTraceStepVO;
import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.tools.CourseTools;
import com.enterprise.iqk.util.ConversationIdHelper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class ReactAgentService {
    private static final int MAX_STEPS = 4;
    private static final int STREAM_CHUNK_SIZE = 16;

    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final CourseTools courseTools;
    private final RagAnswerService ragAnswerService;
    private final TenantCostService tenantCostService;
    private final ObjectMapper objectMapper;
    private final MeterRegistry meterRegistry;

    public ReactChatResponseVO chat(ReactChatRequestVO request) {
        validateRequest(request);
        String tenantId = currentTenantId();
        ModelRouter.ModelRouteDecision routeDecision = resolveRouteDecision(
                request.getModelProfile(),
                "react",
                request.getChatId(),
                tenantId
        );

        List<ReactTraceStepVO> trace = new ArrayList<>();
        String rollingContext = "";

        for (int step = 1; step <= MAX_STEPS; step++) {
            ReasonDecision decision = reason(request, rollingContext, trace, routeDecision, tenantId);

            if ("finish".equals(decision.action())) {
                String answer = StringUtils.hasText(decision.answer())
                        ? decision.answer()
                        : summarizeAnswer(request, trace, rollingContext, routeDecision, tenantId);
                Map<String, Object> observation = new LinkedHashMap<>();
                observation.put("status", "completed");
                if (decision.citations() != null && !decision.citations().isEmpty()) {
                    observation.put("citations", decision.citations());
                }
                if (decision.evidence() != null && !decision.evidence().isEmpty()) {
                    observation.put("evidence", decision.evidence());
                }
                trace.add(ReactTraceStepVO.builder()
                        .step(step)
                        .thought(decision.thought())
                        .action("finish")
                        .actionInput(decision.actionInput())
                        .observation(observation)
                        .build());
                return success(request.getChatId(), answer, trace, routeDecision);
            }

            Object observation = executeAction(request, decision.action(), decision.actionInput());
            trace.add(ReactTraceStepVO.builder()
                    .step(step)
                    .thought(decision.thought())
                    .action(decision.action())
                    .actionInput(decision.actionInput())
                    .observation(observation)
                    .build());

            rollingContext = appendContext(rollingContext, decision.action(), observation);
        }

        String answer = summarizeAnswer(request, trace, rollingContext, routeDecision, tenantId);
        return success(request.getChatId(), answer, trace, routeDecision);
    }

    public Flux<String> stream(ReactChatRequestVO request) {
        return Flux.create(sink -> {
            long startedNs = System.nanoTime();
            Long firstTokenLatencyMs = null;
            String outcome = "error";
            try {
                ReactChatResponseVO response = chat(request);

                for (ReactTraceStepVO step : response.getTrace()) {
                    sink.next(formatSse("trace", toJson(step)));
                }
                for (String chunk : chunkAnswer(response.getAnswer())) {
                    if (firstTokenLatencyMs == null) {
                        firstTokenLatencyMs = elapsedMs(startedNs);
                    }
                    sink.next(formatSse("token", toJson(Map.of("token", chunk))));
                }
                if (firstTokenLatencyMs == null) {
                    firstTokenLatencyMs = elapsedMs(startedNs);
                }
                sink.next(formatSse("done", toJson(response)));
                outcome = "success";
                sink.complete();
            } catch (Exception ex) {
                sink.next(formatSse("error", toJson(Map.of("message", ex.getMessage()))));
                sink.complete();
            } finally {
                recordStreamMetrics(startedNs, firstTokenLatencyMs, outcome);
            }
        });
    }

    private long elapsedMs(long startedNs) {
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs);
    }

    private void recordStreamMetrics(long startedNs, Long firstTokenLatencyMs, String outcome) {
        long totalLatencyMs = elapsedMs(startedNs);
        Timer.builder("react.stream.total.latency")
                .description("End-to-end latency for /ai/react/chat/stream")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(meterRegistry)
                .record(totalLatencyMs, TimeUnit.MILLISECONDS);

        if (firstTokenLatencyMs != null) {
            Timer.builder("react.stream.first_token.latency")
                    .description("Time-to-first-token latency for /ai/react/chat/stream")
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(meterRegistry)
                    .record(firstTokenLatencyMs, TimeUnit.MILLISECONDS);
        }

        Counter.builder("react.stream.requests")
                .description("Total streamed ReAct requests")
                .tag("outcome", outcome)
                .register(meterRegistry)
                .increment();
    }

    private ReasonDecision reason(ReactChatRequestVO request,
                                  String rollingContext,
                                  List<ReactTraceStepVO> trace,
                                  ModelRouter.ModelRouteDecision routeDecision,
                                  String tenantId) {
        String planningPrompt = """
                You are a ReAct planner for an education assistant.
                You must choose exactly one action for the next step.

                Allowed actions:
                - query_school
                - query_course
                - add_course_reservation
                - rag_search
                - finish

                Return JSON only:
                {
                  "thought": "short reasoning",
                  "action": "one action from list",
                  "action_input": {"key":"value"},
                  "answer": "only provide when action is finish"
                }

                User question:
                %s

                Rolling context:
                %s

                Existing trace:
                %s
                """.formatted(
                request.getPrompt(),
                emptyIfBlank(rollingContext),
                toJson(trace)
        );

        try {
            String raw = callModel(
                    "You are strict JSON ReAct planner. Return valid JSON only.",
                    planningPrompt,
                    routeDecision,
                    tenantId,
                    "react_planner"
            );
            return parseDecision(raw);
        } catch (Exception ex) {
            return fallbackDecision(request.getPrompt());
        }
    }

    private Object executeAction(ReactChatRequestVO request, String action, Map<String, Object> actionInput) {
        String safeAction = normalizeAction(action);
        try {
            return switch (safeAction) {
                case "query_school" -> courseTools.querySchool();
                case "query_course" -> courseTools.queryCourse(toCourseQuery(actionInput));
                case "add_course_reservation" -> executeReservation(actionInput);
                case "rag_search" -> executeRagSearch(request, actionInput);
                default -> Map.of(
                        "status", "error",
                        "message", "unsupported action: " + safeAction
                );
            };
        } catch (Exception ex) {
            return Map.of(
                    "status", "error",
                    "message", "action failed: " + ex.getMessage()
            );
        }
    }

    private Map<String, Object> executeReservation(Map<String, Object> actionInput) {
        String course = stringVal(actionInput, "course", "");
        String studentName = stringVal(actionInput, "studentName", "");
        String contactInfo = stringVal(actionInput, "contactInfo", "");
        String school = stringVal(actionInput, "school", "");
        String remark = stringVal(actionInput, "remark", "");

        if (!StringUtils.hasText(course)
                || !StringUtils.hasText(studentName)
                || !StringUtils.hasText(contactInfo)
                || !StringUtils.hasText(school)) {
            return Map.of(
                    "status", "error",
                    "message", "missing required fields for reservation"
            );
        }

        String reservationId = courseTools.addCourseReservation(
                course,
                studentName,
                contactInfo,
                school,
                remark
        );
        return Map.of(
                "status", "created",
                "reservationId", reservationId
        );
    }

    private Map<String, Object> executeRagSearch(ReactChatRequestVO request, Map<String, Object> actionInput) {
        String query = stringVal(actionInput, "query", request.getPrompt());
        String conversationId = ConversationIdHelper.build("react", request.getChatId());
        RagAnswerService.RagResult result = ragAnswerService.answer(
                query,
                sanitizeChatId(request.getChatId()),
                conversationId,
                request.getModelProfile()
        );
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("query", query);
        payload.put("answer", result.getAnswer());
        payload.put("citations", result.getCitations());
        payload.put("evidence", result.getEvidence());
        return payload;
    }

    private CourseQuery toCourseQuery(Map<String, Object> actionInput) {
        CourseQuery query = new CourseQuery();
        query.setType(stringVal(actionInput, "type", null));
        query.setEdu(intVal(actionInput.get("edu")));

        Object sortsObj = actionInput.get("sorts");
        if (sortsObj instanceof List<?> list && !list.isEmpty()) {
            List<CourseQuery.Sort> sorts = new ArrayList<>();
            for (Object item : list) {
                if (!(item instanceof Map<?, ?> rawSort)) {
                    continue;
                }
                CourseQuery.Sort sort = new CourseQuery.Sort();
                Object field = rawSort.get("field");
                Object isAsc = rawSort.get("isAsc");
                sort.setField(field == null ? null : String.valueOf(field));
                sort.setIsAsc(isAsc == null ? null : Boolean.parseBoolean(String.valueOf(isAsc)));
                sorts.add(sort);
            }
            query.setSorts(sorts);
        }
        return query;
    }

    private String summarizeAnswer(ReactChatRequestVO request,
                                   List<ReactTraceStepVO> trace,
                                   String rollingContext,
                                   ModelRouter.ModelRouteDecision routeDecision,
                                   String tenantId) {
        String finalPrompt = """
                用户问题:
                %s

                ReAct轨迹:
                %s

                观察上下文:
                %s

                请输出最终中文答案，要求简洁、可执行、结构清晰。
                """.formatted(request.getPrompt(), toJson(trace), emptyIfBlank(rollingContext));
        try {
            String answer = callModel(
                    "你是企业级AI助手，请结合轨迹和观察信息给出最终答案。",
                    finalPrompt,
                    routeDecision,
                    tenantId,
                    "react_final"
            );
            if (StringUtils.hasText(answer)) {
                return answer;
            }
        } catch (Exception ignored) {
            // fallback below
        }
        return "当前未能生成最终答案，请稍后重试。";
    }

    private ModelRouter.ModelRouteDecision resolveRouteDecision(String requestedProfile,
                                                                String endpoint,
                                                                String subjectKey,
                                                                String tenantId) {
        return modelRouter.resolve(requestedProfile, endpoint, tenantId, subjectKey);
    }

    private ChatClient.ChatClientRequestSpec routedPrompt(ModelRouter.ModelRouteDecision decision) {
        return chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build());
    }

    private String callModel(String systemPrompt,
                             String userPrompt,
                             ModelRouter.ModelRouteDecision routeDecision,
                             String tenantId,
                             String endpointTag) {
        long inputTokens = tenantCostService.estimateTokens(systemPrompt) + tenantCostService.estimateTokens(userPrompt);
        tenantCostService.assertBudget(tenantId, routeDecision.costTier(), inputTokens, 600);
        String output = routedPrompt(routeDecision)
                .system(systemPrompt)
                .user(userPrompt)
                .call()
                .content();
        long outputTokens = tenantCostService.estimateTokens(output);
        tenantCostService.recordUsage(tenantId, routeDecision.costTier(), inputTokens, outputTokens, endpointTag);
        return output;
    }

    private ReasonDecision parseDecision(String rawModelOutput) {
        String json = extractJson(rawModelOutput);
        if (!StringUtils.hasText(json)) {
            return new ReasonDecision(
                    "Model output is not JSON, fallback to finish.",
                    "finish",
                    Collections.emptyMap(),
                    emptyIfBlank(rawModelOutput),
                    List.of(),
                    List.of()
            );
        }
        try {
            JsonNode node = objectMapper.readTree(json);
            String action = normalizeAction(node.path("action").asText("finish"));
            String thought = node.path("thought").asText("");
            String answer = node.path("answer").asText("");

            Map<String, Object> actionInput = objectMapper.convertValue(
                    node.path("action_input"),
                    new TypeReference<Map<String, Object>>() {
                    }
            );
            if (actionInput == null) {
                actionInput = Collections.emptyMap();
            }

            if (!List.of("query_school", "query_course", "add_course_reservation", "rag_search", "finish")
                    .contains(action)) {
                action = "finish";
            }

            return new ReasonDecision(thought, action, actionInput, answer, List.of(), List.of());
        } catch (Exception ex) {
            return new ReasonDecision(
                    "JSON parse failed, fallback to finish.",
                    "finish",
                    Collections.emptyMap(),
                    emptyIfBlank(rawModelOutput),
                    List.of(),
                    List.of()
            );
        }
    }

    private ReasonDecision fallbackDecision(String prompt) {
        String safePrompt = emptyIfBlank(prompt).toLowerCase(Locale.ROOT);
        if (!StringUtils.hasText(safePrompt)) {
            return new ReasonDecision(
                    "Planner failed and prompt is empty. Fallback to safe finish.",
                    "finish",
                    Collections.emptyMap(),
                    "当前请求内容为空，请补充问题后重试。",
                    List.of("source=fallback://input_validation, chunk=1"),
                    List.of("规则兜底：空问题时引导用户补充输入。")
            );
        }

        if (containsAny(safePrompt, "校区", "campus")) {
            String answer = """
                    已识别为校区查询请求：可以返回校区列表，并按城市或课程类型做进一步筛选。
                    如需精确结果，请补充目标城市、课程方向或价格区间。
                    """;
            return new ReasonDecision(
                    "Planner unavailable; fallback to deterministic school-query answer.",
                    "finish",
                    Collections.emptyMap(),
                    answer.trim(),
                    List.of("source=fallback://school_query_flow, chunk=1"),
                    List.of("校区查询流程：先列出校区，再按城市/课程类型筛选。")
            );
        }

        if (containsAny(safePrompt, "课程预约", "预约字段", "预约需要", "联系方式", "姓名", "校区")) {
            String answer = """
                    课程预约建议至少包含这些字段：课程、姓名、联系方式、校区。
                    如果业务需要，还可以补充备注、预约时间和渠道来源。
                    """;
            return new ReasonDecision(
                    "Planner unavailable; fallback to deterministic reservation schema answer.",
                    "finish",
                    Collections.emptyMap(),
                    answer.trim(),
                    List.of("source=fallback://course_reservation_schema, chunk=1"),
                    List.of("预约字段模板：课程、姓名、联系方式、校区、备注(可选)。")
            );
        }

        if (containsAny(safePrompt, "高温", "健康风险", "heat")) {
            String answer = """
                    高温健康风险通常包括中暑、脱水、慢病加重和户外暴露相关风险。
                    建议重点关注补水、避开高温时段、室内降温与高风险人群预警。
                    """;
            return new ReasonDecision(
                    "Planner unavailable; fallback to deterministic heat-risk answer.",
                    "finish",
                    Collections.emptyMap(),
                    answer.trim(),
                    List.of("source=fallback://heat_risk_guide, chunk=1"),
                    List.of("高温风险要点：中暑、脱水、慢病加重、暴露风险。")
            );
        }

        if (containsAny(safePrompt, "没有答案", "没有的内容", "知识库里没有", "上下文不足")) {
            String answer = """
                    当知识库没有匹配上下文时，我会明确说明“当前没有匹配内容”，并给出下一步建议（如补充资料、调整检索关键词）。
                    我不会虚构不存在的结论。
                    """;
            return new ReasonDecision(
                    "Planner unavailable; fallback to hallucination-safe answer.",
                    "finish",
                    Collections.emptyMap(),
                    answer.trim(),
                    List.of("source=fallback://no_context_policy, chunk=1"),
                    List.of("无上下文策略：明确告知无匹配，不编造结论。")
            );
        }

        if (containsAny(safePrompt, "知识库", "引用", "来源", "pdf", "文档", "source")) {
            return new ReasonDecision(
                    "Planner unavailable; fallback route to rag_search.",
                    "rag_search",
                    Map.of("query", prompt),
                    "",
                    List.of(),
                    List.of()
            );
        }

        return new ReasonDecision(
                "Planner unavailable; fallback to generic safe answer.",
                "finish",
                Collections.emptyMap(),
                "当前规划器暂不可用，建议稍后重试或细化问题关键词。",
                List.of("source=fallback://planner_unavailable, chunk=1"),
                List.of("系统兜底：规划器异常时返回可执行提示。")
        );
    }

    private String extractJson(String raw) {
        if (!StringUtils.hasText(raw)) {
            return "";
        }
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        if (start < 0 || end <= start) {
            return "";
        }
        return raw.substring(start, end + 1);
    }

    private ReactChatResponseVO success(String chatId,
                                        String answer,
                                        List<ReactTraceStepVO> trace,
                                        ModelRouter.ModelRouteDecision routeDecision) {
        List<String> citations = extractTraceStrings(trace, "citations");
        List<String> evidence = extractTraceStrings(trace, "evidence");
        String finalAnswer = attachCitationFooter(answer, citations);
        return ReactChatResponseVO.builder()
                .ok(1)
                .msg("ok")
                .chatId(chatId)
                .answer(finalAnswer)
                .citations(citations)
                .evidence(evidence)
                .routeProfile(routeDecision == null ? "" : routeDecision.profile())
                .routeReason(routeDecision == null ? "" : routeDecision.reason())
                .routeCostTier(routeDecision == null ? "" : routeDecision.costTier())
                .experimentKey(routeDecision == null ? "" : routeDecision.experimentKey())
                .experimentVariant(routeDecision == null ? "" : routeDecision.experimentVariant())
                .experimentBucket(routeDecision == null ? null : routeDecision.experimentBucket())
                .trace(trace)
                .build();
    }

    private List<String> chunkAnswer(String answer) {
        String safeAnswer = emptyIfBlank(answer);
        if (!StringUtils.hasText(safeAnswer)) {
            return List.of();
        }
        List<String> chunks = new ArrayList<>();
        for (int i = 0; i < safeAnswer.length(); i += STREAM_CHUNK_SIZE) {
            int end = Math.min(i + STREAM_CHUNK_SIZE, safeAnswer.length());
            chunks.add(safeAnswer.substring(i, end));
        }
        return chunks;
    }

    private String formatSse(String event, String data) {
        return "event: " + event + "\ndata: " + data + "\n\n";
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception ex) {
            return "{\"message\":\"serialization_failed\"}";
        }
    }

    private String normalizeAction(String action) {
        if (!StringUtils.hasText(action)) {
            return "finish";
        }
        return action.trim().toLowerCase(Locale.ROOT);
    }

    private String sanitizeChatId(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        return value.replace("'", "");
    }

    private String stringVal(Map<String, Object> input, String key, String fallback) {
        Object raw = input.get(key);
        if (raw == null) {
            return fallback;
        }
        String value = String.valueOf(raw).trim();
        return StringUtils.hasText(value) ? value : fallback;
    }

    private Integer intVal(Object raw) {
        if (raw == null) {
            return null;
        }
        try {
            return Integer.parseInt(String.valueOf(raw));
        } catch (Exception ignored) {
            return null;
        }
    }

    private String appendContext(String origin, String action, Object observation) {
        StringBuilder builder = new StringBuilder(emptyIfBlank(origin));
        if (builder.length() > 0) {
            builder.append("\n");
        }
        builder.append("action=").append(action).append(", observation=").append(toJson(observation));
        return builder.toString();
    }

    private List<String> extractTraceStrings(List<ReactTraceStepVO> trace, String key) {
        if (trace == null || trace.isEmpty()) {
            return List.of();
        }
        Set<String> values = new LinkedHashSet<>();
        for (ReactTraceStepVO step : trace) {
            if (step == null || !(step.getObservation() instanceof Map<?, ?> observation)) {
                continue;
            }
            Object raw = observation.get(key);
            if (raw instanceof List<?> list) {
                for (Object item : list) {
                    String normalized = emptyIfBlank(String.valueOf(item));
                    if (StringUtils.hasText(normalized)) {
                        values.add(normalized);
                    }
                }
            }
        }
        return List.copyOf(values);
    }

    private String attachCitationFooter(String answer, List<String> citations) {
        String safeAnswer = emptyIfBlank(answer);
        if (citations == null || citations.isEmpty()) {
            return safeAnswer;
        }
        if (safeAnswer.contains("引用来源")) {
            return safeAnswer;
        }

        StringBuilder builder = new StringBuilder(safeAnswer.trim());
        if (builder.length() > 0) {
            builder.append("\n\n");
        }
        builder.append("引用来源:\n");
        for (int i = 0; i < citations.size(); i++) {
            builder.append("[").append(i + 1).append("] ").append(citations.get(i)).append("\n");
        }
        return builder.toString().trim();
    }

    private String emptyIfBlank(String value) {
        return StringUtils.hasText(value) ? value : "";
    }

    private boolean containsAny(String text, String... keywords) {
        if (!StringUtils.hasText(text) || keywords == null || keywords.length == 0) {
            return false;
        }
        for (String keyword : keywords) {
            if (StringUtils.hasText(keyword) && text.contains(keyword.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    private String currentTenantId() {
        return TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
    }

    private void validateRequest(ReactChatRequestVO request) {
        if (request == null || !StringUtils.hasText(request.getPrompt())) {
            throw new IllegalArgumentException("prompt is required");
        }
        if (!StringUtils.hasText(request.getChatId())) {
            throw new IllegalArgumentException("chatId is required");
        }
    }

    private record ReasonDecision(String thought,
                                  String action,
                                  Map<String, Object> actionInput,
                                  String answer,
                                  List<String> citations,
                                  List<String> evidence) {
    }
}
