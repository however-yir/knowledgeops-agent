package com.enterprise.iqk.agent.harness;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

@Component
@RequiredArgsConstructor
public class McpToolRuntime implements AgentRuntime {
    private final List<McpToolAdapter> adapters;

    @Override
    public String source() {
        return "mcp";
    }

    @Override
    public boolean supports(String action) {
        return "mcp_call".equals(action);
    }

    @Override
    public AgentObservation execute(AgentAction action) {
        long startedNs = System.nanoTime();
        String server = stringVal(action.actionInput(), "server");
        String tool = stringVal(action.actionInput(), "tool");
        Map<String, Object> arguments = mapVal(action.actionInput().get("arguments"));
        McpToolAdapter adapter = adapters.stream()
                .filter(candidate -> candidate.supports(server, tool))
                .findFirst()
                .orElse(null);
        if (adapter == null) {
            return AgentObservation.error(source(),
                    "mcp tool is not registered: " + server + "/" + tool,
                    elapsedMs(startedNs));
        }
        Object result = adapter.execute(server, tool, arguments);
        if (result instanceof Map<?, ?> resultMap && "error".equals(resultMap.get("status"))) {
            Object message = resultMap.get("message");
            return AgentObservation.error(source(),
                    message == null ? "mcp tool failed" : String.valueOf(message),
                    elapsedMs(startedNs));
        }
        return AgentObservation.success(source(), Map.of(
                "server", server,
                "tool", tool,
                "result", result
        ), elapsedMs(startedNs));
    }

    private Map<String, Object> mapVal(Object raw) {
        if (!(raw instanceof Map<?, ?> map)) {
            return Map.of();
        }
        java.util.LinkedHashMap<String, Object> result = new java.util.LinkedHashMap<>();
        map.forEach((key, value) -> result.put(String.valueOf(key), value));
        return result;
    }

    private String stringVal(Map<String, Object> input, String key) {
        Object raw = input.get(key);
        return raw == null ? "" : String.valueOf(raw).trim();
    }

    private long elapsedMs(long startedNs) {
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNs);
    }
}
