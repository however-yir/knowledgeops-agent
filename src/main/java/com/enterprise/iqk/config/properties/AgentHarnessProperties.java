package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

@Data
@ConfigurationProperties(prefix = "app.agent-harness")
public class AgentHarnessProperties {
    private boolean trustedRuntimeEnabled = true;
    private Set<String> disabledActions = new LinkedHashSet<>();
    private Map<String, Set<String>> tenantAllowedActions = new LinkedHashMap<>();
    private Workspace workspace = new Workspace();
    private Mcp mcp = new Mcp();

    @Data
    public static class Workspace {
        private String root = ".";
        private boolean writeEnabled = false;
        private boolean shellEnabled = false;
        private int commandTimeoutSeconds = 10;
        private int maxCommandOutputBytes = 12_000;
        private int maxFileBytes = 20_000;
        private int maxSearchFiles = 1_000;
        private Set<String> allowedCommands = new LinkedHashSet<>(Set.of("pwd", "ls", "rg", "git", "mvn"));
        private Set<String> allowedGitSubcommands = new LinkedHashSet<>(
                Set.of("status", "diff", "show", "log", "rev-parse", "branch"));
    }

    @Data
    public static class Mcp {
        private Map<String, McpServer> servers = new LinkedHashMap<>();
    }

    @Data
    public static class McpServer {
        private boolean enabled = true;
        private String baseUrl = "";
        private Map<String, McpTool> tools = new LinkedHashMap<>();
    }

    @Data
    public static class McpTool {
        private boolean enabled = true;
        private String path = "/mcp/tools/call";
        private int timeoutMs = 5_000;
    }
}
