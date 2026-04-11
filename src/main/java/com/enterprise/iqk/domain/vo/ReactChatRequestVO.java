package com.enterprise.iqk.domain.vo;

import lombok.Data;

@Data
public class ReactChatRequestVO {
    private String prompt;
    private String chatId;
    private String modelProfile;
}

