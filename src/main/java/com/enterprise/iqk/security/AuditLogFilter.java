package com.enterprise.iqk.security;

import com.enterprise.iqk.domain.AuditLog;
import com.enterprise.iqk.mapper.AuditLogMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.LocalDateTime;

@Slf4j
@Component
@RequiredArgsConstructor
public class AuditLogFilter extends OncePerRequestFilter {
    private final AuditLogMapper auditLogMapper;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        long started = System.currentTimeMillis();
        try {
            filterChain.doFilter(request, response);
        } finally {
            try {
                long duration = System.currentTimeMillis() - started;
                String uri = request.getRequestURI();
                if (uri.startsWith("/actuator")) {
                    return;
                }
                Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
                String principal = authentication == null ? "anonymous" : authentication.getName();
                String tenantId = resolveTenant(request);
                AuditLog logRecord = AuditLog.builder()
                        .requestId(MDC.get("request_id"))
                        .traceId(MDC.get("trace_id"))
                        .tenantId(tenantId)
                        .userIdentity(principal)
                        .method(request.getMethod())
                        .path(uri)
                        .statusCode(response.getStatus())
                        .durationMs(duration)
                        .chatId(extractChatId(request))
                        .jobId(request.getParameter("jobId"))
                        .extraPayload(buildSafePayload(request))
                        .createdAt(LocalDateTime.now())
                        .build();
                auditLogMapper.insert(logRecord);
            } catch (Exception e) {
                log.warn("Failed to persist audit log", e);
            }
        }
    }

    private String resolveTenant(HttpServletRequest request) {
        Object tenantFromAttr = request.getAttribute(TenantContext.TENANT_REQUEST_ATTRIBUTE);
        if (tenantFromAttr != null && StringUtils.hasText(String.valueOf(tenantFromAttr))) {
            return TenantContext.normalize(String.valueOf(tenantFromAttr));
        }
        return TenantContext.normalize(request.getHeader(TenantContext.TENANT_HEADER));
    }

    private String extractChatId(HttpServletRequest request) {
        String chatId = request.getParameter("chatId");
        if (StringUtils.hasText(chatId)) {
            return chatId;
        }
        String uri = request.getRequestURI();
        String[] tokens = uri.split("/");
        for (int i = 0; i < tokens.length; i++) {
            if ("upload".equals(tokens[i]) && i + 1 < tokens.length) {
                return tokens[i + 1];
            }
        }
        return "";
    }

    private String buildSafePayload(HttpServletRequest request) {
        String query = request.getQueryString();
        if (!StringUtils.hasText(query)) {
            return "";
        }
        String safe = query
                .replaceAll("(?i)(api[-_]?key=)[^&]+", "$1***")
                .replaceAll("(?i)(token=)[^&]+", "$1***")
                .replaceAll("(?i)(contact(_info)?=)[^&]+", "$1***");
        return safe.length() <= 1000 ? safe : safe.substring(0, 1000);
    }
}
