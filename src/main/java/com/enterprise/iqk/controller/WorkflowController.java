package com.enterprise.iqk.controller;

import com.enterprise.iqk.agent.workflow.AgentWorkflowEngine;
import com.enterprise.iqk.agent.workflow.WorkflowEventVO;
import com.enterprise.iqk.agent.workflow.WorkflowReactAgentService;
import com.enterprise.iqk.agent.workflow.WorkflowTaskVO;
import com.enterprise.iqk.domain.vo.ReactChatRequestVO;
import com.enterprise.iqk.domain.vo.ReactChatResponseVO;
import com.enterprise.iqk.security.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

@Tag(name = "Agent Workflow", description = "多Agent工作流任务管理")
@RestController
@RequestMapping("/ai/workflow")
@RequiredArgsConstructor
public class WorkflowController {

    private final WorkflowReactAgentService workflowReactAgentService;
    private final AgentWorkflowEngine workflowEngine;

    @Operation(summary = "同步ReAct工作流")
    @PostMapping("/react/chat")
    public ResponseEntity<ReactChatResponseVO> reactChat(@RequestBody ReactChatRequestVO request) {
        return ResponseEntity.ok(workflowReactAgentService.chat(request));
    }

    @Operation(summary = "流式ReAct工作流 (SSE)")
    @PostMapping(value = "/react/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> reactChatStream(@RequestBody ReactChatRequestVO request) {
        return workflowReactAgentService.stream(request);
    }

    @Operation(summary = "查询工作流任务详情")
    @GetMapping("/tasks/{taskId}")
    public ResponseEntity<?> getTask(@PathVariable String taskId) {
        WorkflowTaskVO task = workflowEngine.getTask(taskId);
        if (task == null) {
            return ResponseEntity.status(404).body(Map.of("ok", 0, "msg", "task not found"));
        }
        return ResponseEntity.ok(task);
    }

    @Operation(summary = "查询工作流任务事件列表")
    @GetMapping("/tasks/{taskId}/events")
    public ResponseEntity<List<WorkflowEventVO>> getTaskEvents(@PathVariable String taskId) {
        return ResponseEntity.ok(workflowEngine.getTaskEvents(taskId));
    }

    @Operation(summary = "查询租户工作流任务列表")
    @GetMapping("/tasks")
    public ResponseEntity<List<WorkflowTaskVO>> listTasks(
            @RequestHeader(value = "X-Tenant-Id", defaultValue = "public") String tenantId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ResponseEntity.ok(workflowEngine.listTasks(
                TenantContext.normalize(tenantId), page, pageSize));
    }
}
