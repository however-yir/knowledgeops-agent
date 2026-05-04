package com.enterprise.iqk.agent.workflow;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class WorkflowStepVO {
    private String stepId;
    private String taskId;
    private String agentName;
    private String status;
    private int stepOrder;
    private String thought;
    private String action;
    private Map<String, Object> actionInput;
    private Object observation;
    private String modelProfile;
    private long inputTokens;
    private long outputTokens;
    private long latencyMs;
    private String errorMessage;
    private LocalDateTime startedAt;
    private LocalDateTime endedAt;
}
