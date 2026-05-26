package com.enterprise.iqk.controller;

import com.enterprise.iqk.agent.harness.ActionSchema;
import com.enterprise.iqk.agent.harness.ActionSchemaRegistry;
import com.enterprise.iqk.agent.harness.AgentObservation;
import com.enterprise.iqk.agent.harness.TrustedActionPreviewResponse;
import com.enterprise.iqk.agent.harness.TrustedActionRequest;
import com.enterprise.iqk.agent.harness.TrustedActionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(name = "Agent Harness", description = "Trusted agent runtime action confirmation")
@RestController
@RequestMapping("/ai/harness")
@RequiredArgsConstructor
public class AgentHarnessController {
    private final TrustedActionService trustedActionService;
    private final ActionSchemaRegistry actionSchemaRegistry;

    @Operation(summary = "List registered agent action schemas")
    @GetMapping("/actions")
    @PreAuthorize("hasAnyAuthority('PERM_AGENT_TRUSTED','ROLE_ADMIN')")
    public ResponseEntity<List<ActionSchema>> actions() {
        return ResponseEntity.ok(actionSchemaRegistry.list());
    }

    @Operation(summary = "Preview a trusted runtime action and create a one-time confirmation token")
    @PostMapping("/actions/preview")
    @PreAuthorize("hasAnyAuthority('PERM_AGENT_TRUSTED','ROLE_ADMIN')")
    public ResponseEntity<TrustedActionPreviewResponse> preview(@RequestBody TrustedActionRequest request) {
        return ResponseEntity.ok(trustedActionService.preview(request));
    }

    @Operation(summary = "Execute a previously previewed trusted runtime action")
    @PostMapping("/actions/execute/{token}")
    @PreAuthorize("hasAnyAuthority('PERM_AGENT_TRUSTED','ROLE_ADMIN')")
    public ResponseEntity<?> execute(@PathVariable String token) {
        AgentObservation observation = trustedActionService.execute(token);
        return ResponseEntity.ok(observation.toMap());
    }
}
