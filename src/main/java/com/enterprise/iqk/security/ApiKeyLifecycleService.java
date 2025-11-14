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

    public ApiKeyIssueResult issue(String keyName, String roleName) {
        ApiKeyRecord active = apiKeyMapper.findActiveByKeyName(keyName);
        if (active != null) {
            throw new IllegalArgumentException("active api key already exists for keyName");
        }
        String raw = "ak-" + UUID.randomUUID().toString().replace("-", "");
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime expiresAt = now.plusDays(Math.max(1, securityProperties.getApiKeyExpireDays()));
        ApiKeyRecord record = ApiKeyRecord.builder()
                .keyHash(HashUtils.sha256Hex(raw))
                .keyName(keyName)
                .roleName(roleName)
                .enabled(1)
                .expiresAt(expiresAt)
                .createdAt(now)
                .updatedAt(now)
                .build();
        apiKeyMapper.insert(record);
        return new ApiKeyIssueResult(raw, record.getKeyName(), expiresAt);
    }

    public ApiKeyIssueResult rotate(String keyName, String reason) {
        ApiKeyRecord old = apiKeyMapper.findActiveByKeyName(keyName);
        if (old == null) {
            throw new IllegalArgumentException("active api key not found");
        }
        apiKeyMapper.revoke(old.getId(), LocalDateTime.now(), reason, LocalDateTime.now());
        ApiKeyIssueResult issued = issue(keyName, old.getRoleName());
        ApiKeyRecord newer = apiKeyMapper.findActiveByKeyName(keyName);
        if (newer != null) {
            newer.setRotatedFromId(old.getId());
            newer.setUpdatedAt(LocalDateTime.now());
            apiKeyMapper.updateById(newer);
        }
        return issued;
    }

    public void revoke(String keyName, String reason) {
        ApiKeyRecord record = apiKeyMapper.findActiveByKeyName(keyName);
        if (record == null) {
            throw new IllegalArgumentException("active api key not found");
        }
        apiKeyMapper.revoke(record.getId(), LocalDateTime.now(), reason, LocalDateTime.now());
    }

    public record ApiKeyIssueResult(String rawApiKey, String keyName, LocalDateTime expiresAt) {}
}
