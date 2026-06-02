import { Injectable } from "@nestjs/common";
import type { Citation, ReactChatRequest, ReactChatResponse } from "@knowledgeops/shared";

import { HistoryService } from "../history/history.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { BusinessToolsService } from "../platform/business-tools.service.js";
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
    private readonly llmClient: OpenAiCompatibleClient,
    private readonly businessTools: BusinessToolsService
  ) {}

  async reactChat(request: ReactChatRequest, tenantId = "public", historyType = "react", traceId = newId("trace")): Promise<ReactChatResponse> {
    const started = Date.now();
    const prompt = request.prompt || "";
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    const toolAnswer = await this.educationToolAnswer(prompt).catch(() => undefined);
    const rag = await this.retrievalService.answerAsync(prompt, tenantId, request.chatId);
    const memoryUsed = this.relevantMemory(tenantId, prompt);
    const context = [prompt, ...(toolAnswer?.evidence ?? []), ...rag.evidence, ...memoryUsed].join("\n");
    const estimatedInputTokens = this.costService.estimateTokens(context);
    const localAnswer = composeAnswer(toolAnswer?.answer ?? rag.answer, memoryUsed);
    const estimatedOutputTokens = this.costService.estimateTokens(localAnswer);
    this.costService.assertBudget(tenantId, route.costTier, estimatedInputTokens, estimatedOutputTokens);
    const llmResult = await this.generateWithFallback({
      prompt,
      route,
      groundedContext: [...(toolAnswer?.evidence ?? []), ...rag.evidence],
      memoryContext: memoryUsed
    });
    const finalAnswer = llmResult?.answer ?? localAnswer;
    const inputTokens = llmResult?.inputTokens ?? estimatedInputTokens;
    const outputTokens = llmResult?.outputTokens ?? this.costService.estimateTokens(finalAnswer);
    const model = llmResult?.model ?? route.model;
    this.costService.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    this.metrics.increment("react_requests_total", { outcome: "success", route: route.profile });
    this.metrics.increment("react_latency_ms_sum", { route: route.profile }, Date.now() - started);
    this.metrics.observe("react_latency_ms", Date.now() - started, { route: route.profile });

    const response = {
      ok: 1,
      msg: "ok",
      chatId: request.chatId,
      answer: finalAnswer,
      model,
      usage: {
        inputTokens,
        outputTokens,
        totalTokens: inputTokens + outputTokens,
        costUsd: this.costService.calculateCost(route.costTier, inputTokens + outputTokens)
      },
      traceId,
      citations: [...(toolAnswer?.citations ?? []), ...rag.citations],
      evidence: [...(toolAnswer?.evidence ?? []), ...rag.evidence],
      retrievalStats: rag.retrievalStats,
      routeProfile: route.profile,
      routeReason: route.reason,
      routeCostTier: route.costTier,
      experimentKey: route.experimentKey,
      experimentVariant: route.experimentVariant,
      experimentBucket: route.experimentBucket,
      trace: [
        {
          step: 1,
          thoughtSummary: "Resolved model profile, budget, memory, and hybrid retrieval context.",
          action: toolAnswer ? toolAnswer.action : "hybrid_retrieve",
          actionInput: { prompt, chatId: request.chatId, tenantId, model: route.model },
          observation: {
            citations: rag.citations.length + (toolAnswer?.citations.length ?? 0),
            evidence: rag.evidence.length + (toolAnswer?.evidence.length ?? 0),
            memoryUsed: memoryUsed.length,
            retrievalStats: rag.retrievalStats
          }
        },
        {
          step: 2,
          thoughtSummary: "Generated a grounded answer using the routed model or deterministic local fallback.",
          action: llmResult?.degraded === false ? "llm_generate" : "local_fallback",
          actionInput: { routeProfile: route.profile },
          observation: {
            status: "completed",
            model,
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
    const done = JSON.stringify({ ok: 1, msg: "ok", data: responseData(response) });
    return `${trace}event: token\ndata: ${token}\n\nevent: done\ndata: ${done}\n\n`;
  }

  async reactChatStream(request: ReactChatRequest, tenantId = "public", historyType = "react", traceId = newId("trace")): Promise<string> {
    const started = Date.now();
    const prompt = request.prompt || "";
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    const toolAnswer = await this.educationToolAnswer(prompt).catch(() => undefined);
    const rag = await this.retrievalService.answerAsync(prompt, tenantId, request.chatId);
    const memoryUsed = this.relevantMemory(tenantId, prompt);
    const localAnswer = composeAnswer(toolAnswer?.answer ?? rag.answer, memoryUsed);
    const estimatedInputTokens = this.costService.estimateTokens([prompt, ...(toolAnswer?.evidence ?? []), ...rag.evidence, ...memoryUsed].join("\n"));
    const estimatedOutputTokens = this.costService.estimateTokens(localAnswer);
    this.costService.assertBudget(tenantId, route.costTier, estimatedInputTokens, estimatedOutputTokens);

    const trace = {
      step: 1,
      thoughtSummary: "Resolved route and streamed provider tokens from grounded retrieval context.",
      action: toolAnswer ? toolAnswer.action : "llm_stream",
      actionInput: { prompt, chatId: request.chatId, tenantId, model: route.model },
      observation: {
        citations: rag.citations.length + (toolAnswer?.citations.length ?? 0),
        evidence: rag.evidence.length + (toolAnswer?.evidence.length ?? 0),
        memoryUsed: memoryUsed.length,
        retrievalStats: rag.retrievalStats
      }
    };
    let answer = "";
    let sse = `event: trace\ndata: ${JSON.stringify(trace)}\n\n`;
    try {
      for await (const chunk of this.llmClient.streamComplete({
        prompt,
        route,
        groundedContext: [...(toolAnswer?.evidence ?? []), ...rag.evidence],
        memoryContext: memoryUsed
      })) {
        answer += chunk.token;
        sse += `event: token\ndata: ${JSON.stringify({ token: chunk.token })}\n\n`;
      }
    } catch (error) {
      this.metrics.increment("llm_stream_fallback_total", { route: route.profile });
      sse += `event: error\ndata: ${JSON.stringify({ message: error instanceof Error ? error.message : String(error) })}\n\n`;
    }

    if (!answer.trim()) {
      const fallback = await this.reactChat(request, tenantId, historyType, traceId);
      return this.textStream(fallback);
    }
    const outputTokens = this.costService.estimateTokens(answer);
    const model = route.model;
    this.costService.recordUsage(tenantId, route.costTier, estimatedInputTokens, outputTokens);
    this.metrics.increment("react_stream_requests_total", { outcome: "success", route: route.profile });
    this.metrics.observe("react_stream_latency_ms", Date.now() - started, { route: route.profile });
    const response: ReactChatResponse = {
      ok: 1,
      msg: "ok",
      chatId: request.chatId,
      answer,
      model,
      usage: {
        inputTokens: estimatedInputTokens,
        outputTokens,
        totalTokens: estimatedInputTokens + outputTokens,
        costUsd: this.costService.calculateCost(route.costTier, estimatedInputTokens + outputTokens)
      },
      traceId,
      citations: [...(toolAnswer?.citations ?? []), ...rag.citations],
      evidence: [...(toolAnswer?.evidence ?? []), ...rag.evidence],
      retrievalStats: rag.retrievalStats,
      routeProfile: route.profile,
      routeReason: route.reason,
      routeCostTier: route.costTier,
      experimentKey: route.experimentKey,
      experimentVariant: route.experimentVariant,
      experimentBucket: route.experimentBucket,
      trace: [
        trace,
        {
          step: 2,
          thoughtSummary: "Finished provider streaming response and persisted usage/history.",
          action: "finish",
          observation: { status: "completed", model, inputTokens: estimatedInputTokens, outputTokens }
        }
      ]
    };
    if (request.chatId?.trim()) {
      this.historyService.appendExchange(tenantId, historyType, request.chatId, prompt, answer);
      this.saveConversationSummary(tenantId, request.chatId, prompt, answer);
    }
    sse += `event: done\ndata: ${JSON.stringify({ ok: 1, msg: "ok", data: responseData(response) })}\n\n`;
    return sse;
  }

  saveFeedback(tenantId: string, payload: Record<string, unknown>): void {
    this.store.feedback.push({ tenantId, ...payload, createdAt: new Date().toISOString() });
    this.store.persist();
  }

  private async educationToolAnswer(prompt: string): Promise<{ action: string; answer: string; citations: Citation[]; evidence: string[] } | undefined> {
    const normalized = prompt.toLowerCase();
    if (containsAny(normalized, ["校区", "campus"])) {
      const schools = await this.businessTools.querySchool();
      return {
        action: "query_school",
        answer: `可以参考这些校区：\n${markdownTable(["校区", "城市"], schools.map((school) => [school.name, school.city ?? ""]))}`,
        citations: [builtinCitation("query_school", "School catalog", schools.map((school) => school.name).join(", "))],
        evidence: schools.map((school) => `校区：${school.name}，城市：${school.city ?? "未知"}`)
      };
    }
    if (containsAny(normalized, ["课程", "编程", "设计", "自媒体", "course"])) {
      const courses = await this.businessTools.queryCourse({
        type: inferCourseType(prompt),
        edu: inferEducationLevel(prompt),
        sorts: [{ field: "duration", isAsc: true }]
      });
      return {
        action: "query_course",
        answer: `可以参考这些课程：\n${markdownTable(["课程", "类型", "学历要求", "学习时长(天)"], courses.map((course) => [
          course.name,
          course.type ?? "",
          educationLabel(course.edu),
          String(course.duration ?? "")
        ]))}`,
        citations: [builtinCitation("query_course", "Course catalog", courses.map((course) => course.name).join(", "))],
        evidence: courses.map((course) => `课程：${course.name}，类型：${course.type ?? "未分类"}，学历要求：${educationLabel(course.edu)}，学习时长：${course.duration ?? "未知"}天`)
      };
    }
    return undefined;
  }

  private relevantMemory(tenantId: string, prompt: string): string[] {
    const tokens = prompt.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    return this.store.memoryItems
      .filter((item) => item.tenantId === tenantId && (!item.expiresAt || Date.parse(item.expiresAt) > Date.now()))
      .slice(-500)
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
    const now = new Date().toISOString();
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
    const existing = this.store.memoryItems.find((item) => item.tenantId === tenantId && item.source === "chat_summary" && item.sourceTaskId === chatId);
    if (existing) {
      existing.content = content;
      existing.updatedAt = now;
      existing.expiresAt = expiresAt;
      return;
    }
    this.store.memoryItems.push({
      memoryId: newId("mem"),
      tenantId,
      userId: "anonymous",
      type: "short",
      content,
      source: "chat_summary",
      sourceTaskId: chatId,
      confidence: 0.6,
      expiresAt,
      createdAt: now,
      updatedAt: now
    });
    this.store.persist();
  }
}

function responseData(response: ReactChatResponse) {
  const { ok: _ok, msg: _msg, ...data } = response;
  return data;
}

function builtinCitation(action: string, title: string, snippet: string): Citation {
  return {
    id: `cite-${action}`,
    source: `builtin://${action}`,
    title,
    chunkId: "builtin:1",
    snippet: snippet || title
  };
}

function containsAny(value: string, needles: string[]): boolean {
  return needles.some((needle) => value.includes(needle.toLowerCase()));
}

function inferCourseType(prompt: string): string | undefined {
  if (prompt.includes("设计")) {
    return "设计";
  }
  if (prompt.includes("自媒体") || prompt.includes("短视频")) {
    return "自媒体";
  }
  if (prompt.includes("编程") || prompt.toLowerCase().includes("java") || prompt.toLowerCase().includes("python")) {
    return "编程";
  }
  return undefined;
}

function inferEducationLevel(prompt: string): number | undefined {
  if (prompt.includes("本科")) {
    return 4;
  }
  if (prompt.includes("大专")) {
    return 3;
  }
  if (prompt.includes("高中")) {
    return 2;
  }
  if (prompt.includes("初中")) {
    return 1;
  }
  if (prompt.includes("零基础") || prompt.includes("无学历")) {
    return 0;
  }
  return undefined;
}

function educationLabel(value: number | undefined): string {
  return ["无", "初中", "高中", "大专", "本科以上"][value ?? 0] ?? "未知";
}

function markdownTable(headers: string[], rows: string[][]): string {
  if (rows.length === 0) {
    return "暂无匹配结果。";
  }
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.join(" | ")} |`)
  ].join("\n");
}

function composeAnswer(ragAnswer: string, memoryUsed: string[]): string {
  if (memoryUsed.length === 0) {
    return ragAnswer;
  }
  return `${ragAnswer}\n\n记忆上下文:\n${memoryUsed.map((item) => `- ${item}`).join("\n")}`;
}
