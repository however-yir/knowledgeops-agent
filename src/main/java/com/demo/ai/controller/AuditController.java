package com.demo.ai.controller;

import com.demo.ai.domain.AuditLog;
import com.demo.ai.mapper.AuditLogMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/audit")
@RequiredArgsConstructor
public class AuditController {
    private final AuditLogMapper auditLogMapper;

    @GetMapping("/logs")
    @PreAuthorize("hasAnyAuthority('PERM_AUDIT_READ','ROLE_ADMIN')")
    public List<AuditLog> latest(@RequestParam(value = "limit", defaultValue = "50") int limit) {
        return auditLogMapper.latest(Math.max(1, Math.min(limit, 200)));
    }
}
