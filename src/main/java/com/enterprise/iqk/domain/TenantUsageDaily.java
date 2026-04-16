package com.enterprise.iqk.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@TableName("tenant_usage_daily")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TenantUsageDaily {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String tenantId;
    private LocalDate usageDate;
    private Long requestCount;
    private Long inputTokens;
    private Long outputTokens;
    private BigDecimal totalCostUsd;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
