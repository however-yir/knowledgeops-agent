import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { HistoryService } from "../history/history.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { PlatformStore } from "../platform/platform.store.js";
import { TenantCostService } from "../platform/tenant-cost.service.js";
import { newId } from "../common/ids.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import { RetrievalService } from "./retrieval.service.js";

@Injectable()
export class AiService {
  constructor(
    private readonly store: PlatformStore,
    private readonly retrievalService: RetrievalService,
    private readonly historyService: HistoryService,
    private readonly modelRouter: ModelRouterService,
    private readonly costService: TenantCostService,
    private readonly metrics: MetricsService,
    private readonly llmClient: OpenAiCompatibleClient
  ) {}

  async reactChat(request: ReactChatRequest, tenantId = "public", historyType = "react"): Promise<ReactChatResponse> {
    const started = Date.now();
    const prompt = request.prompt || "";
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    const rag = await this.retrievalService.answerAsync(prompt, tenantId, request.chatId);
    const memoryUsed = this.relevantMemory(tenantId, prompt);
    const context = [prompt, ...rag.evidence, ...memoryUsed].join("\n");
    const estimatedInputTokens = this.costService.estimateTokens(context);
    const localAnswer = composeAnswer(rag.answer, memoryUsed);
    const estimatedOutputTokens = this.costService.estimateTokens(localAnswer);
    this.costService.assertBudget(tenantId, route.costTier, estimatedInputTokens, estimatedOutputTokens);
    const llmResult = await this.generateWithFallback({
      prompt,
      route,
      groundedContext: rag.evidence,
      memoryContext: memoryUsed
    });
    const finalAnswer = llmResult?.answer ?? localAnswer;
    const inputTokens = llmResult?.inputTokens ?? estimatedInputTokens;
    const outputTokens = llmResult?.outputTokens ?? this.costService.estimateTokens(finalAnswer);
    this.costService.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    this.metrics.increment("react_requests_total", { outcome: "success", route: route.profile });
    this.metrics.increment("react_latency_ms_sum", { route: route.profile }, Date.now() - started);
    this.metrics.observe("react_latency_ms", Date.now() - started, { route: route.profile });

    const response = {
      ok: 1,
      msg: "ok",
      chatId: request.chatId,
      answer: finalAnswer,
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
          thought: "Generate a grounded answer using the routed model, falling back to deterministic local composition when needed.",
          action: llmResult?.degraded === false ? "llm_generate" : "local_fallback",
          actionInput: { routeProfile: route.profile },
          observation: {
            status: "completed",
            model: llmResult?.model ?? "local-grounded",
            degraded: llmResult?.degraded ?? true,
            errorMessage: llmResult?.errorMessage,
            inputTokens,
            outputTokens
          }
        }
      ]
    };
    if (request.chatId?.trim()) {
      this.historyService.appendExchange(tenantId, historyType, request.chatId, prompt, finalAnswer);
      this.saveConversationSummary(tenantId, request.chatId, prompt, finalAnswer);
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

  private async generateWithFallback(input: {
    prompt: string;
    route: ReturnType<ModelRouterService["resolve"]>;
    groundedContext: string[];
    memoryContext: string[];
  }) {
    try {
      return await this.llmClient.complete(input);
    } catch (error) {
      this.metrics.increment("llm_fallback_total", { route: input.route.profile });
      return undefined;
    }
  }

  private saveConversationSummary(tenantId: string, chatId: string, prompt: string, answer: string): void {
    const content = `chat=${chatId}; user=${prompt.slice(0, 180)}; assistant=${answer.slice(0, 220)}`;
    const exists = this.store.memoryItems.some((item) => item.tenantId === tenantId && item.source === "chat_summary" && item.sourceTaskId === chatId && item.content === content);
    if (exists) {
      return;
    }
    const now = new Date().toISOString();
    this.store.memoryItems.push({
      memoryId: newId("mem"),
      tenantId,
      userId: "anonymous",
      type: "short",
      content,
      source: "chat_summary",
      sourceTaskId: chatId,
      confidence: 0.6,
      expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      createdAt: now,
      updatedAt: now
    });
    this.store.persist();
  }
}

function composeAnswer(ragAnswer: string, memoryUsed: string[]): string {
  if (memoryUsed.length === 0) {
    return ragAnswer;
  }
  return `${ragAnswer}\n\n记忆上下文:\n${memoryUsed.map((item) => `- ${item}`).join("\n")}`;
}
