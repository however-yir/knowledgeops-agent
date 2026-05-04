package com.enterprise.iqk.agent.workflow;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("agent_event")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AgentEventRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String eventId;
    private String taskId;
    private String stepId;
    private String eventType;
    private String payloadJson;
    private LocalDateTime createdAt;
}
