package com.enterprise.iqk.security;

import com.enterprise.iqk.domain.ApiKeyRecord;
import com.enterprise.iqk.mapper.ApiKeyMapper;
import com.enterprise.iqk.mapper.PermissionMapper;
import com.enterprise.iqk.util.HashUtils;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class ApiKeyAuthService {
    private final ApiKeyMapper apiKeyMapper;
    private final PermissionMapper permissionMapper;

    public AuthIdentity authenticate(String rawApiKey) {
        if (!StringUtils.hasText(rawApiKey)) {
            return null;
        }
        String keyHash = HashUtils.sha256Hex(rawApiKey.trim());
        ApiKeyRecord record = apiKeyMapper.findActiveByKeyHash(keyHash);
        if (record == null) {
            return null;
        }
        LocalDateTime now = LocalDateTime.now();
        apiKeyMapper.touch(record.getId(), now, now);
        return AuthIdentity.builder()
                .principal(record.getKeyName())
                .roles(List.of(record.getRoleName()))
                .permissions(permissionMapper.findByRoleName(record.getRoleName()))
                .source("api_key")
                .build();
    }
}
