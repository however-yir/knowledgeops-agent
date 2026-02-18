package com.enterprise.iqk.config.properties;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.LinkedHashMap;
import java.util.Map;

@Data
@ConfigurationProperties(prefix = "app.model-router")
public class ModelRouterProperties {
    private boolean enabled = true;
    private String defaultProfile = "balanced";
    private Map<String, String> endpointProfiles = new LinkedHashMap<>();
    private Map<String, RouteProfile> profiles = new LinkedHashMap<>();

    @Data
    public static class RouteProfile {
        private String model;
        private String costTier = "balanced";
        private boolean enabled = true;
        private String fallbackProfile;
    }
}
