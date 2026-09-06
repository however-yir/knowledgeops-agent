package com.enterprise.iqk.controller;


import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.TenantCostService;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.ai.chat.memory.ChatMemory.CONVERSATION_ID;

@RequiredArgsConstructor
@RestController
@RequestMapping("/ai")
public class CustomerServiceController {

    private final ChatClient serviceChatClient;//注意bean的名字已经换成了serviceChatClient
    private final ModelRouter modelRouter;
    private final TenantCostService tenantCostService;

    private final ChatHistoryRepository chatHistoryRepository;

    @PostMapping(value = "/service", produces = "text/html;charset=utf-8")
    public String service(String prompt,
                          String chatId,
                          @RequestParam(value = "modelProfile", required = false) String modelProfile) {
        // 1.保存会话id
        chatHistoryRepository.save("service", chatId);
        String conversationId = ConversationIdHelper.build("service", chatId);
        String tenantId = TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(modelProfile, "service", tenantId, chatId);
        // Cost governance: same pattern as WorkflowReactAgentService.callModel
        // (assert before send, record after) so the synchronous /ai/service
        // endpoint counts the same as the streaming ReAct endpoints.
        long inputTokens = tenantCostService.estimateTokens(prompt);
        tenantCostService.assertBudget(tenantId, decision.costTier(), inputTokens, 600);
        // 2.请求模型
        String answer = serviceChatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build())
                .user(prompt)
                .advisors(a -> a.param(CONVERSATION_ID, conversationId))
                .call()
                .content();
        long outputTokens = tenantCostService.estimateTokens(answer);
        tenantCostService.recordUsage(tenantId, decision.costTier(), inputTokens, outputTokens, "service");
        return answer;
    }
}
