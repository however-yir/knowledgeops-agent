package com.enterprise.iqk.domain.vo;

import lombok.Data;

@Data
public class BranchCompareRequestVO {
    private String sourceBranchId;
    private String targetBranchId;
}
