package com.enterprise.iqk.security;

import lombok.Builder;
import lombok.Data;

import java.util.List;

@Data
@Builder
public class AuthIdentity {
    private String principal;
    private List<String> roles;
    private List<String> permissions;
    private String source;
    private String tenantId;
}
