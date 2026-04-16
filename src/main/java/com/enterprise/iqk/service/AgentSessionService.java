package com.enterprise.iqk.service;

import com.enterprise.iqk.domain.AgentSessionStateRecord;
import com.enterprise.iqk.domain.vo.AgentSessionBranchVO;
import com.enterprise.iqk.domain.vo.AgentSessionMessageVO;
import com.enterprise.iqk.domain.vo.AgentSessionStateVO;
import com.enterprise.iqk.domain.vo.BranchCompareResultVO;
import com.enterprise.iqk.domain.vo.BranchMergeResultVO;
import com.enterprise.iqk.domain.vo.PagedResult;
import com.enterprise.iqk.mapper.AgentSessionStateMapper;
import com.enterprise.iqk.security.TenantContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class AgentSessionService {
    private final AgentSessionStateMapper agentSessionStateMapper;
    private final ObjectMapper objectMapper;

    public PagedResult<AgentSessionStateVO> list(String tenantId,
                                                 String keyword,
                                                 String workspaceId,
                                                 boolean includeArchived,
                                                 int page,
                                                 int pageSize) {
        String tenant = TenantContext.normalize(tenantId);
        int safePage = Math.max(1, page);
        int safePageSize = Math.max(1, pageSize);
        long total = agentSessionStateMapper.countByTenant(tenant, emptyToNull(keyword), workspaceId, includeArchived);
        if (total == 0) {
            return new PagedResult<>(Collections.emptyList(), 0, safePage, safePageSize);
        }
        long offset = (long) (safePage - 1) * safePageSize;
        List<AgentSessionStateVO> items = agentSessionStateMapper.findByTenant(tenant, emptyToNull(keyword), workspaceId, includeArchived, offset, safePageSize)
                .stream()
                .map(this::toSessionState)
                .toList();
        return new PagedResult<>(items, total, safePage, safePageSize);
    }

    public AgentSessionStateVO get(String tenantId, String sessionId) {
        AgentSessionStateRecord record = findRecord(tenantId, sessionId);
        return toSessionState(record);
    }

    public AgentSessionStateVO upsert(String tenantId, String sessionId, AgentSessionStateVO payload) {
        if (payload == null) {
            throw new IllegalArgumentException("session payload is required");
        }
        if (!StringUtils.hasText(sessionId)) {
            throw new IllegalArgumentException("session id is required");
        }
        String tenant = TenantContext.normalize(tenantId);
        String normalizedSessionId = sessionId.trim();
        LocalDateTime now = LocalDateTime.now();

        AgentSessionStateVO state = normalizeSessionPayload(normalizedSessionId, payload);
        String serialized = writeJson(state);

        AgentSessionStateRecord existing = agentSessionStateMapper.findByTenantAndSessionId(tenant, normalizedSessionId);
        if (existing == null) {
            AgentSessionStateRecord inserted = AgentSessionStateRecord.builder()
                    .sessionId(normalizedSessionId)
                    .tenantId(tenant)
                    .title(defaultText(state.getTitle(), "新会话"))
                    .workspaceId(defaultText(state.getWorkspaceId(), "default"))
                    .modelProfile(defaultText(state.getModelProfile(), "balanced"))
                    .streaming(Boolean.TRUE.equals(state.getStreaming()) ? 1 : 0)
                    .pinned(Boolean.TRUE.equals(state.getPinned()) ? 1 : 0)
                    .archived(Boolean.TRUE.equals(state.getArchived()) ? 1 : 0)
                    .activeBranchId(state.getActiveBranchId())
                    .sessionPayload(serialized)
                    .createdAt(now)
                    .updatedAt(now)
                    .build();
            agentSessionStateMapper.insert(inserted);
        } else {
            existing.setTitle(defaultText(state.getTitle(), "新会话"));
            existing.setWorkspaceId(defaultText(state.getWorkspaceId(), "default"));
            existing.setModelProfile(defaultText(state.getModelProfile(), "balanced"));
            existing.setStreaming(Boolean.TRUE.equals(state.getStreaming()) ? 1 : 0);
            existing.setPinned(Boolean.TRUE.equals(state.getPinned()) ? 1 : 0);
            existing.setArchived(Boolean.TRUE.equals(state.getArchived()) ? 1 : 0);
            existing.setActiveBranchId(state.getActiveBranchId());
            existing.setSessionPayload(serialized);
            existing.setUpdatedAt(now);
            agentSessionStateMapper.updateById(existing);
        }
        return get(tenant, normalizedSessionId);
    }

    public AgentSessionStateVO setPinned(String tenantId, String sessionId, boolean pinned) {
        String tenant = TenantContext.normalize(tenantId);
        int updated = agentSessionStateMapper.updatePinned(tenant, sessionId, pinned ? 1 : 0);
        if (updated <= 0) {
            throw new IllegalArgumentException("session not found");
        }
        AgentSessionStateVO state = get(tenant, sessionId);
        state.setPinned(pinned);
        return upsert(tenant, sessionId, state);
    }

    public AgentSessionStateVO setArchived(String tenantId, String sessionId, boolean archived) {
        String tenant = TenantContext.normalize(tenantId);
        int updated = agentSessionStateMapper.updateArchived(tenant, sessionId, archived ? 1 : 0);
        if (updated <= 0) {
            throw new IllegalArgumentException("session not found");
        }
        AgentSessionStateVO state = get(tenant, sessionId);
        state.setArchived(archived);
        return upsert(tenant, sessionId, state);
    }

    public BranchCompareResultVO compareBranches(String tenantId, String sessionId, String sourceBranchId, String targetBranchId) {
        AgentSessionStateVO state = get(tenantId, sessionId);
        AgentSessionBranchVO source = findBranch(state, sourceBranchId);
        AgentSessionBranchVO target = findBranch(state, targetBranchId);

        Set<String> sourceFingerprints = toMessageFingerprintSet(source.getMessages());
        Set<String> targetFingerprints = toMessageFingerprintSet(target.getMessages());

        Set<String> common = new LinkedHashSet<>(sourceFingerprints);
        common.retainAll(targetFingerprints);

        Set<String> sourceOnly = new LinkedHashSet<>(sourceFingerprints);
        sourceOnly.removeAll(targetFingerprints);

        Set<String> targetOnly = new LinkedHashSet<>(targetFingerprints);
        targetOnly.removeAll(sourceFingerprints);

        return BranchCompareResultVO.builder()
                .sourceBranchId(sourceBranchId)
                .targetBranchId(targetBranchId)
                .sourceMessageCount(sizeOf(source.getMessages()))
                .targetMessageCount(sizeOf(target.getMessages()))
                .commonMessageCount(common.size())
                .sourceOnlyCount(sourceOnly.size())
                .targetOnlyCount(targetOnly.size())
                .sourceOnlyPreview(previewContents(source.getMessages(), sourceOnly))
                .targetOnlyPreview(previewContents(target.getMessages(), targetOnly))
                .build();
    }

    public BranchMergeResultVO mergeBranches(String tenantId,
                                             String sessionId,
                                             String sourceBranchId,
                                             String targetBranchId,
                                             String title) {
        String tenant = TenantContext.normalize(tenantId);
        AgentSessionStateVO state = get(tenant, sessionId);
        AgentSessionBranchVO source = findBranch(state, sourceBranchId);
        AgentSessionBranchVO target = findBranch(state, targetBranchId);

        List<AgentSessionMessageVO> targetMessages = copyMessages(target.getMessages());
        List<AgentSessionMessageVO> sourceMessages = copyMessages(source.getMessages());

        Set<String> targetFingerprints = toMessageFingerprintSet(targetMessages);
        Set<String> existingIds = messageIdSet(targetMessages);
        int added = 0;
        for (AgentSessionMessageVO message : sourceMessages) {
            String fingerprint = fingerprint(message);
            if (targetFingerprints.contains(fingerprint)) {
                continue;
            }
            ensureUniqueMessageId(message, existingIds);
            targetMessages.add(message);
            targetFingerprints.add(fingerprint);
            added++;
        }

        AgentSessionBranchVO mergedBranch = new AgentSessionBranchVO();
        mergedBranch.setId(buildMergedBranchId());
        mergedBranch.setTitle(StringUtils.hasText(title) ? title.trim() : defaultText(target.getTitle(), "分支") + " · merge");
        mergedBranch.setParentBranchId(target.getId());
        mergedBranch.setParentMessageId(target.getParentMessageId());
        mergedBranch.setUpdatedAt(System.currentTimeMillis());
        mergedBranch.setMessages(targetMessages);
        mergedBranch.setTraceSteps(target.getTraceSteps());

        List<AgentSessionBranchVO> branches = state.getBranches() == null ? new ArrayList<>() : new ArrayList<>(state.getBranches());
        branches.add(0, mergedBranch);
        state.setBranches(branches);
        state.setActiveBranchId(mergedBranch.getId());
        state.setUpdatedAt(System.currentTimeMillis());

        AgentSessionStateVO saved = upsert(tenant, sessionId, state);
        return BranchMergeResultVO.builder()
                .session(saved)
                .mergedBranch(mergedBranch)
                .mergedMessageCount(sizeOf(targetMessages))
                .build();
    }

    private AgentSessionStateRecord findRecord(String tenantId, String sessionId) {
        if (!StringUtils.hasText(sessionId)) {
            throw new IllegalArgumentException("session id is required");
        }
        AgentSessionStateRecord record = agentSessionStateMapper.findByTenantAndSessionId(TenantContext.normalize(tenantId), sessionId.trim());
        if (record == null) {
            throw new IllegalArgumentException("session not found");
        }
        return record;
    }

    private AgentSessionStateVO toSessionState(AgentSessionStateRecord record) {
        AgentSessionStateVO payload = readJson(record.getSessionPayload());
        payload.setId(record.getSessionId());
        payload.setTitle(defaultText(record.getTitle(), payload.getTitle()));
        payload.setWorkspaceId(defaultText(record.getWorkspaceId(), payload.getWorkspaceId()));
        payload.setModelProfile(defaultText(record.getModelProfile(), payload.getModelProfile()));
        payload.setStreaming(record.getStreaming() != null && record.getStreaming() == 1);
        payload.setPinned(record.getPinned() != null && record.getPinned() == 1);
        payload.setArchived(record.getArchived() != null && record.getArchived() == 1);
        payload.setActiveBranchId(defaultText(record.getActiveBranchId(), payload.getActiveBranchId()));
        payload.setUpdatedAt(record.getUpdatedAt() == null ? System.currentTimeMillis() : record.getUpdatedAt().atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli());
        payload.setBranches(payload.getBranches() == null ? new ArrayList<>() : payload.getBranches());
        return payload;
    }

    private AgentSessionStateVO normalizeSessionPayload(String sessionId, AgentSessionStateVO payload) {
        AgentSessionStateVO state = new AgentSessionStateVO();
        state.setId(sessionId);
        state.setTitle(defaultText(payload.getTitle(), "新会话"));
        state.setUpdatedAt(payload.getUpdatedAt() == null ? System.currentTimeMillis() : payload.getUpdatedAt());
        state.setModelProfile(defaultText(payload.getModelProfile(), "balanced"));
        state.setStreaming(payload.getStreaming() == null ? Boolean.TRUE : payload.getStreaming());
        state.setPinned(Boolean.TRUE.equals(payload.getPinned()));
        state.setArchived(Boolean.TRUE.equals(payload.getArchived()));
        state.setWorkspaceId(defaultText(payload.getWorkspaceId(), "default"));
        state.setActiveBranchId(payload.getActiveBranchId());
        state.setBranches(payload.getBranches() == null ? new ArrayList<>() : payload.getBranches());
        if (!StringUtils.hasText(state.getActiveBranchId()) && !state.getBranches().isEmpty()) {
            state.setActiveBranchId(state.getBranches().get(0).getId());
        }
        return state;
    }

    private AgentSessionBranchVO findBranch(AgentSessionStateVO state, String branchId) {
        if (!StringUtils.hasText(branchId)) {
            throw new IllegalArgumentException("branch id is required");
        }
        if (state.getBranches() == null || state.getBranches().isEmpty()) {
            throw new IllegalArgumentException("branch not found");
        }
        return state.getBranches()
                .stream()
                .filter(item -> Objects.equals(item.getId(), branchId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("branch not found"));
    }

    private Set<String> toMessageFingerprintSet(List<AgentSessionMessageVO> messages) {
        Set<String> values = new LinkedHashSet<>();
        if (messages == null) {
            return values;
        }
        for (AgentSessionMessageVO message : messages) {
            values.add(fingerprint(message));
        }
        return values;
    }

    private Set<String> messageIdSet(List<AgentSessionMessageVO> messages) {
        Set<String> ids = new LinkedHashSet<>();
        if (messages == null) {
            return ids;
        }
        for (AgentSessionMessageVO message : messages) {
            if (message != null && StringUtils.hasText(message.getId())) {
                ids.add(message.getId());
            }
        }
        return ids;
    }

    private List<String> previewContents(List<AgentSessionMessageVO> messages, Set<String> selected) {
        if (messages == null || messages.isEmpty() || selected == null || selected.isEmpty()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (AgentSessionMessageVO message : messages) {
            String fingerprint = fingerprint(message);
            if (!selected.contains(fingerprint)) {
                continue;
            }
            values.add(trimPreview(message.getContent()));
            if (values.size() >= 5) {
                break;
            }
        }
        return values;
    }

    private String trimPreview(String content) {
        if (!StringUtils.hasText(content)) {
            return "";
        }
        String normalized = content.replaceAll("\\s+", " ").trim();
        if (normalized.length() <= 120) {
            return normalized;
        }
        return normalized.substring(0, 120) + "...";
    }

    private String fingerprint(AgentSessionMessageVO message) {
        if (message == null) {
            return "null";
        }
        String role = defaultText(message.getRole(), "unknown");
        String content = defaultText(message.getContent(), "");
        String normalizedContent = content.replaceAll("\\s+", " ").trim();
        return role + "::" + normalizedContent;
    }

    private List<AgentSessionMessageVO> copyMessages(List<AgentSessionMessageVO> original) {
        if (original == null || original.isEmpty()) {
            return new ArrayList<>();
        }
        List<AgentSessionMessageVO> copied = new ArrayList<>(original.size());
        for (AgentSessionMessageVO item : original) {
            AgentSessionMessageVO value = new AgentSessionMessageVO();
            value.setId(item.getId());
            value.setRole(item.getRole());
            value.setContent(item.getContent());
            value.setCreatedAt(item.getCreatedAt());
            value.setState(item.getState());
            value.setCitations(item.getCitations() == null ? List.of() : new ArrayList<>(item.getCitations()));
            value.setEvidence(item.getEvidence() == null ? List.of() : new ArrayList<>(item.getEvidence()));
            copied.add(value);
        }
        return copied;
    }

    private void ensureUniqueMessageId(AgentSessionMessageVO message, Set<String> existingIds) {
        if (message == null) {
            return;
        }
        String id = message.getId();
        if (!StringUtils.hasText(id)) {
            id = "merged-" + System.currentTimeMillis() + "-" + Math.abs(fingerprint(message).hashCode());
            message.setId(id);
        }
        if (existingIds.contains(id)) {
            id = id + "-m" + existingIds.size();
            message.setId(id);
        }
        existingIds.add(id);
    }

    private String buildMergedBranchId() {
        return "branch-merge-" + System.currentTimeMillis() + "-" + Math.abs((int) (Math.random() * 100000));
    }

    private int sizeOf(List<?> list) {
        return list == null ? 0 : list.size();
    }

    private String writeJson(AgentSessionStateVO payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (Exception ex) {
            throw new IllegalArgumentException("failed to serialize session payload");
        }
    }

    private AgentSessionStateVO readJson(String raw) {
        if (!StringUtils.hasText(raw)) {
            return new AgentSessionStateVO();
        }
        try {
            return objectMapper.readValue(raw, AgentSessionStateVO.class);
        } catch (Exception ex) {
            throw new IllegalArgumentException("failed to parse session payload");
        }
    }

    private String emptyToNull(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }

    private String defaultText(String value, String fallback) {
        return StringUtils.hasText(value) ? value : fallback;
    }
}
