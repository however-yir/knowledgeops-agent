package com.enterprise.iqk.agent.harness;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
@RequiredArgsConstructor
public class TrustedActionService {
    private static final Duration TOKEN_TTL = Duration.ofMinutes(10);

    private final AgentHarnessService harnessService;
    private final ActionSchemaRegistry schemaRegistry;
    private final HarnessPayloadSanitizer payloadSanitizer;
    private final Map<String, PendingTrustedAction> pendingActions = new ConcurrentHashMap<>();

    public TrustedActionPreviewResponse preview(TrustedActionRequest request) {
        AgentAction action = toTrustedAction(request);
        ActionSchema schema = schemaRegistry.find(action.action())
                .orElseThrow(() -> new IllegalArgumentException("unsupported action: " + action.action()));
        if (!schema.trustedOnly()) {
            throw new IllegalArgumentException("action does not require trusted runtime: " + action.action());
        }

        String token = "ta-" + UUID.randomUUID().toString().replace("-", "");
        Instant expiresAt = Instant.now().plus(TOKEN_TTL);
        pendingActions.put(token, new PendingTrustedAction(action, expiresAt));
        return new TrustedActionPreviewResponse(
                1,
                token,
                action.action(),
                expiresAt,
                previewPayload(action, schema)
        );
    }

    public AgentObservation execute(String token) {
        PendingTrustedAction pending = pendingActions.remove(token);
        if (pending == null) {
            return AgentObservation.error("trusted-action", "trusted action token not found", 0);
        }
        if (pending.expiresAt().isBefore(Instant.now())) {
            return AgentObservation.error("trusted-action", "trusted action token expired", 0);
        }
        return harnessService.execute(pending.action());
    }

    private Map<String, Object> previewPayload(AgentAction action, ActionSchema schema) {
        if ("workspace_apply_patch".equals(action.action())) {
            AgentObservation observation = harnessService.execute(new AgentAction(
                    "workspace_propose_patch",
                    action.actionInput(),
                    action.prompt(),
                    action.tenantId(),
                    action.chatId(),
                    action.modelProfile(),
                    action.taskId(),
                    action.stepId(),
                    true
            ));
            return observation.toMap();
        }
        return Map.of(
                "status", "pending_confirmation",
                "source", schema.runtime(),
                "action", action.action(),
                "actionInput", payloadSanitizer.sanitizeActionInput(action, schema)
        );
    }

    private AgentAction toTrustedAction(TrustedActionRequest request) {
        if (request == null || !StringUtils.hasText(request.action())) {
            throw new IllegalArgumentException("action is required");
        }
        return new AgentAction(
                request.action(),
                request.actionInput(),
                request.prompt(),
                request.tenantId(),
                request.chatId(),
                request.modelProfile(),
                request.taskId(),
                request.stepId(),
                true
        );
    }

    private record PendingTrustedAction(AgentAction action, Instant expiresAt) {
    }
}
