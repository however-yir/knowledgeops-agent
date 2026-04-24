package com.enterprise.iqk.repository.impl;

import com.enterprise.iqk.domain.Conversation;
import com.enterprise.iqk.domain.vo.MessageVO;
import com.enterprise.iqk.domain.vo.PagedResult;
import com.enterprise.iqk.mapper.ConversationMapper;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.util.ConversationIdHelper;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Repository;

import java.util.Collections;
import java.util.List;

@Primary
@Repository
@RequiredArgsConstructor
public class MysqlChatHistoryRepository implements ChatHistoryRepository {
    private final ConversationMapper conversationMapper;

    @Override
    public void save(String type, String chatId) {
        // 历史列表以 conversation 表为准，这里只负责提前校验会话参数格式。
        ConversationIdHelper.build(type, chatId);
    }

    @Override
    public PagedResult<String> getChatIds(String type, int page, int pageSize) {
        int safePage = Math.max(page, 1);
        int safePageSize = Math.max(pageSize, 1);
        String tenantId = currentTenantId();
        long total = conversationMapper.countConversationIdsByType(tenantId, type);
        if (total == 0) {
            return new PagedResult<>(Collections.emptyList(), 0, safePage, safePageSize);
        }
        long offset = (long) (safePage - 1) * safePageSize;
        List<String> items = conversationMapper.findConversationIdsByType(tenantId, type, offset, safePageSize)
                .stream()
                .map(ConversationIdHelper::extractChatId)
                .toList();
        return new PagedResult<>(items, total, safePage, safePageSize);
    }

    @Override
    public PagedResult<MessageVO> getChatHistory(String type, String chatId, int page, int pageSize) {
        int safePage = Math.max(page, 1);
        int safePageSize = Math.max(pageSize, 1);
        String conversationId = ConversationIdHelper.build(type, chatId);
        String tenantId = currentTenantId();
        long total = conversationMapper.countMessagesByConversationId(tenantId, conversationId);
        if (total == 0) {
            return new PagedResult<>(Collections.emptyList(), 0, safePage, safePageSize);
        }
        long offset = (long) (safePage - 1) * safePageSize;
        List<MessageVO> items = conversationMapper.findMessagesByConversationId(tenantId, conversationId, offset, safePageSize)
                .stream()
                .map(this::toMessageVO)
                .toList();
        return new PagedResult<>(items, total, safePage, safePageSize);
    }

    private MessageVO toMessageVO(Conversation conversation) {
        MessageVO vo = new MessageVO();
        String role = switch (conversation.getType()) {
            case "USER" -> "user";
            case "ASSISTANT" -> "assistant";
            case "SYSTEM" -> "system";
            default -> "";
        };
        vo.setRole(role);
        vo.setContent(conversation.getMessage());
        return vo;
    }

    private String currentTenantId() {
        return TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
    }
}
