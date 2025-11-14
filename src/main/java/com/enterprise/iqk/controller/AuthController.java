package com.enterprise.iqk.controller;

import com.enterprise.iqk.config.properties.SecurityProperties;
import com.enterprise.iqk.domain.vo.ApiKeyIssueVO;
import com.enterprise.iqk.domain.vo.AuthTokenVO;
import com.enterprise.iqk.security.*;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
public class AuthController {
    private final ApiKeyAuthService apiKeyAuthService;
    private final ApiKeyLifecycleService apiKeyLifecycleService;
    private final JwtService jwtService;
    private final RefreshTokenService refreshTokenService;
    private final PermissionService permissionService;
    private final SecurityProperties securityProperties;

    @PostMapping("/token")
    public AuthTokenVO token(@RequestHeader("X-API-Key") String apiKey) {
        AuthIdentity identity = apiKeyAuthService.authenticate(apiKey);
        if (identity == null) {
            return AuthTokenVO.builder().ok(0).msg("invalid api key").build();
        }
        List<String> permissions = permissionService.permissionsForRoles(identity.getRoles());
        String token = jwtService.issueToken(identity.getPrincipal(), identity.getRoles(), permissions);
        String refresh = refreshTokenService.issue(identity.getPrincipal(), identity.getRoles());
        return AuthTokenVO.builder()
                .ok(1)
                .msg("ok")
                .token(token)
                .refreshToken(refresh)
                .expiresInSeconds(securityProperties.getJwtExpireMinutes() * 60L)
                .build();
    }

    @PostMapping("/refresh")
    public AuthTokenVO refresh(@RequestHeader("X-Refresh-Token") String refreshToken) {
        AuthIdentity identity = refreshTokenService.consume(refreshToken);
        if (identity == null) {
            return AuthTokenVO.builder().ok(0).msg("invalid refresh token").build();
        }
        List<String> permissions = permissionService.permissionsForRoles(identity.getRoles());
        String token = jwtService.issueToken(identity.getPrincipal(), identity.getRoles(), permissions);
        String newRefresh = refreshTokenService.issue(identity.getPrincipal(), identity.getRoles());
        return AuthTokenVO.builder()
                .ok(1)
                .msg("ok")
                .token(token)
                .refreshToken(newRefresh)
                .expiresInSeconds(securityProperties.getJwtExpireMinutes() * 60L)
                .build();
    }

    @PostMapping("/api-keys")
    @PreAuthorize("hasAnyAuthority('PERM_AUTH_KEY_MANAGE','ROLE_ADMIN')")
    public ApiKeyIssueVO issueApiKey(@RequestParam("keyName") String keyName,
                                     @RequestParam(value = "role", defaultValue = "USER") String roleName) {
        ApiKeyLifecycleService.ApiKeyIssueResult result = apiKeyLifecycleService.issue(keyName, roleName);
        return ApiKeyIssueVO.builder()
                .ok(1)
                .msg("ok")
                .keyName(result.keyName())
                .rawApiKey(result.rawApiKey())
                .expiresAt(result.expiresAt())
                .build();
    }

    @PostMapping("/api-keys/rotate")
    @PreAuthorize("hasAnyAuthority('PERM_AUTH_KEY_MANAGE','ROLE_ADMIN')")
    public ApiKeyIssueVO rotateApiKey(@RequestParam("keyName") String keyName,
                                      @RequestParam(value = "reason", defaultValue = "rotation") String reason) {
        ApiKeyLifecycleService.ApiKeyIssueResult result = apiKeyLifecycleService.rotate(keyName, reason);
        return ApiKeyIssueVO.builder()
                .ok(1)
                .msg("rotated")
                .keyName(result.keyName())
                .rawApiKey(result.rawApiKey())
                .expiresAt(result.expiresAt())
                .build();
    }

    @PostMapping("/api-keys/revoke")
    @PreAuthorize("hasAnyAuthority('PERM_AUTH_KEY_MANAGE','ROLE_ADMIN')")
    public ApiKeyIssueVO revokeApiKey(@RequestParam("keyName") String keyName,
                                      @RequestParam(value = "reason", defaultValue = "manual revoke") String reason) {
        apiKeyLifecycleService.revoke(keyName, reason);
        return ApiKeyIssueVO.builder()
                .ok(1)
                .msg("revoked")
                .keyName(keyName)
                .build();
    }
}
