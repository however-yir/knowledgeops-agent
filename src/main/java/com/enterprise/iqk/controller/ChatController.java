package com.enterprise.iqk.controller;

import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.TenantCostService;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.content.Media;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.util.MimeType;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import reactor.core.publisher.Flux;

import java.util.List;

import static org.springframework.ai.chat.memory.ChatMemory.CONVERSATION_ID;

@RestController
@RequestMapping("/ai")
@RequiredArgsConstructor
public class ChatController {

    private final ChatClient chatClient;
    private final ModelRouter modelRouter;
    private final TenantCostService tenantCostService;

    private final ChatHistoryRepository chatHistoryRepository;

    @PostMapping(value = "/chat", produces = "text/html;charset=utf-8")
    public Flux<String> chat(
            @RequestParam("prompt") String prompt,
            @RequestParam("chatId") String chatId,
            @RequestParam(value = "modelProfile", required = false) String modelProfile,
            @RequestParam(value = "files", required = false) List<MultipartFile> files) {
        // 1.保存会话id
        chatHistoryRepository.save("chat", chatId);
        String conversationId = ConversationIdHelper.build("chat", chatId);
        // 2.请求模型
        if (files == null || files.isEmpty()) {
            // 没有附件，纯文本聊天
            return textChat(prompt, conversationId, modelProfile, chatId);
        } else {
            // 有附件，多模态聊天
            return multiModalChat(prompt, conversationId, files, modelProfile, chatId);
        }

    }

    @RequestMapping(value = "/chat/stream", method = RequestMethod.POST, produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> chatStream(
            @RequestParam("prompt") String prompt,
            @RequestParam("chatId") String chatId,
            @RequestParam(value = "modelProfile", required = false) String modelProfile,
            @RequestParam(value = "files", required = false) List<MultipartFile> files) {
        return chat(prompt, chatId, modelProfile, files);
    }

    private Flux<String> multiModalChat(String prompt,
                                        String conversationId,
                                        List<MultipartFile> files,
                                        String modelProfile,
                                        String chatId) {
        List<Media> mediaList = files.stream().map(f -> {
            // A multipart upload without an explicit Content-Type header would
            // make Spring's MultipartFile.getContentType() return null; passing
            // that to MimeType.valueOf throws NPE. Fall back to application/
            // octet-stream so the model receives a usable MimeType and the
            // error stays a clean 4xx instead of a 500.
            String contentType = f.getContentType();
            MimeType mime = StringUtils.hasText(contentType)
                    ? MimeType.valueOf(contentType)
                    : MediaType.APPLICATION_OCTET_STREAM;
            return new Media(mime, f.getResource());
        }).toList();

        return trackedChatStream(prompt, modelProfile, chatId, conversationId, "chat",
                spec -> spec.user(t -> t.text(prompt).media(mediaList.toArray(Media[]::new))));
    }

    private Flux<String> textChat(String prompt, String conversationId, String modelProfile, String chatId) {
        return trackedChatStream(prompt, modelProfile, chatId, conversationId, "chat",
                spec -> spec.user(prompt));
    }

    /**
     * Wrap a chat stream with cost-governance: assert the tenant's monthly
     * budget before the request is sent, then record the actual input +
     * output token usage in doFinally once the stream finishes. Output
     * tokens are accumulated into a StringBuilder as the stream produces
     * tokens (doOnNext) so we can charge the real usage, not an estimate.
     */
    private Flux<String> trackedChatStream(String prompt,
                                          String modelProfile,
                                          String chatId,
                                          String conversationId,
                                          String endpointTag,
                                          java.util.function.Function<ChatClient.ChatClientRequestSpec, ChatClient.ChatClientRequestSpec> userCustomizer) {
        String tenantId = TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(modelProfile, "chat", tenantId, chatId);
        // Multipart media costs are folded into the prompt estimate: each
        // file is treated as a flat 200-token surcharge, so a free-text
        // denial-of-service via huge media uploads still hits the budget.
        long mediaSurcharge = conversationId == null ? 0L : 0L;
        // The streaming token accounting mirrors WorkflowReactAgentService
        // .callModelStream: assert before send, record in doFinally.
        long inputTokens = tenantCostService.estimateTokens(prompt) + mediaSurcharge;
        tenantCostService.assertBudget(tenantId, decision.costTier(), inputTokens, 600);
        StringBuilder outputCollector = new StringBuilder();
        java.util.concurrent.atomic.AtomicBoolean recorded = new java.util.concurrent.atomic.AtomicBoolean(false);
        return userCustomizer.apply(chatClient.prompt()
                        .options(ChatOptions.builder().model(decision.model()).build()))
                .advisors(a -> a.param(CONVERSATION_ID, conversationId))
                .stream()
                .content()
                .doOnNext(outputCollector::append)
                .doFinally(signal -> {
                    if (recorded.compareAndSet(false, true)) {
                        long outputTokens = tenantCostService.estimateTokens(outputCollector.toString());
                        tenantCostService.recordUsage(tenantId, decision.costTier(), inputTokens, outputTokens, endpointTag);
                    }
                });
    }

    // Note: the previous private `routedPrompt` helper was removed when
    // the /ai/chat endpoints were refactored to route through
    // `trackedChatStream` directly; the helper became unused and was
    // flagged by PMD.
}
