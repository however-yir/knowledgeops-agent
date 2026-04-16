package com.enterprise.iqk.domain.vo;

import lombok.Builder;
import lombok.Data;

import java.math.BigDecimal;

@Data
@Builder
public class TenantCostSummaryVO {
    private String tenantId;
    private String month;
    private BigDecimal monthlyBudgetUsd;
    private Boolean hardLimitEnabled;
    private BigDecimal monthCostUsd;
    private Long monthRequestCount;
    private Long monthInputTokens;
    private Long monthOutputTokens;
    private BigDecimal todayCostUsd;
    private Long todayRequestCount;
    private BigDecimal budgetRemainingUsd;
    private Boolean budgetExceeded;
}
