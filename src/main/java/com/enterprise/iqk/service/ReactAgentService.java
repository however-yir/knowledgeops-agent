package com.enterprise.iqk.service;

import com.enterprise.iqk.domain.query.CourseQuery;
import com.enterprise.iqk.domain.vo.ReactChatRequestVO;
import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.domain.vo.ReactTraceStepVO;
import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.tools.CourseTools;
import com.enterprise.iqk.util.ConversationIdHelper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

@Service
@RequiredArgsConstructor
public class ReactAgentService {
    private static final int MAX_STEPS = 4;
    private static final int STREAM_CHUNK_SIZE = 16;

    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final CourseTools courseTools;
    private final RagAnswerService ragAnswerService;
    private final ObjectMapper objectMapper;

    public ReactChatResponseVO chat(ReactChatRequestVO request) {
        validateRequest(request);

        List<ReactTraceStepVO> trace = new ArrayList<>();
        String rollingContext = "";

        for (int step = 1; step <= MAX_STEPS; step++) {
            ReasonDecision decision = reason(request, rollingContext, trace);

            if ("finish".equals(decision.action())) {
                String answer = StringUtils.hasText(decision.answer())
                        ? decision.answer()
                        : summarizeAnswer(request, trace, rollingContext);
                trace.add(ReactTraceStepVO.builder()
                        .step(step)
                        .thought(decision.thought())
                        .action("finish")
                        .actionInput(decision.actionInput())
                        .observation(Map.of("status", "completed"))
                        .build());
                return success(request.getChatId(), answer, trace);
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

        String answer = summarizeAnswer(request, trace, rollingContext);
        return success(request.getChatId(), answer, trace);
    }

    public Flux<String> stream(ReactChatRequestVO request) {
        return Flux.create(sink -> {
            try {
                ReactChatResponseVO response = chat(request);

                for (ReactTraceStepVO step : response.getTrace()) {
                    sink.next(formatSse("trace", toJson(step)));
                }
                for (String chunk : chunkAnswer(response.getAnswer())) {
                    sink.next(formatSse("token", toJson(Map.of("token", chunk))));
                }
                sink.next(formatSse("done", toJson(response)));
                sink.complete();
            } catch (Exception ex) {
                sink.next(formatSse("error", toJson(Map.of("message", ex.getMessage()))));
                sink.complete();
            }
        });
    }

    private ReasonDecision reason(ReactChatRequestVO request,
                                  String rollingContext,
                                  List<ReactTraceStepVO> trace) {
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
            String raw = routedPrompt(request.getModelProfile(), "react")
                    .system("You are strict JSON ReAct planner. Return valid JSON only.")
                    .user(planningPrompt)
                    .call()
                    .content();
            return parseDecision(raw);
        } catch (Exception ex) {
            return new ReasonDecision(
                    "Planner failed, fallback to finish.",
                    "finish",
                    Collections.emptyMap(),
                    "当前规划器不可用，建议稍后重试。"
            );
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
                                   String rollingContext) {
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
            String answer = routedPrompt(request.getModelProfile(), "react")
                    .system("你是企业级AI助手，请结合轨迹和观察信息给出最终答案。")
                    .user(finalPrompt)
                    .call()
                    .content();
            if (StringUtils.hasText(answer)) {
                return answer;
            }
        } catch (Exception ignored) {
            // fallback below
        }
        return "当前未能生成最终答案，请稍后重试。";
    }

    private ChatClient.ChatClientRequestSpec routedPrompt(String requestedProfile, String endpoint) {
        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(requestedProfile, endpoint);
        return chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build());
    }

    private ReasonDecision parseDecision(String rawModelOutput) {
        String json = extractJson(rawModelOutput);
        if (!StringUtils.hasText(json)) {
            return new ReasonDecision(
                    "Model output is not JSON, fallback to finish.",
                    "finish",
                    Collections.emptyMap(),
                    emptyIfBlank(rawModelOutput)
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

            return new ReasonDecision(thought, action, actionInput, answer);
        } catch (Exception ex) {
            return new ReasonDecision(
                    "JSON parse failed, fallback to finish.",
                    "finish",
                    Collections.emptyMap(),
                    emptyIfBlank(rawModelOutput)
            );
        }
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

    private ReactChatResponseVO success(String chatId, String answer, List<ReactTraceStepVO> trace) {
        return ReactChatResponseVO.builder()
                .ok(1)
                .msg("ok")
                .chatId(chatId)
                .answer(answer)
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

    private String emptyIfBlank(String value) {
        return StringUtils.hasText(value) ? value : "";
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
                                  String answer) {
    }
}

