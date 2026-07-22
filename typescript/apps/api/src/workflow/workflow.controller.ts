import { BadRequestException, Body, Controller, Get, NotFoundException, Param, Post, Query, Req, Res } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { ReactChatRequest } from "@knowledgeops/shared";

import { AiService } from "../ai/ai.service.js";
import { formatSse, sendSse, type SseEvent } from "../ai/sse.js";
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
  async workflowReactStream(
    @TenantId() tenantId: string,
    @Body() body: ReactChatRequest | null | undefined,
    @Req() request?: FastifyRequest,
    @Res() reply?: FastifyReply
  ): Promise<string | void> {
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
    let doneData: Record<string, unknown> | undefined;
    try {
      if (request && reply) {
        await sendSse(request, reply, (signal) => trackDoneEvents(
          this.aiService.reactChatStream(body, tenantId, "workflow_react", undefined, signal),
          (value) => { doneData = value; }
        ));
        this.completeStreamTask(tenantId, task.taskId, doneData, body);
        return;
      }
      const stream = await this.aiService.reactChatStream(body, tenantId, "workflow_react");
      if (typeof stream === "string") {
        doneData = streamDoneData(stream);
        this.completeStreamTask(tenantId, task.taskId, doneData, body);
        return stream;
      }
      let output = "";
      for await (const event of trackDoneEvents(stream, (value) => { doneData = value; })) {
        output += formatSse(event);
      }
      this.completeStreamTask(tenantId, task.taskId, doneData, body);
      return output;
    } catch (error) {
      this.workflowService.failReactTask(tenantId, task.taskId, error);
      throw error;
    }
  }

  private completeStreamTask(tenantId: string, taskId: string, response: Record<string, unknown> | undefined, body: ReactChatRequest): void {
    if (!response) {
      return;
    }
    this.workflowService.completeReactTask(tenantId, taskId, String(response.answer ?? ""));
    this.workflowService.attachSessionSnapshot(
      tenantId,
      taskId,
      optionalString(response.traceId),
      body.sessionId,
      body.branchId,
      body.messageId
    );
  }
}

async function* trackDoneEvents(stream: AsyncIterable<SseEvent>, onDone: (value: Record<string, unknown> | undefined) => void): AsyncGenerator<SseEvent> {
  for await (const event of stream) {
    if (event.event === "done") {
      onDone(doneDataFromPayload(event.data));
    }
    yield event;
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
      return doneDataFromPayload(JSON.parse(data));
    } catch {
      return undefined;
    }
  }
  return undefined;
}

function doneDataFromPayload(value: unknown): Record<string, unknown> | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  return isRecord(value.data) ? value.data : value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
