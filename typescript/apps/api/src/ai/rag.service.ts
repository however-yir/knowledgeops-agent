import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { newId } from "../common/ids.js";
import { env } from "../config/env.js";
import { HistoryService } from "../history/history.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { TenantCostService } from "../platform/tenant-cost.service.js";
import { explicitFallback, responseOf, stripEnvelope, validateRequest } from "./chat.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import { RetrievalService } from "./retrieval.service.js";
import type { SseEvent } from "./sse.js";

@Injectable()
export class RagService {
  constructor(
    private readonly retrieval: RetrievalService,
    private readonly history: HistoryService,
    private readonly modelRouter: ModelRouterService,
    private readonly cost: TenantCostService,
    private readonly metrics: MetricsService,
    private readonly llm: OpenAiCompatibleClient
  ) {}

  async chat(request: ReactChatRequest, tenantId = "public", historyType = "pdf", traceId = newId("trace"), signal?: AbortSignal): Promise<ReactChatResponse> {
    validateRequest(request);
    const rag = await this.retrieval.answerAsync(request.prompt, tenantId, request.chatId);
    const route = this.modelRouter.resolve(request.modelProfile, "rag", tenantId, request.chatId);
    const context = [request.prompt, ...rag.evidence].join("\n");
    const inputTokens = this.cost.estimateTokens(context);
    this.cost.assertBudget(tenantId, route.costTier, inputTokens, 600);
    let result;
    if (rag.citations.length > 0) {
      try {
        result = await this.llm.complete({
          prompt: request.prompt,
          route,
          groundedContext: rag.evidence,
          memoryContext: [],
          systemPrompt: env.RAG_ANSWER_SYSTEM_PROMPT,
          temperature: env.RAG_TEMPERATURE
        }, signal);
      } catch (error) {
        if (signal?.aborted) throw error;
        this.metrics.increment("llm_fallback_total", { route: route.profile, flow: "rag" });
      }
    }
    const answer = result?.answer ?? (rag.citations.length === 0 ? rag.answer : explicitFallback("rag", rag.answer));
    const outputTokens = result?.outputTokens ?? this.cost.estimateTokens(answer);
    const actualInputTokens = result?.inputTokens ?? inputTokens;
    this.cost.recordUsage(tenantId, route.costTier, actualInputTokens, outputTokens);
    this.metrics.increment("rag_requests_total", { outcome: result ? "provider" : rag.citations.length ? "fallback" : "empty", route: route.profile });
    if (request.chatId.trim()) this.history.appendExchange(tenantId, historyType, request.chatId, request.prompt, answer);
    return responseOf(request, traceId, route, answer, result?.model ?? "local-rag", actualInputTokens, outputTokens, result?.degraded ?? !result, {
      citations: rag.citations,
      evidence: rag.evidence,
      retrievalStats: rag.retrievalStats,
      trace: [
        {
          step: 1,
          thoughtSummary: "Retrieved and judged tenant-scoped evidence.",
          action: "hybrid_retrieve",
          actionInput: { chatId: request.chatId, tenantId },
          observation: { citations: rag.citations.length, retrievalStats: rag.retrievalStats }
        },
        {
          step: 2,
          thoughtSummary: "Generated an evidence-grounded answer.",
          action: result ? "llm_generate" : "explicit_rag_fallback",
          observation: { model: result?.model ?? "local-rag", degraded: result?.degraded ?? !result }
        }
      ]
    });
  }

  async *stream(request: ReactChatRequest, tenantId = "public", historyType = "pdf", traceId = newId("trace"), signal?: AbortSignal): AsyncGenerator<SseEvent> {
    validateRequest(request);
    const rag = await this.retrieval.answerAsync(request.prompt, tenantId, request.chatId);
    const route = this.modelRouter.resolve(request.modelProfile, "rag", tenantId, request.chatId);
    const inputTokens = this.cost.estimateTokens([request.prompt, ...rag.evidence].join("\n"));
    this.cost.assertBudget(tenantId, route.costTier, inputTokens, 600);
    yield {
      event: "trace",
      data: {
        step: 1,
        thoughtSummary: "Retrieved and judged tenant-scoped evidence.",
        action: "hybrid_retrieve",
        actionInput: { chatId: request.chatId, tenantId },
        observation: { citations: rag.citations.length, retrievalStats: rag.retrievalStats }
      }
    };
    let answer = "";
    let model = route.model;
    let degraded = false;
    if (rag.citations.length > 0) {
      try {
        for await (const chunk of this.llm.streamComplete({
          prompt: request.prompt,
          route,
          groundedContext: rag.evidence,
          memoryContext: [],
          systemPrompt: env.RAG_ANSWER_SYSTEM_PROMPT,
          temperature: env.RAG_TEMPERATURE
        }, signal)) {
          answer += chunk.token;
          model = chunk.model;
          degraded = chunk.degraded;
          yield { event: "token", data: { token: chunk.token } };
        }
      } catch (error) {
        if (signal?.aborted || answer) throw error;
        answer = explicitFallback("rag", rag.answer);
        model = "local-rag";
        degraded = true;
        this.metrics.increment("llm_stream_fallback_total", { route: route.profile, flow: "rag" });
        yield { event: "token", data: { token: answer, fallback: true } };
      }
    }
    if (!answer) {
      answer = rag.citations.length === 0 ? rag.answer : explicitFallback("rag", rag.answer);
      model = "local-rag";
      degraded = rag.citations.length > 0;
      yield { event: "token", data: { token: answer, fallback: degraded } };
    }
    const outputTokens = this.cost.estimateTokens(answer);
    this.cost.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    if (request.chatId.trim()) this.history.appendExchange(tenantId, historyType, request.chatId, request.prompt, answer);
    const response = responseOf(request, traceId, route, answer, model, inputTokens, outputTokens, degraded, {
      citations: rag.citations,
      evidence: rag.evidence,
      retrievalStats: rag.retrievalStats,
      trace: [{
        step: 1,
        thoughtSummary: "Retrieved evidence and streamed the grounded answer.",
        action: "rag_stream",
        observation: { citations: rag.citations.length, model, degraded }
      }]
    });
    yield { event: "done", data: { ok: 1, msg: "ok", data: stripEnvelope(response) } };
  }
}
