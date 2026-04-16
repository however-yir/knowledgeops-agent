package com.enterprise.iqk.domain.vo;

import lombok.Data;

@Data
public class BranchMergeRequestVO {
    private String sourceBranchId;
    private String targetBranchId;
    private String title;
}
