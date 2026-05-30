import { Body, Controller, Get, Header, Headers, Param, Post, Query } from "@nestjs/common";

import { TENANT_HEADER, normalizeTenant } from "../common/tenant.js";
import { AiService } from "../ai/ai.service.js";
import { WorkflowService } from "./workflow.service.js";

@Controller()
export class WorkflowController {
  constructor(private readonly workflowService: WorkflowService, private readonly aiService: AiService) {}

  @Get("ai/workflow/tasks/:taskId")
  getTask(@Param("taskId") taskId: string) {
    return this.workflowService.getTask(taskId) ?? { ok: 0, msg: "task not found" };
  }

  @Get("ai/workflow/tasks/:taskId/events")
  getTaskEvents(@Param("taskId") taskId: string) {
    return this.workflowService.getEvents(taskId);
  }

  @Get("ai/workflow/tasks")
  listTasks(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Query("page") page = "1", @Query("pageSize") pageSize = "20") {
    return this.workflowService.listTasks(normalizeTenant(tenantHeader), Number(page), Number(pageSize));
  }

  @Post("ai/research/tasks")
  createResearch(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() body: { topic?: string; prompt?: string; modelProfile?: string }) {
    const prompt = body.topic ?? body.prompt ?? "research";
    const task = this.workflowService.createTask(tenantHeader, "deep_research", prompt, body.modelProfile);
    return {
      ok: 1,
      taskId: task.taskId,
      report: task.finalOutput,
      task
    };
  }

  @Get("ai/research/tasks/:taskId")
  getResearchTask(@Param("taskId") taskId: string) {
    return this.getTask(taskId);
  }

  @Get("ai/research/tasks/:taskId/events")
  getResearchEvents(@Param("taskId") taskId: string) {
    return this.getTaskEvents(taskId);
  }

  @Get("ai/research/tasks/:taskId/report")
  getResearchReport(@Param("taskId") taskId: string) {
    const task = this.workflowService.getTask(taskId);
    return task ? { taskId, report: task.finalOutput } : { ok: 0, msg: "task not found" };
  }

  @Post("ai/workflow/react/chat")
  workflowReact(@Body() body: { prompt: string; chatId: string; modelProfile?: string }) {
    this.workflowService.createTask(undefined, "react_chat", body.prompt, body.modelProfile);
    return this.aiService.reactChat(body);
  }

  @Post("ai/workflow/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  workflowReactStream(@Body() body: { prompt: string; chatId: string; modelProfile?: string }) {
    this.workflowService.createTask(undefined, "react_chat", body.prompt, body.modelProfile);
    return this.aiService.textStream(this.aiService.reactChat(body));
  }
}
