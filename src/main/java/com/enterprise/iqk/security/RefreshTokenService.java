package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.SecurityProperties;
import com.enterprise.iqk.domain.RefreshTokenRecord;
import com.enterprise.iqk.mapper.RefreshTokenMapper;
import com.enterprise.iqk.util.HashUtils;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class RefreshTokenService {
    private final SecurityProperties securityProperties;
    private final RefreshTokenMapper refreshTokenMapper;

    public RefreshTokenIssueResult issue(String principal, List<String> roles, String tenantId) {
        String raw = UUID.randomUUID() + "." + UUID.randomUUID();
        LocalDateTime expiresAt = LocalDateTime.now().plusDays(Math.max(1, securityProperties.getRefreshExpireDays()));
        String roleCsv = roles == null ? "" : roles.stream()
                .filter(StringUtils::hasText)
                .collect(java.util.stream.Collectors.joining(","));
        RefreshTokenRecord record = RefreshTokenRecord.builder()
                .tokenHash(HashUtils.sha256Hex(raw))
                .principal(principal)
                .tenantId(TenantContext.normalize(tenantId))
                .roles(roleCsv)
                .expiresAt(expiresAt)
                .createdAt(LocalDateTime.now())
                .build();
        refreshTokenMapper.insert(record);
        return new RefreshTokenIssueResult(raw, record.getTenantId(), expiresAt);
    }

    @Transactional
    public AuthIdentity consume(String rawToken) {
        if (!StringUtils.hasText(rawToken)) {
            return null;
        }
        String hash = HashUtils.sha256Hex(rawToken);
        RefreshTokenRecord record = refreshTokenMapper.findActiveByHash(hash);
        if (record == null) {
            return null;
        }
        // Conditional revoke guards against concurrent reuse of the same token:
        // only the first caller flips revoked_at, the rest get 0 rows and are rejected.
        if (refreshTokenMapper.revoke(record.getId(), LocalDateTime.now()) == 0) {
            return null;
        }
        String roleCsv = Objects.toString(record.getRoles(), "");
        List<String> roles = Arrays.stream(roleCsv.split(","))
                .filter(StringUtils::hasText)
                .toList();
        return AuthIdentity.builder()
                .principal(record.getPrincipal())
                .roles(roles)
                .permissions(List.of())
                .source("refresh_token")
                .tenantId(TenantContext.normalize(record.getTenantId()))
                .build();
    }

    public record RefreshTokenIssueResult(String rawToken, String tenantId, LocalDateTime expiresAt) {}
}
