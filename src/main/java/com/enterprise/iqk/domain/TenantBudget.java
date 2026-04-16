package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@TableName("tenant_budget")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TenantBudget {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String tenantId;
    private BigDecimal monthlyBudgetUsd;
    private Integer hardLimitEnabled;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
