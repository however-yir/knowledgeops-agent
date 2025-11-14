package com.enterprise.iqk.security;

import com.enterprise.iqk.mapper.PermissionMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
@RequiredArgsConstructor
public class PermissionService {
    private final PermissionMapper permissionMapper;

    public List<String> permissionsForRoles(List<String> roles) {
        if (roles == null || roles.isEmpty()) {
            return List.of();
        }
        List<String> result = new ArrayList<>();
        for (String role : roles) {
            if (role == null) {
                continue;
            }
            result.addAll(permissionMapper.findByRoleName(role.replace("ROLE_", "")));
        }
        return result.stream().distinct().toList();
    }
}
