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
import reactor.core.publisher.Flux;

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
 * Verifies that /ai/chat now routes through TenantCostService so the
 * tenant's monthly budget is actually consumed. Without the tracked
 * helper added to fix bug 7, callers with PERM_CHAT_WRITE could fire
 * unlimited /ai/chat requests and consume LLM tokens without ever
 * being counted.
 */
@WebMvcTest(value = ChatController.class, excludeFilters = {
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = ApiKeyOrJwtAuthFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RateLimitFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = AuditLogFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = HttpMetricsFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RequestContextFilter.class)
})
@AutoConfigureMockMvc(addFilters = false)
class ChatControllerWebMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean(name = "chatClient")
    private ChatClient chatClient;

    @MockBean
    private ModelRouter modelRouter;

    @MockBean
    private TenantCostService tenantCostService;

    @MockBean
    private ChatHistoryRepository chatHistoryRepository;

    @Test
    void chatAssertsBudgetAndRecordsUsage() throws Exception {
        ModelRouter.ModelRouteDecision decision = new ModelRouter.ModelRouteDecision(
                "balanced", "qwen-plus", "balanced", false, "ok", "", "", null);
        when(modelRouter.resolve(any(), anyString(), anyString(), anyString())).thenReturn(decision);
        when(tenantCostService.estimateTokens(anyString())).thenReturn(10L);

        ChatClient.ChatClientRequestSpec spec =
                org.mockito.Mockito.mock(ChatClient.ChatClientRequestSpec.class);
        ChatClient.StreamResponseSpec streamResponse =
                org.mockito.Mockito.mock(ChatClient.StreamResponseSpec.class);
        when(chatClient.prompt()).thenReturn(spec);
        when(spec.options(any())).thenReturn(spec);
        when(spec.user(anyString())).thenReturn(spec);
        // advisors() has two overloads; use doReturn to disambiguate.
        org.mockito.Mockito.doReturn(spec).when(spec).advisors(
                org.mockito.ArgumentMatchers.<org.springframework.ai.chat.client.advisor.api.Advisor>any());
        when(spec.stream()).thenReturn(streamResponse);
        when(streamResponse.content()).thenReturn(Flux.just("ok"));

        mockMvc.perform(post("/ai/chat")
                        .param("prompt", "hi")
                        .param("chatId", "chat-1"))
                .andExpect(status().isOk());

        // Cost governance fires for every chat call: assert before send,
        // record exactly once when the stream finishes.
        verify(tenantCostService).assertBudget(eq("public"), anyString(), anyLong(), anyLong());
        verify(tenantCostService, times(1)).recordUsage(eq("public"), anyString(), anyLong(), anyLong(), anyString());
        // chat history recorded.
        verify(chatHistoryRepository).save(eq("chat"), anyString());
    }
}
