import { All, Body, Controller, Header, Post, Query, Req } from "@nestjs/common";
import type { FastifyRequest } from "fastify";
import type { ReactChatRequest } from "@knowledgeops/shared";

import type { RequestWithContext } from "../common/request-context.js";
import { AiService } from "./ai.service.js";

@Controller()
export class AiController {
  constructor(private readonly aiService: AiService) {}

  @Post("ai/react/chat")
  async reactChat(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChat(request, tenantFrom(req));
  }

  @Post("ai/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  async reactChatStream(@Body() request: ReactChatRequest, @Req() req: FastifyRequest) {
    return this.aiService.reactChatStream(request, tenantFrom(req));
  }

  @All("ai/chat")
  @Header("Content-Type", "text/html;charset=utf-8")
  async chat(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Body() body: Partial<ReactChatRequest> | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, body);
    return (await this.aiService.reactChat(request, tenantFrom(req), "chat")).answer;
  }

  @All("ai/service")
  @Header("Content-Type", "text/html;charset=utf-8")
  async service(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Body() body: Partial<ReactChatRequest> | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, body);
    return (await this.aiService.reactChat(request, tenantFrom(req), "service")).answer;
  }

  @All("ai/pdf/chat")
  @Header("Content-Type", "text/html;charset=UTF-8")
  async pdfChat(
    @Query("prompt") prompt: string | undefined,
    @Query("chatId") chatId: string | undefined,
    @Query("modelProfile") modelProfile: string | undefined,
    @Body() body: Partial<ReactChatRequest> | undefined,
    @Req() req: FastifyRequest
  ) {
    const request = chatRequestFrom(prompt, chatId, modelProfile, body);
    const result = await this.aiService.reactChat(request, tenantFrom(req), "pdf");
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
