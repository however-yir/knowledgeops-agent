package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.agent.workflow.AgentWorkflowEngine;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class HarnessEventRecorderTest {

    @Test
    @SuppressWarnings("unchecked")
    void recordsSanitizedActionInputAndObservationSummary() {
        AgentWorkflowEngine workflowEngine = mock(AgentWorkflowEngine.class);
        HarnessEventRecorder recorder = new HarnessEventRecorder(
                workflowEngine,
                new ActionSchemaRegistry(),
                new HarnessPayloadSanitizer()
        );
        AgentAction action = new AgentAction("add_course_reservation",
                Map.of("course", "Java", "studentName", "A", "contactInfo", "13800000000", "school", "S"),
                "prompt", "tenant", "chat", "balanced", "task-1", "step-1");
        AgentObservation observation = AgentObservation.success("builtin",
                Map.of("status", "created", "reservationId", "r-1"), 9);

        recorder.started(action, "builtin");
        recorder.completed(action, observation);

        ArgumentCaptor<Map<String, Object>> started = ArgumentCaptor.forClass(Map.class);
        ArgumentCaptor<Map<String, Object>> completed = ArgumentCaptor.forClass(Map.class);
        verify(workflowEngine).emitEvent(eq("task-1"), eq("step-1"), eq("ACTION_STARTED"), started.capture());
        verify(workflowEngine).emitEvent(eq("task-1"), eq("step-1"), eq("ACTION_COMPLETED"), completed.capture());

        assertThat((Map<String, Object>) started.getValue().get("actionInput"))
                .containsEntry("contactInfo", "[REDACTED]");
        assertThat((Map<String, Object>) completed.getValue().get("observation"))
                .containsEntry("source", "builtin")
                .containsEntry("latencyMs", 9L);
    }
}
