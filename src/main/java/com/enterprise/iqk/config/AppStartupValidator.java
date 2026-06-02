package com.enterprise.iqk.config;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import java.util.Set;

/**
 * Validates critical security properties at startup.
 * Fails fast if prod-relevant settings are missing or insecure.
 */
@Configuration
public class AppStartupValidator {

    private static final String DEFAULT_JWT_SECRET = "dev-jwt-secret-change-this-in-prod-123456";
    private static final Set<String> FORBIDDEN_JWT_SECRETS = Set.of(
            DEFAULT_JWT_SECRET,
            "replace-me-with-real-secret",
            "change-me",
            "changeme"
    );

    private final Environment environment;

    public AppStartupValidator(Environment environment) {
        this.environment = environment;
    }

    @Value("${app.security.enabled:true}")
    private boolean securityEnabled;

    @Value("${app.security.jwt-secret:}")
    private String jwtSecret;

    @Value("${spring.rabbitmq.username:}")
    private String rabbitUsername;

    @Value("${spring.rabbitmq.password:}")
    private String rabbitPassword;

    @PostConstruct
    void validate() {
        if (isProdProfile() && !securityEnabled) {
            throw new IllegalStateException(
                    "app.security.enabled must be true when the prod profile is active");
        }
        if (!securityEnabled) {
            return;
        }
        if (jwtSecret == null || jwtSecret.isBlank()) {
            throw new IllegalStateException(
                    "app.security.jwt-secret must not be blank when security is enabled");
        }
        if (FORBIDDEN_JWT_SECRETS.contains(jwtSecret)) {
            throw new IllegalStateException(
                    "app.security.jwt-secret must not use a well-known default or placeholder value");
        }
        if (isProdProfile() && usesRabbitGuestCredentials()) {
            throw new IllegalStateException(
                    "spring.rabbitmq guest/guest credentials are not allowed when the prod profile is active");
        }
    }

    private boolean isProdProfile() {
        return environment.acceptsProfiles(Profiles.of("prod"));
    }

    private boolean usesRabbitGuestCredentials() {
        return "guest".equals(rabbitUsername) && "guest".equals(rabbitPassword);
    }
}
