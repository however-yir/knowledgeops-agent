package com.demo.ai.security;

import com.demo.ai.config.properties.SecurityProperties;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

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
                .source("api_key")
                .build());
        ApiKeyOrJwtAuthFilter filter = new ApiKeyOrJwtAuthFilter(props, apiKeyAuthService, jwtService);

        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/ai/chat");
        req.addHeader("X-API-Key", "ak");
        MockHttpServletResponse resp = new MockHttpServletResponse();
        filter.doFilter(req, resp, new MockFilterChain());
        assertEquals(200, resp.getStatus());
    }
}
