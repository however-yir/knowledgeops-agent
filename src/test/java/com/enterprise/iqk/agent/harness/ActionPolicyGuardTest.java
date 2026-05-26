package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.config.properties.AgentHarnessProperties;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class ActionPolicyGuardTest {

    private final ActionPolicyGuard guard = new ActionPolicyGuard(
            new ActionSchemaRegistry(), new AgentHarnessProperties());

    @Test
    void rejectsMissingRequiredFields() {
        AgentAction action = new AgentAction("add_course_reservation",
                Map.of("course", "Java"), "prompt", "tenant", "chat", "balanced", "", "");

        ActionPolicyDecision decision = guard.evaluate(action);

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.code()).isEqualTo("invalid_action_input");
        assertThat(decision.message()).contains("studentName", "contactInfo", "school");
    }

    @Test
    void rejectsTrustedRuntimeActionsWithoutTrustedFlag() {
        AgentAction action = new AgentAction("workspace_read_file",
                Map.of("path", "README.md"), "prompt", "tenant", "chat", "balanced", "", "");

        ActionPolicyDecision decision = guard.evaluate(action);

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.code()).isEqualTo("trusted_runtime_required");
    }

    @Test
    void allowsTrustedRuntimeActionsWithValidInput() {
        AgentAction action = new AgentAction("mcp_call",
                Map.of("server", "demo", "tool", "echo", "arguments", Map.of("text", "hi")),
                "prompt", "tenant", "chat", "balanced", "task-1", "step-1", true);

        ActionPolicyDecision decision = guard.evaluate(action);

        assertThat(decision.allowed()).isTrue();
        assertThat(decision.schema().runtime()).isEqualTo("mcp");
        assertThat(decision.schema().riskLevel()).isEqualTo("external");
    }

    @Test
    void rejectsUnknownFields() {
        AgentAction action = new AgentAction("query_course",
                Map.of("type", "Java", "extra", "x"), "prompt", "tenant", "chat", "balanced", "", "");

        ActionPolicyDecision decision = guard.evaluate(action);

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.message()).contains("unknown field(s): extra");
    }

    @Test
    void rejectsDisabledActionsFromConfiguration() {
        AgentHarnessProperties properties = new AgentHarnessProperties();
        properties.getDisabledActions().add("rag_search");
        ActionPolicyGuard localGuard = new ActionPolicyGuard(new ActionSchemaRegistry(), properties);

        ActionPolicyDecision decision = localGuard.evaluate(new AgentAction("rag_search",
                Map.of("query", "x"), "prompt", "tenant", "chat", "balanced", "", ""));

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.code()).isEqualTo("disabled_action");
    }

    @Test
    void rejectsTenantDeniedActionsFromConfiguration() {
        AgentHarnessProperties properties = new AgentHarnessProperties();
        properties.getTenantAllowedActions().put("tenant-a", java.util.Set.of("query_school"));
        ActionPolicyGuard localGuard = new ActionPolicyGuard(new ActionSchemaRegistry(), properties);

        ActionPolicyDecision decision = localGuard.evaluate(new AgentAction("rag_search",
                Map.of("query", "x"), "prompt", "tenant-a", "chat", "balanced", "", ""));

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.code()).isEqualTo("tenant_action_denied");
    }
}
