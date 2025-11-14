package com.enterprise.iqk.security;

import com.enterprise.iqk.config.properties.AuditProperties;
import com.enterprise.iqk.mapper.AuditLogMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

@Slf4j
@Component
@RequiredArgsConstructor
public class AuditRetentionScheduler {
    private final AuditLogMapper auditLogMapper;
    private final AuditProperties auditProperties;

    @Scheduled(cron = "0 20 3 * * *")
    public void cleanup() {
        LocalDateTime deadline = LocalDateTime.now().minusDays(Math.max(1, auditProperties.getRetentionDays()));
        int deleted = auditLogMapper.deleteBefore(deadline);
        if (deleted > 0) {
            log.info("Audit retention cleanup deleted {} rows before {}", deleted, deadline);
        }
    }
}
