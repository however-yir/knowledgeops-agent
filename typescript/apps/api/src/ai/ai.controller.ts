import { All, Body, Controller, Get, Post, Query, Req, Res } from "@nestjs/common";
import type { FastifyReply, FastifyRequest } from "fastify";
import type { ReactChatRequest } from "@knowledgeops/shared";

import type { RequestWithContext } from "../common/request-context.js";
import { traceIdFrom } from "../common/trace.js";
import { AiService } from "./ai.service.js";
import { AnswerFeedbackService, type AnswerFeedbackPayload } from "./answer-feedback.service.js";
import { sendSse } from "./sse.js";

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
  async reactChatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest, @Res() reply: FastifyReply): Promise<void> {
    await sendSse(req, reply, (signal) => this.aiService.reactChatStream(request, tenantFrom(req), "react", traceIdFrom(req), signal));
  }

  @Post("ai/chat")
  async chatPost(@Body() body: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.chat(body, tenantFrom(req), "chat", traceIdFrom(req));
  }

  @Post("ai/chat/stream")
  async chatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest, @Res() reply: FastifyReply): Promise<void> {
    await sendSse(req, reply, (signal) => this.aiService.chatStream(request, tenantFrom(req), "chat", traceIdFrom(req), signal));
  }

  @Post("ai/service")
  async service(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Body() body: Partial<ReactChatRequest> | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, body);
    return this.aiService.chat(request, tenantFrom(req), "service", traceIdFrom(req));
  }

  @Post("ai/pdf/chat")
  async pdfChatPost(@Body() body: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.ragChat(body, tenantFrom(req), "pdf", traceIdFrom(req));
  }

  @Post("ai/pdf/chat/stream")
  async pdfChatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest, @Res() reply: FastifyReply): Promise<void> {
    await sendSse(req, reply, (signal) => this.aiService.ragChatStream(request, tenantFrom(req), "pdf", traceIdFrom(req), signal));
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
