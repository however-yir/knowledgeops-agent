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

@RestController
@RequestMapping("/ai/react")
@RequiredArgsConstructor
public class ReactController {
    private final ReactAgentService reactAgentService;
    private final ChatHistoryRepository chatHistoryRepository;

    @PostMapping(value = "/chat", produces = MediaType.APPLICATION_JSON_VALUE)
    public ReactChatResponseVO chat(@RequestBody ReactChatRequestVO request) {
        ReactChatResponseVO response = reactAgentService.chat(request);
        if (StringUtils.hasText(response.getChatId())) {
            chatHistoryRepository.save("react", response.getChatId());
        }
        return response;
    }

    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> chatStream(@RequestBody ReactChatRequestVO request) {
        if (request != null && StringUtils.hasText(request.getChatId())) {
            chatHistoryRepository.save("react", request.getChatId());
        }
        return reactAgentService.stream(request);
    }
}
