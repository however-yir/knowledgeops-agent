package com.enterprise.iqk.agent.harness;

import java.time.Instant;
import java.util.Map;

public record TrustedActionPreviewResponse(
        int ok,
        String token,
        String action,
        Instant expiresAt,
        Map<String, Object> preview
) {
}
