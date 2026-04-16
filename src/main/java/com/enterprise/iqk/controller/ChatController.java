package com.enterprise.iqk.controller;

import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.model.Media;
import org.slf4j.MDC;
import org.springframework.util.MimeType;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Objects;

import static org.springframework.ai.chat.client.advisor.AbstractChatMemoryAdvisor.CHAT_MEMORY_CONVERSATION_ID_KEY;

@RestController
@RequestMapping("/ai")
@RequiredArgsConstructor
public class ChatController {

    private final ChatClient chatClient;
    private final ModelRouter modelRouter;

    private final ChatHistoryRepository chatHistoryRepository;

//    @RequestMapping(value = "/chat", produces = "text/html;charset=UTF-8")
//    @SneakyThrows
//    public Flux<String> chat(String prompt,String chatId){
//        //        String content = chatClient
////                .prompt(prompt)
////                .call()//同步调用，就是等他全部执行完，才返回结果
////                .content();
////        return content;
//        chatHistoryRepository.save("chat",chatId);
//        return chatClient
//                .prompt(prompt)
//                .advisors(a -> a.param(CHAT_MEMORY_CONVERSATION_ID_KEY, chatId))
//                .stream()
//                .content();
//    }
    @RequestMapping(value = "/chat", produces = "text/html;charset=utf-8")
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

    private Flux<String> multiModalChat(String prompt,
                                        String conversationId,
                                        List<MultipartFile> files,
                                        String modelProfile,
                                        String chatId) {
        List<Media> mediaList = files.stream().map(f -> {
            return new Media(MimeType.valueOf(Objects.requireNonNull(f.getContentType())), f.getResource());
        }).toList();

        return routedPrompt(modelProfile, "chat", chatId)
                .user(t->t.text(prompt).media(mediaList.toArray(Media[]::new)))
                .advisors(a -> a.param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId))
                .stream()
                .content();
    }

    private Flux<String> textChat(String prompt, String conversationId, String modelProfile, String chatId) {
        return routedPrompt(modelProfile, "chat", chatId)
                .user(prompt)
                .advisors(a -> a.param(CHAT_MEMORY_CONVERSATION_ID_KEY, conversationId))
                .stream()
                .content();
    }

    private ChatClient.ChatClientRequestSpec routedPrompt(String requestedProfile, String endpoint, String subjectKey) {
        String tenantId = TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(requestedProfile, endpoint, tenantId, subjectKey);
        return chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build());
    }
}
