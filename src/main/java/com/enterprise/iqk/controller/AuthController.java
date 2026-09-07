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
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.CookieValue;
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
    /** Name of the HttpOnly cookie that holds the long-lived refresh token. */
    public static final String REFRESH_COOKIE = "kops_refresh";

    private final ApiKeyAuthService apiKeyAuthService;
    private final ApiKeyLifecycleService apiKeyLifecycleService;
    private final JwtService jwtService;
    private final RefreshTokenService refreshTokenService;
    private final PermissionService permissionService;
    private final SecurityProperties securityProperties;

    /**
     * When true (default), the refresh token cookie is marked Secure and
     * the SameSite=Strict policy is used. Operators serving the app over
     * plain HTTP during local development should set
     * {@code app.security.refresh-cookie-secure=false} to make the cookie
     * usable from a localhost browser.
     */
    @Value("${app.security.refresh-cookie-secure:true}")
    private boolean refreshCookieSecure;

    @PostMapping("/token")
    public AuthTokenVO token(@RequestHeader("X-API-Key") String apiKey,
                             @RequestHeader(value = TenantContext.TENANT_HEADER, required = false) String tenantHeader,
                             HttpServletResponse response) {
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
        // Refresh token is delivered as an HttpOnly cookie so an XSS in the
        // front-end cannot exfiltrate the long-lived credential. The body
        // still carries a copy for the existing App.vue that has not yet
        // moved to credentials: 'include'. Once the companion PR (PR B)
        // lands and App.vue drops localStorage, the body field can go
        // away without breaking older clients mid-upgrade.
        setRefreshCookie(response, refreshIssue);
        return buildTokenResponse(token, identityTenant, refreshIssue);
    }

    @PostMapping("/refresh")
    public AuthTokenVO refresh(@RequestHeader(value = "X-Refresh-Token", required = false) String refreshTokenHeader,
                              @CookieValue(value = REFRESH_COOKIE, required = false) String refreshCookie) {
        // Accept the refresh token from either the legacy X-Refresh-Token
        // header or the HttpOnly cookie set by /auth/token. Header takes
        // precedence so older clients (or test scripts) can still override
        // the cookie value.
        String refreshToken = StringUtils.hasText(refreshTokenHeader) ? refreshTokenHeader : refreshCookie;
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

    private void setRefreshCookie(HttpServletResponse response, RefreshTokenService.RefreshTokenIssueResult refreshIssue) {
        long maxAge = Math.max(0L,
                java.time.Duration.between(
                        java.time.Instant.now(),
                        refreshIssue.expiresAt().atZone(java.time.ZoneOffset.UTC).toInstant()
                ).getSeconds());
        // The Servlet Cookie API has no SameSite setter, so build the
        // Set-Cookie header by hand. The Secure flag is omitted in dev
        // profiles (refresh-cookie-secure=false) because Secure cookies
        // are not sent over plain HTTP, which is how the dev front-end
        // talks to the dev back-end.
        String secureAttr = refreshCookieSecure ? "; Secure" : "";
        String cookieValue = String.format(
                "%s=%s; Path=/auth; Max-Age=%d; HttpOnly%s; SameSite=Strict",
                REFRESH_COOKIE,
                refreshIssue.rawToken(),
                Math.min(maxAge, Integer.MAX_VALUE),
                secureAttr);
        Cookie cookie = new Cookie(REFRESH_COOKIE, refreshIssue.rawToken());
        cookie.setHttpOnly(true);
        cookie.setSecure(refreshCookieSecure);
        cookie.setPath("/auth");
        cookie.setMaxAge((int) Math.min(maxAge, Integer.MAX_VALUE));
        response.addCookie(cookie);
        // The standard Cookie API does not expose SameSite; add a second
        // Set-Cookie header (with the SameSite attribute) so the
        // container is required to merge on serialization. The first
        // Set-Cookie (from addCookie) and the second (from addHeader)
        // carry the same value+attributes; downstream caches will keep
        // one of them per RFC 7234.
        response.addHeader("Set-Cookie", cookieValue);
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
