package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.SecurityProperties;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class JwtServiceTest {

    @Test
    void shouldIssueAndParseToken() {
        SecurityProperties properties = new SecurityProperties();
        properties.setJwtSecret("test-secret-test-secret-test-secret-test-secret");
        properties.setJwtExpireMinutes(30);

        JwtService jwtService = new JwtService(properties);
        String token = jwtService.issueToken("alice", List.of("ADMIN"), List.of("chat:write"), "tenant-a");
        assertNotNull(token);

        AuthIdentity identity = jwtService.parse(token);
        assertNotNull(identity);
        assertEquals("alice", identity.getPrincipal());
        assertEquals("ADMIN", identity.getRoles().get(0));
        assertEquals("chat:write", identity.getPermissions().get(0));
        assertEquals("tenant-a", identity.getTenantId());
    }
}
