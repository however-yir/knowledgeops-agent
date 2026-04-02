package com.demo.ai.security;

import io.micrometer.tracing.Tracer;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

@Component("aiRequestContextFilter")
@RequiredArgsConstructor
public class RequestContextFilter extends OncePerRequestFilter {
    private static final String REQUEST_ID_HEADER = "X-Request-Id";
    private final ObjectProvider<Tracer> tracerProvider;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String requestId = request.getHeader(REQUEST_ID_HEADER);
        if (!StringUtils.hasText(requestId)) {
            requestId = UUID.randomUUID().toString();
        }
        String chatId = request.getParameter("chatId");
        String traceId = resolveTraceId();

        MDC.put("request_id", requestId);
        if (StringUtils.hasText(chatId)) {
            MDC.put("chat_id", chatId);
        }
        if (StringUtils.hasText(traceId)) {
            MDC.put("trace_id", traceId);
        }
        response.setHeader(REQUEST_ID_HEADER, requestId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("request_id");
            MDC.remove("chat_id");
            MDC.remove("trace_id");
        }
    }

    private String resolveTraceId() {
        Tracer tracer = tracerProvider.getIfAvailable();
        if (tracer == null || tracer.currentSpan() == null) {
            return "";
        }
        return tracer.currentSpan().context().traceId();
    }
}
