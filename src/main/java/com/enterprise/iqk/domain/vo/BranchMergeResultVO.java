package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class BranchMergeResultVO {
    private AgentSessionStateVO session;
    private AgentSessionBranchVO mergedBranch;
    private Integer mergedMessageCount;
}
