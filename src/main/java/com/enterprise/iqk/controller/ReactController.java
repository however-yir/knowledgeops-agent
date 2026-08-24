package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.ReactChatRequestVO;
import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.service.ReactAgentService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

/**
 * ReAct 智能体聊天接口。
 *
 * <p>ReAct 是 Reasoning（推理）与 Acting（行动）的组合。与普通聊天直接请求模型回答不同，
 * ReAct 服务会在限定步数内重复执行“思考 → 选择动作 → 执行动作 → 获取观察结果”，
 * 最后再根据执行轨迹生成答案。</p>
 *
 * <p>该控制器只负责：</p>
 * <ol>
 *     <li>接收并反序列化前端提交的 JSON 请求；</li>
 *     <li>把请求委托给 {@link ReactAgentService}；</li>
 *     <li>登记 ReAct 类型的会话索引；</li>
 *     <li>以普通 JSON 或 SSE 流的形式返回结果。</li>
 * </ol>
 *
 * <p>推理循环、工具执行、模型路由、证据与引用整理等核心逻辑都在 Service 层完成。</p>
 */
@RestController
@RequestMapping("/ai/react")
@RequiredArgsConstructor
public class ReactController {

    /** 执行 ReAct 推理循环、动作调用和最终答案生成。 */
    private final ReactAgentService reactAgentService;

    /** 保存会话索引，供历史会话列表按类型查询。 */
    private final ChatHistoryRepository chatHistoryRepository;

    /**
     * 同步 ReAct 聊天接口。
     *
     * <p>客户端发送 JSON 请求后，该方法会等待整个 ReAct 流程执行完毕，
     * 再一次性返回包含答案、轨迹、引用、证据和模型路由信息的 JSON 对象。</p>
     *
     * @param request ReAct 请求，包含 prompt、chatId 和可选的 modelProfile
     * @return 完整的 ReAct 执行结果
     */
    @PostMapping(value = "/chat", produces = MediaType.APPLICATION_JSON_VALUE)
    public ReactChatResponseVO chat(@RequestBody ReactChatRequestVO request) {
        // Service 会校验请求，并完整执行 ReAct 的思考、行动、观察和回答流程。
        ReactChatResponseVO response = reactAgentService.chat(request);

        // 使用 Service 最终返回的 chatId 登记会话；hasText 同时排除 null、空串和纯空白字符串。
        if (StringUtils.hasText(response.getChatId())) {
            chatHistoryRepository.save("react", response.getChatId());
        }

        // Spring MVC 会把 VO 自动序列化为 application/json 响应。
        return response;
    }

    /**
     * SSE 流式 ReAct 聊天接口。
     *
     * <p>该方法立即返回一个 {@link Flux}。客户端订阅后，Service 会逐步推送：
     * trace（推理轨迹）、token（答案片段）、done（完成信息）或 error（错误信息）事件。</p>
     *
     * <p>因为流式响应在方法返回后才持续执行，所以这里无法等待最终响应对象，
     * 只能在请求包含有效 chatId 时提前登记会话。</p>
     *
     * @param request ReAct 请求，包含 prompt、chatId 和可选的 modelProfile
     * @return SSE 格式的字符串事件流
     */
    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> chatStream(@RequestBody ReactChatRequestVO request) {
        // 先判断 request，避免请求体为空时调用 request.getChatId() 产生空指针异常。
        if (request != null && StringUtils.hasText(request.getChatId())) {
            chatHistoryRepository.save("react", request.getChatId());
        }

        // 此处只是返回响应式数据流；真正执行通常在 Web 层订阅 Flux 后开始。
        return reactAgentService.stream(request);
    }
}
