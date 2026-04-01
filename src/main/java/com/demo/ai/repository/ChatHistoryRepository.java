package com.demo.ai.repository;

import com.demo.ai.domain.vo.MessageVO;
import com.demo.ai.domain.vo.PagedResult;

import java.util.List;

public interface ChatHistoryRepository {
    /**
     * 保存会话记录
     * @param type 业务类型，如：chat、service、pdf
     * @param chatId 会话ID
     */
    void save(String type, String chatId);

    /**
     * 获取会话ID列表
     * @param type 业务类型，如：chat、service、pdf
     * @return 会话ID列表
     */
    PagedResult<String> getChatIds(String type, int page, int pageSize);

    /**
     * 获取指定会话的分页历史
     * @param type 业务类型
     * @param chatId 会话ID
     * @param page 当前页
     * @param pageSize 每页数量
     * @return 分页消息列表
     */
    PagedResult<MessageVO> getChatHistory(String type, String chatId, int page, int pageSize);
}
