package com.enterprise.iqk.service;

import com.enterprise.iqk.config.properties.CostGovernanceProperties;
import com.enterprise.iqk.domain.TenantBudget;
import com.enterprise.iqk.domain.vo.TenantBudgetUpdateVO;
import com.enterprise.iqk.domain.vo.TenantCostSummaryVO;
import com.enterprise.iqk.mapper.TenantBudgetMapper;
import com.enterprise.iqk.mapper.TenantUsageDailyMapper;
import com.enterprise.iqk.security.TenantContext;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.util.Locale;

@Service
@RequiredArgsConstructor
public class TenantCostService {
    private final TenantBudgetMapper tenantBudgetMapper;
    private final TenantUsageDailyMapper tenantUsageDailyMapper;
    private final CostGovernanceProperties costGovernanceProperties;

    public void assertBudget(String tenantId, String costTier, long inputTokens, long outputTokens) {
        if (!costGovernanceProperties.isEnabled()) {
            return;
        }
        String tenant = TenantContext.normalize(tenantId);
        TenantBudget budget = ensureBudget(tenant);
        BigDecimal estimatedCost = calculateCost(costTier, inputTokens + outputTokens);
        BigDecimal monthCost = monthCost(tenant, YearMonth.now());
        BigDecimal projected = monthCost.add(estimatedCost);
        boolean hardLimit = budget.getHardLimitEnabled() != null && budget.getHardLimitEnabled() == 1;
        if (hardLimit && projected.compareTo(defaultDecimal(budget.getMonthlyBudgetUsd())) > 0) {
            throw new IllegalArgumentException("tenant budget exceeded, request blocked");
        }
    }

    public void recordUsage(String tenantId,
                            String costTier,
                            long inputTokens,
                            long outputTokens,
                            String endpointTag) {
        if (!costGovernanceProperties.isEnabled()) {
            return;
        }
        String tenant = TenantContext.normalize(tenantId);
        long safeInput = Math.max(0, inputTokens);
        long safeOutput = Math.max(0, outputTokens);
        BigDecimal cost = calculateCost(costTier, safeInput + safeOutput);
        tenantUsageDailyMapper.addUsage(
                tenant,
                LocalDate.now(),
                1,
                safeInput,
                safeOutput,
                cost
        );
    }

    public TenantCostSummaryVO summary(String tenantId) {
        String tenant = TenantContext.normalize(tenantId);
        TenantBudget budget = ensureBudget(tenant);
        YearMonth now = YearMonth.now();
        LocalDate monthStart = now.atDay(1);
        LocalDate monthEnd = now.atEndOfMonth();
        LocalDate today = LocalDate.now();

        Long monthRequestCount = safeLong(tenantUsageDailyMapper.sumRequestCount(tenant, monthStart, monthEnd));
        Long monthInput = safeLong(tenantUsageDailyMapper.sumInputTokens(tenant, monthStart, monthEnd));
        Long monthOutput = safeLong(tenantUsageDailyMapper.sumOutputTokens(tenant, monthStart, monthEnd));
        BigDecimal monthCost = defaultDecimal(tenantUsageDailyMapper.sumCostUsd(tenant, monthStart, monthEnd));

        Long todayRequestCount = safeLong(tenantUsageDailyMapper.sumRequestCount(tenant, today, today));
        BigDecimal todayCost = defaultDecimal(tenantUsageDailyMapper.sumCostUsd(tenant, today, today));

        BigDecimal budgetLimit = defaultDecimal(budget.getMonthlyBudgetUsd());
        BigDecimal remaining = budgetLimit.subtract(monthCost).max(BigDecimal.ZERO);
        boolean exceeded = monthCost.compareTo(budgetLimit) > 0;

        return TenantCostSummaryVO.builder()
                .tenantId(tenant)
                .month(now.toString())
                .monthlyBudgetUsd(budgetLimit)
                .hardLimitEnabled(budget.getHardLimitEnabled() != null && budget.getHardLimitEnabled() == 1)
                .monthCostUsd(scale(monthCost))
                .monthRequestCount(monthRequestCount)
                .monthInputTokens(monthInput)
                .monthOutputTokens(monthOutput)
                .todayCostUsd(scale(todayCost))
                .todayRequestCount(todayRequestCount)
                .budgetRemainingUsd(scale(remaining))
                .budgetExceeded(exceeded)
                .build();
    }

    public TenantCostSummaryVO updateBudget(TenantBudgetUpdateVO request) {
        if (request == null) {
            throw new IllegalArgumentException("budget payload is required");
        }
        String tenant = TenantContext.normalize(request.getTenantId());
        TenantBudget budget = ensureBudget(tenant);
        if (request.getMonthlyBudgetUsd() != null) {
            if (request.getMonthlyBudgetUsd().compareTo(BigDecimal.ZERO) < 0) {
                throw new IllegalArgumentException("monthlyBudgetUsd must be non-negative");
            }
            budget.setMonthlyBudgetUsd(request.getMonthlyBudgetUsd());
        }
        if (request.getHardLimitEnabled() != null) {
            budget.setHardLimitEnabled(Boolean.TRUE.equals(request.getHardLimitEnabled()) ? 1 : 0);
        }
        budget.setUpdatedAt(LocalDateTime.now());
        tenantBudgetMapper.updateById(budget);
        return summary(tenant);
    }

    public long estimateTokens(String text) {
        if (!StringUtils.hasText(text)) {
            return 0;
        }
        int divisor = Math.max(1, costGovernanceProperties.getTokenEstimateDivisor());
        int length = text.codePointCount(0, text.length());
        return Math.max(1L, (length + divisor - 1L) / divisor);
    }

    private TenantBudget ensureBudget(String tenantId) {
        TenantBudget existing = tenantBudgetMapper.findByTenantId(tenantId);
        if (existing != null) {
            return existing;
        }
        LocalDateTime now = LocalDateTime.now();
        TenantBudget inserted = TenantBudget.builder()
                .tenantId(tenantId)
                .monthlyBudgetUsd(defaultDecimal(costGovernanceProperties.getDefaultMonthlyBudgetUsd()))
                .hardLimitEnabled(costGovernanceProperties.isDefaultHardLimitEnabled() ? 1 : 0)
                .createdAt(now)
                .updatedAt(now)
                .build();
        tenantBudgetMapper.insert(inserted);
        return tenantBudgetMapper.findByTenantId(tenantId);
    }

    private BigDecimal monthCost(String tenantId, YearMonth month) {
        BigDecimal total = tenantUsageDailyMapper.sumCostUsd(tenantId, month.atDay(1), month.atEndOfMonth());
        return defaultDecimal(total);
    }

    private BigDecimal calculateCost(String costTier, long totalTokens) {
        String tier = StringUtils.hasText(costTier) ? costTier.trim().toLowerCase(Locale.ROOT) : "medium";
        BigDecimal unit = costGovernanceProperties.getUsdPer1kTokens().getOrDefault(
                tier,
                costGovernanceProperties.getUsdPer1kTokens().getOrDefault("medium", new BigDecimal("0.0030"))
        );
        BigDecimal tokens = BigDecimal.valueOf(Math.max(0, totalTokens));
        return tokens.multiply(defaultDecimal(unit))
                .divide(BigDecimal.valueOf(1000), 6, RoundingMode.HALF_UP);
    }

    private Long safeLong(Long value) {
        return value == null ? 0L : value;
    }

    private BigDecimal defaultDecimal(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }

    private BigDecimal scale(BigDecimal value) {
        return defaultDecimal(value).setScale(4, RoundingMode.HALF_UP);
    }
}
