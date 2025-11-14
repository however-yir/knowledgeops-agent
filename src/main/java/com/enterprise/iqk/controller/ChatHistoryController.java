package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.MessageVO;
import com.enterprise.iqk.domain.vo.PagedResult;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RequiredArgsConstructor
@RestController
@RequestMapping("/ai/history")
public class ChatHistoryController {

    private final ChatHistoryRepository chatHistoryRepository;

    /**
     * 查询会话历史列表
     * @param type 业务类型，如：chat,service,pdf
     * @return chatId列表
     */
    @GetMapping("/{type}")
    public PagedResult<String> getChatIds(@PathVariable("type") String type,
                                          @RequestParam(value = "page", defaultValue = "1") int page,
                                          @RequestParam(value = "pageSize", defaultValue = "20") int pageSize) {
        return chatHistoryRepository.getChatIds(type, page, pageSize);
    }

    /**
     * 根据业务类型、chatId查询会话历史
     * @param type 业务类型，如：chat,service,pdf
     * @param chatId 会话id
     * @return 指定会话的历史消息
     */
    @GetMapping("/{type}/{chatId}")
    public PagedResult<MessageVO> getChatHistory(@PathVariable("type") String type,
                                                 @PathVariable("chatId") String chatId,
                                                 @RequestParam(value = "page", defaultValue = "1") int page,
                                                 @RequestParam(value = "pageSize", defaultValue = "50") int pageSize) {
        return chatHistoryRepository.getChatHistory(type, chatId, page, pageSize);
    }
}
