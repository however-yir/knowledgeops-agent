package com.enterprise.iqk.agent.harness;

import java.util.Map;

public interface McpToolAdapter {
    String server();

    String tool();

    default boolean supports(String server, String tool) {
        return server().equals(server) && tool().equals(tool);
    }

    default Object execute(String server, String tool, Map<String, Object> arguments) {
        return execute(arguments);
    }

    Object execute(Map<String, Object> arguments);
}
