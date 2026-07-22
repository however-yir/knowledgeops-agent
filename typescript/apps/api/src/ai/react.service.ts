import { Injectable } from "@nestjs/common";
import type { Citation, ReactChatRequest, ReactChatResponse, ReactTraceStep } from "@knowledgeops/shared";

import { newId } from "../common/ids.js";
import { env } from "../config/env.js";
import { HistoryService } from "../history/history.service.js";
import { BusinessToolsService } from "../platform/business-tools.service.js";
import { MetricsService } from "../platform/metrics.service.js";
import { ModelRouterService } from "../platform/model-router.service.js";
import { TenantCostService } from "../platform/tenant-cost.service.js";
import { explicitFallback, responseOf, stripEnvelope, validateRequest } from "./chat.service.js";
import { OpenAiCompatibleClient } from "./llm.client.js";
import { RetrievalService } from "./retrieval.service.js";
import type { SseEvent } from "./sse.js";

interface PlanDecision {
  thought: string;
  action: "query_school" | "query_course" | "rag_search" | "finish";
  actionInput: Record<string, unknown>;
  answer: string;
}

@Injectable()
export class ReactService {
  constructor(
    private readonly retrieval: RetrievalService,
    private readonly history: HistoryService,
    private readonly modelRouter: ModelRouterService,
    private readonly cost: TenantCostService,
    private readonly metrics: MetricsService,
    private readonly llm: OpenAiCompatibleClient,
    private readonly tools: BusinessToolsService
  ) {}

  async chat(request: ReactChatRequest, tenantId = "public", historyType = "react", traceId = newId("trace"), signal?: AbortSignal): Promise<ReactChatResponse> {
    validateRequest(request);
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    this.cost.assertBudget(tenantId, route.costTier, this.cost.estimateTokens(request.prompt), 600);
    const execution = await this.execute(request, tenantId, route, signal);
    const prompt = finalPrompt(request.prompt, execution.trace);
    const estimatedInputTokens = this.cost.estimateTokens(prompt);
    this.cost.assertBudget(tenantId, route.costTier, estimatedInputTokens, 600);
    let result;
    if (!execution.answer) {
      try {
        result = await this.llm.completeText({
          systemPrompt: env.APP_REACT_FINAL_SYSTEM_PROMPT,
          userPrompt: prompt,
          route
        }, signal);
      } catch (error) {
        if (signal?.aborted) throw error;
        this.metrics.increment("llm_fallback_total", { route: route.profile, flow: "react" });
      }
    }
    const localAnswer = localAnswerFromTrace(execution.trace);
    const answer = execution.answer || result?.answer || explicitFallback("react", localAnswer);
    const inputTokens = result?.inputTokens ?? estimatedInputTokens;
    const outputTokens = result?.outputTokens ?? this.cost.estimateTokens(answer);
    this.cost.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    this.metrics.increment("react_requests_total", { outcome: execution.answer ? "planner" : result ? "provider" : "fallback", route: route.profile });
    if (request.chatId.trim()) this.history.appendExchange(tenantId, historyType, request.chatId, request.prompt, answer);
    return responseOf(
      request,
      traceId,
      route,
      answer,
      execution.answer ? "planner" : result?.model ?? "local-react",
      inputTokens,
      outputTokens,
      execution.answer ? false : result?.degraded ?? !result,
      {
        citations: execution.citations,
        evidence: execution.evidence,
        trace: execution.trace
      }
    );
  }

  async *stream(request: ReactChatRequest, tenantId = "public", historyType = "react", traceId = newId("trace"), signal?: AbortSignal): AsyncGenerator<SseEvent> {
    validateRequest(request);
    const route = this.modelRouter.resolve(request.modelProfile, historyType, tenantId, request.chatId);
    this.cost.assertBudget(tenantId, route.costTier, this.cost.estimateTokens(request.prompt), 600);
    const trace: ReactTraceStep[] = [];
    let directAnswer = "";
    for (let step = 1; step <= env.APP_REACT_MAX_STEPS; step += 1) {
      const decision = await this.plan(request.prompt, trace, route, signal);
      if (decision.action === "finish") {
        directAnswer = decision.answer;
        const traceStep: ReactTraceStep = {
          step,
          thoughtSummary: decision.thought,
          action: "finish",
          actionInput: decision.actionInput,
          observation: { status: "completed" }
        };
        trace.push(traceStep);
        yield { event: "trace", data: traceStep };
        break;
      }
      const observation = await this.executeAction(decision, tenantId, request.chatId);
      const traceStep: ReactTraceStep = {
        step,
        thoughtSummary: decision.thought,
        action: decision.action,
        actionInput: decision.actionInput,
        observation
      };
      trace.push(traceStep);
      yield { event: "trace", data: traceStep };
    }
    const { citations, evidence } = collectGrounding(trace);
    const prompt = finalPrompt(request.prompt, trace);
    const inputTokens = this.cost.estimateTokens(prompt);
    this.cost.assertBudget(tenantId, route.costTier, inputTokens, 600);
    let answer = "";
    let model = route.model;
    let degraded = false;
    if (directAnswer) {
      answer = directAnswer;
      model = "planner";
      yield { event: "token", data: { token: directAnswer } };
    } else {
      try {
        for await (const chunk of this.llm.streamText({ systemPrompt: env.APP_REACT_FINAL_SYSTEM_PROMPT, userPrompt: prompt, route }, signal)) {
          answer += chunk.token;
          model = chunk.model;
          degraded = chunk.degraded;
          yield { event: "token", data: { token: chunk.token } };
        }
      } catch (error) {
        if (signal?.aborted || answer) throw error;
        answer = explicitFallback("react", localAnswerFromTrace(trace));
        model = "local-react";
        degraded = true;
        this.metrics.increment("llm_stream_fallback_total", { route: route.profile, flow: "react" });
        yield { event: "token", data: { token: answer, fallback: true } };
      }
    }
    if (!answer) {
      answer = explicitFallback("react", localAnswerFromTrace(trace));
      model = "local-react";
      degraded = true;
      yield { event: "token", data: { token: answer, fallback: true } };
    }
    const outputTokens = this.cost.estimateTokens(answer);
    this.cost.recordUsage(tenantId, route.costTier, inputTokens, outputTokens);
    if (request.chatId.trim()) this.history.appendExchange(tenantId, historyType, request.chatId, request.prompt, answer);
    const response = responseOf(request, traceId, route, answer, model, inputTokens, outputTokens, degraded, { citations, evidence, trace });
    yield { event: "done", data: { ok: 1, msg: "ok", data: stripEnvelope(response) } };
  }

  private async execute(
    request: ReactChatRequest,
    tenantId: string,
    route: ReturnType<ModelRouterService["resolve"]>,
    signal?: AbortSignal
  ): Promise<{ trace: ReactTraceStep[]; answer: string; citations: Citation[]; evidence: string[] }> {
    const trace: ReactTraceStep[] = [];
    let answer = "";
    for (let step = 1; step <= env.APP_REACT_MAX_STEPS; step += 1) {
      const decision = await this.plan(request.prompt, trace, route, signal);
      if (decision.action === "finish") {
        answer = decision.answer;
        trace.push({ step, thoughtSummary: decision.thought, action: "finish", actionInput: decision.actionInput, observation: { status: "completed" } });
        break;
      }
      const observation = await this.executeAction(decision, tenantId, request.chatId);
      trace.push({ step, thoughtSummary: decision.thought, action: decision.action, actionInput: decision.actionInput, observation });
    }
    return { trace, answer, ...collectGrounding(trace) };
  }

  private async plan(prompt: string, trace: ReactTraceStep[], route: ReturnType<ModelRouterService["resolve"]>, signal?: AbortSignal): Promise<PlanDecision> {
    const planningPrompt = [
      "Choose one action: query_school, query_course, rag_search, finish.",
      "Return JSON only: {\"thought\":\"short\",\"action\":\"...\",\"action_input\":{},\"answer\":\"only for finish\"}.",
      `User question: ${prompt}`,
      `Existing trace: ${JSON.stringify(trace)}`
    ].join("\n");
    try {
      const result = await this.llm.completeText({ systemPrompt: env.APP_REACT_PLANNER_SYSTEM_PROMPT, userPrompt: planningPrompt, route, temperature: 0 }, signal);
      if (result?.answer) return parseDecision(result.answer);
    } catch (error) {
      if (signal?.aborted) throw error;
      this.metrics.increment("react_planner_fallback_total", { route: route.profile });
    }
    return fallbackDecision(prompt, trace);
  }

  private async executeAction(decision: PlanDecision, tenantId: string, chatId: string): Promise<Record<string, unknown>> {
    if (decision.action === "query_school") {
      const schools = await this.tools.querySchool();
      return { status: "success", data: schools, evidence: schools.map((school) => `校区：${school.name}，城市：${school.city ?? "未知"}`) };
    }
    if (decision.action === "query_course") {
      const courses = await this.tools.queryCourse(decision.actionInput);
      return { status: "success", data: courses, evidence: courses.map((course) => `课程：${course.name}，类型：${course.type ?? "未分类"}`) };
    }
    const rag = await this.retrieval.answerAsync(String(decision.actionInput.query ?? ""), tenantId, chatId);
    return { status: "success", answer: rag.answer, citations: rag.citations, evidence: rag.evidence, retrievalStats: rag.retrievalStats };
  }
}

function parseDecision(raw: string): PlanDecision {
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end <= start) return { thought: "Planner returned plain text.", action: "finish", actionInput: {}, answer: raw.trim() };
  const parsed = JSON.parse(raw.slice(start, end + 1)) as Record<string, unknown>;
  const action = String(parsed.action ?? "finish").toLowerCase();
  const allowed = ["query_school", "query_course", "rag_search", "finish"].includes(action) ? action : "finish";
  return {
    thought: String(parsed.thought ?? ""),
    action: allowed as PlanDecision["action"],
    actionInput: isRecord(parsed.action_input) ? parsed.action_input : {},
    answer: String(parsed.answer ?? "")
  };
}

function fallbackDecision(prompt: string, trace: ReactTraceStep[]): PlanDecision {
  if (trace.length > 0) return { thought: "Deterministic planner completed after tool observation.", action: "finish", actionInput: {}, answer: "" };
  const normalized = prompt.toLowerCase();
  if (["校区", "campus"].some((keyword) => normalized.includes(keyword))) {
    return { thought: "Deterministic route for school query.", action: "query_school", actionInput: {}, answer: "" };
  }
  if (["课程", "course", "编程", "设计"].some((keyword) => normalized.includes(keyword))) {
    return { thought: "Deterministic route for course query.", action: "query_course", actionInput: {}, answer: "" };
  }
  if (["知识库", "引用", "pdf", "文档", "source"].some((keyword) => normalized.includes(keyword))) {
    return { thought: "Deterministic route for RAG search.", action: "rag_search", actionInput: { query: prompt }, answer: "" };
  }
  return { thought: "No safe tool route matched.", action: "finish", actionInput: {}, answer: "当前规划器不可用，请细化问题或稍后重试。" };
}

function finalPrompt(prompt: string, trace: ReactTraceStep[]): string {
  return `用户问题:\n${prompt}\n\nReAct轨迹:\n${JSON.stringify(trace)}\n\n请基于工具观察给出简洁、可执行的最终答案。`;
}

function localAnswerFromTrace(trace: ReactTraceStep[]): string {
  for (let index = trace.length - 1; index >= 0; index -= 1) {
    const observation = trace[index]?.observation;
    if (!isRecord(observation)) continue;
    if (typeof observation.answer === "string" && observation.answer.trim()) return observation.answer;
    if (Array.isArray(observation.data) && observation.data.length) return JSON.stringify(observation.data, null, 2);
  }
  return "当前未能生成最终答案，请稍后重试。";
}

function collectGrounding(trace: ReactTraceStep[]): { citations: Citation[]; evidence: string[] } {
  const citations: Citation[] = [];
  const evidence: string[] = [];
  for (const step of trace) {
    if (!isRecord(step.observation)) continue;
    if (Array.isArray(step.observation.citations)) citations.push(...step.observation.citations.filter(isCitation));
    if (Array.isArray(step.observation.evidence)) evidence.push(...step.observation.evidence.map(String));
  }
  return {
    citations: [...new Map(citations.map((citation) => [citation.id, citation])).values()],
    evidence: [...new Set(evidence)]
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCitation(value: unknown): value is Citation {
  return isRecord(value) && typeof value.id === "string" && typeof value.source === "string"
    && typeof value.title === "string" && typeof value.chunkId === "string" && typeof value.snippet === "string";
}
