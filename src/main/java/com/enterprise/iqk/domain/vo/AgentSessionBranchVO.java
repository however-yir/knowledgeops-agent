package com.enterprise.iqk.domain.vo;

import lombok.Data;

import java.util.List;

@Data
public class AgentSessionBranchVO {
    private String id;
    private String title;
    private String parentBranchId;
    private String parentMessageId;
    private Long updatedAt;
    private List<AgentSessionMessageVO> messages;
    private List<ReactTraceStepVO> traceSteps;
}
