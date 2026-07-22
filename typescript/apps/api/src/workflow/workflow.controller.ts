import { BadRequestException, Body, Controller, Get, Header, NotFoundException, Param, Post, Query } from "@nestjs/common";
import type { ReactChatRequest } from "@knowledgeops/shared";

import { AiService } from "../ai/ai.service.js";
import { TenantId } from "../common/tenant-id.decorator.js";
import { env } from "../config/env.js";
import { WorkflowService } from "./workflow.service.js";

@Controller()
export class WorkflowController {
  constructor(private readonly workflowService: WorkflowService, private readonly aiService: AiService) {}

  @Get("ai/workflow/tasks/:taskId")
  getTask(@TenantId() tenantId: string, @Param("taskId") taskId: string) {
    const task = this.workflowService.getTask(tenantId, taskId);
    if (!task) {
      throw new NotFoundException("task not found");
    }
    return task;
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
  async createResearch(
    @TenantId() tenantId: string,
    @Body() body: { topic?: string; prompt?: string; modelProfile?: string } | null | undefined
  ) {
    if (!body) {
      throw new BadRequestException("research request is required");
    }
    const topic = body.topic ?? body.prompt ?? "research";
    const task = env.APP_WORKFLOW_ASYNC_ENABLED
      ? this.workflowService.enqueueResearch(tenantId, topic, body.modelProfile)
      : await this.workflowService.executeResearchAsync(tenantId, topic, body.modelProfile);
    return this.workflowService.toResearchResult(task);
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
    if (!task) {
      throw new NotFoundException("task not found");
    }
    return { taskId: task.taskId, report: task.finalOutput };
  }

  @Post("ai/workflow/react/chat")
  async workflowReact(@TenantId() tenantId: string, @Body() body: ReactChatRequest | null | undefined) {
    if (!body) {
      throw new BadRequestException("request is required");
    }
    const task = this.workflowService.startReactTask(tenantId, body.prompt, body.modelProfile, body.chatId, body.sessionId);
    try {
      const response = await this.aiService.reactChat(body, tenantId, "workflow_react");
      this.workflowService.completeReactTask(tenantId, task.taskId, response.answer);
      this.workflowService.attachSessionSnapshot(tenantId, task.taskId, response.traceId, body.sessionId, body.branchId, body.messageId);
      return response;
    } catch (error) {
      this.workflowService.failReactTask(tenantId, task.taskId, error);
      throw error;
    }
  }

  @Post("ai/workflow/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  async workflowReactStream(@TenantId() tenantId: string, @Body() body: ReactChatRequest | null | undefined) {
    if (!body) {
      throw new BadRequestException("request is required");
    }
    const task = this.workflowService.startReactTask(
      tenantId,
      body.prompt,
      body.modelProfile,
      body.chatId,
      body.sessionId,
      "REACT_STREAM"
    );
    try {
      const stream = await this.aiService.reactChatStream(body, tenantId, "workflow_react");
      const response = streamDoneData(stream);
      if (response) {
        this.workflowService.completeReactTask(tenantId, task.taskId, String(response.answer ?? ""));
        this.workflowService.attachSessionSnapshot(
          tenantId,
          task.taskId,
          optionalString(response.traceId),
          body.sessionId,
          body.branchId,
          body.messageId
        );
      }
      return stream;
    } catch (error) {
      this.workflowService.failReactTask(tenantId, task.taskId, error);
      throw error;
    }
  }
}

function streamDoneData(stream: string): Record<string, unknown> | undefined {
  for (const event of stream.split("\n\n")) {
    if (!event.startsWith("event: done")) {
      continue;
    }
    const data = event.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
    if (!data) {
      return undefined;
    }
    try {
      const parsed = JSON.parse(data) as { data?: Record<string, unknown> };
      return parsed.data;
    } catch {
      return undefined;
    }
  }
  return undefined;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
