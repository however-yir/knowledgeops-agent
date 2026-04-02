package com.demo.ai.config;

import com.demo.ai.config.properties.SecurityProperties;
import com.demo.ai.security.ApiKeyOrJwtAuthFilter;
import com.demo.ai.security.AuditLogFilter;
import com.demo.ai.security.HttpMetricsFilter;
import com.demo.ai.security.RateLimitFilter;
import com.demo.ai.security.RequestContextFilter;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableMethodSecurity
@RequiredArgsConstructor
public class SecurityConfiguration {

    private final SecurityProperties securityProperties;
    private final RequestContextFilter requestContextFilter;
    private final ApiKeyOrJwtAuthFilter apiKeyOrJwtAuthFilter;
    private final RateLimitFilter rateLimitFilter;
    private final AuditLogFilter auditLogFilter;
    private final HttpMetricsFilter httpMetricsFilter;

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf.disable())
                .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        if (!securityProperties.isEnabled()) {
            http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
        } else {
            http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/actuator/health", "/actuator/info", "/error").permitAll()
                    .requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                    .requestMatchers("/actuator/prometheus").hasAnyAuthority("PERM_METRICS_READ", "ROLE_ADMIN", "ROLE_OPS")
                    .requestMatchers(HttpMethod.GET, "/audit/logs").hasAnyAuthority("PERM_AUDIT_READ", "ROLE_ADMIN", "ROLE_OPS")
                    .requestMatchers(HttpMethod.POST, "/auth/token", "/auth/refresh").permitAll()
                    .requestMatchers(HttpMethod.POST, "/auth/api-keys/**").hasAnyAuthority("PERM_AUTH_KEY_MANAGE", "ROLE_ADMIN")
                    .requestMatchers(HttpMethod.GET, "/ai/chat", "/ai/service").hasAnyAuthority("PERM_CHAT_READ", "PERM_CHAT_WRITE", "ROLE_ADMIN")
                    .requestMatchers(HttpMethod.POST, "/ai/chat", "/ai/service").hasAnyAuthority("PERM_CHAT_WRITE", "ROLE_ADMIN")
                    .requestMatchers(HttpMethod.GET, "/ai/pdf/chat", "/ai/pdf/file/**").hasAnyAuthority("PERM_RAG_READ", "ROLE_ADMIN")
                    .requestMatchers(HttpMethod.POST, "/ai/pdf/upload/**", "/ingestion/upload/**").hasAnyAuthority("PERM_INGESTION_WRITE", "ROLE_ADMIN")
                    .requestMatchers(HttpMethod.GET, "/ingestion/jobs/**", "/ingestion/jobs").hasAnyAuthority("PERM_INGESTION_READ", "PERM_INGESTION_WRITE", "ROLE_ADMIN", "ROLE_OPS")
                    .requestMatchers(HttpMethod.POST, "/ingestion/jobs/process").hasRole("ADMIN")
                    .requestMatchers("/ingestion/**", "/ai/pdf/**").hasAnyAuthority("PERM_INGESTION_WRITE", "ROLE_ADMIN")
                    .anyRequest().authenticated()
            );
        }

        http.addFilterBefore(requestContextFilter, UsernamePasswordAuthenticationFilter.class);
        http.addFilterAfter(httpMetricsFilter, RequestContextFilter.class);
        http.addFilterBefore(apiKeyOrJwtAuthFilter, UsernamePasswordAuthenticationFilter.class);
        http.addFilterAfter(rateLimitFilter, ApiKeyOrJwtAuthFilter.class);
        http.addFilterAfter(auditLogFilter, RateLimitFilter.class);
        return http.build();
    }
}
