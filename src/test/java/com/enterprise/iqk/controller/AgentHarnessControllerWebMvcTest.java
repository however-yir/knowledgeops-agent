package com.enterprise.iqk.controller;

import com.enterprise.iqk.agent.harness.ActionSchema;
import com.enterprise.iqk.agent.harness.ActionSchemaRegistry;
import com.enterprise.iqk.agent.harness.AgentObservation;
import com.enterprise.iqk.agent.harness.TrustedActionPreviewResponse;
import com.enterprise.iqk.agent.harness.TrustedActionService;
import com.enterprise.iqk.security.ApiKeyOrJwtAuthFilter;
import com.enterprise.iqk.security.AuditLogFilter;
import com.enterprise.iqk.security.HttpMetricsFilter;
import com.enterprise.iqk.security.RateLimitFilter;
import com.enterprise.iqk.security.RequestContextFilter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(value = AgentHarnessController.class, excludeFilters = {
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = ApiKeyOrJwtAuthFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RateLimitFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = AuditLogFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = HttpMetricsFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RequestContextFilter.class)
})
@AutoConfigureMockMvc(addFilters = false)
class AgentHarnessControllerWebMvcTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private TrustedActionService trustedActionService;

    @MockBean
    private ActionSchemaRegistry actionSchemaRegistry;

    @Test
    void previewsAndExecutesTrustedAction() throws Exception {
        when(trustedActionService.preview(any())).thenReturn(new TrustedActionPreviewResponse(
                1,
                "ta-1",
                "workspace_apply_patch",
                Instant.parse("2026-05-25T00:00:00Z"),
                Map.of("status", "pending_confirmation")
        ));
        when(trustedActionService.execute("ta-1"))
                .thenReturn(AgentObservation.success("workspace", Map.of("status", "written"), 1));

        mockMvc.perform(post("/ai/harness/actions/preview")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "action": "workspace_apply_patch",
                                  "actionInput": {"path": "README.md", "content": "next"}
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(1))
                .andExpect(jsonPath("$.token").value("ta-1"));

        mockMvc.perform(post("/ai/harness/actions/execute/ta-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("written"))
                .andExpect(jsonPath("$.source").value("workspace"));
    }

    @Test
    void listsRegisteredActions() throws Exception {
        when(actionSchemaRegistry.list()).thenReturn(List.of(new ActionSchema(
                "workspace_read_file",
                "workspace",
                Set.of("path"),
                Set.of("maxBytes"),
                Set.of(),
                "read",
                true
        )));

        mockMvc.perform(get("/ai/harness/actions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("workspace_read_file"))
                .andExpect(jsonPath("$[0].riskLevel").value("read"))
                .andExpect(jsonPath("$[0].trustedOnly").value(true));
    }
}
