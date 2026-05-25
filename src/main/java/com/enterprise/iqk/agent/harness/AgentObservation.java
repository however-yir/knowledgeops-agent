package com.enterprise.iqk.agent.harness;

import org.springframework.util.StringUtils;

import java.util.LinkedHashMap;
import java.util.Map;

public record AgentObservation(
        String status,
        String source,
        Object payload,
        String errorMessage,
        long latencyMs
) {
    public AgentObservation {
        status = StringUtils.hasText(status) ? status : "success";
        source = StringUtils.hasText(source) ? source : "unknown";
        payload = payload == null ? Map.of() : payload;
        errorMessage = StringUtils.hasText(errorMessage) ? errorMessage : "";
        latencyMs = Math.max(0, latencyMs);
    }

    public static AgentObservation success(String source, Object payload, long latencyMs) {
        return new AgentObservation("success", source, payload, "", latencyMs);
    }

    public static AgentObservation error(String source, String errorMessage, long latencyMs) {
        return new AgentObservation("error", source, Map.of(), errorMessage, latencyMs);
    }

    public boolean successful() {
        return !"error".equals(status);
    }

    public Map<String, Object> toMap() {
        Map<String, Object> result = new LinkedHashMap<>();
        if (payload instanceof Map<?, ?> mapPayload) {
            Object payloadStatus = mapPayload.get("status");
            result.put("status", payloadStatus == null ? status : payloadStatus);
            mapPayload.forEach((key, value) -> {
                if (key != null && !"status".equals(String.valueOf(key))) {
                    result.put(String.valueOf(key), value);
                }
            });
        } else {
            result.put("status", status);
            result.put("data", payload);
        }
        result.put("source", source);
        result.put("latencyMs", latencyMs);
        if (StringUtils.hasText(errorMessage)) {
            result.put("message", errorMessage);
        }
        return result;
    }
}
