package com.enterprise.iqk.domain.vo;

import lombok.Data;

@Data
public class AnswerFeedbackSubmitVO {
    private String chatId;
    private String sessionId;
    private String branchId;
    private String messageId;
    private Integer rating;
    private String comment;
    private String question;
    private String answer;
}
