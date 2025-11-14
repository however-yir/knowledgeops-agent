package com.enterprise.iqk.security;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@RequiredArgsConstructor
public class HttpMetricsFilter extends OncePerRequestFilter {
    private final MeterRegistry meterRegistry;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        Timer.Sample sample = Timer.start(meterRegistry);
        try {
            filterChain.doFilter(request, response);
        } finally {
            sample.stop(Timer.builder("http.requests.latency")
                    .tag("method", request.getMethod())
                    .tag("path", normalizePath(request.getRequestURI()))
                    .tag("status", String.valueOf(response.getStatus()))
                    .register(meterRegistry));
        }
    }

    private String normalizePath(String raw) {
        if (raw == null || raw.isBlank()) {
            return "/";
        }
        if (raw.startsWith("/actuator")) {
            return "/actuator";
        }
        if (raw.startsWith("/ai/pdf/file/")) {
            return "/ai/pdf/file/{chatId}";
        }
        if (raw.startsWith("/ingestion/jobs/")) {
            return "/ingestion/jobs/{jobId}";
        }
        return raw;
    }
}
