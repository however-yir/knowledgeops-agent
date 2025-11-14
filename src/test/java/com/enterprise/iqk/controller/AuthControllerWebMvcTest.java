package com.enterprise.iqk.controller;

import com.enterprise.iqk.config.properties.SecurityProperties;
import com.enterprise.iqk.security.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(value = AuthController.class, excludeFilters = {
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = ApiKeyOrJwtAuthFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RateLimitFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = AuditLogFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = HttpMetricsFilter.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RequestContextFilter.class)
})
@AutoConfigureMockMvc(addFilters = false)
class AuthControllerWebMvcTest {
    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ApiKeyAuthService apiKeyAuthService;
    @MockBean
    private ApiKeyLifecycleService apiKeyLifecycleService;
    @MockBean
    private JwtService jwtService;
    @MockBean
    private RefreshTokenService refreshTokenService;
    @MockBean
    private PermissionService permissionService;
    @MockBean
    private SecurityProperties securityProperties;

    @Test
    void shouldIssueAccessAndRefreshTokens() throws Exception {
        when(apiKeyAuthService.authenticate("abc")).thenReturn(AuthIdentity.builder()
                .principal("tester")
                .roles(List.of("ADMIN"))
                .permissions(List.of("chat:write"))
                .source("api_key")
                .build());
        when(permissionService.permissionsForRoles(any())).thenReturn(List.of("chat:write"));
        when(jwtService.issueToken(any(), any(), any())).thenReturn("jwt-token");
        when(refreshTokenService.issue(any(), any())).thenReturn("refresh-token");
        when(securityProperties.getJwtExpireMinutes()).thenReturn(120);

        mockMvc.perform(post("/auth/token").header("X-API-Key", "abc").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(1))
                .andExpect(jsonPath("$.token").value("jwt-token"))
                .andExpect(jsonPath("$.refreshToken").value("refresh-token"));
    }

    @Test
    void shouldRotateApiKey() throws Exception {
        when(apiKeyLifecycleService.rotate("legacy", "manual"))
                .thenReturn(new ApiKeyLifecycleService.ApiKeyIssueResult("new-raw", "legacy-v2", LocalDateTime.now().plusDays(30)));

        mockMvc.perform(post("/auth/api-keys/rotate")
                        .param("keyName", "legacy")
                        .param("reason", "manual"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(1))
                .andExpect(jsonPath("$.rawApiKey").value("new-raw"));
    }
}
