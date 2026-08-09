package com.enterprise.iqk.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@Component
@RequiredArgsConstructor
public class ReactDecisionParser {
    private static final List<String> ALLOWED_ACTIONS = List.of(
            "query_school", "query_course", "add_course_reservation", "rag_search", "finish"
    );

    private final ObjectMapper objectMapper;

    public ReasonDecision parse(String rawModelOutput) {
        String json = extractJson(rawModelOutput);
        if (!StringUtils.hasText(json)) {
            return finishWithAnswer("Model output is not JSON, fallback to finish.", rawModelOutput);
        }
        try {
            JsonNode node = objectMapper.readTree(json);
            String action = normalizeAction(node.path("action").asText("finish"));
            if (!ALLOWED_ACTIONS.contains(action)) {
                action = "finish";
            }
            Map<String, Object> actionInput = objectMapper.convertValue(
                    node.path("action_input"), new TypeReference<Map<String, Object>>() {
                    }
            );
            return new ReasonDecision(
                    node.path("thought").asText(""),
                    action,
                    actionInput == null ? Collections.emptyMap() : actionInput,
                    node.path("answer").asText(""),
                    List.of(),
                    List.of(),
                    false
            );
        } catch (JsonProcessingException ex) {
            return finishWithAnswer("JSON parse failed, fallback to finish.", rawModelOutput);
        }
    }

    public ReasonDecision fallback(String prompt) {
        String safePrompt = emptyIfBlank(prompt).toLowerCase(Locale.ROOT);
        if (!StringUtils.hasText(safePrompt)) {
            return decision(
                    "Planner failed and prompt is empty. Fallback to safe finish.",
                    "当前请求内容为空，请补充问题后重试。",
                    "fallback://input_validation",
                    "规则兜底：空问题时引导用户补充输入。"
            );
        }
        if (containsAny(safePrompt, "校区", "campus")) {
            return decision(
                    "Planner unavailable; fallback to deterministic school-query answer.",
                    "已识别为校区查询请求：可以返回校区列表，并按城市或课程类型做进一步筛选。\n如需精确结果，请补充目标城市、课程方向或价格区间。",
                    "fallback://school_query_flow",
                    "校区查询流程：先列出校区，再按城市/课程类型筛选。"
            );
        }
        if (containsAny(safePrompt, "课程预约", "预约字段", "预约需要", "联系方式", "姓名", "校区")) {
            return decision(
                    "Planner unavailable; fallback to deterministic reservation schema answer.",
                    "课程预约建议至少包含这些字段：课程、姓名、联系方式、校区。\n如果业务需要，还可以补充备注、预约时间和渠道来源。",
                    "fallback://course_reservation_schema",
                    "预约字段模板：课程、姓名、联系方式、校区、备注(可选)。"
            );
        }
        if (containsAny(safePrompt, "高温", "健康风险", "heat")) {
            return decision(
                    "Planner unavailable; fallback to deterministic heat-risk answer.",
                    "高温健康风险通常包括中暑、脱水、慢病加重和户外暴露相关风险。\n建议重点关注补水、避开高温时段、室内降温与高风险人群预警。",
                    "fallback://heat_risk_guide",
                    "高温风险要点：中暑、脱水、慢病加重、暴露风险。"
            );
        }
        if (containsAny(safePrompt, "没有答案", "没有的内容", "知识库里没有", "上下文不足")) {
            return decision(
                    "Planner unavailable; fallback to hallucination-safe answer.",
                    "当知识库没有匹配上下文时，我会明确说明“当前没有匹配内容”，并给出下一步建议（如补充资料、调整检索关键词）。\n我不会虚构不存在的结论。",
                    "fallback://no_context_policy",
                    "无上下文策略：明确告知无匹配，不编造结论。"
            );
        }
        if (containsAny(safePrompt, "知识库", "引用", "来源", "pdf", "文档", "source")) {
            return new ReasonDecision(
                    "Planner unavailable; fallback route to rag_search.",
                    "rag_search",
                    Map.of("query", prompt),
                    "",
                    List.of(),
                    List.of(),
                    true
            );
        }
        return decision(
                "Planner unavailable; fallback to generic safe answer.",
                "当前规划器暂不可用，建议稍后重试或细化问题关键词。",
                "fallback://planner_unavailable",
                "系统兜底：规划器异常时返回可执行提示。"
        );
    }

    private ReasonDecision decision(String thought, String answer, String citation, String evidence) {
        return new ReasonDecision(
                thought,
                "finish",
                Collections.emptyMap(),
                answer,
                List.of("source=" + citation + ", chunk=1"),
                List.of(evidence),
                true
        );
    }

    private ReasonDecision finishWithAnswer(String thought, String rawModelOutput) {
        return new ReasonDecision(thought, "finish", Collections.emptyMap(), emptyIfBlank(rawModelOutput), List.of(), List.of(), false);
    }

    private String extractJson(String raw) {
        if (!StringUtils.hasText(raw)) {
            return "";
        }
        int start = raw.indexOf('{');
        int end = raw.lastIndexOf('}');
        return start < 0 || end <= start ? "" : raw.substring(start, end + 1);
    }

    private String normalizeAction(String action) {
        return StringUtils.hasText(action) ? action.trim().toLowerCase(Locale.ROOT) : "finish";
    }

    private boolean containsAny(String text, String... keywords) {
        if (!StringUtils.hasText(text) || keywords == null || keywords.length == 0) {
            return false;
        }
        for (String keyword : keywords) {
            if (StringUtils.hasText(keyword) && text.contains(keyword.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    private String emptyIfBlank(String value) {
        return StringUtils.hasText(value) ? value : "";
    }

    public record ReasonDecision(String thought,
                                 String action,
                                 Map<String, Object> actionInput,
                                 String answer,
                                 List<String> citations,
                                 List<String> evidence,
                                 boolean fallback) {
    }
}
