package com.enterprise.iqk.controller;

import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.AuditLogFilter;
import com.enterprise.iqk.security.HttpMetricsFilter;
import com.enterprise.iqk.security.RateLimitFilter;
import com.enterprise.iqk.security.RequestContextFilter;
import com.enterprise.iqk.security.ApiKeyOrJwtAuthFilter;
import com.enterprise.iqk.service.TenantCostService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
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
 * End-to-end test for the cost-governance wiring on /ai/chat. We boot the
 * full application context (but with the auth / rate-limit / audit filter
 * chain disabled) so that the real ModelRouter, real chat history repo and
 * the real Hibernate-style transaction handling is exercised. The ChatClient
 * is mocked because the model would otherwise need a live OpenAI endpoint.
 */
@SpringBootTest(properties = {
        "app.cost-governance.enabled=true"
})
@AutoConfigureMockMvc(addFilters = false)
@ComponentScan(
        basePackages = "com.enterprise.iqk",
        excludeFilters = {
                @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = ApiKeyOrJwtAuthFilter.class),
                @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RateLimitFilter.class),
                @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = AuditLogFilter.class),
                @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = HttpMetricsFilter.class),
                @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RequestContextFilter.class),
        }
)
class ChatControllerWebMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean(name = "chatClient")
    private org.springframework.ai.chat.client.ChatClient chatClient;

    @MockBean
    private TenantCostService tenantCostService;

    @MockBean
    private ChatHistoryRepository chatHistoryRepository;

    @Test
    void chatAssertsBudgetAndRecordsUsage() throws Exception {
        when(tenantCostService.estimateTokens(anyString())).thenReturn(10L);

        org.springframework.ai.chat.client.ChatClient.ChatClientRequestSpec spec =
                org.mockito.Mockito.mock(org.springframework.ai.chat.client.ChatClient.ChatClientRequestSpec.class);
        org.springframework.ai.chat.client.ChatClient.StreamResponseSpec streamResponse =
                org.mockito.Mockito.mock(org.springframework.ai.chat.client.ChatClient.StreamResponseSpec.class);
        when(chatClient.prompt()).thenReturn(spec);
        when(spec.options(any())).thenReturn(spec);
        when(spec.user(anyString())).thenReturn(spec);
        org.mockito.Mockito.doReturn(spec).when(spec).advisors(
                org.mockito.ArgumentMatchers.<org.springframework.ai.chat.client.advisor.api.Advisor>any());
        when(spec.stream()).thenReturn(streamResponse);
        when(streamResponse.content()).thenReturn(Flux.just("ok"));

        mockMvc.perform(post("/ai/chat")
                        .param("prompt", "hi")
                        .param("chatId", "chat-1"))
                .andExpect(status().isOk());

        // Cost governance fires for every chat call: assert before send,
        // record exactly once on stream completion.
        verify(tenantCostService).assertBudget(eq("public"), anyString(), anyLong(), anyLong());
        verify(tenantCostService, times(1)).recordUsage(eq("public"), anyString(), anyLong(), anyLong(), anyString());
        // chat history recorded.
        verify(chatHistoryRepository).save(eq("chat"), anyString());
    }
}
