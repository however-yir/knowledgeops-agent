import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { HistoryService } from "../history/history.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { RetrievalService } from "./retrieval.service.js";

@Injectable()
export class AiService {
  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly historyService: HistoryService
  ) {}

  reactChat(request: ReactChatRequest, tenantId = "public", historyType = "react"): ReactChatResponse {
    const prompt = request.prompt || "";
    const rag = this.retrievalService.answer(prompt, tenantId, request.chatId);
    const response = {
      ok: 1,
      msg: "ok",
      chatId: request.chatId,
      answer: rag.answer,
      citations: rag.citations,
      evidence: rag.evidence,
      routeProfile: request.modelProfile ?? "balanced",
      routeReason: "typescript local hybrid retrieval",
      routeCostTier: "low",
      trace: [
        {
          step: 1,
          thought: "Retrieve tenant-scoped chunks and compose a grounded answer.",
          action: "rag_retrieve",
          actionInput: { prompt, chatId: request.chatId, tenantId },
          observation: { citations: rag.citations.length, evidence: rag.evidence.length }
        }
      ]
    };
    if (request.chatId?.trim()) {
      this.historyService.appendExchange(tenantId, historyType, request.chatId, prompt, rag.answer);
    }
    return response;
  }

  textStream(response: ReactChatResponse): string {
    const token = JSON.stringify({ token: response.answer });
    const done = JSON.stringify({ chatId: response.chatId });
    return `event: token\ndata: ${token}\n\nevent: done\ndata: ${done}\n\n`;
  }

  saveFeedback(tenantId: string, payload: Record<string, unknown>): void {
    this.store.feedback.push({ tenantId, ...payload, createdAt: new Date().toISOString() });
    this.store.persist();
  }
}
