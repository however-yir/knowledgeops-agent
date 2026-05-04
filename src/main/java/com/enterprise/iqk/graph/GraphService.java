package com.enterprise.iqk.graph;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class GraphService {

    private final KgEntityMapper entityMapper;
    private final KgRelationMapper relationMapper;
    private final KgFactMapper factMapper;

    /**
     * Search entities by keyword (name or alias match).
     */
    public List<KgEntityRecord> searchEntities(String tenantId, String keyword, int limit) {
        if (!StringUtils.hasText(keyword)) return List.of();
        return entityMapper.searchByName(tenantId, keyword.trim(), Math.max(1, limit));
    }

    /**
     * Get one-hop neighbors of an entity, with relation info.
     */
    public List<GraphNeighbor> getNeighbors(String tenantId, String entityId) {
        List<KgRelationRecord> relations = relationMapper.findRelations(tenantId, entityId);
        Map<String, KgEntityRecord> entityCache = new HashMap<>();
        List<GraphNeighbor> neighbors = new ArrayList<>();

        for (KgRelationRecord rel : relations) {
            String neighborId = rel.getSourceEntityId().equals(entityId)
                    ? rel.getTargetEntityId() : rel.getSourceEntityId();
            KgEntityRecord entity = entityCache.computeIfAbsent(neighborId,
                    id -> entityMapper.findByEntityId(id));
            if (entity == null) continue;
            boolean outgoing = rel.getSourceEntityId().equals(entityId);
            neighbors.add(GraphNeighbor.builder()
                    .entity(entity)
                    .relationType(rel.getRelationType())
                    .direction(outgoing ? "OUT" : "IN")
                    .weight(rel.getWeight())
                    .build());
        }
        return neighbors;
    }

    /**
     * Search facts by keyword (subject or object match).
     */
    public List<KgFactRecord> searchFacts(String tenantId, String keyword, int limit) {
        if (!StringUtils.hasText(keyword)) return List.of();
        return factMapper.searchByKeyword(tenantId, keyword.trim(), Math.max(1, limit));
    }

    /**
     * Get entities by type, e.g., all COURSE entities.
     */
    public List<KgEntityRecord> getEntitiesByType(String tenantId, String type) {
        return entityMapper.findByType(tenantId, type);
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class GraphNeighbor {
        private KgEntityRecord entity;
        private String relationType;
        private String direction;  // IN or OUT
        private Double weight;
    }
}
