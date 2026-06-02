package com.enterprise.iqk.config;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class SecurityDefaultsTest {

    @Test
    void composeDefaultsAvoidKnownUnsafePlaceholders() throws IOException {
        String compose = Files.readString(Path.of("docker-compose.yml"));

        assertThat(compose).doesNotContain("APP_JWT_SECRET: ${APP_JWT_SECRET:-replace-me-with-real-secret}");
        assertThat(compose).doesNotContain("RABBITMQ_USERNAME: guest");
        assertThat(compose).doesNotContain("RABBITMQ_PASSWORD: guest");
        assertThat(compose).contains("RABBITMQ_DEFAULT_USER");
        assertThat(compose).contains("RABBITMQ_DEFAULT_PASS");
    }
}
