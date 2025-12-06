package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.SecurityProperties;
import com.enterprise.iqk.domain.ApiKeyRecord;
import com.enterprise.iqk.mapper.ApiKeyMapper;
import com.enterprise.iqk.util.HashUtils;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class ApiKeyLifecycleService {
    private final ApiKeyMapper apiKeyMapper;
    private final SecurityProperties securityProperties;

    public ApiKeyIssueResult issue(String keyName, String roleName, String tenantId) {
        String normalizedTenant = normalizeTenant(tenantId);
        ApiKeyRecord active = apiKeyMapper.findActiveByKeyName(keyName, normalizedTenant);
        if (active != null) {
            throw new IllegalArgumentException("active api key already exists for keyName");
        }
        String raw = "ak-" + UUID.randomUUID().toString().replace("-", "");
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime expiresAt = now.plusDays(Math.max(1, securityProperties.getApiKeyExpireDays()));
        ApiKeyRecord record = ApiKeyRecord.builder()
                .keyHash(HashUtils.sha256Hex(raw))
                .keyName(keyName)
                .tenantId(normalizedTenant)
                .roleName(roleName)
                .enabled(1)
                .expiresAt(expiresAt)
                .createdAt(now)
                .updatedAt(now)
                .build();
        apiKeyMapper.insert(record);
        return new ApiKeyIssueResult(raw, record.getKeyName(), normalizedTenant, expiresAt);
    }

    public ApiKeyIssueResult rotate(String keyName, String reason, String tenantId) {
        String normalizedTenant = normalizeTenant(tenantId);
        ApiKeyRecord old = apiKeyMapper.findActiveByKeyName(keyName, normalizedTenant);
        if (old == null) {
            throw new IllegalArgumentException("active api key not found");
        }
        apiKeyMapper.revoke(old.getId(), LocalDateTime.now(), reason, LocalDateTime.now());
        ApiKeyIssueResult issued = issue(keyName, old.getRoleName(), normalizedTenant);
        ApiKeyRecord newer = apiKeyMapper.findActiveByKeyName(keyName, normalizedTenant);
        if (newer != null) {
            newer.setRotatedFromId(old.getId());
            newer.setUpdatedAt(LocalDateTime.now());
            apiKeyMapper.updateById(newer);
        }
        return issued;
    }

    public void revoke(String keyName, String reason, String tenantId) {
        String normalizedTenant = normalizeTenant(tenantId);
        ApiKeyRecord record = apiKeyMapper.findActiveByKeyName(keyName, normalizedTenant);
        if (record == null) {
            throw new IllegalArgumentException("active api key not found");
        }
        apiKeyMapper.revoke(record.getId(), LocalDateTime.now(), reason, LocalDateTime.now());
    }

    private String normalizeTenant(String tenantId) {
        return TenantContext.normalize(tenantId);
    }

    public record ApiKeyIssueResult(String rawApiKey, String keyName, String tenantId, LocalDateTime expiresAt) {}
}
