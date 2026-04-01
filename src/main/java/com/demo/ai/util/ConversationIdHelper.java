package com.demo.ai.util;

import org.springframework.util.StringUtils;

public final class ConversationIdHelper {
    private static final String SEPARATOR = "::";

    private ConversationIdHelper() {
    }

    public static String build(String type, String chatId) {
        if (!StringUtils.hasText(type) || !StringUtils.hasText(chatId)) {
            throw new IllegalArgumentException("type and chatId must not be blank");
        }
        return type + SEPARATOR + chatId;
    }

    public static String extractChatId(String conversationId) {
        if (!StringUtils.hasText(conversationId)) {
            return conversationId;
        }
        int index = conversationId.indexOf(SEPARATOR);
        return index < 0 ? conversationId : conversationId.substring(index + SEPARATOR.length());
    }
}
