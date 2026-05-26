package com.enterprise.iqk.agent.harness;

import java.util.Set;

public record ActionSchema(
        String action,
        String runtime,
        Set<String> requiredFields,
        Set<String> optionalFields,
        Set<String> sensitiveFields,
        String riskLevel,
        boolean trustedOnly
) {
    public boolean knowsField(String field) {
        return requiredFields.contains(field) || optionalFields.contains(field);
    }
}
