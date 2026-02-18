package com.enterprise.iqk.llm;

import com.enterprise.iqk.config.properties.ModelRouterProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class ModelRouter {
    private static final String DEFAULT_MODEL = "qwen-plus";

    private final ModelRouterProperties modelRouterProperties;

    public ModelRouteDecision resolve(String requestedProfile, String endpoint) {
        String initialProfile = normalizeProfile(selectInitialProfile(requestedProfile, endpoint));
        if (!modelRouterProperties.isEnabled()) {
            return resolveDisabled(initialProfile);
        }
        return resolveEnabled(initialProfile);
    }

    private ModelRouteDecision resolveDisabled(String initialProfile) {
        if (hasRoute(initialProfile)) {
            ModelRouterProperties.RouteProfile profile = modelRouterProperties.getProfiles().get(initialProfile);
            return new ModelRouteDecision(initialProfile,
                    profile.getModel(),
                    safeCostTier(profile.getCostTier()),
                    false,
                    "router_disabled_profile_direct");
        }
        return new ModelRouteDecision(initialProfile, DEFAULT_MODEL, "balanced", false, "router_disabled_default");
    }

    private ModelRouteDecision resolveEnabled(String initialProfile) {
        Set<String> visited = new LinkedHashSet<>();
        String current = initialProfile;
        while (StringUtils.hasText(current) && !visited.contains(current)) {
            visited.add(current);
            ModelRouterProperties.RouteProfile route = modelRouterProperties.getProfiles().get(current);
            if (route != null && route.isEnabled() && StringUtils.hasText(route.getModel())) {
                return new ModelRouteDecision(current,
                        route.getModel(),
                        safeCostTier(route.getCostTier()),
                        !current.equals(initialProfile),
                        !current.equals(initialProfile) ? "fallback_chain" : "profile_match");
            }
            String fallback = route == null ? "" : normalizeProfile(route.getFallbackProfile());
            if (!StringUtils.hasText(fallback)) {
                fallback = normalizeProfile(modelRouterProperties.getDefaultProfile());
            }
            if (!StringUtils.hasText(fallback) || visited.contains(fallback)) {
                break;
            }
            current = fallback;
        }
        for (Map.Entry<String, ModelRouterProperties.RouteProfile> entry : modelRouterProperties.getProfiles().entrySet()) {
            ModelRouterProperties.RouteProfile route = entry.getValue();
            if (route != null && route.isEnabled() && StringUtils.hasText(route.getModel())) {
                return new ModelRouteDecision(entry.getKey(),
                        route.getModel(),
                        safeCostTier(route.getCostTier()),
                        !entry.getKey().equals(initialProfile),
                        "first_enabled_fallback");
            }
        }
        return new ModelRouteDecision(initialProfile, DEFAULT_MODEL, "balanced", true, "default_model_fallback");
    }

    private String selectInitialProfile(String requestedProfile, String endpoint) {
        if (StringUtils.hasText(requestedProfile)) {
            return requestedProfile;
        }
        if (StringUtils.hasText(endpoint)) {
            String endpointProfile = modelRouterProperties.getEndpointProfiles().get(normalizeProfile(endpoint));
            if (StringUtils.hasText(endpointProfile)) {
                return endpointProfile;
            }
        }
        return modelRouterProperties.getDefaultProfile();
    }

    private boolean hasRoute(String profile) {
        return StringUtils.hasText(profile)
                && modelRouterProperties.getProfiles().containsKey(profile)
                && StringUtils.hasText(modelRouterProperties.getProfiles().get(profile).getModel());
    }

    private String normalizeProfile(String profile) {
        if (!StringUtils.hasText(profile)) {
            return "";
        }
        return profile.trim().toLowerCase(Locale.ROOT);
    }

    private String safeCostTier(String costTier) {
        return StringUtils.hasText(costTier) ? costTier : "balanced";
    }

    public record ModelRouteDecision(String profile,
                                     String model,
                                     String costTier,
                                     boolean fallbackApplied,
                                     String reason) {
    }
}
