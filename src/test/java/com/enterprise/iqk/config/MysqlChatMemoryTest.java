package com.enterprise.iqk.config;

import com.enterprise.iqk.domain.Conversation;
import com.enterprise.iqk.mapper.ConversationMapper;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.MessageType;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class MysqlChatMemoryTest {

    @Test
    void skipsUnsupportedMessageTypesWhenReadingHistory() {
        ConversationMapper mapper = mock(ConversationMapper.class);
        MysqlChatMemory memory = new MysqlChatMemory(mapper);
        when(mapper.findLatestMessages("public", "chat-1", 3)).thenReturn(List.of(
                conversation(MessageType.ASSISTANT.getValue(), "answer"),
                conversation("tool", "internal"),
                conversation(MessageType.USER.getValue(), "question")
        ));

        List<Message> messages = memory.get("chat-1", 3);

        assertThat(messages).hasSize(2);
        assertThat(messages).extracting(Message::getText).containsExactly("question", "answer");
    }

    private Conversation conversation(String type, String text) {
        return Conversation.builder()
                .tenantId("public")
                .conversationId("chat-1")
                .type(type)
                .message(text)
                .build();
    }
}
