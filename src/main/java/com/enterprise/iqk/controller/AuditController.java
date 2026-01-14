package com.enterprise.iqk.controller;

import com.enterprise.iqk.domain.AuditLog;
import com.enterprise.iqk.mapper.AuditLogMapper;
import com.enterprise.iqk.security.TenantContext;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/audit")
@RequiredArgsConstructor
public class AuditController {
    private final AuditLogMapper auditLogMapper;

    @GetMapping("/logs")
    @PreAuthorize("hasAnyAuthority('PERM_AUDIT_READ','ROLE_ADMIN')")
    public List<AuditLog> latest(@RequestParam(value = "limit", defaultValue = "50") int limit,
                                 @RequestParam(value = "tenantId", required = false) String tenantId,
                                 HttpServletRequest request) {
        int boundedLimit = Math.max(1, Math.min(limit, 200));
        String effectiveTenant = StringUtils.hasText(tenantId)
                ? TenantContext.normalize(tenantId)
                : resolveTenantFromRequest(request);
        if (StringUtils.hasText(effectiveTenant)) {
            return auditLogMapper.latestByTenant(effectiveTenant, boundedLimit);
        }
        return auditLogMapper.latest(boundedLimit);
    }

    private String resolveTenantFromRequest(HttpServletRequest request) {
        Object tenantFromAttr = request.getAttribute(TenantContext.TENANT_REQUEST_ATTRIBUTE);
        if (tenantFromAttr != null && StringUtils.hasText(String.valueOf(tenantFromAttr))) {
            return TenantContext.normalize(String.valueOf(tenantFromAttr));
        }
        String tenantHeader = request.getHeader(TenantContext.TENANT_HEADER);
        return StringUtils.hasText(tenantHeader) ? TenantContext.normalize(tenantHeader) : "";
    }
}
