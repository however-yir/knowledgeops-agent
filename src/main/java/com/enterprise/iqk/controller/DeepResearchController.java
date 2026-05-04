package com.enterprise.iqk.controller;

import com.enterprise.iqk.agent.research.DeepResearchService;
import com.enterprise.iqk.agent.research.ResearchTaskRequest;
import com.enterprise.iqk.agent.workflow.AgentWorkflowEngine;
import com.enterprise.iqk.agent.workflow.WorkflowEventVO;
import com.enterprise.iqk.agent.workflow.WorkflowTaskVO;
import com.enterprise.iqk.security.TenantContext;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@Tag(name = "Deep Research", description = "多Agent深度研究API")
@RestController
@RequestMapping("/ai/research")
@RequiredArgsConstructor
public class DeepResearchController {

    private final DeepResearchService deepResearchService;
    private final AgentWorkflowEngine workflowEngine;

    @Operation(summary = "创建并执行深度研究任务")
    @PostMapping("/tasks")
    public ResponseEntity<?> createResearch(@RequestBody ResearchTaskRequest request,
                                             @RequestHeader(value = "X-Tenant-Id", defaultValue = "public") String tenantId) {
        DeepResearchService.DeepResearchResult result = deepResearchService.executeResearch(request, tenantId);
        return ResponseEntity.ok(result);
    }

    @Operation(summary = "查询研究任务详情")
    @GetMapping("/tasks/{taskId}")
    public ResponseEntity<?> getTask(@PathVariable String taskId) {
        WorkflowTaskVO task = workflowEngine.getTask(taskId);
        if (task == null) {
            return ResponseEntity.status(404).body(Map.of("ok", 0, "msg", "task not found"));
        }
        return ResponseEntity.ok(task);
    }

    @Operation(summary = "查询研究任务事件流")
    @GetMapping("/tasks/{taskId}/events")
    public ResponseEntity<List<WorkflowEventVO>> getEvents(@PathVariable String taskId) {
        return ResponseEntity.ok(workflowEngine.getTaskEvents(taskId));
    }

    @Operation(summary = "查询研究任务报告")
    @GetMapping("/tasks/{taskId}/report")
    public ResponseEntity<?> getReport(@PathVariable String taskId) {
        WorkflowTaskVO task = workflowEngine.getTask(taskId);
        if (task == null) {
            return ResponseEntity.status(404).body(Map.of("ok", 0, "msg", "task not found"));
        }
        return ResponseEntity.ok(Map.of("taskId", task.getTaskId(), "report", task.getFinalOutput()));
    }
}
