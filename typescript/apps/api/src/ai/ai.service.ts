import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { newId } from "../common/ids.js";
import { ChatService } from "./chat.service.js";
import { RagService } from "./rag.service.js";
import { ReactService } from "./react.service.js";
import type { SseEvent } from "./sse.js";

@Injectable()
export class AiService {
  constructor(
    private readonly chatService: ChatService,
    private readonly ragService: RagService,
    private readonly reactService: ReactService
  ) {}

  chat(request: ReactChatRequest, tenantId = "public", historyType = "chat", traceId = newId("trace"), signal?: AbortSignal): Promise<ReactChatResponse> {
    return this.chatService.chat(request, tenantId, historyType, traceId, signal);
  }

  ragChat(request: ReactChatRequest, tenantId = "public", historyType = "pdf", traceId = newId("trace"), signal?: AbortSignal): Promise<ReactChatResponse> {
    return this.ragService.chat(request, tenantId, historyType, traceId, signal);
  }

  reactChat(request: ReactChatRequest, tenantId = "public", historyType = "react", traceId = newId("trace"), signal?: AbortSignal): Promise<ReactChatResponse> {
    return this.reactService.chat(request, tenantId, historyType, traceId, signal);
  }

  chatStream(request: ReactChatRequest, tenantId = "public", historyType = "chat", traceId = newId("trace"), signal?: AbortSignal): AsyncIterable<SseEvent> {
    return this.chatService.stream(request, tenantId, historyType, traceId, signal);
  }

  ragChatStream(request: ReactChatRequest, tenantId = "public", historyType = "pdf", traceId = newId("trace"), signal?: AbortSignal): AsyncIterable<SseEvent> {
    return this.ragService.stream(request, tenantId, historyType, traceId, signal);
  }

  reactChatStream(request: ReactChatRequest, tenantId = "public", historyType = "react", traceId = newId("trace"), signal?: AbortSignal): AsyncIterable<SseEvent> {
    return this.reactService.stream(request, tenantId, historyType, traceId, signal);
  }
}
