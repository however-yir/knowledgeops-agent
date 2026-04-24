package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Data
@ConfigurationProperties(prefix = "app.security")
public class SecurityProperties {
    private boolean enabled = true;
    private String jwtSecret;
    private int jwtExpireMinutes = 120;
    private int refreshExpireDays = 14;
    private int apiKeyExpireDays = 30;
}
