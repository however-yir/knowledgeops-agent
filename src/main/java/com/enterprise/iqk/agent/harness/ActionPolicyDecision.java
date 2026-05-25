package com.enterprise.iqk.agent.harness;

public record ActionPolicyDecision(
        boolean allowed,
        String code,
        String message,
        ActionSchema schema
) {
    public static ActionPolicyDecision allow(ActionSchema schema) {
        return new ActionPolicyDecision(true, "allowed", "", schema);
    }

    public static ActionPolicyDecision deny(String code, String message) {
        return new ActionPolicyDecision(false, code, message, null);
    }
}
