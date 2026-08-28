package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.SecurityProperties;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.slf4j.MDC;

import java.io.IOException;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ApiKeyOrJwtAuthFilterTest {

    @Test
    void shouldReturn401WithoutCredentials() throws ServletException, IOException {
        SecurityProperties props = new SecurityProperties();
        props.setEnabled(true);
        ApiKeyAuthService apiKeyAuthService = mock(ApiKeyAuthService.class);
        JwtService jwtService = mock(JwtService.class);
        ApiKeyOrJwtAuthFilter filter = new ApiKeyOrJwtAuthFilter(props, apiKeyAuthService, jwtService);

        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/ai/chat");
        MockHttpServletResponse resp = new MockHttpServletResponse();
        filter.doFilter(req, resp, new MockFilterChain());
        assertEquals(401, resp.getStatus());
    }

    @Test
    void shouldPassWithApiKey() throws ServletException, IOException {
        SecurityProperties props = new SecurityProperties();
        props.setEnabled(true);
        ApiKeyAuthService apiKeyAuthService = mock(ApiKeyAuthService.class);
        JwtService jwtService = mock(JwtService.class);
        when(apiKeyAuthService.authenticate("ak")).thenReturn(AuthIdentity.builder()
                .principal("tester")
                .roles(List.of("ADMIN"))
                .permissions(List.of("chat:write"))
                .tenantId("tenant-a")
                .source("api_key")
                .build());
        ApiKeyOrJwtAuthFilter filter = new ApiKeyOrJwtAuthFilter(props, apiKeyAuthService, jwtService);

        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/ai/chat");
        req.addHeader("X-API-Key", "ak");
        req.addHeader(TenantContext.TENANT_HEADER, "tenant-b");
        MockHttpServletResponse resp = new MockHttpServletResponse();
        filter.doFilter(req, resp, (request, response) -> {
            assertEquals("tenant-a", request.getAttribute(TenantContext.TENANT_REQUEST_ATTRIBUTE));
            assertEquals("tenant-a", MDC.get(TenantContext.TENANT_REQUEST_ATTRIBUTE));
        });
        assertEquals(200, resp.getStatus());
        assertEquals("tenant-a", resp.getHeader(TenantContext.TENANT_HEADER));
    }
}
