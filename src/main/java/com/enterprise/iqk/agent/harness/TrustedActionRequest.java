package com.enterprise.iqk.agent.harness;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public record TrustedActionRequest(
        String action,
        Map<String, Object> actionInput,
        String prompt,
        String tenantId,
        String chatId,
        String modelProfile,
        String taskId,
        String stepId
) {
    public TrustedActionRequest {
        actionInput = actionInput == null
                ? Collections.emptyMap()
                : Collections.unmodifiableMap(new LinkedHashMap<>(actionInput));
    }
}
