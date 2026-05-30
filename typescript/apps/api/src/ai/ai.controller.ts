import { Body, Controller, Get, Headers, Header, Post, Query } from "@nestjs/common";
import type { ReactChatRequest } from "@knowledgeops/shared";

import { normalizeTenant, TENANT_HEADER } from "../common/tenant.js";
import { AiService } from "./ai.service.js";

@Controller()
export class AiController {
  constructor(private readonly aiService: AiService) {}

  @Post("ai/react/chat")
  reactChat(@Body() request: ReactChatRequest) {
    return this.aiService.reactChat(request);
  }

  @Post("ai/react/chat/stream")
  @Header("Content-Type", "text/event-stream")
  reactChatStream(@Body() request: ReactChatRequest) {
    return this.aiService.textStream(this.aiService.reactChat(request));
  }

  @Get("ai/chat")
  @Header("Content-Type", "text/html;charset=utf-8")
  chat(@Query("prompt") prompt: string, @Query("chatId") chatId: string, @Query("modelProfile") modelProfile?: string) {
    return this.aiService.reactChat({ prompt, chatId, modelProfile }).answer;
  }

  @Get("ai/pdf/chat")
  @Header("Content-Type", "text/html;charset=UTF-8")
  pdfChat(@Query("prompt") prompt: string, @Query("chatId") chatId: string, @Query("modelProfile") modelProfile?: string) {
    const result = this.aiService.reactChat({ prompt, chatId, modelProfile });
    return `${result.answer}\n\n引用来源:\n[1] ${result.citations?.[0] ?? "typescript://rag/in-memory"}`;
  }

  @Post("ai/feedback")
  feedback(@Headers(TENANT_HEADER) tenantHeader: string | undefined, @Body() payload: Record<string, unknown>) {
    this.aiService.saveFeedback(normalizeTenant(tenantHeader), payload ?? {});
    return { ok: 1, msg: "ok" };
  }
}
