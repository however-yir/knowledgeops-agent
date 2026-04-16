package com.enterprise.iqk.domain.vo;

import lombok.Data;

import java.util.List;

@Data
public class AgentSessionStateVO {
    private String id;
    private String title;
    private Long updatedAt;
    private String modelProfile;
    private Boolean streaming;
    private Boolean pinned;
    private Boolean archived;
    private String workspaceId;
    private String activeBranchId;
    private List<AgentSessionBranchVO> branches;
}
