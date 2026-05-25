package com.enterprise.iqk.agent.harness;

import com.enterprise.iqk.rag.RagAnswerService;
import com.enterprise.iqk.tools.CourseTools;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class BuiltinToolRuntimeTest {

    @Test
    void executeRagSearchReturnsTraceFriendlyObservation() {
        CourseTools courseTools = mock(CourseTools.class);
        RagAnswerService ragAnswerService = mock(RagAnswerService.class);
        when(ragAnswerService.answer(
                eq("java cache"),
                eq("tenant-a"),
                eq("chat-1"),
                eq("react::chat-1"),
                eq("balanced")
        )).thenReturn(RagAnswerService.RagResult.builder()
                .answer("answer")
                .citations(List.of("source=doc, chunk=1"))
                .evidence(List.of("evidence"))
                .build());
        BuiltinToolRuntime runtime = new BuiltinToolRuntime(courseTools, ragAnswerService);

        AgentObservation observation = runtime.execute(new AgentAction(
                "rag_search",
                Map.of("query", "java cache"),
                "fallback prompt",
                "tenant-a",
                "chat-1",
                "balanced",
                "task-1",
                "step-1"
        ));

        Map<String, Object> payload = observation.toMap();
        assertThat(payload)
                .containsEntry("status", "success")
                .containsEntry("query", "java cache")
                .containsEntry("answer", "answer")
                .containsEntry("source", "builtin");
        assertThat(payload.get("citations")).isEqualTo(List.of("source=doc, chunk=1"));
    }

    @Test
    void executeReservationRejectsMissingRequiredFields() {
        CourseTools courseTools = mock(CourseTools.class);
        RagAnswerService ragAnswerService = mock(RagAnswerService.class);
        BuiltinToolRuntime runtime = new BuiltinToolRuntime(courseTools, ragAnswerService);

        AgentObservation observation = runtime.execute(new AgentAction(
                "add_course_reservation",
                Map.of("course", "Java"),
                "prompt",
                "tenant-a",
                "chat-1",
                "balanced",
                "",
                ""
        ));

        assertThat(observation.toMap())
                .containsEntry("status", "error")
                .containsEntry("source", "builtin")
                .containsEntry("message", "missing required fields for reservation");
        verifyNoInteractions(courseTools, ragAnswerService);
    }

    @Test
    void executeSchoolQueryDelegatesToCourseTools() {
        CourseTools courseTools = mock(CourseTools.class);
        RagAnswerService ragAnswerService = mock(RagAnswerService.class);
        when(courseTools.querySchool()).thenReturn(List.of());
        BuiltinToolRuntime runtime = new BuiltinToolRuntime(courseTools, ragAnswerService);

        AgentObservation observation = runtime.execute(new AgentAction(
                "query_school",
                Map.of(),
                "prompt",
                "tenant-a",
                "chat-1",
                "balanced",
                "",
                ""
        ));

        assertThat(observation.toMap())
                .containsEntry("status", "success")
                .containsEntry("data", List.of());
        verify(courseTools).querySchool();
        verifyNoInteractions(ragAnswerService);
    }
}
