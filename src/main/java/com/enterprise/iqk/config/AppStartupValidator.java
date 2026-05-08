package com.enterprise.iqk.config;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

/**
 * Validates critical security properties at startup.
 * Fails fast if prod-relevant settings are missing or insecure.
 */
@Configuration
public class AppStartupValidator {

    private static final String DEFAULT_JWT_SECRET = "dev-jwt-secret-change-this-in-prod-123456";

    @Value("${app.security.enabled:true}")
    private boolean securityEnabled;

    @Value("${app.security.jwt-secret:}")
    private String jwtSecret;

    @PostConstruct
    void validate() {
        if (!securityEnabled) {
            return;
        }
        if (jwtSecret == null || jwtSecret.isBlank()) {
            throw new IllegalStateException(
                    "app.security.jwt-secret must not be blank when security is enabled");
        }
        if (DEFAULT_JWT_SECRET.equals(jwtSecret)) {
            throw new IllegalStateException(
                    "app.security.jwt-secret must not use the well-known default value");
        }
    }
}
