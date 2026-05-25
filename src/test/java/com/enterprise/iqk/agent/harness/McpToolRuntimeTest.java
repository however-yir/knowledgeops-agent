package com.enterprise.iqk.agent.harness;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class McpToolRuntimeTest {

    @Test
    void executesRegisteredAdapter() {
        McpToolAdapter adapter = new McpToolAdapter() {
            @Override
            public String server() {
                return "demo";
            }

            @Override
            public String tool() {
                return "echo";
            }

            @Override
            public Object execute(Map<String, Object> arguments) {
                return Map.of("echo", arguments.get("text"));
            }
        };
        McpToolRuntime runtime = new McpToolRuntime(List.of(adapter));

        AgentObservation observation = runtime.execute(new AgentAction("mcp_call",
                Map.of("server", "demo", "tool", "echo", "arguments", Map.of("text", "hi")),
                "prompt", "tenant", "chat", "balanced", "task-1", "step-1", true));

        assertThat(observation.toMap())
                .containsEntry("status", "success")
                .containsEntry("source", "mcp")
                .containsEntry("server", "demo")
                .containsEntry("tool", "echo");
        assertThat(observation.toMap().get("result")).isEqualTo(Map.of("echo", "hi"));
    }

    @Test
    void returnsErrorForUnregisteredTool() {
        McpToolRuntime runtime = new McpToolRuntime(List.of());

        AgentObservation observation = runtime.execute(new AgentAction("mcp_call",
                Map.of("server", "demo", "tool", "missing", "arguments", Map.of()),
                "prompt", "tenant", "chat", "balanced", "task-1", "step-1", true));

        assertThat(observation.toMap())
                .containsEntry("status", "error")
                .containsEntry("source", "mcp")
                .containsEntry("message", "mcp tool is not registered: demo/missing");
    }
}
