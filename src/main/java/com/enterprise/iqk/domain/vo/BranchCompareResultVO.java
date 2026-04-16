package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class BranchCompareResultVO {
    private String sourceBranchId;
    private String targetBranchId;
    private Integer sourceMessageCount;
    private Integer targetMessageCount;
    private Integer commonMessageCount;
    private Integer sourceOnlyCount;
    private Integer targetOnlyCount;
    private List<String> sourceOnlyPreview;
    private List<String> targetOnlyPreview;
}
