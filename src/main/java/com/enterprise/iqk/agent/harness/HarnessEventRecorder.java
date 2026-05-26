package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.agent.workflow.AgentWorkflowEngine;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Map;

@Component
@RequiredArgsConstructor
public class HarnessEventRecorder {
    private final AgentWorkflowEngine workflowEngine;
    private final ActionSchemaRegistry schemaRegistry;
    private final HarnessPayloadSanitizer payloadSanitizer;

    public void started(AgentAction action, String source) {
        if (!shouldRecord(action)) {
            return;
        }
        ActionSchema schema = schemaRegistry.find(action.action()).orElse(null);
        emit(action, "ACTION_STARTED", Map.of(
                "action", action.action(),
                "source", source,
                "riskLevel", schema == null ? "unknown" : schema.riskLevel(),
                "actionInput", payloadSanitizer.sanitizeActionInput(action, schema)
        ));
    }

    public void completed(AgentAction action, AgentObservation observation) {
        if (!shouldRecord(action)) {
            return;
        }
        emit(action, observation.successful() ? "ACTION_COMPLETED" : "ACTION_FAILED", Map.of(
                "action", action.action(),
                "source", observation.source(),
                "status", observation.status(),
                "latencyMs", observation.latencyMs(),
                "observation", payloadSanitizer.summarizeObservation(observation)
        ));
    }

    private void emit(AgentAction action, String eventType, Map<String, Object> payload) {
        workflowEngine.emitEvent(action.taskId(), action.stepId(), eventType, payload);
    }

    private boolean shouldRecord(AgentAction action) {
        return action != null
                && StringUtils.hasText(action.taskId())
                && StringUtils.hasText(action.stepId());
    }
}
