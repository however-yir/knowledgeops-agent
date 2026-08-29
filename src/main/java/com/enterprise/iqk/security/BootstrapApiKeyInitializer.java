package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.BootstrapProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/**
 * Seeds an operator-provided bootstrap ADMIN credential at startup when
 * APP_BOOTSTRAP_API_KEY is configured. Repository-committed demo keys were
 * revoked by Flyway V15; this is the explicit per-deployment equivalent (the
 * Python runtime ships the same mechanism via the same environment name).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class BootstrapApiKeyInitializer implements ApplicationRunner {

    private final ApiKeyLifecycleService apiKeyLifecycleService;
    private final BootstrapProperties properties;

    @Override
    public void run(ApplicationArguments args) {
        String rawKey = properties.getApiKey();
        if (!StringUtils.hasText(rawKey)) {
            return;
        }
        try {
            ApiKeyLifecycleService.ApiKeyIssueResult result =
                    apiKeyLifecycleService.provision(rawKey, properties.getKeyName(), properties.getRole(), properties.getTenantId());
            if (result.rawApiKey() != null) {
                log.info("bootstrap api key '{}' provisioned for tenant '{}' (expires {})",
                        result.keyName(), result.tenantId(), result.expiresAt());
            } else {
                log.info("bootstrap api key '{}' already active for tenant '{}'", result.keyName(), result.tenantId());
            }
        } catch (RuntimeException exc) {
            // Fail closed: a misconfigured bootstrap credential must surface at
            // startup instead of leaving the deployment without an admin.
            throw new IllegalStateException("failed to provision bootstrap api key '" + properties.getKeyName() + "'", exc);
        }
    }
}
