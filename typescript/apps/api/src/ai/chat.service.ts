import { Injectable } from "@nestjs/common";
import type { ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { newId } from "../common/ids.js";
import { env } from "../config/env.js";
import { HistoryService } from "../history/history.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { TenantCostService } from "../platform/tenant-cost.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import type { SseEvent } from "./sse.js";

@Injectable()
export class ChatService {
  constructor(
    private readonly history: HistoryService,
    private readonly modelRouter: ModelRouterService,
    private readonly cost: TenantCostService,
    private readonly metrics: MetricsService,
    private readonly llm: OpenAiCompatibleClient
  ) {}

  async chat(request: ReactChatRequest, tenantId = "public", historyType = "chat", traceId = newId("trace"), signal?: AbortSignal): Promise<ReactChatResponse> {
    validateRequest(request);
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    const inputTokens = this.cost.estimateTokens(request.prompt);
    this.cost.assertBudget(tenantId, route.costTier, inputTokens, 600);
    let result;
    try {
      result = await this.llm.completeText({
        systemPrompt: env.APP_LLM_SYSTEM_PROMPT,
        userPrompt: request.prompt,
        route
      }, signal);
    } catch (error) {
      if (signal?.aborted) throw error;
      this.metrics.increment("llm_fallback_total", { route: route.profile, flow: "chat" });
    }
    const answer = result?.answer ?? explicitFallback("chat");
    const outputTokens = result?.outputTokens ?? this.cost.estimateTokens(answer);
    const actualInputTokens = result?.inputTokens ?? inputTokens;
    this.cost.recordUsage(tenantId, route.costTier, actualInputTokens, outputTokens);
    this.metrics.increment("chat_requests_total", { outcome: result ? "provider" : "fallback", route: route.profile });
    this.saveHistory(tenantId, historyType, request, answer);
    return responseOf(request, traceId, route, answer, result?.model ?? "local-fallback", actualInputTokens, outputTokens, result?.degraded ?? true);
  }

  async *stream(request: ReactChatRequest, tenantId = "public", historyType = "chat", traceId = newId("trace"), signal?: AbortSignal): AsyncGenerator<SseEvent> {
    validateRequest(request);
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    const inputTokens = this.cost.estimateTokens(request.prompt);
    this.cost.assertBudget(tenantId, route.costTier, inputTokens, 600);
    yield {
      event: "trace",
      data: { step: 1, thoughtSummary: "Resolved direct chat model route.", action: "llm_stream", actionInput: { model: route.model } }
    };
    let answer = "";
    let model = route.model;
    let degraded = false;
    try {
      for await (const chunk of this.llm.streamText({ systemPrompt: env.APP_LLM_SYSTEM_PROMPT, userPrompt: request.prompt, route }, signal)) {
        answer += chunk.token;
        model = chunk.model;
        degraded = chunk.degraded;
        yield { event: "token", data: { token: chunk.token } };
      }
    } catch (error) {
      if (signal?.aborted || answer) throw error;
      const fallback = explicitFallback("chat");
      answer = fallback;
      model = "local-fallback";
      degraded = true;
      this.metrics.increment("llm_stream_fallback_total", { route: route.profile, flow: "chat" });
      yield { event: "token", data: { token: fallback, fallback: true } };
    }
    if (!answer) {
      const fallback = explicitFallback("chat");
      answer = fallback;
      model = "local-fallback";
      degraded = true;
      yield { event: "token", data: { token: fallback, fallback: true } };
    }
    const outputTokens = this.cost.estimateTokens(answer);
    this.cost.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    this.saveHistory(tenantId, historyType, request, answer);
    yield { event: "done", data: { ok: 1, msg: "ok", data: stripEnvelope(responseOf(request, traceId, route, answer, model, inputTokens, outputTokens, degraded)) } };
  }

  private saveHistory(tenantId: string, historyType: string, request: ReactChatRequest, answer: string): void {
    if (request.chatId.trim()) this.history.appendExchange(tenantId, historyType, request.chatId, request.prompt, answer);
  }
}

export function validateRequest(request: ReactChatRequest): void {
  if (!request?.prompt?.trim()) throw new Error("prompt is required");
  if (!request.chatId?.trim()) throw new Error("chatId is required");
}

export function explicitFallback(flow: string, localAnswer?: string): string {
  if (!env.APP_LLM_LOCAL_FALLBACK_ENABLED) {
    throw new Error(`LLM provider unavailable for ${flow}; local fallback is disabled`);
  }
  return localAnswer?.trim() || "模型服务当前不可用，已启用本地兜底，但没有足够信息生成可靠答案。";
}

export function responseOf(
  request: ReactChatRequest,
  traceId: string,
  route: ReturnType<ModelRouterService["resolve"]>,
  answer: string,
  model: string,
  inputTokens: number,
  outputTokens: number,
  degraded: boolean,
  extra: Partial<ReactChatResponse> = {}
): ReactChatResponse {
  return {
    ok: 1,
    msg: "ok",
    chatId: request.chatId,
    answer,
    model,
    usage: {
      inputTokens,
      outputTokens,
      totalTokens: inputTokens + outputTokens,
      costUsd: 0
    },
    traceId,
    routeProfile: route.profile,
    routeReason: route.reason,
    routeCostTier: route.costTier,
    experimentKey: route.experimentKey,
    experimentVariant: route.experimentVariant,
    experimentBucket: route.experimentBucket,
    trace: [{
      step: 1,
      thoughtSummary: "Completed direct model generation.",
      action: degraded ? "explicit_fallback" : "llm_generate",
      observation: { model, degraded }
    }],
    ...extra
  };
}

export function stripEnvelope(response: ReactChatResponse): Omit<ReactChatResponse, "ok" | "msg"> {
  const { ok: _ok, msg: _msg, ...data } = response;
  return data;
}
