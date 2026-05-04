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
public class WorkflowEventVO {
    private String eventId;
    private String taskId;
    private String stepId;
    private String eventType;
    private Map<String, Object> payload;
    private LocalDateTime createdAt;
}
