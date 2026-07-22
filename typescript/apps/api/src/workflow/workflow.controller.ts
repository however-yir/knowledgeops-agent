import { Body, Controller, Get, Header, Param, Post, Query } from "@nestjs/common";

import { AiService } from "../ai/ai.service.js";
import { TenantId } from "../common/tenant-id.decorator.js";
import { env } from "../config/env.js";
import { WorkflowService } from "./workflow.service.js";

@Controller()
export class WorkflowController {
  constructor(private readonly workflowService: WorkflowService, private readonly aiService: AiService) {}

  @Get("ai/workflow/tasks/:taskId")
  getTask(@TenantId() tenantId: string, @Param("taskId") taskId: string) {
    return this.workflowService.getTask(tenantId, taskId) ?? { ok: 0, msg: "task not found" };
  }

  @Get("ai/workflow/tasks/:taskId/events")
  getTaskEvents(@TenantId() tenantId: string, @Param("taskId") taskId: string) {
    return this.workflowService.getEvents(tenantId, taskId);
  }

  @Get("ai/workflow/tasks")
  listTasks(@TenantId() tenantId: string, @Query("page") page = "1", @Query("pageSize") pageSize = "20") {
    return this.workflowService.listTasks(tenantId, Number(page), Number(pageSize));
  }

  @Post("ai/research/tasks")
  async createResearch(@TenantId() tenantId: string, @Body() body: { topic?: string; prompt?: string; modelProfile?: string }) {
    const prompt = body.topic ?? body.prompt ?? "research";
    const task = env.APP_WORKFLOW_ASYNC_ENABLED
      ? this.workflowService.enqueueResearch(tenantId, prompt, body.modelProfile)
      : await this.workflowService.executeResearchAsync(tenantId, prompt, body.modelProfile);
    return {
      ok: 1,
      taskId: task.taskId,
      report: task.finalOutput,
      task
    };
  }

  @Get("ai/research/tasks/:taskId")
  getResearchTask(@TenantId() tenantId: string, @Param("taskId") taskId: string) {
    return this.getTask(tenantId, taskId);
  }

  @Get("ai/research/tasks/:taskId/events")
  getResearchEvents(@TenantId() tenantId: string, @Param("taskId") taskId: string) {
    return this.getTaskEvents(tenantId, taskId);
  }

  @Get("ai/research/tasks/:taskId/report")
  getResearchReport(@TenantId() tenantId: string, @Param("taskId") taskId: string) {
    const task = this.workflowService.getTask(tenantId, taskId);
    return task ? { taskId, report: task.finalOutput } : { ok: 0, msg: "task not found" };
  }

  @Post("ai/workflow/react/chat")
  async workflowReact(
    @TenantId() tenantId: string,
    @Body() body: { prompt: string; chatId: string; modelProfile?: string; sessionId?: string }
  ) {
    this.workflowService.startReactTask(tenantId, body.prompt, body.modelProfile, body.chatId, body.sessionId);
    return this.aiService.reactChat(body, tenantId, "workflow_react");
  }

  @Post("ai/workflow/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  async workflowReactStream(
    @TenantId() tenantId: string,
    @Body() body: { prompt: string; chatId: string; modelProfile?: string; sessionId?: string }
  ) {
    this.workflowService.startReactTask(tenantId, body.prompt, body.modelProfile, body.chatId, body.sessionId);
    return this.aiService.reactChatStream(body, tenantId, "workflow_react");
  }
}
