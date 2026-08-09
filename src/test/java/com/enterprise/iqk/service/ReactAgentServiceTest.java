package com.enterprise.iqk.service;

import com.enterprise.iqk.agent.harness.AgentHarnessService;
import com.enterprise.iqk.domain.vo.ReactChatRequestVO;
import com.enterprise.iqk.llm.ModelRouter;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.client.ChatClient;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ReactAgentServiceTest {

    @Test
    void rejectsRequestsWithoutPromptOrChatIdBeforeCallingExternalDependencies() {
        ReactAgentService service = new ReactAgentService(
                mock(AgentHarnessService.class),
                mock(ChatClient.class),
                mock(ModelRouter.class),
                mock(TenantCostService.class),
                mock(MeterRegistry.class),
                new ReactDecisionParser(new ObjectMapper()),
                new ReactResponseFormatter(new ObjectMapper())
        );
        ReactChatRequestVO missingPrompt = new ReactChatRequestVO();
        missingPrompt.setChatId("chat-1");
        ReactChatRequestVO missingChatId = new ReactChatRequestVO();
        missingChatId.setPrompt("hello");

        assertThatThrownBy(() -> service.chat(missingPrompt))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("prompt is required");
        assertThatThrownBy(() -> service.chat(missingChatId))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("chatId is required");
    }

    @Test
    void marksTheResponseAsFallbackWhenThePlannerModelIsUnavailable() {
        AgentHarnessService harness = mock(AgentHarnessService.class);
        ChatClient chatClient = mock(ChatClient.class);
        ModelRouter modelRouter = mock(ModelRouter.class);
        when(chatClient.prompt()).thenThrow(new IllegalStateException("model unavailable"));
        when(modelRouter.resolve(anyString(), anyString(), anyString(), anyString())).thenReturn(
                new ModelRouter.ModelRouteDecision("quality", "model-a", "premium", false, "profile_match", "", "", null)
        );
        ReactAgentService service = new ReactAgentService(
                harness,
                chatClient,
                modelRouter,
                mock(TenantCostService.class),
                mock(MeterRegistry.class),
                new ReactDecisionParser(new ObjectMapper()),
                new ReactResponseFormatter(new ObjectMapper())
        );
        ReactChatRequestVO request = new ReactChatRequestVO();
        request.setPrompt("高温健康风险有哪些？");
        request.setChatId("chat-1");
        request.setModelProfile("quality");

        assertThat(service.chat(request).getFallback()).isTrue();
        verify(harness, never()).execute(org.mockito.ArgumentMatchers.any());
    }
}
