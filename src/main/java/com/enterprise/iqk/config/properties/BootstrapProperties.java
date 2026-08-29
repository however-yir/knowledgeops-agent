package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Operator-provided bootstrap credential for deployments where repository
 * committed demo keys have been revoked (Flyway V15) and production must not
 * seed them. Binding prefix {@code app.bootstrap} maps
 * APP_BOOTSTRAP_API_KEY / APP_BOOTSTRAP_KEY_NAME / APP_BOOTSTRAP_TENANT_ID
 * so the Python runtime and the cross-runtime contract stack share one
 * environment surface.
 */
@Data
@ConfigurationProperties(prefix = "app.bootstrap")
public class BootstrapProperties {
    private String apiKey;
    private String keyName = "bootstrap-admin";
    private String tenantId = "public";
    private String role = "ADMIN";
}
