package com.enterprise.iqk.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class ReactDecisionParserTest {
    private final ReactDecisionParser parser = new ReactDecisionParser(new ObjectMapper());

    @Test
    void parsesAllowedActionAndInputFromModelJson() {
        ReactDecisionParser.ReasonDecision decision = parser.parse("""
                planner: {"thought":"look up documents","action":"rag_search", "action_input":{"query":"RAG"}}
                """);

        assertThat(decision.action()).isEqualTo("rag_search");
        assertThat(decision.thought()).isEqualTo("look up documents");
        assertThat(decision.actionInput()).isEqualTo(Map.of("query", "RAG"));
    }

    @Test
    void convertsUnknownOrInvalidModelOutputToSafeFinish() {
        ReactDecisionParser.ReasonDecision unknown = parser.parse("{" +
                "\"action\":\"delete_everything\",\"answer\":\"safe\"}");
        ReactDecisionParser.ReasonDecision invalid = parser.parse("not-json-answer");
        ReactDecisionParser.ReasonDecision malformed = parser.parse("{not-json}");
        ReactDecisionParser.ReasonDecision blank = parser.parse("");
        ReactDecisionParser.ReasonDecision blankAction = parser.parse("{\"action\":\"\"}");

        assertThat(unknown.action()).isEqualTo("finish");
        assertThat(unknown.answer()).isEqualTo("safe");
        assertThat(invalid.action()).isEqualTo("finish");
        assertThat(invalid.answer()).isEqualTo("not-json-answer");
        assertThat(malformed.action()).isEqualTo("finish");
        assertThat(blank.answer()).isEmpty();
        assertThat(blankAction.action()).isEqualTo("finish");
    }

    @Test
    void providesDeterministicFallbacksForSafetyAndRetrievalQuestions() {
        ReactDecisionParser.ReasonDecision heat = parser.fallback("高温健康风险有哪些？");
        ReactDecisionParser.ReasonDecision noContext = parser.fallback("知识库里没有答案怎么办？");
        ReactDecisionParser.ReasonDecision knowledgeBase = parser.fallback("请从知识库引用来源");
        ReactDecisionParser.ReasonDecision school = parser.fallback("校区怎么查询？");
        ReactDecisionParser.ReasonDecision reservation = parser.fallback("课程预约需要哪些字段？");
        ReactDecisionParser.ReasonDecision generic = parser.fallback("你好");

        assertThat(heat.action()).isEqualTo("finish");
        assertThat(heat.answer()).contains("中暑", "脱水");
        assertThat(noContext.answer()).contains("不会虚构");
        assertThat(knowledgeBase.action()).isEqualTo("rag_search");
        assertThat(knowledgeBase.actionInput()).containsEntry("query", "请从知识库引用来源");
        assertThat(school.answer()).contains("校区查询");
        assertThat(reservation.answer()).contains("课程预约");
        assertThat(generic.answer()).contains("规划器暂不可用");
    }

    @Test
    void rejectsBlankPromptWithAUserFacingFallback() {
        ReactDecisionParser.ReasonDecision decision = parser.fallback("  ");

        assertThat(decision.action()).isEqualTo("finish");
        assertThat(decision.answer()).contains("请求内容为空");
        assertThat(decision.citations()).anyMatch(citation -> citation.contains("fallback://input_validation"));
    }
}
