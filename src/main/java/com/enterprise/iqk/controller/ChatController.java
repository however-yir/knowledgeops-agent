package com.enterprise.iqk.controller;

import com.enterprise.iqk.llm.ModelRouter;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.prompt.ChatOptions;
import org.springframework.ai.content.Media;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.util.MimeType;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Objects;

import static org.springframework.ai.chat.memory.ChatMemory.CONVERSATION_ID;

/**
 * 通用 AI 聊天接口。
 *
 * <p>该控制器负责接收 HTTP 请求，并完成以下编排：</p>
 * <ol>
 *     <li>登记会话 ID，供历史会话列表使用；</li>
 *     <li>根据业务类型和 chatId 生成隔离后的记忆键；</li>
 *     <li>根据租户、接口和模型档位选择实际模型；</li>
 *     <li>根据是否携带附件，进入纯文本或多模态调用；</li>
 *     <li>通过 {@link Flux} 将模型生成的内容流式返回给客户端。</li>
 * </ol>
 *
 * <p>控制器只负责请求参数接收和流程编排，具体的模型路由、会话记录、
 * 对话记忆等能力由注入的组件负责。</p>
 */
@RestController
@RequestMapping("/ai")
@RequiredArgsConstructor
public class ChatController {

    /** Spring AI 的模型调用客户端，由 Spring 容器注入。 */
    private final ChatClient chatClient;

    /** 根据模型档位、租户和请求场景选择实际模型。 */
    private final ModelRouter modelRouter;

    /** 保存会话索引，便于后续查询聊天历史。 */
    private final ChatHistoryRepository chatHistoryRepository;

    /**
     * 通用聊天入口，同时支持纯文本和附件输入。
     *
     * <p>{@code Flux<String>} 表示返回值不是一次性生成的完整字符串，
     * 而是一段一段异步产生的文本数据。</p>
     *
     * @param prompt 用户输入的问题或指令
     * @param chatId 客户端提供的会话标识，用于区分不同会话
     * @param modelProfile 可选的模型档位，例如 economy、balanced、quality
     * @param files 可选的附件列表；为空时执行纯文本聊天
     * @return 模型生成的文本流
     */
    @RequestMapping(value = "/chat", produces = "text/html;charset=utf-8")
    public Flux<String> chat(
            @RequestParam("prompt") String prompt,
            @RequestParam("chatId") String chatId,
            @RequestParam(value = "modelProfile", required = false) String modelProfile,
            @RequestParam(value = "files", required = false) List<MultipartFile> files) {
        // 保存原始 chatId 对应的会话索引，类型 "chat" 用于区分其他会话业务。
        chatHistoryRepository.save("chat", chatId);

        // 生成对话记忆使用的隔离键，例如将业务类型和 chatId 组合，避免不同入口串会话。
        String conversationId = ConversationIdHelper.build("chat", chatId);

        // 根据附件是否存在选择调用方式；两条分支最终都会以流式方式返回模型内容。
        if (files == null || files.isEmpty()) {
            return textChat(prompt, conversationId, modelProfile, chatId);
        }
        return multiModalChat(prompt, conversationId, files, modelProfile, chatId);
    }

    /**
     * SSE 流式聊天入口。
     *
     * <p>该方法复用 {@link #chat(String, String, String, List)} 的完整处理逻辑，
     * 仅通过 {@code text/event-stream} 明确告诉客户端按 SSE 方式消费响应。</p>
     */
    @RequestMapping(value = "/chat/stream", method = RequestMethod.POST, produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> chatStream(
            @RequestParam("prompt") String prompt,
            @RequestParam("chatId") String chatId,
            @RequestParam(value = "modelProfile", required = false) String modelProfile,
            @RequestParam(value = "files", required = false) List<MultipartFile> files) {
        return chat(prompt, chatId, modelProfile, files);
    }

    /** 构造包含文本和附件的多模态模型请求。 */
    private Flux<String> multiModalChat(String prompt,
                                        String conversationId,
                                        List<MultipartFile> files,
                                        String modelProfile,
                                        String chatId) {
        // 将 Spring MVC 接收到的 MultipartFile 转成 Spring AI 能识别的 Media。
        List<Media> mediaList = files.stream().map(f -> {
            // requireNonNull 会在附件缺少 Content-Type 时立即抛出异常，避免构造无类型媒体。
            return new Media(MimeType.valueOf(Objects.requireNonNull(f.getContentType())), f.getResource());
        }).toList();

        // 先选择模型，再组装用户文本与附件，并把 conversationId 交给对话记忆 Advisor。
        return routedPrompt(modelProfile, "chat", chatId)
                .user(t -> t.text(prompt).media(mediaList.toArray(Media[]::new)))
                .advisors(a -> a.param(CONVERSATION_ID, conversationId))
                .stream()
                .content();
    }

    /** 构造纯文本模型请求。 */
    private Flux<String> textChat(String prompt, String conversationId, String modelProfile, String chatId) {
        return routedPrompt(modelProfile, "chat", chatId)
                .user(prompt)
                // CONVERSATION_ID 是 MessageChatMemoryAdvisor 读取的参数名。
                .advisors(a -> a.param(CONVERSATION_ID, conversationId))
                .stream()
                .content();
    }

    /**
     * 根据租户、业务入口、聊天 ID 和模型档位，选出实际模型，并生成一个还没有发给模型的请求构建器。
     *
     * @param requestedProfile 客户端请求的模型档位
     * @param endpoint 当前业务入口，用于应用端点级路由策略
     * @param subjectKey 路由主体标识；此处使用 chatId，可用于稳定的实验分桶
     * @return 已配置实际模型、但尚未添加用户消息和发起调用的请求对象
     */
    private ChatClient.ChatClientRequestSpec routedPrompt(String requestedProfile, String endpoint, String subjectKey) {
        // 认证过滤器会把租户 ID 放入 MDC；缺失时 normalize 会回退到 public。
        String tenantId = TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));

        // 路由结果中包含最终模型名，以及档位、降级、实验分桶等决策信息。
        ModelRouter.ModelRouteDecision decision = modelRouter.resolve(requestedProfile, endpoint, tenantId, subjectKey);

        // prompt() 创建请求构建器；options() 将本次请求实际使用的模型覆盖进去。
        return chatClient.prompt()
                .options(ChatOptions.builder().model(decision.model()).build());
    }
}
