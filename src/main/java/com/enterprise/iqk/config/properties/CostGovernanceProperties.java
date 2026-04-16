package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

@Data
@ConfigurationProperties(prefix = "app.cost-governance")
public class CostGovernanceProperties {
    private boolean enabled = true;
    private BigDecimal defaultMonthlyBudgetUsd = new BigDecimal("25.0000");
    private boolean defaultHardLimitEnabled = false;
    private int tokenEstimateDivisor = 4;
    private Map<String, BigDecimal> usdPer1kTokens = new LinkedHashMap<>();

    public CostGovernanceProperties() {
        usdPer1kTokens.put("low", new BigDecimal("0.0010"));
        usdPer1kTokens.put("medium", new BigDecimal("0.0030"));
        usdPer1kTokens.put("high", new BigDecimal("0.0100"));
    }
}
