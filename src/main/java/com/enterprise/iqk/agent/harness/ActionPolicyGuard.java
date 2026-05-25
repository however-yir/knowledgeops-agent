package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.config.properties.AgentHarnessProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Component
@RequiredArgsConstructor
public class ActionPolicyGuard {
    private final ActionSchemaRegistry schemaRegistry;
    private final AgentHarnessProperties harnessProperties;

    public boolean isAllowed(AgentAction action) {
        return evaluate(action).allowed();
    }

    public ActionPolicyDecision evaluate(AgentAction action) {
        if (action == null) {
            return ActionPolicyDecision.deny("missing_action", "action is required");
        }
        ActionSchema schema = schemaRegistry.find(action.action()).orElse(null);
        if (schema == null) {
            return ActionPolicyDecision.deny("unsupported_action", "unsupported action: " + action.action());
        }
        if (harnessProperties.getDisabledActions().contains(action.action())) {
            return ActionPolicyDecision.deny("disabled_action", "action is disabled: " + action.action());
        }
        List<String> tenantAllowed = tenantAllowedActions(action.tenantId());
        if (!tenantAllowed.isEmpty() && !tenantAllowed.contains(action.action())) {
            return ActionPolicyDecision.deny("tenant_action_denied",
                    "action is not allowed for tenant: " + action.action());
        }
        if (schema.trustedOnly() && !action.trustedRuntimeAccess()) {
            return ActionPolicyDecision.deny("trusted_runtime_required",
                    "action requires trusted runtime access: " + action.action());
        }
        if (schema.trustedOnly() && !harnessProperties.isTrustedRuntimeEnabled()) {
            return ActionPolicyDecision.deny("trusted_runtime_disabled",
                    "trusted runtime is disabled");
        }
        List<String> missing = missingRequiredFields(schema, action.actionInput());
        if (!missing.isEmpty()) {
            return ActionPolicyDecision.deny("invalid_action_input",
                    "missing required field(s): " + String.join(", ", missing));
        }
        if (requiresPatchPayload(action.action()) && !hasValue(action.actionInput().get("content"))
                && !hasValue(action.actionInput().get("patch"))) {
            return ActionPolicyDecision.deny("invalid_action_input",
                    "missing required field: content or patch");
        }
        List<String> unknown = unknownFields(schema, action.actionInput());
        if (!unknown.isEmpty()) {
            return ActionPolicyDecision.deny("invalid_action_input",
                    "unknown field(s): " + String.join(", ", unknown));
        }
        return ActionPolicyDecision.allow(schema);
    }

    private List<String> missingRequiredFields(ActionSchema schema, Map<String, Object> input) {
        List<String> missing = new ArrayList<>();
        for (String field : schema.requiredFields()) {
            if (!hasValue(input.get(field))) {
                missing.add(field);
            }
        }
        return missing;
    }

    private List<String> unknownFields(ActionSchema schema, Map<String, Object> input) {
        List<String> unknown = new ArrayList<>();
        for (String field : input.keySet()) {
            if (!schema.knowsField(field)) {
                unknown.add(field);
            }
        }
        return unknown;
    }

    private boolean hasValue(Object value) {
        if (value == null) {
            return false;
        }
        if (value instanceof String text) {
            return StringUtils.hasText(text);
        }
        return true;
    }

    private List<String> tenantAllowedActions(String tenantId) {
        if (!StringUtils.hasText(tenantId)) {
            return List.of();
        }
        return new ArrayList<>(harnessProperties.getTenantAllowedActions().getOrDefault(tenantId, Set.of()));
    }

    private boolean requiresPatchPayload(String action) {
        return "workspace_propose_patch".equals(action) || "workspace_apply_patch".equals(action);
    }
}
