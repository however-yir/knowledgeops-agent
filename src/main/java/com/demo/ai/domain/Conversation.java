package com.demo.ai.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@Builder
@AllArgsConstructor
@NoArgsConstructor
public class Conversation {
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;
    private String conversationId;
    private String message;
    private String type;
    private LocalDateTime createTime;
}