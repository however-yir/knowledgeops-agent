package com.demo.ai.repository.impl;

import com.demo.ai.repository.ChatHistoryRepository;
import org.springframework.stereotype.Repository;

import java.util.ArrayList;
import java.util.HashMap;
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

        List<String> list = chatHistory.computeIfAbsent(type, k -> new ArrayList<>());
        if (list.contains(chatId)) {
            //说明这个chatId已经有了
            return;
        }
        list.add(chatId);
    }

    @Override
    public List<String> getChatIds(String type) {
//        List<String> list = chatHistory.get(type);
//        if(list==null){
//            list = new ArrayList<>();
//        }
//        return list;
        return chatHistory.getOrDefault(type,new ArrayList<>());
    }
}
