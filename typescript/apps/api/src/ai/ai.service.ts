import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { PlatformStore } from "../platform/platform.store.js";

@Injectable()
export class AiService {
  constructor(private readonly store: PlatformStore) {}

  reactChat(request: ReactChatRequest): ReactChatResponse {
    const prompt = request.prompt || "";
    const answer = prompt
      ? `TS agent draft answer: ${prompt}`
      : "TS agent draft answer is ready.";
    return {
      ok: 1,
      msg: "ok",
      chatId: request.chatId,
      answer,
      citations: ["typescript://rag/in-memory"],
      evidence: ["Contract-first TypeScript RAG scaffold response."],
      routeProfile: request.modelProfile ?? "balanced",
      routeReason: "typescript scaffold route",
      routeCostTier: "low",
      trace: [
        {
          step: 1,
          thought: "Route request through the TypeScript contract scaffold.",
          action: "draft_answer",
          actionInput: { prompt },
          observation: { source: "in-memory" }
        }
      ]
    };
  }

  textStream(response: ReactChatResponse): string {
    const token = JSON.stringify({ token: response.answer });
    const done = JSON.stringify({ chatId: response.chatId });
    return `event: token\ndata: ${token}\n\nevent: done\ndata: ${done}\n\n`;
  }

  saveFeedback(tenantId: string, payload: Record<string, unknown>): void {
    this.store.feedback.push({ tenantId, ...payload, createdAt: new Date().toISOString() });
  }
}
