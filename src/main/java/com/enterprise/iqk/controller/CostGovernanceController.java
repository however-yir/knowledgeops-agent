package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.vo.TenantBudgetUpdateVO;
import com.enterprise.iqk.domain.vo.TenantCostSummaryVO;
import com.enterprise.iqk.security.TenantContext;
import com.enterprise.iqk.service.TenantCostService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.util.StringUtils;

@RestController
@RequestMapping("/cost")
@RequiredArgsConstructor
public class CostGovernanceController {
    private final TenantCostService tenantCostService;

    @GetMapping("/summary")
    public TenantCostSummaryVO summary(@RequestHeader(value = TenantContext.TENANT_HEADER, required = false) String tenantId) {
        return tenantCostService.summary(tenantId);
    }

    @PostMapping("/budget")
    public TenantCostSummaryVO updateBudget(@RequestBody TenantBudgetUpdateVO request,
                                            @RequestHeader(value = TenantContext.TENANT_HEADER, required = false) String tenantId) {
        if (request != null && !StringUtils.hasText(request.getTenantId())) {
            request.setTenantId(TenantContext.normalize(tenantId));
        }
        return tenantCostService.updateBudget(request);
    }
}
