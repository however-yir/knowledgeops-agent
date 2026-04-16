package com.enterprise.iqk.llm;

import com.enterprise.iqk.config.properties.ModelRouterProperties;
import com.enterprise.iqk.domain.ModelAbExposure;
import com.enterprise.iqk.mapper.ModelAbExposureMapper;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Service
public class ModelRouter {
    private static final String DEFAULT_MODEL = "qwen-plus";

    private final ModelRouterProperties modelRouterProperties;
    private final ModelAbExposureMapper modelAbExposureMapper;

    public ModelRouter(ModelRouterProperties modelRouterProperties) {
        this.modelRouterProperties = modelRouterProperties;
        this.modelAbExposureMapper = null;
    }

    @Autowired
    public ModelRouter(ModelRouterProperties modelRouterProperties,
                       ObjectProvider<ModelAbExposureMapper> modelAbExposureMapperProvider) {
        this.modelRouterProperties = modelRouterProperties;
        this.modelAbExposureMapper = modelAbExposureMapperProvider.getIfAvailable();
    }

    public ModelRouteDecision resolve(String requestedProfile, String endpoint) {
        return resolve(requestedProfile, endpoint, "public", "");
    }

    public ModelRouteDecision resolve(String requestedProfile,
                                      String endpoint,
                                      String tenantId,
                                      String subjectKey) {
        String normalizedTenant = normalizeTenant(tenantId);
        ExperimentRouting experiment = applyExperiment(requestedProfile, endpoint, normalizedTenant, subjectKey);
        String initialProfile = normalizeProfile(selectInitialProfile(experiment.routedProfile(), endpoint));

        ModelRouteDecision baseDecision;
        if (!modelRouterProperties.isEnabled()) {
            baseDecision = resolveDisabled(initialProfile);
        } else {
            baseDecision = resolveEnabled(initialProfile);
        }

        ModelRouteDecision decision = new ModelRouteDecision(
                baseDecision.profile(),
                baseDecision.model(),
                baseDecision.costTier(),
                baseDecision.fallbackApplied(),
                baseDecision.reason(),
                experiment.experimentKey(),
                experiment.variant(),
                experiment.bucket()
        );
        saveExposure(normalizedTenant, endpoint, subjectKey, decision);
        return decision;
    }

    private void saveExposure(String tenantId, String endpoint, String subjectKey, ModelRouteDecision decision) {
        if (modelAbExposureMapper == null || !StringUtils.hasText(decision.experimentKey())) {
            return;
        }
        try {
            modelAbExposureMapper.insert(ModelAbExposure.builder()
                    .tenantId(normalizeTenant(tenantId))
                    .experimentKey(decision.experimentKey())
                    .subjectKey(StringUtils.hasText(subjectKey) ? subjectKey : "na")
                    .endpoint(StringUtils.hasText(endpoint) ? endpoint : "unknown")
                    .bucket(decision.experimentBucket() == null ? -1 : decision.experimentBucket())
                    .variant(StringUtils.hasText(decision.experimentVariant()) ? decision.experimentVariant() : "unknown")
                    .routedProfile(decision.profile())
                    .createdAt(LocalDateTime.now())
                    .build());
        } catch (Exception ignored) {
            // exposure logging should never break routing path
        }
    }

    private ExperimentRouting applyExperiment(String requestedProfile,
                                              String endpoint,
                                              String tenantId,
                                              String subjectKey) {
        String normalizedRequested = normalizeProfile(requestedProfile);
        if ("quality_first".equals(normalizedRequested) || "quality-priority".equals(normalizedRequested)) {
            return new ExperimentRouting("quality", "manual_quality_first", "quality", 100);
        }
        if ("cost_first".equals(normalizedRequested) || "cost-priority".equals(normalizedRequested)) {
            return new ExperimentRouting("economy", "manual_cost_first", "cost", 0);
        }

        ModelRouterProperties.AbExperiment experiment = modelRouterProperties.getQualityCostExperiment();
        String triggerProfile = normalizeProfile(experiment.getTriggerProfile());
        boolean triggerMatched = StringUtils.hasText(triggerProfile) && triggerProfile.equals(normalizedRequested);
        if (!experiment.isEnabled() || !triggerMatched) {
            return new ExperimentRouting(normalizedRequested, "", "", null);
        }

        int qualityPercent = Math.min(100, Math.max(0, experiment.getQualityPercent()));
        String normalizedEndpoint = StringUtils.hasText(endpoint) ? normalizeProfile(endpoint) : "na";
        String normalizedSubject = StringUtils.hasText(subjectKey) ? subjectKey.trim() : "na";
        int bucket = Math.floorMod((tenantId + "|" + normalizedEndpoint + "|" + normalizedSubject).hashCode(), 100);
        boolean qualityVariant = bucket < qualityPercent;
        String variant = qualityVariant ? "quality" : "cost";
        String routedProfile = qualityVariant ? "quality" : "economy";
        return new ExperimentRouting(
                routedProfile,
                StringUtils.hasText(experiment.getExperimentKey()) ? experiment.getExperimentKey() : "quality_vs_cost",
                variant,
                bucket
        );
    }

    private ModelRouteDecision resolveDisabled(String initialProfile) {
        if (hasRoute(initialProfile)) {
            ModelRouterProperties.RouteProfile profile = modelRouterProperties.getProfiles().get(initialProfile);
            return new ModelRouteDecision(initialProfile,
                    profile.getModel(),
                    safeCostTier(profile.getCostTier()),
                    false,
                    "router_disabled_profile_direct",
                    "",
                    "",
                    null);
        }
        return new ModelRouteDecision(initialProfile, DEFAULT_MODEL, "balanced", false, "router_disabled_default", "", "", null);
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
                        !current.equals(initialProfile) ? "fallback_chain" : "profile_match",
                        "",
                        "",
                        null);
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
                        "first_enabled_fallback",
                        "",
                        "",
                        null);
            }
        }
        return new ModelRouteDecision(initialProfile, DEFAULT_MODEL, "balanced", true, "default_model_fallback", "", "", null);
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

    private String normalizeTenant(String tenantId) {
        if (!StringUtils.hasText(tenantId)) {
            return "public";
        }
        return tenantId.trim();
    }

    public record ModelRouteDecision(String profile,
                                     String model,
                                     String costTier,
                                     boolean fallbackApplied,
                                     String reason,
                                     String experimentKey,
                                     String experimentVariant,
                                     Integer experimentBucket) {
    }

    private record ExperimentRouting(String routedProfile,
                                     String experimentKey,
                                     String variant,
                                     Integer bucket) {
    }
}
