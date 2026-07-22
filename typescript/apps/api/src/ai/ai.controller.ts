import { All, Body, Controller, Get, Header, Post, Query, Req } from "@nestjs/common";
import type { FastifyRequest } from "fastify";
import type { ReactChatRequest } from "@knowledgeops/shared";

import type { RequestWithContext } from "../common/request-context.js";
import { traceIdFrom } from "../common/trace.js";
import { AiService } from "./ai.service.js";
import { AnswerFeedbackService, type AnswerFeedbackPayload } from "./answer-feedback.service.js";

@Controller()
export class AiController {
  constructor(
    private readonly aiService: AiService,
    private readonly answerFeedbackService: AnswerFeedbackService
  ) {}

  @Post("ai/react/chat")
  async reactChat(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChat(request, tenantFrom(req), "react", traceIdFrom(req));
  }

  @Post("ai/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  async reactChatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChatStream(request, tenantFrom(req), "react", traceIdFrom(req));
  }

  @Post("ai/chat")
  async chatPost(@Body() body: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChat(body, tenantFrom(req), "chat", traceIdFrom(req));
  }

  @Get("ai/chat")
  async chat(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, undefined);
    return this.aiService.reactChat(request, tenantFrom(req), "chat", traceIdFrom(req));
  }

  @Post("ai/chat/stream")
  @Header("Content-Type", "text/event-stream")
  async chatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChatStream(request, tenantFrom(req), "chat", traceIdFrom(req));
  }

  @All("ai/service")
  async service(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Body() body: Partial<ReactChatRequest> | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, body);
    return this.aiService.reactChat(request, tenantFrom(req), "service", traceIdFrom(req));
  }

  @Post("ai/pdf/chat")
  async pdfChatPost(@Body() body: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChat(body, tenantFrom(req), "pdf", traceIdFrom(req));
  }

  @Get("ai/pdf/chat")
  async pdfChat(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, undefined);
    return this.aiService.reactChat(request, tenantFrom(req), "pdf", traceIdFrom(req));
  }

  @Post("ai/feedback")
  feedback(@Req() req: FastifyRequest, @Body() payload: AnswerFeedbackPayload) {
    this.answerFeedbackService.submit(tenantFrom(req), payload);
    return { ok: 1, msg: "ok" };
  }
}

function tenantFrom(req: FastifyRequest): string {
  return (req as RequestWithContext).context?.tenantId ?? "public";
}

function chatRequestFrom(
  prompt: string | undefined,
  chatId: string | undefined,
  modelProfile: string | undefined,
  body: Partial<ReactChatRequest> | undefined
): ReactChatRequest {
  return {
    prompt: prompt ?? body?.prompt ?? "",
    chatId: chatId ?? body?.chatId ?? "",
    modelProfile: modelProfile ?? body?.modelProfile
  };
}
