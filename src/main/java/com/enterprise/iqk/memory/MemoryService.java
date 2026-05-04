package com.enterprise.iqk.memory;

import com.enterprise.iqk.security.TenantContext;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class MemoryService {

    private final MemoryItemMapper itemMapper;
    private final MemoryEventMapper eventMapper;
    private final ObjectMapper objectMapper;

    // ── Save ─────────────────────────────────────────────────────

    public MemoryItemRecord saveShortMemory(String tenantId, String userId,
                                             String content, String source) {
        return save(tenantId, userId, "short", content, source, null, 0.9,
                LocalDateTime.now().plusHours(24));
    }

    public MemoryItemRecord saveLongMemory(String tenantId, String userId,
                                            String content, String source) {
        return save(tenantId, userId, "long", content, source, null, 0.85, null);
    }

    public MemoryItemRecord saveTaskMemory(String tenantId, String userId,
                                            String content, String taskId) {
        return save(tenantId, userId, "task", content, "task:" + taskId, taskId, 0.9,
                LocalDateTime.now().plusDays(30));
    }

    public MemoryItemRecord saveFactMemory(String tenantId, String userId,
                                            String content, String source,
                                            double confidence) {
        return save(tenantId, userId, "fact", content, source, null,
                confidence, null);
    }

    private MemoryItemRecord save(String tenantId, String userId, String type,
                                   String content, String source, String sourceTaskId,
                                   double confidence, LocalDateTime expiresAt) {
        if (!StringUtils.hasText(content)) return null;
        String memoryId = "mem-" + UUID.randomUUID().toString().replace("-", "");
        LocalDateTime now = LocalDateTime.now();
        MemoryItemRecord item = MemoryItemRecord.builder()
                .memoryId(memoryId)
                .tenantId(TenantContext.normalize(tenantId))
                .userId(userId)
                .type(type)
                .content(content.trim())
                .source(source)
                .sourceTaskId(sourceTaskId)
                .confidence(confidence)
                .expiresAt(expiresAt)
                .createdAt(now)
                .updatedAt(now)
                .build();
        itemMapper.insert(item);
        emitEvent(memoryId, "CREATE", "saved " + type + " memory");
        return item;
    }

    // ── Query ─────────────────────────────────────────────────────

    public List<MemoryItemRecord> queryShortMemory(String tenantId, String userId, int limit) {
        return itemMapper.findByUserAndType(tenantId, userId, "short", limit);
    }

    public List<MemoryItemRecord> queryLongMemory(String tenantId, String userId, int limit) {
        return itemMapper.findByUserAndType(tenantId, userId, "long", limit);
    }

    public List<MemoryItemRecord> queryTaskMemory(String tenantId, String taskId) {
        return itemMapper.findByTaskId(taskId);
    }

    public List<MemoryItemRecord> queryFactMemory(String tenantId, double minConfidence, int limit) {
        return itemMapper.findByTypeAndConfidence(tenantId, "fact", minConfidence, limit);
    }

    /**
     * Query all relevant memories for a user:
     * - Recent short-term memories
     * - Long-term profile/preferences
     * - High-confidence facts
     */
    public MemoryContextSnapshot buildContext(String tenantId, String userId) {
        List<MemoryItemRecord> shortMem = queryShortMemory(tenantId, userId, 5);
        List<MemoryItemRecord> longMem = queryLongMemory(tenantId, userId, 10);
        List<MemoryItemRecord> facts = queryFactMemory(tenantId, 0.7, 5);

        StringBuilder context = new StringBuilder();
        if (!longMem.isEmpty()) {
            context.append("用户长期记忆:\n");
            for (MemoryItemRecord m : longMem) {
                context.append("- ").append(m.getContent()).append("\n");
            }
            context.append("\n");
        }
        if (!shortMem.isEmpty()) {
            context.append("近期对话要点:\n");
            for (MemoryItemRecord m : shortMem) {
                context.append("- ").append(m.getContent()).append("\n");
            }
        }
        return new MemoryContextSnapshot(context.toString(), shortMem, longMem, facts);
    }

    // ── Maintenance ──────────────────────────────────────────────

    @Scheduled(cron = "0 0 3 * * ?") // daily at 3am
    public void cleanExpiredMemories() {
        int deleted = itemMapper.deleteExpired();
        if (deleted > 0) {
            log.info("Cleaned {} expired memory items", deleted);
        }
    }

    public void deleteMemory(String memoryId) {
        MemoryItemRecord item = itemMapper.findByMemoryId(memoryId);
        if (item != null) {
            itemMapper.deleteById(item.getId());
            emitEvent(memoryId, "DELETE", "manual deletion");
        }
    }

    // ── Event ─────────────────────────────────────────────────────

    private void emitEvent(String memoryId, String action, String reason) {
        try {
            MemoryEventRecord event = MemoryEventRecord.builder()
                    .eventId("mevt-" + UUID.randomUUID().toString().replace("-", ""))
                    .memoryId(memoryId)
                    .action(action)
                    .reason(reason)
                    .createdAt(LocalDateTime.now())
                    .build();
            eventMapper.insert(event);
        } catch (Exception e) {
            log.error("Failed to persist memory event", e);
        }
    }

    public List<MemoryEventRecord> getEvents(String memoryId) {
        return eventMapper.findByMemoryId(memoryId);
    }

    public record MemoryContextSnapshot(String contextText,
                                         List<MemoryItemRecord> shortMemories,
                                         List<MemoryItemRecord> longMemories,
                                         List<MemoryItemRecord> facts) {}
}
