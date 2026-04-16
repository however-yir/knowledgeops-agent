package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("answer_feedback")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AnswerFeedback {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String tenantId;
    private String chatId;
    private String sessionId;
    private String branchId;
    private String messageId;
    private Integer rating;
    private String comment;
    private String questionText;
    private String answerText;
    private LocalDateTime createdAt;
}
