package com.enterprise.iqk.controller;

import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.AuditLogFilter;
import com.enterprise.iqk.security.HttpMetricsFilter;
import com.enterprise.iqk.security.RateLimitFilter;
import com.enterprise.iqk.security.RequestContextFilter;
import com.enterprise.iqk.security.ApiKeyOrJwtAuthFilter;
import com.enterprise.iqk.service.TenantCostService;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Verifies that /ai/service now routes through TenantCostService so the
 * synchronous customer-service endpoint counts the same as the streaming
 * ReAct endpoints.
 */
@WebMvcTest(value = CustomerServiceController.class, excludeFilters = {
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = ApiKeyOrJwtAuthFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RateLimitFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = AuditLogFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = HttpMetricsFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RequestContextFilter.class)
})
@AutoConfigureMockMvc(addFilters = false)
class CustomerServiceControllerWebMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean(name = "serviceChatClient")
    private ChatClient serviceChatClient;

    @MockBean
    private ModelRouter modelRouter;

    @MockBean
    private TenantCostService tenantCostService;

    @MockBean
    private ChatHistoryRepository chatHistoryRepository;

    @Test
    void serviceAssertsBudgetAndRecordsUsage() throws Exception {
        ModelRouter.ModelRouteDecision decision = new ModelRouter.ModelRouteDecision(
                "balanced", "qwen-plus", "balanced", false, "ok", "", "", null);
        when(modelRouter.resolve(any(), anyString(), anyString(), anyString())).thenReturn(decision);
        when(tenantCostService.estimateTokens(anyString())).thenReturn(10L);

        ChatClient.ChatClientRequestSpec spec =
                org.mockito.Mockito.mock(ChatClient.ChatClientRequestSpec.class);
        ChatClient.CallResponseSpec callResponse =
                org.mockito.Mockito.mock(ChatClient.CallResponseSpec.class);
        when(serviceChatClient.prompt()).thenReturn(spec);
        when(spec.options(any())).thenReturn(spec);
        when(spec.user(anyString())).thenReturn(spec);
        org.mockito.Mockito.doReturn(spec).when(spec).advisors(
                org.mockito.ArgumentMatchers.<org.springframework.ai.chat.client.advisor.api.Advisor>any());
        when(spec.call()).thenReturn(callResponse);
        when(callResponse.content()).thenReturn("ok");

        mockMvc.perform(post("/ai/service")
                        .param("prompt", "hi")
                        .param("chatId", "chat-1"))
                .andExpect(status().isOk());

        verify(tenantCostService).assertBudget(eq("public"), anyString(), anyLong(), anyLong());
        verify(tenantCostService, times(1)).recordUsage(eq("public"), anyString(), anyLong(), anyLong(), anyString());
        verify(chatHistoryRepository).save(eq("service"), anyString());
    }
}
