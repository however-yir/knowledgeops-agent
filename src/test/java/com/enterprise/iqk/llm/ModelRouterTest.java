package com.enterprise.iqk.llm;

import com.enterprise.iqk.config.properties.ModelRouterProperties;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModelRouterTest {

    @Test
    void shouldResolveByRequestedProfile() {
        ModelRouter router = new ModelRouter(buildProperties(true));

        ModelRouter.ModelRouteDecision decision = router.resolve("quality", "chat");

        assertEquals("quality", decision.profile());
        assertEquals("qwen-max", decision.model());
        assertEquals("high", decision.costTier());
        assertTrue(!decision.fallbackApplied());
    }

    @Test
    void shouldFallbackToBalancedWhenProfileDisabled() {
        ModelRouterProperties properties = buildProperties(true);
        properties.getProfiles().get("quality").setEnabled(false);
        ModelRouter router = new ModelRouter(properties);

        ModelRouter.ModelRouteDecision decision = router.resolve("quality", "chat");

        assertEquals("balanced", decision.profile());
        assertEquals("qwen-plus", decision.model());
        assertTrue(decision.fallbackApplied());
    }

    @Test
    void shouldUseEndpointDefaultWhenNoRequestedProfile() {
        ModelRouter router = new ModelRouter(buildProperties(true));

        ModelRouter.ModelRouteDecision decision = router.resolve("", "service");

        assertEquals("quality", decision.profile());
        assertEquals("qwen-max", decision.model());
    }

    private ModelRouterProperties buildProperties(boolean enabled) {
        ModelRouterProperties properties = new ModelRouterProperties();
        properties.setEnabled(enabled);
        properties.setDefaultProfile("balanced");
        properties.setEndpointProfiles(Map.of(
                "chat", "balanced",
                "service", "quality",
                "rag", "balanced"
        ));

        ModelRouterProperties.RouteProfile economy = new ModelRouterProperties.RouteProfile();
        economy.setModel("qwen-turbo");
        economy.setCostTier("low");

        ModelRouterProperties.RouteProfile balanced = new ModelRouterProperties.RouteProfile();
        balanced.setModel("qwen-plus");
        balanced.setCostTier("medium");
        balanced.setFallbackProfile("economy");

        ModelRouterProperties.RouteProfile quality = new ModelRouterProperties.RouteProfile();
        quality.setModel("qwen-max");
        quality.setCostTier("high");
        quality.setFallbackProfile("balanced");

        properties.setProfiles(Map.of(
                "economy", economy,
                "balanced", balanced,
                "quality", quality
        ));
        return properties;
    }
}
