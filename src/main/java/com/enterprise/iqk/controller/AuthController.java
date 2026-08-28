package com.enterprise.iqk.controller;

import com.enterprise.iqk.config.properties.SecurityProperties;
import com.enterprise.iqk.domain.vo.ApiKeyIssueVO;
import com.enterprise.iqk.domain.vo.AuthTokenVO;
import com.enterprise.iqk.security.ApiKeyAuthService;
import com.enterprise.iqk.security.ApiKeyLifecycleService;
import com.enterprise.iqk.security.AuthIdentity;
import com.enterprise.iqk.security.JwtService;
import com.enterprise.iqk.security.PermissionService;
import com.enterprise.iqk.security.RefreshTokenService;
import com.enterprise.iqk.security.TenantContext;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
public class AuthController {
    private static final long REFRESH_EXPIRE_SOON_DAYS = 2L;

    private final ApiKeyAuthService apiKeyAuthService;
    private final ApiKeyLifecycleService apiKeyLifecycleService;
    private final JwtService jwtService;
    private final RefreshTokenService refreshTokenService;
    private final PermissionService permissionService;
    private final SecurityProperties securityProperties;

    @PostMapping("/token")
    public AuthTokenVO token(@RequestHeader("X-API-Key") String apiKey,
                             @RequestHeader(value = TenantContext.TENANT_HEADER, required = false) String tenantHeader) {
        AuthIdentity identity = apiKeyAuthService.authenticate(apiKey);
        if (identity == null) {
            return AuthTokenVO.builder().ok(0).msg("invalid api key").build();
        }
        String identityTenant = TenantContext.normalize(identity.getTenantId());
        if (StringUtils.hasText(tenantHeader) && !identityTenant.equals(TenantContext.normalize(tenantHeader))) {
            return AuthTokenVO.builder().ok(0).msg("tenant mismatch for api key").build();
        }
        List<String> permissions = permissionService.permissionsForRoles(identity.getRoles());
        String token = jwtService.issueToken(identity.getPrincipal(), identity.getRoles(), permissions, identityTenant);
        RefreshTokenService.RefreshTokenIssueResult refreshIssue =
                refreshTokenService.issue(identity.getPrincipal(), identity.getRoles(), identityTenant);
        return buildTokenResponse(token, identityTenant, refreshIssue);
    }

    @PostMapping("/refresh")
    public AuthTokenVO refresh(@RequestHeader("X-Refresh-Token") String refreshToken) {
        AuthIdentity identity = refreshTokenService.consume(refreshToken);
        if (identity == null) {
            return AuthTokenVO.builder().ok(0).msg("invalid refresh token").build();
        }
        String tenantId = TenantContext.normalize(identity.getTenantId());
        List<String> permissions = permissionService.permissionsForRoles(identity.getRoles());
        String token = jwtService.issueToken(identity.getPrincipal(), identity.getRoles(), permissions, tenantId);
        RefreshTokenService.RefreshTokenIssueResult refreshIssue =
                refreshTokenService.issue(identity.getPrincipal(), identity.getRoles(), tenantId);
        return buildTokenResponse(token, tenantId, refreshIssue);
    }

    @PostMapping("/api-keys")
    @PreAuthorize("hasAnyAuthority('PERM_AUTH_KEY_MANAGE','ROLE_ADMIN')")
    public ApiKeyIssueVO issueApiKey(@RequestParam("keyName") String keyName,
                                     @RequestParam(value = "role", defaultValue = "USER") String roleName) {
        ApiKeyLifecycleService.ApiKeyIssueResult result = apiKeyLifecycleService.issue(
                keyName, roleName, TenantContext.currentTenantId());
        return ApiKeyIssueVO.builder()
                .ok(1)
                .msg("ok")
                .keyName(result.keyName())
                .tenantId(result.tenantId())
                .rawApiKey(result.rawApiKey())
                .expiresAt(result.expiresAt())
                .build();
    }

    @PostMapping("/api-keys/rotate")
    @PreAuthorize("hasAnyAuthority('PERM_AUTH_KEY_MANAGE','ROLE_ADMIN')")
    public ApiKeyIssueVO rotateApiKey(@RequestParam("keyName") String keyName,
                                      @RequestParam(value = "reason", defaultValue = "rotation") String reason) {
        ApiKeyLifecycleService.ApiKeyIssueResult result = apiKeyLifecycleService.rotate(
                keyName, reason, TenantContext.currentTenantId());
        return ApiKeyIssueVO.builder()
                .ok(1)
                .msg("rotated")
                .keyName(result.keyName())
                .tenantId(result.tenantId())
                .rawApiKey(result.rawApiKey())
                .expiresAt(result.expiresAt())
                .build();
    }

    @PostMapping("/api-keys/revoke")
    @PreAuthorize("hasAnyAuthority('PERM_AUTH_KEY_MANAGE','ROLE_ADMIN')")
    public ApiKeyIssueVO revokeApiKey(@RequestParam("keyName") String keyName,
                                      @RequestParam(value = "reason", defaultValue = "manual revoke") String reason) {
        String normalizedTenant = TenantContext.currentTenantId();
        apiKeyLifecycleService.revoke(keyName, reason, normalizedTenant);
        return ApiKeyIssueVO.builder()
                .ok(1)
                .msg("revoked")
                .keyName(keyName)
                .tenantId(normalizedTenant)
                .build();
    }

    private AuthTokenVO buildTokenResponse(String token,
                                           String tenantId,
                                           RefreshTokenService.RefreshTokenIssueResult refreshIssue) {
        LocalDateTime refreshExpiresAt = refreshIssue.expiresAt();
        boolean refreshWillExpireSoon = refreshExpiresAt != null
                && refreshExpiresAt.isBefore(LocalDateTime.now().plusDays(REFRESH_EXPIRE_SOON_DAYS));
        return AuthTokenVO.builder()
                .ok(1)
                .msg("ok")
                .token(token)
                .refreshToken(refreshIssue.rawToken())
                .tenantId(tenantId)
                .expiresInSeconds(securityProperties.getJwtExpireMinutes() * 60L)
                .refreshExpiresAt(refreshExpiresAt)
                .refreshWillExpireSoon(refreshWillExpireSoon)
                .build();
    }
}
