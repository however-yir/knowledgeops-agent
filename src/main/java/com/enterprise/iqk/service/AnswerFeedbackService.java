package com.enterprise.iqk.service;

import com.enterprise.iqk.config.properties.FeedbackProperties;
import com.enterprise.iqk.domain.AnswerFeedback;
import com.enterprise.iqk.domain.vo.AnswerFeedbackSubmitVO;
import com.enterprise.iqk.mapper.AnswerFeedbackMapper;
import com.enterprise.iqk.security.TenantContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class AnswerFeedbackService {
    private final AnswerFeedbackMapper answerFeedbackMapper;
    private final FeedbackProperties feedbackProperties;
    private final ObjectMapper objectMapper;

    public void submit(String tenantId, AnswerFeedbackSubmitVO payload) {
        if (payload == null) {
            throw new IllegalArgumentException("feedback payload is required");
        }
        if (!StringUtils.hasText(payload.getChatId())) {
            throw new IllegalArgumentException("chatId is required");
        }
        if (payload.getRating() == null || payload.getRating() < 1 || payload.getRating() > 5) {
            throw new IllegalArgumentException("rating must be between 1 and 5");
        }
        if (!StringUtils.hasText(payload.getAnswer())) {
            throw new IllegalArgumentException("answer is required");
        }

        String tenant = TenantContext.normalize(tenantId);
        LocalDateTime now = LocalDateTime.now();
        AnswerFeedback feedback = AnswerFeedback.builder()
                .tenantId(tenant)
                .chatId(payload.getChatId())
                .sessionId(payload.getSessionId())
                .branchId(payload.getBranchId())
                .messageId(payload.getMessageId())
                .rating(payload.getRating())
                .comment(trimToLength(payload.getComment(), 1024))
                .questionText(payload.getQuestion())
                .answerText(payload.getAnswer())
                .createdAt(now)
                .build();
        answerFeedbackMapper.insert(feedback);

        if (feedbackProperties.isEnabled()) {
            appendToDataset(tenant, feedback, now);
        }
    }

    private void appendToDataset(String tenantId, AnswerFeedback feedback, LocalDateTime createdAt) {
        Map<String, Object> datasetItem = new LinkedHashMap<>();
        datasetItem.put("id", "feedback_" + createdAt.toLocalDate() + "_" + feedback.getId());
        datasetItem.put("category", "user_feedback");
        datasetItem.put("tenant_id", tenantId);
        datasetItem.put("chatId", feedback.getChatId());
        datasetItem.put("question", defaultText(feedback.getQuestionText(), "用户反馈问题"));
        datasetItem.put("answer", trimToLength(feedback.getAnswerText(), 1500));
        datasetItem.put("rating", feedback.getRating());
        datasetItem.put("comment", defaultText(feedback.getComment(), ""));
        datasetItem.put("created_at", createdAt.toString());

        List<String> keywords = extractKeywords(
                defaultText(feedback.getComment(), "") + " " + defaultText(feedback.getAnswerText(), "")
        );
        if (feedback.getRating() >= 4) {
            datasetItem.put("expected_keywords", keywords);
            datasetItem.put("forbidden_keywords", List.of("不知道", "无法回答", "胡编"));
        } else if (feedback.getRating() <= 2) {
            datasetItem.put("expected_keywords", List.of("改进", "更准确"));
            datasetItem.put("forbidden_keywords", keywords);
        } else {
            datasetItem.put("expected_keywords", keywords);
            datasetItem.put("forbidden_keywords", List.of());
        }

        Path output = Path.of(feedbackProperties.getDatasetPath());
        try {
            if (output.getParent() != null) {
                Files.createDirectories(output.getParent());
            }
            String line = objectMapper.writeValueAsString(datasetItem) + System.lineSeparator();
            Files.writeString(output, line, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException ex) {
            throw new IllegalStateException("failed to append feedback dataset", ex);
        }
    }

    private List<String> extractKeywords(String text) {
        if (!StringUtils.hasText(text)) {
            return List.of();
        }
        String normalized = text.toLowerCase(Locale.ROOT);
        String[] tokens = normalized.split("[^\\p{IsHan}\\p{L}\\p{N}]+");
        Set<String> values = new LinkedHashSet<>();
        for (String token : tokens) {
            if (!StringUtils.hasText(token) || token.length() < 2) {
                continue;
            }
            if (isStopWord(token)) {
                continue;
            }
            values.add(token);
            if (values.size() >= 6) {
                break;
            }
        }
        return new ArrayList<>(values);
    }

    private boolean isStopWord(String token) {
        return Set.of("这个", "那个", "然后", "但是", "我们", "你们", "他们", "以及", "因为").contains(token);
    }

    private String trimToLength(String value, int maxLength) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        String normalized = value.trim();
        if (normalized.length() <= maxLength) {
            return normalized;
        }
        return normalized.substring(0, maxLength);
    }

    private String defaultText(String value, String fallback) {
        return StringUtils.hasText(value) ? value : fallback;
    }
}
