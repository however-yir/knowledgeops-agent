package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.config.properties.AgentHarnessProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class HttpMcpToolAdapter implements McpToolAdapter {
    // Allow only public HTTP(S) endpoints for outbound MCP calls. Any
    // RFC1918 / loopback / link-local / cloud-metadata address is refused
    // to prevent an agent invocation of mcp_call from being turned into
    // an SSRF probe against internal services or the host metadata API.
    private static final Set<String> ALLOWED_SCHEMES = Set.of("http", "https");

    private final AgentHarnessProperties harnessProperties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newHttpClient();
    // Cap the MCP HTTP response body so a hostile or compromised MCP
    // server cannot exhaust JVM memory by returning a multi-MB payload.
    // 2 MiB matches the same order of magnitude as the workspace
    // max-file-bytes cap and is generous for typical JSON-RPC responses.
    private static final long MAX_MCP_RESPONSE_BYTES = 2L * 1024L * 1024L;

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
                && isSafeBaseUrl(serverConfig.getBaseUrl(), harnessProperties.getMcp().getAllowedHosts())
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
            HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            byte[] bodyBytes = response.body();
            if (bodyBytes.length > MAX_MCP_RESPONSE_BYTES) {
                return Map.of("status", "error", "message",
                        "mcp response exceeds " + MAX_MCP_RESPONSE_BYTES + " bytes");
            }
            String bodyStr = new String(bodyBytes, java.nio.charset.StandardCharsets.UTF_8);
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                return Map.of("status", "error", "message", "mcp http status: " + response.statusCode());
            }
            return objectMapper.readValue(bodyStr, Object.class);
        } catch (Exception ex) {
            return Map.of("status", "error", "message", "mcp http call failed: " + ex.getMessage());
        }
    }

    @Override
    public Object execute(Map<String, Object> arguments) {
        return Map.of("status", "error", "message", "configured MCP call requires server and tool");
    }

    private URI resolveUri(String baseUrl, String path) {
        if (!isSafeBaseUrl(baseUrl, harnessProperties.getMcp().getAllowedHosts())) {
            throw new IllegalArgumentException("MCP baseUrl is not a permitted public endpoint: " + baseUrl);
        }
        String safeBase = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        String safePath = path.startsWith("/") ? path : "/" + path;
        return URI.create(safeBase + safePath);
    }

    /**
     * Reject baseUrls whose scheme is not http(s) or whose host resolves to a
     * private, loopback, link-local, or cloud-metadata address. Without this,
     * an operator (or an LLM-driven agent invocation of mcp_call) could
     * point the MCP HTTP adapter at e.g. http://169.254.169.254/latest/meta-data/
     * to harvest cloud instance credentials.
     *
     * <p>Operators can opt in to a curated list of host patterns (exact
     * host or suffix match like ".internal.example.com") via
     * {@code app.agent-harness.mcp.allowed-hosts}. Tests and dev
     * environments typically need to set it to {@code ["localhost",
     * "127.0.0.1", "::1"]}.
     */
    static boolean isSafeBaseUrl(String baseUrl, java.util.List<String> allowedHosts) {
        if (!StringUtils.hasText(baseUrl)) {
            return false;
        }
        URI uri;
        try {
            uri = URI.create(baseUrl);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        String scheme = uri.getScheme();
        if (scheme == null || !ALLOWED_SCHEMES.contains(scheme.toLowerCase())) {
            return false;
        }
        String host = uri.getHost();
        if (!StringUtils.hasText(host)) {
            return false;
        }
        if (hostMatchesAllowList(host, allowedHosts)) {
            return true;
        }
        try {
            InetAddress[] addresses = InetAddress.getAllByName(host);
            for (InetAddress addr : addresses) {
                if (addr.isLoopbackAddress() || addr.isAnyLocalAddress()
                        || addr.isLinkLocalAddress() || addr.isSiteLocalAddress()
                        || addr.isMulticastAddress()) {
                    return false;
                }
            }
        } catch (UnknownHostException ex) {
            return false;
        }
        return true;
    }

    private static boolean hostMatchesAllowList(String host, java.util.List<String> allowedHosts) {
        if (allowedHosts == null || allowedHosts.isEmpty()) {
            return false;
        }
        String normalized = host.toLowerCase();
        for (String pattern : allowedHosts) {
            if (!StringUtils.hasText(pattern)) {
                continue;
            }
            String p = pattern.trim().toLowerCase();
            if (p.startsWith(".")) {
                // suffix match: ".internal.example.com" matches "a.internal.example.com"
                if (normalized.endsWith(p)) {
                    return true;
                }
            } else if (p.equals(normalized)) {
                return true;
            }
        }
        return false;
    }
}
