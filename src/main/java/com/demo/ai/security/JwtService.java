package com.demo.ai.security;

import com.demo.ai.config.properties.SecurityProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class JwtService {
    private final SecurityProperties securityProperties;

    public AuthIdentity parse(String token) {
        if (!StringUtils.hasText(token)) {
            return null;
        }
        Claims claims = Jwts.parser()
                .verifyWith(secretKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
        Date expiration = claims.getExpiration();
        if (expiration != null && expiration.before(new Date())) {
            return null;
        }
        String subject = claims.getSubject();
        List<String> roles = extractRoles(claims);
        List<String> permissions = extractPermissions(claims);
        if (!StringUtils.hasText(subject)) {
            return null;
        }
        if (roles.isEmpty()) {
            roles = List.of("USER");
        }
        return AuthIdentity.builder()
                .principal(subject)
                .roles(roles)
                .permissions(permissions)
                .source("jwt")
                .build();
    }

    public String issueToken(String subject, List<String> roles, List<String> permissions) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(subject)
                .claim("roles", roles == null ? Collections.emptyList() : roles)
                .claim("permissions", permissions == null ? Collections.emptyList() : permissions)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plusSeconds(securityProperties.getJwtExpireMinutes() * 60L)))
                .signWith(secretKey())
                .compact();
    }

    private SecretKey secretKey() {
        String secret = securityProperties.getJwtSecret();
        byte[] bytes = secret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length == 0) {
            bytes = "fallback-secret-fallback-secret-0001".getBytes(StandardCharsets.UTF_8);
        }
        if (bytes.length < 32) {
            byte[] expanded = new byte[32];
            for (int i = 0; i < expanded.length; i++) {
                expanded[i] = bytes[i % bytes.length];
            }
            return Keys.hmacShaKeyFor(expanded);
        }
        return Keys.hmacShaKeyFor(bytes);
    }

    @SuppressWarnings("unchecked")
    private List<String> extractRoles(Claims claims) {
        Object raw = claims.get("roles");
        if (raw == null) {
            return new ArrayList<>();
        }
        if (raw instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        if (raw instanceof String s && StringUtils.hasText(s)) {
            return List.of(s.split(","));
        }
        if (raw instanceof Map<?, ?> map && map.containsKey("value")) {
            return List.of(String.valueOf(map.get("value")));
        }
        return new ArrayList<>();
    }

    @SuppressWarnings("unchecked")
    private List<String> extractPermissions(Claims claims) {
        Object raw = claims.get("permissions");
        if (raw == null) {
            return new ArrayList<>();
        }
        if (raw instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        if (raw instanceof String s && StringUtils.hasText(s)) {
            return List.of(s.split(","));
        }
        if (raw instanceof Map<?, ?> map && map.containsKey("value")) {
            return List.of(String.valueOf(map.get("value")));
        }
        return new ArrayList<>();
    }
}
