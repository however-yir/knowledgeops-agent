package com.enterprise.iqk.config;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.enterprise.iqk.domain.Conversation;
import com.enterprise.iqk.mapper.ConversationMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.*;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class MysqlChatMemory implements ChatMemory {
    private final ConversationMapper conversationMapper;


    @Override
    public void add(String conversationId, List<Message> messages) {
        for (Message message : messages) {
            Conversation conversation = Conversation.builder()
                    .conversationId(conversationId)
                    .createTime(LocalDateTime.now())
                    .message(message.getText())
                    .type(message.getMessageType().getValue())//role
                    .build();
            conversationMapper.insert(conversation);
        }
    }

    @Override
    public List<Message> get(String conversationId, int lastN) {
        if (lastN <= 0) {
            return List.of();
        }
        List<Conversation> records = conversationMapper.findLatestMessages(conversationId, lastN);
        if(records==null||records.size()==0){
            //没查到
            return new ArrayList<>();
        }else{
            //说明有数据

            List<Message> messageList = new ArrayList<>();
            for (Conversation r : records) {
                Message message = null;
                if (MessageType.USER.getValue().equals(r.getType())) {
                    message = new UserMessage(r.getMessage());
                } else if (MessageType.ASSISTANT.getValue().equals(r.getType())) {
                    message = new AssistantMessage(r.getMessage());
                } else if (MessageType.SYSTEM.getValue().equals(r.getType())) {
                    message =  new SystemMessage(r.getMessage());
                }
                messageList.add(message);
            }
            Collections.reverse(messageList);
            return messageList;
        }
    }

    @Override
    public void clear(String conversationId) {
        //sql：delete from conversation where conversation_id = ?
        conversationMapper.delete(new LambdaQueryWrapper<Conversation>().eq(Conversation::getConversationId,conversationId));
        //清空所有对话
    }
}
