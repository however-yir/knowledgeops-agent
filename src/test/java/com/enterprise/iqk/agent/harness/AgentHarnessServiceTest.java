package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.config.properties.AgentHarnessProperties;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class AgentHarnessServiceTest {

    @Test
    void executeRoutesAllowedActionToRuntime() {
        HarnessEventRecorder recorder = mock(HarnessEventRecorder.class);
        AgentRuntime runtime = new AgentRuntime() {
            @Override
            public String source() {
                return "fake";
            }

            @Override
            public boolean supports(String action) {
                return "query_school".equals(action);
            }

            @Override
            public AgentObservation execute(AgentAction action) {
                return AgentObservation.success(source(), Map.of("result", "ok"), 5);
            }
        };
        AgentHarnessService service = new AgentHarnessService(
                List.of(runtime),
                new ActionPolicyGuard(new ActionSchemaRegistry(), new AgentHarnessProperties()),
                recorder,
                new HarnessPayloadSanitizer()
        );
        AgentAction action = new AgentAction("query_school", Map.of(), "prompt",
                "tenant", "chat", "balanced", "task-1", "step-1");

        AgentObservation observation = service.execute(action);

        assertThat(observation.toMap()).containsEntry("result", "ok");
        verify(recorder).started(action, "fake");
        verify(recorder).completed(action, observation);
        verifyNoMoreInteractions(recorder);
    }

    @Test
    void executeRejectsUnsupportedActionBeforeRuntime() {
        HarnessEventRecorder recorder = mock(HarnessEventRecorder.class);
        AgentRuntime runtime = mock(AgentRuntime.class);
        AgentHarnessService service = new AgentHarnessService(
                List.of(runtime),
                new ActionPolicyGuard(new ActionSchemaRegistry(), new AgentHarnessProperties()),
                recorder,
                new HarnessPayloadSanitizer()
        );
        AgentAction action = new AgentAction("run_shell", Map.of(), "prompt",
                "tenant", "chat", "balanced", "task-1", "step-1");

        AgentObservation observation = service.execute(action);

        assertThat(observation.toMap())
                .containsEntry("status", "error")
                .containsEntry("source", "policy")
                .containsEntry("message", "unsupported action: run_shell");
        verify(recorder).completed(action, observation);
        verifyNoMoreInteractions(recorder, runtime);
    }
}
