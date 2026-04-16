package com.enterprise.iqk.domain.vo;

import lombok.Data;

import java.math.BigDecimal;

@Data
public class TenantBudgetUpdateVO {
    private String tenantId;
    private BigDecimal monthlyBudgetUsd;
    private Boolean hardLimitEnabled;
}
