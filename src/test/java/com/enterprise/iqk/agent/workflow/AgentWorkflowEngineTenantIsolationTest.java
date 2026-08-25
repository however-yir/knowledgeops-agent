package com.enterprise.iqk.agent.workflow;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AgentWorkflowEngineTenantIsolationTest {

    private AgentTaskMapper taskMapper;
    private AgentStepMapper stepMapper;
    private AgentEventMapper eventMapper;
    private AgentWorkflowEngine engine;

    @BeforeEach
    void setUp() {
        taskMapper = mock(AgentTaskMapper.class);
        stepMapper = mock(AgentStepMapper.class);
        eventMapper = mock(AgentEventMapper.class);
        engine = new AgentWorkflowEngine(
                taskMapper,
                stepMapper,
                eventMapper,
                new ObjectMapper(),
                new SimpleMeterRegistry()
        );
    }

    @Test
    void returnsTaskOnlyWhenItBelongsToCurrentTenant() {
        AgentTaskRecord task = AgentTaskRecord.builder()
                .taskId("task-1")
                .tenantId("tenant-a")
                .status(WorkflowState.DONE.name())
                .build();
        when(taskMapper.findByTenantAndTaskId("tenant-a", "task-1")).thenReturn(task);
        when(stepMapper.findByTaskId("task-1")).thenReturn(Collections.emptyList());
        when(eventMapper.findByTaskId("task-1")).thenReturn(Collections.emptyList());

        WorkflowTaskVO result = engine.getTask("tenant-a", "task-1");

        assertThat(result).isNotNull();
        assertThat(result.getTenantId()).isEqualTo("tenant-a");
    }

    @Test
    void hidesTaskAndEventsFromAnotherTenant() {
        when(taskMapper.findByTenantAndTaskId("tenant-b", "task-1")).thenReturn(null);

        WorkflowTaskVO task = engine.getTask("tenant-b", "task-1");
        List<WorkflowEventVO> events = engine.getTaskEvents("tenant-b", "task-1");

        assertThat(task).isNull();
        assertThat(events).isEmpty();
        verify(stepMapper, never()).findByTaskId("task-1");
        verify(eventMapper, never()).findByTaskId("task-1");
    }

    @Test
    void persistsTaskAndStepLifecycleWithEventsAndMetrics() {
        AgentTaskRecord task = engine.startTask(
                "tenant-a", "REACT", "question", "", "chat-1", "session-1");
        AgentStepRecord step = engine.startStep(task.getTaskId(), "planner", 1, Map.of("prompt", "question"));
        when(stepMapper.findByStepId(step.getStepId())).thenReturn(step);

        engine.completeStep(
                step.getStepId(), "DONE", Map.of("answer", "ok"), Map.of("found", true),
                "reason", "search", Map.of("query", "question"),
                10, 20, 35, null);
        engine.completeTask(task.getTaskId(), WorkflowState.DONE, "final answer");
        engine.recordStepMetrics("planner", "DONE", 35);
        engine.recordTaskMetrics("REACT", "DONE", 50);

        assertThat(task.getTenantId()).isEqualTo("tenant-a");
        assertThat(task.getModelProfile()).isEqualTo("balanced");
        assertThat(step.getThought()).isEqualTo("reason");
        assertThat(step.getAction()).isEqualTo("search");
        verify(taskMapper).insert(task);
        verify(taskMapper).updateStatus(task.getTaskId(), WorkflowState.PLANNING.name());
        verify(stepMapper).insert(step);
        verify(stepMapper).updateById(step);
        verify(taskMapper).completeTask(task.getTaskId(), WorkflowState.DONE.name(), "final answer");
        ArgumentCaptor<AgentEventRecord> eventCaptor = ArgumentCaptor.forClass(AgentEventRecord.class);
        verify(eventMapper, org.mockito.Mockito.atLeastOnce()).insert(eventCaptor.capture());
        assertThat(eventCaptor.getAllValues()).isNotEmpty();
    }

    @Test
    void convertsScopedTaskDetailsAndHandlesInvalidState() {
        LocalDateTime now = LocalDateTime.now();
        AgentTaskRecord task = AgentTaskRecord.builder()
                .taskId("task-2")
                .tenantId("tenant-a")
                .type("RESEARCH")
                .status(WorkflowState.WRITING.name())
                .userInput("topic")
                .modelProfile("quality")
                .createdAt(now)
                .updatedAt(now)
                .build();
        AgentStepRecord step = AgentStepRecord.builder()
                .stepId("step-2")
                .taskId("task-2")
                .agentName("writer")
                .status("DONE")
                .stepOrder(2)
                .actionInputJson("{\"topic\":\"java\"}")
                .observationJson("{\"sources\":2}")
                .build();
        AgentEventRecord event = AgentEventRecord.builder()
                .eventId("event-2")
                .taskId("task-2")
                .eventType("STATE_CHANGED")
                .payloadJson("{\"to\":\"WRITING\"}")
                .createdAt(now)
                .build();
        when(taskMapper.findByTenantAndTaskId("tenant-a", "task-2")).thenReturn(task);
        when(stepMapper.findByTaskId("task-2")).thenReturn(List.of(step));
        when(eventMapper.findByTaskId("task-2")).thenReturn(List.of(event));
        when(taskMapper.findByTenant("tenant-a", 0, 20)).thenReturn(List.of(task));
        when(taskMapper.findByTaskId("task-2")).thenReturn(task);

        WorkflowTaskVO detail = engine.getTask("tenant-a", "task-2");
        List<WorkflowTaskVO> listed = engine.listTasks("tenant-a", 1, 20);
        List<WorkflowEventVO> events = engine.getTaskEvents("tenant-a", "task-2");
        WorkflowState state = engine.currentState("task-2");

        assertThat(detail.getSteps()).singleElement()
                .satisfies(item -> assertThat(item.getActionInput()).containsEntry("topic", "java"));
        assertThat(detail.getEvents()).singleElement()
                .satisfies(item -> assertThat(item.getPayload()).containsEntry("to", "WRITING"));
        assertThat(listed).hasSize(1);
        assertThat(events).hasSize(1);
        assertThat(state).isEqualTo(WorkflowState.WRITING);

        task.setStatus("NOT_A_STATE");
        assertThat(engine.currentState("task-2")).isEqualTo(WorkflowState.FAILED);
        when(taskMapper.findByTaskId("missing")).thenReturn(null);
        assertThat(engine.currentState("missing")).isNull();

    }

    @Test
    void rejectsInvalidStateTransitionWithoutPersisting() {
        engine.transitionStatus("task-illegal", WorkflowState.CREATED, WorkflowState.DONE);

        verify(taskMapper, never()).updateStatus("task-illegal", WorkflowState.DONE.name());
        verifyNoInteractions(eventMapper);
    }

    @Test
    void skipsEventWhenTransitionAffectsZeroRows() {
        when(taskMapper.updateStatus("task-stale", WorkflowState.PLANNING.name())).thenReturn(0);

        engine.transitionStatus("task-stale", WorkflowState.CREATED, WorkflowState.PLANNING);

        verify(taskMapper).updateStatus("task-stale", WorkflowState.PLANNING.name());
        verifyNoInteractions(eventMapper);
    }
}
