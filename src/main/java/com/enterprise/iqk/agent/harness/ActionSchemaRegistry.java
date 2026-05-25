package com.enterprise.iqk.agent.harness;

import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

@Component
public class ActionSchemaRegistry {
    private final Map<String, ActionSchema> schemas = new LinkedHashMap<>();

    public ActionSchemaRegistry() {
        register(new ActionSchema("query_school", "builtin",
                Set.of(), Set.of(), Set.of(), false));
        register(new ActionSchema("query_course", "builtin",
                Set.of(), Set.of("type", "edu", "sorts"), Set.of(), false));
        register(new ActionSchema("add_course_reservation", "builtin",
                Set.of("course", "studentName", "contactInfo", "school"),
                Set.of("remark"), Set.of("contactInfo"), false));
        register(new ActionSchema("rag_search", "builtin",
                Set.of(), Set.of("query"), Set.of(), false));

        register(new ActionSchema("mcp_call", "mcp",
                Set.of("server", "tool", "arguments"), Set.of(),
                Set.of("arguments"), true));

        register(new ActionSchema("workspace_list_files", "workspace",
                Set.of(), Set.of("path", "maxDepth"), Set.of(), true));
        register(new ActionSchema("workspace_read_file", "workspace",
                Set.of("path"), Set.of("maxBytes"), Set.of(), true));
        register(new ActionSchema("workspace_search_text", "workspace",
                Set.of("query"), Set.of("path", "maxMatches"), Set.of(), true));
        register(new ActionSchema("workspace_propose_patch", "workspace",
                Set.of("path"), Set.of("content", "patch", "summary"), Set.of("content", "patch"), true));
        register(new ActionSchema("workspace_apply_patch", "workspace",
                Set.of("path"), Set.of("content", "patch", "summary"), Set.of("content", "patch"), true));
        register(new ActionSchema("workspace_run_shell", "workspace",
                Set.of("command"), Set.of("timeoutSeconds"), Set.of("command"), true));
    }

    public Optional<ActionSchema> find(String action) {
        return Optional.ofNullable(schemas.get(action));
    }

    public Set<String> actions() {
        return Set.copyOf(schemas.keySet());
    }

    private void register(ActionSchema schema) {
        schemas.put(schema.action(), schema);
    }
}
