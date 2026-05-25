package com.enterprise.iqk.agent.harness;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TrustedActionServiceTest {

    @Test
    void previewCreatesOneTimeTokenAndExecuteRunsTrustedAction() {
        AgentHarnessService harnessService = mock(AgentHarnessService.class);
        when(harnessService.execute(any())).thenAnswer(invocation -> {
            AgentAction action = invocation.getArgument(0);
            return AgentObservation.success("workspace", Map.of(
                    "action", action.action(),
                    "patch", "--- a/README.md\n+++ b/README.md\n"
            ), 1);
        });
        TrustedActionService service = new TrustedActionService(
                harnessService,
                new ActionSchemaRegistry(),
                new HarnessPayloadSanitizer()
        );

        TrustedActionPreviewResponse preview = service.preview(new TrustedActionRequest(
                "workspace_apply_patch",
                Map.of("path", "README.md", "content", "next"),
                "prompt", "tenant", "chat", "balanced", "task-1", "step-1"));
        AgentObservation executed = service.execute(preview.token());
        AgentObservation secondExecute = service.execute(preview.token());

        assertThat(preview.ok()).isEqualTo(1);
        assertThat(preview.preview()).containsKey("patch");
        assertThat(executed.toMap()).containsEntry("action", "workspace_apply_patch");
        assertThat(secondExecute.toMap())
                .containsEntry("status", "error")
                .containsEntry("message", "trusted action token not found");
        ArgumentCaptor<AgentAction> actionCaptor = ArgumentCaptor.forClass(AgentAction.class);
        verify(harnessService, org.mockito.Mockito.times(2)).execute(actionCaptor.capture());
        assertThat(actionCaptor.getAllValues().get(0).action()).isEqualTo("workspace_propose_patch");
        assertThat(actionCaptor.getAllValues().get(1).trustedRuntimeAccess()).isTrue();
    }

    @Test
    void rejectsPreviewForDefaultRuntimeActions() {
        TrustedActionService service = new TrustedActionService(
                mock(AgentHarnessService.class),
                new ActionSchemaRegistry(),
                new HarnessPayloadSanitizer()
        );

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.preview(new TrustedActionRequest(
                "query_school", Map.of(), "prompt", "tenant", "chat", "balanced", "", "")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("does not require trusted runtime");
    }
}
