package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.RateLimitProperties;
import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.Bucket;
import io.github.bucket4j.Refill;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
@RequiredArgsConstructor
public class RateLimitFilter extends OncePerRequestFilter {
    private final RateLimitProperties rateLimitProperties;
    private final Map<String, Bucket> buckets = new ConcurrentHashMap<>();

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        if (!rateLimitProperties.isEnabled() || request.getRequestURI().startsWith("/actuator")) {
            filterChain.doFilter(request, response);
            return;
        }
        String key = resolveKey(request);
        Bucket bucket = buckets.computeIfAbsent(key, k -> newBucket());
        if (!bucket.tryConsume(1)) {
            response.setStatus(429);
            response.setContentType("application/json");
            response.getWriter().write("{\"ok\":0,\"msg\":\"rate limit exceeded\"}");
            return;
        }
        filterChain.doFilter(request, response);
    }

    private String resolveKey(HttpServletRequest request) {
        String tenantId = resolveTenant(request);
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null && StringUtils.hasText(authentication.getName())) {
            return "tenant:" + tenantId + ":principal:" + authentication.getName();
        }
        String remoteIp = StringUtils.hasText(request.getRemoteAddr()) ? request.getRemoteAddr() : "unknown";
        return "tenant:" + tenantId + ":ip:" + remoteIp;
    }

    private String resolveTenant(HttpServletRequest request) {
        Object tenantFromAttr = request.getAttribute(TenantContext.TENANT_REQUEST_ATTRIBUTE);
        if (tenantFromAttr != null && StringUtils.hasText(String.valueOf(tenantFromAttr))) {
            return TenantContext.normalize(String.valueOf(tenantFromAttr));
        }
        return TenantContext.normalize(request.getHeader(TenantContext.TENANT_HEADER));
    }

    private Bucket newBucket() {
        Refill refill = Refill.greedy(rateLimitProperties.getRefillTokens(),
                Duration.ofSeconds(rateLimitProperties.getRefillSeconds()));
        Bandwidth limit = Bandwidth.classic(rateLimitProperties.getCapacity(), refill);
        return Bucket.builder().addLimit(limit).build();
    }
}
