package com.enterprise.iqk.agent.workflow;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@TableName("agent_step")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AgentStepRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String stepId;
    private String taskId;
    private String agentName;
    private String status;
    private Integer stepOrder;
    private String inputJson;
    private String outputJson;
    private String thought;
    private String action;
    private String actionInputJson;
    private String observationJson;
    private String modelProfile;
    private Long inputTokens;
    private Long outputTokens;
    private Long latencyMs;
    private String errorMessage;
    private LocalDateTime startedAt;
    private LocalDateTime endedAt;
}
