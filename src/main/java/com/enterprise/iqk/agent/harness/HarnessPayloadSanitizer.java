package com.enterprise.iqk.agent.harness;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Component
public class HarnessPayloadSanitizer {
    private static final int MAX_STRING_LENGTH = 4_000;
    private static final int MAX_EVENT_STRING_LENGTH = 600;
    private static final int MAX_COLLECTION_ITEMS = 30;
    private static final int MAX_MAP_ENTRIES = 60;
    private static final Set<String> SENSITIVE_KEYWORDS = Set.of(
            "password", "secret", "token", "apikey", "api_key", "contactinfo", "authorization"
    );

    public Map<String, Object> sanitizeActionInput(AgentAction action, ActionSchema schema) {
        if (action == null) {
            return Map.of();
        }
        Set<String> schemaSensitive = schema == null ? Set.of() : schema.sensitiveFields();
        Map<String, Object> result = new LinkedHashMap<>();
        action.actionInput().forEach((key, value) -> {
            if (isSensitive(key, schemaSensitive)) {
                result.put(key, "[REDACTED]");
            } else {
                result.put(key, limit(value, MAX_EVENT_STRING_LENGTH));
            }
        });
        return result;
    }

    public Map<String, Object> summarizeObservation(AgentObservation observation) {
        if (observation == null) {
            return Map.of();
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("source", observation.source());
        summary.put("status", observation.status());
        summary.put("latencyMs", observation.latencyMs());
        if (observation.payload() instanceof Map<?, ?> payload) {
            summary.put("payloadKeys", payload.keySet().stream()
                    .map(String::valueOf)
                    .limit(MAX_COLLECTION_ITEMS)
                    .toList());
            Object message = payload.get("message");
            if (message != null) {
                summary.put("message", truncate(String.valueOf(message), MAX_EVENT_STRING_LENGTH));
            }
        }
        if (!observation.errorMessage().isBlank()) {
            summary.put("errorMessage", truncate(observation.errorMessage(), MAX_EVENT_STRING_LENGTH));
        }
        return summary;
    }

    public AgentObservation limitObservation(AgentObservation observation) {
        if (observation == null) {
            return null;
        }
        return new AgentObservation(
                observation.status(),
                observation.source(),
                limit(observation.payload(), MAX_STRING_LENGTH),
                truncate(observation.errorMessage(), MAX_EVENT_STRING_LENGTH),
                observation.latencyMs()
        );
    }

    private Object limit(Object value, int stringLength) {
        if (value instanceof String text) {
            return truncate(text, stringLength);
        }
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            int count = 0;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (count++ >= MAX_MAP_ENTRIES) {
                    result.put("_truncated", true);
                    break;
                }
                result.put(String.valueOf(entry.getKey()), limit(entry.getValue(), stringLength));
            }
            return result;
        }
        if (value instanceof Iterable<?> iterable) {
            List<Object> result = new ArrayList<>();
            int count = 0;
            for (Object item : iterable) {
                if (count++ >= MAX_COLLECTION_ITEMS) {
                    result.add(Map.of("_truncated", true));
                    break;
                }
                result.add(limit(item, stringLength));
            }
            return result;
        }
        return value;
    }

    private boolean isSensitive(String key, Set<String> schemaSensitive) {
        if (schemaSensitive.contains(key)) {
            return true;
        }
        String normalized = key.toLowerCase();
        return SENSITIVE_KEYWORDS.stream().anyMatch(normalized::contains);
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength) + "...[truncated]";
    }
}
