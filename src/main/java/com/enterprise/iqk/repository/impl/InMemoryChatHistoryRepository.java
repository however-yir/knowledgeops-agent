package com.enterprise.iqk.repository.impl;

import com.enterprise.iqk.domain.vo.MessageVO;
import com.enterprise.iqk.domain.vo.PagedResult;
import com.enterprise.iqk.repository.ChatHistoryRepository;
import com.enterprise.iqk.security.TenantContext;
import org.slf4j.MDC;
import org.springframework.stereotype.Repository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Repository
public class InMemoryChatHistoryRepository implements ChatHistoryRepository {
    private Map<String, List<String>> chatHistory = new ConcurrentHashMap<>();
    @Override
    public void save(String type, String chatId) {
//        List<String> list = chatHistory.get(type);
//        if(list==null){
//            list = new ArrayList<>();
//            chatHistory.put(type,list);
//        }
        List<String> list = chatHistory.computeIfAbsent(scopedKey(type), k -> new ArrayList<>());
        if (list.contains(chatId)) {
            //说明这个chatId已经有了
            return;
        }
        list.add(chatId);
    }

    @Override
    public PagedResult<String> getChatIds(String type, int page, int pageSize) {
        List<String> all = chatHistory.getOrDefault(scopedKey(type), new ArrayList<>());
        int safePage = Math.max(page, 1);
        int safePageSize = Math.max(pageSize, 1);
        int fromIndex = Math.min((safePage - 1) * safePageSize, all.size());
        int toIndex = Math.min(fromIndex + safePageSize, all.size());
        return new PagedResult<>(all.subList(fromIndex, toIndex), all.size(), safePage, safePageSize);
    }

    @Override
    public PagedResult<MessageVO> getChatHistory(String type, String chatId, int page, int pageSize) {
        return new PagedResult<>(Collections.emptyList(), 0, Math.max(page, 1), Math.max(pageSize, 1));
    }

    private String scopedKey(String type) {
        String tenantId = TenantContext.normalize(MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
        return tenantId + "::" + type;
    }
}
