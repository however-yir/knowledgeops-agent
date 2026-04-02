package com.demo.ai.security;

import com.demo.ai.config.properties.SecurityProperties;
import com.demo.ai.domain.RefreshTokenRecord;
import com.demo.ai.mapper.RefreshTokenMapper;
import com.demo.ai.util.HashUtils;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class RefreshTokenService {
    private final SecurityProperties securityProperties;
    private final RefreshTokenMapper refreshTokenMapper;

    public String issue(String principal, List<String> roles) {
        String raw = UUID.randomUUID() + "." + UUID.randomUUID();
        RefreshTokenRecord record = RefreshTokenRecord.builder()
                .tokenHash(HashUtils.sha256Hex(raw))
                .principal(principal)
                .roles(String.join(",", roles))
                .expiresAt(LocalDateTime.now().plusDays(Math.max(1, securityProperties.getRefreshExpireDays())))
                .createdAt(LocalDateTime.now())
                .build();
        refreshTokenMapper.insert(record);
        return raw;
    }

    public AuthIdentity consume(String rawToken) {
        if (!StringUtils.hasText(rawToken)) {
            return null;
        }
        String hash = HashUtils.sha256Hex(rawToken);
        RefreshTokenRecord record = refreshTokenMapper.findActiveByHash(hash);
        if (record == null) {
            return null;
        }
        refreshTokenMapper.revoke(record.getId(), LocalDateTime.now());
        List<String> roles = Arrays.stream(record.getRoles().split(","))
                .filter(StringUtils::hasText)
                .toList();
        return AuthIdentity.builder()
                .principal(record.getPrincipal())
                .roles(roles)
                .permissions(List.of())
                .source("refresh_token")
                .build();
    }
}
