package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.config.properties.AgentHarnessProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class HttpMcpToolAdapter implements McpToolAdapter {
    private final AgentHarnessProperties harnessProperties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newHttpClient();

    @Override
    public String server() {
        return "configured-http";
    }

    @Override
    public String tool() {
        return "configured-http";
    }

    @Override
    public boolean supports(String server, String tool) {
        AgentHarnessProperties.McpServer serverConfig = harnessProperties.getMcp().getServers().get(server);
        return serverConfig != null
                && serverConfig.isEnabled()
                && StringUtils.hasText(serverConfig.getBaseUrl())
                && serverConfig.getTools().containsKey(tool)
                && serverConfig.getTools().get(tool).isEnabled();
    }

    @Override
    public Object execute(String server, String tool, Map<String, Object> arguments) {
        try {
            AgentHarnessProperties.McpServer serverConfig = harnessProperties.getMcp().getServers().get(server);
            AgentHarnessProperties.McpTool toolConfig = serverConfig.getTools().get(tool);
            String body = objectMapper.writeValueAsString(Map.of(
                    "jsonrpc", "2.0",
                    "id", UUID.randomUUID().toString(),
                    "method", "tools/call",
                    "params", Map.of("name", tool, "arguments", arguments)
            ));
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(resolveUri(serverConfig.getBaseUrl(), toolConfig.getPath()))
                    .timeout(Duration.ofMillis(Math.max(1, toolConfig.getTimeoutMs())))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return Map.of("status", "error", "message", "mcp http status: " + response.statusCode());
            }
            return objectMapper.readValue(response.body(), Object.class);
        } catch (Exception ex) {
            return Map.of("status", "error", "message", "mcp http call failed: " + ex.getMessage());
        }
    }

    @Override
    public Object execute(Map<String, Object> arguments) {
        return Map.of("status", "error", "message", "configured MCP call requires server and tool");
    }

    private URI resolveUri(String baseUrl, String path) {
        String safeBase = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        String safePath = path.startsWith("/") ? path : "/" + path;
        return URI.create(safeBase + safePath);
    }
}
