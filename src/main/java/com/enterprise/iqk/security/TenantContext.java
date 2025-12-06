package com.enterprise.iqk.security;

import org.springframework.util.StringUtils;

public final class TenantContext {
    public static final String TENANT_HEADER = "X-Tenant-Id";
    public static final String TENANT_REQUEST_ATTRIBUTE = "tenant_id";
    public static final String DEFAULT_TENANT = "public";

    private TenantContext() {
    }

    public static String normalize(String tenantId) {
        return StringUtils.hasText(tenantId) ? tenantId.trim() : DEFAULT_TENANT;
    }
}
