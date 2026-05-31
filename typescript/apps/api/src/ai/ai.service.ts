import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { HistoryService } from "../history/history.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { TenantCostService } from "../platform/tenant-cost.service.js";
import { RetrievalService } from "./retrieval.service.js";

@Injectable()
export class AiService {
  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly historyService: HistoryService,
    private readonly modelRouter: ModelRouterService,
    private readonly costService: TenantCostService,
    private readonly metrics: MetricsService
  ) {}

  reactChat(request: ReactChatRequest, tenantId = "public", historyType = "react"): ReactChatResponse {
    const started = Date.now();
    const prompt = request.prompt || "";
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    const rag = this.retrievalService.answer(prompt, tenantId, request.chatId);
    const memoryUsed = this.relevantMemory(tenantId, prompt);
    const context = [prompt, ...rag.evidence, ...memoryUsed].join("\n");
    const inputTokens = this.costService.estimateTokens(context);
    const localAnswer = composeAnswer(rag.answer, memoryUsed);
    const outputTokens = this.costService.estimateTokens(localAnswer);
    this.costService.assertBudget(tenantId, route.costTier, inputTokens, outputTokens);
    this.costService.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    this.metrics.increment("react_requests_total", { outcome: "success", route: route.profile });
    this.metrics.increment("react_latency_ms_sum", { route: route.profile }, Date.now() - started);

    const response = {
      ok: 1,
      msg: "ok",
      chatId: request.chatId,
      answer: localAnswer,
      citations: rag.citations,
      evidence: rag.evidence,
      routeProfile: route.profile,
      routeReason: route.reason,
      routeCostTier: route.costTier,
      experimentKey: route.experimentKey,
      experimentVariant: route.experimentVariant,
      experimentBucket: route.experimentBucket,
      trace: [
        {
          step: 1,
          thought: "Resolve model profile, budget, memory, and hybrid retrieval context.",
          action: "hybrid_retrieve",
          actionInput: { prompt, chatId: request.chatId, tenantId, model: route.model },
          observation: {
            citations: rag.citations.length,
            evidence: rag.evidence.length,
            memoryUsed: memoryUsed.length,
            retrievalStats: rag.retrievalStats
          }
        },
        {
          step: 2,
          thought: "Compose a grounded answer from retrieved evidence.",
          action: "finish",
          actionInput: { routeProfile: route.profile },
          observation: { status: "completed", inputTokens, outputTokens }
        }
      ]
    };
    if (request.chatId?.trim()) {
      this.historyService.appendExchange(tenantId, historyType, request.chatId, prompt, localAnswer);
    }
    return response;
  }

  textStream(response: ReactChatResponse): string {
    const trace = response.trace.map((step) => `event: trace\ndata: ${JSON.stringify(step)}\n\n`).join("");
    const token = JSON.stringify({ token: response.answer });
    const done = JSON.stringify(response);
    return `${trace}event: token\ndata: ${token}\n\nevent: done\ndata: ${done}\n\n`;
  }

  saveFeedback(tenantId: string, payload: Record<string, unknown>): void {
    this.store.feedback.push({ tenantId, ...payload, createdAt: new Date().toISOString() });
    this.store.persist();
  }

  private relevantMemory(tenantId: string, prompt: string): string[] {
    const tokens = prompt.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    return this.store.memoryItems
      .filter((item) => item.tenantId === tenantId && (!item.expiresAt || Date.parse(item.expiresAt) > Date.now()))
      .map((item) => ({
        content: item.content,
        score: tokens.filter((token) => item.content.toLowerCase().includes(token)).length + item.confidence
      }))
      .filter((item) => item.score > 0.5)
      .sort((a, b) => b.score - a.score)
      .slice(0, 5)
      .map((item) => item.content);
  }
}

function composeAnswer(ragAnswer: string, memoryUsed: string[]): string {
  if (memoryUsed.length === 0) {
    return ragAnswer;
  }
  return `${ragAnswer}\n\n记忆上下文:\n${memoryUsed.map((item) => `- ${item}`).join("\n")}`;
}
