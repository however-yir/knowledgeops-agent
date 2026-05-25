package com.enterprise.iqk.agent.harness;

import org.springframework.util.StringUtils;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public record AgentAction(
        String action,
        Map<String, Object> actionInput,
        String prompt,
        String tenantId,
        String chatId,
        String modelProfile,
        String taskId,
        String stepId,
        boolean trustedRuntimeAccess
) {
    public AgentAction(String action,
                       Map<String, Object> actionInput,
                       String prompt,
                       String tenantId,
                       String chatId,
                       String modelProfile,
                       String taskId,
                       String stepId) {
        this(action, actionInput, prompt, tenantId, chatId, modelProfile, taskId, stepId, false);
    }

    public AgentAction {
        action = normalize(action);
        actionInput = actionInput == null
                ? Collections.emptyMap()
                : Collections.unmodifiableMap(new LinkedHashMap<>(actionInput));
        prompt = emptyIfBlank(prompt);
        tenantId = emptyIfBlank(tenantId);
        chatId = emptyIfBlank(chatId);
        modelProfile = emptyIfBlank(modelProfile);
        taskId = emptyIfBlank(taskId);
        stepId = emptyIfBlank(stepId);
    }

    private static String normalize(String value) {
        if (!StringUtils.hasText(value)) {
            return "finish";
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }

    private static String emptyIfBlank(String value) {
        return StringUtils.hasText(value) ? value : "";
    }
}
