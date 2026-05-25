package com.enterprise.iqk.agent.workflow;

import com.enterprise.iqk.security.TenantContext;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class AgentWorkflowEngine {

    private final AgentTaskMapper taskMapper;
    private final AgentStepMapper stepMapper;
    private final AgentEventMapper eventMapper;
    private final ObjectMapper objectMapper;
    private final MeterRegistry meterRegistry;

    // ── Task lifecycle ───────────────────────────────────────────

    public AgentTaskRecord startTask(String tenantId, String type, String userInput,
                                     String modelProfile, String chatId, String sessionId) {
        String taskId = "task-" + UUID.randomUUID().toString().replace("-", "");
        LocalDateTime now = LocalDateTime.now();
        AgentTaskRecord task = AgentTaskRecord.builder()
                .taskId(taskId)
                .tenantId(TenantContext.normalize(tenantId))
                .type(type)
                .status(WorkflowState.CREATED.name())
                .userInput(userInput)
                .modelProfile(StringUtils.hasText(modelProfile) ? modelProfile : "balanced")
                .chatId(chatId)
                .sessionId(sessionId)
                .createdAt(now)
                .updatedAt(now)
                .build();
        taskMapper.insert(task);
        transitionStatus(taskId, WorkflowState.CREATED, WorkflowState.PLANNING);
        return task;
    }

    public AgentStepRecord startStep(String taskId, String agentName, int stepOrder,
                                      Map<String, Object> input) {
        String stepId = "step-" + UUID.randomUUID().toString().replace("-", "");
        AgentStepRecord step = AgentStepRecord.builder()
                .stepId(stepId)
                .taskId(taskId)
                .agentName(agentName)
                .status("RUNNING")
                .stepOrder(stepOrder)
                .inputJson(toJson(input))
                .startedAt(LocalDateTime.now())
                .build();
        stepMapper.insert(step);
        emitEvent(taskId, stepId, "STEP_STARTED", Map.of("agentName", agentName, "stepOrder", stepOrder));
        return step;
    }

    public void completeStep(String stepId, String status, Map<String, Object> output,
                              Object observation, String thought, String action,
                              Map<String, Object> actionInput,
                              long inputTokens, long outputTokens, long latencyMs,
                              String errorMessage) {
        stepMapper.completeStep(stepId, status,
                toJson(output), toJson(observation),
                outputTokens, latencyMs, errorMessage);

        AgentStepRecord step = stepMapper.findByStepId(stepId);
        if (StringUtils.hasText(thought) && step != null) {
            step.setThought(thought);
            step.setAction(action);
            step.setActionInputJson(toJson(actionInput));
            stepMapper.updateById(step);
        }
        String taskId = step == null ? "unknown" : step.getTaskId();
        emitEvent(taskId, stepId, "STEP_COMPLETED",
                Map.of("status", status, "latencyMs", latencyMs));
    }

    public void completeTask(String taskId, WorkflowState finalStatus, String finalOutput) {
        taskMapper.completeTask(taskId, finalStatus.name(), finalOutput);
        emitEvent(taskId, null, "TASK_COMPLETED",
                Map.of("status", finalStatus.name()));
    }

    public void failTask(String taskId, String errorMessage) {
        taskMapper.completeTask(taskId, WorkflowState.FAILED.name(), errorMessage);
        emitEvent(taskId, null, "TASK_FAILED", Map.of("error", errorMessage));
    }

    // ── State management ─────────────────────────────────────────

    public void transitionStatus(String taskId, WorkflowState from, WorkflowState to) {
        if (!from.canTransitionTo(to)) {
            log.warn("Invalid state transition: {} -> {} for task {}", from, to, taskId);
        }
        taskMapper.updateStatus(taskId, to.name());
        emitEvent(taskId, null, "STATE_CHANGED",
                Map.of("from", from.name(), "to", to.name()));
    }

    public WorkflowState currentState(String taskId) {
        AgentTaskRecord task = taskMapper.findByTaskId(taskId);
        if (task == null) {
            return null;
        }
        try {
            return WorkflowState.valueOf(task.getStatus());
        } catch (IllegalArgumentException e) {
            return WorkflowState.FAILED;
        }
    }

    // ── Event sourcing ───────────────────────────────────────────

    public void emitEvent(String taskId, String stepId, String eventType, Map<String, Object> payload) {
        try {
            AgentEventRecord event = AgentEventRecord.builder()
                    .eventId("evt-" + UUID.randomUUID().toString().replace("-", ""))
                    .taskId(taskId)
                    .stepId(stepId)
                    .eventType(eventType)
                    .payloadJson(toJson(payload))
                    .createdAt(LocalDateTime.now())
                    .build();
            eventMapper.insert(event);
        } catch (Exception e) {
            log.error("Failed to persist agent event: taskId={}, type={}", taskId, eventType, e);
        }
    }

    // ── Metrics ──────────────────────────────────────────────────

    public void recordStepMetrics(String agentName, String status, long latencyMs) {
        Timer.builder("agent.workflow.step.latency")
                .description("Step execution latency")
                .tag("agent", agentName)
                .tag("status", status)
                .publishPercentileHistogram()
                .register(meterRegistry)
                .record(latencyMs, TimeUnit.MILLISECONDS);

        Counter.builder("agent.workflow.step.count")
                .description("Step execution count")
                .tag("agent", agentName)
                .tag("status", status)
                .register(meterRegistry)
                .increment();
    }

    public void recordTaskMetrics(String type, String status, long latencyMs) {
        Timer.builder("agent.workflow.task.latency")
                .description("Task execution latency")
                .tag("type", type)
                .tag("status", status)
                .publishPercentileHistogram()
                .register(meterRegistry)
                .record(latencyMs, TimeUnit.MILLISECONDS);

        Counter.builder("agent.workflow.task.count")
                .description("Task execution count")
                .tag("type", type)
                .tag("status", status)
                .register(meterRegistry)
                .increment();
    }

    // ── Query ────────────────────────────────────────────────────

    public WorkflowTaskVO getTask(String taskId) {
        AgentTaskRecord task = taskMapper.findByTaskId(taskId);
        if (task == null) {
            return null;
        }
        List<AgentStepRecord> steps = stepMapper.findByTaskId(taskId);
        List<AgentEventRecord> events = eventMapper.findByTaskId(taskId);
        return toTaskVO(task, steps, events);
    }

    public List<WorkflowTaskVO> listTasks(String tenantId, int page, int pageSize) {
        long offset = (long) (Math.max(1, page) - 1) * pageSize;
        return taskMapper.findByTenant(TenantContext.normalize(tenantId), offset, pageSize)
                .stream()
                .map(t -> toTaskVO(t, stepMapper.findByTaskId(t.getTaskId()),
                        Collections.emptyList()))
                .toList();
    }

    public List<WorkflowEventVO> getTaskEvents(String taskId) {
        return eventMapper.findByTaskId(taskId).stream()
                .map(this::toEventVO)
                .toList();
    }

    // ── Conversion helpers ───────────────────────────────────────

    private WorkflowTaskVO toTaskVO(AgentTaskRecord t, List<AgentStepRecord> steps,
                                     List<AgentEventRecord> events) {
        return WorkflowTaskVO.builder()
                .taskId(t.getTaskId())
                .tenantId(t.getTenantId())
                .type(t.getType())
                .status(t.getStatus())
                .userInput(t.getUserInput())
                .finalOutput(t.getFinalOutput())
                .modelProfile(t.getModelProfile())
                .chatId(t.getChatId())
                .sessionId(t.getSessionId())
                .createdAt(t.getCreatedAt())
                .updatedAt(t.getUpdatedAt())
                .steps(steps.stream().map(this::toStepVO).toList())
                .events(events.stream().map(this::toEventVO).toList())
                .build();
    }

    private WorkflowStepVO toStepVO(AgentStepRecord s) {
        return WorkflowStepVO.builder()
                .stepId(s.getStepId())
                .taskId(s.getTaskId())
                .agentName(s.getAgentName())
                .status(s.getStatus())
                .stepOrder(s.getStepOrder())
                .thought(s.getThought())
                .action(s.getAction())
                .actionInput(parseJsonMap(s.getActionInputJson()))
                .observation(s.getObservationJson() != null ? parseJsonMap(s.getObservationJson()) : null)
                .modelProfile(s.getModelProfile())
                .inputTokens(s.getInputTokens() != null ? s.getInputTokens() : 0)
                .outputTokens(s.getOutputTokens() != null ? s.getOutputTokens() : 0)
                .latencyMs(s.getLatencyMs() != null ? s.getLatencyMs() : 0)
                .errorMessage(s.getErrorMessage())
                .startedAt(s.getStartedAt())
                .endedAt(s.getEndedAt())
                .build();
    }

    private WorkflowEventVO toEventVO(AgentEventRecord e) {
        return WorkflowEventVO.builder()
                .eventId(e.getEventId())
                .taskId(e.getTaskId())
                .stepId(e.getStepId())
                .eventType(e.getEventType())
                .payload(parseJsonMap(e.getPayloadJson()))
                .createdAt(e.getCreatedAt())
                .build();
    }

    private Map<String, Object> parseJsonMap(String json) {
        if (!StringUtils.hasText(json)) {
            return Collections.emptyMap();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException e) {
            return Collections.emptyMap();
        }
    }

    private String toJson(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            return "{}";
        }
    }
}
