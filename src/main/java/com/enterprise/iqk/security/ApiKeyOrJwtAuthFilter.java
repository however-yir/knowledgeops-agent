package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.SecurityProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.stream.Stream;

@Component
@RequiredArgsConstructor
public class ApiKeyOrJwtAuthFilter extends OncePerRequestFilter {
    private static final String API_KEY_HEADER = "X-API-Key";

    private final SecurityProperties securityProperties;
    private final ApiKeyAuthService apiKeyAuthService;
    private final JwtService jwtService;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        if (!securityProperties.isEnabled()) {
            filterChain.doFilter(request, response);
            return;
        }
        if (isPublic(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }
        AuthIdentity identity = resolveIdentity(request);
        if (identity == null) {
            unauthorized(response, "missing or invalid credentials");
            return;
        }
        List<SimpleGrantedAuthority> roleAuthorities = (identity.getRoles() == null ? List.<String>of() : identity.getRoles()).stream()
                .filter(StringUtils::hasText)
                .map(role -> role.startsWith("ROLE_") ? role : "ROLE_" + role)
                .map(SimpleGrantedAuthority::new)
                .toList();
        List<SimpleGrantedAuthority> permissionAuthorities = identity.getPermissions() == null
                ? List.of()
                : identity.getPermissions().stream()
                .filter(StringUtils::hasText)
                .map(perm -> "PERM_" + perm.replace(':', '_').toUpperCase())
                .map(SimpleGrantedAuthority::new)
                .toList();
        List<SimpleGrantedAuthority> authorities = Stream.concat(roleAuthorities.stream(), permissionAuthorities.stream())
                .toList();
        UsernamePasswordAuthenticationToken authenticationToken =
                new UsernamePasswordAuthenticationToken(identity.getPrincipal(), identity.getSource(), authorities);
        SecurityContextHolder.getContext().setAuthentication(authenticationToken);
        filterChain.doFilter(request, response);
    }

    private AuthIdentity resolveIdentity(HttpServletRequest request) {
        String authorization = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (StringUtils.hasText(authorization) && authorization.startsWith("Bearer ")) {
            String token = authorization.substring("Bearer ".length()).trim();
            AuthIdentity jwtIdentity = jwtService.parse(token);
            if (jwtIdentity != null) {
                return jwtIdentity;
            }
        }
        return apiKeyAuthService.authenticate(request.getHeader(API_KEY_HEADER));
    }

    private boolean isPublic(String uri) {
        return uri.startsWith("/actuator/health")
                || uri.startsWith("/actuator/info")
                || uri.startsWith("/v3/api-docs")
                || uri.startsWith("/swagger-ui")
                || uri.startsWith("/auth/token")
                || uri.startsWith("/auth/refresh")
                || uri.startsWith("/error");
    }

    private void unauthorized(HttpServletResponse response, String msg) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write("{\"ok\":0,\"msg\":\"" + msg + "\"}");
    }
}
