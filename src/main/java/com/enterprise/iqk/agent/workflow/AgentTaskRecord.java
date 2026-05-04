package com.enterprise.iqk.agent.workflow;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("agent_task")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AgentTaskRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String taskId;
    private String tenantId;
    private String type;
    private String status;
    private String userInput;
    private String finalOutput;
    private String modelProfile;
    private String chatId;
    private String sessionId;
    private String metadataJson;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
