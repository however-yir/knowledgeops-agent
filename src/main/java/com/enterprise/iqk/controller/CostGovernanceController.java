package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.TenantBudgetUpdateVO;
import com.enterprise.iqk.domain.vo.TenantCostSummaryVO;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.TenantCostService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/cost")
@RequiredArgsConstructor
public class CostGovernanceController {
    private final TenantCostService tenantCostService;

    @GetMapping("/summary")
    public TenantCostSummaryVO summary() {
        return tenantCostService.summary(TenantContext.currentTenantId());
    }

    @PostMapping("/budget")
    public TenantCostSummaryVO updateBudget(@RequestBody TenantBudgetUpdateVO request) {
        if (request != null) {
            request.setTenantId(TenantContext.currentTenantId());
        }
        return tenantCostService.updateBudget(request);
    }
}
