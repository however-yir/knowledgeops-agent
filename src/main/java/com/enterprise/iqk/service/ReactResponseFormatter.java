package com.enterprise.iqk.service;

import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.domain.vo.ReactTraceStepVO;
import com.enterprise.iqk.llm.ModelRouter;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

@Component
@RequiredArgsConstructor
public class ReactResponseFormatter {
    private final ObjectMapper objectMapper;

    public ReactChatResponseVO success(String chatId,
                                       String answer,
                                       List<ReactTraceStepVO> trace,
                                       ModelRouter.ModelRouteDecision routeDecision,
                                       boolean fallback) {
        List<String> citations = extractTraceStrings(trace, "citations");
        List<String> evidence = extractTraceStrings(trace, "evidence");
        return ReactChatResponseVO.builder()
                .ok(1)
                .msg("ok")
                .chatId(chatId)
                .answer(attachCitationFooter(answer, citations))
                .fallback(fallback)
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

    public String formatSse(String event, String data) {
        return "event: " + event + "\ndata: " + data + "\n\n";
    }

    public String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception ex) {
            return "{\"message\":\"serialization_failed\"}";
        }
    }

    public String appendContext(String origin, String action, Object observation) {
        StringBuilder builder = new StringBuilder(emptyIfBlank(origin));
        if (builder.length() > 0) {
            builder.append("\n");
        }
        return builder.append("action=").append(action).append(", observation=").append(toJson(observation)).toString();
    }

    private List<String> extractTraceStrings(List<ReactTraceStepVO> trace, String key) {
        if (trace == null || trace.isEmpty()) {
            return List.of();
        }
        Set<String> values = new LinkedHashSet<>();
        for (ReactTraceStepVO step : trace) {
            if (step == null || !(step.getObservation() instanceof java.util.Map<?, ?> observation)) {
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
        if (citations == null || citations.isEmpty() || safeAnswer.contains("引用来源")) {
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
}
