package com.enterprise.iqk.controller;

import com.enterprise.iqk.evaluation.EvaluationController;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class JavaApiContractTest {

    private static final String ANY = "ANY";

    @Test
    void exposesSharedParityEndpoints() throws IOException {
        Set<Endpoint> endpoints = new LinkedHashSet<>();
        for (Class<?> controller : List.of(
                AuthController.class,
                ChatController.class,
                ReactController.class,
                PdfController.class,
                IngestionController.class,
                AgentSessionController.class,
                FeedbackController.class,
                EvaluationController.class,
                AuditController.class,
                CostGovernanceController.class
        )) {
            endpoints.addAll(mappings(controller));
        }

        assertSupports(endpoints, "POST", "/auth/token");
        assertSupports(endpoints, "POST", "/auth/refresh");
        assertSupports(endpoints, "POST", "/auth/api-keys");
        assertSupports(endpoints, "POST", "/ai/chat");
        assertSupports(endpoints, "POST", "/ai/chat/stream");
        assertSupports(endpoints, "POST", "/ai/react/chat");
        assertSupports(endpoints, "POST", "/ai/react/chat/stream");
        assertSupports(endpoints, "POST", "/ai/pdf/upload/{chatId}");
        assertSupports(endpoints, "POST", "/ingestion/upload/{chatId}");
        assertSupports(endpoints, "GET", "/ingestion/jobs");
        assertSupports(endpoints, "GET", "/ingestion/jobs/{jobId}");
        assertSupports(endpoints, "POST", "/ai/pdf/chat");
        assertSupports(endpoints, "GET", "/ai/sessions");
        assertSupports(endpoints, "GET", "/ai/sessions/{sessionId}");
        assertSupports(endpoints, "POST", "/ai/feedback");
        assertSupports(endpoints, "GET", "/ai/evaluation/datasets");
        assertSupports(endpoints, "POST", "/ai/evaluation/runs");
        assertSupports(endpoints, "GET", "/audit/logs");
        assertSupports(endpoints, "GET", "/cost/summary");
        assertSupports(endpoints, "POST", "/cost/budget");

        String appConfig = Files.readString(Path.of("src/main/resources/application.yml"));
        assertThat(appConfig).contains("health,info,prometheus,metrics");
    }

    private static void assertSupports(Set<Endpoint> endpoints, String method, String path) {
        boolean supported = endpoints.stream()
                .anyMatch(endpoint -> endpoint.path().equals(path)
                        && (endpoint.method().equals(method) || endpoint.method().equals(ANY)));
        assertThat(supported)
                .as("Expected endpoint %s %s in %s", method, path, endpoints)
                .isTrue();
    }

    private static Set<Endpoint> mappings(Class<?> controller) {
        Set<Endpoint> endpoints = new LinkedHashSet<>();
        List<String> prefixes = classPrefixes(controller);
        for (Method method : controller.getDeclaredMethods()) {
            addRequestMappings(endpoints, prefixes, method);
            addGetMappings(endpoints, prefixes, method);
            addPostMappings(endpoints, prefixes, method);
            addPutMappings(endpoints, prefixes, method);
            addDeleteMappings(endpoints, prefixes, method);
        }
        return endpoints;
    }

    private static List<String> classPrefixes(Class<?> controller) {
        RequestMapping mapping = controller.getAnnotation(RequestMapping.class);
        if (mapping == null) {
            return List.of("");
        }
        String[] paths = mapping.path().length > 0 ? mapping.path() : mapping.value();
        if (paths.length == 0) {
            return List.of("");
        }
        return List.of(paths);
    }

    private static void addRequestMappings(Set<Endpoint> endpoints, List<String> prefixes, Method method) {
        RequestMapping mapping = method.getAnnotation(RequestMapping.class);
        if (mapping == null) {
            return;
        }
        String[] paths = mapping.path().length > 0 ? mapping.path() : mapping.value();
        RequestMethod[] methods = mapping.method();
        if (methods.length == 0) {
            add(endpoints, prefixes, ANY, paths);
            return;
        }
        for (RequestMethod requestMethod : methods) {
            add(endpoints, prefixes, requestMethod.name(), paths);
        }
    }

    private static void addGetMappings(Set<Endpoint> endpoints, List<String> prefixes, Method method) {
        GetMapping mapping = method.getAnnotation(GetMapping.class);
        if (mapping != null) {
            add(endpoints, prefixes, "GET", mapping.path().length > 0 ? mapping.path() : mapping.value());
        }
    }

    private static void addPostMappings(Set<Endpoint> endpoints, List<String> prefixes, Method method) {
        PostMapping mapping = method.getAnnotation(PostMapping.class);
        if (mapping != null) {
            add(endpoints, prefixes, "POST", mapping.path().length > 0 ? mapping.path() : mapping.value());
        }
    }

    private static void addPutMappings(Set<Endpoint> endpoints, List<String> prefixes, Method method) {
        PutMapping mapping = method.getAnnotation(PutMapping.class);
        if (mapping != null) {
            add(endpoints, prefixes, "PUT", mapping.path().length > 0 ? mapping.path() : mapping.value());
        }
    }

    private static void addDeleteMappings(Set<Endpoint> endpoints, List<String> prefixes, Method method) {
        DeleteMapping mapping = method.getAnnotation(DeleteMapping.class);
        if (mapping != null) {
            add(endpoints, prefixes, "DELETE", mapping.path().length > 0 ? mapping.path() : mapping.value());
        }
    }

    private static void add(Set<Endpoint> endpoints, List<String> prefixes, String method, String[] paths) {
        String[] normalizedPaths = paths.length == 0 ? new String[]{""} : paths;
        for (String prefix : prefixes) {
            for (String path : normalizedPaths) {
                endpoints.add(new Endpoint(method, normalize(prefix, path)));
            }
        }
    }

    private static String normalize(String prefix, String path) {
        String combined = ("/" + trimSlashes(prefix) + "/" + trimSlashes(path)).replaceAll("/{2,}", "/");
        if (combined.length() > 1 && combined.endsWith("/")) {
            return combined.substring(0, combined.length() - 1);
        }
        return combined;
    }

    private static String trimSlashes(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        return value.replaceAll("^/+", "").replaceAll("/+$", "");
    }

    private record Endpoint(String method, String path) {
    }
}
