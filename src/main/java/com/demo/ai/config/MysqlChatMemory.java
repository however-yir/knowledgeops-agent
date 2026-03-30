package com.demo.ai.config;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demo.ai.domain.Conversation;
import com.demo.ai.mapper.ConversationMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.*;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

//@Component
@RequiredArgsConstructor
public class MysqlChatMemory implements ChatMemory {
    private final ConversationMapper conversationMapper;


    @Override
    public void add(String conversationId, List<Message> messages) {
        //把数据存到mysql
        System.out.println("conversationId = " + conversationId);
        System.out.println("messages = " + messages);

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
        Page<Conversation> page = new Page<>(1,lastN);
        LambdaQueryWrapper<Conversation> lqw = new LambdaQueryWrapper<>();
        lqw.eq(Conversation::getConversationId,conversationId);
        Page<Conversation> pageResult = conversationMapper.selectPage(page, lqw);
        List<Conversation> records = pageResult.getRecords();
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
