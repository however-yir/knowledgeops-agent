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
import org.springframework.scheduling.annotation.Scheduled;
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
    // Hard ceiling on the per-process bucket map so a burst of distinct keys
    // cannot exhaust the JVM. Once exceeded we drop everything; legitimate
    // callers rebuild their bucket on the next request.
    private static final int MAX_BUCKETS = 50_000;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        if (!rateLimitProperties.isEnabled() || request.getRequestURI().startsWith("/actuator")) {
            filterChain.doFilter(request, response);
            return;
        }
        String key = resolveKey(request);
        if (buckets.size() >= MAX_BUCKETS) {
            // Memory-safety guard: when the map is full (likely a flood of
            // distinct keys), drop everything before adding a new entry.
            buckets.clear();
        }
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
        return "tenant:" + tenantId + ":ip:" + resolveClientIp(request);
    }

    /**
     * Pick the most useful client IP for the rate-limit key. When the
     * request comes through a reverse proxy, the direct {@code RemoteAddr}
     * is the proxy's own address, so every anonymous caller would share
     * one bucket and a single attacker could exhaust the limit for the
     * whole tenant. Parse {@code X-Forwarded-For} only when the direct
     * peer is a private/loopback address (i.e. we are behind a proxy),
     * and prefer the rightmost non-private address so a malicious caller
     * cannot inject a fake leftmost entry to rotate their own bucket.
     */
    static String resolveClientIp(HttpServletRequest request) {
        String direct = StringUtils.hasText(request.getRemoteAddr()) ? request.getRemoteAddr() : "unknown";
        String forwarded = request.getHeader("X-Forwarded-For");
        if (!StringUtils.hasText(forwarded)) {
            return direct;
        }
        if (!isPrivateOrLoopback(direct)) {
            // Direct peer is already a public address, so the X-Forwarded-For
            // header would be untrusted. Keep using the direct address.
            return direct;
        }
        String[] hops = forwarded.split(",");
        for (int i = hops.length - 1; i >= 0; i--) {
            String hop = hops[i].trim();
            if (StringUtils.hasText(hop) && !isPrivateOrLoopback(hop)) {
                return hop;
            }
        }
        return direct;
    }

    private static boolean isPrivateOrLoopback(String ip) {
        if (ip == null) {
            return false;
        }
        if ("127.0.0.1".equals(ip) || "::1".equals(ip) || "0:0:0:0:0:0:0:1".equals(ip)) {
            return true;
        }
        // Simple textual prefix check covers the common RFC1918 / link-local
        // ranges. InetAddress parsing is intentionally avoided here because
        // X-Forwarded-For is a string and we want to fail closed (treat
        // unparseable values as not-private so we keep using the direct
        // address).
        if (ip.startsWith("10.") || ip.startsWith("192.168.")) {
            return true;
        }
        if (ip.startsWith("169.254.")) {
            return true;
        }
        if (ip.startsWith("172.")) {
            int firstDot = ip.indexOf('.', 4);
            if (firstDot > 0) {
                try {
                    int second = Integer.parseInt(ip.substring(4, firstDot));
                    if (second >= 16 && second <= 31) {
                        return true;
                    }
                } catch (NumberFormatException ignored) {
                    // fall through
                }
            }
        }
        return false;
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

    /**
     * Drops buckets that fully refilled (idle for at least the refill window) so the
     * per-tenant/per-IP bucket map does not grow without bound. Scheduler-based
     * eviction is safe: keys knocked out simply start with a fresh bucket.
     */
    @Scheduled(fixedDelayString = "${app.rate-limit.evict-interval-ms:300000}")
    public void evictIdleBuckets() {
        if (!rateLimitProperties.isEnabled()) {
            return;
        }
        if (buckets.isEmpty()) {
            return;
        }
        long capacity = rateLimitProperties.getCapacity();
        buckets.entrySet().removeIf(entry -> entry.getValue().getAvailableTokens() >= capacity);
    }
}
