import { Body, Controller, Get, Header, Post, Query, Req } from "@nestjs/common";
import type { FastifyRequest } from "fastify";
import type { ReactChatRequest } from "@knowledgeops/shared";

import type { RequestWithContext } from "../common/request-context.js";
import { AiService } from "./ai.service.js";

@Controller()
export class AiController {
  constructor(private readonly aiService: AiService) {}

  @Post("ai/react/chat")
  reactChat(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChat(request, tenantFrom(req));
  }

  @Post("ai/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  reactChatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.textStream(this.aiService.reactChat(request, tenantFrom(req)));
  }

  @Get("ai/chat")
  @Header("Content-Type", "text/html;charset=utf-8")
  chat(@Query("prompt") prompt: string, @Query("chatId") chatId: string, @Query("modelProfile") modelProfile: string | undefined, @Req() req: FastifyRequest) {
    return this.aiService.reactChat({ prompt, chatId, modelProfile }, tenantFrom(req)).answer;
  }

  @Get("ai/pdf/chat")
  @Header("Content-Type", "text/html;charset=UTF-8")
  pdfChat(@Query("prompt") prompt: string, @Query("chatId") chatId: string, @Query("modelProfile") modelProfile: string | undefined, @Req() req: FastifyRequest) {
    const result = this.aiService.reactChat({ prompt, chatId, modelProfile }, tenantFrom(req));
    const citations = result.citations?.length
      ? result.citations.map((citation, index) => `[${index + 1}] ${citation}`).join("\n")
      : "";
    return citations ? `${result.answer}\n\n引用来源:\n${citations}` : result.answer;
  }

  @Post("ai/feedback")
  feedback(@Req() req: FastifyRequest, @Body() payload: Record<string, unknown>) {
    this.aiService.saveFeedback(tenantFrom(req), payload ?? {});
    return { ok: 1, msg: "ok" };
  }
}

function tenantFrom(req: FastifyRequest): string {
  return (req as RequestWithContext).context?.tenantId ?? "public";
}
