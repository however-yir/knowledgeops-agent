package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.domain.query.CourseQuery;
import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.tools.CourseTools;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

@Component
@RequiredArgsConstructor
public class BuiltinToolRuntime implements AgentRuntime {
    private static final Set<String> SUPPORTED_ACTIONS = Set.of(
            "query_school",
            "query_course",
            "add_course_reservation",
            "rag_search"
    );

    private final CourseTools courseTools;
    private final RagAnswerService ragAnswerService;

    @Override
    public String source() {
        return "builtin";
    }

    @Override
    public boolean supports(String action) {
        return SUPPORTED_ACTIONS.contains(action);
    }

    @Override
    public AgentObservation execute(AgentAction action) {
        long startedNs = System.nanoTime();
        Object payload = switch (action.action()) {
            case "query_school" -> courseTools.querySchool();
            case "query_course" -> courseTools.queryCourse(toCourseQuery(action.actionInput()));
            case "add_course_reservation" -> executeReservation(action.actionInput());
            case "rag_search" -> executeRagSearch(action);
            default -> Map.of("status", "error", "message", "unsupported action: " + action.action());
        };
        if (payload instanceof Map<?, ?> mapPayload && "error".equals(mapPayload.get("status"))) {
            Object message = mapPayload.get("message");
            return AgentObservation.error(source(), message == null ? "action failed" : String.valueOf(message),
                    elapsedMs(startedNs));
        }
        return AgentObservation.success(source(), payload, elapsedMs(startedNs));
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

    private Map<String, Object> executeRagSearch(AgentAction action) {
        String query = stringVal(action.actionInput(), "query", action.prompt());
        String conversationId = ConversationIdHelper.build("react", action.chatId());
        RagAnswerService.RagResult result = ragAnswerService.answer(
                query,
                action.tenantId(),
                sanitizeChatId(action.chatId()),
                conversationId,
                action.modelProfile()
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

    private long elapsedMs(long startedNs) {
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs);
    }
}
