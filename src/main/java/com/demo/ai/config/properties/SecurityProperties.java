package com.demo.ai.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "app.security")
public class SecurityProperties {
    private boolean enabled = false;
    private String jwtSecret = "change-me-change-me-change-me-change-me";
    private int jwtExpireMinutes = 120;
    private int refreshExpireDays = 14;
    private int apiKeyExpireDays = 30;
}
