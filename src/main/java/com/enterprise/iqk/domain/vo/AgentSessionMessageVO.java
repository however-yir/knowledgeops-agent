package com.enterprise.iqk.domain.vo;

import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class AgentSessionMessageVO {
    private String id;
    private String role;
    private String content;
    private Long createdAt;
    private String state;
    private List<String> citations;
    private List<String> evidence;
    private String taskId;
    private String traceId;
    private List<Map<String, Object>> memorySnapshot;
    private Map<String, Object> workflowState;
}
