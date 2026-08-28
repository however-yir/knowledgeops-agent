package com.enterprise.iqk.security;

import io.micrometer.tracing.Tracer;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RequestContextFilterTest {

    @SuppressWarnings("unchecked")
    private RequestContextFilter newFilter() {
        ObjectProvider<Tracer> tracerProvider = mock(ObjectProvider.class);
        when(tracerProvider.getIfAvailable()).thenReturn(null);
        return new RequestContextFilter(tracerProvider);
    }

    @Test
    void authenticatedTenantAttributeWinsOverHeader() throws ServletException, IOException {
        RequestContextFilter filter = newFilter();

        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/ai/chat");
        req.setAttribute(TenantContext.TENANT_REQUEST_ATTRIBUTE, "tenant-a");
        req.addHeader(TenantContext.TENANT_HEADER, "tenant-b");
        MockHttpServletResponse resp = new MockHttpServletResponse();
        filter.doFilter(req, resp, (request, response) ->
                assertEquals("tenant-a", MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE)));

        assertEquals("tenant-a", resp.getHeader(TenantContext.TENANT_HEADER));
    }

    @Test
    void headerStillUsedWhenNoAuthenticatedTenant() throws ServletException, IOException {
        RequestContextFilter filter = newFilter();

        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/actuator/health");
        req.addHeader(TenantContext.TENANT_HEADER, "tenant-b");
        MockHttpServletResponse resp = new MockHttpServletResponse();
        filter.doFilter(req, resp, new MockFilterChain());

        assertEquals("tenant-b", resp.getHeader(TenantContext.TENANT_HEADER));
    }
}
